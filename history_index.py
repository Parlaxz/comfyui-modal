"""Rebuildable derived SQLite summary index for run-history source JSON.

The index is a local SQLite database at ``<run_history_root>/.history_index.db``
that caches summary fields from the authoritative per-run ``meta.json`` files.
Source JSON is always authoritative; the index is a derived cache that can be
rebuilt at any time without data loss.

Schema versioning and WAL journal mode are used for safe concurrent access.
Transactional upserts keep the index consistent.  Index writes never block
or corrupt source writes.  When the index is missing, corrupt,
schema-incompatible, or demonstrably stale, it is rebuilt once (bounded)
from the authoritative source.  Staleness is detected by comparing the
source root's run directories against a stored source fingerprint; health
validation and the staleness probe are rate-limited per process so healthy
indexes are never revalidated or rebuilt on every request.

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

# How often a validated index is re-checked for health (per process).
# Keeps per-request work on a healthy index to a single cached check.
VALIDATE_INTERVAL_S = 60.0
# How often the source root is probed for staleness (per process).
STALE_CHECK_INTERVAL_S = 5.0

# Columns a usable ``index_entries`` table must have.  Used to detect and
# repair flat/incompatible/foreign tables during schema initialisation.
_INDEX_ENTRIES_COLUMNS = frozenset({
    "run_id", "kind", "status", "started_at", "completed_at", "updated_at",
    "experiment_id", "experiment_revision", "preset_id", "preset_label",
    "feature_id", "favorite", "note", "prompt", "negative_prompt",
    "seed", "steps", "guidance", "sampler", "scheduler",
    "primary_image_path", "output_count", "duration_ms",
    "timing_summary_json", "execution_engine", "source_path", "source_mtime",
    "output_saved", "output_saved_index",
})

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  schema_version INTEGER PRIMARY KEY NOT NULL DEFAULT {v}
);
INSERT OR IGNORE INTO meta (schema_version) VALUES ({v});

CREATE TABLE IF NOT EXISTS index_meta (
  key   TEXT PRIMARY KEY NOT NULL,
  value TEXT NOT NULL DEFAULT ''
);

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
  source_mtime    REAL NOT NULL DEFAULT 0,
  output_saved    INTEGER NOT NULL DEFAULT 0,
  output_saved_index INTEGER
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
        idx.ensure()                  # validate (rate-limited per process)
        idx.rebuild()                 # full scan of source meta.json files
        idx.refresh_if_stale()        # rebuild only when source is stale
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
        # Health/staleness caches: full validation and the source-root
        # staleness probe are rate-limited per process so a healthy index is
        # neither revalidated nor rebuilt on every request.
        self._validated_at: Optional[float] = None
        self._last_stale_check: float = 0.0
        self._ensure_lock = threading.Lock()

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

        A pre-existing ``index_entries`` table that is flat or otherwise
        incompatible (wrong columns) is dropped and recreated first, so a
        foreign/partial database cannot wedge the index forever.  This is a
        derived cache — dropping it loses nothing but derived rows.

        Serialized behind the process-wide write lock and retried on
        transient lock contention so concurrent first-use from multiple
        threads/instances cannot fail schema initialisation.
        """
        with _db_lock:
            try:
                cols = {
                    row[1] for row in conn.execute("PRAGMA table_info(index_entries)")
                }
            except sqlite3.DatabaseError:
                cols = set()
            if cols and cols != _INDEX_ENTRIES_COLUMNS:
                conn.execute("DROP TABLE IF EXISTS index_entries")
            for attempt in range(1, self.MAX_ENSURE_ATTEMPTS + 1):
                try:
                    conn.executescript(_SCHEMA_SQL)
                    return
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt == self.MAX_ENSURE_ATTEMPTS:
                        raise
                    time.sleep(0.05 * attempt)

    def _cursor(self) -> sqlite3.Cursor:
        return self._conn().cursor()

    def close(self) -> None:
        tid = threading.get_ident()
        with self._connections_lock:
            conn = self._connections.pop(tid, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

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
        if not isinstance(controls, dict):
            controls = {}

        def _value(mapping: dict, *keys: str, fallback: Any = None) -> Any:
            for key in keys:
                if key in mapping and mapping[key] is not None:
                    return mapping[key]
            return fallback

        prompt = _value(
            controls,
            "prompt",
            fallback=_value(extra, "prompt", fallback=meta_obj.get("prompt", "")),
        )
        negative_prompt = _value(
            controls,
            "negative_prompt",
            fallback=_value(extra, "negative_prompt", fallback=meta_obj.get("negative_prompt", "")),
        )
        experiment_revision = _value(
            extra,
            "experiment_revision",
            fallback=meta_obj.get("experiment_revision", 0),
        )
        try:
            experiment_revision = int(experiment_revision or 0)
        except (TypeError, ValueError):
            experiment_revision = 0
        output_count = _value(extra, "output_count", fallback=0)
        try:
            output_count = int(output_count or 0)
        except (TypeError, ValueError):
            output_count = 0
        saved_index = _value(extra, "output_saved_index")
        try:
            saved_index = int(saved_index) if saved_index is not None else None
        except (TypeError, ValueError):
            saved_index = None

        return {
            "run_id": meta_obj.get("run_id", ""),
            "kind": meta_obj.get("kind", ""),
            "status": meta_obj.get("status", ""),
            "started_at": meta_obj.get("started_at", "") or "",
            "completed_at": meta_obj.get("completed_at", "") or "",
            "updated_at": meta_obj.get("updated_at", "") or "",
            "experiment_id": extra.get("experiment_id", "") or meta_obj.get("experiment_id", ""),
            "experiment_revision": experiment_revision,
            "preset_id": preset_id,
            "preset_label": preset_label,
            "feature_id": feature_id,
            "favorite": 1 if ann.get("favorite") else 0,
            "note": ann.get("note", "") or "",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": _value(controls, "seed", fallback=_value(extra, "seed", fallback=meta_obj.get("seed"))),
            "steps": _value(controls, "steps", fallback=_value(extra, "steps", fallback=meta_obj.get("steps"))),
            "guidance": _value(
                controls,
                "guidance",
                "cfg",
                fallback=_value(extra, "guidance", "cfg", fallback=meta_obj.get("guidance")),
            ),
            "sampler": _value(
                controls,
                "sampler",
                "sampler_name",
                fallback=_value(extra, "sampler", "sampler_name", fallback=meta_obj.get("sampler", "")),
            ),
            "scheduler": _value(
                controls,
                "scheduler",
                fallback=_value(extra, "scheduler", fallback=meta_obj.get("scheduler", "")),
            ),
            "primary_image_path": primary_image,
            "output_count": output_count,
            "duration_ms": duration_ms,
            "timing_summary_json": json.dumps(timing_summary, ensure_ascii=False, default=str),
            "execution_engine": extra.get("execution_engine", "") or "",
            "source_path": source_path,
            "source_mtime": os.path.getmtime(source_path) if source_path and os.path.isfile(source_path) else 0,
            "output_saved": 1 if extra.get("output_saved") is True else 0,
            "output_saved_index": saved_index,
        }

    def upsert_from_meta(self, meta_obj: dict, source_path: str = "") -> None:
        """Insert or update a single index entry from a meta.json dict.

        Safe to call from any thread.  Uses a transactional UPSERT so
        concurrent callers do not corrupt each other.  Also keeps the stored
        source fingerprint in sync so plugin-owned writes are not mistaken
        for external (stale) changes by the staleness probe.
        """
        row = self._extract_summary(meta_obj, source_path)
        run_id = row["run_id"]
        if not run_id:
            return
        conn = self._conn()
        with _db_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existed = (
                    conn.execute(
                        "SELECT 1 FROM index_entries WHERE run_id = ?", (run_id,)
                    ).fetchone()
                    is not None
                )
                conn.execute(
                    """INSERT OR REPLACE INTO index_entries (
                        run_id, kind, status, started_at, completed_at, updated_at,
                        experiment_id, experiment_revision,
                        preset_id, preset_label, feature_id,
                        favorite, note, prompt, negative_prompt,
                        seed, steps, guidance, sampler, scheduler,
                        primary_image_path, output_count, duration_ms,
                        timing_summary_json, execution_engine,
                        source_path, source_mtime, output_saved, output_saved_index
                    ) VALUES (
                        :run_id, :kind, :status, :started_at, :completed_at, :updated_at,
                        :experiment_id, :experiment_revision,
                        :preset_id, :preset_label, :feature_id,
                        :favorite, :note, :prompt, :negative_prompt,
                        :seed, :steps, :guidance, :sampler, :scheduler,
                        :primary_image_path, :output_count, :duration_ms,
                        :timing_summary_json, :execution_engine,
                        :source_path, :source_mtime, :output_saved, :output_saved_index
                    )""",
                    row,
                )
                self._bump_index_meta(
                    conn,
                    added=not existed,
                    dir_mtime=self._source_dir_mtime(source_path),
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
                existed = (
                    conn.execute(
                        "SELECT 1 FROM index_entries WHERE run_id = ?", (run_id,)
                    ).fetchone()
                    is not None
                )
                conn.execute("DELETE FROM index_entries WHERE run_id = ?", (run_id,))
                if existed:
                    self._bump_index_meta(conn, removed=True)
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
        # Refresh only the entries explicitly marked stale (source_mtime = 0);
        # this is bounded by the number of marked rows and never rescans the
        # whole source root.
        self._refresh_marked_stale(conn)

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

        Always clears the previous index first — including when the source
        is now empty — so removed runs are pruned.  Also records a source
        fingerprint (run-directory count + max mtime) used by the
        ``refresh_if_stale`` staleness probe.
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

        # Source fingerprint for the staleness probe: count of run dirs plus
        # the newest run-dir mtime (cheap shallow stat, no JSON parsing).
        src_count = 0
        src_max_mtime = 0.0
        for entry_dir in sorted(self._root.iterdir()):
            if not entry_dir.is_dir() or entry_dir.name.startswith("."):
                continue
            src_count += 1
            try:
                src_max_mtime = max(src_max_mtime, entry_dir.stat().st_mtime)
            except OSError:
                pass

        conn = self._conn()
        with _db_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Delete all existing entries efficiently (also prunes removed
                # runs when the source is now empty).
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
                            source_path, source_mtime, output_saved, output_saved_index
                        ) VALUES (
                            :run_id, :kind, :status, :started_at, :completed_at, :updated_at,
                            :experiment_id, :experiment_revision,
                            :preset_id, :preset_label, :feature_id,
                            :favorite, :note, :prompt, :negative_prompt,
                            :seed, :steps, :guidance, :sampler, :scheduler,
                            :primary_image_path, :output_count, :duration_ms,
                            :timing_summary_json, :execution_engine,
                            :source_path, :source_mtime, :output_saved, :output_saved_index
                        )""",
                        (self._extract_summary(meta, path) for meta, path in entries),
                    )
                self._write_index_meta(conn, {
                    "schema_version": str(SCHEMA_VERSION),
                    "source_dir_count": str(src_count),
                    "source_max_mtime": repr(src_max_mtime),
                    "built_at": repr(time.time()),
                })
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

    def ensure(self, *, force: bool = False) -> bool:
        """Ensure the index exists and is usable.

        Cheap for a healthy index: the full health check (fresh connection,
        SQLite header probe, integrity check, schema-version check) runs at
        most once per ``VALIDATE_INTERVAL_S`` per process, so a healthy
        index is never revalidated — or rebuilt — on every request.  A
        rebuild is triggered ONLY when the index is missing, corrupt, or
        schema-incompatible.  Demonstrable staleness is handled separately
        by ``refresh_if_stale``.

        Returns True if the index was already usable, False if a rebuild
        was triggered.  Raises ``sqlite3.Error`` if the index cannot be made
        usable after bounded recovery attempts.
        """
        with self._ensure_lock:
            now = time.monotonic()
            if (not force and self._validated_at is not None
                    and now - self._validated_at < VALIDATE_INTERVAL_S):
                return True

            # Close cached handles and re-initialise so the validation opens
            # a fresh connection and detects file-level corruption (not stale
            # cached handles).  This happens only on a validation event, not
            # on every request.
            self._close_all()
            self._schema_initialised = False

            if not self._db_path.exists():
                count = self.rebuild()
                self._validated_at = time.monotonic()
                print(
                    f"[comfyui-modal.history-index] index missing; "
                    f"rebuilt {count} records from source"
                )
                return False

            # Cheap corruption probe: a SQLite database file starts with a
            # 16-byte magic header.  A missing/foreign header means the file
            # is not (or is no longer) a usable database.
            if not self._main_file_has_sqlite_header():
                self._recover_and_rebuild("index file is not a database")
                return False

            try:
                conn = self._conn()
                # Run integrity_check to force full file validation.
                check = conn.execute("PRAGMA integrity_check").fetchone()
                if check and check[0] != "ok":
                    raise sqlite3.DatabaseError(
                        "integrity check: " + str(check[0])
                    )
                row = conn.execute(
                    "SELECT schema_version FROM meta LIMIT 1"
                ).fetchone()
                sv = row[0] if row else 0
                if sv != SCHEMA_VERSION:
                    raise sqlite3.DatabaseError(
                        f"schema version {sv} != expected {SCHEMA_VERSION}"
                    )
                self._validated_at = time.monotonic()
                return True
            except sqlite3.DatabaseError as exc:
                # Corrupt or schema-incompatible — rebuild once (bounded).
                self._recover_and_rebuild(f"index invalid ({exc})")
                return False

    def refresh_if_stale(self, *, force: bool = False) -> dict:
        """Rebuild the index when the source is demonstrably stale.

        Compares the source root's current run directories against the
        fingerprint stored at the last build/upsert.  A rebuild is triggered
        only when the fingerprint differs (new, modified, or removed run
        dirs), never on every request — the probe is rate-limited per
        process via ``STALE_CHECK_INTERVAL_S``.

        Returns ``{"rebuilt": bool, "reason": str, "record_count": int}``.
        Staleness rebuild failures are returned, not raised, so callers can
        keep serving the existing (stale but usable) index.
        """
        with self._ensure_lock:
            now = time.monotonic()
            if (not force and self._last_stale_check
                    and now - self._last_stale_check < STALE_CHECK_INTERVAL_S):
                return {
                    "rebuilt": False,
                    "reason": "rate_limited",
                    "record_count": -1,
                }
            self._last_stale_check = now
            try:
                probe = self._staleness_probe()
            except (OSError, sqlite3.Error) as exc:
                print(
                    f"[comfyui-modal.history-index] staleness probe failed: {exc}"
                )
                return {
                    "rebuilt": False,
                    "reason": f"probe_error: {exc}",
                    "record_count": -1,
                }
            if not probe["stale"]:
                return {"rebuilt": False, "reason": "fresh", "record_count": -1}
            try:
                count = self.rebuild()
                return {
                    "rebuilt": True,
                    "reason": probe["reason"],
                    "record_count": count,
                }
            except Exception as exc:
                print(
                    f"[comfyui-modal.history-index] stale rebuild failed: {exc}"
                )
                return {
                    "rebuilt": False,
                    "reason": f"rebuild_error: {exc}",
                    "record_count": -1,
                }

    # ── Recovery / staleness helpers ───────────────────────────────────

    def _recover_and_rebuild(self, reason: str) -> int:
        """Unlink a broken index and rebuild it from source (bounded).

        Returns the number of records indexed.  Raises ``sqlite3.Error`` if
        the database still cannot be recreated after
        ``MAX_ENSURE_ATTEMPTS`` (e.g. a foreign process holds a file lock on
        Windows).
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.MAX_ENSURE_ATTEMPTS + 1):
            try:
                self._close_all()
                self._unlink_db_files(self._db_path)
                self._schema_initialised = False
                count = self.rebuild()
                self._validated_at = time.monotonic()
                print(
                    f"[comfyui-modal.history-index] {reason}; rebuilt "
                    f"{count} records from source "
                    f"(attempt {attempt}/{self.MAX_ENSURE_ATTEMPTS})"
                )
                return count
            except (sqlite3.Error, OSError) as exc:
                last_exc = exc
                time.sleep(0.1 * attempt)
        raise sqlite3.OperationalError(
            "history index unrecoverable after "
            f"{self.MAX_ENSURE_ATTEMPTS} attempts: {last_exc}"
        )

    def _main_file_has_sqlite_header(self) -> bool:
        """True when the main DB file starts with the SQLite magic header."""
        try:
            with open(self._db_path, "rb") as f:
                return f.read(16) == b"SQLite format 3\x00"
        except OSError:
            return False

    def _staleness_probe(self) -> dict:
        """Cheap shallow scan of the source root to detect index staleness.

        Compares the current set of run directories (count + max dir mtime)
        against the fingerprint stored in ``index_meta`` at the last
        build/upsert.  A missing fingerprint (fresh, flat, or foreign
        schema) is treated as stale so incompletely-built indexes recover on
        the first request.
        """
        if not self._root.is_dir():
            return {
                "stale": False,
                "reason": "no_source",
                "count": 0,
                "max_mtime": 0.0,
            }

        cur_count = 0
        cur_max_mtime = 0.0
        for entry in self._root.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            cur_count += 1
            try:
                cur_max_mtime = max(cur_max_mtime, entry.stat().st_mtime)
            except OSError:
                pass

        if not self._db_path.exists():
            return {
                "stale": True,
                "reason": "index_missing",
                "count": cur_count,
                "max_mtime": cur_max_mtime,
            }

        conn = self._conn()
        stored_count = self._index_meta_int(conn, "source_dir_count", -1)
        stored_max = self._index_meta_float(conn, "source_max_mtime", -1.0)
        if stored_count < 0 or stored_max < 0:
            return {
                "stale": True,
                "reason": "fingerprint_missing",
                "count": cur_count,
                "max_mtime": cur_max_mtime,
            }
        if cur_count != stored_count:
            return {
                "stale": True,
                "reason": f"source dir count {stored_count} -> {cur_count}",
                "count": cur_count,
                "max_mtime": cur_max_mtime,
            }
        if cur_max_mtime > stored_max:
            return {
                "stale": True,
                "reason": "source run dirs updated since index build",
                "count": cur_count,
                "max_mtime": cur_max_mtime,
            }
        return {
            "stale": False,
            "reason": "fresh",
            "count": cur_count,
            "max_mtime": cur_max_mtime,
        }

    def _refresh_marked_stale(self, conn: sqlite3.Connection) -> None:
        """Refresh entries explicitly marked stale (``source_mtime = 0``).

        Bounded: only rows marked via ``mark_stale`` are re-read from the
        authoritative source; a query never rescans the whole source root.
        Rows whose source file is gone are removed from the index.
        """
        rows = conn.execute(
            "SELECT run_id, source_path FROM index_entries WHERE source_mtime = 0"
        ).fetchall()
        for row in rows:
            run_id = row["run_id"]
            source_path = row["source_path"]
            if source_path and os.path.isfile(source_path):
                try:
                    meta_obj = json.loads(
                        Path(source_path).read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    continue
                self.upsert_from_meta(meta_obj, source_path)
            else:
                self.remove(run_id)

    # ── index_meta helpers ─────────────────────────────────────────────

    def _read_index_meta(self, conn: sqlite3.Connection, key: str) -> Optional[str]:
        """Read a single index_meta value (None when absent/unreadable)."""
        try:
            row = conn.execute(
                "SELECT value FROM index_meta WHERE key = ?", (key,)
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
        return row[0] if row else None

    def _write_index_meta(self, conn: sqlite3.Connection, values: dict) -> None:
        """Upsert index_meta key/value pairs (caller owns the transaction)."""
        for key, value in values.items():
            conn.execute(
                "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
                (key, str(value)),
            )

    def _index_meta_int(self, conn: sqlite3.Connection, key: str, default: int) -> int:
        val = self._read_index_meta(conn, key)
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def _index_meta_float(self, conn: sqlite3.Connection, key: str, default: float) -> float:
        val = self._read_index_meta(conn, key)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _bump_index_meta(
        self,
        conn: sqlite3.Connection,
        *,
        added: bool = False,
        removed: bool = False,
        dir_mtime: float = 0.0,
    ) -> None:
        """Adjust the stored source fingerprint after an incremental write.

        Keeps ``source_dir_count`` / ``source_max_mtime`` in sync with the
        authoritative source so the staleness probe does not false-positive
        on plugin-owned writes.
        """
        count = self._index_meta_int(conn, "source_dir_count", 0)
        max_mtime = self._index_meta_float(conn, "source_max_mtime", 0.0)
        if added:
            count += 1
        if removed:
            count = max(0, count - 1)
        if dir_mtime and dir_mtime > max_mtime:
            max_mtime = dir_mtime
        self._write_index_meta(conn, {
            "source_dir_count": str(count),
            "source_max_mtime": repr(max_mtime),
        })

    @staticmethod
    def _source_dir_mtime(source_path: str) -> float:
        """Directory mtime of a run's meta.json (matches the staleness probe).

        Uses the *directory* mtime so plugin-owned writes stay consistent
        with the probe, which compares run-directory mtimes.
        """
        if not source_path:
            return 0.0
        try:
            return os.path.getmtime(os.path.dirname(source_path))
        except OSError:
            return 0.0

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
        d["output_saved"] = bool(d.get("output_saved", 0))
        return d
