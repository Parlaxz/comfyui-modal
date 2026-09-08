"""Pure immutable replay core for History V2 Generate Original.

This module deliberately stops before repository mutation and remote execution.
It validates the raw serialized snapshot before ``ExecutionPlan.from_dict`` can
fill defaults, then produces an Attempt-scoped output-intent copy for the later
History route/service integration.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan


REASON_MISSING_REQUEST_SNAPSHOT = "missing_request_snapshot"
REASON_MISSING_EXECUTION_PLAN = "missing_execution_plan"
REASON_MISSING_WORKFLOW = "missing_workflow"
REASON_MISSING_WORKFLOW_HASH = "missing_workflow_hash"
REASON_MISSING_SOURCE_WORKFLOW_HASH = "missing_source_workflow_hash"
REASON_MISSING_EXECUTION_OPTIONS = "missing_execution_options"
REASON_MISSING_OUTPUT_NODE_IDENTITY = "missing_output_node_identity"
REASON_MISSING_REQUEST = "missing_request"
REASON_MISSING_IDENTITY = "missing_identity"
REASON_MISSING_VALIDATION_PROOF = "missing_validation_proof"
REASON_MISSING_DEPLOYMENT_IDENTITY = "missing_deployment_identity"
REASON_IDENTITY_MISMATCH = "identity_mismatch"
REASON_INVALID_PLAN = "invalid_plan"
REASON_UNSUPPORTED_SNAPSHOT_SCHEMA = "unsupported_snapshot_schema"
REASON_SNAPSHOT_WORKFLOW_MISMATCH = "snapshot_workflow_mismatch"
REASON_SNAPSHOT_HASH_MISMATCH = "snapshot_hash_mismatch"
REASON_SNAPSHOT_DEPLOYMENT_MISMATCH = "snapshot_deployment_mismatch"
REASON_NOT_ORIGINAL_FAILURE = "not_failed_original"
REASON_GENERATION_MISMATCH = "generation_mismatch"
REASON_SNAPSHOT_MISMATCH = "snapshot_mismatch"

CURRENT_PLAN_SCHEMA_VERSION = int(ExecutionPlan().schema_version)
REQUIRED_EXECUTION_OPTION_KEYS = frozenset(ExecutionOptions().to_dict().keys())
CORRELATION_METADATA_KEYS = frozenset({
    "attempt_id",
    "correlation_id",
    "history_attempt_id",
    "origin_attempt_id",
    "prompt_id",
    "request_id",
    "run_id",
    "trace_id",
})


def _plain_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_copy(item) for item in value]
    return value


def _object_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _snapshot_parts(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    if not isinstance(snapshot, Mapping) and hasattr(snapshot, "request_snapshot"):
        snapshot = getattr(snapshot, "request_snapshot", None)
    if snapshot is None:
        return None
    if isinstance(snapshot, Mapping):
        source = snapshot

        def value(name: str, alias: str) -> Any:
            return source.get(name, source.get(alias))

    else:
        source = snapshot

        def value(name: str, alias: str) -> Any:
            result = getattr(source, name, None)
            return result if result is not None else getattr(source, alias, None)

    return {
        "schema_version": value("schema_version", "schema_version"),
        "workflow": value("workflow", "workflow_json"),
        "workflow_hash": value("workflow_hash", "workflow_hash"),
        "workflow_version_id": value("workflow_version_id", "workflow_version_id"),
        "request": value("request", "request_json"),
        "execution_plan": value("execution_plan", "execution_plan_json"),
        "deployment_identity": value(
            "deployment_identity", "deployment_identity_json"
        ),
        "preset_snapshot": value("preset_snapshot", "preset_snapshot_json"),
        "generation_params": value("generation_params", "generation_params_json"),
        "snapshot_id": value("snapshot_id", "snapshot_id"),
    }


@dataclass(frozen=True)
class ReplayCapability:
    """Raw-snapshot capability result; no plan deserialization occurs here."""

    capable: bool
    reason: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.capable

    @property
    def replay_capable(self) -> bool:
        return self.capable

    def to_dict(self) -> dict[str, Any]:
        return {
            "capable": self.capable,
            "reason": self.reason,
            "details": _plain_copy(self.details),
        }


class ReplayCapabilityError(ValueError):
    """Raised only by the explicit plan-loading API after validation fails."""

    def __init__(self, capability: ReplayCapability):
        self.capability = capability
        super().__init__(capability.reason or REASON_INVALID_PLAN)


def _fail(reason: str, **details: Any) -> ReplayCapability:
    return ReplayCapability(False, reason, details)


def _identity_values(
    name: str,
    *,
    plan: Mapping[str, Any],
    request: Mapping[str, Any],
    preset_snapshot: Mapping[str, Any],
    generation_params: Mapping[str, Any],
    snapshot_identity: Mapping[str, Any],
    generation: Any,
) -> list[tuple[str, str]]:
    plan_meta = _mapping(plan.get("request_metadata")) or {}
    request_meta = _mapping(request.get("request_metadata")) or {}
    aliases = {
        "workflow_id": ("workflow_id",),
        "workflow_version_id": ("workflow_version_id", "version_id"),
        "preset_id": ("preset_id",),
    }[name]
    sources: list[tuple[str, Mapping[str, Any]]] = [
        ("plan.request_metadata", plan_meta),
        ("request", request),
        ("request.request_metadata", request_meta),
        ("preset_snapshot", preset_snapshot),
        ("generation_params", generation_params),
        ("snapshot", snapshot_identity),
    ]
    values: list[tuple[str, str]] = []
    for source_name, source in sources:
        for alias in aliases:
            value = source.get(alias)
            if value not in (None, ""):
                values.append((source_name, str(value)))
                break
    generation_value = _object_value(generation, name, None)
    if generation_value not in (None, ""):
        values.append(("generation", str(generation_value)))
    return values


def validate_replay_capability(
    snapshot: Any,
    *,
    generation: Any = None,
    require_deployment_identity: bool = True,
) -> ReplayCapability:
    """Validate a raw RequestSnapshot without calling ``ExecutionPlan.from_dict``."""
    parts = _snapshot_parts(snapshot)
    if parts is None:
        return _fail(REASON_MISSING_REQUEST_SNAPSHOT)

    snapshot_schema = parts.get("schema_version")
    if snapshot_schema not in (None, 1):
        return _fail(REASON_UNSUPPORTED_SNAPSHOT_SCHEMA, schema_version=snapshot_schema)

    raw_plan = _mapping(parts.get("execution_plan"))
    if not raw_plan:
        return _fail(REASON_MISSING_EXECUTION_PLAN)

    plan_schema = raw_plan.get("schema_version")
    if plan_schema != CURRENT_PLAN_SCHEMA_VERSION:
        return _fail(REASON_UNSUPPORTED_SNAPSHOT_SCHEMA, plan_schema=plan_schema)

    workflow = _mapping(raw_plan.get("workflow"))
    if not workflow:
        return _fail(REASON_MISSING_WORKFLOW)
    snapshot_workflow = _mapping(parts.get("workflow"))
    if not snapshot_workflow:
        return _fail(REASON_MISSING_WORKFLOW, location="snapshot.workflow")
    if _plain_copy(snapshot_workflow) != _plain_copy(workflow):
        return _fail(REASON_SNAPSHOT_WORKFLOW_MISMATCH)

    workflow_hash = raw_plan.get("workflow_hash")
    if not isinstance(workflow_hash, str) or not workflow_hash.strip():
        return _fail(REASON_MISSING_WORKFLOW_HASH)
    source_workflow_hash = raw_plan.get("source_workflow_hash")
    if not isinstance(source_workflow_hash, str) or not source_workflow_hash.strip():
        return _fail(REASON_MISSING_SOURCE_WORKFLOW_HASH)

    snapshot_hash = parts.get("workflow_hash")
    if not isinstance(snapshot_hash, str) or not snapshot_hash.strip():
        return _fail(REASON_MISSING_WORKFLOW_HASH, location="snapshot.workflow_hash")
    if snapshot_hash != workflow_hash:
        return _fail(
            REASON_SNAPSHOT_HASH_MISMATCH,
            snapshot_hash=snapshot_hash,
            plan_hash=workflow_hash,
        )

    options = _mapping(raw_plan.get("execution_options"))
    if options is None or not REQUIRED_EXECUTION_OPTION_KEYS.issubset(options.keys()):
        missing = sorted(REQUIRED_EXECUTION_OPTION_KEYS - set(options or {}))
        return _fail(REASON_MISSING_EXECUTION_OPTIONS, missing=missing)
    production = _mapping(options.get("production"))
    if production is None or "enabled" not in production:
        return _fail(REASON_MISSING_EXECUTION_OPTIONS, missing=["production.enabled"])

    output_node_ids = raw_plan.get("output_node_ids")
    if not isinstance(output_node_ids, Sequence) or isinstance(output_node_ids, (str, bytes)):
        return _fail(REASON_MISSING_OUTPUT_NODE_IDENTITY)
    if not any(str(node_id).strip() for node_id in output_node_ids):
        return _fail(REASON_MISSING_OUTPUT_NODE_IDENTITY)

    for field_name in (
        "production_report",
        "model_stack",
        "prompt_bundle",
        "input_images",
        "request_metadata",
    ):
        if _mapping(raw_plan.get(field_name)) is None:
            return _fail(REASON_INVALID_PLAN, field=field_name)

    validation = _mapping(raw_plan.get("validation"))
    if not validation:
        return _fail(REASON_MISSING_VALIDATION_PROOF)
    if "validated" in validation and validation.get("validated") is not True:
        return _fail(REASON_MISSING_VALIDATION_PROOF, validation="not_validated")

    deployment_identity = _mapping(raw_plan.get("deployment_identity"))
    production_enabled = bool(production.get("enabled"))
    if require_deployment_identity and production_enabled and not deployment_identity:
        return _fail(REASON_MISSING_DEPLOYMENT_IDENTITY, location="plan")
    snapshot_deployment = _mapping(parts.get("deployment_identity"))
    if require_deployment_identity and production_enabled and not snapshot_deployment:
        return _fail(REASON_MISSING_DEPLOYMENT_IDENTITY, location="snapshot")
    if snapshot_deployment is not None and deployment_identity is not None:
        if _plain_copy(snapshot_deployment) != _plain_copy(deployment_identity):
            return _fail(REASON_SNAPSHOT_DEPLOYMENT_MISMATCH)

    request = _mapping(parts.get("request"))
    if not request:
        return _fail(REASON_MISSING_REQUEST)
    preset_snapshot = _mapping(parts.get("preset_snapshot")) or {}
    generation_params = _mapping(parts.get("generation_params")) or {}
    snapshot_identity = {
        "workflow_version_id": parts.get("workflow_version_id"),
    }
    for identity_name in ("workflow_id", "workflow_version_id", "preset_id"):
        values = _identity_values(
            identity_name,
            plan=raw_plan,
            request=request,
            preset_snapshot=preset_snapshot,
            generation_params=generation_params,
            snapshot_identity=snapshot_identity,
            generation=generation,
        )
        if not values:
            return _fail(REASON_MISSING_IDENTITY, field=identity_name)
        unique = {value for _, value in values}
        if len(unique) != 1:
            return _fail(
                REASON_IDENTITY_MISMATCH,
                field=identity_name,
                values=[{"source": source, "value": value} for source, value in values],
            )

    request_hash = request.get("workflow_hash")
    if request_hash not in (None, "") and str(request_hash) != workflow_hash:
        return _fail(REASON_IDENTITY_MISMATCH, field="workflow_hash")
    request_source_hash = request.get("source_workflow_hash")
    if request_source_hash not in (None, "") and str(request_source_hash) != source_workflow_hash:
        return _fail(REASON_IDENTITY_MISMATCH, field="source_workflow_hash")

    return ReplayCapability(
        True,
        details={
            "workflow_hash": workflow_hash,
            "source_workflow_hash": source_workflow_hash,
            "production_enabled": production_enabled,
            "snapshot_id": parts.get("snapshot_id") or "",
        },
    )


def _validated_plan_from_snapshot(
    snapshot: Any,
    *,
    generation: Any = None,
    require_deployment_identity: bool = True,
) -> tuple[ReplayCapability, ExecutionPlan | None]:
    capability = validate_replay_capability(
        snapshot,
        generation=generation,
        require_deployment_identity=require_deployment_identity,
    )
    if not capability.capable:
        return capability, None
    parts = _snapshot_parts(snapshot)
    assert parts is not None
    raw_plan = _mapping(parts["execution_plan"])
    assert raw_plan is not None
    try:
        plan = ExecutionPlan.from_dict(_plain_copy(raw_plan))
    except Exception as exc:
        return _fail(REASON_INVALID_PLAN, error=str(exc)), None
    if plan.to_dict() != _plain_copy(raw_plan):
        return _fail(REASON_INVALID_PLAN, detail="plan_round_trip_mismatch"), None
    return capability, plan


def load_replay_plan(
    snapshot: Any,
    *,
    generation: Any = None,
    require_deployment_identity: bool = True,
) -> ExecutionPlan:
    """Validate raw snapshot data, then deserialize its exact saved plan."""
    capability, plan = _validated_plan_from_snapshot(
        snapshot,
        generation=generation,
        require_deployment_identity=require_deployment_identity,
    )
    if not capability.capable or plan is None:
        raise ReplayCapabilityError(capability)
    return plan


@dataclass(frozen=True)
class ReplayPreparation:
    capability: ReplayCapability
    saved_plan: ExecutionPlan | None = None
    original_plan: ExecutionPlan | None = None


def _original_options(options: ExecutionOptions) -> ExecutionOptions:
    updates: dict[str, Any] = {"output_conversion_options": {"format": "original"}}
    option_names = {item.name for item in fields(options)}
    if "output_intent" in option_names:
        updates["output_intent"] = "original"
    if "output_mode" in option_names:
        # Generate Original is the intentional semantic delta: a saved
        # Preview plan must execute and label as "original", not inherit
        # the frozen preview mode (which would re-derive preview defaults
        # in ExecutionOptions.__post_init__).
        updates["output_mode"] = "original"
    return replace(options, **updates)


def build_original_replay_plan(
    saved_plan: ExecutionPlan,
    *,
    request_id: Any = None,
    prompt_id: Any = None,
    correlation_metadata: Mapping[str, Any] | None = None,
) -> ExecutionPlan:
    """Create an Attempt-scoped Original copy without changing frozen inputs."""
    if not isinstance(saved_plan, ExecutionPlan):
        raise TypeError("build_original_replay_plan requires a validated ExecutionPlan")
    metadata = _replay_correlation_metadata(
        saved_plan,
        request_id=request_id,
        prompt_id=prompt_id,
        correlation_metadata=correlation_metadata,
    )
    return replace(
        saved_plan,
        execution_options=_original_options(saved_plan.execution_options),
        request_metadata=metadata,
    )


def _replay_correlation_metadata(
    saved_plan: ExecutionPlan,
    *,
    request_id: Any = None,
    prompt_id: Any = None,
    correlation_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge approved fresh correlation identity into a copy of the frozen
    request metadata.  Every supplied key must be correlation-approved;
    execution options are never touched here."""
    metadata = dict(saved_plan.request_metadata)
    supplied = dict(correlation_metadata or {})
    if request_id is not None:
        supplied["request_id"] = request_id
    if prompt_id is not None:
        supplied["prompt_id"] = prompt_id
    unsupported = sorted(set(supplied) - CORRELATION_METADATA_KEYS)
    if unsupported:
        raise ValueError(f"unsupported replay correlation fields: {unsupported}")
    for key, value in supplied.items():
        if value is not None:
            metadata[key] = value
    return metadata


