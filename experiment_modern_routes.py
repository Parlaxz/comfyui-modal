"""Modern experiment REST surface (Phase D4, additive only).

Frozen REST contract (``PHASE_D_INTERFACE_FREEZE.md`` §11).  Routes are
additive; no legacy endpoint is replaced or hijacked::

    POST /comfymodal/studio/experiment-v2
    GET  /comfymodal/history-v2/experiments/{experiment_id}/status
    POST /comfymodal/history-v2/experiments/{experiment_id}/cancel
    POST /comfymodal/history-v2/experiments/{experiment_id}/resume
    POST /comfymodal/history-v2/experiments/{experiment_id}/cells/{cell_id}/retry

Two additive convenience aliases kept from the earlier partial file (they do
not exist in the legacy History V2 surface and never shadow it)::

    POST /comfymodal/history-v2/experiments                      (create alias)
    POST /comfymodal/history-v2/experiments/{experiment_id}/start

Create/start is a frozen-body acceptance:

* the request is validated (``experiment_id`` / ``name`` / ``definition``
  object; top-level ``concurrency`` / ``cells`` / raw immutable-request shape
  is rejected as ``INVALID_DEFINITION``);
* the definition is expanded lazily by
  ``experiment_modern_plan.build_cell_plan`` — the single modern seam; no
  legacy graph injector and no invented Generation/Modal callback;
* the complete matrix (Experiment + fixed ordered cells + one stable
  Generation + one queued first attempt per valid cell + a terminal failed
  first attempt per planning-invalid cell + immutable request snapshots + the
  full definition with every ``CellPlan.to_dict()`` and axis metadata) is
  committed through ``HistoryV2Repository.create_modern_matrix`` in ONE
  transaction BEFORE any scheduler dispatch; it never falls back to
  ``create_experiment``;
* scheduler dispatch happens only when a scheduler is registered for the
  experiment; otherwise the accepted matrix stays durably queued and the
  response reports ``started: false`` (a durable acceptance, not a
  half-acceptance).

Status is a flat durable projection built from repository/model derivation
with the current-attempt ``(created_at, run_id)`` tie-break.  ``partial`` is
never emitted; ``queued``/``running`` always aggregate to ``running``; the
heavy immutable request is never included in the polling payload.

Actions never fabricate cancellation or attempts in route helpers: queued
cancel uses the atomic ``cancel_queued_attempt`` repository seam without
execution, running cancel dispatches only to a registered scheduler that
advertises a truthful remote-cancel capability (otherwise ``503
CANCELLATION_UNAVAILABLE`` and the running attempts stay durable, while
queued cells are still atomically canceled so the experiment stops
launching), and resume/retry delegate attempt creation/claim to the
scheduler or the guarded single-transaction repository methods
(``create_resume_attempt`` / ``create_retry_attempt``) — never an unguarded
append.

Public functions:
    register_experiment_modern_routes(server, data_root, registry=None, node_dir=None, transport_factory=None)
    startup_experiment_modern_lifecycle(data_root, registry=None)   # async, aiohttp-safe
    shutdown_experiment_modern_lifecycle(registry=None)             # async, aiohttp-safe

Lifecycle: startup recovery is idempotent and limited to stale ``running``
attempts belonging to modern experiments (they become ``interrupted``);
queued and terminal attempts are unchanged.  Shutdown stops new launches,
shuts down each owned scheduler (best-effort remote close + ``interrupted``
for its active attempts only), and never repo-wide marks legacy attempts.

History V2 is the durable state; the planner (``experiment_modern_plan``) and
scheduler (``experiment_modern_scheduler``) are resolved lazily and never
imported at module import time.  No legacy ``ServiceRegistry``, leases,
journal, or ``scheduler_state.json`` is used.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import logging
import sqlite3
from collections.abc import Mapping as _MappingABC
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

from history_v2_models import current_attempt
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store

_log = logging.getLogger(__name__)

STUDIO_CREATE_PATH = "/comfymodal/studio/experiment-v2"
HISTORY_BASE = "/comfymodal/history-v2"
ASSET_URL_PREFIX = f"{HISTORY_BASE}/assets/"

_ACTION_NAMES = {
    "start": ("start_experiment", "start"),
    "cancel": ("cancel_experiment", "cancel"),
    "resume": ("resume_experiment", "resume"),
    "retry_cell": ("retry_cell",),
}

# Frozen six canonical counts (never ``partial``, never ``skipped``).
_COUNT_KEYS = ("queued", "running", "completed", "failed", "canceled", "interrupted")
_TERMINAL_CANONICAL = frozenset({"completed", "failed", "canceled", "interrupted"})
_ACTIVE_ATTEMPT_STATUSES = frozenset({"queued", "pending", "running"})

# Marker used to identify durable experiments owned by the modern contract
# (startup recovery and shutdown never repo-wide mark legacy attempts).
_CONTRACT_MARKER = "modern_v2"
_DEFINITION_VERSION = 2

_SHUTDOWN_FLAG: list[bool] = [False]
_DEFAULT_DATA_ROOT: list[Optional[Any]] = [None]
_DEFAULT_NODE_DIR: list[Optional[Any]] = [None]
# Production scheduler-construction seam: a callable ``() -> transport`` used
# to build one shared per-experiment transport when a scheduler is constructed
# on create.  ``None`` means scheduler construction is explicitly unavailable
# and accepted experiments stay durably queued.  Injected via
# ``register_experiment_modern_routes(..., transport_factory=...)``.
_DEFAULT_TRANSPORT_FACTORY: list[Optional[Any]] = [None]


def _open_repository(data_root: Any) -> HistoryV2Repository:
    db_path = Path(data_root) / ".studio_history_v2" / "history_v2.db"
    return HistoryV2Repository(HistoryV2Store(db_path))


def _json_error(
    status: int,
    message: str,
    code: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> web.Response:
    payload: dict[str, Any] = {"status": "error", "message": message}
    if code:
        payload["code"] = code
    if extra:
        payload.update(extra)
    return web.json_response(payload, status=status)


async def _read_json(request: web.Request) -> Optional[dict[str, Any]]:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _exc_message(exc: Any) -> str:
    if isinstance(exc, BaseException):
        return (str(exc) or exc.__class__.__name__)[:300]
    return (str(exc) if exc is not None else "unknown error")[:300]


def _parse_iso_ms(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except Exception:
        return None


def _asset_url(asset_id: Optional[str]) -> str:
    return f"{ASSET_URL_PREFIX}{asset_id}" if asset_id else ""


def _plain(value: Any) -> Any:
    """Recursively thaw frozen mappings/tuples into plain JSON-safe containers."""
    if isinstance(value, _MappingABC):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


# ── Registry injection (testable) ─────────────────────────────────────────


def _lazy_module_registry() -> Any:
    try:
        mod = importlib.import_module("experiment_modern_scheduler")
    except Exception:
        return None
    getter = getattr(mod, "get_scheduler", None)
    if callable(getter):
        try:
            return mod
        except Exception:
            pass
    for attr in ("REGISTRY", "registry", "SCHEDULERS", "schedulers"):
        if hasattr(mod, attr):
            return getattr(mod, attr)
    return mod


def _resolve_registry(registry: Any) -> Any:
    if registry is not None:
        return registry
    return _lazy_module_registry()


def _resolve_scheduler(registry: Any, experiment_id: str) -> Any:
    if registry is None:
        return None
    if isinstance(registry, dict):
        return registry.get(experiment_id)
    if callable(registry):
        try:
            return registry(experiment_id)
        except Exception:
            return None
    getter = getattr(registry, "get_scheduler", None)
    if callable(getter):
        try:
            return getter(experiment_id)
        except Exception:
            return None
    getter = getattr(registry, "get", None)
    if callable(getter):
        try:
            return getter(experiment_id)
        except Exception:
            return None
    return registry


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _dispatch_action(registry: Any, experiment_id: str, action: str, *args: Any) -> tuple[str, Any]:
    scheduler = _resolve_scheduler(registry, experiment_id)
    if scheduler is None:
        return ("unavailable", None)
    for name in _ACTION_NAMES.get(action, ()):
        fn = getattr(scheduler, name, None)
        if not callable(fn):
            continue
        try:
            result = fn(*args)
            if inspect.isawaitable(result):
                result = await result
            return ("ok", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return ("error", exc)
    return ("unavailable", None)


async def _scheduler_cancel_cell(registry: Any, experiment_id: str, cell_id: str) -> tuple[str, Any]:
    """Dispatch a per-cell running cancel to the scheduler.

    Supports both the instance surface (``cancel_cell(cell_id, ...)``) and the
    module-level surface (``cancel_cell(experiment_id, cell_id, ...)``).
    """
    scheduler = _resolve_scheduler(registry, experiment_id)
    if scheduler is None:
        return ("unavailable", None)
    fn = getattr(scheduler, "cancel_cell", None)
    if not callable(fn):
        return ("unavailable", None)
    try:
        try:
            result = fn(cell_id, reason="user_cancel")
        except TypeError:
            result = fn(experiment_id, cell_id, reason="user_cancel")
        if inspect.isawaitable(result):
            result = await result
        return ("ok", result)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ("error", exc)


def _scheduler_has_remote_cancel(scheduler: Any) -> bool:
    """Truthful running-cell remote-cancel capability probe.

    Defaults to *unavailable* unless the scheduler advertises a real remote
    cancel primitive (``remote_cancel_available``) or holds a non-noop
    ``_remote_cancel`` callable.  A local iterator-close/noop is never
    labelled truthful (freeze §7 verdict B).
    """
    if scheduler is None:
        return False
    advertised = getattr(scheduler, "remote_cancel_available", None)
    if advertised is not None:
        if callable(advertised):
            try:
                return bool(advertised())
            except Exception:
                return False
        return bool(advertised)
    remote_cancel = getattr(scheduler, "_remote_cancel", None)
    if callable(remote_cancel):
        name = getattr(remote_cancel, "__name__", "") or ""
        module = getattr(remote_cancel, "__module__", "") or ""
        if name in ("_noop", "noop") and "experiment_modern_scheduler" in module:
            return False
        return True
    return False


def _iter_registry_schedulers(registry: Any) -> list[Any]:
    """List the owned schedulers of a registry for shutdown (never legacy)."""
    if registry is None:
        return []
    if isinstance(registry, dict):
        return list(registry.values())
    for attr in ("_SCHEDULERS", "SCHEDULERS", "schedulers", "registry", "schedulers_map"):
        value = getattr(registry, attr, None)
        if isinstance(value, dict):
            return list(value.values())
        if callable(value) and not inspect.isclass(value):
            try:
                value = value()
            except Exception:
                continue
            if isinstance(value, dict):
                return list(value.values())
    for name in ("values", "items", "all"):
        fn = getattr(registry, name, None)
        if callable(fn):
            try:
                result = fn()
            except Exception:
                continue
            if isinstance(result, dict):
                return list(result.values())
            if isinstance(result, (list, tuple)):
                return list(result)
    return []


# ── Scheduler construction for a newly accepted Experiment (D3 binding) ──


def _bound_repository(repo: HistoryV2Repository, experiment_id: str) -> HistoryV2Repository:
    """A repository bound to *experiment_id* for the scheduler adapter.

    The modern scheduler persistence methods that take no experiment argument
    (``load_queued_cells`` / ``list_recoverable_cells`` / ``aggregate_status``)
    require the experiment scope; cell-scoped operations resolve it from the
    cell row.  ``initialize`` is idempotent.
    """
    return HistoryV2Repository(repo._store, experiment_id=experiment_id)


def _build_scheduler_for_experiment(
    registry: Any,
    experiment_id: str,
    cell_plan: Any,
    repo: HistoryV2Repository,
    node_dir: Any,
) -> Any:
    """Construct + register one scheduler for a newly accepted Experiment.

    Uses the scheduler module factory with the existing bound repository, the
    immutable cell plans, and a shared per-experiment transport (one
    ``transport_factory()`` call per experiment).  Returns the scheduler, or
    ``None`` when construction is explicitly unavailable (no transport factory
    configured, no factory in the scheduler module, no cells, or a
    construction error) — the accepted matrix then stays durably queued and
    the response must not claim ``started``.
    """
    transport_factory = _DEFAULT_TRANSPORT_FACTORY[0]
    if transport_factory is None:
        return None
    cells = getattr(cell_plan, "cells", None)
    if not cells:
        return None
    mod = _lazy_module_registry()
    factory = getattr(mod, "build_experiment_scheduler", None) if mod is not None else None
    if factory is None:
        return None
    try:
        scheduler = factory(
            experiment_id=experiment_id,
            cell_plans=list(cells),
            persistence=_bound_repository(repo, experiment_id),
            transport_factory=transport_factory,
        )
    except Exception:
        _log.exception("scheduler construction failed for %s", experiment_id)
        return None
    # The scheduler registers itself in the scheduler module registry; also
    # register into a test-injected non-module registry so dispatch finds it.
    if registry is not None and registry is not mod:
        if isinstance(registry, dict):
            registry[experiment_id] = scheduler
        else:
            register = getattr(registry, "register_scheduler", None)
            if callable(register):
                try:
                    register(scheduler)
                except Exception:
                    _log.exception(
                        "scheduler registration failed for %s", experiment_id
                    )
    return scheduler


# ── Status derivation (repository/model derivation, current-attempt tie-break)


def _canonical_cell_status(cell: Any) -> str:
    status = cell.status
    if status in ("pending", "queued"):
        return "queued"
    if status in _TERMINAL_CANONICAL or status == "running":
        return status
    # Modern cells never produce ``skipped``/unknown; fall back to queued.
    return "queued"


def _counts_from_cells(cells: list[Any]) -> dict[str, int]:
    counts = {k: 0 for k in _COUNT_KEYS}
    for cell in cells:
        counts[_canonical_cell_status(cell)] += 1
    return counts


def _aggregate_from_counts(counts: dict[str, int]) -> str:
    """Frozen truth table (§10); ``queued``/``running`` always map to running."""
    if counts["queued"] > 0 or counts["running"] > 0:
        return "running"
    if counts["interrupted"] > 0:
        return "interrupted"
    if counts["canceled"] > 0:
        return "canceled"
    if counts["failed"] > 0:
        return "completed_with_failures"
    return "completed"


def _active_attempt(attempts: list[Any]) -> Optional[Any]:
    current = current_attempt(attempts) if attempts else None
    if current is not None and current.status in _ACTIVE_ATTEMPT_STATUSES:
        return current
    return None


def _attempt_duration_ms(attempt: Optional[Any]) -> Optional[int]:
    if attempt is None or not attempt.started_at or not attempt.finished_at:
        return None
    start_ms = _parse_iso_ms(attempt.started_at)
    finish_ms = _parse_iso_ms(attempt.finished_at)
    if start_ms is None or finish_ms is None:
        return None
    return max(finish_ms - start_ms, 0)


def _cell_duration_ms(attempts: list[Any]) -> Optional[int]:
    if not attempts:
        return None
    return _attempt_duration_ms(current_attempt(attempts))


def _attempts_map(repo: HistoryV2Repository, cells: list[Any]) -> dict[str, list[Any]]:
    by_cell: dict[str, list[Any]] = {}
    cell_ids = [c.cell_id for c in cells]
    if not cell_ids:
        return by_cell
    for attempt in repo.get_attempts_for_cells(cell_ids):
        if attempt.cell_id:
            by_cell.setdefault(attempt.cell_id, []).append(attempt)
    return by_cell


def _plan_cells(definition: Any) -> dict[str, dict[str, Any]]:
    """Index the persisted definition's ``cells`` (every ``CellPlan.to_dict()``)."""
    plan_cells: dict[str, dict[str, Any]] = {}
    raw = definition.get("cells") if isinstance(definition, dict) else None
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and entry.get("cell_id"):
                plan_cells[entry["cell_id"]] = entry
    return plan_cells


