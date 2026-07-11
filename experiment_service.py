"""Service layer that wires experiments, presets, warmup, run-history,
and the WS event bridge to the rest of comfyui-modal.

The service layer owns:

  - one ``ExperimentStore`` per experiment_id, lazily created from the
    node directory and a checkpoint id
  - one ``LeaseRegistry`` per checkpoint, persisted at
    ``<node>/.experiment_leases.db``
  - one ``ExperimentScheduler`` per experiment_id, registered while a
    run is in progress
  - one ``WarmupState`` persisted at ``<node>/.deploy_warmup_state.json``
  - one ``RunHistory`` directory at ``<node>/.run_history/<run_id>``

Routes in ``__init__.py`` call into this module. The module also
exposes a ``broadcast_event`` helper used by the WS event bridge and
the ``_event_bridge_loop`` background task that drains journal events
from a scheduler and forwards them to ``PromptServer.send_sync``.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional


# ── Paths ────────────────────────────────────────────────────────────────

NODE_DIR = os.path.dirname(os.path.abspath(__file__))


def experiments_root() -> Path:
    p = Path(NODE_DIR) / ".experiments"
    p.mkdir(parents=True, exist_ok=True)
    return p


def presets_root() -> Path:
    p = Path(NODE_DIR) / ".presets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def blobs_root() -> Path:
    p = Path(NODE_DIR) / ".preset_blobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Remote event handler (Phase 7) ────────────────────────────────────────

async def _default_remote_event_handler(exp_id: str, ev: dict) -> None:
    """Default terminal event handler for recovered schedulers.

    This is a minimal handler that persists terminal events.
    The full handler (with materialization and broadcasting) is registered
    by __init__.py when available.
    """
    try:
        from server import PromptServer
        server = PromptServer.instance
        if server:
            server.send_sync("experiment.event", {"experiment_id": exp_id, **dict(ev)})
    except Exception:
        pass

_remote_event_handler = _default_remote_event_handler


def set_remote_event_handler(handler):
    global _remote_event_handler
    _remote_event_handler = handler


def run_history_root() -> Path:
    p = Path(NODE_DIR) / ".run_history"
    p.mkdir(parents=True, exist_ok=True)
    return p


def leases_db_path() -> Path:
    return Path(NODE_DIR) / ".experiment_leases.db"


def warmup_state_path() -> Path:
    return Path(NODE_DIR) / ".deploy_warmup_state.json"


def experiment_dir(exp_id: str) -> Path:
    return experiments_root() / exp_id


# ── Worker progress buffer ──────────────────────────────────────────────


class WorkerProgressBuffer:
    """In-memory rolling buffer of ephemeral worker progress samples.

    The runner emits ``cell.started``, ``checkpoint.started``,
    ``cell.progress``, and ``sampler.step`` events through the
    EventBridge / ``experiment.worker.progress`` socket.io channel.
    These are not persisted to the journal because they are high-rate
    and ephemeral. The buffer caches the most recent sample per
    (checkpoint_id, cell_key) and an aggregate step-percent per
    checkpoint, so the REST ``/events`` endpoint can include a
    ``progress`` field for the polling UI.
    """

    MAX_CELL_SAMPLES = 64

    def __init__(self) -> None:
        self._cells: dict[str, dict] = {}  # key: "{ck}::{cell}" -> latest sample
        self._checkpoints: dict[str, dict] = {}  # ck_id -> aggregate
        self._lock = threading.Lock()

    @staticmethod
    def _key(checkpoint_id: str, cell_key: str) -> str:
        return f"{checkpoint_id or '_'}::{cell_key or '_'}"

    def update(self, *, checkpoint_id: str, cell_key: str, sample: dict) -> None:
        ck = checkpoint_id or ""
        ck_key = self._key(ck, cell_key)
        sample = dict(sample or {})
        sample["received_at"] = _utc_now_iso()
        with self._lock:
            self._cells[ck_key] = sample
            if len(self._cells) > self.MAX_CELL_SAMPLES * 4:
                # Bound memory: keep newest 75% of samples
                ordered = sorted(
                    self._cells.items(),
                    key=lambda kv: kv[1].get("received_at", ""),
                    reverse=True,
                )
                keep = max(1, int(len(ordered) * 0.75))
                self._cells = dict(ordered[:keep])
            # Aggregate per checkpoint
            if ck:
                agg = self._checkpoints.setdefault(
                    ck,
                    {
                        "checkpoint_id": ck,
                        "cells": {},
                        "last_event_type": None,
                        "last_received_at": None,
                    },
                )
                agg["cells"][cell_key or "_"] = {
                    "cell_key": cell_key,
                    "type": sample.get("type"),
                    "step": sample.get("step"),
                    "total_steps": sample.get("total_steps"),
                    "pct": sample.get("pct"),
                    "received_at": sample["received_at"],
                }
                agg["last_event_type"] = sample.get("type")
                agg["last_received_at"] = sample["received_at"]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cells": dict(self._cells),
                "checkpoints": {
                    ck: {
                        "checkpoint_id": agg["checkpoint_id"],
                        "last_event_type": agg["last_event_type"],
                        "last_received_at": agg["last_received_at"],
                        "cells": dict(agg["cells"]),
                    }
                    for ck, agg in self._checkpoints.items()
                },
            }

    def clear_checkpoint(self, checkpoint_id: str) -> None:
        with self._lock:
            self._checkpoints.pop(checkpoint_id, None)
            self._cells = {
                k: v for k, v in self._cells.items() if not k.startswith(f"{checkpoint_id}::")
            }


# ── Service registry ────────────────────────────────────────────────────


class ServiceRegistry:
    """Process-wide registry of stores, leases, schedulers, and event
    bridges. A single instance is created at import time and used by
    every route."""

    def __init__(self) -> None:
        self._schedulers: dict[str, "ExperimentScheduler"] = {}
        self._store_singletons: dict[str, "ExperimentStore"] = {}
        self._lease_singletons: dict[str, "LeaseRegistry"] = {}
        self._bridges: dict[str, "_EventBridge"] = {}
        self._progress_buffers: dict[str, "WorkerProgressBuffer"] = {}
        self._lock = asyncio.Lock()

    # ── Stores / leases ──

    def store(self, exp_id: str) -> "ExperimentStore":
        from experiment_store import ExperimentStore
        if exp_id not in self._store_singletons:
            d = experiment_dir(exp_id)
            d.mkdir(parents=True, exist_ok=True)
            self._store_singletons[exp_id] = ExperimentStore(d, root=Path(NODE_DIR))
            self._store_singletons[exp_id].ensure()
        return self._store_singletons[exp_id]

    def leases(self) -> "LeaseRegistry":
        from experiment_lease import LeaseRegistry
        if "_default" not in self._lease_singletons:
            self._lease_singletons["_default"] = LeaseRegistry(leases_db_path())
        return self._lease_singletons["_default"]

    # ── Worker progress buffer ──

    def worker_progress(self, exp_id: str) -> "WorkerProgressBuffer":
        if exp_id not in self._progress_buffers:
            self._progress_buffers[exp_id] = WorkerProgressBuffer()
        return self._progress_buffers[exp_id]

    # ── Scheduler registry ──

    async def get_or_create_scheduler(
        self,
        exp_id: str,
        *,
        compilation: dict,
        invoker=None,
        max_containers: int = 1,
    ) -> "ExperimentScheduler":
        from experiment_scheduler import ExperimentScheduler
        async with self._lock:
            existing = self._schedulers.get(exp_id)
            if existing is not None:
                return existing
            store = self.store(exp_id)
            leases = self.leases()
            sched = ExperimentScheduler(
                store=store, leases=leases, invoker=invoker,
                compilation=compilation, max_containers=max_containers,
                event_callback=None,  # Phase 8: EventBridge is the sole broadcaster
            )
            self._schedulers[exp_id] = sched
            return sched

    def get_scheduler(self, exp_id: str) -> Optional["ExperimentScheduler"]:
        return self._schedulers.get(exp_id)

    async def recover_scheduler(self, exp_id) -> Optional["ExperimentScheduler"]:
        """Try to reconstruct a scheduler from persisted state."""
        # Check if we already have one
        existing = self._schedulers.get(exp_id)
        if existing is not None:
            return existing
        # Check persisted state
        sched_file = experiment_dir(exp_id) / ".scheduler_state.json"
        if not sched_file.exists():
            return None
        try:
            import json
            data = json.loads(sched_file.read_text(encoding="utf-8"))
            compilation = data.get("compilation", {})
            max_containers = data.get("max_containers", 1)
            if not compilation:
                return None
            store = self.store(exp_id)
            leases = self.leases()
            from experiment_scheduler import ExperimentScheduler
            from experiment_runner import CheckpointStreamInvoker
            # Try to create a real invoker with a safe stream event sink.
            # The sink must be awaitable (CheckpointStreamInvoker._drive awaits
            # it) but we must not blindly double-wrap an already-async handler
            # in create_task.
            invoker = None
            try:
                from modal_client import run_checkpoint_stream

                async def _recovery_sink(ev):
                    try:
                        result = _remote_event_handler(exp_id, ev)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass

                invoker = CheckpointStreamInvoker(
                    run_checkpoint_stream,
                    stream_event_sink=_recovery_sink,
                )
            except Exception:
                pass  # No modal? Fine, we'll skip checkpoint streams
            sched = ExperimentScheduler(
                store=store, leases=leases,
                invoker=invoker,
                compilation=compilation,
                max_containers=max_containers,
                # Fix: EventBridge is the durable broadcaster; do not give
                # recovered schedulers a direct event_callback duplicate.
                event_callback=None,
            )
            # Restore skipped checkpoints
            skipped = data.get("skipped_checkpoints", [])
            sched._skipped_checkpoints = set(skipped)
            # ── Fix: recovery must invalidate dead claimed leases so
            #     (a) they become reclaimable and (b) stale events are
            #     rejected by the bumped generation / "cancelling" status.
            #     The "experiment.recovered" marker event prevents
            #     duplicate interruptions on repeated recovery.
            already_recovered = any(
                ev["type"] == "experiment.recovered"
                for ev in store.read_events()
            )
            if not already_recovered:
                for ck_id, lease_info in leases.snapshot(exp_id).get("leases", {}).items():
                    if lease_info.get("status") == "claimed":
                        try:
                            leases.invalidate(exp_id, ck_id)
                        except Exception:
                            pass
                        for cell in compilation.get("cells", []):
                            if cell.get("checkpoint_id") == ck_id:
                                ck = cell.get("cell_key", "")
                                if ck:
                                    store.append_event({
                                        "type": "cell.interrupted",
                                        "payload": {
                                            "cell_key": ck,
                                            "checkpoint_id": ck_id,
                                            "worker_invocation_id": lease_info.get("worker_invocation_id", ""),
                                            "lease_generation": lease_info.get("lease_generation", 0),
                                            "reason": "recovery",
                                        },
                                    })
                store.append_event({
                    "type": "experiment.recovered",
                    "payload": {"experiment_id": exp_id},
                })
            # Convert any running-like state to paused (resumable) on recovery.
            from experiment_scheduler import (
                STATUS_RUNNING, STATUS_PAUSE_REQUESTED,
                STATUS_STOP_NOW_REQUESTED, STATUS_STOP_AFTER_CURRENT_REQUESTED,
                STATUS_PAUSED, STATUS_STOPPED,
            )
            restored_status = data.get("status", "draft")
            if restored_status in (
                STATUS_RUNNING,
                STATUS_PAUSE_REQUESTED,
                STATUS_STOP_NOW_REQUESTED,
                STATUS_STOP_AFTER_CURRENT_REQUESTED,
            ):
                restored_status = STATUS_PAUSED
            sched._status = restored_status
            # Persist the corrected status so a second recovery sees it.
            self.save_scheduler_state(
                exp_id,
                compilation=compilation,
                max_containers=data.get("max_containers", 1),
                status=restored_status,
                skipped_checkpoints=data.get("skipped_checkpoints", []),
            )
            self._schedulers[exp_id] = sched
            self.start_bridge(exp_id)
            return sched
        except Exception as exc:
            print(f"[comfyui-modal] scheduler recovery failed for {exp_id}: {exc}")
            return None

    def save_scheduler_state(self, exp_id, compilation=None, max_containers=1, status="draft", skipped_checkpoints=None):
        """Persist scheduler compilation and status so it can be recovered after a restart."""
        import json
        sched_file = experiment_dir(exp_id) / ".scheduler_state.json"
        # ── Fix: ensure parent dir exists before writing ──
        sched_file.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if sched_file.exists():
            try:
                existing = json.loads(sched_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        # ── Fix: use ``is not None`` instead of ``or`` so that falsy
        #     but valid values (empty dict, 0, empty string, empty list)
        #     are not silently replaced with the existing value.
        data = {
            "experiment_id": exp_id,
            "compilation": compilation if compilation is not None else existing.get("compilation", {}),
            "max_containers": max_containers if max_containers is not None else existing.get("max_containers", 1),
            "status": status if status is not None else existing.get("status", "draft"),
            "skipped_checkpoints": skipped_checkpoints if skipped_checkpoints is not None else existing.get("skipped_checkpoints", []),
        }
        sched_file.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def drop_scheduler(self, exp_id: str) -> None:
        self._schedulers.pop(exp_id, None)
        bridge = self._bridges.pop(exp_id, None)
        if bridge is not None:
            bridge.cancel()
        buf = self._progress_buffers.pop(exp_id, None)
        if buf is not None:
            for ck_id in list(buf._checkpoints.keys()):
                buf.clear_checkpoint(ck_id)

    # ── Event bridge ──

    def _on_journal_event(self, exp_id: str, ev: dict) -> None:
        """Forward a single journal event to PromptServer. The scheduler
        calls this from its event_callback; we send it to the WS bus."""
        try:
            from server import PromptServer
            server = PromptServer.instance
            if server is None:
                return
            sid = ev.get("sid", "")  # may be empty
            payload = dict(ev)
            payload["experiment_id"] = exp_id
            server.send_sync("experiment.event", payload, sid)
        except Exception:
            pass

    def start_bridge(self, exp_id: str) -> None:
        """Start a background task that streams new journal events
        to PromptServer. Idempotent."""
        if exp_id in self._bridges:
            return
        self._bridges[exp_id] = _EventBridge(self, exp_id)
        self._bridges[exp_id].start()

    # ── Run history ──

    def history(self) -> "RunHistoryService":
        return RunHistoryService(run_history_root())


# ── Event bridge background task ─────────────────────────────────────────


class _EventBridge:
    def __init__(self, registry: ServiceRegistry, exp_id: str) -> None:
        self._registry = registry
        self._exp_id = exp_id
        self._task: Optional[asyncio.Task] = None
        self._stop = False

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    def cancel(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        last_seq = 0
        while not self._stop:
            try:
                store = self._registry.store(self._exp_id)
                rows = store.read_events_after(last_seq)
                for ev in rows:
                    try:
                        self._registry._on_journal_event(self._exp_id, ev)
                        if isinstance(ev.get("sequence"), int):
                            last_seq = ev["sequence"]
                    except Exception:
                        # ── Fix: do NOT advance last_seq if send fails.
                        #     The event will be retried on the next poll cycle.
                        pass
            except Exception:
                pass
            await asyncio.sleep(0.2)


# ── Atomic write helpers ────────────────────────────────────────────────


def _atomic_write_json(path: Path, data: Any) -> None:
    """Atomically write JSON to *path* via temp file + os.replace."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    """Atomically write text to *path* via temp file + os.replace."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ── Run-history service ─────────────────────────────────────────────────