def build_resume_replay_plan(
    saved_plan: ExecutionPlan,
    *,
    request_id: Any = None,
    prompt_id: Any = None,
    correlation_metadata: Mapping[str, Any] | None = None,
) -> ExecutionPlan:
    """Create an Attempt-scoped Resume copy that preserves the semantic mode.

    Resume means "re-execute the interrupted immutable request", NOT
    "Generate Original": the saved ExecutionPlan's ``execution_options``
    (including its semantic ``output_mode`` and output conversion options)
    are preserved verbatim.  Only explicitly approved fresh correlation
    identity differs from the frozen plan.
    """
    if not isinstance(saved_plan, ExecutionPlan):
        raise TypeError("build_resume_replay_plan requires a validated ExecutionPlan")
    metadata = _replay_correlation_metadata(
        saved_plan,
        request_id=request_id,
        prompt_id=prompt_id,
        correlation_metadata=correlation_metadata,
    )
    return replace(saved_plan, request_metadata=metadata)


def prepare_original_replay(
    snapshot: Any,
    *,
    generation: Any = None,
    require_deployment_identity: bool = True,
    request_id: Any = None,
    prompt_id: Any = None,
    correlation_metadata: Mapping[str, Any] | None = None,
) -> ReplayPreparation:
    """Run the complete raw-validation, round-trip, and copy sequence."""
    capability, saved_plan = _validated_plan_from_snapshot(
        snapshot,
        generation=generation,
        require_deployment_identity=require_deployment_identity,
    )
    if saved_plan is None:
        return ReplayPreparation(capability)
    original_plan = build_original_replay_plan(
        saved_plan,
        request_id=request_id,
        prompt_id=prompt_id,
        correlation_metadata=correlation_metadata,
    )
    return ReplayPreparation(capability, saved_plan, original_plan)