def _build_status_detail(repo: HistoryV2Repository, experiment_id: str) -> Optional[dict[str, Any]]:
    """Flat durable status projection (§11.2).

    Cell identity/status come from the repository-derived cell rows
    (``current_attempt`` tie-break, terminal-first-wins).  Workflow/version/
    preset identity comes from the durable definition plan (the authoritative
    fixed-matrix index) because the current Generation insert does not carry
    those fields correctly.  No ``partial``, no client inference, no heavy
    immutable request in the polling payload.
    """
    detail = repo.get_experiment(experiment_id)
    if detail is None:
        return None
    exp = detail.experiment
    cells = detail.cells
    plan_cells = _plan_cells(exp.definition)
    attempts_by_cell = _attempts_map(repo, cells)
    gen_ids = [c.generation_id for c in cells if c.generation_id]
    assets_by_gen: dict[str, list[Any]] = {}
    for asset in repo.get_assets_for_generations(gen_ids):
        assets_by_gen.setdefault(asset.generation_id, []).append(asset)
    gen_by_id: dict[str, Any] = {}
    for gid in set(gen_ids):
        gdetail = repo.get_generation(gid)
        if gdetail is not None:
            gen_by_id[gid] = gdetail

    counts = {k: 0 for k in _COUNT_KEYS}
    cell_records: list[dict[str, Any]] = []
    active_attempt_ids: list[str] = []
    workflow_ids: set[str] = set()
    workflow_version_ids: set[str] = set()
    preset_ids: set[str] = set()
    for cell in cells:  # fixed position order
        canonical = _canonical_cell_status(cell)
        counts[canonical] += 1
        attempts = attempts_by_cell.get(cell.cell_id, [])
        active = _active_attempt(attempts)
        plan = plan_cells.get(cell.cell_id, {})
        gen = gen_by_id.get(cell.generation_id) if cell.generation_id else None
        gen_dict = gen.generation.to_dict() if gen else {}
        assets = assets_by_gen.get(cell.generation_id, []) if cell.generation_id else []
        thumb = next((a for a in assets if a.type == "thumbnail"), None)
        output_asset = next((a for a in assets if a.type in ("original", "preview", "thumbnail")), None)
        error = cell.error
        if error is None:
            current = current_attempt(attempts)
            if current is not None and current.error:
                error = current.error
        axis_values = plan.get("axis_values")
        if not isinstance(axis_values, dict):
            axis_values = dict(cell.axis_labels or {})
        axis_names = plan.get("axis_labels")
        if not isinstance(axis_names, list) or not axis_names:
            axis_names = list(axis_values.keys())
        workflow_id = str(plan.get("workflow_id") or "")
        workflow_version_id = str(
            plan.get("workflow_version_id") or gen_dict.get("workflow_version_id") or ""
        )
        preset_id = str(plan.get("preset_id") or "")
        if active is not None:
            active_attempt_ids.append(active.run_id)
        if workflow_id:
            workflow_ids.add(workflow_id)
        if workflow_version_id:
            workflow_version_ids.add(workflow_version_id)
        if preset_id:
            preset_ids.add(preset_id)
        cell_records.append({
            "cell_id": cell.cell_id,
            "position": cell.position,
            "status": canonical,
            "active_attempt_id": active.run_id if active is not None else None,
            "generation_id": cell.generation_id,
            "workflow_id": workflow_id,
            "workflow_version_id": workflow_version_id,
            "preset_id": preset_id,
            "workflow_name": str(plan.get("workflow_name") or ""),
            "preset_name": str(plan.get("preset_name") or ""),
            "axis_labels": dict(cell.axis_labels or {}),
            "axis_values": axis_values,
            "axes": axis_names,
            "error": error,
            "duration_ms": _cell_duration_ms(attempts),
            "thumbnail_url": _asset_url(thumb.asset_id) if thumb else "",
            "output_reference": _asset_url(output_asset.asset_id) if output_asset else None,
        })

    return {
        "status": "ok",
        "experiment_id": exp.experiment_id,
        "name": exp.name,
        "aggregate_status": _aggregate_from_counts(counts),
        "total": len(cells),
        "counts": counts,
        "active_attempt_ids": active_attempt_ids,
        "workflow_ids": sorted(workflow_ids),
        "workflow_version_ids": sorted(workflow_version_ids),
        "preset_ids": sorted(preset_ids),
        "cells": cell_records,
    }


