"""Authoritative SQLite-backed event journal + rebuildable snapshot for experiments.

Layout (created by ``ensure()``):
    <root>/.experiments/<exp_id>/store.db     # authoritative state

The store is one SQLite database per experiment. SQLite is used in
WAL journal mode and ``BEGIN IMMEDIATE`` for every write transaction
so:

  - two processes (or threads) cannot both append a sequence 1, 2, 3...
    with overlapping numbers — SQLite's serialised write lock gives us
    monotonic sequences across processes;
  - a single transaction either commits a complete event or none of it;
  - crash-recovery is automatic — the WAL checkpoint resumes from the
    last committed transaction.

The public API matches the previous journal-shaped module:
  - ``append_event(partial) -> dict`` assigns ``sequence``,
    ``event_id`` and ``timestamp`` and returns the persisted event;
  - ``read_events() -> Iterator[dict]`` yields every persisted event
    in sequence order (rebuilt from SQLite rows on demand);
  - ``write_snapshot(snapshot)`` and ``read_snapshot()`` round-trip
    the derived counters and last-sequence cache;
  - ``rebuild_snapshot()`` recomputes the snapshot from the events;
  - ``write_definition(defn)`` and ``read_definition()`` round-trip
    the immutable experiment definition;
  - ``ensure()`` creates the directory and opens the database.

The internal ``_atomic_write_json`` helper used by the snapshot and
definition uses ``tempfile.mkstemp`` so concurrent writers do not
collide on a shared ``.tmp`` path.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


EVENT_COUNTERS: dict[str, str] = {
    "cell.completed": "completed",
    "cell.failed": "failed",
    "cell.skipped": "skipped",
    "cell.interrupted": "interrupted",
}


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Thread-local SQLite connections. SQLite forbids sharing a connection
# across threads, so we keep one per thread per store instance.
_local = threading.local()


class ExperimentStore:
    def __init__(self, exp_dir: Path, root: Path) -> None:
        self._exp_dir = Path(exp_dir)
        self._root = Path(root)
        # An in-process lock; cross-process safety comes from SQLite's
        # serialised write transactions.
        self._lock = threading.Lock()
        # Per-thread connection cache. Keyed by thread id so we never
        # share a connection across threads.
        self._conns: dict[int, sqlite3.Connection] = {}
        # Schema initialised lazily on first connect.

    # ── Paths ──────────────────────────────────────────────────────────

    def _db_path(self) -> Path:
        return self._exp_dir / "store.db"

    def _snapshot_path(self) -> Path:
        return self._exp_dir / "snapshot.json"

    def _definition_path(self) -> Path:
        return self._exp_dir / "definition.json"

    # ── Connection management ───────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection in WAL mode."""
        tid = threading.get_ident()
        conn = self._conns.get(tid)
        if conn is None:
            self._exp_dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self._db_path()),
                isolation_level=None,  # autocommit; we use explicit transactions
                timeout=30.0,
                check_same_thread=True,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                "  sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  event_id TEXT NOT NULL UNIQUE,"
                "  type TEXT NOT NULL,"
                "  payload TEXT NOT NULL,"
                "  timestamp TEXT NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta ("
                "  key TEXT PRIMARY KEY,"
                "  value TEXT NOT NULL"
                ")"
            )
            self._conns[tid] = conn
        return conn

    def close(self) -> None:
        """Close all per-thread connections. Idempotent."""
        for conn in list(self._conns.values()):
            try:
                conn.close()
            except Exception:
                pass
        self._conns.clear()

    def close_thread(self) -> None:
        """Close the connection held by the calling thread, if any."""
        tid = threading.get_ident()
        conn = self._conns.pop(tid, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def __enter__(self) -> "ExperimentStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ── Lifecycle ─────────────────────────────────────────────────────

    def ensure(self) -> None:
        self._exp_dir.mkdir(parents=True, exist_ok=True)
        # Open the DB so the schema is created immediately.
        self._conn()

    # ── Definition ────────────────────────────────────────────────────

    def write_definition(self, defn: Mapping[str, Any]) -> None:
        self._atomic_write_json(self._definition_path(), dict(defn))

    def read_definition(self) -> dict | None:
        p = self._definition_path()
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── Event journal ─────────────────────────────────────────────────

    def append_event(self, partial: Mapping[str, Any]) -> dict:
        """Append an event inside a single SQLite transaction.

        ``partial`` must not include ``sequence``, ``event_id``, or
        ``timestamp`` -- these are filled in here. Sequence is assigned
        by SQLite's AUTOINCREMENT column which is strictly monotonic
        across processes when the table is in WAL mode.
        """
        with self._lock:
            conn = self._conn()
            event = dict(partial)
            event.setdefault("event_id", str(uuid.uuid4()))
            event.setdefault("timestamp", _utc_now_iso())
            # BEGIN IMMEDIATE acquires the write lock immediately so a
            # competing writer cannot interleave between SELECT MAX and
            # INSERT.
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    "INSERT INTO events (event_id, type, payload, timestamp) VALUES (?, ?, ?, ?)",
                    (
                        event["event_id"],
                        str(event.get("type", "")),
                        json.dumps(event.get("payload", {}), ensure_ascii=False, sort_keys=False),
                        event["timestamp"],
                    ),
                )
                seq = cur.lastrowid
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            event["sequence"] = int(seq)
            return event

    def read_events(self) -> Iterator[dict]:
        conn = self._conn()
        cur = conn.execute("SELECT sequence, event_id, type, payload, timestamp FROM events ORDER BY sequence ASC")
        for row in cur.fetchall():
            seq, event_id, etype, payload, ts = row
            try:
                payload_dict = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                payload_dict = {}
            yield {
                "sequence": int(seq),
                "event_id": str(event_id),
                "type": str(etype),
                "payload": payload_dict,
                "timestamp": str(ts),
            }

    def read_events_after(self, after_sequence: int) -> list[dict]:
        """Read all events with sequence strictly greater than ``after_sequence``.

        Used by the WS event bridge to fetch deltas.
        """
        conn = self._conn()
        cur = conn.execute(
            "SELECT sequence, event_id, type, payload, timestamp FROM events WHERE sequence > ? ORDER BY sequence ASC",
            (int(after_sequence),),
        )
        out: list[dict] = []
        for row in cur.fetchall():
            seq, event_id, etype, payload, ts = row
            try:
                payload_dict = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                payload_dict = {}
            out.append({
                "sequence": int(seq),
                "event_id": str(event_id),
                "type": str(etype),
                "payload": payload_dict,
                "timestamp": str(ts),
            })
        return out

    def last_sequence(self) -> int:
        conn = self._conn()
        cur = conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM events")
        return int(cur.fetchone()[0])

    # ── Snapshot ──────────────────────────────────────────────────────

    def write_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self._atomic_write_json(self._snapshot_path(), dict(snapshot))

    def read_snapshot(self) -> dict | None:
        p = self._snapshot_path()
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def rebuild_snapshot(self, total_cells: int = 0) -> dict:
        """Recompute snapshot from definition + events. Returns the new snap.

        ``total_cells`` is the total number of cells in the compilation (for
        progress computation). Defaults to 0 if not provided.
        """
        last_sequence = 0
        status = "draft"
        checkpoints: dict[str, dict] = {}
        # attempts maps cell_key -> latest attempt state.
        attempts: dict[str, dict] = {}
        # cell_visible tracks the current visible attempt status per cell.
        # When attempt.superseded arrives, the cell is removed from visible
        # counts; only the latest visible attempt per cell is counted.
        cell_visible: dict[str, str] = {}
        # raw_counter counts terminal events that have NO cell_key (e.g.
        # test payloads without cell_key).  Cells with cell_key are counted
        # through cell_visible instead.
        raw_counter: Counter[str] = Counter()

        started_total_cells = 0
        for ev in self.read_events():
            seq = ev.get("sequence", 0)
            if isinstance(seq, int) and seq > last_sequence:
                last_sequence = seq
            et = ev.get("type", "")
            payload = ev.get("payload", {}) or {}
            cell_key = payload.get("cell_key", "")
            checkpoint_id = payload.get("checkpoint_id", "")

            if et == "experiment.status":
                new_status = payload.get("status", "")
                if new_status:
                    status = new_status
            elif et in {"experiment.started", "experiment.resumed"}:
                status = "running"
                started_total_cells = int(payload.get("total_cells", 0))
            elif et == "experiment.paused":
                status = "paused"
            elif et == "experiment.stopped":
                status = "stopped"
            elif et == "experiment.completed":
                status = "completed"
            elif et == "experiment.failed_fatal":
                status = "failed_fatal"
            elif et == "experiment.error":
                # Treat scheduler/background errors as terminal failure
                if status not in ("completed", "stopped", "failed_fatal"):
                    status = "failed_fatal"

            if et == "checkpoint.claimed":
                ck = checkpoint_id
                if ck:
                    checkpoints[ck] = {
                        "status": "claimed",
                        "lease_generation": int(payload.get("lease_generation", 1)),
                        "worker_invocation_id": payload.get("worker_invocation_id", ""),
                    }
            elif et == "checkpoint.released":
                ck = checkpoint_id
                if ck and ck in checkpoints:
                    checkpoints[ck]["status"] = "released"
            elif et == "checkpoint.completed":
                ck = checkpoint_id
                if ck and ck in checkpoints:
                    checkpoints[ck]["status"] = "completed"
            elif et == "checkpoint.failed_fatal":
                ck = checkpoint_id
                if ck and ck in checkpoints:
                    checkpoints[ck]["status"] = "failed_fatal"

            # Track cell visible attempt status (only for events with cell_key)
            if cell_key:
                if et == "cell.completed":
                    cell_visible[cell_key] = "completed"
                elif et == "cell.failed":
                    cell_visible[cell_key] = "failed"
                elif et == "cell.interrupted":
                    cell_visible[cell_key] = "interrupted"
                elif et == "cell.skipped":
                    cell_visible[cell_key] = "skipped"
                elif et == "cell.attempt_created":
                    if cell_key not in cell_visible:
                        cell_visible[cell_key] = "running"
                elif et == "attempt.superseded":
                    # Remove superseded cell from visible tracking entirely.
                    # A new cell.attempt_created will re-add it.
                    cell_visible.pop(cell_key, None)
            else:
                # No cell_key: fall back to raw event counting for terminal events
                counter_key = EVENT_COUNTERS.get(et)
                if counter_key is not None:
                    raw_counter[counter_key] += 1

            # Track per-cell attempt details (same as before)
            if et == "cell.attempt_created":
                k = cell_key
                if k:
                    attempts[k] = {
                        "checkpoint_id": checkpoint_id,
                        "lease_generation": int(payload.get("lease_generation", 1)),
                        "attempt_id": payload.get("attempt_id", ""),
                        "status": "pending",
                    }
            elif et == "cell.completed":
                k = cell_key
                if k:
                    prev = attempts.get(k, {})
                    attempts[k] = {
                        "checkpoint_id": checkpoint_id or prev.get("checkpoint_id", ""),
                        "lease_generation": int(payload.get("lease_generation", prev.get("lease_generation", 1))),
                        "attempt_id": payload.get("attempt_id", ""),
                        "status": "completed",
                    }
            elif et == "cell.failed":
                k = cell_key
                if k:
                    prev = attempts.get(k, {})
                    attempts[k] = {
                        "checkpoint_id": checkpoint_id or prev.get("checkpoint_id", ""),
                        "lease_generation": int(payload.get("lease_generation", prev.get("lease_generation", 1))),
                        "attempt_id": payload.get("attempt_id", ""),
                        "status": "failed",
                        "error": payload.get("error", ""),
                    }
            elif et == "cell.interrupted":
                k = cell_key
                if k:
                    prev = attempts.get(k, {})
                    attempts[k] = {
                        "checkpoint_id": checkpoint_id or prev.get("checkpoint_id", ""),
                        "lease_generation": int(payload.get("lease_generation", prev.get("lease_generation", 1))),
                        "attempt_id": payload.get("attempt_id", ""),
                        "status": "interrupted",
                    }
            elif et == "cell.skipped":
                k = cell_key
                if k:
                    prev = attempts.get(k, {})
                    attempts[k] = {
                        "checkpoint_id": checkpoint_id or prev.get("checkpoint_id", ""),
                        "lease_generation": int(payload.get("lease_generation", prev.get("lease_generation", 1))),
                        "attempt_id": payload.get("attempt_id", ""),
                        "status": "skipped",
                    }
            elif et == "attempt.superseded":
                k = cell_key
                if k and k in attempts:
                    prev = attempts[k]
                    prev["superseded"] = True
                    attempts.pop(k, None)

        # Compute counters from visible cells only (excludes superseded)
        # plus raw events that have no cell_key.
        counters: Counter[str] = Counter()
        for ck, v in cell_visible.items():
            if v in {"completed", "failed", "interrupted", "skipped"}:
                counters[v] += 1
        # Add raw-event counts for events without cell_key
        for k, v in raw_counter.items():
            counters[k] += v

        # Infer total_cells from experiment.started/resumed event payload
        # when no explicit arg was provided (total_cells == 0).
        if total_cells == 0 and started_total_cells > 0:
            total_cells = started_total_cells

        snapshot = {
            "status": status,
            "counters": {
                "completed": int(counters.get("completed", 0)),
                "failed": int(counters.get("failed", 0)),
                "interrupted": int(counters.get("interrupted", 0)),
                "skipped": int(counters.get("skipped", 0)),
            },
            "cell_visible": cell_visible,
            "checkpoints": checkpoints,
            "attempts": attempts,
            "last_sequence": last_sequence,
            "rebuilt_at": _utc_now_iso(),
            "total_cells": total_cells,
        }
        self.write_snapshot(snapshot)
        return snapshot

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Use mkstemp to avoid the fixed .tmp filename that concurrent
        # writers in different processes were colliding on.
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