def prepare_resume_replay(
    snapshot: Any,
    *,
    generation: Any = None,
    require_deployment_identity: bool = True,
    request_id: Any = None,
    prompt_id: Any = None,
    correlation_metadata: Mapping[str, Any] | None = None,
) -> ReplayPreparation:
    """Raw-validation + round-trip + mode-preserving Resume copy sequence.

    Identical validation to the Original preparation; the replayed plan is
    the saved plan verbatim except for approved fresh correlation identity
    (the semantic output mode is never converted).
    """
    capability, saved_plan = _validated_plan_from_snapshot(
        snapshot,
        generation=generation,
        require_deployment_identity=require_deployment_identity,
    )
    if saved_plan is None:
        return ReplayPreparation(capability)
    resume_plan = build_resume_replay_plan(
        saved_plan,
        request_id=request_id,
        prompt_id=prompt_id,
        correlation_metadata=correlation_metadata,
    )
    return ReplayPreparation(capability, saved_plan, resume_plan)


@dataclass(frozen=True)
class ReplayDelta:
    allowed: bool
    changed_paths: tuple[str, ...] = ()
    unexpected_paths: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "changed_paths": list(self.changed_paths),
            "unexpected_paths": list(self.unexpected_paths),
        }


def _delta_paths(before: Any, after: Any, path: str = "") -> list[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        for key in sorted(set(before) | set(after), key=str):
            child = f"{path}.{key}" if path else str(key)
            if key not in before or key not in after:
                paths.append(child)
            else:
                paths.extend(_delta_paths(before[key], after[key], child))
        return paths
    if before != after:
        return [path or "<root>"]
    return []


def _delta_allowed(path: str) -> bool:
    if path == "execution_options.output_conversion_options" or path.startswith(
        "execution_options.output_conversion_options."
    ):
        return True
    if path == "execution_options.output_intent":
        return True
    # Generate Original's intentional semantic delta: the replayed plan
    # converts a frozen preview mode to "original".  Resume never touches
    # output_mode (build_resume_replay_plan preserves it verbatim).
    if path == "execution_options.output_mode":
        return True
    prefix = "request_metadata."
    return path.startswith(prefix) and path[len(prefix):] in CORRELATION_METADATA_KEYS


def validate_replay_delta(
    saved_plan: ExecutionPlan,
    original_plan: ExecutionPlan,
) -> ReplayDelta:
    """Assert that an Original plan differs only at approved output/correlation paths."""
    if not isinstance(saved_plan, ExecutionPlan) or not isinstance(original_plan, ExecutionPlan):
        return ReplayDelta(False, unexpected_paths=("<plan_type>",))
    changed = tuple(_delta_paths(saved_plan.to_dict(), original_plan.to_dict()))
    unexpected = tuple(path for path in changed if not _delta_allowed(path))
    return ReplayDelta(not unexpected, changed, unexpected)


class OriginalDecision(str, Enum):
    CREATE = "create_original"
    REUSE_ACTIVE = "reuse_active"
    REUSE_SUCCESSFUL = "reuse_successful"
    RETRY_REQUIRED = "retry_required"
    BUSY = "busy"


def _attempt_field(attempt: Any, name: str, default: Any = None) -> Any:
    if isinstance(attempt, Mapping):
        return attempt.get(name, default)
    return getattr(attempt, name, default)


def _attempt_key(attempt: Any) -> tuple[str, str]:
    return (str(_attempt_field(attempt, "created_at", "") or ""), str(_attempt_field(attempt, "run_id", "") or ""))


@dataclass(frozen=True)
class OriginalDecisionResult:
    decision: str
    attempt_id: str = ""
    reused: bool = False
    reason: str = ""

    @property
    def action(self) -> str:
        return self.decision

    @property
    def create_new(self) -> bool:
        return self.decision == OriginalDecision.CREATE.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "attempt_id": self.attempt_id,
            "reused": self.reused,
            "reason": self.reason,
        }