# ── Default annotations ──────────────────────────────────────────────

_DEFAULT_ANNOTATIONS: dict = {
    "schema_version": 1,
    "favorite": False,
    "note": "",
    "updated_at": None,
}

_ANNOTATION_NOTE_MAX_LENGTH: int = 2000
_ANNOTATION_ALLOWED_FIELDS: frozenset = frozenset({"favorite", "note"})


def _validate_annotation_payload(payload: dict) -> list[str]:
    """Validate an annotation PATCH payload.

    Returns a list of error messages (empty = valid).
    Only ``favorite`` (bool) and ``note`` (str, max length) are allowed.
    """
    errors: list[str] = []

    if not isinstance(payload, dict):
        return ["payload must be a dict"]

    # Check for unknown fields
    for key in payload:
        if key not in _ANNOTATION_ALLOWED_FIELDS:
            errors.append(f"Unknown field: {key!r}")

    # Validate favorite if present
    if "favorite" in payload:
        fav = payload["favorite"]
        if not isinstance(fav, bool):
            errors.append("favorite must be a boolean")

    # Validate note if present
    if "note" in payload:
        note = payload["note"]
        if not isinstance(note, str):
            errors.append("note must be a string")
        elif len(note) > _ANNOTATION_NOTE_MAX_LENGTH:
            errors.append(
                f"note must not exceed {_ANNOTATION_NOTE_MAX_LENGTH} characters"
            )

    return errors