# ── Create-body validation (frozen immutable request shape) ───────────────


_BANNED_TOP_LEVEL_KEYS = (
    "concurrency",
    "cells",
    "raw",
    "immutable_request",
    "execution_plan",
    "workflow_snapshot",
)


def _validate_create_body(body: Any) -> dict[str, Any]:
    """Validate the frozen create/start request body.

    Returns ``{"experiment_id", "name", "definition"}`` on success, or
    ``{"error", "errors": [...]}`` for a globally malformed request.
    """
    if not isinstance(body, dict):
        return {
            "error": "request body must be a JSON object",
            "errors": [{"field": "body", "message": "expected a JSON object"}],
        }
    for key in _BANNED_TOP_LEVEL_KEYS:
        if key in body:
            return {
                "error": (
                    f"top-level {key!r} is not accepted by the modern create "
                    "contract; send an immutable 'definition' object"
                ),
                "errors": [
                    {
                        "field": key,
                        "message": "immutable request shape is not accepted at the top level",
                    }
                ],
            }
    experiment_id = body.get("experiment_id")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        return {
            "error": "experiment_id is required",
            "errors": [{"field": "experiment_id", "message": "experiment_id must be a non-empty string"}],
        }
    name = body.get("name")
    if name is not None and not isinstance(name, str):
        return {
            "error": "name must be a string",
            "errors": [{"field": "name", "message": "name must be a string"}],
        }
    definition = body.get("definition")
    if not isinstance(definition, dict):
        return {
            "error": "definition must be an object",
            "errors": [{"field": "definition", "message": "definition must be an object"}],
        }
    try:
        json.dumps(definition, allow_nan=False)
    except (TypeError, ValueError) as exc:
        return {
            "error": f"definition is not JSON-serializable: {_exc_message(exc)}",
            "errors": [
                {
                    "field": "definition",
                    "message": "definition must be strict-JSON serializable",
                }
            ],
        }
    return {
        "experiment_id": experiment_id.strip(),
        "name": name,
        "definition": dict(definition),
    }