def decide_original_action(
    attempts: Sequence[Any],
    *,
    explicit_rerender: bool = False,
) -> OriginalDecisionResult:
    """Choose the pure active/success/retry/create policy for one Generation."""
    original = [a for a in attempts if _attempt_field(a, "mode") == "original"]
    active_original = [
        a for a in original if _attempt_field(a, "status") in {"queued", "running"}
    ]
    if active_original:
        selected = max(active_original, key=_attempt_key)
        return OriginalDecisionResult(
            OriginalDecision.REUSE_ACTIVE.value,
            str(_attempt_field(selected, "run_id", "") or ""),
            reused=True,
            reason="original_attempt_active",
        )

    successful = [a for a in original if _attempt_field(a, "status") == "completed"]
    active_preview = [
        a for a in attempts
        if _attempt_field(a, "mode") == "preview"
        and _attempt_field(a, "status") in {"queued", "running"}
    ]
    if successful and not explicit_rerender:
        selected = max(successful, key=_attempt_key)
        return OriginalDecisionResult(
            OriginalDecision.REUSE_SUCCESSFUL.value,
            str(_attempt_field(selected, "run_id", "") or ""),
            reused=True,
            reason="newest_successful_original",
        )
    if active_preview:
        return OriginalDecisionResult(
            OriginalDecision.BUSY.value,
            reason="preview_attempt_active",
        )
    if explicit_rerender:
        return OriginalDecisionResult(
            OriginalDecision.CREATE.value,
            reason="explicit_rerender",
        )
    failed = [a for a in original if _attempt_field(a, "status") == "failed"]
    if failed:
        selected = max(failed, key=_attempt_key)
        return OriginalDecisionResult(
            OriginalDecision.RETRY_REQUIRED.value,
            str(_attempt_field(selected, "run_id", "") or ""),
            reason="only_failed_original_attempts",
        )
    return OriginalDecisionResult(
        OriginalDecision.CREATE.value,
        reason="no_successful_or_active_original",
    )


@dataclass(frozen=True)
class RetryValidation:
    valid: bool
    reason: str = ""
    mode: str = "original"
    generation_id: str = ""
    snapshot_id: str = ""

    @property
    def ok(self) -> bool:
        return self.valid


def validate_original_retry(
    attempt: Any,
    *,
    generation_id: Any = None,
    snapshot_id: Any = None,
    retry_snapshot_id: Any = None,
    snapshot: Any = None,
    retry_snapshot: Any = None,
) -> RetryValidation:
    """Validate that a failed Original retry retains purpose and identity."""
    mode = str(_attempt_field(attempt, "mode", "") or "")
    actual_generation = str(_attempt_field(attempt, "generation_id", "") or "")
    if mode != "original":
        return RetryValidation(False, REASON_NOT_ORIGINAL_FAILURE, mode, actual_generation)
    if _attempt_field(attempt, "status") != "failed":
        return RetryValidation(False, REASON_NOT_ORIGINAL_FAILURE, mode, actual_generation)
    if generation_id not in (None, "") and actual_generation != str(generation_id):
        return RetryValidation(False, REASON_GENERATION_MISMATCH, mode, actual_generation)
    if snapshot_id not in (None, "") and retry_snapshot_id not in (None, ""):
        if str(snapshot_id) != str(retry_snapshot_id):
            return RetryValidation(False, REASON_SNAPSHOT_MISMATCH, mode, actual_generation)
    if snapshot is not None and retry_snapshot is not None:
        if _plain_copy(_snapshot_parts(snapshot)) != _plain_copy(_snapshot_parts(retry_snapshot)):
            return RetryValidation(False, REASON_SNAPSHOT_MISMATCH, mode, actual_generation)
    return RetryValidation(
        True,
        mode=mode,
        generation_id=actual_generation,
        snapshot_id=str(snapshot_id or retry_snapshot_id or ""),
    )


class ReplayExecutor(Protocol):
    """Callable shape implemented later by the canonical execution adapter."""

    async def __call__(self, plan: ExecutionPlan, **kwargs: Any) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class ReplayDispatchRequest:
    generation_id: str
    attempt_id: str
    plan: ExecutionPlan
    snapshot_id: str = ""
    mode: str = "original"

    def __post_init__(self) -> None:
        if not self.generation_id or not self.attempt_id:
            raise ValueError("replay dispatch requires generation_id and attempt_id")
        if self.mode not in ("original", "preview"):
            raise ValueError(
                "replay dispatch mode must be the frozen semantic mode "
                "(original or preview)"
            )
        if not isinstance(self.plan, ExecutionPlan):
            raise TypeError("replay dispatch requires a validated ExecutionPlan")

    @property
    def executor_name(self) -> str:
        return "canonical_execution.execute_plan"


@dataclass(frozen=True)
class ReplayDispatchResult:
    generation_id: str
    attempt_id: str
    status: str
    mode: str = "original"
    payload: Mapping[str, Any] = field(default_factory=dict)


# ── E3B2 production Generate Original service ────────────────────────────
#
# The pure replay core above stays free of repository mutation and remote
# execution.  This section is the production orchestration seam that owns:
# transactional decision -> guarded Attempt creation -> canonical dispatch
# -> required-output persistence -> terminal ordering.  Every external
# effect (transport, executor, materializer, writer, scheduler registry) is
# an injectable seam so offline tests never touch Modal.


OUTCOME_CREATED = "created"
OUTCOME_REUSE_ACTIVE = "reuse_active"
OUTCOME_REUSE_SUCCESSFUL = "reuse_successful"
OUTCOME_RETRY_REQUIRED = "retry_required"
OUTCOME_BUSY = "busy"
OUTCOME_NOT_RETRYABLE = "not_retryable"

CODE_ORIGINAL_CREATED = "original_created"
CODE_ORIGINAL_ALREADY_ACTIVE = "original_already_active"
CODE_ORIGINAL_ALREADY_COMPLETED = "original_already_completed"
CODE_RETRY_REQUIRED = "retry_required"
CODE_GENERATION_BUSY = "generation_busy"
CODE_GENERATION_NOT_REPRODUCIBLE = "generation_not_reproducible"
CODE_DISPATCH_UNAVAILABLE = "dispatch_unavailable"
CODE_GENERATION_NOT_FOUND = "generation_not_found"
CODE_RETRY_NOT_AVAILABLE = "retry_not_available"
CODE_RESUME_CREATED = "resume_created"
CODE_RESUME_NOT_AVAILABLE = "resume_not_available"

_TERMINAL_RESULT_STATUSES = frozenset({"canceled", "interrupted"})
_META_PASSTHROUGH_KEYS = (
    "asset_descriptors",
    "output_descriptors",
    "logical_output_key",
    "logical_output_keys",
    "node_id",
    "output_key",
    "output_index",
)


@dataclass(frozen=True)
class GenerateOriginalResult:
    """Route-ready outcome of one Generate Original / Retry action."""

    http_status: int
    payload: Mapping[str, Any]

    @property
    def ok(self) -> bool:
        return self.http_status < 400


def _error_result(
    http_status: int, code: str, message: str, **extra: Any
) -> GenerateOriginalResult:
    payload: dict[str, Any] = {
        "status": "error",
        "code": code,
        "message": message,
    }
    payload.update(extra)
    return GenerateOriginalResult(http_status, payload)