def _normalize_annotations(meta_obj: dict) -> dict:
    """Ensure *meta_obj* has an ``annotations`` key with normalized defaults.

    Annotations live at the top level of meta.json (not inside ``extra``)
    so the PATCH endpoint can modify them without racing with finalization
    writes that update ``extra``.

    Migration: if annotations exist in ``extra`` but not at top level,
    promote them to top level and remove from ``extra``.
    Returns *meta_obj* mutated in place for convenience.
    """
    # Migrate from extra.annotations to top-level annotations
    extra = meta_obj.get("extra")
    if isinstance(extra, dict) and "annotations" in extra and "annotations" not in meta_obj:
        meta_obj["annotations"] = extra.pop("annotations")

    if "annotations" not in meta_obj:
        meta_obj["annotations"] = dict(_DEFAULT_ANNOTATIONS)
    else:
        # Ensure all keys exist even if partial
        ann = meta_obj["annotations"]
        if not isinstance(ann, dict):
            meta_obj["annotations"] = dict(_DEFAULT_ANNOTATIONS)
        else:
            merged = dict(_DEFAULT_ANNOTATIONS)
            merged.update(ann)
            meta_obj["annotations"] = merged
    return meta_obj


# ── Per-run lock manager ─────────────────────────────────────────────


class _PerRunLock:
    """Lightweight per-run-id lock manager for concurrent update safety."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    def acquire(self, run_id: str) -> threading.Lock:
        with self._lock:
            if run_id not in self._locks:
                self._locks[run_id] = threading.Lock()
            return self._locks[run_id]


# ── Run ID validation ────────────────────────────────────────────────

_RUN_ID_PATTERN = re.compile(r"^r_[a-zA-Z0-9_\-]+$")


def _validate_run_id(run_id: str) -> bool:
    """Return True if *run_id* is safe for filesystem use.

    Rejects empty strings, path-traversal chars (``..``, ``/``, ``\\``),
    null bytes, and any character outside ``[a-zA-Z0-9_-]`` after the
    ``r_`` prefix.
    """
    if not run_id or not isinstance(run_id, str):
        return False
    if "\x00" in run_id:
        return False
    if ".." in run_id:
        return False
    if "/" in run_id or "\\" in run_id:
        return False
    return bool(_RUN_ID_PATTERN.match(run_id))


# ── Run-history service ─────────────────────────────────────────────────


class RunHistoryService:
    """Persists per-run records to ``.run_history/<run_id>/meta.json``.

    Thread-safe per-run locking: each ``run_id`` has its own lock so
    concurrent updates to different records do not block each other.
    Timing data is stored in a separate ``timing.json`` file and merged
    on write so that finalization and annotation writes can coexist.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._run_locks = _PerRunLock()

    def _lock_for(self, run_id: str) -> threading.Lock:
        return self._run_locks.acquire(run_id)

    def record_run(
        self,
        *,
        kind: str,
        prompt_id: str,
        workflow_hash: str = "",
        status: str = "running",
        meta: Optional[dict] = None,
        log_text: str = "",
        timings: Optional[dict] = None,
        output_path: str = "",
        started_at: Optional[str] = None,
    ) -> dict:
        run_id = f"r_{uuid.uuid4().hex[:12]}"
        run_dir = self._root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        meta_path = run_dir / "meta.json"
        log_path = run_dir / "log.txt"
        timing_path = run_dir / "timing.json"
        extra = dict(meta or {})
        # Extract annotations from meta and place at top level
        caller_annotations = extra.pop("annotations", None) if meta else None
        if isinstance(caller_annotations, dict):
            merged_ann = dict(_DEFAULT_ANNOTATIONS)
            merged_ann.update(caller_annotations)
            top_annotations = merged_ann
        else:
            top_annotations = dict(_DEFAULT_ANNOTATIONS)
        meta_obj = {
            "run_id": run_id,
            "kind": kind,
            "prompt_id": prompt_id,
            "workflow_hash": workflow_hash,
            "status": status,
            "started_at": started_at if started_at is not None else _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "output_path": output_path,
            "extra": extra,
            "annotations": top_annotations,
        }
        _atomic_write_json(meta_path, meta_obj)
        if log_text:
            _atomic_write_text(log_path, log_text)
        if timings:
            _atomic_write_json(timing_path, timings)
        return meta_obj

    def update_run(
        self,
        run_id: str,
        *,
        status: Optional[str] = None,
        meta: Optional[dict] = None,
        output_path: Optional[str] = None,
        timings: Optional[dict] = None,
        completed_at: Optional[str] = None,
        workflow_hash: Optional[str] = None,
        primary_asset_id: Optional[str] = None,
    ) -> dict:
        # Validate run_id before any filesystem access
        if not _validate_run_id(run_id):
            return {"status": "error", "message": "invalid run_id"}
        # Copy caller-supplied meta dict to avoid mutation
        meta_copy: Optional[dict] = None
        if meta is not None:
            meta_copy = dict(meta)
        meta = meta_copy

        run_dir = self._root / run_id
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            return {"status": "error", "message": "unknown run_id"}

        # Acquire per-run lock to prevent concurrent read-modify-write races
        lock = self._lock_for(run_id)
        with lock:
            # ── Read and update meta.json ──────────────────────────────
            try:
                meta_obj = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta_obj = {}
            if status is not None:
                meta_obj["status"] = status
            if output_path is not None:
                meta_obj["output_path"] = output_path
            if workflow_hash is not None:
                meta_obj["workflow_hash"] = workflow_hash
            if completed_at is not None:
                meta_obj["completed_at"] = completed_at
            if primary_asset_id is not None:
                meta_obj["primary_asset_id"] = primary_asset_id
            if meta is not None:
                # Extract annotations from meta and store at top-level
                caller_annotations: Optional[dict] = None
                if "annotations" in meta:
                    caller_annotations = meta.pop("annotations")
                    if not isinstance(caller_annotations, dict):
                        caller_annotations = None
                # Merge remaining meta fields into extra
                if meta:
                    meta_obj.setdefault("extra", {}).update(meta)
                # Handle annotations at top level
                if caller_annotations is not None:
                    merged = dict(_DEFAULT_ANNOTATIONS)
                    merged.update(caller_annotations)
                    meta_obj["annotations"] = merged

            # Ensure top-level annotations always exist after any update
            meta_obj.setdefault("annotations", dict(_DEFAULT_ANNOTATIONS))
            meta_obj["updated_at"] = _utc_now_iso()
            _atomic_write_json(meta_path, meta_obj)

            # ── Merge timings into timing.json (do not replace) ────────
            if timings is not None:
                timing_path = run_dir / "timing.json"
                existing_timing: dict = {}
                if timing_path.exists():
                    try:
                        existing_timing = json.loads(
                            timing_path.read_text(encoding="utf-8")
                        )
                    except json.JSONDecodeError:
                        existing_timing = {}
                existing_timing.update(timings)
                _atomic_write_json(timing_path, existing_timing)

        return meta_obj

    def list_runs(
        self,
        *,
        kind: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        sort: str = "newest",
        status_filter: Optional[str] = None,
        favorite_only: bool = False,
        search: Optional[str] = None,
        feature: Optional[str] = None,
        preset: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        has_image: Optional[bool] = None,
    ) -> dict:
        """List run history records with pagination, filtering, and sorting.

        Parameters
        ----------
        kind : str, optional
            Filter by record kind (e.g. ``"studio_run"``).
        limit : int
            Maximum records to return (default 200).
        offset : int
            Number of records to skip (for pagination).
        sort : str
            Sort order: ``"newest"`` (default), ``"oldest"``, ``"fastest"``,
            ``"slowest"``.
        status_filter : str, optional
            Filter by record status (e.g. ``"completed"``, ``"error"``).
        favorite_only : bool
            If True, only return records with ``annotations.favorite == true``.
        search : str, optional
            Case-insensitive search across prompt_id, note (annotations),
            preset_label, run_id, experiment_id.
        feature : str, optional
            Filter by ``studio_feature_id`` in extra.
        preset : str, optional
            Filter by ``studio_preset_id`` in extra.
        date_from : str, optional
            ISO datetime string; only return runs with ``started_at >= date_from``.
        date_to : str, optional
            ISO datetime string; only return runs with ``started_at <= date_to``.
        has_image : bool, optional
            If True, only return runs with a non-empty ``output_path``.

        Returns
        -------
        dict
            ``{"runs": [...], "total": int, "limit": int, "offset": int}``
        """
        out: list[dict] = []
        for run_dir in self._root.iterdir():
            if not run_dir.is_dir():
                continue
            meta_path = run_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta_obj = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if kind is not None and meta_obj.get("kind") != kind:
                continue
            if status_filter is not None and meta_obj.get("status") != status_filter:
                continue
            if favorite_only:
                ann = meta_obj.get("annotations", {}) or {}
                if not ann.get("favorite"):
                    continue
            # ── Search filter ───────────────────────────────────────
            if search:
                _search_lower = search.lower()
                extra = meta_obj.get("extra", {}) or {}
                ann = meta_obj.get("annotations", {}) or {}
                # Fields to search
                _search_fields = [
                    meta_obj.get("prompt_id", ""),
                    meta_obj.get("run_id", ""),
                    extra.get("experiment_id", ""),
                    extra.get("preset_label", ""),
                    ann.get("note", ""),
                ]
                if not any(_search_lower in (f or "").lower() for f in _search_fields):
                    continue
            # ── Feature filter ──────────────────────────────────────
            if feature is not None:
                extra = meta_obj.get("extra", {}) or {}
                if extra.get("studio_feature_id") != feature:
                    continue
            # ── Preset filter ───────────────────────────────────────
            if preset is not None:
                extra = meta_obj.get("extra", {}) or {}
                if extra.get("studio_preset_id") != preset:
                    continue
            # ── Date range filter ───────────────────────────────────
            if date_from is not None:
                sa = meta_obj.get("started_at", "") or ""
                if sa < date_from:
                    continue
            if date_to is not None:
                sa = meta_obj.get("started_at", "") or ""
                if sa > date_to:
                    continue
            # ── Has image filter ────────────────────────────────────
            if has_image is True:
                if not meta_obj.get("output_path"):
                    continue
            elif has_image is False:
                if meta_obj.get("output_path"):
                    continue
            meta_obj["_path"] = str(run_dir)
            # Normalize annotations for old records
            _normalize_annotations(meta_obj)
            out.append(meta_obj)

        total = len(out)

        # Sort
        def _sort_key(r: dict) -> tuple:
            ca = r.get("completed_at", "") or ""
            sa = r.get("started_at", "") or ""
            mtime = Path(r.get("_path", "")).stat().st_mtime if r.get("_path") else 0
            return (ca or "", sa or "", mtime)

        if sort == "newest":
            out.sort(key=_sort_key, reverse=True)
        elif sort == "oldest":
            out.sort(key=_sort_key)
        elif sort == "fastest":
            # Sort by total_ms from timing.json ascending
            def _fast_sort_key(r):
                run_id = r.get("run_id", "")
                timing = self.get_timing(run_id)
                return timing.get("scheduler_execution_ms", timing.get("total_ms", float("inf"))) or 0
            out.sort(key=_fast_sort_key)
        elif sort == "slowest":
            def _slow_sort_key(r):
                run_id = r.get("run_id", "")
                timing = self.get_timing(run_id)
                return -(timing.get("scheduler_execution_ms", timing.get("total_ms", 0)) or 0)
            out.sort(key=_slow_sort_key)
        else:
            # Default: newest
            out.sort(key=_sort_key, reverse=True)

        # Apply pagination
        paginated = out[offset:offset + limit] if offset > 0 else out[:limit]

        return {
            "runs": paginated,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_run(self, run_id: str) -> Optional[dict]:
        if not _validate_run_id(run_id):
            return None
        run_dir = self._root / run_id
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            return None
        try:
            meta_obj = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        meta_obj["_path"] = str(run_dir)
        # Normalize annotations for old records that lack them
        _normalize_annotations(meta_obj)
        return meta_obj

    def get_log(self, run_id: str) -> str:
        if not _validate_run_id(run_id):
            return ""
        run_dir = self._root / run_id
        log_path = run_dir / "log.txt"
        if not log_path.exists():
            return ""
        return log_path.read_text(encoding="utf-8")

    def get_timing(self, run_id: str) -> dict:
        if not _validate_run_id(run_id):
            return {}
        run_dir = self._root / run_id
        timing_path = run_dir / "timing.json"
        if not timing_path.exists():
            return {}
        try:
            return json.loads(timing_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Process-wide singleton ──────────────────────────────────────────────

REGISTRY = ServiceRegistry()
