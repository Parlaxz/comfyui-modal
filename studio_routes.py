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
string) and use appropriate HTTP status codes.
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from studio_models import (
    _KNOWN_FEATURE_IDS,
    _normalize_label,
    _sanitize_description,
    _validate_feature_ids,
    normalize_preset_payload,
    normalize_snapshot_payload,
)
from studio_store import StudioJsonStore, StudioStoreError

# ── Helpers ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_snapshot_id() -> str:
    return f"snap_{uuid.uuid4().hex[:16]}"


def _make_preset_id() -> str:
    return f"preset_{uuid.uuid4().hex[:16]}"


def _build_snapshots_by_id(snapshots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {s.get("id", ""): s for s in snapshots if s.get("id")}


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
            if not include_archived:
                snapshots = [s for s in snapshots if not s.get("archived")]
            return web.json_response({"status": "ok", "snapshots": snapshots})
        except StudioStoreError as exc:
            return _json_error(500, str(exc.args[0]) if exc.args else "Store read error")
        except OSError as exc:
            return _json_error(500, f"Storage error: {exc}")

    @server.routes.post("/comfymodal/studio/snapshots")
    async def studio_snapshots_create(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return _json_error(400, "Invalid JSON body")
        except Exception:
            return _json_error(400, "Request body could not be read")

        now = _now_iso()
        features = _validate_feature_ids(body.get("compatibleFeatures", []))

        # Reject entirely unknown feature sets with a stable message
        raw_features = body.get("compatibleFeatures", [])
        if isinstance(raw_features, list) and raw_features:
            if not features:
                return _json_error(400, "Invalid compatible feature")

        entry: dict[str, Any] = {
            "id": _make_snapshot_id(),
            "name": _normalize_label(body.get("name", "Untitled Snapshot")),
            "description": _sanitize_description(body.get("description", "")),
            "createdAt": now,
            "updatedAt": now,
            "compatibleFeatures": features,
            "graphJson": body.get("graphJson"),
            "apiPromptJson": body.get("apiPromptJson"),
            "nodeBindings": body.get("nodeBindings", {}),
            "outputNodeId": body.get("outputNodeId", ""),
            "modelSummary": body.get("modelSummary", ""),
            "source": _normalize_label(body.get("source", "manual")),
            "archived": False,
            "disabledReason": body.get("disabledReason", ""),
        }

        # Derive status and featureStatus via the normalisation function
        enriched = normalize_snapshot_payload(entry)
        entry["status"] = enriched.get("status", "runnable")
        entry["featureStatus"] = enriched.get("featureStatus", {})

        try:
            snapshots = _snapshots_store.read()
            snapshots.append(entry)
            _snapshots_store.write_atomic(snapshots)
        except StudioStoreError as exc:
            return _json_error(500, str(exc.args[0]) if exc.args else "Store write error")
        except OSError as exc:
            return _json_error(500, f"Storage error: {exc}")

        return web.json_response({"status": "ok", "snapshot": entry})

    @server.routes.get("/comfymodal/studio/snapshots/{snapshot_id}")
    async def studio_snapshots_detail(request: web.Request) -> web.Response:
        sid = request.match_info.get("snapshot_id", "")
        try:
            snapshots = _snapshots_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        for s in snapshots:
            if s.get("id") == sid:
                return web.json_response({"status": "ok", "snapshot": s})
        return _json_error(404, "Snapshot not found")

    @server.routes.patch("/comfymodal/studio/snapshots/{snapshot_id}")
    async def studio_snapshots_update(request: web.Request) -> web.Response:
        sid = request.match_info.get("snapshot_id", "")
        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "Invalid JSON body")

        try:
            snapshots = _snapshots_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        for s in snapshots:
            if s.get("id") == sid:
                if "name" in body and isinstance(body["name"], str):
                    s["name"] = _normalize_label(body["name"])
                if "description" in body and isinstance(body["description"], str):
                    s["description"] = _sanitize_description(body["description"])
                if "compatibleFeatures" in body:
                    s["compatibleFeatures"] = _validate_feature_ids(body["compatibleFeatures"])
                if "modelSummary" in body and isinstance(body["modelSummary"], str):
                    s["modelSummary"] = body["modelSummary"].strip()
                if "nodeBindings" in body and isinstance(body["nodeBindings"], dict):
                    s["nodeBindings"] = body["nodeBindings"]
                if "outputNodeId" in body and isinstance(body["outputNodeId"], str):
                    s["outputNodeId"] = body["outputNodeId"]
                if "disabledReason" in body and isinstance(body["disabledReason"], str):
                    s["disabledReason"] = body["disabledReason"].strip()
                if "archived" in body:
                    s["archived"] = bool(body["archived"])

                s["updatedAt"] = _now_iso()
                # Re-derive status after update
                enriched = normalize_snapshot_payload(s)
                s["status"] = enriched.get("status", "runnable")
                s["featureStatus"] = enriched.get("featureStatus", {})

                try:
                    _snapshots_store.write_atomic(snapshots)
                except (StudioStoreError, OSError) as exc:
                    return _json_error(500, f"Storage error: {exc}")
                return web.json_response({"status": "ok", "snapshot": s})

        return _json_error(404, "Snapshot not found")

    @server.routes.delete("/comfymodal/studio/snapshots/{snapshot_id}")
    async def studio_snapshots_archive(request: web.Request) -> web.Response:
        """Archive (soft-delete) a snapshot by marking ``archived=True``."""
        sid = request.match_info.get("snapshot_id", "")
        try:
            snapshots = _snapshots_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        for s in snapshots:
            if s.get("id") == sid:
                s["archived"] = True
                s["updatedAt"] = _now_iso()
                try:
                    _snapshots_store.write_atomic(snapshots)
                except (StudioStoreError, OSError) as exc:
                    return _json_error(500, f"Storage error: {exc}")
                return web.json_response({"status": "ok"})

        return _json_error(404, "Snapshot not found")

    @server.routes.post("/comfymodal/studio/snapshots/{snapshot_id}/duplicate")
    async def studio_snapshots_duplicate(request: web.Request) -> web.Response:
        sid = request.match_info.get("snapshot_id", "")
        try:
            snapshots = _snapshots_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        for s in snapshots:
            if s.get("id") == sid:
                dup = copy.deepcopy(s)
                dup["id"] = _make_snapshot_id()
                dup["name"] = (dup.get("name", "Untitled") or "Untitled") + " (Copy)"
                dup["createdAt"] = _now_iso()
                dup["updatedAt"] = _now_iso()
                dup["archived"] = False
                snapshots.append(dup)
                try:
                    _snapshots_store.write_atomic(snapshots)
                except (StudioStoreError, OSError) as exc:
                    return _json_error(500, f"Storage error: {exc}")
                return web.json_response({"status": "ok", "snapshot": dup})

        return _json_error(404, "Snapshot not found")

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
                enriched.append(normalized)
            return web.json_response({"status": "ok", "presets": enriched})
        except StudioStoreError as exc:
            return _json_error(500, str(exc.args[0]) if exc.args else "Store read error")
        except OSError as exc:
            return _json_error(500, f"Storage error: {exc}")

    @server.routes.post("/comfymodal/studio/presets")
    async def studio_presets_create(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "Invalid JSON body")

        now = _now_iso()
        features = _validate_feature_ids(body.get("compatibleFeatures", []))

        entry: dict[str, Any] = {
            "id": _make_preset_id(),
            "label": _normalize_label(body.get("label", body.get("name", "Untitled Preset"))),
            "description": _sanitize_description(body.get("description", "")),
            "snapshotId": body.get("snapshotId", ""),
            "compatibleFeatures": features,
            "defaults": body.get("defaults", {}),
            "sourceType": body.get("sourceType", "manual"),
            "sourceId": body.get("sourceId", ""),
            "disabledReason": body.get("disabledReason", ""),
            "archived": False,
            "createdAt": now,
            "updatedAt": now,
        }

        # Check snapshot reference on create
        try:
            snapshots = _snapshots_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        snapshots_by_id = _build_snapshots_by_id(snapshots)
        normalized = normalize_preset_payload(entry, snapshots_by_id)
        entry["status"] = normalized.get("status", "runnable")
        entry["disabledReason"] = normalized.get("disabledReason", "")

        # Reject creation for missing snapshots with a stable message
        if entry.get("status") == "invalid" and entry.get("disabledReason") == "Preset references a missing snapshot":
            return _json_error(400, "Preset references a missing snapshot")

        try:
            presets = _presets_store.read()
            presets.append(entry)
            _presets_store.write_atomic(presets)
        except StudioStoreError as exc:
            return _json_error(500, str(exc.args[0]) if exc.args else "Store write error")
        except OSError as exc:
            return _json_error(500, f"Storage error: {exc}")

        return web.json_response({"status": "ok", "preset": entry})

    @server.routes.patch("/comfymodal/studio/presets/{preset_id}")
    async def studio_presets_update(request: web.Request) -> web.Response:
        pid = request.match_info.get("preset_id", "")
        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "Invalid JSON body")

        try:
            presets = _presets_store.read()
            snapshots = _snapshots_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        for p in presets:
            if p.get("id") == pid:
                if "label" in body and isinstance(body["label"], str):
                    p["label"] = _normalize_label(body["label"])
                if "description" in body and isinstance(body["description"], str):
                    p["description"] = _sanitize_description(body["description"])
                if "snapshotId" in body and isinstance(body["snapshotId"], str):
                    p["snapshotId"] = body["snapshotId"]
                if "compatibleFeatures" in body:
                    p["compatibleFeatures"] = _validate_feature_ids(body["compatibleFeatures"])
                if "defaults" in body and isinstance(body["defaults"], dict):
                    p["defaults"] = body["defaults"]
                if "sourceType" in body and isinstance(body["sourceType"], str):
                    p["sourceType"] = body["sourceType"]
                if "sourceId" in body and isinstance(body["sourceId"], str):
                    p["sourceId"] = body["sourceId"]
                if "disabledReason" in body and isinstance(body["disabledReason"], str):
                    p["disabledReason"] = body["disabledReason"].strip()
                if "archived" in body:
                    p["archived"] = bool(body["archived"])

                p["updatedAt"] = _now_iso()
                # Re-derive status
                snapshots_by_id = _build_snapshots_by_id(snapshots)
                normalized = normalize_preset_payload(p, snapshots_by_id)
                p["status"] = normalized.get("status", "runnable")
                p["disabledReason"] = normalized.get("disabledReason", "")

                try:
                    _presets_store.write_atomic(presets)
                except (StudioStoreError, OSError) as exc:
                    return _json_error(500, f"Storage error: {exc}")
                return web.json_response({"status": "ok", "preset": p})

        return _json_error(404, "Preset not found")

    @server.routes.delete("/comfymodal/studio/presets/{preset_id}")
    async def studio_presets_archive(request: web.Request) -> web.Response:
        """Archive (soft-delete) a preset by marking ``archived=True``."""
        pid = request.match_info.get("preset_id", "")
        try:
            presets = _presets_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        for p in presets:
            if p.get("id") == pid:
                p["archived"] = True
                p["updatedAt"] = _now_iso()
                try:
                    _presets_store.write_atomic(presets)
                except (StudioStoreError, OSError) as exc:
                    return _json_error(500, f"Storage error: {exc}")
                return web.json_response({"status": "ok"})

        return _json_error(404, "Preset not found")

    @server.routes.post("/comfymodal/studio/presets/{preset_id}/duplicate")
    async def studio_presets_duplicate(request: web.Request) -> web.Response:
        pid = request.match_info.get("preset_id", "")
        try:
            presets = _presets_store.read()
        except (StudioStoreError, OSError) as exc:
            return _json_error(500, f"Storage error: {exc}")

        for p in presets:
            if p.get("id") == pid:
                dup = copy.deepcopy(p)
                dup["id"] = _make_preset_id()
                dup["label"] = (dup.get("label", "Untitled") or "Untitled") + " (Copy)"
                dup["createdAt"] = _now_iso()
                dup["updatedAt"] = _now_iso()
                dup["archived"] = False
                presets.append(dup)
                try:
                    _presets_store.write_atomic(presets)
                except (StudioStoreError, OSError) as exc:
                    return _json_error(500, f"Storage error: {exc}")
                return web.json_response({"status": "ok", "preset": dup})

        return _json_error(404, "Preset not found")
