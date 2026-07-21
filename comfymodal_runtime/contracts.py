"""Typed, serializable contracts for the v2 runtime."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


METADATA_RUNTIME_MODE = "runtime_mode"
METADATA_WORKFLOW_HASH_PREFIX = "workflow_hash_prefix"
METADATA_APP_NAME = "app_name"
METADATA_CLASS_NAME = "class_name"
METADATA_METHOD_NAME = "method_name"
METADATA_MODAL_INPUT_ID = "modal_input_id"
METADATA_CONTAINER_TASK_ID = "container_task_id"
METADATA_CONTAINER_SESSION_ID = "container_session_id"
METADATA_IMAGE_ID = "image_id"
METADATA_GPU = "gpu"
METADATA_CLOUD = "cloud"
METADATA_REGION = "region"
METADATA_CPU = "cpu"
METADATA_MEMORY_MB = "memory_mb"
METADATA_SNAPSHOT_ENABLED = "snapshot_enabled"
METADATA_GPU_SNAPSHOT_ENABLED = "gpu_snapshot_enabled"
METADATA_RESTORE_PLAN_GENERATION = "restore_plan_generation"


def diagnosis_metadata(**kwargs: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is not None:
            result[key] = value
    return result


_COMPATIBILITY_KEY_COUNTS: dict[str, int] = {}


def _record_compatibility_key(key: str) -> None:
    _COMPATIBILITY_KEY_COUNTS[key] = _COMPATIBILITY_KEY_COUNTS.get(key, 0) + 1


def compatibility_usage_snapshot() -> dict[str, int]:
    return dict(_COMPATIBILITY_KEY_COUNTS)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(v) for v in value))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def _jsonable(value: Any) -> Any:
    return _thaw(value)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_ids(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    def sort_key(value: str) -> tuple[int, int | str]:
        try:
            return (0, int(value))
        except ValueError:
            return (1, value)

    return tuple(sorted(result, key=sort_key))


@dataclass(frozen=True)
class ExecutionOptions:
    production_enabled: bool = True
    production_output_node_ids: tuple[str, ...] = ()
    output_conversion_options: Mapping[str, Any] = field(default_factory=dict)
    result_route: str = ""
    profiling_level: str = "summary"
    requested_backend: str = "in_process"
    cancellation_options: Mapping[str, Any] = field(default_factory=dict)
    progress_options: Mapping[str, Any] = field(default_factory=dict)
    compatibility_flags: Mapping[str, Any] = field(default_factory=dict)
    legacy_passthrough: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "production_output_node_ids", _normalized_ids(self.production_output_node_ids))
        for name in (
            "output_conversion_options",
            "cancellation_options",
            "progress_options",
            "compatibility_flags",
            "legacy_passthrough",
        ):
            object.__setattr__(self, name, _freeze(getattr(self, name) or {}))
        object.__setattr__(self, "production_enabled", bool(self.production_enabled))
        object.__setattr__(self, "result_route", str(self.result_route or ""))
        object.__setattr__(self, "profiling_level", str(self.profiling_level or "summary").lower())
        object.__setattr__(self, "requested_backend", str(self.requested_backend or "in_process").lower())

    @classmethod
    def from_legacy(
        cls,
        value: Mapping[str, Any] | None,
        *,
        production_report: Mapping[str, Any] | None = None,
        default_production: bool = True,
    ) -> "ExecutionOptions":
        source = dict(value or {})
        production = source.get("production")
        if isinstance(production, Mapping):
            _record_compatibility_key("production")
            production_enabled = bool(production.get("enabled", default_production))
            output_ids = production.get("output_node_ids", ())
        elif isinstance(production_report, Mapping) and production_report.get("enabled"):
            production_enabled = True
            output_ids = production_report.get("output_node_ids", ())
        else:
            production_enabled = bool(default_production)
            output_ids = ()

        conversion = source.get("output_conversion_options", source.get("output_conversion"))
        if conversion is None and "output_format" in source:
            conversion = {"format": source["output_format"]}
            _record_compatibility_key("output_format")
        if conversion is None:
            conversion = {}
        if "output_conversion" in source:
            _record_compatibility_key("output_conversion")

        runtime = source.get("runtime")
        runtime = runtime if isinstance(runtime, Mapping) else {}
        backend = source.get("requested_backend", source.get("backend", runtime.get("requested_backend", runtime.get("backend", "in_process"))))
        profile = source.get("profiling_level", source.get("profile_level", runtime.get("profiling_level", "summary")))
        cancellation = source.get("cancellation_options", source.get("cancellation", source.get("cancel", {})))
        progress = source.get("progress_options", source.get("progress", {}))
        flags = source.get("compatibility_flags", {})
        if "actual_load" in source:
            _record_compatibility_key("actual_load")
            flags = dict(flags) if isinstance(flags, Mapping) else {}
            flags.setdefault("actual_load", source["actual_load"])

        known = {
            "production",
            "output_conversion_options",
            "output_conversion",
            "output_format",
            "result_route",
            "profiling_level",
            "profile_level",
            "requested_backend",
            "backend",
            "runtime",
            "cancellation_options",
            "cancellation",
            "cancel",
            "progress_options",
            "progress",
            "compatibility_flags",
            "actual_load",
            "legacy_passthrough",
        }
        passthrough = source.get("legacy_passthrough", {})
        passthrough = dict(passthrough) if isinstance(passthrough, Mapping) else {}
        for key in source:
            if key not in known:
                _record_compatibility_key(str(key))
                passthrough[str(key)] = source[key]

        if isinstance(production, Mapping):
            production_unknown = {
                str(key): value
                for key, value in production.items()
                if key not in {"enabled", "output_node_ids"}
            }
            if production_unknown:
                existing = passthrough.get("production", {})
                merged = dict(existing) if isinstance(existing, Mapping) else {}
                merged.update(production_unknown)
                passthrough["production"] = merged

        runtime_source = source.get("runtime")
        if isinstance(runtime_source, Mapping):
            runtime_unknown = {
                str(key): value
                for key, value in runtime_source.items()
                if key not in {"requested_backend", "backend", "profiling_level"}
            }
            if runtime_unknown:
                existing = passthrough.get("runtime", {})
                merged = dict(existing) if isinstance(existing, Mapping) else {}
                merged.update(runtime_unknown)
                passthrough["runtime"] = merged

        return cls(
            production_enabled=production_enabled,
            production_output_node_ids=output_ids,
            output_conversion_options=conversion,
            result_route=source.get("result_route", ""),
            profiling_level=profile,
            requested_backend=backend,
            cancellation_options=cancellation,
            progress_options=progress,
            compatibility_flags=flags,
            legacy_passthrough=passthrough,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ExecutionOptions":
        return cls.from_legacy(value, default_production=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "production": {
                "enabled": self.production_enabled,
                "output_node_ids": list(self.production_output_node_ids),
            },
            "output_conversion_options": _thaw(self.output_conversion_options),
            "result_route": self.result_route,
            "profiling_level": self.profiling_level,
            "requested_backend": self.requested_backend,
            "cancellation_options": _thaw(self.cancellation_options),
            "progress_options": _thaw(self.progress_options),
            "compatibility_flags": _thaw(self.compatibility_flags),
            "legacy_passthrough": _thaw(self.legacy_passthrough),
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        passthrough = _thaw(self.legacy_passthrough)
        result = dict(passthrough) if isinstance(passthrough, dict) else {}
        result.pop("legacy_passthrough", None)

        # Typed fields are applied after passthrough values so the canonical
        # contract always wins over stale compatibility data.
        result["production"] = {
            **(
                dict(result.get("production", {}))
                if isinstance(result.get("production"), Mapping)
                else {}
            ),
            "enabled": self.production_enabled,
            "output_node_ids": list(self.production_output_node_ids),
        }
        result["output_conversion_options"] = _thaw(self.output_conversion_options)
        result["result_route"] = self.result_route
        result["profiling_level"] = self.profiling_level
        result["requested_backend"] = self.requested_backend
        result["cancellation_options"] = _thaw(self.cancellation_options)
        result["progress_options"] = _thaw(self.progress_options)
        result["compatibility_flags"] = _thaw(self.compatibility_flags)

        runtime = result.get("runtime")
        runtime = dict(runtime) if isinstance(runtime, Mapping) else {}
        runtime["requested_backend"] = self.requested_backend
        runtime["profiling_level"] = self.profiling_level
        result["runtime"] = runtime

        conversion = _thaw(self.output_conversion_options)
        if isinstance(conversion, dict) and "format" in conversion:
            result["output_format"] = conversion["format"]
        flags = _thaw(self.compatibility_flags)
        actual_load = flags.get("actual_load") if isinstance(flags, dict) else None
        if isinstance(actual_load, Mapping):
            result["actual_load"] = dict(actual_load)
        return result


@dataclass(frozen=True)
class ExecutionPlan:
    schema_version: int = 1
    workflow: Mapping[str, Any] = field(default_factory=dict)
    workflow_hash: str = ""
    source_workflow_hash: str = ""
    production_report: Mapping[str, Any] = field(default_factory=dict)
    model_stack: Mapping[str, Any] = field(default_factory=dict)
    prompt_bundle: Mapping[str, Any] = field(default_factory=dict)
    output_node_ids: tuple[str, ...] = ()
    input_images: Mapping[str, str] = field(default_factory=dict)
    execution_options: ExecutionOptions = field(default_factory=ExecutionOptions)
    request_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workflow", _freeze(self.workflow or {}))
        object.__setattr__(self, "production_report", _freeze(self.production_report or {}))
        object.__setattr__(self, "model_stack", _freeze(self.model_stack or {}))
        object.__setattr__(self, "prompt_bundle", _freeze(self.prompt_bundle or {}))
        object.__setattr__(self, "input_images", _freeze(self.input_images or {}))
        object.__setattr__(self, "request_metadata", _freeze(self.request_metadata or {}))
        if not isinstance(self.execution_options, ExecutionOptions):
            object.__setattr__(self, "execution_options", ExecutionOptions.from_dict(self.execution_options))
        output_ids = self.output_node_ids
        if not output_ids and isinstance(self.production_report, Mapping):
            output_ids = self.production_report.get("output_node_ids", ())
        object.__setattr__(self, "output_node_ids", _normalized_ids(output_ids))
        workflow_hash = self.workflow_hash or stable_hash(self.workflow)
        object.__setattr__(self, "workflow_hash", str(workflow_hash))
        object.__setattr__(self, "source_workflow_hash", str(self.source_workflow_hash or workflow_hash))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExecutionPlan":
        source = dict(value)
        return cls(
            schema_version=int(source.get("schema_version", 1)),
            workflow=source.get("workflow", {}),
            workflow_hash=str(source.get("workflow_hash", "")),
            source_workflow_hash=str(source.get("source_workflow_hash", "")),
            production_report=source.get("production_report", {}),
            model_stack=source.get("model_stack", {}),
            prompt_bundle=source.get("prompt_bundle", {}),
            output_node_ids=source.get("output_node_ids", ()),
            input_images=source.get("input_images", {}),
            execution_options=ExecutionOptions.from_dict(source.get("execution_options", {})),
            request_metadata=source.get("request_metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow": _thaw(self.workflow),
            "workflow_hash": self.workflow_hash,
            "source_workflow_hash": self.source_workflow_hash,
            "production_report": _thaw(self.production_report),
            "model_stack": _thaw(self.model_stack),
            "prompt_bundle": _thaw(self.prompt_bundle),
            "output_node_ids": list(self.output_node_ids),
            "input_images": _thaw(self.input_images),
            "execution_options": self.execution_options.to_dict(),
            "request_metadata": _thaw(self.request_metadata),
        }


@dataclass(frozen=True)
class ModelRestoreKey:
    unet_identity: str = ""
    clip_identity: str = ""
    vae_identity: str = ""
    clip_type: str = ""
    loader_configuration: Mapping[str, Any] = field(default_factory=dict)
    model_volume_generation: str = ""
    optimization_loader_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("loader_configuration", "optimization_loader_options"):
            object.__setattr__(self, name, _freeze(getattr(self, name) or {}))
        for name in ("unet_identity", "clip_identity", "vae_identity", "clip_type", "model_volume_generation"):
            object.__setattr__(self, name, str(getattr(self, name) or ""))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ModelRestoreKey":
        source = dict(value or {})
        return cls(
            unet_identity=source.get("unet_identity", source.get("unet", "")),
            clip_identity=source.get("clip_identity", source.get("clip", "")),
            vae_identity=source.get("vae_identity", source.get("vae", "")),
            clip_type=source.get("clip_type", ""),
            loader_configuration=source.get("loader_configuration", source.get("loader_config", {})),
            model_volume_generation=str(source.get("model_volume_generation", source.get("model_generation", ""))),
            optimization_loader_options=source.get("optimization_loader_options", source.get("optimization_options", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "unet_identity": self.unet_identity,
            "clip_identity": self.clip_identity,
            "vae_identity": self.vae_identity,
            "clip_type": self.clip_type,
            "loader_configuration": _thaw(self.loader_configuration),
            "model_volume_generation": self.model_volume_generation,
            "optimization_loader_options": _thaw(self.optimization_loader_options),
        }

    @property
    def stable_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class PrefillKey:
    model_key: ModelRestoreKey = field(default_factory=ModelRestoreKey)
    prompt_bundle_hash: str = ""
    encode_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model_key, ModelRestoreKey):
            object.__setattr__(self, "model_key", ModelRestoreKey.from_dict(self.model_key))
        object.__setattr__(self, "prompt_bundle_hash", str(self.prompt_bundle_hash or ""))
        object.__setattr__(self, "encode_options", _freeze(self.encode_options or {}))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "PrefillKey":
        source = dict(value or {})
        return cls(
            model_key=ModelRestoreKey.from_dict(source.get("model_key", {})),
            prompt_bundle_hash=str(source.get("prompt_bundle_hash", source.get("bundle_hash", ""))),
            encode_options=source.get("encode_options", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_key": self.model_key.to_dict(),
            "prompt_bundle_hash": self.prompt_bundle_hash,
            "encode_options": _thaw(self.encode_options),
        }

    @property
    def stable_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class RestorePlan:
    schema_version: int = 1
    generation: int | str = 0
    model_key: ModelRestoreKey = field(default_factory=ModelRestoreKey)
    prefill_key: PrefillKey = field(default_factory=PrefillKey)
    model_spec: Mapping[str, Any] = field(default_factory=dict)
    prefill_spec: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    source_workflow_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.model_key, ModelRestoreKey):
            object.__setattr__(self, "model_key", ModelRestoreKey.from_dict(self.model_key))
        if not isinstance(self.prefill_key, PrefillKey):
            object.__setattr__(self, "prefill_key", PrefillKey.from_dict(self.prefill_key))
        object.__setattr__(self, "model_spec", _freeze(self.model_spec or {}))
        object.__setattr__(self, "prefill_spec", _freeze(self.prefill_spec or {}))
        object.__setattr__(self, "source_workflow_hash", str(self.source_workflow_hash or ""))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "RestorePlan":
        source = dict(value or {})
        return cls(
            schema_version=int(source.get("schema_version", 1)),
            generation=source.get("generation", 0),
            model_key=ModelRestoreKey.from_dict(source.get("model_key", {})),
            prefill_key=PrefillKey.from_dict(source.get("prefill_key", {})),
            model_spec=source.get("model_spec", {}),
            prefill_spec=source.get("prefill_spec", {}),
            created_at=float(source.get("created_at", time.time())),
            source_workflow_hash=str(source.get("source_workflow_hash", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generation": self.generation,
            "model_key": self.model_key.to_dict(),
            "prefill_key": self.prefill_key.to_dict(),
            "model_spec": _thaw(self.model_spec),
            "prefill_spec": _thaw(self.prefill_spec),
            "created_at": self.created_at,
            "source_workflow_hash": self.source_workflow_hash,
        }

    @property
    def canonical_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class OutputStrategy:
    name: str
    source: str
    priority: int = 0
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "constraints", _freeze(self.constraints or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "priority": self.priority,
            "constraints": _thaw(self.constraints),
        }


@dataclass(frozen=True)
class DeploymentIdentity:
    schema_version: int = 1
    runtime_hash: str = ""
    dependency_hash: str = ""
    custom_node_hash: str = ""
    source_bytes: int = 0
    file_hashes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_hashes", _freeze(self.file_hashes or {}))

    @property
    def combined_hash(self) -> str:
        return stable_hash({
            "schema_version": self.schema_version,
            "runtime_hash": self.runtime_hash,
            "dependency_hash": self.dependency_hash,
            "custom_node_hash": self.custom_node_hash,
            "file_hashes": _thaw(self.file_hashes),
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime_hash": self.runtime_hash,
            "dependency_hash": self.dependency_hash,
            "custom_node_hash": self.custom_node_hash,
            "source_bytes": self.source_bytes,
            "file_hashes": _thaw(self.file_hashes),
            "combined_hash": self.combined_hash,
        }


@dataclass(frozen=True)
class TraceEvent:
    name: str
    process: str = "local"
    phase: str = ""
    wall_unix_ns: int = field(default_factory=time.time_ns)
    monotonic_ns: int = field(default_factory=time.perf_counter_ns)
    request_id: str = ""
    container_session_id: str = ""
    trace_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata or {}))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "process", str(self.process))
        object.__setattr__(self, "phase", str(self.phase))

    @classmethod
    def now(
        cls,
        name: str,
        *,
        process: str = "local",
        phase: str = "",
        request_id: str = "",
        container_session_id: str = "",
        trace_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "TraceEvent":
        return cls(
            name=name,
            process=process,
            phase=phase,
            request_id=request_id,
            container_session_id=container_session_id,
            trace_id=trace_id,
            metadata=metadata or {},
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TraceEvent":
        source = dict(value)
        return cls(
            name=str(source.get("name", "")),
            process=str(source.get("process", "legacy")),
            phase=str(source.get("phase", "legacy")),
            wall_unix_ns=int(source.get("wall_unix_ns", source.get("wall_ns", time.time_ns()))),
            monotonic_ns=int(source.get("monotonic_ns", source.get("mono_ns", 0))),
            request_id=str(source.get("request_id", "")),
            container_session_id=str(source.get("container_session_id", source.get("container_session", ""))),
            trace_id=str(source.get("trace_id", "")),
            metadata=source.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "process": self.process,
            "phase": self.phase,
            "wall_unix_ns": self.wall_unix_ns,
            "monotonic_ns": self.monotonic_ns,
            "request_id": self.request_id,
            "container_session_id": self.container_session_id,
            "trace_id": self.trace_id,
            "metadata": _thaw(self.metadata),
        }
