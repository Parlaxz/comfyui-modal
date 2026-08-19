"""Pure immutable replay core for History V2 Generate Original.

This module deliberately stops before repository mutation and remote execution.
It validates the raw serialized snapshot before ``ExecutionPlan.from_dict`` can
fill defaults, then produces an Attempt-scoped output-intent copy for the later
History route/service integration.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import Enum
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
    return replace(
        saved_plan,
        execution_options=_original_options(saved_plan.execution_options),
        request_metadata=metadata,
    )


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
        if self.mode != "original":
            raise ValueError("replay dispatch mode must remain original")
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


__all__ = [
    "CORRELATION_METADATA_KEYS",
    "CURRENT_PLAN_SCHEMA_VERSION",
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
    "build_replay_dispatch",
    "decide_original_action",
    "load_replay_plan",
    "prepare_original_replay",
    "validate_original_retry",
    "validate_replay_capability",
    "validate_replay_delta",
]
