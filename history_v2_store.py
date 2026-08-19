"""History V2 SQLite storage foundation.

Manages the ``history_v2.db`` database file plus the asset-root directory
convention.  Stdlib-only and importable standalone (no imports from any
other repo module).

Layout convention:
    <data_root>/.studio_history_v2/history_v2.db   # the database file
    <data_root>/.studio_assets/                    # managed asset files

``data_root()`` is derived as ``db_path.parent.parent``; callers should pass
``<data_root>/.studio_history_v2/history_v2.db`` as ``db_path``.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


DEFAULT_DATA_ROOT_ENV = "COMFYMODAL_LOCAL_DATA_DIR"


def default_data_root() -> Path:
    """Resolve the default local data root.

    Uses ``$COMFYMODAL_LOCAL_DATA_DIR`` when set, otherwise derives it from
    this file's location: the ComfyUI root (parent of the ``custom_nodes``
    directory) with ``comfymodal-data`` appended.
    """
    env = os.environ.get(DEFAULT_DATA_ROOT_ENV)
    if env:
        return Path(env)
    # <comfyui-root>/custom_nodes/comfyui-modal/history_v2_store.py
    # parents[0]=comfyui-modal, parents[1]=custom_nodes, parents[2]=ComfyUI root
    return Path(__file__).resolve().parents[2] / "comfymodal-data"


# ── Schema ────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiments (
  experiment_id TEXT PRIMARY KEY,
  name TEXT,
  definition_json TEXT NOT NULL DEFAULT '{}',
  cell_ordering_json TEXT NOT NULL DEFAULT '[]',
  expected_cell_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  favorite INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS experiment_cells (
  cell_id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  axis_labels_json TEXT NOT NULL DEFAULT '{}',
  generation_id TEXT REFERENCES generations(generation_id),
  attempt_ids_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  error TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiment_cells_experiment
  ON experiment_cells(experiment_id, position);

CREATE TABLE IF NOT EXISTS generations (
  generation_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  workflow_id TEXT,
  workflow_version_id TEXT,
  preset_id TEXT,
  preset_name TEXT,
  request_snapshot_id TEXT,
  experiment_id TEXT REFERENCES experiments(experiment_id),
  featured_asset_id TEXT REFERENCES assets(asset_id),
  favorite INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  prompt_text TEXT NOT NULL DEFAULT '',
  negative_prompt_text TEXT NOT NULL DEFAULT '',
  model_stack_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_generations_created
  ON generations(created_at DESC, generation_id DESC);
CREATE INDEX IF NOT EXISTS idx_generations_status ON generations(status);
CREATE INDEX IF NOT EXISTS idx_generations_workflow_id ON generations(workflow_id);
CREATE INDEX IF NOT EXISTS idx_generations_preset_id ON generations(preset_id);
CREATE INDEX IF NOT EXISTS idx_generations_favorite ON generations(favorite);
CREATE INDEX IF NOT EXISTS idx_generations_experiment_id ON generations(experiment_id);

CREATE TABLE IF NOT EXISTS run_attempts (
  run_id TEXT PRIMARY KEY,
  generation_id TEXT NOT NULL REFERENCES generations(generation_id) ON DELETE CASCADE,
  experiment_id TEXT REFERENCES experiments(experiment_id),
  cell_id TEXT REFERENCES experiment_cells(cell_id),
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  timing_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_attempts_generation
  ON run_attempts(generation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_run_attempts_status ON run_attempts(status);
CREATE INDEX IF NOT EXISTS idx_run_attempts_cell ON run_attempts(cell_id);

CREATE TABLE IF NOT EXISTS assets (
  asset_id TEXT PRIMARY KEY,
  generation_id TEXT NOT NULL REFERENCES generations(generation_id) ON DELETE CASCADE,
  run_id TEXT REFERENCES run_attempts(run_id),
  type TEXT NOT NULL,
  managed_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  format TEXT,
  sha256 TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  logical_output_key TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_generation_created
  ON assets(generation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_assets_generation_type ON assets(generation_id, type);

CREATE TABLE IF NOT EXISTS export_records (
  export_id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  destination_path TEXT,
  exported_at TEXT,
  state TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_export_records_asset
  ON export_records(asset_id, updated_at);

CREATE TABLE IF NOT EXISTS request_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  generation_id TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1,
  workflow_json TEXT NOT NULL,
  workflow_hash TEXT,
  workflow_version_id TEXT,
  generation_params_json TEXT NOT NULL DEFAULT '{}',
  preset_snapshot_json TEXT NOT NULL DEFAULT '{}',
  request_json TEXT NOT NULL DEFAULT '{}',
  execution_plan_json TEXT NOT NULL DEFAULT '{}',
  deployment_identity_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_request_snapshots_generation
  ON request_snapshots(generation_id);

CREATE TABLE IF NOT EXISTS legacy_mapping (
  legacy_run_id TEXT PRIMARY KEY,
  generation_id TEXT NOT NULL,
  source TEXT NOT NULL,
  migrated_at TEXT NOT NULL
);
"""