# ── Planner + matrix acceptance ───────────────────────────────────────────


def _load_planner() -> Any:
    """Lazily load the modern planner (never at module import time)."""
    try:
        import experiment_modern_plan as _emp

        return _emp
    except Exception:
        return None


def _stable_modern_id(prefix: str, seed: str, salt: str) -> str:
    """Deterministic stable id minted per cell (``gen_``/``run_`` + digest)."""
    digest = hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:16]}"


def _cell_specs_from_plan(cell_plan: Any, experiment_id: str) -> list[dict[str, Any]]:
    """Map every ``CellPlan.to_dict()`` to a ``create_modern_matrix`` spec.

    The repository seam now consumes the planner's ``CellPlan.to_dict()``
    shape verbatim: it freezes generation/workflow/version/preset identity,
    stores the exact executable request snapshot fields (§4.2), and derives a
    terminal ``failed`` first attempt for a planning-invalid cell (spec
    ``error``/``error_code``) while valid cells get one queued first attempt.
    A deterministic stable ``generation_id``/``run_id`` is minted per cell so
    the same definition always accepts the same stable identities.
    """
    specs: list[dict[str, Any]] = []
    for cell in cell_plan.cells:
        d = cell.to_dict()
        cell_key = str(d.get("cell_key") or d.get("cell_id") or f"{experiment_id}:{d.get('position', 0)}")
        spec = dict(d)
        spec["generation_id"] = _stable_modern_id("gen_", cell_key, "generation")
        spec["run_id"] = _stable_modern_id("run_", cell_key, "attempt-0")
        specs.append(spec)
    return specs


def _definition_payload(
    experiment_id: str,
    name: Optional[str],
    definition: dict[str, Any],
    cell_plan: Any,
) -> dict[str, Any]:
    """Versioned durable definition: request definition + axis metadata + every
    ``CellPlan.to_dict()`` (authoritative fixed-matrix index, §4.2)."""
    return {
        "version": _DEFINITION_VERSION,
        "contract": _CONTRACT_MARKER,
        "experiment_id": experiment_id,
        "name": name,
        "definition": definition,
        "axis_labels": list(cell_plan.axis_labels),
        "axis_metadata": {
            "expected_cell_count": len(cell_plan.cells),
            "cell_ordering": list(cell_plan.cell_ordering),
            "modal_options": _plain(cell_plan.modal_options),
            "workflow_branches": [dict(b) for b in cell_plan.workflow_branches],
        },
        "cells": [cell.to_dict() for cell in cell_plan.cells],
    }


def _count_of(result: Any, key: str) -> int:
    if isinstance(result, dict):
        if key in result:
            value = result[key]
            return int(value) if isinstance(value, (int, float)) else 0
        counts = result.get("counts")
        if isinstance(counts, dict) and key in counts:
            value = counts[key]
            return int(value) if isinstance(value, (int, float)) else 0
    return 0