def _default_transport_factory() -> Any:
    from comfymodal_runtime.modal_transport import ModalTransport

    return ModalTransport()


def _resolve_replay_workspace(plan: ExecutionPlan) -> dict[str, Any] | None:
    """Resolve the credential dict for the replay dispatch (E7).

    Prefers the immutable snapshot's ``request_metadata.workspace_id``;
    falls back to the registry's ACTIVE workspace when the snapshot predates
    workspace-id freezing (older snapshots carry an empty id).  Mirrors
    ``history_v2_routes._resolve_workspace_dict``.  Returns ``None`` when
    unresolvable (fail-closed upstream).
    """
    metadata = getattr(plan, "request_metadata", None)
    workspace_id = ""
    if isinstance(metadata, Mapping):
        workspace_id = str(metadata.get("workspace_id", "") or "")
    try:
        from pathlib import Path

        from modal_workspaces import (
            get_workspace,
            load_workspace_registry,
            resolve_workspace_registry_path,
            resolve_modal_destination,
        )

        registry_file = resolve_workspace_registry_path(Path(__file__).resolve().parent)
        registry = load_workspace_registry(registry_file)
        destination = resolve_modal_destination(Path(__file__).resolve().parent)
        configured_id = str(destination.get("workspace_id", "") or "")
        if workspace_id and workspace_id != configured_id:
            return None
        workspace_id = configured_id
        if not workspace_id:
            return None
        return get_workspace(registry, workspace_id)
    except Exception:
        return None


async def _default_replay_executor(
    plan: ExecutionPlan, *, transport: Any = None
) -> Mapping[str, Any]:
    """Canonical execution seam: fresh per-attempt trace, same engine."""
    from canonical_execution import execute_plan
    from comfymodal_runtime.trace import RuntimeTrace

    metadata = getattr(plan, "request_metadata", {}) or {}
    request_id = str(
        metadata.get("prompt_id") or metadata.get("request_id")
        or uuid.uuid4().hex[:16]
    )
    trace = RuntimeTrace(request_id=request_id, process="local")
    workspace = _resolve_replay_workspace(plan)
    return await execute_plan(
        plan, transport=transport, trace=trace, workspace=workspace
    )


def _sync_default_materialize(
    result: dict[str, Any], plan: ExecutionPlan, prompt_id: str
) -> list[str]:
    from comfymodal_runtime.result_delivery import materialize_modal_result
    from local_artifacts import get_studio_outputs_dir

    out_dir = str(get_studio_outputs_dir())
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    materialized = materialize_modal_result(
        result,
        output_dir=out_dir,
        prompt_id=prompt_id,
        require_output=False,
        expected_output_node_ids=tuple(plan.output_node_ids),
    )
    paths = [
        str(Path(value).name)
        for value in (materialized.get("written_files") or [])
        if str(value)
    ]
    primary = (
        materialized.get("primary_output")
        if isinstance(materialized, dict)
        else None
    )
    if not paths and isinstance(primary, dict):
        result["primary_asset_id"] = primary.get("asset_id", "")
        result["_local_primary_output"] = primary
    return paths


async def _default_replay_materializer(
    result: dict[str, Any], plan: ExecutionPlan, prompt_id: str
) -> list[str]:
    return await asyncio.to_thread(
        _sync_default_materialize, result, plan, prompt_id
    )