class HistoryV2Store:
    """Owns the History V2 SQLite database file and directory conventions."""

    SCHEMA_VERSION = 2

    def __init__(self, db_path: Path) -> None:
        # db_path is the .db FILE path; parent dirs are created in initialize().
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    # ── Lifecycle ──────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create dirs + schema.  Idempotent (safe to call repeatedly)."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.assets_root().mkdir(parents=True, exist_ok=True)
        conn = self.connect()
        try:
            conn.executescript(_SCHEMA_SQL)
            self._ensure_experiment_annotations(conn)
            self._ensure_request_snapshot_columns(conn)
            self._ensure_asset_logical_output_column(conn)
            conn.execute("PRAGMA user_version = %d" % self.SCHEMA_VERSION)
        finally:
            conn.close()

    def _ensure_experiment_annotations(self, conn: sqlite3.Connection) -> None:
        """Idempotently add experiment annotation columns to existing DBs.

        Fresh databases already carry the columns via the CREATE TABLE
        statement; pre-existing databases are upgraded in place.  Duplicate
        column errors are expected (column already exists) and pass silently.
        """
        for ddl in (
            "ALTER TABLE experiments ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE experiments ADD COLUMN note TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass

    def _ensure_request_snapshot_columns(self, conn: sqlite3.Connection) -> None:
        """Idempotently add immutable execution-snapshot columns to existing DBs.

        Fresh databases already carry the columns via the CREATE TABLE
        statement; pre-existing databases are upgraded in place.  The added
        columns are ``TEXT NOT NULL DEFAULT '{}'`` so old rows keep their
        values untouched and round-trip with the empty-dict defaults.
        Duplicate column errors are expected (column already exists) and pass
        silently.
        """
        for ddl in (
            "ALTER TABLE request_snapshots ADD COLUMN request_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE request_snapshots ADD COLUMN execution_plan_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE request_snapshots ADD COLUMN deployment_identity_json TEXT NOT NULL DEFAULT '{}'",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass

    def _ensure_asset_logical_output_column(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ALTER TABLE assets ADD COLUMN logical_output_key TEXT")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_generation_logical_output "
            "ON assets(generation_id, logical_output_key, created_at)"
        )

    # ── Connections ─────────────────────────────────────────────────────

    def connect(self) -> sqlite3.Connection:
        """Open a new connection with row factory and safe PRAGMAs."""
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """Run a statement on a fresh connection and return fetched rows."""
        conn = self.connect()
        try:
            return conn.execute(sql, tuple(params)).fetchall()
        finally:
            conn.close()

    def executescript(self, script: str) -> None:
        """Run a script (DDL) on a fresh connection."""
        conn = self.connect()
        try:
            conn.executescript(script)
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """``BEGIN IMMEDIATE`` transaction on one connection.

        Commits on success, rolls back on any exception.
        """
        conn = self.connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
        finally:
            conn.close()

    # ── Directory conventions ───────────────────────────────────────────

    def data_root(self) -> Path:
        """``db_path.parent.parent`` — the local data root."""
        return self._db_path.parent.parent

    def assets_root(self) -> Path:
        """Managed asset storage root: ``<data_root>/.studio_assets``."""
        return self.data_root() / ".studio_assets"