def _ok_status_response(repo: HistoryV2Repository, experiment_id: str, extra: Optional[dict[str, Any]] = None) -> web.Response:
    status = _build_status_detail(repo, experiment_id) or {}
    payload: dict[str, Any] = {
        "status": "ok",
        "experiment_id": experiment_id,
        "aggregate_status": status.get("aggregate_status"),
        "total": status.get("total"),
        "counts": status.get("counts"),
    }
    if extra:
        payload.update(extra)
    return web.json_response(payload, status=200)


# ── Handlers ──────────────────────────────────────────────────────────────


async def _handle_create(request: web.Request, data_root: Any, registry: Any, node_dir: Any) -> web.Response:
    if _SHUTDOWN_FLAG[0]:
        return _json_error(503, "experiment lifecycle is shutting down")
    body = await _read_json(request)
    if body is None:
        return _json_error(400, "Invalid JSON body", code="INVALID_DEFINITION")
    validated = _validate_create_body(body)
    if "error" in validated:
        return _json_error(
            400,
            validated["error"],
            code="INVALID_DEFINITION",
            extra={"errors": validated["errors"]},
        )
    experiment_id = validated["experiment_id"]
    name = validated.get("name")
    definition = validated["definition"]

    repo = _open_repository(data_root)
    if repo.get_experiment(experiment_id) is not None:
        return _json_error(
            409,
            "experiment already exists",
            code="EXPERIMENT_EXISTS",
            extra={"experiment_id": experiment_id},
        )

    planner = _load_planner()
    if planner is None:
        return _json_error(
            500,
            "modern experiment planner is unavailable",
            code="PERSISTENCE_ERROR",
            extra={"experiment_id": experiment_id},
        )

    definition = dict(definition)
    definition["experiment_id"] = experiment_id
    try:
        cell_plan = planner.build_cell_plan(definition, node_dir)
    except planner.ExperimentDefinitionError as exc:
        return _json_error(
            400,
            str(exc),
            code="INVALID_DEFINITION",
            extra={"errors": [{"field": "definition", "message": str(exc)}]},
        )
    except Exception as exc:
        _log.exception("definition planning failed for %s", experiment_id)
        return _json_error(
            400,
            f"definition planning failed: {_exc_message(exc)}",
            code="INVALID_DEFINITION",
            extra={"errors": [{"field": "definition", "message": _exc_message(exc)}]},
        )

    specs = _cell_specs_from_plan(cell_plan, experiment_id)
    definition_payload = _definition_payload(experiment_id, name, definition, cell_plan)

    try:
        repo.create_modern_matrix(
            experiment_id=experiment_id,
            name=name,
            definition=definition_payload,
            cells=specs,
        )
    except sqlite3.IntegrityError:
        # Lost the create race: the experiment row already exists.
        return _json_error(
            409,
            "experiment already exists",
            code="EXPERIMENT_EXISTS",
            extra={"experiment_id": experiment_id},
        )
    except Exception as exc:
        _log.exception("experiment matrix persistence failed for %s", experiment_id)
        return _json_error(
            500,
            f"experiment persistence failed: {_exc_message(exc)}",
            code="PERSISTENCE_ERROR",
            extra={"experiment_id": experiment_id},
        )

    # Planning-invalid cells must carry a terminal failed first attempt with
    # no Modal submission before any scheduler action (§3.3 preferred upfront
    # model).  The current ``create_modern_matrix`` seam creates that atomically
    # inside the acceptance transaction (spec ``error``); the reconcile below is
    # a defensive no-op for that path and only backfills older repository
    # implementations.  Terminal-first-wins guards make it idempotent.
    try:
        for spec, cell in zip(specs, cell_plan.cells):
            if not cell.ok:
                stored = repo.get_attempt(spec["run_id"])
                if stored is not None and stored.status != "failed":
                    repo.update_attempt_status(
                        spec["run_id"],
                        "failed",
                        error=cell.error or "cell planning failed",
                    )
    except Exception as exc:
        _log.exception("failed-cell persistence failed for %s", experiment_id)
        return _json_error(
            500,
            f"failed-cell persistence failed: {_exc_message(exc)}",
            code="PERSISTENCE_ERROR",
            extra={"experiment_id": experiment_id},
        )

    # Dispatch only to a REGISTERED scheduler: construct one for the accepted
    # matrix FIRST (bound repository + immutable cell plans + one shared
    # per-experiment transport).  When construction is explicitly unavailable
    # the accepted matrix stays durably queued and ``started`` is false (a
    # durable acceptance, never a half-acceptance — never claim started when
    # no scheduler is bound).
    started = False
    notice: Optional[str] = None
    resolved = _resolve_registry(registry)
    if resolved is not None:
        scheduler = _build_scheduler_for_experiment(
            resolved, experiment_id, cell_plan, repo, node_dir
        )
        if scheduler is None:
            _log.warning(
                "experiment %s accepted but no scheduler could be constructed; "
                "staying durably queued",
                experiment_id,
            )
        else:
            outcome, result = await _dispatch_action(resolved, experiment_id, "start", experiment_id)
            if outcome == "ok":
                started = True
            elif outcome == "error":
                notice = f"scheduler start failed: {_exc_message(result)}"
                _log.warning("experiment %s accepted but scheduler start failed: %s", experiment_id, notice)

    status = _build_status_detail(repo, experiment_id) or {}
    payload: dict[str, Any] = {
        "status": "ok",
        "experiment_id": experiment_id,
        "started": started,
        "aggregate_status": status.get("aggregate_status") or "running",
        "total": status.get("total", len(specs)),
        "counts": status.get("counts") or {k: 0 for k in _COUNT_KEYS},
    }
    if notice:
        payload["notice"] = notice
    return web.json_response(payload, status=200)


async def _handle_status(request: web.Request, data_root: Any) -> web.Response:
    experiment_id = request.match_info["experiment_id"]
    repo = _open_repository(data_root)
    detail = _build_status_detail(repo, experiment_id)
    if detail is None:
        return _json_error(
            404,
            "experiment not found",
            code="EXPERIMENT_NOT_FOUND",
            extra={"experiment_id": experiment_id},
        )
    return web.json_response(detail, status=200)


