"""History V2 production writer: the single V2 write boundary for production
history events.

Mirrors the legacy ``RunHistoryService`` production events
(``experiment_service.py`` — ``record_run`` / ``update_run``) into the
History V2 SQLite store: the same ``<data_root>/.studio_history_v2/
history_v2.db`` database the V2 routes use (see ``history_v2_routes``).
Later lanes call this module from the production call sites.  This module
never writes to or modifies the legacy ``.run_history`` files.

Design rules:
- Deterministic ids derived from production identity (sha256 truncated to
  12 hex chars, prefixed per repo convention) + existence checks make every
  write idempotent (duplicate terminal callbacks, reconnect/replay, retry).
- Every public method is fully exception-isolated: it catches ``Exception``,
  logs via ``logging.getLogger("history_v2_writer")`` and returns a safe
  default (``{}`` / ``False`` / ``None``).  Never re-raises.
- Importable standalone: module-level imports are stdlib + the three
  ``history_v2_*`` siblings.  ``local_artifacts`` and ``PIL`` are imported
  lazily inside methods; ``server.PromptServer`` is probed lazily.
- First-terminal-wins: once an attempt stores a terminal status it is never
  overwritten by a replayed different outcome.
"""
from __future__ import annotations

import hashlib
import io
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from history_v2_models import (
    Asset,
    TERMINAL_RUN_STATUSES,
    logical_output_key_from_metadata,
    normalize_logical_output_key,
    utc_now_iso,
)
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store, default_data_root

logger = logging.getLogger("history_v2_writer")


# ── Module-level writer configuration ────────────────────────────────────
# ``set_writer_data_root`` / ``set_writer_enabled`` are test overrides.
# ``get_writer`` caches one writer per resolved data root.
_DATA_ROOT_OVERRIDE: Optional[Path] = None
_ENABLED_OVERRIDE: Optional[bool] = None
_WRITERS: dict[str, "HistoryV2ProductionWriter"] = {}
_WRITERS_LOCK = threading.Lock()
# Producer-asset resolution override (test seam); cleared by
# ``reset_writer_config``.  Production default resolves through
# ``experiment_service.REGISTRY.leases().resolve_asset`` (lazy).
_ASSET_RESOLVER_OVERRIDE: Optional[Callable[[str], Optional[dict]]] = None


def set_writer_data_root(path: Any) -> None:
    """Test override for the writer data root; also implies enabled."""
    global _DATA_ROOT_OVERRIDE, _ENABLED_OVERRIDE
    _DATA_ROOT_OVERRIDE = Path(path)
    _ENABLED_OVERRIDE = True


def set_writer_enabled(enabled: bool) -> None:
    """Explicit enable/disable override (used by tests)."""
    global _ENABLED_OVERRIDE
    _ENABLED_OVERRIDE = bool(enabled)


def set_asset_resolver(fn: Optional[Callable[[str], Optional[dict]]]) -> None:
    """Test override for producer primary-asset resolution.

    ``fn(asset_id)`` returns the producer asset record dict or None.  Clearing
    restores the production ``experiment_service.REGISTRY.leases()`` path.
    """
    global _ASSET_RESOLVER_OVERRIDE
    _ASSET_RESOLVER_OVERRIDE = fn


def reset_writer_config() -> None:
    """Clear all overrides and the per-data-root writer cache (tests)."""
    global _DATA_ROOT_OVERRIDE, _ENABLED_OVERRIDE, _ASSET_RESOLVER_OVERRIDE
    _DATA_ROOT_OVERRIDE = None
    _ENABLED_OVERRIDE = None
    _ASSET_RESOLVER_OVERRIDE = None
    with _WRITERS_LOCK:
        _WRITERS.clear()


def _server_available() -> bool:
    """Lazily probe whether the ComfyUI PromptServer is running."""
    try:
        from server import PromptServer  # type: ignore
        return PromptServer.instance is not None
    except ImportError:
        logger.debug("history_v2_writer: 'server' module not importable; writer disabled")
        return False
    except Exception:
        logger.debug("history_v2_writer: PromptServer probe failed; writer disabled")
        return False


def get_writer(data_root: Any = None) -> Optional["HistoryV2ProductionWriter"]:
    """Return the (cached) production writer for the resolved data root.

    - ``data_root`` explicitly passed → always return a writer for it.
    - Otherwise enabled only when an explicit ``set_writer_enabled(True)``
      override is set OR the ComfyUI ``PromptServer.instance`` is running.
      When not enabled → ``None``.
    - When enabled without a ``data_root`` → module-level override if set,
      else ``history_v2_store.default_data_root()``.
    """
    if data_root is not None:
        resolved = Path(data_root)
    else:
        if _ENABLED_OVERRIDE is not None:
            if not _ENABLED_OVERRIDE:
                return None
        else:
            if not _server_available():
                return None
        if _DATA_ROOT_OVERRIDE is not None:
            resolved = _DATA_ROOT_OVERRIDE
        else:
            resolved = default_data_root()
    key = str(Path(resolved).resolve())
    with _WRITERS_LOCK:
        writer = _WRITERS.get(key)
        if writer is None:
            try:
                writer = HistoryV2ProductionWriter(resolved)
            except Exception:
                logger.exception(
                    "history_v2_writer: failed to build writer for data root %s", key
                )
                return None
            _WRITERS[key] = writer
        return writer


# ── Deterministic id helpers ─────────────────────────────────────────────
# sha256 of the production identity, truncated to 12 hex chars, prefixed per
# repo convention.  Same production identity → same V2 id (idempotency).


def _digest(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def _gen_id(run_id: str) -> str:
    return "gen_" + _digest(f"v2gen:{run_id}")


def _run_id(run_id: str) -> str:
    return "run_" + _digest(f"v2run:{run_id}")


def _cell_gen_id(experiment_id: str, cell_key: str) -> str:
    return "gen_" + _digest(f"v2cellgen:{experiment_id}:{cell_key}")


def _cell_run_id(experiment_id: str, cell_key: str, attempt_id: str) -> str:
    return "run_" + _digest(f"v2cellrun:{experiment_id}:{cell_key}:{attempt_id}")


def _cell_id(experiment_id: str, cell_key: str) -> str:
    return "cell_" + _digest(f"v2cell:{experiment_id}:{cell_key}")


def _looks_like_hash(value: Any) -> bool:
    """True when *value* is a workflow content hash (64 lowercase hex chars).

    Modern Studio workflow identity ids (``wf_*`` / ``wv_*``) must NOT be
    treated as content hashes for late-binding comparisons, so the
    update-time mismatch warning is skipped for those records.
    """
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(c in "0123456789abcdef" for c in value)


# ── Status mapping ───────────────────────────────────────────────────────

_LEGACY_STATUS_MAP = {
    "submitted": "queued",
    "running": "running",
    "completed": "completed",
    "error": "failed",
    "failed": "failed",
    "canceled": "canceled",
    "interrupted": "interrupted",
    # Attempt-level detail preserved in timing metadata by the writer.
    "completed_with_failures": "completed",
}

_TERMINAL_STATUS_VALUES = frozenset(s.value for s in TERMINAL_RUN_STATUSES)

_EXPERIMENT_STATUS_MAP = {
    "completed": "completed",
    "completed_with_failures": "completed_with_failures",
    "interrupted": "interrupted",
    "canceled": "canceled",
    "failed": "failed",
    "stopped": "interrupted",
}

_SKIPPED_KINDS = frozenset({"deploy", "warmup"})

_CELL_PARAM_KEYS = (
    "prompt", "negative_prompt", "seed", "steps", "guidance", "sampler",
    "scheduler", "denoise", "width", "height", "unet", "clip", "vae",
    "lora_chain",
)

_SNAPSHOT_PARAM_KEYS = (
    "seed", "steps", "guidance", "cfg", "sampler", "scheduler", "denoise",
    "width", "height", "prompt", "negative_prompt",
)

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})

