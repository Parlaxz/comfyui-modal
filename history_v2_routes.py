"""History V2 HTTP API routes (server side of the History V2 frontend).

Registered via ``register_history_v2_routes(server, data_root)``.  The
*server* argument may be any of:

- a ComfyUI ``PromptServer`` (its ``server.routes`` is an aiohttp
  ``web.RouteTableDef`` with ``get``/``patch`` decorators),
- an aiohttp ``web.UrlDispatcher`` (``add_get``/``add_patch``),
- an ``aiohttp.web.Application`` (its ``.router`` is used).

Route summary (all under ``/comfymodal/history-v2``):

    GET   /comfymodal/history-v2/feed                         — mixed/single feed
    GET   /comfymodal/history-v2/generations/{generation_id}  — generation detail
    POST  /comfymodal/history-v2/generations/{generation_id}/original        — Generate Original (E3B2)
    POST  /comfymodal/history-v2/generations/{generation_id}/original/retry  — Retry failed Original (E3B2)
    POST  /comfymodal/history-v2/generations/{generation_id}/resume         — Resume interrupted ordinary Single (F1A)
    GET   /comfymodal/history-v2/experiments/{experiment_id}  — experiment detail
    PATCH /comfymodal/history-v2/generations/{generation_id}/favorite
    PATCH /comfymodal/history-v2/generations/{generation_id}/note
    PATCH /comfymodal/history-v2/generations/{generation_id}/featured
    PATCH /comfymodal/history-v2/experiments/{experiment_id}/favorite
    PATCH /comfymodal/history-v2/experiments/{experiment_id}/note
    GET   /comfymodal/history-v2/assets/{asset_id}            — managed asset bytes
    POST  /comfymodal/history-v2/assets/{asset_id}/export     — configured-folder Export (F9)

The repository is constructed per request (cheap: idempotent store
initialization) from ``<data_root>/.studio_history_v2/history_v2.db``.

F9 Export: the POST route is BODYLESS — the selected ``asset_id`` uniquely
identifies the managed source; generation association, logical-output index,
naming context, and live canonical Output settings are all derived and
validated SERVER-SIDE (settings via the injected ``settings_provider``,
wired from ``__init__._load_modal_settings`` at the composition root).
Export state is projected per variant (Preview/Original independently)
through the F7 ``HistoryV2ExportService`` lazy checker.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

from history_v2_models import (
    Asset,
    ExperimentCell,
    GenerationDetail,
    RequestSnapshot,
    RunAttempt,
    logical_output_key_from_metadata,
)
from history_v2_export import (
    ExportNamingContext,
    ExportOptions,
    HistoryV2ExportService,
)
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store

_log = logging.getLogger(__name__)

BASE = "/comfymodal/history-v2"
ASSET_URL_PREFIX = f"{BASE}/assets/"

# Asset types that count as "output" imagery (thumbnail / preview / original).
_OUTPUT_TYPES = frozenset({"thumbnail", "preview", "original"})

# Terminal experiment statuses: once reached, "completed_at" reflects
# updated_at instead of staying null.
_TERMINAL_EXPERIMENT_STATUSES = frozenset({
    "completed", "failed", "completed_with_failures",
    "interrupted", "canceled", "stopped",
})

# UI status aliases → backend statuses, per kind.  "running" expands to every
# in-flight backend value; generations have no "completed_with_failures", so
# that alias matches nothing there (handled via the empty-mapped path).
_GEN_STATUS_ALIASES = {
    "success": ["completed"],
    "completed": ["completed"],
    "partial": ["completed"],
    "running": ["running", "pending", "queued"],
    "failed": ["failed"],
    "canceled": ["canceled"],
    "interrupted": ["interrupted"],
    "completed_with_failures": [],
}
_EXP_STATUS_ALIASES = {
    "success": ["completed"],
    "completed": ["completed"],
    "partial": ["completed_with_failures"],
    "running": ["running", "pending", "queued"],
    "failed": ["failed"],
    "canceled": ["canceled"],
    "interrupted": ["interrupted"],
    "completed_with_failures": ["completed_with_failures"],
}

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

# Canonical camelCase param keys → accepted backend key aliases.
_PARAM_SPEC = [
    ("seed", ("seed",)),
    ("steps", ("steps", "num_inference_steps")),
    ("cfg", ("cfg", "cfg_scale")),
    ("guidance", ("guidance", "guidance_scale")),
    ("sampler", ("sampler", "sampler_name")),
    ("scheduler", ("scheduler",)),
    ("denoise", ("denoise", "denoising_strength")),
    ("width", ("width",)),
    ("height", ("height",)),
]

_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


# ── Small helpers ───────────────────────────────────────────────────────


def _json_error(
    status: int,
    message: str,
    code: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> web.Response:
    body: dict[str, Any] = {"status": "error", "message": message}
    if code:
        body["code"] = code
    if extra:
        body.update(extra)
    return web.json_response(body, status=status)


async def _read_json(request: web.Request) -> Optional[dict[str, Any]]:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return None


def _parse_limit(raw: Optional[str], default: int = 24) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer between 1 and 200") from None
    if value < 1 or value > 200:
        raise ValueError("limit must be between 1 and 200")
    return value


def _map_statuses(
    kind: str, status: Optional[str], statuses: list[str]
) -> tuple[list[str], bool]:
    """Map UI status aliases to backend statuses for a kind.

    Returns ``(mapped_statuses, had_filter)``.  ``had_filter`` is True when
    the caller requested any status filtering; an empty ``mapped_statuses``
    combined with ``had_filter`` means the filter matches nothing.
    """
    aliases = _EXP_STATUS_ALIASES if kind == "experiment" else _GEN_STATUS_ALIASES
    had_filter = status is not None or bool(statuses)
    mapped: list[str] = []
    if status is not None:
        mapped.extend(aliases.get(status, [status]))
    for value in statuses:
        mapped.extend(aliases.get(value, [value]))
    return mapped, had_filter


def _asset_url(asset_id: Optional[str]) -> str:
    return f"{ASSET_URL_PREFIX}{asset_id}" if asset_id else ""


def _model_name(entry: dict[str, Any]) -> Optional[str]:
    for key in ("name", "model", "label"):
        value = entry.get(key)
        if value:
            return str(value)
    return None


def _parse_iso_ms(value: str) -> Optional[int]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except Exception:
        return None


def _ts_ms(value: str) -> int:
    ms = _parse_iso_ms(value)
    return ms if ms is not None else 0


class _Ticker:
    """Cheap inline timing; attached when ``_timing=1`` is requested."""

    def __init__(self) -> None:
        self._marks: dict[str, float] = {}
        self._start = time.perf_counter()

    def mark(self, name: str) -> None:
        self._marks[name] = round((time.perf_counter() - self._start) * 1000, 2)

    def summary(self) -> dict[str, float]:
        return dict(self._marks)


def _maybe_timing(
    request: web.Request, response_data: dict[str, Any], ticker: _Ticker
) -> None:
    if request.query.get("_timing", "") == "1":
        ticker.mark("total")
        response_data["_diagnostic_timing_ms"] = ticker.summary()


# ── Feed item builders ──────────────────────────────────────────────────


def _asset_is_structurally_available(asset: Asset) -> bool:
    managed_path = str(asset.managed_path or "")
    if managed_path.startswith("modal://"):
        return True
    return Path(managed_path).is_file()


def _asset_logical_output_key(asset: Asset) -> Optional[str]:
    return asset.logical_output_key or logical_output_key_from_metadata(asset.metadata)


def _logical_output_groups(assets: list[Asset]) -> list[list[Asset]]:
    grouped: dict[tuple[str, str], list[Asset]] = {}
    for asset in assets:
        if asset.type not in _OUTPUT_TYPES:
            continue
        logical_key = _asset_logical_output_key(asset)
        if logical_key:
            group_key = ("logical", logical_key)
        elif asset.run_id:
            group_key = ("legacy_run", asset.run_id)
        else:
            group_key = ("legacy_asset", asset.asset_id)
        grouped.setdefault(group_key, []).append(asset)
    ordered = list(grouped.items())
    ordered.sort(
        key=lambda entry: (
            min(asset.created_at for asset in entry[1]),
            entry[0][0],
            entry[0][1],
        )
    )
    return [group for _, group in ordered]


def _asset_is_usable_variant(
    asset: Asset,
    attempts: Optional[list[RunAttempt]],
    required_mode: Optional[str] = None,
) -> bool:
    if not _asset_is_structurally_available(asset):
        return False
    return _asset_attempt_is_completed(asset, attempts, required_mode)


def _asset_attempt_is_completed(
    asset: Asset,
    attempts: Optional[list[RunAttempt]],
    required_mode: Optional[str] = None,
) -> bool:
    if attempts is None or asset.run_id is None:
        return True
    attempt = next((a for a in attempts if a.run_id == asset.run_id), None)
    if attempt is None or attempt.status != "completed":
        return False
    return required_mode is None or attempt.mode == required_mode


def _select_variant(
    assets: list[Asset],
    asset_type: str,
    attempts: Optional[list[RunAttempt]],
    required_mode: Optional[str] = None,
    check_availability: bool = True,
) -> Optional[Asset]:
    candidates = [
        asset
        for asset in assets
        if asset.type == asset_type
        and (
            _asset_is_usable_variant(asset, attempts, required_mode)
            if check_availability
            else _asset_attempt_is_completed(asset, attempts, required_mode)
        )
    ]
    return max(candidates, key=lambda asset: (asset.created_at, asset.asset_id), default=None)


def _original_projection(
    assets: list[Asset], attempts: Optional[list[RunAttempt]] = None
) -> tuple[Optional[Asset], bool]:
    originals = [asset for asset in assets if asset.type == "original"]
    selected = _select_variant(assets, "original", attempts)
    latest_original_attempt = max(
        (attempt for attempt in (attempts or []) if attempt.mode == "original"),
        key=lambda attempt: (attempt.created_at, attempt.run_id),
        default=None,
    )
    if selected is not None:
        return selected, False
    if latest_original_attempt is not None:
        if latest_original_attempt.status in ("queued", "running"):
            return None, False
        if latest_original_attempt.status == "failed":
            return None, True
    return None, bool(originals)


def _build_outputs(
    assets: list[Asset],
    gen_thumb_url: str = "",
    attempts: Optional[list[RunAttempt]] = None,
    export_state_of: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Group assets by logical output identity and build feed outputs.

    Keyed assets group by ``logical_output_key``. Legacy assets use run
    provenance when available, otherwise remain isolated by asset id.

    ``export_state_of(asset_id) -> state`` (F9): when provided, each output
    additionally projects per-variant ``preview_asset_id`` /
    ``preview_export_state`` / ``original_asset_id`` / ``original_export_state``
    (None/absent when that variant does not exist — a nonexistent Original is
    never reported as ``not_exported``).  The projected ids are the SAME
    winner objects the URLs point at, so URL + asset id + export state always
    describe one selected Asset.  Without the projector (feed paths) no
    export fields are emitted and nothing is looked up.
    """
    groups = _logical_output_groups(assets)

    outputs: list[dict[str, Any]] = []
    for group in groups:
        ordered = sorted(group, key=lambda a: (a.created_at, a.type, a.asset_id))
        thumb = _select_variant(group, "thumbnail", attempts)
        preview = _select_variant(
            group, "preview", attempts, "preview", check_availability=False
        )
        original, original_failed = _original_projection(group, attempts)
        primary = original or preview or thumb or ordered[0]
        output = {
            "index": len(outputs),
            "asset_id": primary.asset_id,
            "thumb_url": _asset_url(thumb.asset_id) if thumb else "",
            "preview_url": _asset_url(preview.asset_id) if preview else "",
            "original_url": _asset_url(original.asset_id) if original else "",
            "original_failed": original_failed,
            "status": "success",
        }
        if export_state_of is not None:
            output["preview_asset_id"] = preview.asset_id if preview else None
            output["preview_export_state"] = (
                export_state_of(preview.asset_id) if preview else None
            )
            output["original_asset_id"] = original.asset_id if original else None
            output["original_export_state"] = (
                export_state_of(original.asset_id) if original else None
            )
        outputs.append(output)
    return outputs