class GenerateOriginalService:
    """Production Generate Original orchestrator (E3B2).

    Sequence per action:

    1. Load Generation + linked immutable RequestSnapshot.
    2. Raw replay-capability validation (fail closed, non-destructive 409).
    3. Ensure dispatch capability BEFORE any Attempt exists (no orphan
       queued work): Single builds its transport; Experiment resolves or
       narrowly reconstructs the existing modern scheduler.
    4. One serialized repository transaction applies the E3B1 duplicate/
       busy/success/retry/rerender decision and creates at most one queued
       Original Attempt under the SAME Generation.
    5. Dispatch the validated output-intent-only replay plan through the
       canonical execution machinery (``canonical_execution.execute_plan``
       for Single; the existing modern scheduler binding for Experiment).
    6. Persist running, then required outputs/History association, then the
       terminal status — never completed-before-asset.
    """

    def __init__(
        self,
        repo: Any,
        *,
        data_root: Any = None,
        transport_factory: Any = None,
        executor: Any = None,
        materializer: Any = None,
        writer_factory: Any = None,
        scheduler_getter: Any = None,
        scheduler_factory: Any = None,
    ) -> None:
        self._repo = repo
        resolved_root = data_root
        if resolved_root is None:
            store = getattr(repo, "_store", None)
            resolver = getattr(store, "data_root", None)
            resolved_root = resolver() if callable(resolver) else None
        self._data_root = resolved_root
        self._transport_factory = transport_factory or _default_transport_factory
        self._executor = executor or _default_replay_executor
        self._materializer = materializer or _default_replay_materializer
        self._writer_factory = writer_factory or self._default_writer_factory
        self._scheduler_getter = scheduler_getter or _default_scheduler_getter
        self._scheduler_factory = (
            scheduler_factory
            or _default_scheduler_factory(repo, self._transport_factory)
        )
        self._pending_tasks: set[asyncio.Task] = set()

    # ── seams ────────────────────────────────────────────────────────────

    def _default_writer_factory(self) -> Any:
        from history_v2_writer import HistoryV2ProductionWriter

        return HistoryV2ProductionWriter(self._data_root)

    def _writer(self) -> Any:
        return self._writer_factory()

    # ── public actions ──────────────────────────────────────────────────

    async def generate(
        self, generation_id: str, *, rerender: bool = False
    ) -> GenerateOriginalResult:
        detail = self._repo.get_generation(str(generation_id))
        if detail is None:
            return _error_result(
                404,
                CODE_GENERATION_NOT_FOUND,
                "generation not found",
                generation_id=str(generation_id),
            )
        capability = validate_replay_capability(
            detail.request_snapshot, generation=detail.generation
        )
        if not capability.capable:
            return _error_result(
                409,
                CODE_GENERATION_NOT_REPRODUCIBLE,
                "generation snapshot is not reproducible",
                generation_id=detail.generation.generation_id,
                reason=capability.reason,
                details=_plain_copy(capability.details),
            )
        lane = self._ensure_dispatch_lane(detail)
        if lane is None:
            return _error_result(
                503,
                CODE_DISPATCH_UNAVAILABLE,
                "no capable dispatcher is available for this generation",
                generation_id=detail.generation.generation_id,
            )
        claim = self._repo.claim_or_reuse_original_attempt(
            str(generation_id), explicit_rerender=bool(rerender)
        )
        if claim is None:
            return _error_result(
                404,
                CODE_GENERATION_NOT_FOUND,
                "generation not found",
                generation_id=str(generation_id),
            )
        return await self._resolve_claim(claim, lane)

    async def retry(self, generation_id: str) -> GenerateOriginalResult:
        detail = self._repo.get_generation(str(generation_id))
        if detail is None:
            return _error_result(
                404,
                CODE_GENERATION_NOT_FOUND,
                "generation not found",
                generation_id=str(generation_id),
            )
        capability = validate_replay_capability(
            detail.request_snapshot, generation=detail.generation
        )
        if not capability.capable:
            return _error_result(
                409,
                CODE_GENERATION_NOT_REPRODUCIBLE,
                "generation snapshot is not reproducible",
                generation_id=detail.generation.generation_id,
                reason=capability.reason,
                details=_plain_copy(capability.details),
            )
        lane = self._ensure_dispatch_lane(detail)
        if lane is None:
            return _error_result(
                503,
                CODE_DISPATCH_UNAVAILABLE,
                "no capable dispatcher is available for this generation",
                generation_id=detail.generation.generation_id,
            )
        claim = self._repo.create_original_retry_attempt(str(generation_id))
        if claim is None:
            return _error_result(
                404,
                CODE_GENERATION_NOT_FOUND,
                "generation not found",
                generation_id=str(generation_id),
            )
        if claim.outcome == OUTCOME_BUSY:
            return _error_result(
                409,
                CODE_GENERATION_BUSY,
                "an attempt of this generation is already active",
                generation_id=detail.generation.generation_id,
            )
        if claim.outcome == OUTCOME_NOT_RETRYABLE:
            return _error_result(
                409,
                CODE_RETRY_NOT_AVAILABLE,
                "only a failed original attempt can be retried",
                generation_id=detail.generation.generation_id,
                reason=claim.reason,
            )
        return await self._resolve_claim(claim, lane)

    async def resume_single(self, generation_id: str) -> GenerateOriginalResult:
        """F1A Generation-level Resume of an interrupted ordinary Single.

        Resume means "re-execute the interrupted immutable request", never
        "Generate Original": the frozen ExecutionPlan's semantic output mode
        (``execution_options.output_mode`` / conversion options) is preserved
        verbatim and only approved fresh correlation identity differs.
        Sequence mirrors the E3B2 no-orphan discipline: raw replay-capability
        validation → workspace preflight → dispatch-lane construction → one
        transactional guarded claim (``create_single_resume_attempt``) →
        canonical dispatch with truthful terminal ordering.  Refusals are
        machine-readable and never silently convert state: failed requires
        Retry, canceled/completed are not resumable, active attempts are
        busy, Experiment cells resume through the Experiment surface.
        """
        detail = self._repo.get_generation(str(generation_id))
        if detail is None:
            return _error_result(
                404,
                CODE_GENERATION_NOT_FOUND,
                "generation not found",
                generation_id=str(generation_id),
            )
        try:
            saved_plan = load_replay_plan(
                detail.request_snapshot, generation=detail.generation
            )
        except ReplayCapabilityError as exc:
            return _error_result(
                409,
                CODE_GENERATION_NOT_REPRODUCIBLE,
                "generation snapshot is not reproducible",
                generation_id=detail.generation.generation_id,
                reason=exc.capability.reason,
                details=_plain_copy(exc.capability.details),
            )
        if getattr(detail.generation, "experiment_id", None):
            return _error_result(
                409,
                CODE_RESUME_NOT_AVAILABLE,
                "Experiment cell generations resume through the Experiment surface",
                generation_id=detail.generation.generation_id,
                reason="experiment_cell_generation",
            )
        # Pre-claim workspace preflight (E7 fail-closed policy): an explicit
        # saved workspace that cannot resolve — or no active fallback — must
        # refuse BEFORE any Attempt exists so no orphan queued Resume work
        # can be created.
        if _resolve_replay_workspace(saved_plan) is None:
            return _error_result(
                503,
                CODE_DISPATCH_UNAVAILABLE,
                "no resolvable Modal workspace is available for this frozen plan",
                generation_id=detail.generation.generation_id,
                reason="workspace_unresolved",
            )
        lane = self._ensure_dispatch_lane(detail)
        if lane is None:
            return _error_result(
                503,
                CODE_DISPATCH_UNAVAILABLE,
                "no capable dispatcher is available for this generation",
                generation_id=detail.generation.generation_id,
            )
        claim = self._repo.create_single_resume_attempt(str(generation_id))
        if claim is None:
            return _error_result(
                404,
                CODE_GENERATION_NOT_FOUND,
                "generation not found",
                generation_id=str(generation_id),
            )
        if claim.outcome == OUTCOME_BUSY:
            return _error_result(
                409,
                CODE_GENERATION_BUSY,
                "an attempt of this generation is already active",
                generation_id=detail.generation.generation_id,
                reason=claim.reason,
            )
        if claim.outcome == "not_resumable":
            return _error_result(
                409,
                CODE_RESUME_NOT_AVAILABLE,
                "only an interrupted ordinary Single can be resumed",
                generation_id=detail.generation.generation_id,
                reason=claim.reason,
            )
        attempt_mode = claim.attempt.mode if claim.attempt is not None else "preview"
        return await self._dispatch_created(
            claim,
            lane,
            {
                "generation_id": detail.generation.generation_id,
                "purpose": "resume",
                "decision": claim.decision,
                "reason": claim.reason,
            },
            purpose="resume",
            mode=attempt_mode,
        )

    # ── dispatch lanes ──────────────────────────────────────────────────

    def _experiment_cell_plan(self, detail: Any) -> Mapping[str, Any] | None:
        snapshot = detail.request_snapshot
        request = getattr(snapshot, "request", None)
        if isinstance(request, Mapping) and request.get("cell_id"):
            return request
        return None

    def _ensure_dispatch_lane(self, detail: Any) -> Any:
        """Construct dispatch capability BEFORE any Attempt is created."""
        experiment_id = getattr(detail.generation, "experiment_id", None)
        if experiment_id:
            cell_plan = self._experiment_cell_plan(detail)
            if cell_plan is None:
                return None
            scheduler = None
            getter = self._scheduler_getter
            if callable(getter):
                try:
                    scheduler = getter(str(experiment_id))
                except Exception:
                    scheduler = None
            if scheduler is None:
                factory = self._scheduler_factory
                if not callable(factory):
                    return None
                try:
                    scheduler = factory(
                        str(experiment_id), [dict(cell_plan)]
                    )
                except Exception:
                    return None
            if scheduler is None:
                return None
            return ("experiment", scheduler, dict(cell_plan))
        try:
            transport = self._transport_factory()
        except Exception:
            return None
        return ("single", transport, None)

    async def _submit_experiment_cell(
        self, scheduler: Any, cell_plan: Mapping[str, Any], plan: ExecutionPlan
    ) -> None:
        submitted = dict(cell_plan)
        submitted["execution_plan"] = plan.to_dict()
        await scheduler.submit_cell(submitted)

    # ── decision resolution ─────────────────────────────────────────────

    async def _resolve_claim(self, claim: Any, lane: Any) -> GenerateOriginalResult:
        generation = claim.generation
        attempt = claim.attempt
        base = {
            "generation_id": generation.generation_id,
            "purpose": "original",
            "decision": claim.decision,
            "reason": claim.reason,
        }
        if claim.outcome == OUTCOME_CREATED and attempt is not None:
            return await self._dispatch_created(claim, lane, base)
        if claim.outcome == OUTCOME_REUSE_ACTIVE:
            return GenerateOriginalResult(200, {
                **base,
                "status": "ok",
                "outcome": CODE_ORIGINAL_ALREADY_ACTIVE,
                "run_id": attempt.run_id if attempt else "",
                "attempt_status": attempt.status if attempt else "",
                "reused": True,
            })
        if claim.outcome == OUTCOME_REUSE_SUCCESSFUL:
            return GenerateOriginalResult(200, {
                **base,
                "status": "ok",
                "outcome": CODE_ORIGINAL_ALREADY_COMPLETED,
                "run_id": attempt.run_id if attempt else "",
                "attempt_status": attempt.status if attempt else "",
                "reused": True,
            })
        if claim.outcome == OUTCOME_RETRY_REQUIRED:
            return GenerateOriginalResult(200, {
                **base,
                "status": "ok",
                "outcome": CODE_RETRY_REQUIRED,
                "run_id": attempt.run_id if attempt else "",
                "attempt_status": attempt.status if attempt else "failed",
                "reused": False,
            })
        if claim.outcome == OUTCOME_BUSY:
            return _error_result(
                409,
                CODE_GENERATION_BUSY,
                "a preview attempt of this generation is still active",
                **base,
            )
        return _error_result(
            409,
            CODE_RETRY_NOT_AVAILABLE,
            "generate original is not available for this generation state",
            **base,
        )

    async def _dispatch_created(
        self,
        claim: Any,
        lane: Any,
        base: dict[str, Any],
        *,
        purpose: str = "original",
        mode: str = "original",
    ) -> GenerateOriginalResult:
        generation = claim.generation
        attempt = claim.attempt
        assert attempt is not None
        correlation_id = uuid.uuid4().hex[:16]
        try:
            if purpose == "resume":
                dispatch = build_resume_replay_dispatch(
                    claim.snapshot,
                    generation_id=generation.generation_id,
                    attempt_id=attempt.run_id,
                    mode=str(mode),
                    snapshot_id=(
                        claim.snapshot.snapshot_id
                        if claim.snapshot is not None
                        else ""
                    ),
                    generation=generation,
                    request_id=correlation_id,
                    prompt_id=correlation_id,
                    correlation_metadata={
                        "run_id": attempt.run_id,
                        "attempt_id": attempt.run_id,
                    },
                )
            else:
                dispatch = build_replay_dispatch(
                    claim.snapshot,
                    generation_id=generation.generation_id,
                    attempt_id=attempt.run_id,
                    snapshot_id=(
                        claim.snapshot.snapshot_id
                        if claim.snapshot is not None
                        else ""
                    ),
                    generation=generation,
                    request_id=correlation_id,
                    prompt_id=correlation_id,
                    correlation_metadata={
                        "run_id": attempt.run_id,
                        "attempt_id": attempt.run_id,
                    },
                )
        except ReplayCapabilityError as exc:
            replay_error = f"replay validation failed: {exc.capability.reason}"
            if purpose == "resume":
                self._repo.update_attempt_terminal(
                    attempt.run_id,
                    status="failed",
                    error=replay_error,
                )
            else:
                self._repo.cancel_queued_attempt(
                    attempt.run_id,
                    error=replay_error,
                )
            return _error_result(
                409,
                CODE_GENERATION_NOT_REPRODUCIBLE,
                "generation snapshot is not reproducible",
                generation_id=generation.generation_id,
                reason=exc.capability.reason,
            )
        kind = lane[0]
        try:
            if kind == "single":
                loop = asyncio.get_running_loop()
                task = loop.create_task(
                    self._run_single_attempt(dispatch, lane[1])
                )
                self._pending_tasks.add(task)
                task.add_done_callback(self._pending_tasks.discard)
            else:
                await self._submit_experiment_cell(
                    lane[1], lane[2], dispatch.plan
                )
        except Exception as exc:
            self._repo.update_attempt_terminal(
                attempt.run_id,
                status="failed",
                error=f"dispatch failed: {exc}",
            )
            return _error_result(
                503,
                CODE_DISPATCH_UNAVAILABLE,
                "dispatch registration failed; the attempt was marked failed",
                generation_id=generation.generation_id,
                run_id=attempt.run_id,
            )
        return GenerateOriginalResult(200, {
            **base,
            "status": "ok",
            "outcome": (
                CODE_RESUME_CREATED if purpose == "resume" else CODE_ORIGINAL_CREATED
            ),
            "run_id": attempt.run_id,
            "attempt_status": attempt.status,
            "reused": False,
            "executor": dispatch.executor_name,
            "mode": dispatch.mode,
        })

    # ── Single attempt runner (terminal ordering contract) ──────────────

    async def _run_single_attempt(
        self, dispatch: ReplayDispatchRequest, transport: Any
    ) -> None:
        from history_v2_models import CLAIM_CLAIMED

        repo = self._repo
        attempt_id = dispatch.attempt_id
        generation_id = dispatch.generation_id
        plan = dispatch.plan

        def fail(error: str) -> None:
            repo.update_attempt_terminal(
                attempt_id, status="failed", error=str(error)[:500]
            )

        claim = repo.claim_attempt(attempt_id)
        if claim.outcome != CLAIM_CLAIMED:
            return
        required = bool(
            plan.execution_options.production_enabled
        ) or bool(plan.output_node_ids)
        try:
            raw_result = await self._executor(plan, transport=transport)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            fail(f"execution failed: {exc}")
            return
        result = dict(raw_result) if isinstance(raw_result, Mapping) else {}
        status = str(result.get("status", "") or "")
        if status in ("failed", "error"):
            fail(
                result.get("error")
                or result.get("message")
                or f"execution reported status {status!r}"
            )
            return
        if status in _TERMINAL_RESULT_STATUSES:
            repo.update_attempt_terminal(attempt_id, status=status)
            return
        output_paths: list[str] = []
        try:
            output_paths = list(
                await self._materializer(result, plan, attempt_id) or []
            )
        except Exception as exc:
            if required:
                fail(f"output materialization failed: {exc}")
                return
        has_remote_output = bool(
            result.get("outputs")
            or result.get("images")
            or result.get("videos")
            or result.get("primary_output")
            or result.get("_local_primary_output")
        )
        if required and not has_remote_output and not output_paths:
            fail("v2 execution returned no output")
            return
        meta: dict[str, Any] = {
            key: result[key]
            for key in _META_PASSTHROUGH_KEYS
            if key in result
        }
        # Semantic output mode flows from the frozen plan into History asset
        # typing: a resumed Preview attempt must attach as "preview" (never
        # silently retyped "original").  Original replays already carry the
        # converted plan's explicit "original" mode, so this is additive.
        semantic_mode = str(
            getattr(plan.execution_options, "output_mode", "") or ""
        )
        if semantic_mode:
            meta.setdefault("output_mode", semantic_mode)
            meta.setdefault("variant", semantic_mode)
        primary_asset_id = str(result.get("primary_asset_id", "") or "")
        if output_paths:
            meta["output_paths"] = list(output_paths)
        attached = False
        try:
            attached = bool(
                self._writer().attach_result_assets(
                    generation_id,
                    attempt_id,
                    output_paths=output_paths,
                    primary_asset_id=primary_asset_id,
                    meta=meta,
                )
            )
        except Exception:
            attached = False
        if required and not attached:
            fail("History output finalization failed")
            return
        repo.update_attempt_terminal(attempt_id, status="completed")
        self._promote_newest_original(generation_id, attempt_id)

    def _promote_newest_original(
        self, generation_id: str, attempt_id: str
    ) -> None:
        """Deliberately prefer the newest successful Original asset.

        The Preview asset is retained; only the Generation-level featured
        pointer moves to this attempt's newest original so E1B projection
        reports the newest successful Original as the winner.
        """
        try:
            assets = [
                asset
                for asset in self._repo.get_generation_assets(generation_id)
                if asset.type == "original" and asset.run_id == attempt_id
            ]
            newest = max(
                assets,
                key=lambda asset: (asset.created_at, asset.asset_id),
                default=None,
            )
            if newest is not None:
                self._repo.set_featured_asset(generation_id, newest.asset_id)
        except Exception:
            pass


