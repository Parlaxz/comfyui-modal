"""History V2 repository: the typed persistence API over HistoryV2Store.

All methods return model dataclasses (from ``history_v2_models``).  Writes go
through ``store.transaction()``; read-only queries open one connection per
call.  Stdlib-only and importable standalone.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional, Sequence

from history_v2_models import (
    CLAIM_ALREADY_CLAIMED,
    CLAIM_CLAIMED,
    CLAIM_NOT_FOUND,
    CLAIM_TERMINAL,
    Asset,
    AssetType,
    CellStatus,
    ClaimResult,
    Experiment,
    ExperimentCell,
    ExperimentDetail,
    ExportRecord,
    ExportState,
    Generation,
    GenerationDetail,
    RequestSnapshot,
    RunAttempt,
    RunMode,
    RunStatus,
    TERMINAL_RUN_STATUSES,
    current_attempt,
    derive_cell_status,
    derive_experiment_status,
    derive_generation_status,
    logical_output_key_from_metadata,
    normalize_logical_output_key,
    new_id,
    utc_now_iso,
)
from history_v2_store import HistoryV2Store

_TERMINAL_RUN_STATUS_VALUES = frozenset(s.value for s in TERMINAL_RUN_STATUSES)

# Generate Original (E3B2) retry rejection reason when no failed Original
# Attempt is available to retry.
REASON_NOT_RETRYABLE = "not_a_failed_original"

# Single Resume (F1A) refusal reasons for ``create_single_resume_attempt``.
RESUME_REASON_EXPERIMENT_CELL = "experiment_cell_generation"
RESUME_REASON_NO_ATTEMPTS = "no_attempts"
RESUME_REASON_COMPLETED = "generation_completed"
RESUME_REASON_FAILED = "failed_requires_retry"
RESUME_REASON_CANCELED = "canceled_not_resumable"
RESUME_REASON_NOT_INTERRUPTED = "current_attempt_not_interrupted"


@dataclass(frozen=True)
class OriginalClaimOutcome:
    """Result of the transactional Generate-Original decision.

    ``outcome`` is one of ``created``, ``reused_active``,
    ``reused_successful``, ``retry_required``, ``busy`` or
    ``not_retryable``.  ``decision``/``reason`` carry the pure E3B1
    decision values; ``attempt`` is the relevant (new or existing)
    attempt; ``generation``/``snapshot`` are the loaded immutable records.
    """

    outcome: str
    attempt: Optional[RunAttempt]
    generation: Generation
    snapshot: Optional[RequestSnapshot]
    decision: str = ""
    reason: str = ""


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _escape_like(term: str) -> str:
    """Escape ``%``/``_``/``\\`` for a ``LIKE ... ESCAPE '\\'`` clause."""
    return (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _cursor_has_key(cursor: Optional[str]) -> bool:
    """True when a decoded cursor payload carries the ``"k"`` sort-key field.

    Cursors encoded before the six-order feature omit ``"k"``; those are
    "legacy" and fall back to oldest-style continuation under non-time orders.
    """
    if not cursor:
        return False
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        )
        return "k" in payload
    except Exception:
        return False


# The six advertised History V2 feed orders.
_ORDERS = ("newest", "oldest", "fastest", "slowest", "workflow_asc", "workflow_desc")

# Per-row duration (ms) computed DB-side as the max attempt wall-clock time.
# NULL when no attempt has both started_at and finished_at.
_GEN_DURATION_SQL = (
    "(SELECT MAX(CASE WHEN a.started_at IS NOT NULL AND a.finished_at IS NOT NULL "
    "THEN (julianday(a.finished_at) - julianday(a.started_at)) * 86400000.0 END) "
    "FROM run_attempts a WHERE a.generation_id = g.generation_id)"
)
_EXP_DURATION_SQL = (
    "(SELECT MAX(CASE WHEN a.started_at IS NOT NULL AND a.finished_at IS NOT NULL "
    "THEN (julianday(a.finished_at) - julianday(a.started_at)) * 86400000.0 END) "
    "FROM run_attempts a WHERE a.experiment_id = e.experiment_id)"
)


def _keyset_order(
    order: str,
    id_col: str,
    key_col: str,
    flag_sql: str,
    dur_col: str = "duration_ms",
) -> tuple[str, Any]:
    """Return ``(order_by, keyset_fn)`` for a History V2 sort order.

    ``keyset_fn(key, created_at, item_id)`` returns ``(predicate, params)``
    selecting rows strictly AFTER the cursor row in the total order.  Column
    references are unqualified and resolve against the outer query scope of the
    derived table ``SELECT * FROM (SELECT <t>.*, <duration> AS duration_ms ...
    )``.

    Total orders (tie-breaks always end ``created_at ASC, <id> ASC``):
      newest       → created_at DESC, id DESC
      oldest       → created_at ASC, id ASC
      fastest      → (duration IS NULL) ASC, duration ASC, ...
      slowest      → (duration IS NULL) ASC, duration DESC, ...
      workflow_asc → missing-flag ASC, key COLLATE NOCASE ASC, ...
      workflow_desc→ missing-flag ASC, key COLLATE NOCASE DESC, ...
    """
    if order == "newest":
        return (
            f"created_at DESC, {id_col} DESC",
            lambda key, ca, cid: (f"(created_at, {id_col}) < (?, ?)", [ca, cid]),
        )
    if order == "oldest":
        return (
            f"created_at ASC, {id_col} ASC",
            lambda key, ca, cid: (f"(created_at, {id_col}) > (?, ?)", [ca, cid]),
        )
    if order in ("fastest", "slowest"):
        direction = "ASC" if order == "fastest" else "DESC"
        op = ">" if order == "fastest" else "<"
        order_by = (
            f"({dur_col} IS NULL) ASC, {dur_col} {direction}, "
            f"created_at ASC, {id_col} ASC"
        )

        def keyset(key, ca, cid):
            kn = 1 if key is None else 0
            kd = 0.0 if key is None else key
            return (
                f"({dur_col} IS NULL) > ? "
                f"OR (({dur_col} IS NULL) = ? AND COALESCE({dur_col}, 0) {op} ?) "
                f"OR (({dur_col} IS NULL) = ? AND COALESCE({dur_col}, 0) = ? "
                f"AND created_at > ?) "
                f"OR (({dur_col} IS NULL) = ? AND COALESCE({dur_col}, 0) = ? "
                f"AND created_at = ? AND {id_col} > ?)",
                [kn, kn, kd, kn, kd, ca, kn, kd, ca, cid],
            )

        return order_by, keyset
    if order in ("workflow_asc", "workflow_desc"):
        collation = "ASC" if order == "workflow_asc" else "DESC"
        op = ">" if order == "workflow_asc" else "<"
        order_by = (
            f"{flag_sql} ASC, {key_col} COLLATE NOCASE {collation}, "
            f"created_at ASC, {id_col} ASC"
        )

        def keyset(key, ca, cid):
            kf = 1 if (key is None or key == "") else 0
            kk = key if key is not None else ""
            return (
                f"{flag_sql} > ? "
                f"OR ({flag_sql} = ? AND {key_col} COLLATE NOCASE {op} ?) "
                f"OR ({flag_sql} = ? AND {key_col} COLLATE NOCASE = ? "
                f"AND created_at > ?) "
                f"OR ({flag_sql} = ? AND {key_col} COLLATE NOCASE = ? "
                f"AND created_at = ? AND {id_col} > ?)",
                [kf, kf, kk, kf, kk, ca, kf, kk, ca, cid],
            )

        return order_by, keyset
    raise ValueError(
        "order must be one of 'newest', 'oldest', 'fastest', 'slowest', "
        "'workflow_asc', 'workflow_desc'"
    )


class HistoryV2Repository:
    """Typed CRUD + query API over the History V2 SQLite schema."""

    def __init__(
        self,
        store: HistoryV2Store,
        *,
        experiment_id: Optional[str] = None,
    ) -> None:
        self._store = store
        # Optional experiment scope for the modern (D3) scheduler persistence
        # adapter methods that take no experiment argument (load_queued_cells,
        # list_recoverable_cells, aggregate_status).  Cell-scoped operations
        # resolve the experiment from the cell row itself.
        self.experiment_id = experiment_id
        self._store.initialize()

    # ── Row → model conversions ─────────────────────────────────────────

    @staticmethod
    def _parse_json(value: Optional[str], default: Any) -> Any:
        if value is None:
            return default
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default

    def _row_to_generation(self, row: sqlite3.Row) -> Generation:
        return Generation(
            generation_id=row["generation_id"],
            created_at=row["created_at"],
            status=row["status"],
            workflow_id=row["workflow_id"],
            workflow_version_id=row["workflow_version_id"],
            preset_id=row["preset_id"],
            preset_name=row["preset_name"],
            request_snapshot_id=row["request_snapshot_id"],
            experiment_id=row["experiment_id"],
            featured_asset_id=row["featured_asset_id"],
            favorite=bool(row["favorite"]),
            note=row["note"],
            prompt_text=row["prompt_text"],
            negative_prompt_text=row["negative_prompt_text"],
            model_stack=self._parse_json(row["model_stack_json"], []),
            updated_at=row["updated_at"],
        )

    def _row_to_attempt(self, row: sqlite3.Row) -> RunAttempt:
        return RunAttempt(
            run_id=row["run_id"],
            generation_id=row["generation_id"],
            mode=row["mode"],
            status=row["status"],
            created_at=row["created_at"],
            experiment_id=row["experiment_id"],
            cell_id=row["cell_id"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error=row["error"],
            timing=self._parse_json(row["timing_json"], {}),
        )

    def _row_to_asset(self, row: sqlite3.Row) -> Asset:
        return Asset(
            asset_id=row["asset_id"],
            generation_id=row["generation_id"],
            type=row["type"],
            managed_path=row["managed_path"],
            filename=row["filename"],
            created_at=row["created_at"],
            run_id=row["run_id"],
            width=row["width"],
            height=row["height"],
            format=row["format"],
            sha256=row["sha256"],
            metadata=self._parse_json(row["metadata_json"], {}),
            logical_output_key=(
                row["logical_output_key"]
                if "logical_output_key" in row.keys()
                else None
            ),
        )

    def _row_to_export(self, row: sqlite3.Row) -> ExportRecord:
        return ExportRecord(
            export_id=row["export_id"],
            asset_id=row["asset_id"],
            state=row["state"],
            updated_at=row["updated_at"],
            destination_path=row["destination_path"],
            exported_at=row["exported_at"],
        )

    def _row_to_experiment(self, row: sqlite3.Row) -> Experiment:
        return Experiment(
            experiment_id=row["experiment_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            name=row["name"],
            definition=self._parse_json(row["definition_json"], {}),
            cell_ordering=self._parse_json(row["cell_ordering_json"], []),
            expected_cell_count=row["expected_cell_count"],
            favorite=bool(row["favorite"]) if "favorite" in row.keys() else False,
            note=row["note"] if "note" in row.keys() else "",
        )

    def _row_to_cell(self, row: sqlite3.Row) -> ExperimentCell:
        return ExperimentCell(
            cell_id=row["cell_id"],
            experiment_id=row["experiment_id"],
            position=row["position"],
            status=row["status"],
            updated_at=row["updated_at"],
            axis_labels=self._parse_json(row["axis_labels_json"], {}),
            generation_id=row["generation_id"],
            attempt_ids=self._parse_json(row["attempt_ids_json"], []),
            error=row["error"],
        )

    def _row_to_snapshot(self, row: sqlite3.Row) -> RequestSnapshot:
        return RequestSnapshot(
            snapshot_id=row["snapshot_id"],
            created_at=row["created_at"],
            workflow=self._parse_json(row["workflow_json"], {}),
            generation_id=row["generation_id"],
            schema_version=row["schema_version"],
            workflow_hash=row["workflow_hash"],
            workflow_version_id=row["workflow_version_id"],
            generation_params=self._parse_json(row["generation_params_json"], {}),
            preset_snapshot=self._parse_json(row["preset_snapshot_json"], {}),
            request=self._parse_json(
                row["request_json"] if "request_json" in row.keys() else None, {}
            ),
            execution_plan=self._parse_json(
                row["execution_plan_json"] if "execution_plan_json" in row.keys() else None,
                {},
            ),
            deployment_identity=self._parse_json(
                row["deployment_identity_json"]
                if "deployment_identity_json" in row.keys()
                else None,
                {},
            ),
        )

    # ── Internal attempt/cell helpers (caller owns the connection) ──────

    def _attempts_for_generation(
        self, conn: sqlite3.Connection, generation_id: str
    ) -> list[RunAttempt]:
        rows = conn.execute(
            "SELECT * FROM run_attempts WHERE generation_id = ? "
            "ORDER BY created_at ASC",
            (generation_id,),
        ).fetchall()
        return [self._row_to_attempt(r) for r in rows]

    def _attempts_for_cell(self, conn: sqlite3.Connection, cell_id: str) -> list[RunAttempt]:
        rows = conn.execute(
            "SELECT * FROM run_attempts WHERE cell_id = ? ORDER BY created_at ASC",
            (cell_id,),
        ).fetchall()
        return [self._row_to_attempt(r) for r in rows]

    def _derive_experiment_status(
        self, conn: sqlite3.Connection, experiment_id: str
    ) -> None:
        """Recompute + persist an experiment's aggregate status from its cells.

        Loads every cell of the experiment (position order), applies the pure
        ``derive_experiment_status`` rules, and persists the result with a
        fresh ``updated_at``.  No-op when the experiment row is missing.
        ``failed`` is never produced here — it is an explicit fatal state only
        settable via ``set_experiment_status``.
        """
        exp = conn.execute(
            "SELECT experiment_id FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if exp is None:
            return
        rows = conn.execute(
            "SELECT * FROM experiment_cells WHERE experiment_id = ? "
            "ORDER BY position ASC",
            (experiment_id,),
        ).fetchall()
        cells = [self._row_to_cell(r) for r in rows]
        status = derive_experiment_status(cells)
        conn.execute(
            "UPDATE experiments SET status = ?, updated_at = ? "
            "WHERE experiment_id = ?",
            (status, utc_now_iso(), experiment_id),
        )

    def _recompute_generation(
        self, conn: sqlite3.Connection, generation_id: str, now: str
    ) -> None:
        """Recompute + persist a generation's derived status from its attempts."""
        attempts = self._attempts_for_generation(conn, generation_id)
        status = derive_generation_status(attempts)
        conn.execute(
            "UPDATE generations SET status = ?, updated_at = ? "
            "WHERE generation_id = ?",
            (status, now, generation_id),
        )

    def _recompute_cell(self, conn: sqlite3.Connection, cell_id: str, now: str) -> None:
        """Recompute + persist a cell's derived status/error from its attempts.

        The CURRENT (latest) attempt is authoritative: a stale older attempt
        can never overwrite a newer in-flight (queued/running) Retry/Resume
        state.  The cell error mirrors the current attempt's error (None when
        the current attempt is not terminal or carries no error).  The
        containing experiment's aggregate status is recomputed afterwards.
        """
        attempts = self._attempts_for_cell(conn, cell_id)
        current = current_attempt(attempts)
        status = derive_cell_status(attempts)
        error = current.error if current is not None else None
        conn.execute(
            "UPDATE experiment_cells SET status = ?, error = ?, updated_at = ? "
            "WHERE cell_id = ?",
            (status, error, now, cell_id),
        )
        cell_row = conn.execute(
            "SELECT experiment_id FROM experiment_cells WHERE cell_id = ?",
            (cell_id,),
        ).fetchone()
        if cell_row is not None:
            self._derive_experiment_status(conn, cell_row["experiment_id"])

    # ── Generations ─────────────────────────────────────────────────────

    def create_generation(
        self,
        *,
        generation_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_version_id: Optional[str] = None,
        preset_id: Optional[str] = None,
        preset_name: Optional[str] = None,
        request_snapshot_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        prompt_text: str = "",
        negative_prompt_text: str = "",
        model_stack: Optional[list[dict[str, Any]]] = None,
        favorite: bool = False,
        note: str = "",
        created_at: Optional[str] = None,
    ) -> Generation:
        generation_id = generation_id if generation_id is not None else new_id("gen_")
        now = created_at or utc_now_iso()
        stack = [dict(m) for m in (model_stack or []) if isinstance(m, dict)]
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO generations (
                    generation_id, created_at, workflow_id, workflow_version_id,
                    preset_id, preset_name, request_snapshot_id, experiment_id,
                    featured_asset_id, favorite, note, status, prompt_text,
                    negative_prompt_text, model_stack_json, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    generation_id, now, workflow_id, workflow_version_id,
                    preset_id, preset_name, request_snapshot_id, experiment_id,
                    None, int(bool(favorite)), note, "pending", prompt_text,
                    negative_prompt_text, _compact_json(stack), now,
                ),
            )
        return Generation(
            generation_id=generation_id,
            created_at=now,
            status="pending",
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            preset_id=preset_id,
            preset_name=preset_name,
            request_snapshot_id=request_snapshot_id,
            experiment_id=experiment_id,
            featured_asset_id=None,
            favorite=bool(favorite),
            note=note,
            prompt_text=prompt_text,
            negative_prompt_text=negative_prompt_text,
            model_stack=stack,
            updated_at=now,
        )

    def get_generation(self, generation_id: str) -> Optional[GenerationDetail]:
        """Full detail: generation + attempts + assets + exports + snapshot."""
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM generations WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            if row is None:
                return None
            generation = self._row_to_generation(row)
            attempts = [
                self._row_to_attempt(r)
                for r in conn.execute(
                    "SELECT * FROM run_attempts WHERE generation_id = ? "
                    "ORDER BY created_at ASC",
                    (generation_id,),
                ).fetchall()
            ]
            assets = [
                self._row_to_asset(r)
                for r in conn.execute(
                    "SELECT * FROM assets WHERE generation_id = ? "
                    "ORDER BY created_at ASC",
                    (generation_id,),
                ).fetchall()
            ]
            export_records: list[ExportRecord] = []
            if assets:
                asset_ids = tuple(a.asset_id for a in assets)
                placeholders = ",".join("?" * len(asset_ids))
                export_records = [
                    self._row_to_export(r)
                    for r in conn.execute(
                        f"SELECT * FROM export_records WHERE asset_id IN ({placeholders}) "
                        "ORDER BY updated_at ASC",
                        asset_ids,
                    ).fetchall()
                ]
            request_snapshot: Optional[RequestSnapshot] = None
            if generation.request_snapshot_id:
                srow = conn.execute(
                    "SELECT * FROM request_snapshots WHERE snapshot_id = ?",
                    (generation.request_snapshot_id,),
                ).fetchone()
                if srow is not None:
                    request_snapshot = self._row_to_snapshot(srow)
            return GenerationDetail(
                generation=generation,
                attempts=attempts,
                assets=assets,
                export_records=export_records,
                request_snapshot=request_snapshot,
            )
        finally:
            conn.close()

    get_generation_detail = get_generation  # alias for UI-agent convenience

    def add_attempt(
        self,
        generation_id: str,
        *,
        run_id: Optional[str] = None,
        mode: str = "preview",
        experiment_id: Optional[str] = None,
        cell_id: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> RunAttempt:
        run_id = run_id if run_id is not None else new_id("run_")
        now = utc_now_iso()
        started = started_at or now
        mode_value = RunMode(mode).value
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO run_attempts (
                    run_id, generation_id, experiment_id, cell_id, mode, status,
                    started_at, finished_at, error, timing_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, generation_id, experiment_id, cell_id, mode_value,
                 RunStatus.QUEUED.value, started, None, None, "{}", now),
            )
            # Recompute the generation's derived status (a queued attempt makes
            # the generation "running-ish" per derive_generation_status).
            self._recompute_generation(conn, generation_id, now)
            # A cell-affecting queued retry/replay must surface immediately
            # (current-attempt derivation: a stale terminal attempt can never
            # mask a newer in-flight Retry/Resume state).
            if cell_id:
                self._recompute_cell(conn, cell_id, now)
        return RunAttempt(
            run_id=run_id,
            generation_id=generation_id,
            mode=mode_value,
            status=RunStatus.QUEUED.value,
            created_at=now,
            experiment_id=experiment_id,
            cell_id=cell_id,
            started_at=started,
            finished_at=None,
            error=None,
            timing={},
        )

    def update_attempt_terminal(
        self,
        run_id: str,
        *,
        status: str,
        error: Optional[str] = None,
        finished_at: Optional[str] = None,
        timing: Optional[dict[str, Any]] = None,
    ) -> Optional[RunAttempt]:
        """Persist a terminal attempt status and recompute derived states."""
        run_status = RunStatus(status)  # raises ValueError on unknown status
        if run_status not in TERMINAL_RUN_STATUSES:
            raise ValueError(
                f"status {status!r} is not a terminal RunStatus; "
                f"terminal statuses: {sorted(s.value for s in TERMINAL_RUN_STATUSES)}"
            )
        finished = finished_at or utc_now_iso()
        return self._update_attempt(
            run_id,
            status=run_status.value,
            error=error,
            finished_at=finished,
            timing=timing,
        )

    def update_attempt_status(
        self,
        run_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        finished_at: Optional[str] = None,
        timing: Optional[dict[str, Any]] = None,
    ) -> Optional[RunAttempt]:
        """Persist an attempt status (terminal OR non-terminal) and recompute
        derived generation/cell/experiment state.

        Behaves exactly like ``update_attempt_terminal`` for terminal statuses
        (``finished_at`` defaults to now).  Non-terminal statuses (e.g.
        ``"running"``) leave ``finished_at`` untouched.
        """
        run_status = RunStatus(status)  # raises ValueError on unknown status
        if run_status in TERMINAL_RUN_STATUSES:
            finished = finished_at or utc_now_iso()
        else:
            finished = finished_at
        return self._update_attempt(
            run_id,
            status=run_status.value,
            error=error,
            finished_at=finished,
            timing=timing,
        )

    def _update_attempt(
        self,
        run_id: str,
        *,
        status: str,
        error: Optional[str] = None,
        finished_at: Optional[str] = None,
        timing: Optional[dict[str, Any]] = None,
    ) -> Optional[RunAttempt]:
        """Shared status-application + derived-state recomputation core.

        Single source of truth for updating a ``run_attempts`` row and then
        recomputing the derived statuses of its generation (and, for cell
        attempts, its cell and experiment).  Used by both
        ``update_attempt_terminal`` and ``update_attempt_status``.

        Hardened: the UPDATE carries a SQL predicate so a terminal attempt is
        never reopened or overwritten and a ``"running"`` update can never
        reopen a terminal attempt.  The returned attempt reflects the
        ACTUALLY stored row — a requested value that lost a race is never
        reported as stored.
        """
        now = utc_now_iso()
        timing_dict = dict(timing or {})
        terminal_values = tuple(sorted(_TERMINAL_RUN_STATUS_VALUES))
        placeholders = ",".join("?" * len(terminal_values))
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            generation_id = row["generation_id"]
            cell_id = row["cell_id"]
            conn.execute(
                f"""UPDATE run_attempts
                    SET status = ?, finished_at = ?, error = ?, timing_json = ?
                    WHERE run_id = ? AND status NOT IN ({placeholders})""",
                (status, finished_at, error, _compact_json(timing_dict), run_id)
                + terminal_values,
            )
            stored = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            self._recompute_generation(conn, generation_id, now)
            if cell_id:
                self._recompute_cell(conn, cell_id, now)
        return self._row_to_attempt(stored)

    def get_attempt(self, run_id: str) -> Optional[RunAttempt]:
        """Look up a single run attempt by id, or None if unknown."""
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            return self._row_to_attempt(row) if row is not None else None
        finally:
            conn.close()

    def claim_attempt(
        self, run_id: str, *, claimed_at: Optional[str] = None
    ) -> ClaimResult:
        """Atomically claim a queued attempt as running (compare-and-swap).

        Non-throwing: the returned ``ClaimResult.outcome`` distinguishes
        ``CLAIM_CLAIMED`` (this call performed the queued → running
        transition), ``CLAIM_ALREADY_CLAIMED`` (the attempt is currently
        running under another worker), ``CLAIM_TERMINAL`` (a terminal attempt
        can never be reopened) and ``CLAIM_NOT_FOUND`` (unknown run id).
        ``started_at`` is set only on a successful claim — queued attempts
        stay un-started.  Derived generation/cell/experiment states are
        recomputed inside the same transaction.
        """
        now = claimed_at or utc_now_iso()
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return ClaimResult(outcome=CLAIM_NOT_FOUND, attempt=None)
            if row["status"] != RunStatus.QUEUED.value:
                outcome = (
                    CLAIM_TERMINAL
                    if row["status"] in _TERMINAL_RUN_STATUS_VALUES
                    else CLAIM_ALREADY_CLAIMED
                )
                return ClaimResult(outcome=outcome, attempt=self._row_to_attempt(row))
            conn.execute(
                """UPDATE run_attempts
                   SET status = ?, started_at = ?
                   WHERE run_id = ? AND status = ?""",
                (RunStatus.RUNNING.value, now, run_id, RunStatus.QUEUED.value),
            )
            stored = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            self._recompute_generation(conn, row["generation_id"], now)
            if row["cell_id"]:
                self._recompute_cell(conn, row["cell_id"], now)
            return ClaimResult(
                outcome=CLAIM_CLAIMED, attempt=self._row_to_attempt(stored)
            )

    def cancel_queued_attempt(
        self,
        run_id: str,
        *,
        error: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> Optional[RunAttempt]:
        """Atomically terminal-cancel a queued attempt (queued → canceled).

        Non-throwing: an attempt that is not queued (running or terminal) is
        left untouched and returned as the currently stored row; unknown run
        ids return None.  Derived generation/cell/experiment states are
        recomputed inside the same transaction.
        """
        now = finished_at or utc_now_iso()
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            if row["status"] != RunStatus.QUEUED.value:
                return self._row_to_attempt(row)
            conn.execute(
                """UPDATE run_attempts
                   SET status = ?, finished_at = ?, error = ?
                   WHERE run_id = ? AND status = ?""",
                (RunStatus.CANCELED.value, now, error, run_id, RunStatus.QUEUED.value),
            )
            stored = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            self._recompute_generation(conn, row["generation_id"], now)
            if row["cell_id"]:
                self._recompute_cell(conn, row["cell_id"], now)
            return self._row_to_attempt(stored)

    def add_cell_attempt(
        self,
        cell_id: str,
        *,
        generation_id: str,
        run_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        mode: str = "original",
        created_at: Optional[str] = None,
    ) -> RunAttempt:
        """Create a new queued retry/resume attempt for a cell's generation.

        The new attempt reuses the cell's existing generation — and therefore
        its immutable request snapshot — so it retries the SAME immutable
        request.  ``started_at`` stays unset until the attempt is claimed.
        Raises ``ValueError`` for an unknown cell/generation or when the cell
        is already linked to a different generation.  The cell's attempt_ids
        list and derived generation/cell/experiment states are updated in the
        same transaction.
        """
        run_id = run_id if run_id is not None else new_id("run_")
        now = created_at or utc_now_iso()
        mode_value = RunMode(mode).value
        with self._store.transaction() as conn:
            cell = conn.execute(
                "SELECT * FROM experiment_cells WHERE cell_id = ?", (cell_id,)
            ).fetchone()
            if cell is None:
                raise ValueError(f"unknown experiment cell: {cell_id}")
            if cell["generation_id"] and cell["generation_id"] != generation_id:
                raise ValueError(
                    f"cell {cell_id} is linked to generation "
                    f"{cell['generation_id']}, not {generation_id}"
                )
            gen = conn.execute(
                "SELECT 1 FROM generations WHERE generation_id = ?", (generation_id,)
            ).fetchone()
            if gen is None:
                raise ValueError(f"unknown generation: {generation_id}")
            exp_id = experiment_id or cell["experiment_id"]
            conn.execute(
                """INSERT INTO run_attempts (
                    run_id, generation_id, experiment_id, cell_id, mode, status,
                    started_at, finished_at, error, timing_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, generation_id, exp_id, cell_id, mode_value,
                 RunStatus.QUEUED.value, None, None, None, "{}", now),
            )
            attempt_ids = list(self._parse_json(cell["attempt_ids_json"], []))
            if run_id not in attempt_ids:
                attempt_ids.append(run_id)
            conn.execute(
                """UPDATE experiment_cells
                   SET generation_id = ?, attempt_ids_json = ?, updated_at = ?
                   WHERE cell_id = ?""",
                (generation_id, _compact_json(attempt_ids), now, cell_id),
            )
            self._recompute_generation(conn, generation_id, now)
            self._recompute_cell(conn, cell_id, now)
        return RunAttempt(
            run_id=run_id,
            generation_id=generation_id,
            mode=mode_value,
            status=RunStatus.QUEUED.value,
            created_at=now,
            experiment_id=exp_id,
            cell_id=cell_id,
            started_at=None,
            finished_at=None,
            error=None,
            timing={},
        )

    def list_stale_running_attempts(
        self,
        *,
        cell_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        started_before: Optional[str] = None,
        limit: int = 100,
    ) -> list[RunAttempt]:
        """List ``"running"`` attempts, oldest-start first.

        ``started_before`` restricts the list to attempts started strictly
        before the cutoff (the stale ones a reconciler should revisit);
        ``cell_id``/``experiment_id`` optionally narrow the scope.
        """
        where = ["status = ?"]
        params: list[Any] = [RunStatus.RUNNING.value]
        if cell_id is not None:
            where.append("cell_id = ?")
            params.append(cell_id)
        if experiment_id is not None:
            where.append("experiment_id = ?")
            params.append(experiment_id)
        if started_before is not None:
            where.append("started_at < ?")
            params.append(started_before)
        conn = self._store.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM run_attempts WHERE {' AND '.join(where)} "
                "ORDER BY started_at ASC LIMIT ?",
                params + [int(limit)],
            ).fetchall()
            return [self._row_to_attempt(r) for r in rows]
        finally:
            conn.close()

    def get_current_cell_attempt(self, cell_id: str) -> Optional[RunAttempt]:
        """Return the cell's CURRENT (latest) attempt, or None when it has none."""
        conn = self._store.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM run_attempts WHERE cell_id = ? ORDER BY created_at ASC",
                (cell_id,),
            ).fetchall()
            return current_attempt([self._row_to_attempt(r) for r in rows])
        finally:
            conn.close()

    def attach_asset(
        self,
        generation_id: str,
        *,
        run_id: Optional[str] = None,
        asset_type: str,
        source_path: Optional[str] = None,
        data: Optional[bytes] = None,
        filename: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fmt: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        sha256: Optional[str] = None,
        copy: bool = True,
        created_at: Optional[str] = None,
        logical_output_key: Optional[str] = None,
    ) -> Asset:
        if (source_path is None) == (data is None):
            raise ValueError("exactly one of source_path/data is required")
        asset_type_value = AssetType(asset_type).value
        asset_id = new_id("ast_")
        now = created_at or utc_now_iso()

        if data is None:
            if source_path is None:
                raise ValueError("source_path required when data is not provided")
            src_path = Path(source_path)
            payload = src_path.read_bytes()
        else:
            src_path = Path(source_path) if source_path else None
            payload = bytes(data)

        digest = sha256 or hashlib.sha256(payload).hexdigest()

        ext = ""
        if fmt in ("png", "jpg", "jpeg", "webp"):
            ext = fmt if fmt != "jpeg" else "jpg"
        elif src_path is not None:
            ext = src_path.suffix.lstrip(".") or "bin"
        else:
            ext = "bin"

        if copy:
            out_name = filename or (src_path.name if src_path is not None else f"{asset_id}.{ext}")
            out_dir = self._store.assets_root() / generation_id
            out_dir.mkdir(parents=True, exist_ok=True)
            managed_path = out_dir / f"{asset_id}.{ext}"
            tmp_path = managed_path.with_suffix(managed_path.suffix + ".tmp")
            with open(tmp_path, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, managed_path)
            managed_path_str = str(managed_path)
        else:
            if src_path is None:
                raise ValueError("copy=False requires source_path")
            managed_path_str = str(src_path.resolve())
            out_name = filename or src_path.name

        metadata_dict = dict(metadata or {})
        logical_key = normalize_logical_output_key(logical_output_key)
        if logical_key is None:
            logical_key = logical_output_key_from_metadata(metadata_dict)
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO assets (
                    asset_id, generation_id, run_id, type, managed_path, filename,
                    width, height, format, sha256, metadata_json,
                    logical_output_key, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (asset_id, generation_id, run_id, asset_type_value, managed_path_str,
                 out_name, width, height, fmt or (ext or None), digest,
                 _compact_json(metadata_dict), logical_key, now),
            )
        return Asset(
            asset_id=asset_id,
            generation_id=generation_id,
            type=asset_type_value,
            managed_path=managed_path_str,
            filename=out_name,
            created_at=now,
            run_id=run_id,
            width=width,
            height=height,
            format=fmt or (ext or None),
            sha256=digest,
            metadata=metadata_dict,
            logical_output_key=logical_key,
        )

    def adopt_asset(
        self,
        generation_id: str,
        *,
        run_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        source_path: Optional[str] = None,
        reference: Optional[str] = None,
        filename: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fmt: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        sha256: Optional[str] = None,
        created_at: Optional[str] = None,
        logical_output_key: Optional[str] = None,
    ) -> Optional[Asset]:
        """Insert a managed reference / adopted original asset.

        Narrow managed-reference analogue of ``attach_asset`` (same assets
        table/FK/route contract as the migration's ``copy=False`` use): the
        bytes are never copied or re-encoded.  ``reference`` (a remote
        ``modal://`` origin string) is stored verbatim as ``managed_path``;
        ``source_path`` is stored as a resolved local path reference.  The
        digest comes from *sha256* (the producer ``content_hash``) for remote
        references and is computed from the local file only when *sha256* is
        omitted — bytes are never fabricated.

        Idempotent within a generation: an *asset_id* already present in the
        same generation returns None (no row is written).  Because a producer
        ``primary_asset_id`` is content-addressed and may recur across
        generations, an *asset_id* owned by ANOTHER generation mints a fresh
        History-local ``ast_*`` id instead (the producer identity is retained
        in ``metadata["producer_asset_id"]``) so a valid descriptor-only run
        never completes with zero History assets.
        """
        if (source_path is None) == (reference is None):
            raise ValueError("exactly one of source_path/reference is required")
        asset_type_value = AssetType("original").value

        if reference is not None:
            managed_path_str = str(reference)
            try:
                out_name = (
                    filename
                    or Path(str(reference).split("|", 2)[-1]).name
                    or "asset"
                )
            except Exception:
                out_name = filename or "asset"
            ext = ""
            if not sha256:
                sha256 = None
        else:
            if source_path is None:
                raise ValueError("source_path required when reference is not provided")
            src_path = Path(source_path)
            managed_path_str = str(src_path.resolve())
            out_name = filename or src_path.name
            ext = src_path.suffix.lstrip(".").lower()
            if not sha256:
                try:
                    sha256 = hashlib.sha256(src_path.read_bytes()).hexdigest()
                except OSError:
                    sha256 = None

        if asset_id:
            existing = self.get_asset(asset_id)
            if existing is not None:
                if existing.generation_id == generation_id:
                    return None  # same generation: idempotent duplicate
                # Content-addressed producer id already owned by another
                # generation: mint a fresh History-local id and retain the
                # producer identity in the metadata.
                resolved_id = new_id("ast_")
                metadata = dict(metadata or {})
                metadata.setdefault("producer_asset_id", asset_id)
            else:
                resolved_id = asset_id
        else:
            resolved_id = new_id("ast_")
        now = created_at or utc_now_iso()
        metadata_dict = dict(metadata or {})
        logical_key = normalize_logical_output_key(logical_output_key)
        if logical_key is None:
            logical_key = logical_output_key_from_metadata(metadata_dict)
        try:
            with self._store.transaction() as conn:
                conn.execute(
                    """INSERT INTO assets (
                        asset_id, generation_id, run_id, type, managed_path, filename,
                        width, height, format, sha256, metadata_json,
                        logical_output_key, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (resolved_id, generation_id, run_id, asset_type_value,
                     managed_path_str, out_name, width, height, fmt or (ext or None),
                     sha256, _compact_json(metadata_dict), logical_key, now),
                )
        except sqlite3.IntegrityError:
            return None  # concurrent duplicate identity; rejected
        return Asset(
            asset_id=resolved_id,
            generation_id=generation_id,
            type=asset_type_value,
            managed_path=managed_path_str,
            filename=out_name,
            created_at=now,
            run_id=run_id,
            width=width,
            height=height,
            format=fmt or (ext or None),
            sha256=sha256,
            metadata=metadata_dict,
            logical_output_key=logical_key,
        )

    def set_featured_asset(self, generation_id: str, asset_id: str) -> bool:
        """Set the featured asset, verifying it belongs to the generation."""
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT 1 FROM assets WHERE asset_id = ? AND generation_id = ?",
                (asset_id, generation_id),
            ).fetchone()
            if row is None:
                return False
            cur = conn.execute(
                "UPDATE generations SET featured_asset_id = ? WHERE generation_id = ?",
                (asset_id, generation_id),
            )
            return cur.rowcount > 0

    def set_favorite(self, generation_id: str, favorite: bool) -> bool:
        with self._store.transaction() as conn:
            cur = conn.execute(
                "UPDATE generations SET favorite = ?, updated_at = ? "
                "WHERE generation_id = ?",
                (int(bool(favorite)), utc_now_iso(), generation_id),
            )
            return cur.rowcount > 0

    def set_note(self, generation_id: str, note: str) -> bool:
        if len(note) > 2000:
            raise ValueError("note exceeds 2000 characters (legacy limit)")
        with self._store.transaction() as conn:
            cur = conn.execute(
                "UPDATE generations SET note = ?, updated_at = ? "
                "WHERE generation_id = ?",
                (note, utc_now_iso(), generation_id),
            )
            return cur.rowcount > 0

    def get_generation_assets(
        self, generation_id: str, *, asset_type: Optional[str] = None
    ) -> list[Asset]:
        conn = self._store.connect()
        try:
            if asset_type is None:
                rows = conn.execute(
                    "SELECT * FROM assets WHERE generation_id = ? "
                    "ORDER BY created_at ASC",
                    (generation_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM assets WHERE generation_id = ? AND type = ? "
                    "ORDER BY created_at ASC",
                    (generation_id, AssetType(asset_type).value),
                ).fetchall()
            return [self._row_to_asset(r) for r in rows]
        finally:
            conn.close()

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        """Look up a single asset by id, or None if unknown."""
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return self._row_to_asset(row) if row is not None else None
        finally:
            conn.close()

    def get_assets_for_generations(
        self, generation_ids: Sequence[str]
    ) -> list[Asset]:
        """Batch asset lookup for feed enrichment (created_at order)."""
        if not generation_ids:
            return []
        ids = list(dict.fromkeys(generation_ids))
        placeholders = ",".join("?" * len(ids))
        conn = self._store.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM assets WHERE generation_id IN ({placeholders}) "
                "ORDER BY created_at ASC",
                ids,
            ).fetchall()
            return [self._row_to_asset(r) for r in rows]
        finally:
            conn.close()

    def get_attempts_for_generations(
        self, generation_ids: Sequence[str]
    ) -> list[RunAttempt]:
        """Batch run-attempt lookup for feed enrichment (created_at order)."""
        if not generation_ids:
            return []
        ids = list(dict.fromkeys(generation_ids))
        placeholders = ",".join("?" * len(ids))
        conn = self._store.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM run_attempts WHERE generation_id IN ({placeholders}) "
                "ORDER BY created_at ASC",
                ids,
            ).fetchall()
            return [self._row_to_attempt(r) for r in rows]
        finally:
            conn.close()

    def get_attempts_for_cells(self, cell_ids: Sequence[str]) -> list[RunAttempt]:
        """Batch run-attempt lookup by cell id (created_at order)."""
        if not cell_ids:
            return []
        ids = list(dict.fromkeys(cell_ids))
        placeholders = ",".join("?" * len(ids))
        conn = self._store.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM run_attempts WHERE cell_id IN ({placeholders}) "
                "ORDER BY created_at ASC",
                ids,
            ).fetchall()
            return [self._row_to_attempt(r) for r in rows]
        finally:
            conn.close()

    def get_cells_for_experiments(
        self, experiment_ids: Sequence[str]
    ) -> list[ExperimentCell]:
        """Batch cell lookup for feed enrichment (position order)."""
        if not experiment_ids:
            return []
        ids = list(dict.fromkeys(experiment_ids))
        placeholders = ",".join("?" * len(ids))
        conn = self._store.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM experiment_cells WHERE experiment_id IN ({placeholders}) "
                "ORDER BY position ASC",
                ids,
            ).fetchall()
            return [self._row_to_cell(r) for r in rows]
        finally:
            conn.close()

    # ── Export records ──────────────────────────────────────────────────

    def upsert_export_record(
        self,
        asset_id: str,
        *,
        state: str,
        destination_path: Optional[str] = None,
        exported_at: Optional[str] = None,
    ) -> ExportRecord:
        state_value = ExportState(state).value
        now = utc_now_iso()
        exported = exported_at or now
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT export_id FROM export_records WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            if row is None:
                export_id = new_id("exp_")
                conn.execute(
                    """INSERT INTO export_records (
                        export_id, asset_id, destination_path, exported_at, state, updated_at
                    ) VALUES (?,?,?,?,?,?)""",
                    (export_id, asset_id, destination_path, exported, state_value, now),
                )
            else:
                export_id = row["export_id"]
                conn.execute(
                    """UPDATE export_records
                       SET destination_path = ?, exported_at = ?, state = ?, updated_at = ?
                       WHERE export_id = ?""",
                    (destination_path, exported, state_value, now, export_id),
                )
        return ExportRecord(
            export_id=export_id,
            asset_id=asset_id,
            state=state_value,
            updated_at=now,
            destination_path=destination_path,
            exported_at=exported,
        )

    def get_export_record(self, asset_id: str) -> Optional[ExportRecord]:
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM export_records WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return self._row_to_export(row) if row is not None else None
        finally:
            conn.close()

    # ── Experiments ─────────────────────────────────────────────────────

    def create_experiment(
        self,
        *,
        experiment_id: Optional[str] = None,
        name: Optional[str] = None,
        definition: Optional[dict[str, Any]] = None,
        cells: Optional[list[dict[str, Any]]] = None,
        status: str = "draft",
        created_at: Optional[str] = None,
    ) -> ExperimentDetail:
        experiment_id = experiment_id if experiment_id is not None else new_id("exp_")
        now = created_at or utc_now_iso()
        cells = list(cells or [])
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO experiments (
                    experiment_id, name, definition_json, cell_ordering_json,
                    expected_cell_count, status, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (experiment_id, name, _compact_json(dict(definition or {})),
                 "[]", len(cells), status, now, now),
            )
            ordering: list[str] = []
            for position, spec in enumerate(cells):
                # Cell specs may carry an explicit "cell_id" (used when
                # present); otherwise a fresh id is generated per repo
                # convention.
                cell_id = (spec or {}).get("cell_id") or new_id("cell_")
                axis = dict((spec or {}).get("axis_labels") or {})
                conn.execute(
                    """INSERT INTO experiment_cells (
                        cell_id, experiment_id, position, axis_labels_json,
                        generation_id, attempt_ids_json, status, error, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (cell_id, experiment_id, position, _compact_json(axis),
                     None, "[]", "pending", None, now),
                )
                ordering.append(cell_id)
            conn.execute(
                "UPDATE experiments SET cell_ordering_json = ? WHERE experiment_id = ?",
                (_compact_json(ordering), experiment_id),
            )
        detail = self.get_experiment(experiment_id)
        assert detail is not None
        return detail

    def create_modern_matrix(
        self,
        *,
        experiment_id: Optional[str] = None,
        name: Optional[str] = None,
        definition: Optional[dict[str, Any]] = None,
        cells: Sequence[dict[str, Any]],
        created_at: Optional[str] = None,
        initial_attempt_status: Optional[str] = None,
    ) -> ExperimentDetail:
        """Atomically create a complete modern matrix in one transaction.

        One ``store.transaction()`` inserts the experiment, its FIXED ordered
        cells and, per cell, one stable generation + one immutable request
        snapshot + one initial attempt, then links everything (generation →
        snapshot, cell → generation, cell attempt_ids, experiment
        cell_ordering) and recomputes the initial statuses.

        Cell specs are the planner's ``CellPlan.to_dict()`` shape::

            {"cell_id": ..., "position": ..., "axis_values": {...},
             "axis_to_control": {...}, "axis_labels": [...],
             "workflow_id": ..., "workflow_version_id": ..., "preset_id": ...,
             "workflow_name": ..., "preset_name": ...,
             "controls": {...}, "merged_values": {...}, "plan_hash": ...,
             "execution_plan": {...} | None, "workflow_hash": ...,
             "error": ..., "error_code": ..., "errors": [...]}

        Explicit ``generation_id`` / ``run_id`` / ``request_snapshot_id`` (the
        older convention) are honored when present and otherwise minted fresh,
        so planner-style specs (which carry none) work unchanged.  Mapping
        contract:

        - ``generations.workflow_id`` ← ``workflow_id`` (never ``workflow_hash``);
          ``workflow_version_id`` / ``preset_id`` / ``preset_name`` are frozen.
        - ``request_snapshots.workflow_json`` ← ``execution_plan["workflow"]``
          when the plan is present, else the spec's own ``workflow``.
        - ``request_snapshots.execution_plan_json`` ← the exact
          ``execution_plan`` payload; ``request_json`` ← the full immutable
          cell plan; ``generation_params_json`` carries
          ``axis_values``/``controls``/``merged_values``/``axis_to_control``/
          ``plan_hash`` plus the resolved identity/names.
        - ``preset_snapshot_json`` ← preset identity/name and the exact merged
          values; ``deployment_identity_json`` ← the plan's deployment
          identity only (never fabricated).
        - ``experiment_cells.axis_labels_json`` ← the cell's ``axis_values``.

        Initial attempt: a valid cell (no plan ``error``) is queued with
        ``started_at`` NULL; a planning-invalid cell (``error``/``error_code``
        present) gets a terminal ``failed`` first attempt carrying the
        planning error.  An explicit ``initial_attempt_status`` (method arg or
        per-spec ``initial_attempt_status``) overrides that default.  Any
        duplicate/missing ``cell_id`` or an explicit ``position`` disagreeing
        with the fixed list order raises ``ValueError``; ANY exception rolls
        back the entire matrix.  Legacy ``create_experiment`` semantics are
        untouched.
        """
        experiment_id = experiment_id if experiment_id is not None else new_id("exp_")
        now = created_at or utc_now_iso()
        specs = [dict(s) for s in cells]
        with self._store.transaction() as conn:
            if not specs:
                raise ValueError("create_modern_matrix requires at least one cell spec")
            for position, spec in enumerate(specs):
                if not spec.get("cell_id"):
                    raise ValueError(
                        f"create_modern_matrix cell {position} is missing "
                        f"required id 'cell_id'"
                    )
                explicit_position = spec.get("position")
                if explicit_position is not None and int(explicit_position) != position:
                    raise ValueError(
                        f"cell {spec['cell_id']} position {explicit_position} "
                        f"!= fixed order index {position}"
                    )
            cell_ids = [str(spec["cell_id"]) for spec in specs]
            if len(set(cell_ids)) != len(cell_ids):
                raise ValueError("duplicate cell_id in create_modern_matrix cells")
            for position, spec in enumerate(specs):
                spec["generation_id"] = str(
                    spec.get("generation_id") or new_id("gen_")
                )
                spec["run_id"] = str(spec.get("run_id") or new_id("run_"))
                spec["request_snapshot_id"] = str(
                    spec.get("request_snapshot_id") or new_id("snap_")
                )
            for key in ("generation_id", "run_id", "request_snapshot_id"):
                ids = [str(spec[key]) for spec in specs]
                if len(set(ids)) != len(ids):
                    raise ValueError(f"duplicate {key} in create_modern_matrix cells")
            conn.execute(
                """INSERT INTO experiments (
                    experiment_id, name, definition_json, cell_ordering_json,
                    expected_cell_count, status, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (experiment_id, name, _compact_json(dict(definition or {})),
                 "[]", len(specs), "running", now, now),
            )
            ordering: list[str] = []
            for position, spec in enumerate(specs):
                cell_id = str(spec["cell_id"])
                generation_id = str(spec["generation_id"])
                run_id = str(spec["run_id"])
                snapshot_id = str(spec["request_snapshot_id"])
                execution_plan = spec.get("execution_plan")
                if not isinstance(execution_plan, dict):
                    execution_plan = {}
                workflow = execution_plan.get("workflow")
                if not isinstance(workflow, dict):
                    workflow = spec.get("workflow")
                    if not isinstance(workflow, dict):
                        workflow = {}
                workflow_hash = spec.get("workflow_hash") or execution_plan.get(
                    "workflow_hash"
                )
                workflow_version_id = spec.get("workflow_version_id") or execution_plan.get(
                    "workflow_version_id"
                )
                deployment_identity = execution_plan.get("deployment_identity")
                if not isinstance(deployment_identity, dict):
                    deployment_identity = spec.get("deployment_identity")
                    if not isinstance(deployment_identity, dict):
                        deployment_identity = {}
                generation_params = {
                    "axis_values": dict(spec.get("axis_values") or {}),
                    "controls": dict(spec.get("controls") or {}),
                    "merged_values": dict(spec.get("merged_values") or {}),
                    "axis_to_control": dict(spec.get("axis_to_control") or {}),
                    "plan_hash": spec.get("plan_hash"),
                    "workflow_id": spec.get("workflow_id"),
                    "workflow_version_id": workflow_version_id,
                    "preset_id": spec.get("preset_id"),
                    "workflow_name": spec.get("workflow_name"),
                    "preset_name": spec.get("preset_name"),
                    "version_number": spec.get("version_number"),
                    "modal_options": dict(spec.get("modal_options") or {}),
                }
                preset_snapshot = {
                    "preset_id": spec.get("preset_id"),
                    "preset_name": spec.get("preset_name"),
                    "merged_values": dict(spec.get("merged_values") or {}),
                }
                conn.execute(
                    """INSERT INTO request_snapshots (
                        snapshot_id, generation_id, schema_version, workflow_json,
                        workflow_hash, workflow_version_id, generation_params_json,
                        preset_snapshot_json, request_json, execution_plan_json,
                        deployment_identity_json, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (snapshot_id, generation_id, 1, _compact_json(workflow),
                     workflow_hash, workflow_version_id,
                     _compact_json(generation_params),
                     _compact_json(preset_snapshot),
                     _compact_json(dict(spec)),
                     _compact_json(execution_plan),
                     _compact_json(deployment_identity), now),
                )
                conn.execute(
                    """INSERT INTO generations (
                        generation_id, created_at, workflow_id, workflow_version_id,
                        preset_id, preset_name, request_snapshot_id, experiment_id,
                        featured_asset_id, favorite, note, status, prompt_text,
                        negative_prompt_text, model_stack_json, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (generation_id, now, spec.get("workflow_id"),
                     workflow_version_id, spec.get("preset_id"),
                     spec.get("preset_name"), snapshot_id,
                     experiment_id, None, 0, "", "pending", "", "", "[]", now),
                )
                # Initial attempt status: explicit override wins, otherwise a
                # planning-invalid cell (either spec.error or spec.error_code)
                # is terminal failed, a valid cell queued.
                override = spec.get("initial_attempt_status") or initial_attempt_status
                if override:
                    initial_status = RunStatus(override).value
                elif spec.get("error") or spec.get("error_code"):
                    initial_status = RunStatus.FAILED.value
                else:
                    initial_status = RunStatus.QUEUED.value
                if initial_status == RunStatus.FAILED.value:
                    attempt_error = (
                        spec.get("error")
                        or spec.get("error_code")
                        or "planning error"
                    )
                    finished_at = now
                else:
                    attempt_error = None
                    finished_at = None
                mode_value = RunMode(spec.get("mode") or "original").value
                axis = spec.get("axis_values")
                if not isinstance(axis, dict):
                    axis = spec.get("axis_labels")
                    if not isinstance(axis, dict):
                        axis = {}
                cell_status = (
                    CellStatus.QUEUED.value
                    if initial_status == RunStatus.QUEUED.value
                    else CellStatus.FAILED.value
                )
                # The cell row precedes the attempt row: run_attempts.cell_id
                # is a foreign key into experiment_cells.
                conn.execute(
                    """INSERT INTO experiment_cells (
                        cell_id, experiment_id, position, axis_labels_json,
                        generation_id, attempt_ids_json, status, error, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (cell_id, experiment_id, position, _compact_json(axis),
                     generation_id, _compact_json([run_id]),
                     cell_status, attempt_error, now),
                )
                conn.execute(
                    """INSERT INTO run_attempts (
                        run_id, generation_id, experiment_id, cell_id, mode, status,
                        started_at, finished_at, error, timing_json, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, generation_id, experiment_id, cell_id, mode_value,
                     initial_status, None, finished_at, attempt_error, "{}", now),
                )
                ordering.append(cell_id)
                self._recompute_generation(conn, generation_id, now)
                self._recompute_cell(conn, cell_id, now)
            conn.execute(
                """UPDATE experiments
                   SET cell_ordering_json = ?, expected_cell_count = ?, updated_at = ?
                   WHERE experiment_id = ?""",
                (_compact_json(ordering), len(specs), now, experiment_id),
            )
            self._derive_experiment_status(conn, experiment_id)
        detail = self.get_experiment(experiment_id)
        assert detail is not None
        return detail

    def add_experiment_cell(
        self,
        experiment_id: str,
        *,
        cell_id: Optional[str] = None,
        axis_labels: Optional[dict[str, Any]] = None,
        position: Optional[int] = None,
    ) -> ExperimentCell:
        cell_id = cell_id if cell_id is not None else new_id("cell_")
        now = utc_now_iso()
        with self._store.transaction() as conn:
            exp = conn.execute(
                "SELECT cell_ordering_json FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if exp is None:
                raise ValueError(f"unknown experiment: {experiment_id}")
            ordering = list(self._parse_json(exp["cell_ordering_json"], []))
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM experiment_cells "
                "WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()[0]
            pos = position if position is not None else int(max_pos) + 1
            conn.execute(
                """INSERT INTO experiment_cells (
                    cell_id, experiment_id, position, axis_labels_json,
                    generation_id, attempt_ids_json, status, error, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (cell_id, experiment_id, pos, _compact_json(dict(axis_labels or {})),
                 None, "[]", "pending", None, now),
            )
            ordering.append(cell_id)
            conn.execute(
                """UPDATE experiments
                   SET expected_cell_count = expected_cell_count + 1,
                       cell_ordering_json = ?, updated_at = ?
                   WHERE experiment_id = ?""",
                (_compact_json(ordering), now, experiment_id),
            )
        return self._get_cell(cell_id)

    def update_experiment_cell(
        self,
        cell_id: str,
        *,
        generation_id: Optional[str] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
        add_attempt: Optional[str] = None,
    ) -> ExperimentCell:
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM experiment_cells WHERE cell_id = ?", (cell_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown experiment cell: {cell_id}")
            now = utc_now_iso()
            attempt_ids = list(self._parse_json(row["attempt_ids_json"], []))
            derived_status: Optional[str] = None
            if add_attempt:
                if add_attempt not in attempt_ids:
                    attempt_ids.append(add_attempt)
                cell_attempts = self._attempts_for_cell(conn, cell_id)
                derived_status = derive_cell_status(cell_attempts)
            final_status = (
                status if status is not None
                else derived_status if derived_status is not None
                else row["status"]
            )
            new_generation_id = (
                generation_id if generation_id is not None else row["generation_id"]
            )
            new_error = error if error is not None else row["error"]
            conn.execute(
                """UPDATE experiment_cells
                   SET generation_id = ?, status = ?, error = ?,
                       attempt_ids_json = ?, updated_at = ?
                   WHERE cell_id = ?""",
                (new_generation_id, final_status, new_error,
                 _compact_json(attempt_ids), now, cell_id),
            )
            self._derive_experiment_status(conn, row["experiment_id"])
        return self._get_cell(cell_id)

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentDetail]:
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if row is None:
                return None
            experiment = self._row_to_experiment(row)
            cells: list[ExperimentCell] = []
            for c in conn.execute(
                "SELECT * FROM experiment_cells WHERE experiment_id = ? "
                "ORDER BY position ASC",
                (experiment_id,),
            ).fetchall():
                cell = self._row_to_cell(c)
                # attempt_ids_json is the authoritative list; verify it against
                # the actual run_attempts rows for this cell.
                actual_ids = [
                    a.run_id for a in self._attempts_for_cell(conn, cell.cell_id)
                ]
                if actual_ids:
                    cell = replace(cell, attempt_ids=actual_ids)
                cells.append(cell)
            return ExperimentDetail(experiment=experiment, cells=cells)
        finally:
            conn.close()

    def set_experiment_status(self, experiment_id: str, status: str) -> bool:
        with self._store.transaction() as conn:
            cur = conn.execute(
                "UPDATE experiments SET status = ?, updated_at = ? "
                "WHERE experiment_id = ?",
                (status, utc_now_iso(), experiment_id),
            )
            return cur.rowcount > 0

    def set_experiment_favorite(self, experiment_id: str, favorite: bool) -> bool:
        with self._store.transaction() as conn:
            cur = conn.execute(
                "UPDATE experiments SET favorite = ?, updated_at = ? "
                "WHERE experiment_id = ?",
                (int(bool(favorite)), utc_now_iso(), experiment_id),
            )
            return cur.rowcount > 0

    def set_experiment_note(self, experiment_id: str, note: str) -> bool:
        if len(note) > 2000:
            raise ValueError("note exceeds 2000 characters (legacy limit)")
        with self._store.transaction() as conn:
            cur = conn.execute(
                "UPDATE experiments SET note = ?, updated_at = ? "
                "WHERE experiment_id = ?",
                (note, utc_now_iso(), experiment_id),
            )
            return cur.rowcount > 0

    def _get_cell(self, cell_id: str) -> ExperimentCell:
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM experiment_cells WHERE cell_id = ?", (cell_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown experiment cell: {cell_id}")
            return self._row_to_cell(row)
        finally:
            conn.close()

    def get_experiment_cell(self, cell_id: str) -> Optional[ExperimentCell]:
        """Public wrapper around ``_get_cell`` returning None for unknown ids."""
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM experiment_cells WHERE cell_id = ?", (cell_id,)
            ).fetchone()
            return self._row_to_cell(row) if row is not None else None
        finally:
            conn.close()

    # ── Modern scheduler persistence adapter (D3) ────────────────────────

    def _require_experiment_scope(self) -> str:
        """The bound ``experiment_id`` for the no-argument adapter methods.

        The modern scheduler calls ``load_queued_cells`` / ``list_recoverable_cells``
        / ``aggregate_status`` with no experiment argument, so the repository
        instance must be bound to one experiment (construct with
        ``experiment_id=...``).  Cell-scoped operations resolve their
        experiment from the cell row and do not need the binding.
        """
        if not self.experiment_id:
            raise ValueError(
                "modern experiment persistence adapter requires an "
                "experiment-bound repository (construct with experiment_id=...)"
            )
        return str(self.experiment_id)

    def _fixed_order_cells(self, conn: sqlite3.Connection, experiment_id: str) -> list[Any]:
        """Experiment cells in fixed ``position`` order (connection-owned)."""
        return conn.execute(
            "SELECT * FROM experiment_cells WHERE experiment_id = ? "
            "ORDER BY position ASC",
            (experiment_id,),
        ).fetchall()

    def _current_attempt_row(
        self, conn: sqlite3.Connection, cell_id: str
    ) -> Optional[sqlite3.Row]:
        """The cell's CURRENT (latest) attempt row by ``(created_at, run_id)``."""
        return conn.execute(
            "SELECT * FROM run_attempts WHERE cell_id = ? "
            "ORDER BY created_at DESC, run_id DESC LIMIT 1",
            (cell_id,),
        ).fetchone()

    def _cell_attempts(self, conn: sqlite3.Connection, cell_id: str) -> list[RunAttempt]:
        return [
            self._row_to_attempt(r)
            for r in conn.execute(
                "SELECT * FROM run_attempts WHERE cell_id = ? "
                "ORDER BY created_at ASC",
                (cell_id,),
            ).fetchall()
        ]

    def load_queued_cells(self) -> list[dict[str, Any]]:
        """Durable ordered queued cells: fixed ``position`` order.

        A cell is queued when its CURRENT attempt is ``"queued"``/``"pending"``
        (``started_at`` unset until claimed) or it has no attempt yet.  Return
        shape is ``_coerce_cell_records``-compatible:
        ``[{"cell_id", "attempt_id", "status"}]``.
        """
        experiment_id = self._require_experiment_scope()
        conn = self._store.connect()
        try:
            records: list[dict[str, Any]] = []
            for cell in self._fixed_order_cells(conn, experiment_id):
                current = self._current_attempt_row(conn, cell["cell_id"])
                if current is None:
                    records.append({
                        "cell_id": cell["cell_id"],
                        "attempt_id": None,
                        "status": None,
                    })
                elif current["status"] in (
                    RunStatus.QUEUED.value, "pending",
                ):
                    records.append({
                        "cell_id": cell["cell_id"],
                        "attempt_id": current["run_id"],
                        "status": current["status"],
                    })
            return records
        finally:
            conn.close()

    def atomically_claim_queued_attempt(self, cell_id: str) -> Optional[ClaimResult]:
        """Atomically claim the cell's current queued attempt (queued → running).

        Single transaction.  NEVER creates an attempt (a cell with no attempt
        stays unclaimed).  Only the CURRENT attempt is eligible; the claim is
        a compare-and-swap so two callers cannot both win.  ``started_at`` is
        stamped on a successful claim.  Returns a ``ClaimResult`` whose
        outcome is one of ``CLAIM_CLAIMED`` / ``CLAIM_ALREADY_CLAIMED`` /
        ``CLAIM_TERMINAL`` / ``CLAIM_NOT_FOUND`` (coercible by
        ``_coerce_claim``), or ``None`` for an unknown cell with no attempt.
        """
        now = utc_now_iso()
        with self._store.transaction() as conn:
            cell = conn.execute(
                "SELECT 1 FROM experiment_cells WHERE cell_id = ?", (cell_id,)
            ).fetchone()
            if cell is None:
                return None
            current = self._current_attempt_row(conn, cell_id)
            if current is None:
                return ClaimResult(outcome=CLAIM_NOT_FOUND, attempt=None)
            if current["status"] != RunStatus.QUEUED.value:
                outcome = (
                    CLAIM_TERMINAL
                    if current["status"] in _TERMINAL_RUN_STATUS_VALUES
                    else CLAIM_ALREADY_CLAIMED
                )
                return ClaimResult(
                    outcome=outcome, attempt=self._row_to_attempt(current)
                )
            conn.execute(
                """UPDATE run_attempts
                   SET status = ?, started_at = ?
                   WHERE run_id = ? AND status = ?""",
                (RunStatus.RUNNING.value, now, current["run_id"],
                 RunStatus.QUEUED.value),
            )
            stored = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (current["run_id"],)
            ).fetchone()
            self._recompute_generation(conn, stored["generation_id"], now)
            self._recompute_cell(conn, cell_id, now)
            return ClaimResult(
                outcome=CLAIM_CLAIMED, attempt=self._row_to_attempt(stored)
            )

    def read_active_attempt(self, cell_id: str) -> Optional[RunAttempt]:
        """The cell's CURRENT attempt (queued/running/terminal), or None."""
        conn = self._store.connect()
        try:
            row = self._current_attempt_row(conn, cell_id)
            return self._row_to_attempt(row) if row is not None else None
        finally:
            conn.close()

    def record_running(self, attempt_id: str, cell_id: str) -> None:
        """Idempotently record ``running`` for the cell's current attempt.

        Only the CURRENT attempt may be marked; a stale older attempt cannot
        mutate a newer one, and a terminal attempt is never reopened.  A
        queued attempt is stamped ``started_at`` on the transition; an
        already-running attempt is left untouched.
        """
        now = utc_now_iso()
        with self._store.transaction() as conn:
            current = self._current_attempt_row(conn, cell_id)
            if (
                current is None
                or current["run_id"] != attempt_id
                or current["status"] in _TERMINAL_RUN_STATUS_VALUES
            ):
                return
            if current["status"] == RunStatus.QUEUED.value:
                conn.execute(
                    """UPDATE run_attempts
                       SET status = ?, started_at = ?
                       WHERE run_id = ? AND status = ?""",
                    (RunStatus.RUNNING.value, now, attempt_id,
                     RunStatus.QUEUED.value),
                )
                stored = conn.execute(
                    "SELECT * FROM run_attempts WHERE run_id = ?", (attempt_id,)
                ).fetchone()
                if stored is not None:
                    self._recompute_generation(conn, stored["generation_id"], now)
                self._recompute_cell(conn, cell_id, now)

    def record_terminal(
        self,
        attempt_id: str,
        cell_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        """Apply a terminal status with terminal first-wins + attempt identity.

        Returns True only when THIS call performed the write.  A stale old
        attempt (not the current one) can never mutate a newer attempt; a
        terminal current attempt is never overwritten.  Derived generation /
        cell / experiment states are recomputed inside the same transaction.
        """
        run_status = RunStatus(status)  # raises ValueError on unknown status
        if run_status not in TERMINAL_RUN_STATUSES:
            raise ValueError(
                f"status {status!r} is not a terminal RunStatus; "
                f"terminal statuses: {sorted(s.value for s in TERMINAL_RUN_STATUSES)}"
            )
        now = utc_now_iso()
        with self._store.transaction() as conn:
            current = self._current_attempt_row(conn, cell_id)
            if (
                current is None
                or current["run_id"] != attempt_id
                or current["status"] in _TERMINAL_RUN_STATUS_VALUES
            ):
                return False
            terminal_values = tuple(sorted(_TERMINAL_RUN_STATUS_VALUES))
            conn.execute(
                f"""UPDATE run_attempts
                   SET status = ?, finished_at = ?, error = ?
                   WHERE run_id = ? AND status NOT IN ({','.join('?' * len(terminal_values))})""",
                (run_status.value, now, error, attempt_id) + terminal_values,
            )
            stored = conn.execute(
                "SELECT * FROM run_attempts WHERE run_id = ?", (attempt_id,)
            ).fetchone()
            if stored is None:
                return False
            self._recompute_generation(conn, stored["generation_id"], now)
            self._recompute_cell(conn, cell_id, now)
            return True

    def record_result(
        self,
        attempt_id: str,
        cell_id: str,
        result: Any,
    ) -> bool:
        """Persist output assets for the current running cell attempt.

        The scheduler calls this before its terminal ``completed`` write.  The
        result carries only materialized basenames or a registered producer
        asset id; no output bytes are fabricated here.  A required-output
        result succeeds only when History V2 can see an associated asset.
        """
        if not isinstance(result, dict):
            return False

        conn = self._store.connect()
        try:
            current = self._current_attempt_row(conn, cell_id)
            if (
                current is None
                or current["run_id"] != str(attempt_id)
                or current["status"] in _TERMINAL_RUN_STATUS_VALUES
            ):
                return False
            experiment_id = str(current["experiment_id"] or self.experiment_id or "")
            generation_id = str(current["generation_id"])
        finally:
            conn.close()

        cell_key = str(result.get("_history_cell_key") or cell_id)
        output_values = result.get("output_paths") or []
        if isinstance(output_values, str):
            output_values = [output_values]
        if not isinstance(output_values, (list, tuple)):
            output_values = []

        # Materialized Experiment outputs live in their attempt directory;
        # accept an already-absolute path as well as the basename contract.
        candidate_dirs: list[Path] = []
        try:
            from local_artifacts import get_experiments_dir, get_studio_outputs_dir

            if experiment_id:
                candidate_dirs.append(
                    get_experiments_dir()
                    / experiment_id
                    / "outputs"
                    / cell_key
                    / str(attempt_id)
                )
            candidate_dirs.append(get_studio_outputs_dir())
        except Exception:
            pass

        resolved_paths: list[str] = []
        for value in output_values:
            candidate = Path(str(value))
            if candidate.is_file():
                resolved_paths.append(str(candidate))
                continue
            for directory in candidate_dirs:
                resolved = directory / candidate.name
                if resolved.is_file():
                    resolved_paths.append(str(resolved))
                    break

        primary_output = result.get("primary_output") or result.get("_local_primary_output")
        primary_asset_id = str(result.get("primary_asset_id") or "")
        if not resolved_paths and isinstance(primary_output, dict):
            primary_path = primary_output.get("path")
            if primary_path:
                primary_candidate = Path(str(primary_path))
                if primary_candidate.is_file():
                    resolved_paths.append(str(primary_candidate))
        required = bool(result.get("_history_output_required"))

        try:
            from history_v2_writer import HistoryV2ProductionWriter

            writer = HistoryV2ProductionWriter(self._store.data_root())
            history_meta = {
                "primary_asset_id": primary_asset_id,
                "cell_key": cell_key,
                "attempt_id": str(attempt_id),
            }
            for key in (
                "logical_output_key",
                "logical_output_keys",
                "asset_descriptors",
                "output_descriptors",
                "node_id",
                "output_key",
                "output_index",
            ):
                if key in result:
                    history_meta[key] = result[key]
            writer.attach_result_assets(
                generation_id,
                str(attempt_id),
                output_paths=resolved_paths,
                primary_asset_id=primary_asset_id,
                meta=history_meta,
            )
        except Exception:
            return False if required else True

        detail = self.get_generation(generation_id)
        has_output = bool(
            detail is not None
            and any(
                asset.type in {"thumbnail", "preview", "original"}
                for asset in detail.assets
            )
        )
        return has_output if required else True

    def _create_cell_attempt(
        self,
        conn: sqlite3.Connection,
        cell_id: str,
        *,
        mode: str = "original",
        now: str,
    ) -> Optional[ClaimResult]:
        """Insert a new queued attempt for a cell (same Generation/snapshot).

        Shared by ``create_resume_attempt`` / ``create_retry_attempt``.  The
        new attempt carries a fresh ``run_`` identity, stays ``queued`` with
        ``started_at`` NULL until claimed, and is appended to the cell's
        attempt_ids.  Unknown cells return None.
        """
        cell = conn.execute(
            "SELECT * FROM experiment_cells WHERE cell_id = ?", (cell_id,)
        ).fetchone()
        if cell is None:
            return None
        generation_id = cell["generation_id"]
        if not generation_id:
            return None
        run_id = new_id("run_")
        conn.execute(
            """INSERT INTO run_attempts (
                run_id, generation_id, experiment_id, cell_id, mode, status,
                started_at, finished_at, error, timing_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, generation_id, cell["experiment_id"], cell_id,
             RunMode(mode).value, RunStatus.QUEUED.value,
             None, None, None, "{}", now),
        )
        attempt_ids = list(self._parse_json(cell["attempt_ids_json"], []))
        if run_id not in attempt_ids:
            attempt_ids.append(run_id)
        conn.execute(
            """UPDATE experiment_cells
               SET attempt_ids_json = ?, updated_at = ?
               WHERE cell_id = ?""",
            (_compact_json(attempt_ids), now, cell_id),
        )
        self._recompute_generation(conn, generation_id, now)
        self._recompute_cell(conn, cell_id, now)
        stored = conn.execute(
            "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
        ).fetchone()
        return ClaimResult(
            outcome=CLAIM_CLAIMED, attempt=self._row_to_attempt(stored)
        )

    def create_resume_attempt(self, cell_id: str) -> Optional[ClaimResult]:
        """Create a NEW queued attempt for an interrupted cell.

        Single transaction.  Only a cell whose CURRENT attempt is
        ``"interrupted"`` is eligible; the interrupted attempt is left
        untouched (append-only).  The new attempt reuses the cell's existing
        Generation — and therefore its immutable request snapshot.  Returns a
        claimed ``ClaimResult`` or None when not eligible.
        """
        now = utc_now_iso()
        with self._store.transaction() as conn:
            current = self._current_attempt_row(conn, cell_id)
            if (
                current is None
                or current["status"] != RunStatus.INTERRUPTED.value
            ):
                return None
            return self._create_cell_attempt(
                conn, cell_id, mode=current["mode"], now=now
            )

    def create_retry_attempt(self, cell_id: str) -> Optional[ClaimResult]:
        """Create a NEW queued attempt for a failed cell.

        Single transaction.  Only a cell whose CURRENT attempt is
        ``"failed"`` is eligible; the failed attempt is left untouched
        (append-only).  The new attempt reuses the cell's existing Generation
        — and therefore its immutable request snapshot.  Returns a claimed
        ``ClaimResult`` or None when not eligible.
        """
        now = utc_now_iso()
        with self._store.transaction() as conn:
            current = self._current_attempt_row(conn, cell_id)
            if current is None or current["status"] != RunStatus.FAILED.value:
                return None
            return self._create_cell_attempt(
                conn, cell_id, mode=current["mode"], now=now
            )

    # ── Generate Original (E3B2): transactional claim/reuse ─────────────

    def _insert_generation_attempt(
        self,
        conn: sqlite3.Connection,
        generation_row: sqlite3.Row,
        *,
        mode: str,
        now: str,
    ) -> RunAttempt:
        """Insert one queued attempt for a generation with an explicit mode.

        Caller owns the open transaction.  Cell-aware: when the generation
        belongs to a modern Experiment cell the attempt carries the cell/
        experiment identity and is appended to the cell's attempt_ids; the
        derived generation/cell/experiment states are recomputed.  The new
        attempt stays ``queued`` with ``started_at`` NULL until claimed.
        """
        generation_id = generation_row["generation_id"]
        run_id = new_id("run_")
        cell_row = conn.execute(
            "SELECT * FROM experiment_cells WHERE generation_id = ?",
            (generation_id,),
        ).fetchone()
        experiment_id = generation_row["experiment_id"]
        cell_id: Optional[str] = None
        if cell_row is not None:
            cell_id = cell_row["cell_id"]
            experiment_id = cell_row["experiment_id"] or experiment_id
        conn.execute(
            """INSERT INTO run_attempts (
                run_id, generation_id, experiment_id, cell_id, mode, status,
                started_at, finished_at, error, timing_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, generation_id, experiment_id, cell_id,
             RunMode(mode).value, RunStatus.QUEUED.value,
             None, None, None, "{}", now),
        )
        if cell_row is not None:
            attempt_ids = list(self._parse_json(cell_row["attempt_ids_json"], []))
            if run_id not in attempt_ids:
                attempt_ids.append(run_id)
            conn.execute(
                """UPDATE experiment_cells
                   SET attempt_ids_json = ?, updated_at = ?
                   WHERE cell_id = ?""",
                (_compact_json(attempt_ids), now, cell_id),
            )
        self._recompute_generation(conn, generation_id, now)
        if cell_id:
            self._recompute_cell(conn, cell_id, now)
        stored = conn.execute(
            "SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)
        ).fetchone()
        return self._row_to_attempt(stored)

    def _insert_original_attempt(
        self,
        conn: sqlite3.Connection,
        generation_row: sqlite3.Row,
        *,
        now: str,
    ) -> RunAttempt:
        """Insert one queued ``mode="original"`` attempt (E3B2 wrapper)."""
        return self._insert_generation_attempt(
            conn, generation_row, mode=RunMode.ORIGINAL.value, now=now
        )

    def claim_or_reuse_original_attempt(
        self,
        generation_id: str,
        *,
        explicit_rerender: bool = False,
    ) -> Optional["OriginalClaimOutcome"]:
        """Transactional E3B1 decision + guarded Original-attempt creation.

        One ``BEGIN IMMEDIATE`` transaction implements the frozen duplicate
        policy: an active Original Attempt is returned (never duplicated), the
        newest successful Original is reused by default, only-failed history
        reports ``retry_required``, an active Preview reports ``busy``, and a
        new queued Original Attempt is created only when policy permits.
        Two racing callers serialize on the write transaction, so a
        double-submit can never create two active Original Attempts and no
        orphan Attempt is left behind.  Snapshot capability validation is NOT
        performed here (the caller validates the immutable snapshot first);
        this method never consults mutable Workflow/Preset state.
        """
        from history_v2_replay import decide_original_action

        now = utc_now_iso()
        with self._store.transaction() as conn:
            gen_row = conn.execute(
                "SELECT * FROM generations WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            if gen_row is None:
                return None
            generation = self._row_to_generation(gen_row)
            snapshot: Optional[RequestSnapshot] = None
            if generation.request_snapshot_id:
                srow = conn.execute(
                    "SELECT * FROM request_snapshots WHERE snapshot_id = ?",
                    (generation.request_snapshot_id,),
                ).fetchone()
                if srow is not None:
                    snapshot = self._row_to_snapshot(srow)
            attempts = self._attempts_for_generation(conn, generation_id)
            decision = decide_original_action(
                attempts, explicit_rerender=explicit_rerender
            )
            if decision.create_new:
                attempt = self._insert_original_attempt(
                    conn, gen_row, now=now
                )
                return OriginalClaimOutcome(
                    outcome="created",
                    attempt=attempt,
                    generation=generation,
                    snapshot=snapshot,
                    decision=decision.decision,
                    reason=decision.reason,
                )
            relevant: Optional[RunAttempt] = None
            if decision.attempt_id:
                relevant = next(
                    (
                        a for a in attempts
                        if a.run_id == decision.attempt_id
                    ),
                    None,
                )
            return OriginalClaimOutcome(
                outcome=str(decision.decision),
                attempt=relevant,
                generation=generation,
                snapshot=snapshot,
                decision=decision.decision,
                reason=decision.reason,
            )

    def create_original_retry_attempt(
        self,
        generation_id: str,
    ) -> Optional["OriginalClaimOutcome"]:
        """Retry path for a failed Original Attempt (one transaction).

        Eligible only when no attempt of the Generation is active and the
        newest ``mode="original"`` attempt is ``failed`` (validated by the
        replay core's ``validate_original_retry``).  The failed attempt is
        never reopened or mutated; a fresh queued ``mode="original"``
        Attempt is appended under the SAME Generation and its SAME immutable
        request snapshot.  A Preview Attempt is never retried as an Original.
        """
        from history_v2_replay import validate_original_retry

        now = utc_now_iso()
        with self._store.transaction() as conn:
            gen_row = conn.execute(
                "SELECT * FROM generations WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            if gen_row is None:
                return None
            generation = self._row_to_generation(gen_row)
            snapshot: Optional[RequestSnapshot] = None
            if generation.request_snapshot_id:
                srow = conn.execute(
                    "SELECT * FROM request_snapshots WHERE snapshot_id = ?",
                    (generation.request_snapshot_id,),
                ).fetchone()
                if srow is not None:
                    snapshot = self._row_to_snapshot(srow)
            attempts = self._attempts_for_generation(conn, generation_id)
            if any(
                a.status in (RunStatus.QUEUED.value, RunStatus.RUNNING.value)
                for a in attempts
            ):
                return OriginalClaimOutcome(
                    outcome="busy",
                    attempt=None,
                    generation=generation,
                    snapshot=snapshot,
                    decision="busy",
                    reason="attempt_active",
                )
            originals = [a for a in attempts if a.mode == RunMode.ORIGINAL.value]
            newest = max(
                originals,
                key=lambda a: (a.created_at, a.run_id),
                default=None,
            )
            if newest is None:
                return OriginalClaimOutcome(
                    outcome="not_retryable",
                    attempt=None,
                    generation=generation,
                    snapshot=snapshot,
                    decision="retry_required",
                    reason="no_original_attempt",
                )
            validation = validate_original_retry(
                newest,
                generation_id=generation.generation_id,
                snapshot_id=(
                    snapshot.snapshot_id if snapshot is not None else ""
                ),
                retry_snapshot_id=(
                    snapshot.snapshot_id if snapshot is not None else ""
                ),
            )
            if not validation.valid:
                return OriginalClaimOutcome(
                    outcome="not_retryable",
                    attempt=newest,
                    generation=generation,
                    snapshot=snapshot,
                    decision="retry_required",
                    reason=validation.reason or REASON_NOT_RETRYABLE,
                )
            attempt = self._insert_original_attempt(conn, gen_row, now=now)
            return OriginalClaimOutcome(
                outcome="created",
                attempt=attempt,
                generation=generation,
                snapshot=snapshot,
                decision="create_original",
                reason="original_retry",
            )

    def create_single_resume_attempt(
        self,
        generation_id: str,
    ) -> Optional["OriginalClaimOutcome"]:
        """Generation-level Single Resume claim/create (F1A, one transaction).

        Eligible only when the Generation is an ordinary modern Single (no
        Experiment identity and no linked Experiment cell), no attempt of the
        Generation is active (queued/running), and the CURRENT attempt is
        ``interrupted``.  The interrupted attempt is never reopened or
        mutated: a fresh queued Attempt is appended under the SAME Generation
        and its SAME immutable request snapshot, preserving the interrupted
        attempt's semantic ``mode`` (the frozen ExecutionPlan's output mode).
        Refusals are truthful machine-readable outcomes — never silent state
        conversions:

        - ``busy`` + ``attempt_active``: an active attempt exists;
        - ``not_resumable`` + ``experiment_cell_generation``: Experiment
          cells resume through the Experiment surface instead;
        - ``not_resumable`` + ``failed_requires_retry`` / ``canceled_not_resumable``
          / ``generation_completed`` / ``no_attempts`` /
          ``current_attempt_not_interrupted``.

        Two racing callers serialize on the write transaction, so a duplicate
        Resume can never create two active Attempts.  Snapshot capability
        validation is NOT performed here (the caller validates first); this
        method never consults mutable Workflow/Preset state.
        """
        now = utc_now_iso()
        with self._store.transaction() as conn:
            gen_row = conn.execute(
                "SELECT * FROM generations WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            if gen_row is None:
                return None
            generation = self._row_to_generation(gen_row)
            snapshot: Optional[RequestSnapshot] = None
            if generation.request_snapshot_id:
                srow = conn.execute(
                    "SELECT * FROM request_snapshots WHERE snapshot_id = ?",
                    (generation.request_snapshot_id,),
                ).fetchone()
                if srow is not None:
                    snapshot = self._row_to_snapshot(srow)

            def _refuse(reason: str, attempt: Optional[RunAttempt] = None) -> "OriginalClaimOutcome":
                return OriginalClaimOutcome(
                    outcome="not_resumable",
                    attempt=attempt,
                    generation=generation,
                    snapshot=snapshot,
                    decision="resume_not_available",
                    reason=reason,
                )

            cell_row = conn.execute(
                "SELECT cell_id FROM experiment_cells WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            if cell_row is not None or gen_row["experiment_id"]:
                return _refuse(RESUME_REASON_EXPERIMENT_CELL)

            attempts = self._attempts_for_generation(conn, generation_id)
            if any(
                a.status in (RunStatus.QUEUED.value, RunStatus.RUNNING.value)
                for a in attempts
            ):
                active = next(
                    (
                        a for a in reversed(attempts)
                        if a.status in (RunStatus.QUEUED.value, RunStatus.RUNNING.value)
                    ),
                    None,
                )
                return OriginalClaimOutcome(
                    outcome="busy",
                    attempt=active,
                    generation=generation,
                    snapshot=snapshot,
                    decision="busy",
                    reason="attempt_active",
                )
            current = current_attempt(attempts)
            if current is None:
                return _refuse(RESUME_REASON_NO_ATTEMPTS)
            if current.status == RunStatus.COMPLETED.value:
                return _refuse(RESUME_REASON_COMPLETED, current)
            if current.status == RunStatus.FAILED.value:
                return _refuse(RESUME_REASON_FAILED, current)
            if current.status == RunStatus.CANCELED.value:
                return _refuse(RESUME_REASON_CANCELED, current)
            if current.status != RunStatus.INTERRUPTED.value:
                return _refuse(RESUME_REASON_NOT_INTERRUPTED, current)
            attempt = self._insert_generation_attempt(
                conn, gen_row, mode=current.mode, now=now
            )
            return OriginalClaimOutcome(
                outcome="created",
                attempt=attempt,
                generation=generation,
                snapshot=snapshot,
                decision="resume_created",
                reason="single_resume",
            )

    def list_recoverable_cells(self) -> list[dict[str, Any]]:
        """Cells needing recovery/resume: fixed ``position`` order.

        Includes every cell whose CURRENT attempt is recoverable
        (``interrupted`` / ``running`` stale / ``queued`` / ``pending``) or
        which has no attempt yet.  Only cells whose current attempt is
        ``completed``, ``failed`` or ``canceled`` are excluded (interrupted is
        recoverable even though it is terminal).  Return shape is
        ``_coerce_cell_records``-compatible.
        """
        experiment_id = self._require_experiment_scope()
        conn = self._store.connect()
        try:
            records: list[dict[str, Any]] = []
            for cell in self._fixed_order_cells(conn, experiment_id):
                current = self._current_attempt_row(conn, cell["cell_id"])
                if current is None:
                    records.append({
                        "cell_id": cell["cell_id"],
                        "attempt_id": None,
                        "status": None,
                    })
                elif current["status"] not in (
                    RunStatus.COMPLETED.value,
                    RunStatus.FAILED.value,
                    RunStatus.CANCELED.value,
                ):
                    records.append({
                        "cell_id": cell["cell_id"],
                        "attempt_id": current["run_id"],
                        "status": current["status"],
                    })
            return records
        finally:
            conn.close()

    def aggregate_status(self) -> str:
        """The experiment's aggregate status via ``derive_experiment_status``.

        Exact precedence: any queued/running → ``running``; else interrupted →
        ``interrupted``; else canceled → ``canceled``; else failed →
        ``completed_with_failures``; else ``completed``.  Requires an
        experiment-bound repository.
        """
        experiment_id = self._require_experiment_scope()
        conn = self._store.connect()
        try:
            cells = [
                self._row_to_cell(c)
                for c in self._fixed_order_cells(conn, experiment_id)
            ]
            return derive_experiment_status(cells)
        finally:
            conn.close()


    # ── Request snapshots ───────────────────────────────────────────────

    def create_request_snapshot(
        self,
        *,
        workflow_json: dict[str, Any],
        generation_params: Optional[dict[str, Any]] = None,
        workflow_hash: Optional[str] = None,
        workflow_version_id: Optional[str] = None,
        preset_snapshot: Optional[dict[str, Any]] = None,
        generation_id: Optional[str] = None,
        created_at: Optional[str] = None,
        request: Optional[dict[str, Any]] = None,
        execution_plan: Optional[dict[str, Any]] = None,
        deployment_identity: Optional[dict[str, Any]] = None,
    ) -> RequestSnapshot:
        snapshot_id = new_id("snap_")
        now = created_at or utc_now_iso()
        workflow = dict(workflow_json)
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO request_snapshots (
                    snapshot_id, generation_id, schema_version, workflow_json,
                    workflow_hash, workflow_version_id, generation_params_json,
                    preset_snapshot_json, request_json, execution_plan_json,
                    deployment_identity_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (snapshot_id, generation_id, 1, _compact_json(workflow),
                 workflow_hash, workflow_version_id,
                 _compact_json(dict(generation_params or {})),
                 _compact_json(dict(preset_snapshot or {})),
                 _compact_json(dict(request or {})),
                 _compact_json(dict(execution_plan or {})),
                 _compact_json(dict(deployment_identity or {})), now),
            )
            if generation_id:
                conn.execute(
                    "UPDATE generations SET request_snapshot_id = ?, updated_at = ? "
                    "WHERE generation_id = ?",
                    (snapshot_id, now, generation_id),
                )
        return RequestSnapshot(
            snapshot_id=snapshot_id,
            created_at=now,
            workflow=workflow,
            generation_id=generation_id,
            schema_version=1,
            workflow_hash=workflow_hash,
            workflow_version_id=workflow_version_id,
            generation_params=dict(generation_params or {}),
            preset_snapshot=dict(preset_snapshot or {}),
            request=dict(request or {}),
            execution_plan=dict(execution_plan or {}),
            deployment_identity=dict(deployment_identity or {}),
        )

    def get_snapshots_for_generations(
        self, generation_ids: Sequence[str]
    ) -> list[RequestSnapshot]:
        """Batch request-snapshot lookup keyed by generation_id."""
        if not generation_ids:
            return []
        ids = list(dict.fromkeys(generation_ids))
        placeholders = ",".join("?" * len(ids))
        conn = self._store.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM request_snapshots WHERE generation_id IN ({placeholders}) "
                "ORDER BY created_at ASC",
                ids,
            ).fetchall()
            return [self._row_to_snapshot(r) for r in rows]
        finally:
            conn.close()

    # ── Queries ─────────────────────────────────────────────────────────

    @staticmethod
    def _encode_cursor(
        created_at: str, item_id: str, key: Optional[Any] = None
    ) -> str:
        """Base64 cursor: ``{"k": sort_key|None, "created_at", "id"}``."""
        payload = _compact_json({"k": key, "created_at": created_at, "id": item_id})
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decode_cursor(cursor: Optional[str]) -> Optional[tuple[Any, str, str]]:
        """Decode a cursor to ``(key, created_at, id)``.

        Legacy cursors (produced before the ``"k"`` field existed) decode with
        ``key=None`` so they stay backward compatible.
        """
        if not cursor:
            return None
        try:
            payload = json.loads(
                base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
            )
            return payload.get("k"), str(payload["created_at"]), str(payload["id"])
        except Exception:
            raise ValueError("invalid cursor") from None

    @staticmethod
    def _cursor_sort_key(order: str, row: Any) -> Any:
        """Sort key to embed in a keyset cursor, matching the SQL total order.

        Column access is safe for both sqlite rows and plain dicts; missing
        columns fall back to the other kind's key column (generations have no
        ``name``, experiments have no ``workflow_id``).
        """
        if order in ("fastest", "slowest"):
            return row["duration_ms"]
        if order in ("workflow_asc", "workflow_desc"):
            try:
                key = row["workflow_id"]
            except Exception:
                key = None
            if key is None:
                try:
                    key = row["name"]
                except Exception:
                    key = None
            return key
        return None

    def query_generations(
        self,
        *,
        cursor: Optional[str] = None,
        limit: int = 50,
        order: str = "newest",
        search: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        workflow_id: Optional[str] = None,
        preset_id: Optional[str] = None,
        favorite: Optional[bool] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        has_preview: Optional[bool] = None,
        has_original: Optional[bool] = None,
        preview_only: Optional[bool] = None,
        interrupted: Optional[bool] = None,
        failed_or_canceled: Optional[bool] = None,
        model_name: Optional[str] = None,
        has_image: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Keyset-paginated generation query.

        Supports six orders: ``newest``, ``oldest``, ``fastest``, ``slowest``,
        ``workflow_asc`` and ``workflow_desc``.  ``cursor`` is a base64-encoded
        ``{"k", "created_at", "id"}`` JSON payload.  Returns ``{"items":
        [Generation dicts incl. a computed "duration_ms"], "next_cursor":
        str|None, "limit": int, "total": int}``.
        """
        limit = int(limit)
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        if order not in _ORDERS:
            raise ValueError(
                "order must be one of 'newest', 'oldest', 'fastest', 'slowest', "
                "'workflow_asc', 'workflow_desc'"
            )

        where: list[str] = []
        params: list[Any] = []

        if status is not None:
            where.append("g.status = ?")
            params.append(status)
        if statuses:
            statuses = list(statuses)
            where.append(f"g.status IN ({','.join('?' * len(statuses))})")
            params.extend(statuses)
        if workflow_id is not None:
            where.append("g.workflow_id = ?")
            params.append(workflow_id)
        if preset_id is not None:
            where.append("g.preset_id = ?")
            params.append(preset_id)
        if favorite is not None:
            where.append("g.favorite = ?")
            params.append(1 if favorite else 0)
        if date_from is not None:
            where.append("g.created_at >= ?")
            params.append(date_from)
        if date_to is not None:
            where.append("g.created_at <= ?")
            params.append(date_to)
        if search:
            escaped = _escape_like(search)
            like = f"%{escaped}%"
            # Search also covers the authoritative workflow display-name
            # representations surfaced by history_v2_routes._workflow_name
            # (request snapshot workflow_json top-level name/title,
            # workflow_json.extra.workflow.name/title, and the preset
            # snapshot's workflow_name fallback) — matching exactly the
            # snapshot the routes read via generation.request_snapshot_id.
            where.append(
                "(g.generation_id LIKE ? ESCAPE '\\' OR g.workflow_id LIKE ? ESCAPE '\\' "
                "OR g.preset_id LIKE ? ESCAPE '\\' OR g.preset_name LIKE ? ESCAPE '\\' "
                "OR g.prompt_text LIKE ? ESCAPE '\\' OR g.negative_prompt_text LIKE ? ESCAPE '\\' "
                "OR g.note LIKE ? ESCAPE '\\' "
                "OR EXISTS (SELECT 1 FROM request_snapshots s "
                "WHERE s.snapshot_id = g.request_snapshot_id AND ("
                "json_extract(s.workflow_json, '$.name') LIKE ? ESCAPE '\\' "
                "OR json_extract(s.workflow_json, '$.title') LIKE ? ESCAPE '\\' "
                "OR json_extract(s.workflow_json, '$.extra.workflow.name') LIKE ? ESCAPE '\\' "
                "OR json_extract(s.workflow_json, '$.extra.workflow.title') LIKE ? ESCAPE '\\' "
                "OR json_extract(s.preset_snapshot_json, '$.workflow_name') LIKE ? ESCAPE '\\')))"
            )
            params.extend([like] * 12)
        if has_preview:
            where.append(
                "EXISTS (SELECT 1 FROM assets a WHERE a.generation_id = g.generation_id "
                "AND a.type = 'preview')"
            )
        if has_original:
            where.append(
                "EXISTS (SELECT 1 FROM assets a WHERE a.generation_id = g.generation_id "
                "AND a.type = 'original')"
            )
        if preview_only:
            where.append(
                "EXISTS (SELECT 1 FROM assets a WHERE a.generation_id = g.generation_id "
                "AND a.type = 'preview') AND NOT EXISTS (SELECT 1 FROM assets a "
                "WHERE a.generation_id = g.generation_id AND a.type = 'original')"
            )
        if interrupted:
            where.append(
                "EXISTS (SELECT 1 FROM run_attempts a WHERE a.generation_id = g.generation_id "
                "AND a.status = 'interrupted')"
            )
        if failed_or_canceled:
            where.append(
                "EXISTS (SELECT 1 FROM run_attempts a WHERE a.generation_id = g.generation_id "
                "AND a.status IN ('failed','canceled'))"
            )
        if model_name:
            # Best-effort containment check over model_stack_json; documented
            # as "where metadata supports it".
            escaped_name = _escape_like(model_name)
            where.append("g.model_stack_json LIKE ? ESCAPE '\\'")
            params.append(f'%"{escaped_name}"%')
        if has_image:
            where.append(
                "EXISTS (SELECT 1 FROM assets a WHERE a.generation_id = g.generation_id "
                "AND a.type IN ('thumbnail','preview','original'))"
            )

        where_clause = " AND ".join(where) if where else "1=1"

        order_by, keyset_fn = _keyset_order(
            order,
            id_col="generation_id",
            key_col="COALESCE(workflow_id, '')",
            flag_sql="(workflow_id IS NULL OR workflow_id = '')",
        )

        conn = self._store.connect()
        try:
            total_row = conn.execute(
                f"SELECT COUNT(*) FROM generations g WHERE {where_clause}",
                params,
            ).fetchone()
            total = int(total_row[0]) if total_row else 0

            sql = (
                f"SELECT * FROM (SELECT g.*, {_GEN_DURATION_SQL} AS duration_ms "
                f"FROM generations g WHERE {where_clause}) q"
            )
            decoded = self._decode_cursor(cursor)
            if decoded is not None:
                key, cursor_created_at, cursor_id = decoded
                if (
                    order in ("fastest", "slowest", "workflow_asc", "workflow_desc")
                    and key is None
                    and not _cursor_has_key(cursor)
                ):
                    # Documented legacy fallback: cursors produced before the
                    # "k" field existed were only ever created under
                    # newest/oldest, so under a non-time order continue with
                    # the oldest-style predicate.
                    pred = "(created_at, generation_id) > (?, ?)"
                    pred_params = [cursor_created_at, cursor_id]
                else:
                    pred, pred_params = keyset_fn(key, cursor_created_at, cursor_id)
                sql += f" WHERE {pred}"
                params = params + pred_params
            sql += f" ORDER BY {order_by} LIMIT ?"
            rows = conn.execute(sql, params + [limit + 1]).fetchall()
            has_next = len(rows) > limit
            items_rows = rows[:limit]
            next_cursor = None
            if has_next and items_rows:
                last = items_rows[-1]
                sort_key = self._cursor_sort_key(order, last)
                next_cursor = self._encode_cursor(
                    last["created_at"], last["generation_id"], sort_key
                )
            items = [
                dict(self._row_to_generation(r).to_dict(), duration_ms=r["duration_ms"])
                for r in items_rows
            ]
            return {
                "items": items,
                "next_cursor": next_cursor,
                "limit": limit,
                "total": total,
            }
        finally:
            conn.close()

    def query_experiments(
        self,
        *,
        cursor: Optional[str] = None,
        limit: int = 50,
        order: str = "newest",
        status: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        search: Optional[str] = None,
        favorite: Optional[bool] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """Keyset-paginated experiment query (same six orders as generations).

        For ``workflow_asc``/``workflow_desc`` the experiment "workflow" sort
        key is its name (``COALESCE(NULLIF(name, ''), '')``) — the sensible
        equivalent of a generation's workflow_id.  ``favorite`` mirrors the
        generation filter exactly (True → favorited only, False → truthful
        inverse, None → no predicate); it is applied inside this SQL query so
        keyset/mixed pagination stays truthful.
        """
        limit = int(limit)
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        if order not in _ORDERS:
            raise ValueError(
                "order must be one of 'newest', 'oldest', 'fastest', 'slowest', "
                "'workflow_asc', 'workflow_desc'"
            )

        where: list[str] = []
        params: list[Any] = []

        if status is not None:
            where.append("e.status = ?")
            params.append(status)
        if statuses:
            statuses = list(statuses)
            where.append(f"e.status IN ({','.join('?' * len(statuses))})")
            params.extend(statuses)
        if favorite is not None:
            where.append("e.favorite = ?")
            params.append(1 if favorite else 0)
        if date_from is not None:
            where.append("e.created_at >= ?")
            params.append(date_from)
        if date_to is not None:
            where.append("e.created_at <= ?")
            params.append(date_to)
        if search:
            escaped = _escape_like(search)
            like = f"%{escaped}%"
            where.append(
                "(e.experiment_id LIKE ? ESCAPE '\\' OR e.name LIKE ? ESCAPE '\\' "
                "OR e.definition_json LIKE ? ESCAPE '\\')"
            )
            params.extend([like] * 3)

        where_clause = " AND ".join(where) if where else "1=1"

        order_by, keyset_fn = _keyset_order(
            order,
            id_col="experiment_id",
            key_col="COALESCE(NULLIF(name, ''), '')",
            flag_sql="(name IS NULL OR name = '')",
        )

        conn = self._store.connect()
        try:
            total_row = conn.execute(
                f"SELECT COUNT(*) FROM experiments e WHERE {where_clause}",
                params,
            ).fetchone()
            total = int(total_row[0]) if total_row else 0

            sql = (
                f"SELECT * FROM (SELECT e.*, {_EXP_DURATION_SQL} AS duration_ms "
                f"FROM experiments e WHERE {where_clause}) q"
            )
            decoded = self._decode_cursor(cursor)
            if decoded is not None:
                key, cursor_created_at, cursor_id = decoded
                if (
                    order in ("fastest", "slowest", "workflow_asc", "workflow_desc")
                    and key is None
                    and not _cursor_has_key(cursor)
                ):
                    pred = "(created_at, experiment_id) > (?, ?)"
                    pred_params = [cursor_created_at, cursor_id]
                else:
                    pred, pred_params = keyset_fn(key, cursor_created_at, cursor_id)
                sql += f" WHERE {pred}"
                params = params + pred_params
            sql += f" ORDER BY {order_by} LIMIT ?"
            rows = conn.execute(sql, params + [limit + 1]).fetchall()
            has_next = len(rows) > limit
            items_rows = rows[:limit]
            next_cursor = None
            if has_next and items_rows:
                last = items_rows[-1]
                sort_key = self._cursor_sort_key(order, last)
                next_cursor = self._encode_cursor(
                    last["created_at"], last["experiment_id"], sort_key
                )
            items = [
                dict(self._row_to_experiment(r).to_dict(), duration_ms=r["duration_ms"])
                for r in items_rows
            ]
            return {
                "items": items,
                "next_cursor": next_cursor,
                "limit": limit,
                "total": total,
            }
        finally:
            conn.close()

    def query_history(
        self, *, item_type: str = "generation", **filters: Any
    ) -> dict[str, Any]:
        """Route a query to generations or experiments by ``item_type``."""
        if item_type == "generation":
            return self.query_generations(**filters)
        if item_type == "experiment":
            return self.query_experiments(**filters)
        raise ValueError(
            f"unknown item_type: {item_type!r} (expected 'generation' or 'experiment')"
        )

    # ── Legacy migration support (used by history_v2_migration) ─────────

    def _legacy_mapping_exists(self, legacy_run_id: str) -> bool:
        conn = self._store.connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM legacy_mapping WHERE legacy_run_id = ?",
                (legacy_run_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def _record_legacy_mapping(
        self, legacy_run_id: str, generation_id: str, source: str
    ) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO legacy_mapping
                   (legacy_run_id, generation_id, source, migrated_at)
                   VALUES (?,?,?,?)""",
                (legacy_run_id, generation_id, source, utc_now_iso()),
            )