def _featured_output_index(
    assets: list[Asset], featured_asset_id: Optional[str]
) -> int:
    if not featured_asset_id:
        return 0
    for index, group in enumerate(_logical_output_groups(assets)):
        if any(asset.asset_id == featured_asset_id for asset in group):
            return index
    return 0


def _workflow_name(workflow_json: Any, preset_snapshot: Any = None) -> Optional[str]:
    """Human-readable workflow name from a request snapshot, or None.

    Falls back to the persisted ``preset_snapshot.workflow_name`` ONLY when
    the workflow JSON carries no display name.  Never falls back to
    workflow_id: an unknown name is reported as null rather than falsely
    labeling an id as a name.
    """
    if isinstance(workflow_json, dict):
        extra = workflow_json.get("extra")
        if isinstance(extra, dict):
            wf = extra.get("workflow")
            if isinstance(wf, dict):
                for key in ("name", "title"):
                    value = wf.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        for key in ("name", "title"):
            value = workflow_json.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(preset_snapshot, dict):
        value = preset_snapshot.get("workflow_name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _generation_feed_item(
    g: dict[str, Any],
    assets: list[Asset],
    attempts: list[RunAttempt],
    snapshot: Optional[RequestSnapshot] = None,
    export_state_of: Optional[Any] = None,
) -> dict[str, Any]:
    """Build the raw snake_case generation feed item consumed by the UI.

    ``export_state_of`` (F9) is passed through to ``_build_outputs`` so
    detail surfaces project per-variant export state; plain feed pages omit
    it (no per-asset export lookups there).
    """
    outputs = _build_outputs(
        assets, attempts=attempts, export_state_of=export_state_of
    )
    has_original = any(output["original_url"] for output in outputs)
    has_preview = any(output["preview_url"] for output in outputs)

    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    finished_times: list[str] = []
    pairs: list[tuple[int, int]] = []
    for attempt in attempts:
        if attempt.finished_at:
            finished_times.append(attempt.finished_at)
            if attempt.started_at:
                start_ms = _parse_iso_ms(attempt.started_at)
                finish_ms = _parse_iso_ms(attempt.finished_at)
                if start_ms is not None and finish_ms is not None:
                    pairs.append((start_ms, finish_ms))
    if finished_times:
        completed_at = max(finished_times)
    if pairs:
        duration_ms = max(f for _, f in pairs) - min(s for s, _ in pairs)

    models: list[dict[str, str]] = []
    for entry in g.get("model_stack") or []:
        if not isinstance(entry, dict):
            continue
        name = _model_name(entry)
        if name:
            models.append({"name": name})

    featured_index = _featured_output_index(assets, g.get("featured_asset_id"))

    return {
        "id": g["generation_id"],
        "kind": "generation",
        "status": g["status"],
        "workflow_id": g.get("workflow_id"),
        "workflow_name": _workflow_name(
            snapshot.workflow if snapshot else None,
            snapshot.preset_snapshot if snapshot else None,
        ),
        "workflow_version": g.get("workflow_version_id"),
        "preset_id": g.get("preset_id"),
        "preset": g.get("preset_name") or g.get("preset_id") or "",
        "preset_name": g.get("preset_name"),
        "prompt": g.get("prompt_text", ""),
        "negative_prompt": g.get("negative_prompt_text", ""),
        "created_at": g["created_at"],
        "started_at": g["created_at"],
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "favorite": bool(g.get("favorite", False)),
        "note": g.get("note", ""),
        "tags": [],
        "models": models,
        "output_count": len(outputs),
        "has_image": any(
            output["thumb_url"] or output["preview_url"] or output["original_url"]
            for output in outputs
        ),
        "preview_only": bool(has_preview and not has_original),
        "original_available": has_original,
        "featured_output_index": featured_index,
        "outputs": outputs,
        **_replay_capability_fields(snapshot, g),
    }


def _cell_thumb_url(
    cell: ExperimentCell, assets_by_gen: dict[str, list[Asset]]
) -> str:
    if not cell.generation_id:
        return ""
    assets = assets_by_gen.get(cell.generation_id, [])
    outputs = _build_outputs(assets)
    for output in outputs:
        if output["thumb_url"]:
            return output["thumb_url"]
        if output["preview_url"]:
            return output["preview_url"]
    return ""


def _axis_labels(
    cells: list[ExperimentCell], definition: dict[str, Any]
) -> dict[str, str]:
    first = next((c.axis_labels for c in cells if c.axis_labels), None)
    if first:
        keys = list(first.keys())
        return {"x": keys[0] if len(keys) > 0 else "", "y": keys[1] if len(keys) > 1 else ""}
    def_axes = definition.get("axis_labels")
    if isinstance(def_axes, dict):
        keys = list(def_axes.keys())
        return {"x": keys[0] if keys else "", "y": keys[1] if len(keys) > 1 else ""}
    return {"x": "", "y": ""}