async def _handle_start(request: web.Request, data_root: Any, registry: Any) -> web.Response:
    """Additive alias: dispatch a registered scheduler for an existing
    accepted-but-queued experiment.  Never creates anything durably."""
    if _SHUTDOWN_FLAG[0]:
        return _json_error(503, "experiment lifecycle is shutting down")
    experiment_id = request.match_info["experiment_id"]
    repo = _open_repository(data_root)
    if repo.get_experiment(experiment_id) is None:
        return _json_error(
            404,
            "experiment not found",
            code="EXPERIMENT_NOT_FOUND",
            extra={"experiment_id": experiment_id},
        )
    started = False
    notice: Optional[str] = None
    resolved = _resolve_registry(registry)
    if resolved is not None:
        outcome, result = await _dispatch_action(resolved, experiment_id, "start", experiment_id)
        if outcome == "ok":
            started = True
        elif outcome == "error":
            notice = f"start action failed: {_exc_message(result)}"
            _log.warning("start failed for experiment %s: %s", experiment_id, notice)
    extra: dict[str, Any] = {"started": started}
    if notice:
        extra["notice"] = notice
    return _ok_status_response(repo, experiment_id, extra)


async def _handle_cancel(request: web.Request, data_root: Any, registry: Any) -> web.Response:
    experiment_id = request.match_info["experiment_id"]
    repo = _open_repository(data_root)
    detail = repo.get_experiment(experiment_id)
    if detail is None:
        return _json_error(
            404,
            "experiment not found",
            code="EXPERIMENT_NOT_FOUND",
            extra={"experiment_id": experiment_id},
        )

    statuses = [_canonical_cell_status(c) for c in detail.cells]
    if statuses and all(s in _TERMINAL_CANONICAL for s in statuses):
        if all(s == "canceled" for s in statuses):
            # Repeated cancel of an already-canceled Experiment is idempotent 200.
            return web.json_response(
                {"status": "ok", "experiment_id": experiment_id, "message": "experiment is already canceled"},
                status=200,
            )
        return _json_error(
            409,
            "experiment is terminal and cannot be cancelled",
            code="EXPERIMENT_TERMINAL",
            extra={"experiment_id": experiment_id},
        )

    running_cells = [c for c, s in zip(detail.cells, statuses) if s == "running"]
    queued_cells = [c for c, s in zip(detail.cells, statuses) if s == "queued"]

    def _cancel_queued_cells() -> Optional[web.Response]:
        """Atomically cancel the queued cells via the guarded repo seam.

        No execution and no new attempt: each queued current attempt flips
        queued → canceled first-wins inside its own transaction.  Safe to run
        even when running-cell cancellation is unavailable (durable cancel of
        queued cells is never tied to a remote primitive).  Returns an error
        response only if a durable write itself fails.
        """
        attempts_by_cell = _attempts_map(repo, detail.cells)
        for cell in queued_cells:
            attempts = attempts_by_cell.get(cell.cell_id, [])
            current = current_attempt(attempts)
            if current is not None and current.status in ("queued", "pending"):
                try:
                    repo.cancel_queued_attempt(current.run_id)
                except Exception as exc:
                    return _json_error(
                        500,
                        f"queued cancel failed for cell {cell.cell_id}: {_exc_message(exc)}",
                        code="PERSISTENCE_ERROR",
                        extra={"experiment_id": experiment_id, "cell_id": cell.cell_id},
                    )
        return None

    if running_cells:
        resolved = _resolve_registry(registry)
        scheduler = _resolve_scheduler(resolved, experiment_id) if resolved is not None else None
        if scheduler is None or not _scheduler_has_remote_cancel(scheduler):
            # Truthful: no running-cell remote cancel primitive.  Never fake
            # running cells as canceled, but still atomically cancel the
            # queued cells (no submission) so the experiment stops launching;
            # then report the running cells truthfully as non-cancellable.
            error = _cancel_queued_cells()
            if error is not None:
                return error
            return _json_error(
                503,
                "running-cell cancellation is unavailable; running cells remain durable",
                code="CANCELLATION_UNAVAILABLE",
                extra={"experiment_id": experiment_id, "running_cells": [c.cell_id for c in running_cells]},
            )
        for cell in running_cells:
            outcome, result = await _scheduler_cancel_cell(resolved, experiment_id, cell.cell_id)
            if outcome != "ok" or str(result) == "cancel_unconfirmed":
                # Truthful: the remote primitive was invoked but did not
                # confirm (or the channel failed).  Never fabricate running
                # cells as canceled — the scheduler left the durable running
                # state untouched — but still atomically cancel the queued
                # cells (no submission) so the experiment stops launching;
                # then report the running cells truthfully as non-cancellable.
                error = _cancel_queued_cells()
                if error is not None:
                    return error
                return _json_error(
                    503,
                    "running-cell cancellation is unconfirmed and remains unavailable",
                    code="CANCELLATION_UNAVAILABLE",
                    extra={
                        "experiment_id": experiment_id,
                        "cell_id": cell.cell_id,
                        "detail": _exc_message(result) if result is not None else None,
                    },
                )

    # Queued cancel: atomic repository seam, no execution, no new attempt.
    error = _cancel_queued_cells()
    if error is not None:
        return error

    return _ok_status_response(repo, experiment_id)