def _default_scheduler_getter(experiment_id: str) -> Any:
    try:
        from experiment_modern_scheduler import get_scheduler

        return get_scheduler(experiment_id)
    except Exception:
        return None


def _default_scheduler_factory(repo: Any, transport_factory: Any) -> Any:
    """Narrow Experiment restart/reconstruction seam.

    Rebuilds the EXISTING production scheduler binding from the persisted
    cell plan and the experiment-bound repository.  No second execution
    engine is introduced: the reconstructed scheduler runs the frozen plan
    through ``canonical_execution.execute_plan`` exactly like acceptance.
    """

    def factory(experiment_id: str, cell_plans: Any) -> Any:
        from experiment_modern_scheduler import build_experiment_scheduler
        from history_v2_repository import HistoryV2Repository

        store = getattr(repo, "_store", None)
        if store is None:
            return None
        bound = HistoryV2Repository(store, experiment_id=str(experiment_id))
        return build_experiment_scheduler(
            experiment_id=str(experiment_id),
            cell_plans=list(cell_plans),
            persistence=bound,
            transport_factory=transport_factory,
        )

    return factory


def build_replay_dispatch(
    snapshot: Any,
    *,
    generation_id: str,
    attempt_id: str,
    snapshot_id: str = "",
    generation: Any = None,
    request_id: Any = None,
    prompt_id: Any = None,
    correlation_metadata: Mapping[str, Any] | None = None,
    require_deployment_identity: bool = True,
) -> ReplayDispatchRequest:
    """Build the E3B2 input for ``canonical_execution.execute_plan`` only."""
    preparation = prepare_original_replay(
        snapshot,
        generation=generation,
        require_deployment_identity=require_deployment_identity,
        request_id=request_id,
        prompt_id=prompt_id,
        correlation_metadata=correlation_metadata,
    )
    if preparation.original_plan is None:
        raise ReplayCapabilityError(preparation.capability)
    return ReplayDispatchRequest(
        generation_id=str(generation_id),
        attempt_id=str(attempt_id),
        snapshot_id=str(snapshot_id or ""),
        plan=preparation.original_plan,
    )


