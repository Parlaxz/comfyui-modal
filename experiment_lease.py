"""Checkpoint lease state machine for the experiment runner.

A lease is per-checkpoint, per-worker-invocation, and carries a monotonic
``lease_generation`` integer. The generation is incremented on every
release+reclaim cycle. Stream events carry a ``lease_generation`` and
``attempt_id``; events whose generation is older than the current lease
generation are rejected as stale. This is the §11 mechanism from the
parent plan.

Persistence is SQLite. Each ``LeaseRegistry`` opens a per-thread
connection to a single ``leases.db`` file. SQLite's serialised write
lock guarantees cross-process safety: two processes cannot both
successfully claim the same checkpoint.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class LeaseError(RuntimeError):
    pass


class LeaseActiveError(LeaseError):
    """Raised when a checkpoint already has an active lease."""


class LeaseOwnershipError(LeaseError):
    """Raised when a release/accept is attempted by a non-owning worker."""


class CancellationBoundary(LeaseError):
    """Raised when an event is rejected because the checkpoint lease has been
    invalidated (status is 'cancelling' rather than 'claimed')."""


class StaleEventError(LeaseError):
    """Raised when an event's lease_generation is older than the current one."""


class UnknownCheckpointError(LeaseError):
    """Raised when an event references a checkpoint that has no active lease."""


def _migrate_asset_schema(conn: sqlite3.Connection) -> None:
    """Migrate the assets table to the extended B3 schema if needed.
    
    Adds columns: parent_asset_id, node_id, output_key, output_index,
    comparison_side, width, height.  Existing rows get default values.
    """
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
    new_cols = {
        "parent_asset_id": "TEXT DEFAULT ''",
        "node_id": "TEXT DEFAULT ''",
        "output_key": "TEXT DEFAULT ''",
        "output_index": "INTEGER DEFAULT 0",
        "comparison_side": "TEXT DEFAULT ''",
        "width": "INTEGER DEFAULT 0",
        "height": "INTEGER DEFAULT 0",
    }
    for col_name, col_def in new_cols.items():
        if col_name not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE assets ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass  # column already exists — race with concurrent migration


