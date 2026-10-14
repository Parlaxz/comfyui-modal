"""Generic CRUD for Studio Phase 9 guidance mapping records.

Registered by ``register_guidance_routes(server, node_dir)``.  Persistence
is the ``GuidanceMappingStore`` key-value file
(``<node_dir>/.studio_guidance_mappings.json``), keyed STRICTLY by
``(model_sha256, mode)`` — the only lookup this module performs.

Route summary (all under ``/comfymodal/studio/``):

    GET     /comfymodal/studio/guidance-mappings?model_sha256=&mode= — read one
    POST    /comfymodal/studio/guidance-mappings                     — save confirmed
    DELETE  /comfymodal/studio/guidance-mappings?model_sha256=&mode= — delete one

These handlers only translate HTTP <-> store calls.  Validation (confirmable
shape) lives in ``studio_guidance``; unconfirmed/invalid records fail with
400.  There is deliberately no query by workflow, family, provider,
checkpoint, or filename — by construction (the handlers accept nothing
else).  Error responses always include a stable ``"message"`` key.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from studio_guidance import GuidanceMappingStore

_log = logging.getLogger(__name__)


def _json_error(status: int, message: str) -> web.Response:
    return web.json_response({"status": "error", "message": message}, status=status)


async def _read_body(request: web.Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def register_guidance_routes(server: Any, node_dir: str | Path) -> None:
    """Register the generic guidance-mapping CRUD routes on *server*.

    *server* must expose ``server.routes.get/post/delete(path)`` decorators
    (matching the ``PromptServer.instance.routes`` interface).  Data lives
    in ``<node_dir>/.studio_guidance_mappings.json`` via
    :class:`GuidanceMappingStore`.
    """
    store = GuidanceMappingStore(Path(node_dir))

    @server.routes.get("/comfymodal/studio/guidance-mappings")
    async def guidance_mapping_get(request: web.Request) -> web.Response:
        try:
            sha = str(request.query.get("model_sha256", "") or "")
            mode = str(request.query.get("mode", "") or "")
            if not sha.strip() or not mode.strip():
                return _json_error(400, "model_sha256 and mode query params are required")
            return web.json_response({"status": "ok", "mapping": store.get(sha, mode)})
        except Exception as exc:  # never leak internals; log instead
            _log.exception("guidance mapping read failed")
            return _json_error(500, f"guidance mapping read failed: {exc}"[:300])

    @server.routes.post("/comfymodal/studio/guidance-mappings")
    async def guidance_mapping_save(request: web.Request) -> web.Response:
        try:
            body = await _read_body(request)
            if body is None:
                return _json_error(400, "request body must be a JSON object")
            record = body.get("mapping")
            if not isinstance(record, dict):
                record = body
            try:
                saved = store.save(record)
            except ValueError as exc:
                return _json_error(400, str(exc)[:300])
            return web.json_response({"status": "ok", "mapping": saved})
        except Exception as exc:  # never leak internals; log instead
            _log.exception("guidance mapping save failed")
            return _json_error(500, f"guidance mapping save failed: {exc}"[:300])

    @server.routes.delete("/comfymodal/studio/guidance-mappings")
    async def guidance_mapping_delete(request: web.Request) -> web.Response:
        try:
            sha = str(request.query.get("model_sha256", "") or "")
            mode = str(request.query.get("mode", "") or "")
            if not sha.strip() or not mode.strip():
                return _json_error(400, "model_sha256 and mode query params are required")
            return web.json_response({"status": "ok", "deleted": store.delete(sha, mode)})
        except Exception as exc:  # never leak internals; log instead
            _log.exception("guidance mapping delete failed")
            return _json_error(500, f"guidance mapping delete failed: {exc}"[:300])