def _experiment_feed_item(
    e: dict[str, Any],
    cells: list[ExperimentCell],
    assets_by_gen: dict[str, list[Asset]],
) -> dict[str, Any]:
    """Build the raw snake_case experiment feed item consumed by the UI."""
    status = e["status"]
    definition = dict(e.get("definition") or {})
    cover = [
        {
            "key": cell.cell_id,
            "thumb_url": _cell_thumb_url(cell, assets_by_gen),
            "status": cell.status,
        }
        for cell in cells[:4]
    ]
    return {
        "id": e["experiment_id"],
        "kind": "experiment",
        "status": status,
        "name": e.get("name") or "",
        "workflow": definition.get("workflow") or "",
        "preset": definition.get("preset") or "",
        "created_at": e["created_at"],
        "started_at": e["created_at"],
        "completed_at": e.get("updated_at") if status in _TERMINAL_EXPERIMENT_STATUSES else None,
        "duration_ms": e.get("duration_ms"),
        "favorite": bool(e.get("favorite", False)),
        "note": e.get("note", ""),
        "tags": [],
        "models": [],
        "true_cell_count": len(cells),
        "result_count": sum(1 for c in cells if c.status == "completed"),
        "failed_count": sum(1 for c in cells if c.status == "failed"),
        "interrupted_count": sum(
            1 for c in cells if c.status in ("interrupted", "canceled")
        ),
        "axis_labels": _axis_labels(cells, definition),
        "cells": cover,
    }