# Asset types that count as visible "output" imagery (mirrors the route
# contract in history_v2_routes).
_OUTPUT_ASSET_TYPES = frozenset({"thumbnail", "preview", "original"})

_THUMBNAIL_MAX = 256

# Asset types that count as REQUIRED workflow results (never derivatives).
# A Thumbnail alone must never satisfy the required-output association gate.
_REQUIRED_ASSET_TYPES = frozenset({"preview", "original"})

# Semantic variant values that map a producer/result record onto a History
# Asset type.  Unknown variants stay backward-compatible Originals.
_VARIANT_ASSET_TYPES = {
    "preview": "preview",
    "original": "original",
    "main": "original",
    "thumbnail": "thumbnail",
}


def semantic_output_mode(meta: Any) -> str:
    """Explicit immutable output mode from E2B request/result metadata.

    Reads ``output_mode`` (then ``variant``) from *meta* and returns exactly
    ``"preview"`` or ``"original"``.  Preview is NEVER inferred from codec,
    quality, extension, filename, or MIME type; a legacy call without the
    semantic field safely defaults to ``"original"``.
    """
    if not isinstance(meta, dict):
        return "original"
    for key in ("output_mode", "variant"):
        value = meta.get(key)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("preview", "original"):
                return normalized
    return "original"


def _asset_type_for_variant(variant: Any) -> str:
    """History Asset type for a producer/result variant (default original)."""
    if isinstance(variant, str):
        return _VARIANT_ASSET_TYPES.get(variant.strip().lower(), "original")
    return "original"


def map_status(status: Any) -> str:
    """Map a legacy production status string to a V2 ``RunStatus.value``."""
    if not isinstance(status, str) or not status:
        logger.warning("history_v2_writer: non-string status %r mapped to 'failed'", status)
        return "failed"
    mapped = _LEGACY_STATUS_MAP.get(status)
    if mapped is not None:
        return mapped
    logger.warning(
        "history_v2_writer: unknown production status %r mapped to 'failed'", status
    )
    return "failed"


# ── Meta extraction helpers ──────────────────────────────────────────────


def _nested_get(meta: dict, key: str) -> Any:
    """Top-level lookup with a nested ``extra`` fallback (legacy meta shapes)."""
    value = meta.get(key)
    if value:
        return value
    extra = meta.get("extra")
    if isinstance(extra, dict):
        value = extra.get(key)
        if value:
            return value
    return None