async def _handle_resume(request: web.Request, data_root: Any, registry: Any) -> web.Response:
    experiment_id = request.match_info["experiment_id"]
    repo = _open_repository(data_root)
    detail = repo.get_experiment(experiment_id)
    if detail is None:
        return _json_error(
            404,
            "experiment not found",
            code="EXPERIMENT_NOT_FOUND",
            extra={"experiment_id": experiment_id},
        )

    interrupted = [c for c in detail.cells if _canonical_cell_status(c) == "interrupted"]
    queued = [c for c in detail.cells if _canonical_cell_status(c) == "queued"]
    if not interrupted and not queued:
        return _json_error(
            409,
            "no resumable cells",
            code="NO_RESUMABLE_CELLS",
            extra={"experiment_id": experiment_id},
        )

    created_runs: list[dict[str, Any]] = []
    resumed_count = 0
    resolved = _resolve_registry(registry)
    scheduler = _resolve_scheduler(resolved, experiment_id) if resolved is not None else None
    outcome: str = "unavailable"
    if scheduler is not None:
        outcome, result = await _dispatch_action(resolved, experiment_id, "resume", experiment_id)
        if outcome == "error":
            return _json_error(
                500,
                f"resume action failed: {_exc_message(result)}",
                code="PERSISTENCE_ERROR",
                extra={"experiment_id": experiment_id},
            )
        if outcome == "ok":
            resumed_count = _count_of(result, "resumed")
        # outcome == "unavailable" -> fall through to durable creation below.
    if scheduler is None or (outcome == "unavailable"):
        # Route-level durable creation via the guarded single-transaction
        # repository adapter: an interrupted cell gets a fresh queued attempt
        # under the same Generation/snapshot (its interrupted attempt is left
        # untouched, append-only); queued never-started cells keep their
        # existing queued attempt (the scheduler claims it on dispatch).  The
        # guard atomically re-checks the CURRENT attempt inside the
        # transaction, so a None return (cell no longer interrupted, e.g. a
        # concurrent claim) is skipped — a duplicate resume stays idempotent.
        # No execution happens here.
        for cell in interrupted:
            try:
                claim = repo.create_resume_attempt(cell.cell_id)
            except Exception as exc:
                return _json_error(
                    500,
                    f"resume failed for cell {cell.cell_id}: {_exc_message(exc)}",
                    code="PERSISTENCE_ERROR",
                    extra={"experiment_id": experiment_id, "cell_id": cell.cell_id},
                )
            if claim is None or claim.attempt is None:
                continue  # not eligible anymore (idempotent no-op)
            created_runs.append({"cell_id": cell.cell_id, "run_id": claim.attempt.run_id})
            resumed_count += 1

    return _ok_status_response(
        repo,
        experiment_id,
        {
            "resumed": resumed_count,
            "created_attempts": created_runs,
            "resumable_cells": [c.cell_id for c in interrupted + queued],
        },
    )


async def _handle_retry(request: web.Request, data_root: Any, registry: Any) -> web.Response:
    experiment_id = request.match_info["experiment_id"]
    cell_id = request.match_info["cell_id"]
    repo = _open_repository(data_root)
    detail = repo.get_experiment(experiment_id)
    if detail is None:
        return _json_error(
            404,
            "experiment not found",
            code="EXPERIMENT_NOT_FOUND",
            extra={"experiment_id": experiment_id},
        )
    cell = repo.get_experiment_cell(cell_id)
    if cell is None or cell.experiment_id != experiment_id:
        return _json_error(
            404,
            "cell not found",
            code="CELL_NOT_FOUND",
            extra={"experiment_id": experiment_id, "cell_id": cell_id},
        )
    if _canonical_cell_status(cell) != "failed":
        return _json_error(
            409,
            "only a failed cell can be retried",
            code="CELL_NOT_FAILED",
            extra={"experiment_id": experiment_id, "cell_id": cell_id},
        )
    if not cell.generation_id:
        return _json_error(
            500,
            f"cell {cell_id} has no generation",
            code="PERSISTENCE_ERROR",
            extra={"experiment_id": experiment_id, "cell_id": cell_id},
        )

    run_id: Optional[str] = None
    resolved = _resolve_registry(registry)
    scheduler = _resolve_scheduler(resolved, experiment_id) if resolved is not None else None
    if scheduler is not None:
        outcome, result = await _dispatch_action(resolved, experiment_id, "retry_cell", experiment_id, cell_id)
        if outcome == "error":
            return _json_error(
                500,
                f"retry action failed: {_exc_message(result)}",
                code="PERSISTENCE_ERROR",
                extra={"experiment_id": experiment_id, "cell_id": cell_id},
            )
        if outcome == "ok":
            if result is False:
                return _json_error(
                    409,
                    "only a failed cell can be retried",
                    code="CELL_NOT_FAILED",
                    extra={"experiment_id": experiment_id, "cell_id": cell_id},
                )
            attempts = [a for a in repo.get_attempts_for_cells([cell_id]) if a.cell_id == cell_id]
            current = current_attempt(attempts)
            run_id = current.run_id if current is not None else None
        else:
            scheduler = None  # outcome == "unavailable" -> durable fallback below
    if scheduler is None:
        # Guarded single-transaction fallback: only a cell whose CURRENT
        # attempt is ``failed`` is eligible (atomically re-checked inside the
        # transaction); the new attempt reuses the same Generation/snapshot.
        # A None return means the cell transitioned away from failed (race) —
        # report the frozen CELL_NOT_FAILED error.
        try:
            claim = repo.create_retry_attempt(cell_id)
        except Exception as exc:
            return _json_error(
                500,
                f"retry failed: {_exc_message(exc)}",
                code="PERSISTENCE_ERROR",
                extra={"experiment_id": experiment_id, "cell_id": cell_id},
            )
        if claim is None or claim.attempt is None:
            return _json_error(
                409,
                "only a failed cell can be retried",
                code="CELL_NOT_FAILED",
                extra={"experiment_id": experiment_id, "cell_id": cell_id},
            )
        run_id = claim.attempt.run_id

    return _ok_status_response(
        repo,
        experiment_id,
        {"cell_id": cell_id, "run_id": run_id, "retried": True},
    )


# ── Registration ──────────────────────────────────────────────────────────


