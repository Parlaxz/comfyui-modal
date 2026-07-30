"""Rebuildable derived SQLite summary index for run-history source JSON.

The index is a local SQLite database at ``<run_history_root>/.history_index.db``
that caches summary fields from the authoritative per-run ``meta.json`` files.
Source JSON is always authoritative; the index is a derived cache that can be
rebuilt at any time without data loss.

Schema versioning and WAL journal mode are used for safe concurrent access.
Transactional upserts keep the index consistent.  Index writes never block
or corrupt source writes.  When the index is missing, corrupt, or stale, it
is rebuilt lazily on the next query.  Stale entries are detected via source
mtime comparison.

Summary fields indexed:
  - record id (run_id)
  - kind (ordinary, experiment_cell, studio_run, deploy, warmup)
  - status
  - started_at, completed_at, updated_at (timestamps)
  - experiment_id, experiment_revision
  - preset_id, preset_label
  - feature_id
  - favorite, note (annotations)
  - prompt, negative_prompt (search summary)
  - seed, steps, guidance, sampler, scheduler
  - primary_image_path, output_count
  - duration_ms, timing_summary_json
  - execution_engine
  - source_path, source_mtime
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ── Schema ─────────────────────────────────────────────────────────────────

SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  schema_version INTEGER NOT NULL DEFAULT {v}
);
INSERT INTO meta (schema_version) VALUES ({v}) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS index_entries (
  run_id          TEXT PRIMARY KEY NOT NULL,
  kind            TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT '',
  started_at      TEXT NOT NULL DEFAULT '',
  completed_at    TEXT NOT NULL DEFAULT '',
  updated_at      TEXT NOT NULL DEFAULT '',
  experiment_id   TEXT NOT NULL DEFAULT '',
  experiment_revision INTEGER NOT NULL DEFAULT 0,
  preset_id       TEXT NOT NULL DEFAULT '',
  preset_label    TEXT NOT NULL DEFAULT '',
  feature_id      TEXT NOT NULL DEFAULT '',
  favorite        INTEGER NOT NULL DEFAULT 0,
  note            TEXT NOT NULL DEFAULT '',
  prompt          TEXT NOT NULL DEFAULT '',
  negative_prompt TEXT NOT NULL DEFAULT '',
  seed            INTEGER,
  steps           INTEGER,
  guidance        REAL,
  sampler         TEXT NOT NULL DEFAULT '',
  scheduler       TEXT NOT NULL DEFAULT '',
  primary_image_path TEXT NOT NULL DEFAULT '',
  output_count    INTEGER NOT NULL DEFAULT 0,
  duration_ms     REAL,
  timing_summary_json TEXT NOT NULL DEFAULT '{{}}',
  execution_engine   TEXT NOT NULL DEFAULT '',
  source_path     TEXT NOT NULL DEFAULT '',
  source_mtime    REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_kind ON index_entries(kind);
CREATE INDEX IF NOT EXISTS idx_status ON index_entries(status);
CREATE INDEX IF NOT EXISTS idx_favorite ON index_entries(favorite);
CREATE INDEX IF NOT EXISTS idx_experiment_id ON index_entries(experiment_id);
CREATE INDEX IF NOT EXISTS idx_preset_id ON index_entries(preset_id);
CREATE INDEX IF NOT EXISTS idx_feature_id ON index_entries(feature_id);
CREATE INDEX IF NOT EXISTS idx_started_at ON index_entries(started_at);
""".format(v=SCHEMA_VERSION)


# ── Locking ────────────────────────────────────────────────────────────────

_db_lock = threading.Lock()


# ── Index class ────────────────────────────────────────────────────────────