def build_resume_replay_dispatch(
    snapshot: Any,
    *,
    generation_id: str,
    attempt_id: str,
    mode: str = "preview",
    snapshot_id: str = "",
    generation: Any = None,
    request_id: Any = None,
    prompt_id: Any = None,
    correlation_metadata: Mapping[str, Any] | None = None,
    require_deployment_identity: bool = True,
) -> ReplayDispatchRequest:
    """Build the F1A Resume input for ``canonical_execution.execute_plan``.

    The replayed plan is the saved immutable plan verbatim except for
    approved fresh correlation identity — the frozen semantic output mode is
    preserved (never converted to Original).
    """
    preparation = prepare_resume_replay(
        snapshot,
        generation=generation,
        require_deployment_identity=require_deployment_identity,
        request_id=request_id,
        prompt_id=prompt_id,
        correlation_metadata=correlation_metadata,
    )
    if preparation.original_plan is None:
        raise ReplayCapabilityError(preparation.capability)
    return ReplayDispatchRequest(
        generation_id=str(generation_id),
        attempt_id=str(attempt_id),
        snapshot_id=str(snapshot_id or ""),
        plan=preparation.original_plan,
        mode=str(mode),
    )


__all__ = [
    "CODE_DISPATCH_UNAVAILABLE",
    "CODE_GENERATION_BUSY",
    "CODE_GENERATION_NOT_FOUND",
    "CODE_GENERATION_NOT_REPRODUCIBLE",
    "CODE_ORIGINAL_ALREADY_ACTIVE",
    "CODE_ORIGINAL_ALREADY_COMPLETED",
    "CODE_ORIGINAL_CREATED",
    "CODE_RESUME_CREATED",
    "CODE_RESUME_NOT_AVAILABLE",
    "CODE_RETRY_NOT_AVAILABLE",
    "CODE_RETRY_REQUIRED",
    "CORRELATION_METADATA_KEYS",
    "CURRENT_PLAN_SCHEMA_VERSION",
    "GenerateOriginalResult",
    "GenerateOriginalService",
    "OUTCOME_BUSY",
    "OUTCOME_CREATED",
    "OUTCOME_NOT_RETRYABLE",
    "OUTCOME_REUSE_ACTIVE",
    "OUTCOME_REUSE_SUCCESSFUL",
    "OUTCOME_RETRY_REQUIRED",
    "REASON_GENERATION_MISMATCH",
    "REASON_IDENTITY_MISMATCH",
    "REASON_INVALID_PLAN",
    "REASON_MISSING_DEPLOYMENT_IDENTITY",
    "REASON_MISSING_EXECUTION_OPTIONS",
    "REASON_MISSING_EXECUTION_PLAN",
    "REASON_MISSING_IDENTITY",
    "REASON_MISSING_OUTPUT_NODE_IDENTITY",
    "REASON_MISSING_REQUEST",
    "REASON_MISSING_REQUEST_SNAPSHOT",
    "REASON_MISSING_SOURCE_WORKFLOW_HASH",
    "REASON_MISSING_VALIDATION_PROOF",
    "REASON_MISSING_WORKFLOW",
    "REASON_MISSING_WORKFLOW_HASH",
    "REASON_NOT_ORIGINAL_FAILURE",
    "REASON_SNAPSHOT_DEPLOYMENT_MISMATCH",
    "REASON_SNAPSHOT_HASH_MISMATCH",
    "REASON_SNAPSHOT_MISMATCH",
    "REASON_SNAPSHOT_WORKFLOW_MISMATCH",
    "REASON_UNSUPPORTED_SNAPSHOT_SCHEMA",
    "REQUIRED_EXECUTION_OPTION_KEYS",
    "OriginalDecision",
    "OriginalDecisionResult",
    "ReplayCapability",
    "ReplayCapabilityError",
    "ReplayDelta",
    "ReplayDispatchRequest",
    "ReplayDispatchResult",
    "ReplayExecutor",
    "ReplayPreparation",
    "RetryValidation",
    "build_original_replay_plan",
    "build_resume_replay_plan",
    "build_resume_replay_dispatch",
    "build_replay_dispatch",
    "decide_original_action",
    "load_replay_plan",
    "prepare_original_replay",
    "prepare_resume_replay",
    "validate_original_retry",
    "validate_replay_capability",
    "validate_replay_delta",
]