def _normalize_model_stack(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [m for m in value if isinstance(m, dict)]
    return []


def _extract_prompt(meta: dict) -> str:
    for value in (
        meta.get("prompt"),
        meta.get("requested_controls", {}).get("prompt")
        if isinstance(meta.get("requested_controls"), dict) else None,
        meta.get("resolved_controls", {}).get("prompt")
        if isinstance(meta.get("resolved_controls"), dict) else None,
    ):
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_negative_prompt(meta: dict) -> str:
    for value in (
        meta.get("negative_prompt"),
        meta.get("requested_controls", {}).get("negative_prompt")
        if isinstance(meta.get("requested_controls"), dict) else None,
        meta.get("resolved_controls", {}).get("negative_prompt")
        if isinstance(meta.get("resolved_controls"), dict) else None,
    ):
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_error(meta: dict) -> Optional[str]:
    for key in ("error", "_error_detail"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _extract_cell_params(meta: dict, params: Optional[dict]) -> dict[str, Any]:
    """Params: explicit ``params`` dict first, then meta, then controls."""
    out: dict[str, Any] = {}
    params_dict = params if isinstance(params, dict) else {}
    controls = meta.get("requested_controls")
    controls = controls if isinstance(controls, dict) else {}
    for key in _CELL_PARAM_KEYS:
        value = params_dict.get(key)
        if value is None:
            value = meta.get(key)
        if value is None:
            value = controls.get(key)
        if value is not None:
            out[key] = value
    return out


def _extract_snapshot_params(meta: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    controls = meta.get("requested_controls")
    controls = controls if isinstance(controls, dict) else {}
    for key in _SNAPSHOT_PARAM_KEYS:
        value = meta.get(key)
        if value is None:
            value = controls.get(key)
        if value is not None:
            out[key] = value
    return out


def _asset_dimension(meta: dict, key: str) -> Optional[int]:
    """int width/height from meta or resolved_controls (tolerates digits)."""
    value = meta.get(key)
    if isinstance(value, bool):
        value = None
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int):
        controls = meta.get("resolved_controls")
        if isinstance(controls, dict):
            value = controls.get(key)
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
    return value


def _candidate_logical_output_key(
    meta: dict, candidate: str, index: int, total: int
) -> Optional[str]:
    keys = meta.get("logical_output_keys")
    if isinstance(keys, (list, tuple)) and index < len(keys):
        key = logical_output_key_from_metadata(
            {"logical_output_key": keys[index]}
        )
        if key:
            return key

    descriptors: list[dict] = []
    for field in ("asset_descriptors", "output_descriptors"):
        value = meta.get(field)
        if isinstance(value, list):
            descriptors.extend(item for item in value if isinstance(item, dict))
    candidate_name = Path(candidate).name
    descriptor = next(
        (
            item for item in descriptors
            if candidate_name in {
                str(item.get("filename") or ""),
                Path(str(item.get("path") or item.get("backend_path") or "")).name,
            }
        ),
        None,
    )
    if descriptor is None and len(descriptors) == total and index < len(descriptors):
        descriptor = descriptors[index]
    if descriptor is not None:
        key = logical_output_key_from_metadata(descriptor)
        if key:
            return key

    if total == 1:
        return logical_output_key_from_metadata(meta)
    return None


def _collect_output_candidates(output_path: Any, meta: dict) -> list[str]:
    """Unique non-empty strings from (output_path, meta output_paths, meta output_path)."""
    raw: list[str] = []
    if isinstance(output_path, str) and output_path:
        raw.append(output_path)
    paths = meta.get("output_paths")
    if isinstance(paths, str) and paths:
        raw.append(paths)
    elif isinstance(paths, (list, tuple)):
        raw.extend(p for p in paths if isinstance(p, str) and p)
    single = meta.get("output_path")
    if isinstance(single, str) and single:
        raw.append(single)
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _collect_cell_output_paths(output_path: Any, meta: dict) -> list[str]:
    """Cell-flow output candidates from the ``output_path`` param + meta."""
    raw: list[str] = []
    if isinstance(output_path, str) and output_path:
        raw.append(output_path)
    paths = meta.get("output_paths")
    if isinstance(paths, str) and paths:
        raw.append(paths)
    elif isinstance(paths, (list, tuple)):
        raw.extend(p for p in paths if isinstance(p, str) and p)
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


# ── Producer asset resolution (LeaseRegistry seam) ───────────────────────


def resolve_producer_asset(asset_id: Any) -> Optional[dict]:
    """Resolve a producer primary asset id through the LeaseRegistry assets
    table (lazy), honoring a test override hook.

    Returns the producer asset record dict, or None when the id is unknown,
    the override returns nothing, or the registry is unavailable (e.g. a
    history shim without ``leases()``).  Never raises.
    """
    if not isinstance(asset_id, str) or not asset_id:
        return None
    if _ASSET_RESOLVER_OVERRIDE is not None:
        try:
            return _ASSET_RESOLVER_OVERRIDE(asset_id)
        except Exception as exc:
            logger.debug(
                "history_v2_writer: asset resolver override failed for %r: %s",
                asset_id, exc,
            )
            return None
    try:
        from experiment_service import REGISTRY
        leases = REGISTRY.leases()
    except Exception as exc:
        logger.debug(
            "history_v2_writer: lease registry unavailable for %r: %s",
            asset_id, exc,
        )
        return None
    try:
        return leases.resolve_asset(asset_id)
    except Exception as exc:
        logger.debug(
            "history_v2_writer: producer asset resolve failed for %r: %s",
            asset_id, exc,
        )
        return None


def preflight_producer_asset(asset_id: Any) -> bool:
    """True when a producer primary asset id resolves to a usable record.

    Small resolver/preflight helper shared with ``studio_workflow_run``: an
    unknown or unavailable id (including a history shim without ``leases()``)
    resolves to False, never raising.
    """
    return resolve_producer_asset(asset_id) is not None


def _producer_reference(record: dict) -> tuple[Optional[str], Optional[str]]:
    """``(reference, source_path)`` for a producer asset record.

    Remote ``modal://`` origins stay a verbatim reference (served remotely);
    local paths become a path reference (no bytes copied).
    """
    path_value = record.get("path")
    if not isinstance(path_value, str) or not path_value:
        return None, None
    if path_value.startswith("modal://"):
        return path_value, None
    return None, path_value


def _fmt_from_mime(mime_type: Any) -> Optional[str]:
    """Format token from a producer mime_type (``image/png`` → ``png``)."""
    if not isinstance(mime_type, str) or "/" not in mime_type:
        return None
    value = mime_type.split("/", 1)[1].strip().lower()
    return value or None


def _producer_dimension(value: Any) -> Optional[int]:
    """Positive int dimension from a producer record (0/None → None)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(value, int):
        return value if value > 0 else None
    return None


def _descriptor_for_asset(meta: Any, asset_id: str) -> Optional[dict]:
    """Find the descriptor dict for *asset_id* in result/history metadata.

    Searches ``derivative_descriptors``, ``asset_descriptors`` and
    ``output_descriptors``; matches on ``asset_id`` (the content-addressed
    producer identity).  Returns None when absent.
    """
    if not isinstance(meta, dict) or not asset_id:
        return None
    for field in ("derivative_descriptors", "asset_descriptors", "output_descriptors"):
        value = meta.get(field)
        if not isinstance(value, (list, tuple)):
            continue
        for item in value:
            if isinstance(item, dict) and str(item.get("asset_id") or "") == asset_id:
                return item
    return None


def _compact_json(value: dict) -> str:
    """Compact JSON encoding matching the repository's metadata storage."""
    import json as _json
    return _json.dumps(value, separators=(",", ":"), sort_keys=True)


def _derivative_ids_from_meta(meta: Any) -> list[str]:
    """Producer asset ids for Thumbnail derivatives referenced by *meta*.

    Sources: an explicit ``derivative_asset_ids`` list, plus any descriptor
    entry under ``derivative_descriptors`` / ``asset_descriptors`` /
    ``output_descriptors`` whose semantic ``variant`` is exactly
    ``thumbnail``.  Order-preserving de-duplication.
    """
    if not isinstance(meta, dict):
        return []
    ids: list[str] = []
    raw_ids = meta.get("derivative_asset_ids")
    if isinstance(raw_ids, (list, tuple)):
        ids.extend(
            str(value) for value in raw_ids
            if not isinstance(value, bool) and str(value)
        )
    for field in ("derivative_descriptors", "asset_descriptors", "output_descriptors"):
        value = meta.get(field)
        if not isinstance(value, (list, tuple)):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            variant = item.get("variant")
            if not isinstance(variant, str) or variant.strip().lower() != "thumbnail":
                continue
            asset_id = str(item.get("asset_id") or "")
            if asset_id:
                ids.append(asset_id)
    seen: set[str] = set()
    out: list[str] = []
    for asset_id in ids:
        if asset_id not in seen:
            seen.add(asset_id)
            out.append(asset_id)
    return out


class HistoryV2ProductionWriter:
    """Mirrors production run/experiment events into the History V2 store.

    Single V2 write boundary.  All public methods are exception-isolated:
    they catch ``Exception``, log truthfully via the ``history_v2_writer``
    logger and return safe defaults (``{}`` / ``False`` / ``None``).  Writes
    are idempotent via deterministic ids + existence checks.
    """

    def __init__(self, data_root: Any) -> None:
        self._data_root = Path(data_root)
        self._db_path = self._data_root / ".studio_history_v2" / "history_v2.db"
        self._store = HistoryV2Store(self._db_path)
        self._repo = HistoryV2Repository(self._store)

    # ── Single-run generation flow ──────────────────────────────────────

    def record_run(self, *, run_id, kind, status="running", prompt_id="",
                   workflow_hash="", meta=None, timings=None, output_path="",
                   started_at=None) -> dict:
        try:
            return self._record_run(
                run_id=run_id, kind=kind, status=status, prompt_id=prompt_id,
                workflow_hash=workflow_hash, meta=meta, timings=timings,
                output_path=output_path, started_at=started_at,
            )
        except Exception:
            logger.exception(
                "history_v2_writer: record_run failed for run_id=%r kind=%r",
                run_id, kind,
            )
            return {}

    def _record_run(self, *, run_id, kind, status, prompt_id, workflow_hash,
                    meta, timings, output_path, started_at) -> dict:
        meta = meta if isinstance(meta, dict) else {}
        kind_value = kind if isinstance(kind, str) else str(kind or "")
        if kind_value in _SKIPPED_KINDS:
            logger.debug(
                "history_v2_writer: record_run skipping kind=%r run_id=%r",
                kind_value, run_id,
            )
            return {}
        if kind_value == "experiment_cell":
            experiment_id = _nested_get(meta, "experiment_id")
            cell_key = _nested_get(meta, "cell_key")
            if not experiment_id or not cell_key:
                logger.warning(
                    "history_v2_writer: experiment_cell run %r missing "
                    "experiment_id/cell_key in meta; skipping", run_id,
                )
                return {}
            return self._mirror_cell_terminal(
                experiment_id=str(experiment_id),
                cell_key=str(cell_key),
                attempt_id=str(run_id),
                status=status,
                meta=meta,
                workflow_hash=workflow_hash,
                output_paths=_collect_cell_output_paths(output_path, meta) or None,
                timings=timings,
            )
        logger.debug(
            "history_v2_writer: record_run run_id=%r kind=%r prompt_id=%r",
            run_id, kind_value, prompt_id,
        )
        return self._record_single_run(
            run_id=run_id, status=status, prompt_id=prompt_id,
            workflow_hash=workflow_hash, meta=meta, timings=timings,
            output_path=output_path, started_at=started_at,
        )

    def _record_single_run(self, *, run_id, status, prompt_id, workflow_hash,
                           meta, timings, output_path, started_at) -> dict:
        generation_id = _gen_id(str(run_id))
        attempt_run_id = _run_id(str(run_id))
        started = started_at or utc_now_iso()

        existing = self._repo.get_generation(generation_id)
        if existing is None:
            self._repo.create_generation(
                generation_id=generation_id,
                workflow_id=meta.get("workflow_id") or workflow_hash or None,
                workflow_version_id=meta.get("workflow_version_id"),
                preset_id=meta.get("studio_preset_id") or meta.get("preset_id"),
                preset_name=meta.get("preset_name")
                or meta.get("studio_preset_label") or meta.get("preset_label"),
                prompt_text=_extract_prompt(meta),
                negative_prompt_text=_extract_negative_prompt(meta),
                model_stack=_normalize_model_stack(meta.get("model_stack")),
                created_at=started,
            )
        else:
            logger.debug(
                "history_v2_writer: duplicate record_run for %r; generation %s exists",
                run_id, generation_id,
            )

        if self._repo.get_attempt(attempt_run_id) is None:
            self._repo.add_attempt(
                generation_id, run_id=attempt_run_id,
                mode=semantic_output_mode(meta),
                started_at=started,
            )

        stored = self._apply_status(attempt_run_id, status, meta, timings=timings)
        if stored is None:
            stored = map_status(status)

        self._ensure_request_snapshot(generation_id, meta, workflow_hash)

        candidates = _collect_output_candidates(output_path, meta)
        if candidates:
            self._attach_output_assets(generation_id, attempt_run_id, candidates, meta)
        if meta.get("primary_asset_id"):
            self._attach_producer_asset(
                generation_id, attempt_run_id, str(meta.get("primary_asset_id")), meta,
            )
        self._attach_derivative_assets(generation_id, attempt_run_id, meta)

        return {
            "generation_id": generation_id,
            "run_id": attempt_run_id,
            "status": stored,
        }

    def update_run(self, run_id, *, status=None, meta=None, output_path=None,
                   timings=None, completed_at=None, workflow_hash=None,
                   primary_asset_id=None) -> dict:
        try:
            return self._update_run(
                run_id=run_id, status=status, meta=meta, output_path=output_path,
                timings=timings, completed_at=completed_at,
                workflow_hash=workflow_hash, primary_asset_id=primary_asset_id,
            )
        except Exception:
            logger.exception(
                "history_v2_writer: update_run failed for run_id=%r", run_id
            )
            return {}

    def _update_run(self, *, run_id, status, meta, output_path, timings,
                    completed_at, workflow_hash, primary_asset_id) -> dict:
        meta = meta if isinstance(meta, dict) else {}
        generation_id = _gen_id(str(run_id))
        attempt_run_id = _run_id(str(run_id))

        detail = self._repo.get_generation(generation_id)
        if detail is None:
            logger.debug(
                "history_v2_writer: update_run before record_run for %r; skipping",
                run_id,
            )
            return {}

        if self._repo.get_attempt(attempt_run_id) is None:
            self._repo.add_attempt(
                generation_id, run_id=attempt_run_id,
                mode=semantic_output_mode(meta),
            )

        if (
            workflow_hash
            and workflow_hash != detail.generation.workflow_id
            and (
                detail.generation.workflow_id is None
                or _looks_like_hash(detail.generation.workflow_id)
            )
        ):
            logger.debug(
                "history_v2_writer: update_run workflow_hash %r differs from stored "
                "%r for %r; not rewritten (no repo method for late binding)",
                workflow_hash, detail.generation.workflow_id, run_id,
            )

        stored = "queued"
        if status is not None:
            stored = self._apply_status(
                attempt_run_id, status, meta,
                completed_at=completed_at, timings=timings,
            )
            if stored is None:
                stored = map_status(status)
        else:
            current = self._repo.get_attempt(attempt_run_id)
            if current is not None:
                stored = current.status

        candidates = _collect_output_candidates(output_path or "", meta)
        new_assets: list[Asset] = []
        if candidates:
            new_assets = self._attach_output_assets(
                generation_id, attempt_run_id, candidates, meta,
            )

        if primary_asset_id:
            self._attach_producer_asset(
                generation_id, attempt_run_id, str(primary_asset_id), meta,
            )
            all_assets = self._repo.get_generation_assets(generation_id)
            target = next(
                (
                    a.asset_id for a in all_assets
                    if a.asset_id == primary_asset_id
                    or a.metadata.get("producer_asset_id") == primary_asset_id
                ),
                None,
            )
            if target:
                self._repo.set_featured_asset(generation_id, target)
        elif len(new_assets) == 1:
            self._repo.set_featured_asset(generation_id, new_assets[0].asset_id)

        self._attach_derivative_assets(generation_id, attempt_run_id, meta)

        return {
            "generation_id": generation_id,
            "run_id": attempt_run_id,
            "status": stored,
        }

    def generation_has_output_association(self, run_id: Any) -> bool:
        """True when the mirrored generation for a production run has at
        least one REQUIRED output asset (preview/original) attached.

        Exception-isolated public query intended for use after the
        nonterminal ``running`` record so a modern output-producing run can
        verify its History output association before the terminal
        ``completed`` write.  A Thumbnail derivative alone never satisfies
        this gate — the required Preview/Original must exist first.
        Returns False for unknown generations.
        """
        try:
            generation_id = _gen_id(str(run_id))
            detail = self._repo.get_generation(generation_id)
            if detail is None:
                return False
            return any(a.type in _REQUIRED_ASSET_TYPES for a in detail.assets)
        except Exception:
            logger.exception(
                "history_v2_writer: generation_has_output_association failed "
                "for %r", run_id,
            )
            return False

    def attach_result_assets(
        self,
        generation_id: str,
        run_id: str,
        *,
        output_paths: Optional[list[str]] = None,
        primary_asset_id: str = "",
        meta: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Attach output assets to an already-created Generation.

        Modern Experiment cells create their durable Generation and Attempt in
        the acceptance transaction, so they cannot use ``record_run``'s
        single-run identity mapping.  This small public seam reuses the same
        path/producer adoption and thumbnail logic for that existing identity.

        E2C: optional Thumbnail derivative producer ids/descriptors in *meta*
        are adopted under the SAME logical output key as the required primary;
        derivative failure is logged truthfully and never fails the result.
        Success still requires a REQUIRED (preview/original) association.
        """
        try:
            metadata = dict(meta or {})
            paths = [str(path) for path in (output_paths or []) if str(path)]
            if paths:
                self._attach_output_assets(
                    str(generation_id), str(run_id), paths, metadata,
                )
            if primary_asset_id:
                self._attach_producer_asset(
                    str(generation_id), str(run_id), str(primary_asset_id), metadata,
                )
            self._attach_derivative_assets(str(generation_id), str(run_id), metadata)
            detail = self._repo.get_generation(str(generation_id))
            return bool(
                detail is not None
                and any(
                    asset.type in _REQUIRED_ASSET_TYPES
                    for asset in detail.assets
                )
            )
        except Exception:
            logger.exception(
                "history_v2_writer: attach_result_assets failed for generation=%r run=%r",
                generation_id,
                run_id,
            )
            return False

    # ── Shared status application (first-terminal-wins) ─────────────────

    def _apply_status(self, attempt_run_id, raw_status, meta, *, completed_at=None,
                      timings=None, error_override=None) -> Optional[str]:
        """Apply a production status with first-terminal-wins idempotency.

        Returns the stored V2 status, or None when the attempt is unknown.
        - ``queued`` → no-op (return current status).
        - ``running`` → ``update_attempt_status`` unless already terminal.
        - terminal → ``update_attempt_terminal`` unless a terminal status is
          already stored (replay of the same status is a silent no-op; a
          replayed different terminal is logged and the first wins).
        """
        attempt = self._repo.get_attempt(attempt_run_id)
        if attempt is None:
            return None
        v2_status = map_status(raw_status)
        merged_timing = dict(attempt.timing)
        if isinstance(timings, dict):
            merged_timing.update(timings)
        if raw_status == "completed_with_failures":
            merged_timing["production_terminal_status"] = "completed_with_failures"

        if v2_status == "queued":
            return attempt.status
        if v2_status == "running":
            if attempt.status in _TERMINAL_STATUS_VALUES:
                logger.debug(
                    "history_v2_writer: attempt %s already terminal (%s); "
                    "ignoring 'running' replay", attempt_run_id, attempt.status,
                )
                return attempt.status
            self._repo.update_attempt_status(
                attempt_run_id, "running", timing=merged_timing or None,
            )
            return "running"

        # Terminal status.
        if attempt.status in _TERMINAL_STATUS_VALUES:
            if attempt.status == v2_status:
                logger.debug(
                    "history_v2_writer: attempt %s already %s; idempotent no-op",
                    attempt_run_id, v2_status,
                )
            else:
                logger.warning(
                    "history_v2_writer: first-terminal-wins: attempt %s already %s; "
                    "keeping it (ignoring replayed %s)",
                    attempt_run_id, attempt.status, v2_status,
                )
            return attempt.status

        if error_override is not None:
            error = error_override or None
        else:
            error = _extract_error(meta)
        self._repo.update_attempt_terminal(
            attempt_run_id, status=v2_status, error=error,
            finished_at=completed_at or utc_now_iso(),
            timing=merged_timing or None,
        )
        return v2_status

    # ── Request snapshots ───────────────────────────────────────────────

    def _ensure_request_snapshot(self, generation_id, meta, workflow_hash) -> None:
        detail = self._repo.get_generation(generation_id)
        if detail is None or detail.generation.request_snapshot_id is not None:
            return
        workflow_json = meta.get("workflow_json")
        if not isinstance(workflow_json, dict) and not workflow_hash:
            return
        preset_snapshot: dict[str, Any] = {}
        preset_name = (
            meta.get("preset_name")
            or meta.get("studio_preset_label") or meta.get("preset_label")
        )
        if preset_name:
            preset_snapshot["preset_name"] = preset_name
        workflow_name = meta.get("workflow_name")
        if workflow_name:
            preset_snapshot["workflow_name"] = workflow_name
        request = meta.get("request_json")
        if not isinstance(request, dict):
            request = {}
        execution_plan = meta.get("execution_plan_json")
        if not isinstance(execution_plan, dict):
            execution_plan = {}
        deployment_identity = meta.get("deployment_identity_json")
        if not isinstance(deployment_identity, dict):
            deployment_identity = {}
        self._repo.create_request_snapshot(
            workflow_json=workflow_json if isinstance(workflow_json, dict) else {},
            generation_params=_extract_snapshot_params(meta),
            workflow_hash=workflow_hash or None,
            workflow_version_id=meta.get("workflow_version_id"),
            preset_snapshot=preset_snapshot or None,
            generation_id=generation_id,
            request=request,
            execution_plan=execution_plan,
            deployment_identity=deployment_identity,
        )

    # ── Asset resolution (single-run / studio outputs) ──────────────────

    def _attach_output_assets(self, generation_id, run_id, candidates,
                              meta) -> list[Asset]:
        """Resolve + attach output files, generate thumbnails, set featured.

        E2C: the attached primary asset type follows the frozen semantic
        output mode (``preview`` or ``original``) from the request/result
        metadata — never the file extension or codec.
        """
        existing = self._repo.get_generation_assets(generation_id)
        existing_names = {(a.run_id, a.filename) for a in existing}
        existing_thumb_keys = {
            (a.run_id, Path(a.filename).stem, a.logical_output_key)
            for a in existing if a.type == "thumbnail"
        }
        attached: list[Asset] = []
        studio_outputs: Optional[Path] = None
        primary_type = semantic_output_mode(meta)

        for index, candidate in enumerate(candidates):
            candidate_path = Path(candidate)
            if candidate_path.is_file():
                full = candidate_path
            else:
                if studio_outputs is None:
                    try:
                        from local_artifacts import get_studio_outputs_dir
                        studio_outputs = get_studio_outputs_dir()
                    except Exception as exc:
                        logger.debug(
                            "history_v2_writer: studio outputs dir unavailable: %s", exc,
                        )
                        continue
                full = studio_outputs / candidate_path.name
                if not full.is_file():
                    logger.debug(
                        "history_v2_writer: output candidate %r not found under %s; "
                        "skipping", candidate, studio_outputs,
                    )
                    continue
            basename = full.name
            logical_key = _candidate_logical_output_key(
                meta, candidate, index, len(candidates)
            )
            if (run_id, basename) in existing_names:
                logger.debug(
                    "history_v2_writer: asset %r already attached to %s; skipping",
                    basename, generation_id,
                )
                continue
            asset = self._repo.attach_asset(
                generation_id,
                run_id=run_id,
                asset_type=primary_type,
                source_path=str(full),
                copy=True,
                width=_asset_dimension(meta, "width"),
                height=_asset_dimension(meta, "height"),
                fmt=full.suffix.lstrip(".").lower() or None,
                filename=basename,
                logical_output_key=logical_key,
            )
            attached.append(asset)
            existing_names.add((run_id, basename))

        # Thumbnails for the newly attached originals (PIL lazily; skip on
        # failure, never raise).
        for asset in attached:
            stem = Path(asset.filename).stem
            thumb_key = (run_id, stem, asset.logical_output_key)
            if thumb_key in existing_thumb_keys:
                continue
            thumb = self._make_thumbnail_asset(generation_id, run_id, asset)
            if thumb is not None:
                existing_thumb_keys.add(thumb_key)

        if not attached:
            if meta.get("primary_asset_id"):
                logger.debug(
                    "history_v2_writer: generation %s has no attachable output "
                    "paths (primary_asset_id %r is a lease id, not a path); "
                    "producer adoption is handled by the caller",
                    generation_id, meta.get("primary_asset_id"),
                )
            return attached

        # Featured: first attached required-type asset (preview/original),
        # else first thumbnail (only when the generation does not already
        # have a featured asset).
        detail = self._repo.get_generation(generation_id)
        if detail is not None and detail.generation.featured_asset_id is None:
            required = [a for a in attached if a.type in _REQUIRED_ASSET_TYPES]
            thumbs = [a for a in attached if a.type == "thumbnail"]
            if required:
                self._repo.set_featured_asset(generation_id, required[0].asset_id)
            elif thumbs:
                self._repo.set_featured_asset(generation_id, thumbs[0].asset_id)
        return attached

    def _attach_producer_asset(self, generation_id, run_id, primary_asset_id,
                               meta) -> Optional[Asset]:
        """Adopt a producer (LeaseRegistry) primary asset as one managed
        original reference (never copied, re-encoded, or thumbnailed).

        Idempotent: an existing generation asset matching the producer id,
        managed path, or content hash yields no second asset.  Returns the
        attached (or matched) Asset, or None when the id does not resolve.
        A content-addressed producer id already adopted by another generation
        mints a fresh History-local id (producer identity kept in metadata).
        """
        if not isinstance(primary_asset_id, str) or not primary_asset_id:
            return None
        record = resolve_producer_asset(primary_asset_id)
        if not isinstance(record, dict) or not record:
            logger.debug(
                "history_v2_writer: producer asset %r not resolvable; no adoption",
                primary_asset_id,
            )
            return None
        producer_id = str(record.get("asset_id") or primary_asset_id)
        content_hash = record.get("content_hash") or None
        reference, source_path = _producer_reference(record)

        existing = self._repo.get_generation_assets(generation_id)
        for asset in existing:
            if (
                asset.asset_id == producer_id
                or asset.metadata.get("producer_asset_id") == producer_id
                or (content_hash and asset.sha256 and asset.sha256 == content_hash)
                or (reference is not None and asset.managed_path == reference)
                or (
                    source_path is not None
                    and asset.managed_path == str(Path(source_path).resolve())
                )
            ):
                logger.debug(
                    "history_v2_writer: producer asset %r already represented by "
                    "%s; skipping adoption", producer_id, asset.asset_id,
                )
                return asset

        width = _producer_dimension(record.get("width"))
        height = _producer_dimension(record.get("height"))
        if width is None:
            width = _asset_dimension(meta, "width")
        if height is None:
            height = _asset_dimension(meta, "height")

        descriptor = _descriptor_for_asset(meta, producer_id)
        logical_key = (
            logical_output_key_from_metadata(record)
            or logical_output_key_from_metadata(descriptor or {})
            or logical_output_key_from_metadata(meta)
        )
        metadata: dict[str, Any] = {"producer_asset_id": producer_id}
        for key in ("variant", "experiment_id", "cell_key", "attempt_id",
                    "node_id", "output_key", "output_index", "parent_asset_id"):
            value = record.get(key)
            if value not in (None, "", 0):
                metadata[key] = value
        for key in ("mime_type", "path", "byte_size", "content_hash"):
            value = record.get(key)
            if value not in (None, ""):
                metadata[key] = value
        if descriptor:
            for key in ("codec", "quality", "output_codec_ms", "comparison_side"):
                value = descriptor.get(key)
                if value not in (None, "", 0):
                    metadata.setdefault(key, value)
            metadata.setdefault(
                "parent_identity", str(descriptor.get("parent_identity") or "")
            )
            metadata.setdefault("derivative_kind", "thumbnail")
        if logical_key:
            metadata["logical_output_key"] = logical_key

        # E2C: the producer/result variant drives the History Asset type.
        # Preview producer results adopt as `preview`, Thumbnail derivatives
        # as `thumbnail`; everything else stays a backward-compatible
        # Original.  The type is NEVER inferred from extension/codec/MIME.
        asset_type = _asset_type_for_variant(record.get("variant"))
        if asset_type == "original":
            asset = self._repo.adopt_asset(
                generation_id,
                run_id=run_id,
                asset_id=producer_id,
                source_path=source_path,
                reference=reference,
                width=width,
                height=height,
                fmt=_fmt_from_mime(record.get("mime_type")),
                metadata=metadata,
                sha256=content_hash,
                logical_output_key=logical_key,
            )
        else:
            asset = self._adopt_typed_asset(
                generation_id,
                run_id=run_id,
                asset_id=producer_id,
                source_path=source_path,
                reference=reference,
                asset_type=asset_type,
                width=width,
                height=height,
                fmt=_fmt_from_mime(record.get("mime_type")),
                metadata=metadata,
                sha256=content_hash,
                logical_key=logical_key,
            )
        if asset is None:
            logger.debug(
                "history_v2_writer: producer asset %r adoption returned no row "
                "(concurrent duplicate insert rejected)", producer_id,
            )
            return None
        detail = self._repo.get_generation(generation_id)
        if detail is not None and detail.generation.featured_asset_id is None:
            self._repo.set_featured_asset(generation_id, asset.asset_id)
        return asset

    def _adopt_typed_asset(
        self,
        generation_id,
        run_id,
        *,
        asset_id,
        source_path,
        reference,
        asset_type,
        width,
        height,
        fmt,
        metadata,
        sha256,
        logical_key,
    ) -> Optional[Asset]:
        """Insert a managed-reference asset with an EXPLICIT History type.

        Narrow typed analogue of ``HistoryV2Repository.adopt_asset`` (which
        hardcodes ``original``): same assets table, same idempotency rules —
        an *asset_id* already present in this generation returns None; an id
        owned by ANOTHER generation mints a deterministic History-local id
        with the producer identity retained in ``metadata["producer_asset_id"]``
        so replayed terminals never duplicate.  Bytes are never copied or
        re-encoded: remote ``modal://`` references stay verbatim managed paths
        and local paths become resolved path references.  The digest comes
        from *sha256* (the producer content hash); it is computed from the
        local file only when omitted — bytes are never fabricated.
        """
        import sqlite3 as _sqlite3

        resolved_id = str(asset_id or "")
        metadata_dict = dict(metadata or {})
        if resolved_id:
            existing = self._repo.get_asset(resolved_id)
            if existing is not None:
                if existing.generation_id == generation_id:
                    return None
                minted = "ast_" + _digest(f"v2typed:{resolved_id}:{generation_id}")
                metadata_dict.setdefault("producer_asset_id", resolved_id)
                resolved_id = minted
        else:
            resolved_id = "ast_" + _digest(
                f"v2typed:{generation_id}:{run_id}:{logical_key or ''}:{sha256 or ''}"
            )

        if reference is not None:
            managed_path_str = str(reference)
            try:
                out_name = (
                    Path(str(reference).split("|", 2)[-1]).name or "asset"
                )
            except Exception:
                out_name = "asset"
            if not sha256:
                sha256 = None
        elif source_path is not None:
            src_path = Path(source_path)
            managed_path_str = str(src_path.resolve())
            out_name = src_path.name
            ext = src_path.suffix.lstrip(".").lower()
            if not sha256:
                try:
                    sha256 = hashlib.sha256(src_path.read_bytes()).hexdigest()
                except OSError:
                    sha256 = None
        else:
            raise ValueError("exactly one of source_path/reference is required")

        now = utc_now_iso()
        logical_value = normalize_logical_output_key(logical_key)
        stored_format = fmt or (
            Path(out_name).suffix.lstrip(".").lower() or None
        )
        try:
            with self._store.transaction() as conn:
                conn.execute(
                    """INSERT INTO assets (
                        asset_id, generation_id, run_id, type, managed_path, filename,
                        width, height, format, sha256, metadata_json,
                        logical_output_key, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (resolved_id, generation_id, run_id, asset_type,
                     managed_path_str, out_name, width, height,
                     stored_format,
                     sha256, _compact_json(metadata_dict), logical_value, now),
                )
        except _sqlite3.IntegrityError:
            return None
        return Asset(
            asset_id=resolved_id,
            generation_id=str(generation_id),
            type=asset_type,
            managed_path=managed_path_str,
            filename=out_name,
            created_at=now,
            run_id=run_id,
            width=width,
            height=height,
            format=stored_format,
            sha256=sha256,
            metadata=metadata_dict,
            logical_output_key=logical_value,
        )

    def _attach_derivative_assets(self, generation_id, run_id, meta) -> list[Asset]:
        """Adopt optional Thumbnail derivative producer assets for one result.

        Derivatives share the primary's canonical logical output key and are
        never the required workflow result: any single derivative failure is
        logged truthfully and never fails the required Preview/Original
        association (graceful derivative-failure policy).
        """
        attached: list[Asset] = []
        for derivative_id in _derivative_ids_from_meta(meta):
            try:
                asset = self._attach_producer_asset(
                    generation_id, run_id, derivative_id, meta,
                )
                if asset is not None:
                    attached.append(asset)
            except Exception as exc:
                logger.warning(
                    "history_v2_writer: thumbnail derivative %r adoption failed "
                    "(non-fatal): %s: %s", derivative_id, type(exc).__name__, exc,
                )
        return attached

    def _make_thumbnail_asset(self, generation_id, run_id, asset) -> Optional[Asset]:
        """WebP thumbnail for a managed original asset, or None on failure."""
        try:
            from PIL import Image
        except Exception as exc:
            logger.debug(
                "history_v2_writer: PIL unavailable; skipping thumbnail for %s (%s)",
                asset.filename, exc,
            )
            return None
        try:
            source = Path(asset.managed_path)
            if not source.is_file():
                return None
            img = Image.open(source)
            img.load()
            orig_width, orig_height = img.size
            img.thumbnail((_THUMBNAIL_MAX, _THUMBNAIL_MAX))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            buffer = io.BytesIO()
            img.save(buffer, "WEBP", quality=75)
            return self._repo.attach_asset(
                generation_id,
                run_id=run_id,
                asset_type="thumbnail",
                data=buffer.getvalue(),
                filename=f"{Path(asset.filename).stem}_thumb.webp",
                fmt="webp",
                width=min(orig_width, _THUMBNAIL_MAX) if orig_width else None,
                height=min(orig_height, _THUMBNAIL_MAX) if orig_height else None,
                logical_output_key=asset.logical_output_key,
            )
        except Exception as exc:
            logger.debug(
                "history_v2_writer: thumbnail generation failed for %s: %s",
                asset.filename, exc,
            )
            return None

    # ── Experiment cell flow ────────────────────────────────────────────

    def mirror_cell_terminal(self, experiment_id, *, cell_key, attempt_id,
                             status, checkpoint_id="", error=None, sequence=None,
                             axis_values=None, params=None, output_paths=None,
                             workflow_hash="", timings=None, meta=None) -> dict:
        try:
            return self._mirror_cell_terminal(
                experiment_id=experiment_id, cell_key=cell_key,
                attempt_id=attempt_id, status=status, checkpoint_id=checkpoint_id,
                error=error, sequence=sequence, axis_values=axis_values,
                params=params, output_paths=output_paths, workflow_hash=workflow_hash,
                timings=timings, meta=meta,
            )
        except Exception:
            logger.exception(
                "history_v2_writer: mirror_cell_terminal failed for "
                "experiment=%r cell=%r attempt=%r",
                experiment_id, cell_key, attempt_id,
            )
            return {}

    def _mirror_cell_terminal(self, experiment_id, cell_key, attempt_id, status,
                              checkpoint_id="", error=None, sequence=None,
                              axis_values=None, params=None, output_paths=None,
                              workflow_hash="", timings=None, meta=None) -> dict:
        meta = meta if isinstance(meta, dict) else {}
        experiment_id = str(experiment_id)
        cell_key = str(cell_key)
        attempt_id = str(attempt_id)
        gen_id = _cell_gen_id(experiment_id, cell_key)
        cell_run_id = _cell_run_id(experiment_id, cell_key, attempt_id)
        cell_id = _cell_id(experiment_id, cell_key)
        now = utc_now_iso()
        studio_meta = meta.get("studio_meta")
        if not isinstance(studio_meta, dict):
            studio_meta = {}

        # ── ensure experiment (lazy creation, production-shaped) ─────────
        if self._repo.get_experiment(experiment_id) is None:
            self._repo.create_experiment(
                experiment_id=experiment_id,
                name=studio_meta.get("name") or meta.get("name") or None,
                definition={
                    "production": True,
                    "workflow_hash": workflow_hash or None,
                    "axis_labels": axis_values if isinstance(axis_values, dict) else {},
                },
                cells=[],
            )

        # ── ensure cell (lazy creation) ──────────────────────────────────
        if self._repo.get_experiment_cell(cell_id) is None:
            if isinstance(axis_values, dict) and axis_values:
                labels = dict(axis_values)
            else:
                labels = _extract_cell_params(meta, params)
            self._repo.add_experiment_cell(
                experiment_id,
                cell_id=cell_id,
                position=sequence if isinstance(sequence, int) else None,
                axis_labels=labels,
            )

        # ── ensure cell generation ───────────────────────────────────────
        if self._repo.get_generation(gen_id) is None:
            cell_params = _extract_cell_params(meta, params)
            self._repo.create_generation(
                generation_id=gen_id,
                workflow_id=meta.get("workflow_id") or workflow_hash or None,
                workflow_version_id=meta.get("workflow_version_id"),
                preset_id=studio_meta.get("studio_preset_id")
                or studio_meta.get("preset_id"),
                prompt_text=str(cell_params.get("prompt") or ""),
                negative_prompt_text=str(cell_params.get("negative_prompt") or ""),
                experiment_id=experiment_id,
                created_at=now,
            )

        # ── link cell → generation (idempotent; powers cell thumbnails
        #    and assets in the History V2 experiment detail) ──────────────
        try:
            cell_row = self._repo.get_experiment_cell(cell_id)
            if cell_row is not None and cell_row.generation_id != gen_id:
                self._repo.update_experiment_cell(cell_id, generation_id=gen_id)
        except Exception:
            logger.debug(
                "history_v2_writer: cell generation link failed "
                "experiment=%r cell=%r", experiment_id, cell_id, exc_info=True,
            )

        # ── ensure cell attempt ──────────────────────────────────────────
        if self._repo.get_attempt(cell_run_id) is None:
            self._repo.add_attempt(
                gen_id, run_id=cell_run_id,
                mode=semantic_output_mode(meta),
                experiment_id=experiment_id, cell_id=cell_id, started_at=now,
            )

        # ── apply terminal status (same idempotency rules as single-run) ─
        merged_timing = dict(timings or {})
        if checkpoint_id:
            merged_timing["checkpoint_id"] = checkpoint_id
        stored = self._apply_status(
            cell_run_id, status, meta,
            timings=merged_timing or None,
            error_override=error,
        )
        if stored is None:
            stored = map_status(status)

        # ── request snapshot ─────────────────────────────────────────────
        self._ensure_request_snapshot(gen_id, meta, workflow_hash)

        # ── assets (full paths or basenames in the attempt output dir) ───
        cell_dir = self._cell_attempt_dir(experiment_id, cell_key, attempt_id)
        self._attach_cell_assets(gen_id, cell_run_id, cell_dir, output_paths, meta)

        return {
            "generation_id": gen_id,
            "cell_id": cell_id,
            "run_id": cell_run_id,
            "status": stored,
        }

    def _cell_attempt_dir(self, experiment_id, cell_key, attempt_id) -> Optional[Path]:
        """``<experiments_root>/<experiment_id>/outputs/<cell_key>/<attempt_id>``."""
        try:
            from local_artifacts import get_experiments_dir
            return (
                get_experiments_dir() / experiment_id
                / "outputs" / cell_key / attempt_id
            )
        except Exception as exc:
            logger.debug(
                "history_v2_writer: experiments dir unavailable: %s", exc,
            )
            return None

    def _attach_cell_assets(self, generation_id, run_id, cell_dir,
                            output_paths, meta=None) -> list[Asset]:
        """Attach experiment-cell output files (semantic primaries + thumbs)."""
        metadata = meta if isinstance(meta, dict) else {}
        primary_type = semantic_output_mode(metadata)
        existing = self._repo.get_generation_assets(generation_id)
        existing_names = {(a.run_id, a.filename) for a in existing}
        attached: list[Asset] = []

        candidates = [p for p in (output_paths or []) if isinstance(p, str) and p]
        if candidates:
            resolved: list[Path] = []
            for entry in candidates:
                entry_path = Path(entry)
                if entry_path.is_file():
                    resolved.append(entry_path)
                    continue
                if cell_dir is not None:
                    joined = cell_dir / entry_path.name
                    if joined.is_file():
                        resolved.append(joined)
                        continue
                logger.debug(
                    "history_v2_writer: cell output %r not found; skipping", entry,
                )
        else:
            resolved = []
            if cell_dir is not None and cell_dir.is_dir():
                resolved = [
                    p for p in sorted(cell_dir.iterdir())
                    if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
                ]

        for index, full in enumerate(resolved):
            basename = full.name
            if (run_id, basename) in existing_names:
                logger.debug(
                    "history_v2_writer: cell asset %r already attached to %s; "
                    "skipping", basename, generation_id,
                )
                continue
            lower = basename.lower()
            asset_type = (
                "thumbnail"
                if lower.endswith(("_thumb.webp", "_thumb.jpg"))
                else primary_type
            )
            logical_key = _candidate_logical_output_key(
                meta if isinstance(meta, dict) else {},
                str(full),
                index,
                len(resolved),
            )
            asset = self._repo.attach_asset(
                generation_id,
                run_id=run_id,
                asset_type=asset_type,
                source_path=str(full),
                copy=True,
                fmt=full.suffix.lstrip(".").lower() or None,
                filename=basename,
                logical_output_key=logical_key,
            )
            attached.append(asset)
            existing_names.add((run_id, basename))

        if not attached:
            return attached
        detail = self._repo.get_generation(generation_id)
        if detail is not None and detail.generation.featured_asset_id is None:
            required = [a for a in attached if a.type in _REQUIRED_ASSET_TYPES]
            thumbs = [a for a in attached if a.type == "thumbnail"]
            if required:
                self._repo.set_featured_asset(generation_id, required[0].asset_id)
            elif thumbs:
                self._repo.set_featured_asset(generation_id, thumbs[0].asset_id)
        return attached

    # ── Experiments ─────────────────────────────────────────────────────

    def ensure_experiment(self, experiment_id, *, name=None, definition=None,
                          cells=None) -> dict:
        try:
            return self._ensure_experiment(
                experiment_id, name=name, definition=definition, cells=cells,
            )
        except Exception:
            logger.exception(
                "history_v2_writer: ensure_experiment failed for %r", experiment_id,
            )
            return {}

    def _ensure_experiment(self, experiment_id, *, name=None, definition=None,
                           cells=None) -> dict:
        """Create an experiment with its full cell layout; idempotent."""
        experiment_id = str(experiment_id)
        existing = self._repo.get_experiment(experiment_id)
        if existing is not None:
            logger.debug(
                "history_v2_writer: experiment %r already exists; idempotent no-op",
                experiment_id,
            )
            return existing.to_dict()

        cell_specs: list[dict[str, Any]] = []
        for spec in cells or []:
            if not isinstance(spec, dict):
                continue
            cell_key = spec.get("cell_key")
            if not cell_key:
                continue
            axis_values = spec.get("axis_values")
            cell_specs.append({
                "cell_id": _cell_id(experiment_id, str(cell_key)),
                "position": spec.get("sequence"),
                "axis_labels": axis_values if isinstance(axis_values, dict) else {},
            })

        merged_definition = {"production": True}
        if isinstance(definition, dict):
            merged_definition.update(definition)

        self._repo.create_experiment(
            experiment_id=experiment_id,
            name=name,
            definition=merged_definition,
            cells=cell_specs,
            status="draft",
        )
        return {
            "experiment_id": experiment_id,
            "cell_count": len(cell_specs),
            "status": "draft",
        }

    def finalize_experiment(self, experiment_id, status) -> bool:
        try:
            if not isinstance(status, str) or not status:
                logger.error(
                    "history_v2_writer: finalize_experiment got invalid status %r",
                    status,
                )
                return False
            mapped = _EXPERIMENT_STATUS_MAP.get(status)
            if mapped is None:
                logger.error(
                    "history_v2_writer: invalid experiment status %r for %r; "
                    "expected one of %s",
                    status, experiment_id, sorted(_EXPERIMENT_STATUS_MAP),
                )
                return False
            if self._repo.get_experiment(experiment_id) is None:
                logger.debug(
                    "history_v2_writer: finalize_experiment for unknown experiment %r",
                    experiment_id,
                )
                return False
            # An explicit status sticks until the next cell update recomputes
            # the aggregate (that is the repository's documented behavior).
            return bool(self._repo.set_experiment_status(experiment_id, mapped))
        except Exception:
            logger.exception(
                "history_v2_writer: finalize_experiment failed for %r", experiment_id,
            )
            return False