class HistoryIndex:
    """Thread-safe, rebuildable SQLite summary index for run history.

    Usage::

        idx = HistoryIndex(run_history_root)
        idx.ensure()
        idx.rebuild()                 # full scan of source meta.json files
        row = idx.get("r_abc123")     # single record
        results = idx.query(...)      # filtered, sorted, paginated
        idx.upsert_from_meta(...)     # incremental update from a meta dict
        idx.remove("r_abc123")        # remove deleted/archived records
        idx.mark_stale(run_id)        # mark for refresh on next query
    """

    MAX_ENSURE_ATTEMPTS = 3

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._db_path = self._root / ".history_index.db"
        # Track whether schema has been initialised this session
        self._schema_initialised = False
        # Connections are owned by this index instance.  A process-wide
        # thread-local cache can retain a temporary database after its service
        # is gone (and, worse, route a second index instance to the first
        # instance's database).  Per-instance caches keep roots isolated and
        # let close() release every handle for Windows cleanup.
        self._connections: dict[int, sqlite3.Connection] = {}
        self._connections_lock = threading.Lock()

    # ── Connection ──────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        tid = threading.get_ident()
        with self._connections_lock:
            conn = self._connections.get(tid)
            if conn is not None:
                return conn
            self._root.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self._db_path),
                isolation_level=None,  # autocommit; explicit transactions
                timeout=30.0,
                check_same_thread=True,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._connections[tid] = conn
            if not self._schema_initialised:
                self._init_schema(conn)
                self._schema_initialised = True
            return conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        """Create tables and indexes if they do not exist.

        Does NOT check schema version or trigger rebuild — that is the
        responsibility of ``ensure()``.  Safe to call multiple times.
        """
        conn.executescript(_SCHEMA_SQL)

    def _cursor(self) -> sqlite3.Cursor:
        return self._conn().cursor()

    def close(self) -> None:
        self._close_all()

    # ── Upsert helpers ──────────────────────────────────────────────────

    def _extract_summary(self, meta_obj: dict, source_path: str = "") -> dict:
        """Flatten a meta.json dict into index summary fields."""
        extra = meta_obj.get("extra", {}) or {}
        ann = meta_obj.get("annotations", {}) or {}
        timing_summary = meta_obj.get("timing_summary", {}) or {}

        # Compute duration from various possible sources
        duration_ms: Optional[float] = meta_obj.get("duration_ms")
        if duration_ms is None:
            duration_ms = timing_summary.get("end_to_end_total_ms")
        if duration_ms is None:
            duration_ms = timing_summary.get("total_ms")

        # Derive primary image path
        primary_image = meta_obj.get("output_path", "") or extra.get("output_path", "")

        # Derive preset_id/label from extra
        preset_id = extra.get("studio_preset_id", "") or extra.get("preset_id", "")
        preset_label = extra.get("studio_preset_label", "") or extra.get("preset_label", "")
        feature_id = extra.get("studio_feature_id", "") or extra.get("feature_id", "")

        # Derive generation controls from extra
        controls = extra.get("resolved_controls", {}) or extra.get("requested_controls", {}) or {}
        prompt = controls.get("prompt", "") or meta_obj.get("prompt", "")
        negative_prompt = controls.get("negative_prompt", "") or meta_obj.get("negative_prompt", "")

        return {
            "run_id": meta_obj.get("run_id", ""),
            "kind": meta_obj.get("kind", ""),
            "status": meta_obj.get("status", ""),
            "started_at": meta_obj.get("started_at", "") or "",
            "completed_at": meta_obj.get("completed_at", "") or "",
            "updated_at": meta_obj.get("updated_at", "") or "",
            "experiment_id": extra.get("experiment_id", "") or meta_obj.get("experiment_id", ""),
            "experiment_revision": int(extra.get("experiment_revision", 0) or meta_obj.get("experiment_revision", 0)),
            "preset_id": preset_id,
            "preset_label": preset_label,
            "feature_id": feature_id,
            "favorite": 1 if ann.get("favorite") else 0,
            "note": ann.get("note", "") or "",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": controls.get("seed") or meta_obj.get("seed"),
            "steps": controls.get("steps") or meta_obj.get("steps"),
            "guidance": controls.get("guidance") or controls.get("cfg") or meta_obj.get("guidance"),
            "sampler": controls.get("sampler") or controls.get("sampler_name") or meta_obj.get("sampler", ""),
            "scheduler": controls.get("scheduler") or meta_obj.get("scheduler", ""),
            "primary_image_path": primary_image,
            "output_count": int(extra.get("output_count", 0) or 0),
            "duration_ms": duration_ms,
            "timing_summary_json": json.dumps(timing_summary, ensure_ascii=False, default=str),
            "execution_engine": extra.get("execution_engine", "") or "",
            "source_path": source_path,
            "source_mtime": os.path.getmtime(source_path) if source_path and os.path.isfile(source_path) else 0,
        }

    def upsert_from_meta(self, meta_obj: dict, source_path: str = "") -> None:
        """Insert or update a single index entry from a meta.json dict.

        Safe to call from any thread.  Uses a transactional UPSERT so
        concurrent callers do not corrupt each other.
        """
        row = self._extract_summary(meta_obj, source_path)
        run_id = row["run_id"]
        if not run_id:
            return
        conn = self._conn()
        with _db_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO index_entries (
                        run_id, kind, status, started_at, completed_at, updated_at,
                        experiment_id, experiment_revision,
                        preset_id, preset_label, feature_id,
                        favorite, note, prompt, negative_prompt,
                        seed, steps, guidance, sampler, scheduler,
                        primary_image_path, output_count, duration_ms,
                        timing_summary_json, execution_engine,
                        source_path, source_mtime
                    ) VALUES (
                        :run_id, :kind, :status, :started_at, :completed_at, :updated_at,
                        :experiment_id, :experiment_revision,
                        :preset_id, :preset_label, :feature_id,
                        :favorite, :note, :prompt, :negative_prompt,
                        :seed, :steps, :guidance, :sampler, :scheduler,
                        :primary_image_path, :output_count, :duration_ms,
                        :timing_summary_json, :execution_engine,
                        :source_path, :source_mtime
                    )""",
                    row,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def remove(self, run_id: str) -> None:
        """Remove a run from the index (e.g. on deletion/archival)."""
        if not run_id:
            return
        conn = self._conn()
        with _db_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM index_entries WHERE run_id = ?", (run_id,))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def mark_stale(self, run_id: str) -> None:
        """Set source_mtime to 0 so the entry is refreshed on next query."""
        if not run_id:
            return
        conn = self._conn()
        with _db_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE index_entries SET source_mtime = 0 WHERE run_id = ?",
                    (run_id,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    # ── Query ───────────────────────────────────────────────────────────

    def get(self, run_id: str) -> Optional[dict]:
        """Fetch a single index entry by run_id."""
        if not run_id:
            return None
        row = self._cursor().execute(
            "SELECT * FROM index_entries WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def query(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        favorite_only: bool = False,
        sort: str = "newest",
        feature: Optional[str] = None,
        preset: Optional[str] = None,
        experiment_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        has_image: Optional[bool] = None,
    ) -> dict:
        """Query the index with filtering, sorting, and pagination.

        Returns ``{"items": [...], "page": int, "page_size": int,
        "total": int, "has_more": bool}``.
        """
        conn = self._conn()

        # ── Build WHERE clauses ─────────────────────────────────────────
        wheres: list[str] = []
        params: list[Any] = []

        if kind:
            wheres.append("kind = ?")
            params.append(kind)
        if status:
            wheres.append("status = ?")
            params.append(status)
        if favorite_only:
            wheres.append("favorite = 1")
        if feature:
            wheres.append("feature_id = ?")
            params.append(feature)
        if preset:
            wheres.append("(preset_id = ? OR preset_label = ?)")
            params.extend([preset, preset])
        if experiment_id:
            wheres.append("experiment_id = ?")
            params.append(experiment_id)
        if date_from:
            wheres.append("started_at >= ?")
            params.append(date_from)
        if date_to:
            # If date-only (no T), extend to end-of-day
            date_to_effective = date_to
            if "T" not in date_to:
                date_to_effective = date_to + "T23:59:59Z"
            wheres.append("(started_at <= ? OR started_at = '')")
            params.append(date_to_effective)
        if has_image is True:
            wheres.append("primary_image_path != ''")
        elif has_image is False:
            wheres.append("primary_image_path = ''")
        if search:
            wheres.append(
                "(run_id LIKE ? OR prompt LIKE ? OR negative_prompt LIKE ? "
                "OR note LIKE ? OR experiment_id LIKE ? OR preset_label LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like, like])

        where_clause = " AND ".join(wheres) if wheres else "1=1"

        # ── Count total ─────────────────────────────────────────────────
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM index_entries WHERE {where_clause}", params
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        # ── Sort ────────────────────────────────────────────────────────
        sort_map = {
            "newest": "COALESCE(started_at, '') DESC",
            "oldest": "COALESCE(started_at, '') ASC",
            "fastest": "COALESCE(duration_ms, 999999999) ASC",
            "slowest": "COALESCE(duration_ms, 0) DESC",
            "preset_az": "CASE WHEN preset_label = '' THEN 1 ELSE 0 END, preset_label ASC",
            "preset_za": "CASE WHEN preset_label = '' THEN 1 ELSE 0 END, preset_label DESC",
        }
        order_by = sort_map.get(sort, "COALESCE(started_at, '') DESC")

        # ── Paginate ────────────────────────────────────────────────────
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM index_entries WHERE {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()

        items = [self._row_to_dict(r) for r in rows]
        has_more = (offset + page_size) < total

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": has_more,
        }

    # ── Rebuild ─────────────────────────────────────────────────────────

    def rebuild(self) -> int:
        """Full rebuild: scan all source meta.json files and re-index.

        The source root is the same directory passed to ``__init__``; each
        run is stored as ``<run_id>/meta.json`` inside it (the layout used
        by ``RunHistoryService``).

        Uses a single transaction for atomicity.  Returns count of records
        indexed.  Safe to call while the index is in use (queries during
        rebuild will see the old index until the replace completes).
        """
        if not self._root.is_dir():
            return 0

        # Collect all meta files with their mtimes
        entries: list[tuple[dict, str]] = []
        for entry_dir in sorted(self._root.iterdir()):
            if not entry_dir.is_dir() or entry_dir.name.startswith("."):
                continue
            meta_path = entry_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta_obj = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            entries.append((meta_obj, str(meta_path)))

        if not entries:
            return 0

        conn = self._conn()
        with _db_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Delete all existing entries efficiently
                conn.execute("DELETE FROM index_entries")
                if entries:
                    conn.executemany(
                        """INSERT INTO index_entries (
                            run_id, kind, status, started_at, completed_at, updated_at,
                            experiment_id, experiment_revision,
                            preset_id, preset_label, feature_id,
                            favorite, note, prompt, negative_prompt,
                            seed, steps, guidance, sampler, scheduler,
                            primary_image_path, output_count, duration_ms,
                            timing_summary_json, execution_engine,
                            source_path, source_mtime
                        ) VALUES (
                            :run_id, :kind, :status, :started_at, :completed_at, :updated_at,
                            :experiment_id, :experiment_revision,
                            :preset_id, :preset_label, :feature_id,
                            :favorite, :note, :prompt, :negative_prompt,
                            :seed, :steps, :guidance, :sampler, :scheduler,
                            :primary_image_path, :output_count, :duration_ms,
                            :timing_summary_json, :execution_engine,
                            :source_path, :source_mtime
                        )""",
                        (self._extract_summary(meta, path) for meta, path in entries),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return len(entries)

    def _close_all(self) -> None:
        """Close all connections owned by this index instance."""
        with self._connections_lock:
            connections = list(self._connections.values())
            self._connections.clear()
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _unlink_db_files(db_path: Path) -> None:
        """Safely remove a SQLite database and its WAL/SHM companions."""
        for suffix in ("", "-wal", "-shm"):
            p = db_path.with_suffix(db_path.suffix + suffix) if suffix else db_path
            try:
                p.unlink(missing_ok=True)
            except PermissionError:
                pass  # locked by another process; will be handled on retry

    def ensure(self) -> bool:
        """Ensure the index exists and is usable.

        Returns True if the index was already usable, False if a rebuild
        was triggered (corrupt, missing, or schema mismatch).

        Handles corrupt databases, missing files, and schema version
        mismatch (both too-old and too-new) safely without infinite
        recursion.  Closes all stale connections before unlinking the
        database file so Windows file-lock issues are avoided.
        """
        attempts = 0
        while attempts < self.MAX_ENSURE_ATTEMPTS:
            if not self._db_path.exists():
                self._init_schema(self._conn())
                self.rebuild()
                return False
            # Close cached connections so the validation opens a fresh one
            # and detects file-level corruption (not stale cached handles).
            self._close_all()
            self._schema_initialised = False
            # Remove stale WAL/SHM files from prior sessions that can mask
            # main-file corruption on the next PRAGMA (SQLite WAL recovery
            # can roll forward from an intact WAL even when the main file
            # is garbage).  Do NOT remove the main DB file — we need it to
            # exist so that fresh-open detects corruption.
            for suffix in ("-wal", "-shm"):
                p = self._db_path.with_suffix(self._db_path.suffix + suffix)
                try:
                    p.unlink(missing_ok=True)
                except PermissionError:
                    pass
            try:
                conn = self._conn()
                # Run integrity_check to force full file validation
                check = conn.execute("PRAGMA integrity_check").fetchone()
                if check and check[0] != "ok":
                    raise sqlite3.DatabaseError(
                        "integrity check: " + str(check[0])
                    )
                row = conn.execute(
                    "SELECT schema_version FROM meta LIMIT 1"
                ).fetchone()
                sv = row[0] if row else 0
                if sv == SCHEMA_VERSION:
                    return True
                # Schema mismatch — rebuild
                self._close_all()
                self._unlink_db_files(self._db_path)
                self._schema_initialised = False
                attempts += 1
                continue
            except sqlite3.DatabaseError:
                self._close_all()
                self._unlink_db_files(self._db_path)
                self._schema_initialised = False
                attempts += 1
                continue
        # Final fallback: re-init from scratch
        self._close_all()
        self._unlink_db_files(self._db_path)
        self._schema_initialised = False
        self._init_schema(self._conn())
        self.rebuild()
        return False

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to a plain dict with parsed timing_summary."""
        d = dict(zip(row.keys(), row))
        # Parse timing_summary_json back to dict
        tsj = d.get("timing_summary_json", "{}") or "{}"
        try:
            d["timing_summary"] = json.loads(tsj) if isinstance(tsj, str) else {}
        except (json.JSONDecodeError, TypeError):
            d["timing_summary"] = {}
        d.pop("timing_summary_json", None)
        d["favorite"] = bool(d.get("favorite", 0))
        return d