class LeaseRegistry:
    """SQLite-backed, cross-process-safe lease registry.

    The schema is one table:
        leases(
            experiment_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            worker_invocation_id TEXT NOT NULL,
            lease_generation INTEGER NOT NULL,
            status TEXT NOT NULL,
            accepted_attempts TEXT NOT NULL,  -- JSON list
            PRIMARY KEY (experiment_id, checkpoint_id)
        )
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conns: dict[int, sqlite3.Connection] = {}

    def _conn(self) -> sqlite3.Connection:
        tid = threading.get_ident()
        conn = self._conns.get(tid)
        if conn is None:
            conn = sqlite3.connect(
                str(self._path),
                isolation_level=None,
                timeout=30.0,
                check_same_thread=True,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS leases ("
                "  experiment_id TEXT NOT NULL,"
                "  checkpoint_id TEXT NOT NULL,"
                "  worker_invocation_id TEXT NOT NULL,"
                "  lease_generation INTEGER NOT NULL,"
                "  status TEXT NOT NULL,"
                "  accepted_attempts TEXT NOT NULL DEFAULT '[]',"
                "  PRIMARY KEY (experiment_id, checkpoint_id)"
                ")"
            )
            # ── Schema migration: add experiment_id column ──────────────
            try:
                conn.execute("SELECT experiment_id FROM leases LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE leases RENAME TO leases_old")
                conn.execute(
                    "CREATE TABLE leases ("
                    "  experiment_id TEXT NOT NULL,"
                    "  checkpoint_id TEXT NOT NULL,"
                    "  worker_invocation_id TEXT NOT NULL,"
                    "  lease_generation INTEGER NOT NULL,"
                    "  status TEXT NOT NULL,"
                    "  accepted_attempts TEXT NOT NULL DEFAULT '[]',"
                    "  PRIMARY KEY (experiment_id, checkpoint_id)"
                    ")"
                )
                conn.execute(
                    "INSERT INTO leases (experiment_id, checkpoint_id, worker_invocation_id, lease_generation, status, accepted_attempts) "
                    "SELECT '', checkpoint_id, worker_invocation_id, lease_generation, status, accepted_attempts FROM leases_old"
                )
                conn.execute("DROP TABLE leases_old")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS assets ("
                "  asset_id TEXT PRIMARY KEY,"
                "  experiment_id TEXT NOT NULL,"
                "  cell_key TEXT,"
                "  attempt_id TEXT,"
                "  variant TEXT NOT NULL,"
                "  parent_asset_id TEXT DEFAULT '',"
                "  path TEXT NOT NULL,"
                "  mime_type TEXT NOT NULL,"
                "  byte_size INTEGER NOT NULL DEFAULT 0,"
                "  content_hash TEXT,"
                "  node_id TEXT DEFAULT '',"
                "  output_key TEXT DEFAULT '',"
                "  output_index INTEGER DEFAULT 0,"
                "  comparison_side TEXT DEFAULT '',"
                "  width INTEGER DEFAULT 0,"
                "  height INTEGER DEFAULT 0,"
                "  created_at TEXT NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assets_exp ON assets(experiment_id)"
            )
            # ── Schema migration: add new columns for B3 asset schema ──
            _migrate_asset_schema(conn)
            self._conns[tid] = conn
        return conn

    def close(self) -> None:
        for conn in list(self._conns.values()):
            try:
                conn.close()
            except Exception:
                pass
        self._conns.clear()

    def close_thread(self) -> None:
        tid = threading.get_ident()
        c = self._conns.pop(tid, None)
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def __enter__(self) -> "LeaseRegistry":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ── Lease invalidation (cancellation boundary) ──────────────────

    def invalidate(self, experiment_id: str, checkpoint_id: str, clear_attempts: bool = False) -> dict:
        """Atomically invalidate a claimed lease.

        Sets status to ``"cancelling"`` and increments the lease generation so
        that ``validate_and_accept`` rejects any late events (the generation
        won't match AND the status won't be ``"claimed"``).

        When *clear_attempts* is ``True`` (A2 stricter mode), the
        ``accepted_attempts`` list is also cleared so a subsequent claim
        sees a clean slate. This is used by stop_now to ensure a re-claim
        after cancellation does not carry forward stale attempt IDs.

        This is an administrative operation — it does **not** require worker
        ownership.  It is called by the scheduler's ``stop_now`` path and by
        recovery to break the lease on dead workers.

        Raises ``UnknownCheckpointError`` if the checkpoint has no lease,
        or ``LeaseError`` if the lease is not in a live state (``"claimed"``
        or ``"cancelling"`` — the latter is a no-op for idempotency).
        """
        with self._lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT worker_invocation_id, lease_generation, status, accepted_attempts "
                    "FROM leases WHERE experiment_id = ? AND checkpoint_id = ?",
                    (experiment_id, checkpoint_id),
                ).fetchone()
                if not row:
                    raise UnknownCheckpointError(
                        f"unknown checkpoint {checkpoint_id!r}"
                    )
                _wid, cur_gen, status, _accepted = row
                if status == "cancelling":
                    # Idempotent — already invalidated.
                    if clear_attempts:
                        conn.execute(
                            "UPDATE leases SET accepted_attempts='[]' "
                            "WHERE experiment_id = ? AND checkpoint_id = ?",
                            (experiment_id, checkpoint_id),
                        )
                    conn.execute("COMMIT")
                    return {
                        "experiment_id": experiment_id,
                        "checkpoint_id": checkpoint_id,
                        "lease_generation": int(cur_gen),
                        "status": "cancelling",
                    }
                if status != "claimed":
                    raise LeaseError(
                        f"checkpoint {checkpoint_id!r} status is {status!r}, "
                        "cannot invalidate"
                    )
                new_gen = int(cur_gen) + 1
                if clear_attempts:
                    conn.execute(
                        "UPDATE leases SET status='cancelling', lease_generation=?, accepted_attempts='[]' "
                        "WHERE experiment_id = ? AND checkpoint_id = ?",
                        (new_gen, experiment_id, checkpoint_id),
                    )
                else:
                    conn.execute(
                        "UPDATE leases SET status='cancelling', lease_generation=? "
                        "WHERE experiment_id = ? AND checkpoint_id = ?",
                        (new_gen, experiment_id, checkpoint_id),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            return {
                "experiment_id": experiment_id,
                "checkpoint_id": checkpoint_id,
                "lease_generation": new_gen,
                "status": "cancelling",
            }

    # ── Public API ───────────────────────────────────────────────────

    def claim(self, experiment_id: str, checkpoint_id: str, worker_invocation_id: str) -> dict:
        with self._lock:
            conn = self._conn()
            # Use BEGIN IMMEDIATE to take the writer lock before the SELECT
            # so no other process can insert a conflicting row.
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT worker_invocation_id, lease_generation, status "
                    "FROM leases WHERE experiment_id = ? AND checkpoint_id = ?",
                    (experiment_id, checkpoint_id),
                ).fetchone()
                if row and row[2] == "claimed":
                    raise LeaseActiveError(
                        f"checkpoint {checkpoint_id!r} already claimed by "
                        f"{row[0]!r}"
                    )
                previous_gen = int(row[1]) if row else 0
                new_gen = previous_gen + 1
                conn.execute(
                    "INSERT OR REPLACE INTO leases "
                    "(experiment_id, checkpoint_id, worker_invocation_id, lease_generation, status, accepted_attempts) "
                    "VALUES (?, ?, ?, ?, 'claimed', '[]')",
                    (experiment_id, checkpoint_id, worker_invocation_id, new_gen),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            return {
                "experiment_id": experiment_id,
                "checkpoint_id": checkpoint_id,
                "worker_invocation_id": worker_invocation_id,
                "lease_generation": new_gen,
                "status": "claimed",
            }

    def release(self, experiment_id: str, checkpoint_id: str, worker_invocation_id: str) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT worker_invocation_id, status FROM leases WHERE experiment_id = ? AND checkpoint_id = ?",
                    (experiment_id, checkpoint_id),
                ).fetchone()
                if not row or row[1] not in ("claimed", "cancelling"):
                    raise LeaseOwnershipError(
                        f"checkpoint {checkpoint_id!r} has no active lease to release"
                    )
                if row[0] != worker_invocation_id:
                    raise LeaseOwnershipError(
                        f"worker {worker_invocation_id!r} does not own "
                        f"checkpoint {checkpoint_id!r}"
                    )
                conn.execute(
                    "UPDATE leases SET status='released' WHERE experiment_id = ? AND checkpoint_id = ?",
                    (experiment_id, checkpoint_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def accept_event(
        self,
        experiment_id: str,
        checkpoint_id: str,
        lease_generation: int,
        attempt_id: str,
    ) -> None:
        """Legacy: validate a streamed event against the current lease.

        Raises StaleEventError if the event's generation is older than the
        current generation for that checkpoint. Raises UnknownCheckpointError
        if the checkpoint has no lease. Returns silently on success.

        Prefer ``validate_and_accept`` which performs stricter validation
        including ownership and duplicate checks.
        """
        with self._lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT lease_generation, accepted_attempts FROM leases WHERE experiment_id = ? AND checkpoint_id = ?",
                    (experiment_id, checkpoint_id),
                ).fetchone()
                if not row:
                    raise UnknownCheckpointError(
                        f"unknown checkpoint {checkpoint_id!r}"
                    )
                current_gen = int(row[0])
                if int(lease_generation) < current_gen:
                    raise StaleEventError(
                        f"stale event for {checkpoint_id!r}: "
                        f"event gen {lease_generation} < current gen {current_gen}"
                    )
                attempts = json.loads(row[1]) if row[1] else []
                attempts.append(attempt_id)
                conn.execute(
                    "UPDATE leases SET accepted_attempts = ? WHERE experiment_id = ? AND checkpoint_id = ?",
                    (json.dumps(attempts), experiment_id, checkpoint_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def validate_and_accept(self, experiment_id: str, checkpoint_id: str, lease_generation: int,
                             worker_invocation_id: str, attempt_id: str) -> None:
        """Validate and accept a terminal event.

        Checks in order:
        1. Checkpoint lease exists.
        2. Lease status is 'claimed'.
        3. Event lease_generation equals current lease_generation exactly.
        4. Worker invocation ID matches the lease owner.
        5. This exact attempt_id hasn't already been accepted.

        Raises LeaseError with a clear message on any failure.
        On success, appends the attempt to accepted_attempts.
        """
        with self._lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT worker_invocation_id, lease_generation, status, accepted_attempts "
                    "FROM leases WHERE experiment_id = ? AND checkpoint_id = ?",
                    (experiment_id, checkpoint_id),
                ).fetchone()
                if not row:
                    raise UnknownCheckpointError(f"unknown checkpoint {checkpoint_id!r}")
                wid, stored_gen, status, attempts_json = row
                if status != "claimed":
                    if status == "cancelling":
                        raise CancellationBoundary(
                            f"checkpoint {checkpoint_id!r} has been cancelled; "
                            f"late event rejected"
                        )
                    raise LeaseError(
                        f"checkpoint {checkpoint_id!r} status is {status!r}, not claimed"
                    )
                if int(lease_generation) != int(stored_gen):
                    raise StaleEventError(
                        f"stale event for {checkpoint_id!r}: "
                        f"event gen {lease_generation} != current gen {stored_gen}"
                    )
                if str(wid) != str(worker_invocation_id):
                    raise LeaseOwnershipError(
                        f"worker {worker_invocation_id!r} does not own "
                        f"checkpoint {checkpoint_id!r} (owner: {wid!r})"
                    )
                try:
                    accepted = json.loads(attempts_json) if attempts_json else []
                except json.JSONDecodeError:
                    accepted = []
                if attempt_id in accepted:
                    raise LeaseError(
                        f"duplicate attempt {attempt_id!r} for checkpoint {checkpoint_id!r}"
                    )
                accepted.append(attempt_id)
                conn.execute(
                    "UPDATE leases SET accepted_attempts = ? WHERE experiment_id = ? AND checkpoint_id = ?",
                    (json.dumps(accepted), experiment_id, checkpoint_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def snapshot(self, experiment_id: str | None = None) -> dict:
        with self._lock:
            conn = self._conn()
            if experiment_id:
                cur = conn.execute(
                    "SELECT checkpoint_id, worker_invocation_id, lease_generation, status, accepted_attempts "
                    "FROM leases WHERE experiment_id = ?",
                    (experiment_id,),
                )
            else:
                cur = conn.execute(
                    "SELECT checkpoint_id, worker_invocation_id, lease_generation, status, accepted_attempts "
                    "FROM leases"
                )
            out: dict[str, Any] = {}
            for row in cur.fetchall():
                out[row[0]] = {
                    "worker_invocation_id": row[1],
                    "lease_generation": int(row[2]),
                    "status": row[3],
                    "accepted_attempts": json.loads(row[4]) if row[4] else [],
                }
            return {"leases": out}

    # ── Asset registry ────────────────────────────────────────────────────

    def register_asset(self, asset_id: str, experiment_id: str, cell_key: str = "",
                        attempt_id: str = "", variant: str = "original",
                        path: str = "", mime_type: str = "image/png",
                        byte_size: int = 0, content_hash: str = "",
                        parent_asset_id: str = "",
                        node_id: str = "", output_key: str = "",
                        output_index: int = 0, comparison_side: str = "",
                        width: int = 0, height: int = 0,
                        created_at: str | None = None) -> None:
        """Register an asset with the extended B3 schema.

        Uses INSERT OR IGNORE — the first write for a given asset_id wins,
        preventing accidental overwrite of ownership records.
        """
        if created_at is None:
            from datetime import datetime, timezone
            created_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO assets "
                "(asset_id, experiment_id, cell_key, attempt_id, variant, "
                " parent_asset_id, path, mime_type, byte_size, content_hash, "
                " node_id, output_key, output_index, comparison_side, "
                " width, height, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (asset_id, experiment_id, cell_key, attempt_id, variant,
                 parent_asset_id, path, mime_type, byte_size, content_hash,
                 node_id, output_key, output_index, comparison_side,
                 width, height, created_at),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def resolve_asset(self, asset_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT asset_id, experiment_id, cell_key, attempt_id, variant, "
            "parent_asset_id, path, mime_type, byte_size, content_hash, "
            "node_id, output_key, output_index, comparison_side, "
            "width, height, created_at "
            "FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "asset_id": row[0],
            "experiment_id": row[1],
            "cell_key": row[2],
            "attempt_id": row[3],
            "variant": row[4],
            "parent_asset_id": row[5],
            "path": row[6],
            "mime_type": row[7],
            "byte_size": row[8],
            "content_hash": row[9],
            "node_id": row[10],
            "output_key": row[11],
            "output_index": row[12],
            "comparison_side": row[13],
            "width": row[14],
            "height": row[15],
            "created_at": row[16],
        }

    def list_assets_for_experiment(self, experiment_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT asset_id, variant, path, node_id, output_key, output_index, "
            "comparison_side, width, height, parent_asset_id "
            "FROM assets WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchall()
        return [
            {"asset_id": r[0], "variant": r[1], "path": r[2],
             "node_id": r[3], "output_key": r[4], "output_index": r[5],
             "comparison_side": r[6], "width": r[7], "height": r[8],
             "parent_asset_id": r[9]}
            for r in rows
        ]

    def list_assets_for_cell(self, cell_key: str, experiment_id: str = "") -> list[dict]:
        """List assets for a specific cell key, optionally filtered by experiment.

        Returns dicts with extended B3 schema fields: asset_id, variant, path,
        mime_type, attempt_id, node_id, output_key, output_index, comparison_side,
        width, height, parent_asset_id, byte_size, content_hash.
        """
        conn = self._conn()
        if experiment_id:
            rows = conn.execute(
                "SELECT asset_id, variant, path, mime_type, attempt_id, "
                "node_id, output_key, output_index, comparison_side, "
                "width, height, parent_asset_id, byte_size, content_hash "
                "FROM assets WHERE cell_key = ? AND experiment_id = ?",
                (cell_key, experiment_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT asset_id, variant, path, mime_type, attempt_id, "
                "node_id, output_key, output_index, comparison_side, "
                "width, height, parent_asset_id, byte_size, content_hash "
                "FROM assets WHERE cell_key = ?",
                (cell_key,),
            ).fetchall()
        return [
            {"asset_id": r[0], "variant": r[1], "path": r[2], "mime_type": r[3],
             "attempt_id": r[4], "node_id": r[5], "output_key": r[6],
             "output_index": r[7], "comparison_side": r[8], "width": r[9],
             "height": r[10], "parent_asset_id": r[11],
             "byte_size": int(r[12]) if r[12] is not None else 0,
             "content_hash": r[13] or ""}
            for r in rows
        ]