def _build_generation_items(
    repo: HistoryV2Repository, gen_dicts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Batch-enrich raw generation dicts into feed items (one page at a time)."""
    if not gen_dicts:
        return []
    ids = [g["generation_id"] for g in gen_dicts]
    assets_by_gen: dict[str, list[Asset]] = {}
    for asset in repo.get_assets_for_generations(ids):
        assets_by_gen.setdefault(asset.generation_id, []).append(asset)
    attempts_by_gen: dict[str, list[RunAttempt]] = {}
    for attempt in repo.get_attempts_for_generations(ids):
        attempts_by_gen.setdefault(attempt.generation_id, []).append(attempt)
    snapshot_by_gen: dict[str, RequestSnapshot] = {}
    for snapshot in repo.get_snapshots_for_generations(ids):
        if snapshot.generation_id:
            snapshot_by_gen[snapshot.generation_id] = snapshot
    return [
        _generation_feed_item(
            g,
            assets_by_gen.get(g["generation_id"], []),
            attempts_by_gen.get(g["generation_id"], []),
            snapshot_by_gen.get(g["generation_id"]),
        )
        for g in gen_dicts
    ]


def _build_experiment_items(
    repo: HistoryV2Repository, exp_dicts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Batch-enrich raw experiment dicts into feed items (one page at a time)."""
    if not exp_dicts:
        return []
    ids = [e["experiment_id"] for e in exp_dicts]
    cells_by_exp: dict[str, list[ExperimentCell]] = {}
    for cell in repo.get_cells_for_experiments(ids):
        cells_by_exp.setdefault(cell.experiment_id, []).append(cell)
    gen_ids: set[str] = set()
    for e in exp_dicts:
        for cell in cells_by_exp.get(e["experiment_id"], [])[:4]:
            if cell.generation_id:
                gen_ids.add(cell.generation_id)
    assets_by_gen: dict[str, list[Asset]] = {}
    if gen_ids:
        for asset in repo.get_assets_for_generations(sorted(gen_ids)):
            assets_by_gen.setdefault(asset.generation_id, []).append(asset)
    return [
        _experiment_feed_item(
            e, cells_by_exp.get(e["experiment_id"], []), assets_by_gen
        )
        for e in exp_dicts
    ]


# ── Mixed-stream merge / cursor ─────────────────────────────────────────


def _item_id(item: dict[str, Any]) -> str:
    return (
        item.get("id")
        or item.get("generation_id")
        or item.get("experiment_id")
        or ""
    )


def _item_kind(item: dict[str, Any]) -> str:
    kind = item.get("__kind")
    if kind:
        return kind
    return "experiment" if "experiment_id" in item else "generation"


def _desc_string_key(s: str) -> tuple:
    """Deterministic descending string sort key (empty string → ())."""
    return tuple(-ord(ch) for ch in s)


def _sort_tuple(item: dict[str, Any], order: str) -> tuple:
    """Sort key matching the repo's total order for a given feed order.

    newest        → (-created_at, experiment-last, id DESC)
    oldest        → (created_at, experiment-last, id ASC)
    fastest       → (no-timing-last, duration, created_at, id ASC)
    slowest       → (no-timing-last, -duration, created_at, id ASC)
    workflow_asc  → (missing-workflow-last, workflow casefold, created_at, id)
    workflow_desc → (missing-workflow-last, -chars(workflow), created_at, id)

    The workflow sort key is ``workflow_id`` for generation items and
    ``name`` for experiment items (the repo's "sensible equivalent").
    """
    ts = _ts_ms(item.get("created_at") or "")
    is_exp = 1 if _item_kind(item) == "experiment" else 0
    item_id = _item_id(item)
    if order == "newest":
        return (-ts, is_exp, item_id[::-1])
    if order == "oldest":
        return (ts, is_exp, item_id)
    duration = item.get("duration_ms")
    dur_none = 1 if duration is None else 0
    dur = float(duration or 0)
    if order == "fastest":
        return (dur_none, dur, ts, item_id)
    if order == "slowest":
        return (dur_none, -dur, ts, item_id)
    if order in ("workflow_asc", "workflow_desc"):
        wf_key = (
            (item.get("name") or "")
            if is_exp
            else (item.get("workflow_id") or "")
        )
        wf_none = 1 if not wf_key else 0
        if order == "workflow_asc":
            return (wf_none, wf_key.casefold(), ts, item_id)
        return (wf_none, _desc_string_key(wf_key), ts, item_id)
    raise ValueError(f"unknown order: {order!r}")


def _merge_streams(
    gen_items: list[dict[str, Any]],
    exp_items: list[dict[str, Any]],
    order: str,
) -> list[dict[str, Any]]:
    """Two-pointer merge of two sorted streams; items are tagged ``__kind``."""
    gen = [dict(x, __kind="generation") for x in gen_items]
    exp = [dict(x, __kind="experiment") for x in exp_items]
    merged: list[dict[str, Any]] = []
    i = j = 0
    while i < len(gen) and j < len(exp):
        if _sort_tuple(gen[i], order) < _sort_tuple(exp[j], order):
            merged.append(gen[i])
            i += 1
        else:
            merged.append(exp[j])
            j += 1
    if i < len(gen):
        merged.extend(gen[i:])
    if j < len(exp):
        merged.extend(exp[j:])
    return merged


_MIXED_CURSOR_VERSION = 2


def _encode_mixed_cursor(
    g_cursor: Optional[str], e_cursor: Optional[str]
) -> str:
    """V2 stateless mixed cursor: per-stream keysets anchored at the last
    EMITTED item of each stream (no skip counts)."""
    payload = json.dumps(
        {"v": _MIXED_CURSOR_VERSION, "g": g_cursor, "e": e_cursor},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_mixed_cursor(cursor: str) -> tuple[Optional[str], Optional[str]]:
    """Decode a mixed cursor to ``(g, e)``.

    V2 payloads carry ``{"v": 2, "g", "e"}``.  Legacy V1 payloads
    (``{"g", "e", "gs", "es"}``) are tolerated: their skip counts were broken
    and are ignored, so continuation from a V1 cursor is best-effort for that
    single page (the response upgrades to V2).  Malformed payloads and
    unknown versions raise ValueError (→ HTTP 400 "invalid cursor").
    """
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        )
    except Exception:
        raise ValueError("invalid cursor") from None
    if not isinstance(payload, dict):
        raise ValueError("invalid cursor")
    version = payload.get("v")
    g = payload.get("g")
    e = payload.get("e")
    if version is None:
        gs = payload.get("gs")
        es = payload.get("es")
        if not isinstance(gs, int) or not isinstance(es, int) or gs < 0 or es < 0:
            raise ValueError("invalid cursor")
        return (g if isinstance(g, str) else None), (
            e if isinstance(e, str) else None
        )
    if version != _MIXED_CURSOR_VERSION:
        raise ValueError("invalid cursor")
    if not isinstance(g, (str, type(None))) or not isinstance(e, (str, type(None))):
        raise ValueError("invalid cursor")
    return g, e


def _stream_cursor_after(
    emitted: list[dict[str, Any]], order: str, previous: Optional[str]
) -> Optional[str]:
    """Keyset cursor positioned after the last emitted item of a stream.

    Sort keys are extracted with the repository's own ``_cursor_sort_key`` so
    cursor advancement and single-kind pagination agree exactly.
    """
    if not emitted:
        return previous
    last = emitted[-1]
    created_at = last.get("created_at") or ""
    item_id = _item_id(last)
    key = HistoryV2Repository._cursor_sort_key(order, last)
    return HistoryV2Repository._encode_cursor(created_at, item_id, key)


def _stream_has_more(next_cursor: Optional[str], tail: int) -> bool:
    """True when a stream still has items: un-emitted window tail or more
    rows after the last fetched one."""
    return tail > 0 or next_cursor is not None


# ── Detail helpers ──────────────────────────────────────────────────────


def _attempt_dict(attempt: RunAttempt) -> dict[str, Any]:
    duration_ms: Optional[int] = None
    if attempt.started_at and attempt.finished_at:
        start_ms = _parse_iso_ms(attempt.started_at)
        finish_ms = _parse_iso_ms(attempt.finished_at)
        if start_ms is not None and finish_ms is not None:
            duration_ms = finish_ms - start_ms
    return {
        "run_id": attempt.run_id,
        "mode": attempt.mode,
        "status": attempt.status,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
        "duration_ms": duration_ms,
        "error": attempt.error,
        "timing": attempt.timing or None,
    }


def _map_params(generation_params: dict[str, Any]) -> dict[str, Any]:
    """Map snapshot generation params to the nine canonical camelCase keys."""
    mapped: dict[str, Any] = {}
    for camel, aliases in _PARAM_SPEC:
        for key in aliases:
            if key in generation_params and generation_params[key] is not None:
                mapped[camel] = generation_params[key]
                break
    return mapped


def _replay_capability_fields(
    snapshot: Optional[RequestSnapshot],
    generation: Any = None,
) -> dict[str, Any]:
    """Project immutable-request replay capability (F5, read-only).

    Reuses the CANONICAL validator that gates Generate Original / Retry
    Original / Single Resume (``load_replay_plan`` = raw-snapshot validation
    plus the exact plan round-trip check), so ``replay_capable=true`` means
    the saved immutable request alone passes every action's capability gate.
    It is deliberately NOT a promise about current Workflow/Preset state,
    workspace credentials, dispatch availability, or execution success —
    actual POST routes re-validate independently and stay fail-closed.  Only
    a stable machine-readable reason code is exposed; validator details and
    raw exceptions never reach the client and nothing is written.
    """
    if snapshot is None:
        return {
            "replay_capable": False,
            "replay_unavailable_reason": "missing_request_snapshot",
        }
    from history_v2_replay import (
        REASON_INVALID_PLAN,
        ReplayCapabilityError,
        load_replay_plan,
    )

    try:
        load_replay_plan(snapshot, generation=generation)
    except ReplayCapabilityError as exc:
        return {
            "replay_capable": False,
            "replay_unavailable_reason": exc.capability.reason
            or REASON_INVALID_PLAN,
        }
    except Exception:
        return {
            "replay_capable": False,
            "replay_unavailable_reason": REASON_INVALID_PLAN,
        }
    return {"replay_capable": True}


def _snapshot_dict(snapshot: RequestSnapshot) -> dict[str, Any]:
    """Immutable RequestSnapshot payload for the experiment-detail enrichment.

    Carries the snapshot's identity ids (``snapshot_id``, ``schema_version``,
    ``generation_id``, ``workflow_hash``, ``workflow_version_id``) together
    with the full immutable request surface: ``request``, ``execution_plan``,
    ``workflow``, ``generation_params``, ``preset_snapshot`` and
    ``deployment_identity``.
    """
    return {
        "snapshot_id": snapshot.snapshot_id,
        "created_at": snapshot.created_at,
        "schema_version": snapshot.schema_version,
        "generation_id": snapshot.generation_id,
        "workflow_hash": snapshot.workflow_hash,
        "workflow_version_id": snapshot.workflow_version_id,
        "request": dict(snapshot.request),
        "execution_plan": dict(snapshot.execution_plan),
        "workflow": dict(snapshot.workflow),
        "generation_params": dict(snapshot.generation_params),
        "preset_snapshot": dict(snapshot.preset_snapshot),
        "deployment_identity": dict(snapshot.deployment_identity),
    }


def _cell_generation_payload(
    detail: GenerationDetail, export_state_of: Optional[Any] = None
) -> dict[str, Any]:
    """Additive per-cell Generation payload for the experiment detail.

    Builds the raw snake_case generation surface a "one card" experiment
    detail needs (mirroring the generation detail route): the generation
    record, its full attempts list, the immutable request snapshot when
    linked, grouped outputs/assets, and the existing error/timing
    diagnostics.  Only cells with a generation receive a payload; the route
    emits ``generation: None`` otherwise.  ``export_state_of`` (F9) gives the
    embedded outputs EXACTLY the same per-variant export projection as
    ordinary generation detail — no Experiment-specific export state exists.
    """
    gen = detail.generation
    attempts = detail.attempts
    snapshot = detail.request_snapshot

    duration_ms: Optional[int] = None
    pairs: list[tuple[int, int]] = []
    for attempt in attempts:
        if attempt.started_at and attempt.finished_at:
            start_ms = _parse_iso_ms(attempt.started_at)
            finish_ms = _parse_iso_ms(attempt.finished_at)
            if start_ms is not None and finish_ms is not None:
                pairs.append((start_ms, finish_ms))
    if pairs:
        duration_ms = max(f for _, f in pairs) - min(s for s, _ in pairs)

    candidates = [a for a in attempts if a.timing and a.finished_at]
    candidates.sort(key=lambda a: a.finished_at or "")
    timing = candidates[-1].timing if candidates else None

    return {
        "id": gen.generation_id,
        "status": gen.status,
        "workflow_id": gen.workflow_id,
        "workflow_version_id": gen.workflow_version_id,
        "preset_id": gen.preset_id,
        "preset_name": gen.preset_name,
        "workflow_name": _workflow_name(
            snapshot.workflow if snapshot else None,
            snapshot.preset_snapshot if snapshot else None,
        ),
        "request_snapshot_id": gen.request_snapshot_id,
        "experiment_id": gen.experiment_id,
        "featured_asset_id": gen.featured_asset_id,
        "favorite": bool(gen.favorite),
        "note": gen.note,
        "prompt": gen.prompt_text,
        "negative_prompt": gen.negative_prompt_text,
        "model_stack": [dict(m) for m in gen.model_stack],
        "created_at": gen.created_at,
        "updated_at": gen.updated_at,
        "duration_ms": duration_ms,
        "params": _map_params(snapshot.generation_params) if snapshot else {},
        "attempts": [_attempt_dict(a) for a in attempts],
        "request_snapshot": (
            _snapshot_dict(snapshot) if snapshot is not None else None
        ),
        "outputs": _build_outputs(
            detail.assets, attempts=attempts, export_state_of=export_state_of
        ),
        "featured_output_index": _featured_output_index(
            detail.assets, gen.featured_asset_id
        ),
        "errors": [
            {"code": "attempt_failed", "message": a.error}
            for a in attempts
            if a.error
        ],
        "timing": timing,
        **_replay_capability_fields(snapshot, gen),
    }


def _detail_cell(
    cell: ExperimentCell,
    assets_by_gen: dict[str, list[Asset]],
    attempts_by_cell: dict[str, list[RunAttempt]],
    fav_by_gen: dict[str, bool],
    axis_names: Optional[dict[str, str]] = None,
    generation_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    assets = assets_by_gen.get(cell.generation_id, []) if cell.generation_id else []
    attempts = attempts_by_cell.get(cell.cell_id, [])
    thumb = _select_variant(assets, "thumbnail", attempts)
    preview = _select_variant(
        assets, "preview", attempts, "preview", check_availability=False
    )
    original, original_failed = _original_projection(assets, attempts)

    duration_ms: Optional[int] = None
    pairs: list[tuple[int, int]] = []
    for attempt in attempts:
        if attempt.started_at and attempt.finished_at:
            start_ms = _parse_iso_ms(attempt.started_at)
            finish_ms = _parse_iso_ms(attempt.finished_at)
            if start_ms is not None and finish_ms is not None:
                pairs.append((start_ms, finish_ms))
    if pairs:
        duration_ms = max(f for _, f in pairs) - min(s for s, _ in pairs)

    labels = cell.axis_labels if isinstance(cell.axis_labels, dict) else {}
    if axis_names is None:
        keys = list(labels.keys())
        axis_names = {
            "x": keys[0] if len(keys) > 0 else "",
            "y": keys[1] if len(keys) > 1 else "",
        }
    x_name = axis_names.get("x") or ""
    y_name = axis_names.get("y") or ""

    def _axis_value(name: str, fallback_index: int) -> str:
        if name and name in labels:
            value = labels[name]
            return str(value) if value is not None else ""
        keys = list(labels.keys())
        if fallback_index < len(keys):
            value = labels[keys[fallback_index]]
            return str(value) if value is not None else ""
        return ""

    return {
        "key": cell.cell_id,
        "index": cell.position,
        "status": cell.status,
        "axis": {"x": _axis_value(x_name, 0), "y": _axis_value(y_name, 1)},
        "axis_labels": {"x": x_name, "y": y_name},
        "error": cell.error,
        "generation_id": cell.generation_id,
        "thumb_url": _asset_url(thumb.asset_id) if thumb else "",
        "preview_url": _asset_url(preview.asset_id) if preview else "",
        "original_url": _asset_url(original.asset_id) if original else "",
        "original_failed": original_failed,
        "duration_ms": duration_ms,
        "favorite": bool(fav_by_gen.get(cell.generation_id, False))
        if cell.generation_id
        else False,
        "generation": generation_payload,
    }


def _content_type_for(asset: Asset) -> str:
    fmt = (asset.format or "").lower()
    if fmt in _CONTENT_TYPES:
        return _CONTENT_TYPES[fmt]
    suffix = Path(asset.managed_path).suffix.lower().lstrip(".")
    return _CONTENT_TYPES.get(suffix, "application/octet-stream")


def _resolve_workspace_dict(workspace_id: str) -> Optional[dict]:
    """Resolve a workspace id to its credential dict (generic asset route
    equivalent) with lazy imports; None when unavailable."""
    if not workspace_id:
        return None
    try:
        from modal_workspaces import get_workspace, load_workspace_registry

        from modal_workspaces import resolve_workspace_registry_path
        workspace_file = resolve_workspace_registry_path(Path(__file__).resolve().parent)
        registry = load_workspace_registry(workspace_file)
        return get_workspace(registry, workspace_id)
    except Exception:
        return None


# ── Managed source resolution (shared by asset GET + F9 Export) ────────


class _ManagedAssetError(Exception):
    """Typed managed-source failure carrying its HTTP serving status.

    ``status`` mirrors the established managed-asset serving truth:
    400 malformed ``modal://`` origin, 404 missing/unavailable source,
    502 remote retrieval failure.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _parse_modal_reference(managed_path: str) -> tuple[str, str, str]:
    """Split ``modal://<workspace>||<gpu>||<backend_path>`` (serving truth)."""
    try:
        workspace_id, gpu, backend_path = managed_path[len("modal://"):].split("|", 2)
        return workspace_id, gpu, backend_path
    except ValueError:
        raise _ManagedAssetError(400, "asset origin invalid") from None


def _managed_source_structural_error(asset: Asset) -> Optional[_ManagedAssetError]:
    """Structural availability check WITHOUT fetching bytes.

    Mirrors the managed-asset GET truth exactly: local path must exist as a
    file; a ``modal://`` reference must parse and its workspace must resolve.
    Remote BYTES are never touched here — absence of remote bytes is only
    truthfully knowable at fetch time.
    """
    managed_path = str(asset.managed_path or "")
    if managed_path.startswith("modal://"):
        try:
            workspace_id, _gpu, _backend = _parse_modal_reference(managed_path)
        except _ManagedAssetError as exc:
            return exc
        if _resolve_workspace_dict(workspace_id) is None:
            return _ManagedAssetError(404, "asset workspace unavailable")
        return None
    if not Path(managed_path).is_file():
        return _ManagedAssetError(404, "asset file not found")
    return None


async def _read_remote_managed_bytes(asset: Asset) -> bytes:
    """Read ``modal://`` managed bytes with the EXACT serving semantics.

    Single internal helper used by BOTH the managed-asset GET route and the
    F9 Export byte resolver, so Export can never drift from serving truth:
    same URI parsing, same lazy workspace resolution, same 3-attempt
    FileNotFoundError retry ladder, same ``expected_sha256`` verification
    inside ``modal_client.read_output_asset``, same status classification.
    """
    managed_path = str(asset.managed_path)
    workspace_id, gpu, backend_path = _parse_modal_reference(managed_path)
    workspace = _resolve_workspace_dict(workspace_id)
    if workspace is None:
        raise _ManagedAssetError(404, "asset workspace unavailable")
    try:
        from modal_client import read_output_asset

        last_exc: Optional[Exception] = None
        for _attempt in range(3):
            try:
                remote = await read_output_asset(
                    backend_path,
                    expected_sha256=str(asset.sha256 or ""),
                    gpu=gpu or None,
                    workspace=workspace,
                )
                payload = remote.get("data", b"") if isinstance(remote, dict) else b""
                if not isinstance(payload, bytes):
                    raise TypeError("remote asset payload is not bytes")
                return payload
            except FileNotFoundError as exc:
                last_exc = exc
                if _attempt < 2:
                    await asyncio.sleep(0.25 if _attempt == 0 else 0.5)
        raise last_exc if last_exc is not None else FileNotFoundError(
            "remote asset missing"
        )
    except FileNotFoundError:
        raise _ManagedAssetError(404, "asset file missing") from None
    except Exception as exc:
        _log.exception("Failed to fetch remote managed asset %s", asset.asset_id)
        raise _ManagedAssetError(502, f"asset fetch failed: {str(exc)[:200]}") from None


# ── Registration ────────────────────────────────────────────────────────


# Per-asset export serialization (process-local; F9 concurrency guard).
# Narrowest possible guard: two concurrent POSTs for the SAME asset are
# serialized so they cannot create conflicting duplicate files or race the
# record; exports of DIFFERENT assets never block each other.
_ASSET_EXPORT_LOCKS: dict[str, asyncio.Lock] = {}


def _asset_export_lock(asset_id: str) -> asyncio.Lock:
    lock = _ASSET_EXPORT_LOCKS.get(asset_id)
    if lock is None:
        lock = asyncio.Lock()
        _ASSET_EXPORT_LOCKS[asset_id] = lock
    return lock


def _derive_output_index(
    assets: list[Asset], asset: Asset
) -> Optional[int]:
    """Real logical-output index of *asset* per current History V2 grouping.

    Uses the SAME ``_logical_output_groups`` grouping/order that
    ``_build_outputs`` projects as each output's canonical ``index``, so a
    Preview and an Original sharing a logical key resolve to the SAME index,
    multi-output generations get distinct real indices, and legacy unkeyed
    assets remain resolvable via run/asset provenance.  Returns None when the
    asset cannot be mapped truthfully — callers must fail closed rather than
    silently assigning index 0.
    """
    for index, group in enumerate(_logical_output_groups(assets)):
        if any(candidate.asset_id == asset.asset_id for candidate in group):
            return index
    return None


def _export_options_from_settings(raw: Any) -> ExportOptions:
    """Build the ONE F7 ExportOptions from acknowledged live server settings.

    The provider returns the canonical normalized settings dict (production:
    ``__init__._load_modal_settings``); this only coerces defensively to the
    F7 field types.  No Export-specific settings exist or are invented.
    """
    defaults = ExportOptions()
    try:
        quality = int(raw.get("quality", defaults.quality))
    except (TypeError, ValueError):
        quality = defaults.quality
    return ExportOptions(
        save_folder=str(raw.get("save_folder", "") or ""),
        output_format=str(raw.get("output_format", "") or defaults.output_format),
        quality=max(0, min(100, quality)),
        webp_lossless_compression=str(
            raw.get("webp_lossless_compression", "")
            or defaults.webp_lossless_compression
        ),
        save_metadata_sidecar=bool(
            raw.get("save_metadata_sidecar", defaults.save_metadata_sidecar)
        ),
    )


def _export_naming_from_detail(
    detail: GenerationDetail, output_index: int
) -> ExportNamingContext:
    """Server-derived naming context from IMMUTABLE/DURABLE data only.

    Prefers the immutable RequestSnapshot (workflow name/hash, seed, preset
    snapshot) OVER Generation durable metadata (preset ids).  Current
    mutable Workflow/Preset state is NEVER resolved for naming.  Missing
    optional metadata is not an export blocker; the real output index is
    required.
    """
    gen = detail.generation
    snapshot = detail.request_snapshot
    workflow_name = ""
    workflow_hash = ""
    seed = ""
    preset_id: Any = None
    preset_name: Any = None
    if snapshot is not None:
        workflow_name = (
            _workflow_name(snapshot.workflow, snapshot.preset_snapshot) or ""
        )
        workflow_hash = str(snapshot.workflow_hash or "")
        params = snapshot.generation_params
        raw_seed = params.get("seed") if isinstance(params, dict) else None
        if raw_seed is not None:
            seed = str(raw_seed)
        preset_snapshot = (
            snapshot.preset_snapshot
            if isinstance(snapshot.preset_snapshot, dict)
            else {}
        )
        preset_id = preset_snapshot.get("preset_id")
        preset_name = preset_snapshot.get("preset_name")
    # Generation durable metadata fills only what the snapshot lacked.
    preset_id = preset_id or gen.preset_id
    preset_name = preset_name or gen.preset_name
    return ExportNamingContext(
        output_index=output_index,
        workflow_name=workflow_name,
        workflow_hash=workflow_hash,
        preset_id=str(preset_id) if preset_id else None,
        preset_name=str(preset_name) if preset_name else None,
        seed=seed,
    )


def _export_error_response(
    status: int,
    asset_id: str,
    reason: str,
    message: str,
    export_state: str,
    *,
    partial: bool = False,
) -> web.Response:
    """Stable machine-readable Export error payload (bounded, secret-free)."""
    return web.json_response(
        {
            "status": "error",
            "asset_id": asset_id,
            "reason": reason,
            "message": str(message or "export failed")[:200],
            "export_state": export_state,
            "partial": bool(partial),
        },
        status=status,
    )


def register_history_v2_routes(
    server: Any,
    data_root: Any,
    *,
    generate_original_service_factory: Any = None,
    settings_provider: Any = None,
) -> None:
    """Register all History V2 routes on *server*.

    *server* may be a ComfyUI PromptServer, an aiohttp UrlDispatcher, or an
    aiohttp.web.Application.  Data is read from
    ``<data_root>/.studio_history_v2/history_v2.db``.

    ``generate_original_service_factory(repo)`` optionally supplies the E3B2
    Generate Original service (tests inject fakes); the default builds the
    production :class:`~history_v2_replay.GenerateOriginalService`.

    ``settings_provider()`` (F9) supplies the live canonical server settings
    dict for configured-folder Export; the composition root wires
    ``__init__._load_modal_settings`` here (dependency injection avoids any
    circular import from this module into ``__init__``).  When absent, the
    Export POST fails closed with a truthful configuration error.
    """

    def _open_repo() -> HistoryV2Repository:
        db_path = Path(data_root) / ".studio_history_v2" / "history_v2.db"
        return HistoryV2Repository(HistoryV2Store(db_path))

    def _open_generate_original_service() -> Any:
        repo = _open_repo()
        if generate_original_service_factory is not None:
            return generate_original_service_factory(repo)
        from history_v2_replay import GenerateOriginalService

        return GenerateOriginalService(repo, data_root=data_root)

    def _route(method: str, path: str):
        """Return a decorator registering a handler for method/path."""
        routes = server
        candidate = getattr(server, "routes", None)
        if candidate is not None and not callable(candidate):
            routes = candidate
        elif hasattr(server, "router"):
            routes = server.router
        if hasattr(routes, "add_" + method):
            adder = getattr(routes, "add_" + method)

            def decorator(handler):
                adder(path, handler)
                return handler

            return decorator
        # aiohttp RouteTableDef: `routes.get(path)` / `.patch(path)` decorators.
        return getattr(routes, method)(path)

    # ── Feed ───────────────────────────────────────────────────────────

    @_route("get", f"{BASE}/feed")
    async def history_v2_feed(request: web.Request) -> web.Response:
        ticker = _Ticker()
        kind = request.query.get("kind", "mixed")
        if kind not in ("generation", "experiment", "mixed"):
            return _json_error(400, "invalid kind")
        try:
            limit = _parse_limit(request.query.get("limit"))
        except ValueError as exc:
            return _json_error(400, str(exc))
        order = request.query.get("order", "newest")
        if order not in ("newest", "oldest", "fastest", "slowest", "workflow_asc", "workflow_desc"):
            return _json_error(400, "invalid order")
        cursor = request.query.get("cursor") or None
        search = request.query.get("search") or None
        status = request.query.get("status") or None
        statuses = [
            s for s in (request.query.get("statuses") or "").split(",") if s
        ]
        workflow_id = (
            request.query.get("workflow_id") or request.query.get("workflow") or None
        )
        preset_id = (
            request.query.get("preset_id") or request.query.get("preset") or None
        )
        favorite = _parse_bool(request.query.get("favorite"))
        date_from = request.query.get("date_from") or None
        date_to = request.query.get("date_to") or None
        preview_only = _parse_bool(request.query.get("preview_only"))
        has_preview = _parse_bool(request.query.get("has_preview"))
        has_original = _parse_bool(request.query.get("has_original"))
        if has_original is None:
            has_original = _parse_bool(request.query.get("original_available"))
        interrupted = _parse_bool(request.query.get("interrupted"))
        failed_or_canceled = _parse_bool(request.query.get("failed_or_canceled"))
        model = request.query.get("model") or None
        has_image = _parse_bool(request.query.get("has_image"))
        ticker.mark("params")

        repo = _open_repo()
        gen_filters = {
            "search": search,
            "workflow_id": workflow_id,
            "preset_id": preset_id,
            "favorite": favorite,
            "date_from": date_from,
            "date_to": date_to,
            "has_preview": has_preview,
            "has_original": has_original,
            "preview_only": preview_only,
            "interrupted": interrupted,
            "failed_or_canceled": failed_or_canceled,
            "model_name": model,
            "has_image": has_image,
        }
        exp_filters = {
            "search": search,
            "favorite": favorite,
            "date_from": date_from,
            "date_to": date_to,
        }

        if kind in ("generation", "experiment"):
            mapped, had = _map_statuses(kind, status, statuses)
            if had and not mapped:
                items: list[dict[str, Any]] = []
                next_cursor: Optional[str] = None
                total = 0
            else:
                if kind == "generation":
                    result = repo.query_generations(
                        cursor=cursor, limit=limit, order=order,
                        statuses=mapped or None, **gen_filters,
                    )
                    items = _build_generation_items(repo, result["items"])
                else:
                    result = repo.query_experiments(
                        cursor=cursor, limit=limit, order=order,
                        statuses=mapped or None, **exp_filters,
                    )
                    items = _build_experiment_items(repo, result["items"])
                next_cursor = result["next_cursor"]
                total = result["total"]
        else:
            # Mixed two-stream merge (stateless; never loads the whole DB).
            #
            # V2 semantics: each stream is queried with a plain keyset cursor
            # anchored at the LAST EMITTED item of that stream.  Items fetched
            # but not emitted in a page (merge losers at the window tail)
            # therefore reappear at the head of the next window and re-enter
            # the merge — nothing is skipped, nothing is lost, windows stay
            # bounded by `limit`.
            g_cursor: Optional[str] = None
            e_cursor: Optional[str] = None
            if cursor:
                try:
                    g_cursor, e_cursor = _decode_mixed_cursor(cursor)
                except ValueError:
                    return _json_error(400, "invalid cursor")

            gen_mapped, gen_had = _map_statuses("generation", status, statuses)
            exp_mapped, exp_had = _map_statuses("experiment", status, statuses)

            if gen_had and not gen_mapped:
                gen_items, gen_next, gen_total = [], None, 0
            else:
                gresult = repo.query_generations(
                    cursor=g_cursor, limit=limit, order=order,
                    statuses=gen_mapped or None, **gen_filters,
                )
                gen_items = gresult["items"]
                gen_next = gresult["next_cursor"]
                gen_total = gresult["total"]
            if exp_had and not exp_mapped:
                exp_items, exp_next, exp_total = [], None, 0
            else:
                eresult = repo.query_experiments(
                    cursor=e_cursor, limit=limit, order=order,
                    statuses=exp_mapped or None, **exp_filters,
                )
                exp_items = eresult["items"]
                exp_next = eresult["next_cursor"]
                exp_total = eresult["total"]
            ticker.mark("query")

            merged = _merge_streams(gen_items, exp_items, order)[:limit]
            gen_emitted = [m for m in merged if m["__kind"] == "generation"]
            exp_emitted = [m for m in merged if m["__kind"] == "experiment"]

            # Re-anchor each stream after its last emitted item; a stream that
            # emitted nothing keeps its previous position so its un-emitted
            # tail is re-fetched and re-merged on the next page.
            new_g_cursor = _stream_cursor_after(gen_emitted, order, g_cursor)
            new_e_cursor = _stream_cursor_after(exp_emitted, order, e_cursor)

            gen_more = _stream_has_more(gen_next, len(gen_items) - len(gen_emitted))
            exp_more = _stream_has_more(exp_next, len(exp_items) - len(exp_emitted))
            if gen_more or exp_more:
                next_cursor = _encode_mixed_cursor(new_g_cursor, new_e_cursor)
            else:
                next_cursor = None
            total = gen_total + exp_total

            gen_dicts = [m for m in merged if m["__kind"] == "generation"]
            exp_dicts = [m for m in merged if m["__kind"] == "experiment"]
            gen_rich = _build_generation_items(repo, gen_dicts)
            exp_rich = _build_experiment_items(repo, exp_dicts)
            items = []
            gi = ei = 0
            for m in merged:
                if m["__kind"] == "generation":
                    items.append(gen_rich[gi])
                    gi += 1
                else:
                    items.append(exp_rich[ei])
                    ei += 1
        ticker.mark("enrich")

        response_data = {
            "status": "ok",
            "items": items,
            "next_cursor": next_cursor,
            "limit": limit,
            "total": total,
            "has_more": next_cursor is not None,
        }
        _maybe_timing(request, response_data, ticker)
        return web.json_response(response_data)

    # ── Generation detail ──────────────────────────────────────────────

    @_route("get", f"{BASE}/generations/{{generation_id}}")
    async def history_v2_generation_detail(request: web.Request) -> web.Response:
        ticker = _Ticker()
        generation_id = request.match_info["generation_id"]
        repo = _open_repo()
        detail = repo.get_generation(generation_id)
        if detail is None:
            return _json_error(404, "generation not found")
        # F9 per-variant export projection: lazily classify each projected
        # variant through the F7 checker (record + destination existence).
        # A recorded `exported` whose file vanished becomes (and persists
        # as) `missing`; unrelated exports are never scanned and the managed
        # source is never touched.  No remote bytes are fetched here.
        export_service = HistoryV2ExportService(repo)

        def _export_state_of(asset_id: str) -> str:
            return export_service.get_export_state(
                asset_id, persist_missing=True
            ).state

        item = _generation_feed_item(
            detail.generation.to_dict(), detail.assets, detail.attempts,
            snapshot=detail.request_snapshot,
            export_state_of=_export_state_of,
        )
        item["attempts"] = [_attempt_dict(a) for a in detail.attempts]
        item["errors"] = [
            {"code": "attempt_failed", "message": a.error}
            for a in detail.attempts
            if a.error
        ]
        variant_states = [
            state
            for output in item["outputs"]
            for state in (
                output.get("preview_export_state"),
                output.get("original_export_state"),
            )
            if state
        ]
        # DEPRECATED aggregate compatibility only (F9): the old collapsed
        # generation-level field, now DERIVED from the lazy per-variant truth
        # above so it can never contradict it.  Frontends must consume the
        # per-variant fields; this stays solely for existing consumers.
        item["export_state"] = "exported" if "exported" in variant_states else "none"
        snapshot = detail.request_snapshot
        item["params"] = _map_params(snapshot.generation_params) if snapshot else {}
        candidates = [a for a in detail.attempts if a.timing and a.finished_at]
        candidates.sort(key=lambda a: a.finished_at or "")
        item["timing"] = candidates[-1].timing if candidates else None
        item["workflow_json"] = dict(snapshot.workflow) if snapshot else None
        response_data = {"status": "ok", "item": item}
        _maybe_timing(request, response_data, ticker)
        return web.json_response(response_data)

    # ── Generate Original (E3B2 production replay action) ──────────────

    @_route("post", f"{BASE}/generations/{{generation_id}}/original")
    async def history_v2_generation_original(request: web.Request) -> web.Response:
        """Generate Original from the immutable History snapshot.

        Body (optional): ``{"rerender": true}`` to force a new Attempt when
        policy permits.  Workflow, seed, preset, controls, plan, and model
        stack come ONLY from the saved snapshot — never from current mutable
        state.
        """
        generation_id = request.match_info["generation_id"]
        body = await _read_json(request)
        if body is None:
            body = {}
        rerender = body.get("rerender", False)
        if not isinstance(rerender, bool):
            return _json_error(400, "rerender must be a boolean")
        service = _open_generate_original_service()
        result = await service.generate(generation_id, rerender=rerender)
        return web.json_response(dict(result.payload), status=result.http_status)

    @_route("post", f"{BASE}/generations/{{generation_id}}/original/retry")
    async def history_v2_generation_original_retry(
        request: web.Request,
    ) -> web.Response:
        """Retry the newest failed Original Attempt (append-only).

        Same Generation, same immutable snapshot, new ``mode="original"``
        Attempt; the failed attempt is retained untouched and a Preview is
        never retried as an Original.
        """
        generation_id = request.match_info["generation_id"]
        service = _open_generate_original_service()
        result = await service.retry(generation_id)
        return web.json_response(dict(result.payload), status=result.http_status)

    @_route("post", f"{BASE}/generations/{{generation_id}}/resume")
    async def history_v2_generation_resume(request: web.Request) -> web.Response:
        """Resume an interrupted ordinary modern Single (F1A, append-only).

        Bodyless.  Re-executes the interrupted immutable request with its
        frozen semantic output mode preserved (never converted to Original);
        the interrupted Attempt is retained and a fresh queued Attempt is
        created under the SAME Generation/snapshot inside one guarded
        transaction.  Failed/canceled/completed/active generations are
        refused truthfully; Experiment cells resume through the Experiment
        surface.
        """
        generation_id = request.match_info["generation_id"]
        service = _open_generate_original_service()
        result = await service.resume_single(generation_id)
        return web.json_response(dict(result.payload), status=result.http_status)

    # ── Experiment detail ──────────────────────────────────────────────

    @_route("get", f"{BASE}/experiments/{{experiment_id}}")
    async def history_v2_experiment_detail(request: web.Request) -> web.Response:
        experiment_id = request.match_info["experiment_id"]
        repo = _open_repo()
        detail = repo.get_experiment(experiment_id)
        if detail is None:
            return _json_error(404, "experiment not found")
        exp = detail.experiment
        cells = detail.cells
        gen_ids = [c.generation_id for c in cells if c.generation_id]
        assets_by_gen: dict[str, list[Asset]] = {}
        for asset in repo.get_assets_for_generations(gen_ids):
            assets_by_gen.setdefault(asset.generation_id, []).append(asset)
        attempts_by_cell: dict[str, list[RunAttempt]] = {}
        for attempt in repo.get_attempts_for_cells([c.cell_id for c in cells]):
            if attempt.cell_id is None:
                continue
            attempts_by_cell.setdefault(attempt.cell_id, []).append(attempt)
        # Load each cell's generation detail (attempts, assets, snapshot)
        # once per generation; favorites are derived from the same records so
        # the existing per-generation lookup is reused rather than duplicated.
        gen_detail_by_id: dict[str, GenerationDetail] = {}
        for gid in set(gen_ids):
            gdetail = repo.get_generation(gid)
            if gdetail is not None:
                gen_detail_by_id[gid] = gdetail
        fav_by_gen = {
            gid: bool(gdetail.generation.favorite)
            for gid, gdetail in gen_detail_by_id.items()
        }

        item = _experiment_feed_item(exp.to_dict(), cells, assets_by_gen)
        axis_names = _axis_labels(cells, exp.definition)
        # F9: the SAME lazy per-variant export projector as generation
        # detail, so every embedded cell Generation projects identical
        # variant asset ids / export states.  No Experiment-specific state.
        export_service = HistoryV2ExportService(repo)

        def _export_state_of(asset_id: str) -> str:
            return export_service.get_export_state(
                asset_id, persist_missing=True
            ).state

        item["cells"] = [
            _detail_cell(
                c,
                assets_by_gen,
                attempts_by_cell,
                fav_by_gen,
                axis_names,
                generation_payload=(
                    _cell_generation_payload(
                        gen_detail_by_id[c.generation_id],
                        export_state_of=_export_state_of,
                    )
                    if c.generation_id and c.generation_id in gen_detail_by_id
                    else None
                ),
            )
            for c in cells
        ]
        cover: list[Optional[dict[str, Any]]] = [
            {"thumb_url": _cell_thumb_url(c, assets_by_gen), "cellKey": c.cell_id}
            for c in cells[:4]
        ]
        while len(cover) < 4:
            cover.append(None)
        item["cover"] = cover
        return web.json_response({"status": "ok", "item": item})

    # ── Generation annotations ─────────────────────────────────────────

    @_route("patch", f"{BASE}/generations/{{generation_id}}/favorite")
    async def history_v2_generation_favorite(request: web.Request) -> web.Response:
        generation_id = request.match_info["generation_id"]
        body = await _read_json(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        favorite = body.get("favorite")
        if not isinstance(favorite, bool):
            return _json_error(400, "favorite must be a boolean")
        repo = _open_repo()
        if not repo.set_favorite(generation_id, favorite):
            return _json_error(404, "generation not found")
        return web.json_response({"status": "ok", "favorite": favorite})

    @_route("patch", f"{BASE}/generations/{{generation_id}}/note")
    async def history_v2_generation_note(request: web.Request) -> web.Response:
        generation_id = request.match_info["generation_id"]
        body = await _read_json(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        note = body.get("note")
        if not isinstance(note, str):
            return _json_error(400, "note must be a string")
        repo = _open_repo()
        try:
            ok = repo.set_note(generation_id, note)
        except ValueError as exc:
            return _json_error(400, str(exc.args[0]) if exc.args else "invalid note")
        if not ok:
            return _json_error(404, "generation not found")
        return web.json_response({"status": "ok", "note": note})

    @_route("patch", f"{BASE}/generations/{{generation_id}}/featured")
    async def history_v2_generation_featured(request: web.Request) -> web.Response:
        generation_id = request.match_info["generation_id"]
        body = await _read_json(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        repo = _open_repo()
        detail = repo.get_generation(generation_id)
        if detail is None:
            return _json_error(404, "generation not found")
        asset_id: Optional[str] = None
        if "output_index" in body:
            index = body.get("output_index")
            if isinstance(index, bool) or not isinstance(index, int):
                return _json_error(400, "invalid output_index")
            outputs = _build_outputs(detail.assets, attempts=detail.attempts)
            if index < 0 or index >= len(outputs):
                return _json_error(400, "invalid output_index")
            asset_id = outputs[index]["asset_id"]
        elif "asset_id" in body:
            asset_id = body.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id:
                return _json_error(400, "invalid asset_id")
        else:
            return _json_error(400, "missing output_index or asset_id")
        if asset_id is None:
            return _json_error(400, "missing output_index or asset_id")
        if not repo.set_featured_asset(generation_id, asset_id):
            return _json_error(400, "asset does not belong to generation")
        return web.json_response({"status": "ok", "featured_asset_id": asset_id})

    # ── Experiment annotations ─────────────────────────────────────────

    @_route("patch", f"{BASE}/experiments/{{experiment_id}}/favorite")
    async def history_v2_experiment_favorite(request: web.Request) -> web.Response:
        experiment_id = request.match_info["experiment_id"]
        body = await _read_json(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        favorite = body.get("favorite")
        if not isinstance(favorite, bool):
            return _json_error(400, "favorite must be a boolean")
        repo = _open_repo()
        if not repo.set_experiment_favorite(experiment_id, favorite):
            return _json_error(404, "experiment not found")
        return web.json_response({"status": "ok", "favorite": favorite})

    @_route("patch", f"{BASE}/experiments/{{experiment_id}}/note")
    async def history_v2_experiment_note(request: web.Request) -> web.Response:
        experiment_id = request.match_info["experiment_id"]
        body = await _read_json(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        note = body.get("note")
        if not isinstance(note, str):
            return _json_error(400, "note must be a string")
        repo = _open_repo()
        try:
            ok = repo.set_experiment_note(experiment_id, note)
        except ValueError as exc:
            return _json_error(400, str(exc.args[0]) if exc.args else "invalid note")
        if not ok:
            return _json_error(404, "experiment not found")
        return web.json_response({"status": "ok", "note": note})

    # ── Managed asset serving ──────────────────────────────────────────

    @_route("get", f"{BASE}/assets/{{asset_id}}")
    async def history_v2_asset(request: web.Request) -> web.Response:
        asset_id = request.match_info["asset_id"]
        repo = _open_repo()
        asset = repo.get_asset(asset_id)
        if asset is None:
            return _json_error(404, "asset not found")
        managed_path = str(asset.managed_path)
        if managed_path.startswith("modal://"):
            # Remote producer reference: served through the SHARED internal
            # byte-resolution helper (F9) so Export reuses the exact same
            # semantics.  Browser Download (this GET) writes ZERO export
            # state — it must never enter the Export service.
            try:
                body: bytes = await _read_remote_managed_bytes(asset)
            except _ManagedAssetError as exc:
                return _json_error(exc.status, exc.message)
            return web.Response(body=body, content_type=_content_type_for(asset))
        path = Path(managed_path)
        if not path.is_file():
            return _json_error(404, "asset file not found")
        try:
            body = path.read_bytes()
        except OSError:
            _log.exception("Failed to read managed asset %s", asset_id)
            return _json_error(500, "asset read error")
        return web.Response(body=body, content_type=_content_type_for(asset))

    # ── Configured-folder Export (F9) ──────────────────────────────────

    @_route("post", f"{BASE}/assets/{{asset_id}}/export")
    async def history_v2_asset_export(request: web.Request) -> web.Response:
        """Export ONE selected managed asset into the configured output folder.

        BODYLESS by contract: the selected ``asset_id`` uniquely identifies
        the managed History source.  Generation association, logical-output
        index, naming context, and the live canonical Output settings are
        derived and validated SERVER-SIDE; client-supplied generation/
        output/naming identity is neither read nor honored.
        """
        asset_id = request.match_info["asset_id"]
        repo = _open_repo()
        asset = repo.get_asset(asset_id)
        if asset is None:
            return _export_error_response(
                404, asset_id, "asset_not_found",
                "asset not found in History V2 store", "not_exported",
            )

        # Structural availability WITHOUT fetching bytes (managed-asset GET
        # truth).  Failing here writes no record — no real attempt occurred.
        structural = _managed_source_structural_error(asset)
        if structural is not None:
            return _export_error_response(
                structural.status, asset_id, "source_unreadable",
                structural.message, "not_exported",
            )

        # Server-owned association truth: derive the Generation from the
        # asset's own durable generation_id; never trust client identity.
        detail = repo.get_generation(str(asset.generation_id))
        if detail is None:
            return _export_error_response(
                404, asset_id, "generation_not_found",
                "asset generation unavailable in History V2 store",
                "not_exported",
            )

        # Real logical-output index from current grouping — fail closed
        # rather than silently assigning index 0.
        output_index = _derive_output_index(detail.assets, asset)
        if output_index is None:
            return _export_error_response(
                500, asset_id, "output_index_unresolved",
                "asset cannot be mapped to a logical output", "not_exported",
            )

        # Live canonical Output settings authority (explicit action NOW).
        if settings_provider is None:
            return _export_error_response(
                503, asset_id, "settings_unavailable",
                "export settings authority is not wired", "not_exported",
            )
        try:
            raw_settings = settings_provider()
        except Exception as exc:
            _log.exception("Export settings provider failed for %s", asset_id)
            return _export_error_response(
                500, asset_id, "settings_unavailable",
                f"export settings unavailable: {str(exc)[:120]}",
                "not_exported",
            )
        options = _export_options_from_settings(
            raw_settings if isinstance(raw_settings, dict) else {}
        )
        naming = _export_naming_from_detail(detail, output_index)

        # Request-scoped classification of remote serving failures so the
        # F7 `source_unreadable` reason can map to its truthful HTTP status
        # (404 missing vs 502 retrieval failure) without diverging from the
        # shared byte-resolution semantics.
        classified_status: dict[str, int] = {}

        async def _export_byte_resolver(resolved_asset: Asset) -> bytes:
            try:
                return await _read_remote_managed_bytes(resolved_asset)
            except _ManagedAssetError as exc:
                classified_status["status"] = exc.status
                raise

        service = HistoryV2ExportService(repo, byte_resolver=_export_byte_resolver)
        async with _asset_export_lock(asset_id):
            try:
                result = await service.export_asset(asset_id, options, naming)
            except Exception:
                _log.exception("History V2 export crashed for %s", asset_id)
                return _export_error_response(
                    500, asset_id, "export_failed",
                    "export failed unexpectedly", "failed",
                )

        if result.ok:
            return web.json_response(
                {
                    "status": "ok",
                    "asset_id": asset_id,
                    "export_state": result.state,
                    # Contract: an already-exported exact reuse reports
                    # saved=false + already_exported=true (the F7 core's
                    # ExportResult.saved stays true on reuse; the HTTP
                    # surface maps it to the frozen response contract).
                    "saved": bool(result.saved) and not result.already_exported,
                    "already_exported": bool(result.already_exported),
                    "destination_path": result.destination_path,
                    "metadata_path": result.metadata_path,
                    "byte_count": int(result.byte_count),
                    "file_ext": result.file_ext,
                    "mime_type": result.mime_type,
                    "exported_at": result.exported_at,
                },
                status=200,
            )

        status_map = {
            "asset_not_found": 404,
            "remote_resolver_unavailable": 502,
            "source_unreadable": classified_status.get("status", 502),
            "hash_mismatch": 502,
            "conversion_failed": 500,
            "write_failed": 500,
            "record_persist_failed": 500,
        }
        http_status = status_map.get(result.reason or "", 500)
        return _export_error_response(
            http_status,
            asset_id,
            result.reason or "export_failed",
            result.message or "export failed",
            result.state,
            partial=result.partial,
        )