def register_experiment_modern_routes(
    server: Any,
    data_root: Any,
    registry: Any = None,
    node_dir: Any = None,
    transport_factory: Any = None,
) -> None:
    """Register the additive modern Experiment routes on *server*.

    *server* may be a ComfyUI PromptServer, an aiohttp UrlDispatcher, or an
    aiohttp.web.Application.  *registry* is the testable scheduler-registry
    injection point (defaults to the scheduler module registry).  *node_dir*
    is passed to the planner's workflow seam and defaults to the ComfyUI root
    derived from this module's location.  *transport_factory* is the
    production scheduler-construction seam: a callable ``() -> transport``
    used to build one shared per-experiment transport when a scheduler is
    constructed on create; ``None`` keeps accepted experiments durably queued
    (scheduler construction explicitly unavailable).
    """
    _DEFAULT_DATA_ROOT[0] = data_root
    if node_dir is None:
        node_dir = _DEFAULT_NODE_DIR[0] or Path(__file__).resolve().parents[2]
    _DEFAULT_NODE_DIR[0] = node_dir
    _DEFAULT_TRANSPORT_FACTORY[0] = transport_factory

    def _route(method: str, path: str):
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
        # aiohttp RouteTableDef-style surface.
        return getattr(routes, method)(path)

    @_route("post", STUDIO_CREATE_PATH)
    async def experiment_v2_create(request: web.Request) -> web.Response:
        return await _handle_create(request, data_root, registry, node_dir)

    @_route("post", f"{HISTORY_BASE}/experiments")
    async def history_v2_experiments_create(request: web.Request) -> web.Response:
        # Additive alias preserved from the partial file (no legacy conflict).
        return await _handle_create(request, data_root, registry, node_dir)

    @_route("get", f"{HISTORY_BASE}/experiments/{{experiment_id}}/status")
    async def experiment_v2_status(request: web.Request) -> web.Response:
        return await _handle_status(request, data_root)

    @_route("post", f"{HISTORY_BASE}/experiments/{{experiment_id}}/start")
    async def experiment_v2_start(request: web.Request) -> web.Response:
        return await _handle_start(request, data_root, registry)

    @_route("post", f"{HISTORY_BASE}/experiments/{{experiment_id}}/cancel")
    async def experiment_v2_cancel(request: web.Request) -> web.Response:
        return await _handle_cancel(request, data_root, registry)

    @_route("post", f"{HISTORY_BASE}/experiments/{{experiment_id}}/resume")
    async def experiment_v2_resume(request: web.Request) -> web.Response:
        return await _handle_resume(request, data_root, registry)

    @_route("post", f"{HISTORY_BASE}/experiments/{{experiment_id}}/cells/{{cell_id}}/retry")
    async def experiment_v2_cell_retry(request: web.Request) -> web.Response:
        return await _handle_retry(request, data_root, registry)


# ── Lifecycle (aiohttp-safe; no fire-and-forget) ──────────────────────────


def _modern_experiment_ids(repo: HistoryV2Repository) -> list[str]:
    """Ids of experiments owned by the modern contract (marker in definition)."""
    ids: list[str] = []
    try:
        rows = repo._store.execute("SELECT experiment_id, definition_json FROM experiments")
    except Exception:
        return ids
    for row in rows:
        try:
            definition = json.loads(row["definition_json"] or "{}")
        except Exception:
            continue
        if isinstance(definition, dict) and definition.get("contract") == _CONTRACT_MARKER:
            ids.append(row["experiment_id"])
    return ids


def _sweep_stale_running(repo: HistoryV2Repository, experiment_ids: list[str]) -> list[str]:
    """Idempotent startup recovery: only stale ``running`` attempts of modern
    experiments become ``interrupted``; queued and terminal stay unchanged."""
    marked: list[str] = []
    if not experiment_ids:
        return marked
    placeholders = ",".join("?" * len(experiment_ids))
    try:
        rows = repo._store.execute(
            f"SELECT run_id FROM run_attempts "
            f"WHERE status = 'running' AND experiment_id IN ({placeholders})",
            experiment_ids,
        )
    except Exception:
        return marked
    for row in rows:
        try:
            repo.update_attempt_status(row["run_id"], "interrupted", error="startup recovery")
            marked.append(row["run_id"])
        except Exception:
            pass
    return marked


async def _call_with_reason(fn: Any, reason: str = "shutdown") -> Any:
    try:
        return await _maybe_await(fn(reason=reason))
    except TypeError:
        return await _maybe_await(fn())


async def startup_experiment_modern_lifecycle(data_root: Any, registry: Any = None) -> dict[str, Any]:
    """Idempotent startup sweep (aiohttp ``on_startup``-safe, fully awaited).

    Marks only stale ``running`` attempts belonging to modern experiments as
    ``interrupted``; queued/not-started and terminal attempts are unchanged.
    """
    _DEFAULT_DATA_ROOT[0] = data_root
    _SHUTDOWN_FLAG[0] = False
    repo = _open_repository(data_root)
    marked = _sweep_stale_running(repo, _modern_experiment_ids(repo))
    resolved = _resolve_registry(registry)
    hooks: list[str] = []
    if resolved is not None:
        for name in ("startup_recovery", "recover", "startup", "on_startup"):
            fn = getattr(resolved, name, None)
            if callable(fn):
                try:
                    await _maybe_await(fn())
                    hooks.append(name)
                except Exception:
                    _log.exception("experiment modern startup hook failed: %s", name)
    return {"status": "ok", "marked_interrupted": marked, "registry_hooks": hooks}


async def shutdown_experiment_modern_lifecycle(registry: Any = None) -> dict[str, Any]:
    """Stop launches, shut down owned schedulers, mark ONLY owned running
    attempts interrupted (aiohttp ``on_shutdown``-safe, fully awaited).

    Never repo-wide marks legacy attempts on shutdown.  Queued cells stay
    queued; all cells/order/results are preserved.
    """
    _SHUTDOWN_FLAG[0] = True
    resolved = _resolve_registry(registry)
    hooks: list[str] = []
    if resolved is not None:
        for name in ("stop_new_launches", "stop"):
            fn = getattr(resolved, name, None)
            if callable(fn):
                try:
                    await _maybe_await(fn())
                    hooks.append(name)
                except Exception:
                    _log.exception("experiment modern stop hook failed: %s", name)
    owned = _iter_registry_schedulers(resolved)
    for scheduler in owned:
        experiment_id = getattr(scheduler, "experiment_id", "?")
        shutdown_fn = getattr(scheduler, "shutdown", None)
        if callable(shutdown_fn):
            try:
                await _call_with_reason(shutdown_fn, reason="shutdown")
                hooks.append(f"scheduler:{experiment_id}")
            except Exception:
                _log.exception(
                    "experiment modern scheduler shutdown failed for %s", experiment_id
                )
        else:
            for name in ("cancel_experiment", "cancel"):
                fn = getattr(scheduler, name, None)
                if callable(fn):
                    try:
                        await _maybe_await(fn())
                        hooks.append(f"scheduler:{experiment_id}:{name}")
                    except Exception:
                        _log.exception(
                            "experiment modern scheduler cancel failed for %s", experiment_id
                        )
                    break
    return {"status": "ok", "shutdown_hooks": hooks, "owned_schedulers": len(owned)}
