"""History V2 data models.

Pure data-model definitions (enums, frozen dataclasses, status-derivation
helpers) for the studio's History V2 persistence layer.  This module is
stdlib-only and importable standalone; it must never import anything from
the rest of the repo.

Conventions:
- UTC ISO-8601 timestamps with millisecond precision.
- Frozen dataclasses with ``to_dict()`` / ``from_dict()`` round-trips.
- All list/dict fields use ``field(default_factory=...)``.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ── Time / id helpers ────────────────────────────────────────────────────


def utc_now_iso() -> str:
    """UTC ISO-8601 timestamp with millisecond precision (repo convention)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    """Short random id like ``gen_4f2a9c0d1e3b``."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def normalize_logical_output_key(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def build_logical_output_key(
    node_id: Any, output_key: Any, output_index: Any = 0
) -> Optional[str]:
    node = normalize_logical_output_key(node_id)
    slot = normalize_logical_output_key(output_key)
    if not node or not slot or isinstance(output_index, bool):
        return None
    try:
        item_index = int(output_index)
    except (TypeError, ValueError):
        return None
    if item_index < 0:
        return None
    return f"node:{node}:slot:{slot}:item:{item_index}"


def logical_output_key_from_metadata(
    metadata: Optional[dict[str, Any]],
) -> Optional[str]:
    if not isinstance(metadata, dict):
        return None
    explicit = normalize_logical_output_key(metadata.get("logical_output_key"))
    if explicit:
        return explicit
    output_index = metadata.get("output_index")
    if output_index is None:
        output_index = metadata.get("item_index")
    if output_index is None:
        output_index = metadata.get("batch_index", 0)
    return build_logical_output_key(
        metadata.get("node_id") or metadata.get("output_node_id"),
        metadata.get("output_key") or metadata.get("output_slot"),
        output_index,
    )


# ── Enums ─────────────────────────────────────────────────────────────────


class AssetType(str, Enum):
    THUMBNAIL = "thumbnail"
    PREVIEW = "preview"
    ORIGINAL = "original"
    INPUT = "input"
    MASK = "mask"
    SECONDARY = "secondary"


class RunMode(str, Enum):
    PREVIEW = "preview"
    ORIGINAL = "original"
    SECONDARY = "secondary"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    INTERRUPTED = "interrupted"


RUN_STATUS_VALUES = frozenset(status.value for status in RunStatus)
TERMINAL_RUN_STATUSES = frozenset({
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELED,
    RunStatus.INTERRUPTED,
})


class GenerationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    INTERRUPTED = "interrupted"


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    INTERRUPTED = "interrupted"
    CANCELED = "canceled"


class CellStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELED = "canceled"
    SKIPPED = "skipped"


class ExportState(str, Enum):
    NOT_EXPORTED = "not_exported"
    EXPORTED = "exported"
    MISSING = "missing"
    FAILED = "failed"


# ── Status derivation (pure functions) ───────────────────────────────────


def current_attempt(attempts: list["RunAttempt"]) -> Optional["RunAttempt"]:
    """Return the CURRENT (latest) run attempt by ``(created_at, run_id)``.

    The tie-break on ``run_id`` keeps the ordering deterministic when two
    attempts share a ``created_at`` stamp.  ``None`` when there are none.
    """
    if not attempts:
        return None
    return max(attempts, key=lambda a: (a.created_at, a.run_id))


# Claim outcomes for ``HistoryV2Repository.claim_attempt``.
CLAIM_CLAIMED = "claimed"
CLAIM_ALREADY_CLAIMED = "already_claimed"
CLAIM_TERMINAL = "terminal"
CLAIM_NOT_FOUND = "not_found"


def derive_generation_status(attempts: list["RunAttempt"]) -> str:
    """Derive a generation's status from its run attempts.

    A generation's status is *derived* — never stored independently — from
    the statuses of its attempts.  Per-attempt failure visibility is
    preserved even when a generation shows ``"completed"`` because a preview
    (or an earlier retry) succeeded: the failed attempt itself still carries
    its ``status``/``error``.
    """
    statuses = [attempt.status for attempt in attempts]
    if any(s in (RunStatus.QUEUED.value, RunStatus.RUNNING.value) for s in statuses):
        return GenerationStatus.RUNNING.value
    if any(s == RunStatus.COMPLETED.value for s in statuses):
        return GenerationStatus.COMPLETED.value
    if any(s == RunStatus.INTERRUPTED.value for s in statuses):
        return GenerationStatus.INTERRUPTED.value
    if any(s == RunStatus.FAILED.value for s in statuses):
        return GenerationStatus.FAILED.value
    if any(s == RunStatus.CANCELED.value for s in statuses):
        return GenerationStatus.CANCELED.value
    return GenerationStatus.PENDING.value


def derive_cell_status(attempts: list["RunAttempt"]) -> str:
    """Derive a cell's status from its CURRENT (latest) run attempt.

    The current attempt is authoritative: queued/running are in-flight, and a
    stale OLDER terminal attempt can never overwrite a newer Retry/Resume
    state.  Per-attempt, terminal first-wins is enforced at write time (a
    terminal attempt is never reopened).  A cell with no attempts keeps the
    legacy ``"pending"`` value so old records still read.
    """
    current = current_attempt(attempts)
    if current is None:
        return CellStatus.PENDING.value
    status = current.status
    if status == RunStatus.QUEUED.value:
        return CellStatus.QUEUED.value
    if status == RunStatus.RUNNING.value:
        return CellStatus.RUNNING.value
    if status == RunStatus.COMPLETED.value:
        return CellStatus.COMPLETED.value
    if status == RunStatus.INTERRUPTED.value:
        return CellStatus.INTERRUPTED.value
    if status == RunStatus.FAILED.value:
        return CellStatus.FAILED.value
    if status == RunStatus.CANCELED.value:
        return CellStatus.CANCELED.value
    return CellStatus.PENDING.value


def derive_experiment_status(cells: list["ExperimentCell"]) -> str:
    """Derive an experiment's aggregate status from its cells.

    An experiment's status is derived from the statuses of its cells.  The
    rules, applied strictly in order:

    1. any cell status ``"queued"``/``"running"`` (and legacy ``"pending"``,
       which aggregates as queued) → ``"running"`` — work is in flight
    2. else any cell status ``"interrupted"`` → ``"interrupted"``
    3. else any cell status ``"canceled"`` → ``"canceled"``
    4. else any cell status ``"failed"`` → ``"completed_with_failures"``
    5. else → ``"completed"``

    ``"skipped"`` cells are terminal and non-failed: they fall through every
    rule above and never block completion.  Examples:

    - 40 completed → ``"completed"``
    - 38 completed, 2 failed → ``"completed_with_failures"``
    - 30 completed, 2 failed, 8 interrupted → ``"interrupted"``
    - resumed: 38 completed, 2 failed → ``"completed_with_failures"``

    ``failed`` is the explicit fatal state and is *never* produced by
    derivation — it is only ever set explicitly via ``set_experiment_status``.
    A fresh experiment keeps ``"draft"`` until the first cell-affecting
    update, and an explicit ``set_experiment_status`` override remains in
    effect until the next cell update triggers a recomputation.
    """
    statuses = [cell.status for cell in cells]
    if any(
        s in (CellStatus.QUEUED.value, CellStatus.RUNNING.value, CellStatus.PENDING.value)
        for s in statuses
    ):
        return ExperimentStatus.RUNNING.value
    if any(s == CellStatus.INTERRUPTED.value for s in statuses):
        return ExperimentStatus.INTERRUPTED.value
    if any(s == CellStatus.CANCELED.value for s in statuses):
        return ExperimentStatus.CANCELED.value
    if any(s == CellStatus.FAILED.value for s in statuses):
        return ExperimentStatus.COMPLETED_WITH_FAILURES.value
    return ExperimentStatus.COMPLETED.value


# ── Frozen dataclasses ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Generation:
    generation_id: str
    created_at: str
    status: str
    workflow_id: Optional[str] = None
    workflow_version_id: Optional[str] = None
    preset_id: Optional[str] = None
    preset_name: Optional[str] = None
    request_snapshot_id: Optional[str] = None
    experiment_id: Optional[str] = None
    featured_asset_id: Optional[str] = None
    favorite: bool = False
    note: str = ""
    prompt_text: str = ""
    negative_prompt_text: str = ""
    model_stack: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Generation":
        return cls(
            generation_id=data["generation_id"],
            created_at=data["created_at"],
            status=data["status"],
            workflow_id=data.get("workflow_id"),
            workflow_version_id=data.get("workflow_version_id"),
            preset_id=data.get("preset_id"),
            preset_name=data.get("preset_name"),
            request_snapshot_id=data.get("request_snapshot_id"),
            experiment_id=data.get("experiment_id"),
            featured_asset_id=data.get("featured_asset_id"),
            favorite=bool(data.get("favorite", False)),
            note=data.get("note", "") or "",
            prompt_text=data.get("prompt_text", "") or "",
            negative_prompt_text=data.get("negative_prompt_text", "") or "",
            model_stack=list(data.get("model_stack") or []),
            updated_at=data.get("updated_at", "") or "",
        )


@dataclass(frozen=True)
class RunAttempt:
    run_id: str
    generation_id: str
    mode: str
    status: str
    created_at: str
    experiment_id: Optional[str] = None
    cell_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    timing: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunAttempt":
        return cls(
            run_id=data["run_id"],
            generation_id=data["generation_id"],
            mode=data["mode"],
            status=data["status"],
            created_at=data["created_at"],
            experiment_id=data.get("experiment_id"),
            cell_id=data.get("cell_id"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            error=data.get("error"),
            timing=dict(data.get("timing") or {}),
        )


@dataclass(frozen=True)
class Asset:
    asset_id: str
    generation_id: str
    type: str
    managed_path: str
    filename: str
    created_at: str
    run_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None
    sha256: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    logical_output_key: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Asset":
        return cls(
            asset_id=data["asset_id"],
            generation_id=data["generation_id"],
            type=data["type"],
            managed_path=data["managed_path"],
            filename=data["filename"],
            created_at=data["created_at"],
            run_id=data.get("run_id"),
            width=data.get("width"),
            height=data.get("height"),
            format=data.get("format"),
            sha256=data.get("sha256"),
            metadata=dict(data.get("metadata") or {}),
            logical_output_key=normalize_logical_output_key(
                data.get("logical_output_key")
            ),
        )


@dataclass(frozen=True)
class ExportRecord:
    export_id: str
    asset_id: str
    state: str
    updated_at: str
    destination_path: Optional[str] = None
    exported_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExportRecord":
        return cls(
            export_id=data["export_id"],
            asset_id=data["asset_id"],
            state=data["state"],
            updated_at=data["updated_at"],
            destination_path=data.get("destination_path"),
            exported_at=data.get("exported_at"),
        )


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    status: str
    created_at: str
    updated_at: str
    name: Optional[str] = None
    definition: dict[str, Any] = field(default_factory=dict)
    cell_ordering: list[str] = field(default_factory=list)
    expected_cell_count: int = 0
    favorite: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Experiment":
        return cls(
            experiment_id=data["experiment_id"],
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            name=data.get("name"),
            definition=dict(data.get("definition") or {}),
            cell_ordering=list(data.get("cell_ordering") or []),
            expected_cell_count=int(data.get("expected_cell_count") or 0),
            favorite=bool(data.get("favorite", False)),
            note=data.get("note", "") or "",
        )


@dataclass(frozen=True)
class ExperimentCell:
    cell_id: str
    experiment_id: str
    position: int
    status: str
    updated_at: str
    axis_labels: dict[str, Any] = field(default_factory=dict)
    generation_id: Optional[str] = None
    attempt_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentCell":
        return cls(
            cell_id=data["cell_id"],
            experiment_id=data["experiment_id"],
            position=int(data.get("position") or 0),
            status=data["status"],
            updated_at=data["updated_at"],
            axis_labels=dict(data.get("axis_labels") or {}),
            generation_id=data.get("generation_id"),
            attempt_ids=list(data.get("attempt_ids") or []),
            error=data.get("error"),
        )


@dataclass(frozen=True)
class RequestSnapshot:
    snapshot_id: str
    created_at: str
    workflow: dict[str, Any] = field(default_factory=dict)
    generation_id: Optional[str] = None
    schema_version: int = 1
    workflow_hash: Optional[str] = None
    workflow_version_id: Optional[str] = None
    generation_params: dict[str, Any] = field(default_factory=dict)
    preset_snapshot: dict[str, Any] = field(default_factory=dict)
    request: dict[str, Any] = field(default_factory=dict)
    execution_plan: dict[str, Any] = field(default_factory=dict)
    deployment_identity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RequestSnapshot":
        return cls(
            snapshot_id=data["snapshot_id"],
            created_at=data["created_at"],
            workflow=dict(data.get("workflow") or {}),
            generation_id=data.get("generation_id"),
            schema_version=int(data.get("schema_version") or 1),
            workflow_hash=data.get("workflow_hash"),
            workflow_version_id=data.get("workflow_version_id"),
            generation_params=dict(data.get("generation_params") or {}),
            preset_snapshot=dict(data.get("preset_snapshot") or {}),
            request=dict(data.get("request") or {}),
            execution_plan=dict(data.get("execution_plan") or {}),
            deployment_identity=dict(data.get("deployment_identity") or {}),
        )


@dataclass(frozen=True)
class ClaimResult:
    """Non-throwing result of an atomic attempt claim.

    ``outcome`` is one of ``CLAIM_CLAIMED``, ``CLAIM_ALREADY_CLAIMED``,
    ``CLAIM_TERMINAL`` or ``CLAIM_NOT_FOUND`` (see the module constants).
    ``attempt`` carries the resulting (actually stored) attempt row, or None
    for ``CLAIM_NOT_FOUND``.
    """

    outcome: str
    attempt: Optional["RunAttempt"] = None


@dataclass(frozen=True)
class GenerationDetail:
    generation: Generation
    attempts: list[RunAttempt] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    export_records: list[ExportRecord] = field(default_factory=list)
    request_snapshot: Optional[RequestSnapshot] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GenerationDetail":
        return cls(
            generation=Generation.from_dict(data["generation"]),
            attempts=[RunAttempt.from_dict(a) for a in data.get("attempts") or []],
            assets=[Asset.from_dict(a) for a in data.get("assets") or []],
            export_records=[
                ExportRecord.from_dict(e) for e in data.get("export_records") or []
            ],
            request_snapshot=(
                RequestSnapshot.from_dict(data["request_snapshot"])
                if data.get("request_snapshot")
                else None
            ),
        )


@dataclass(frozen=True)
class ExperimentDetail:
    experiment: Experiment
    cells: list[ExperimentCell] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentDetail":
        return cls(
            experiment=Experiment.from_dict(data["experiment"]),
            cells=[ExperimentCell.from_dict(c) for c in data.get("cells") or []],
        )
