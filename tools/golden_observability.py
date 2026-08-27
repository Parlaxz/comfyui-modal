"""Stdlib-only P2 Golden observability and report harness.

This module is deliberately a consumer of persisted artifacts.  It does not
import the runtime, profiler, ComfyUI, Modal, or deployment code.  Golden
telemetry is the only timing authority; similarly named legacy profiler
fields are never used to produce a primary row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "golden_observability_p2_v1"
IDENTITY_MATRIX_SCHEMA_VERSION = "golden_identity_matrix_v1"
# P1 persisted this order.  It is an input compatibility contract, not the
# order in which a new report is allowed to display or interpret stages.
STAGE_ORDER = (
    "golden_request_setup",
    "golden_restore",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
    "golden_durable_commit",
)
PRIMARY_STAGE_ORDER = (
    "actual_restore",
    "golden_request_setup",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
    "golden_durable_commit",
)
TEARDOWN_STAGE = "golden_teardown"
PRIMARY_FUNCTION_ORDER = PRIMARY_STAGE_ORDER + (TEARDOWN_STAGE,)
PRIMARY_FUNCTION_LABELS = {
    "actual_restore": "actual_restore",
    "golden_request_setup": "golden_request_setup()",
    "golden_clip_load": "golden_clip_load()",
    "golden_clip_forward": "golden_clip_forward()",
    "golden_unet_load": "golden_unet_load()",
    "golden_sampler_prepare": "golden_sampler_prepare()",
    "golden_sampling": "golden_sampling()",
    "golden_sampler_tail": "golden_sampler_tail()",
    "golden_vae_load": "golden_vae_load()",
    "golden_vae_decode": "golden_vae_decode()",
    "golden_output": "golden_output()",
    "golden_durable_commit": "golden_durable_commit()",
    "golden_teardown": "golden_teardown()",
}
GANTT_BLOCK = "\u2588"

# These are deliberately different hash domains.  In particular, a prompt
# hash is not proof of the bytes loaded from disk, and the source/compiled
# hashes are not interchangeable with the workflow accepted by the runner.
WORKFLOW_IDENTITY_FIELDS = (
    "workflow_file_bytes_sha256",
    "parsed_workflow_json_sha256",
    "source_workflow_sha256",
    "compiled_workflow_sha256",
    "request_prompt_sha256",
    "normalized_golden_request_sha256",
    "actual_executed_workflow_sha256",
    "expected_contract_workflow_sha256",
)
LEGACY_WORKFLOW_ALIASES = {
    "workflow_hash": "source_workflow_sha256",
    "workflow_sha256": "source_workflow_sha256",
    "workflow_hash_sha256": "source_workflow_sha256",
    "source_workflow_hash": "source_workflow_sha256",
    "parsed_workflow_hash": "parsed_workflow_json_sha256",
    "prompt_sha256": "request_prompt_sha256",
    "request_hash": "request_prompt_sha256",
    "expected_workflow_sha256": "expected_contract_workflow_sha256",
    "expected_workflow_hash": "expected_contract_workflow_sha256",
    "actual_workflow_sha256": "actual_executed_workflow_sha256",
    "actual_workflow_hash": "actual_executed_workflow_sha256",
    "executed_workflow_sha256": "actual_executed_workflow_sha256",
    "compiled_workflow_hash": "compiled_workflow_sha256",
    "expected_contract_workflow_hash": "expected_contract_workflow_sha256",
}
WORKFLOW_CONTRACT_FIELDS = (
    "enabled", "bypassed", "actual_executed_workflow_sha256",
    "expected_contract_workflow_sha256",
)
WORKFLOW_CONTRACT_MARKERS = set(WORKFLOW_CONTRACT_FIELDS) | {
    alias for alias, target in LEGACY_WORKFLOW_ALIASES.items()
    if target in {"actual_executed_workflow_sha256", "expected_contract_workflow_sha256"}
}

CANONICAL_CLIP_NAME = "qwen_3_4b.safetensors"
CANONICAL_UNET_NAME = "z_image_turbo_bf16.safetensors"
CANONICAL_VAE_NAME = "ae.safetensors"

BOUNDARY_NAMES = (
    "result_assembled",
    "output_encoded",
    "file_written",
    "volume_commit_start",
    "volume_commit_complete",
    "true_first_durable_result",
    "teardown_complete",
    "remote_return",
    "client_receipt",
    "process_exit",
    "command_start",
    "python_resume",
)

_BOUNDARY_ALIASES = {
    # RESULT_ASSEMBLED is a semantic boundary, not evidence that an output
    # branch happened to execute.  Keep this deliberately exact.
    "result_assembled": {"result_assembled"},
    "output_encoded": {"output_encoded", "output_encode_done", "output_encoding_done"},
    "file_written": {"file_written", "asset_write_done", "output_file_written"},
    "volume_commit_start": {"volume_commit_start"},
    "volume_commit_complete": {"volume_commit_complete", "volume_commit_done"},
    "true_first_durable_result": {
        "true_first_durable_result", "true_first_durable",
    },
    "teardown_complete": {"teardown_complete"},
    # Deliberately do not include generic `result`/`terminal_result` names:
    # those records often describe an assembled value, not a transport edge.
    "remote_return": {"remote_return", "remote_yield", "remote_return_yield",
                       "remote_returned", "remote_result_yield"},
    "client_receipt": {"client_receipt", "client_receive", "result_received", "client_result_received"},
    "process_exit": {"process_exit", "command_exit", "process_terminated", "host_process_exit"},
    "command_start": {"command_start", "submission_start", "command_submission",
                       "command", "submission"},
    "python_resume": {"python_resume", "python_resumed", "command_to_python_resume"},
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "fresh:yes"}


def _zero(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_zero(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return all(_zero(item) for item in value)
    if isinstance(value, bool):
        return not value
    number = _number(value)
    return number == 0


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one JSON byte representation used by request hash domains."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    """Text form of the shared canonical JSON representation."""
    return canonical_json_bytes(value).decode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


canonicalize_json = canonical_json_bytes


def workflow_file_bytes_sha256(value: bytes | bytearray | memoryview | str | os.PathLike[str]) -> str:
    return hashlib.sha256(_read_workflow_bytes(value)).hexdigest()


def parsed_workflow_json_sha256(value: Any) -> str:
    return canonical_json_sha256(value)


def request_prompt_sha256(value: Any) -> str:
    return canonical_json_sha256(value)


def normalized_golden_request_sha256(value: Any) -> str:
    return canonical_json_sha256(value)


def _hash_domain_value(value: Any) -> str:
    """Accept a supplied digest, or hash raw structured input without guessing."""
    if value in (None, ""):
        return ""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(value)).hexdigest()
    if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
        return canonical_json_sha256(value)
    return str(value).strip()


def _read_workflow_bytes(value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, Path) or (isinstance(value, str) and Path(value).is_file()):
        return Path(value).read_bytes()
    raise TypeError("workflow_file_bytes must be bytes or an existing path")


def _identity_sources(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Collect explicit metadata containers, without walking arbitrary data."""
    sources = [value]
    for key in ("identity", "workflow_identity", "workflow_contract", "provenance",
                "workflow", "golden_request", "metadata", "telemetry", "golden_telemetry"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            sources.append(nested)
    return sources


def build_workflow_identity_matrix(
    source: Mapping[str, Any] | None = None,
    *,
    workflow_file_bytes: bytes | bytearray | memoryview | str | os.PathLike[str] | None = None,
    parsed_workflow: Any = None,
    source_workflow: Any = None,
    compiled_workflow: Any = None,
    request_prompt: Any = None,
    normalized_golden_request: Any = None,
    actual_executed_workflow: Any = None,
    expected_contract_workflow: Any = None,
) -> dict[str, Any]:
    """Build an explicit, lossless workflow identity projection.

    Legacy names are accepted as input only.  They are recorded under
    ``legacy_aliases`` and never emitted as ambiguous top-level identity
    fields.  Structured workflow/request inputs use :func:`canonical_json_bytes`;
    supplied digest strings remain supplied values and are not re-hashed.
    """
    root = source if isinstance(source, Mapping) else {}
    sources = _identity_sources(root)
    matrix: dict[str, Any] = {
        "schema": IDENTITY_MATRIX_SCHEMA_VERSION,
        **{name: "" for name in WORKFLOW_IDENTITY_FIELDS},
        "legacy_aliases": {},
    }

    def first(*names: str) -> Any:
        for container in sources:
            for name in names:
                if name in container and container[name] not in (None, ""):
                    return container[name]
        return None

    for field_name in WORKFLOW_IDENTITY_FIELDS:
        value = first(field_name)
        if value not in (None, ""):
            matrix[field_name] = _hash_domain_value(value)
    for alias, target in LEGACY_WORKFLOW_ALIASES.items():
        value = first(alias)
        if value in (None, ""):
            continue
        entry = {"value": _hash_domain_value(value), "field": target}
        matrix["legacy_aliases"][alias] = entry
        if not matrix[target]:
            matrix[target] = entry["value"]

    if workflow_file_bytes is not None:
        matrix["workflow_file_bytes_sha256"] = hashlib.sha256(
            _read_workflow_bytes(workflow_file_bytes)
        ).hexdigest()
    parsed = parsed_workflow if parsed_workflow is not None else first(
        "parsed_workflow", "parsed_workflow_json", "workflow_json", "parsed_prompt"
    )
    if parsed is None:
        workflow_value = first("workflow")
        if isinstance(workflow_value, (Mapping, list, tuple)) and not any(
            key in workflow_value for key in ("workflow_hash", "workflow_sha256", "prompt_sha256",
                                              "enabled", "bypassed")
        ):
            parsed = workflow_value
    if parsed is not None:
        matrix["parsed_workflow_json_sha256"] = canonical_json_sha256(parsed)
    supplied = {
        "source_workflow_sha256": source_workflow if source_workflow is not None else first(
            "source_workflow"
        ),
        "compiled_workflow_sha256": compiled_workflow if compiled_workflow is not None else first(
            "compiled_workflow"
        ),
        "request_prompt_sha256": request_prompt,
        "normalized_golden_request_sha256": normalized_golden_request,
        "actual_executed_workflow_sha256": actual_executed_workflow if actual_executed_workflow is not None else first(
            "actual_executed_workflow"
        ),
        "expected_contract_workflow_sha256": expected_contract_workflow if expected_contract_workflow is not None else first(
            "expected_contract_workflow"
        ),
    }
    structured_request = {
        "request_prompt_sha256": request_prompt if request_prompt is not None else first(
            "request_prompt", "prompt", "request"
        ),
        "normalized_golden_request_sha256": (
            normalized_golden_request if normalized_golden_request is not None else
            first("normalized_golden_request", "normalized_request", "golden_request")
        ),
    }
    for field_name, value in {**supplied, **structured_request}.items():
        if value is not None:
            matrix[field_name] = _hash_domain_value(value)
    return matrix


# Short descriptive aliases used by report consumers.
workflow_identity_matrix = build_workflow_identity_matrix
build_identity_matrix = build_workflow_identity_matrix
build_golden_identity_matrix = build_workflow_identity_matrix
build_identity_provenance = build_workflow_identity_matrix


def workflow_contract_failures(value: Mapping[str, Any] | None) -> list[str]:
    matrix = build_workflow_identity_matrix(value)
    failures: list[str] = []
    enabled = value.get("enabled") if isinstance(value, Mapping) else None
    bypassed = value.get("bypassed") if isinstance(value, Mapping) else None
    if enabled is None and isinstance(value, Mapping):
        enabled = next((item.get("enabled") for item in _identity_sources(value)
                        if "enabled" in item), None)
    if bypassed is None and isinstance(value, Mapping):
        bypassed = next((item.get("bypassed") for item in _identity_sources(value)
                         if "bypassed" in item), None)
    if not _truth(enabled):
        failures.append("workflow contract enabled must be true")
    if bypassed is not False and not (isinstance(bypassed, str) and _norm(bypassed) in {"false", "0", "no", "off"}):
        failures.append("workflow contract bypassed must be false")
    actual = matrix["actual_executed_workflow_sha256"]
    expected = matrix["expected_contract_workflow_sha256"]
    if not actual:
        failures.append("workflow contract actual_executed_workflow_sha256 is missing")
    if not expected:
        failures.append("workflow contract expected_contract_workflow_sha256 is missing")
    if actual and expected and actual != expected:
        failures.append("workflow contract actual and expected workflow hashes differ")
    return failures


def validate_workflow_contract(value: Mapping[str, Any] | None) -> dict[str, Any]:
    matrix = build_workflow_identity_matrix(value)
    reasons = workflow_contract_failures(value)
    return {
        "valid": not reasons,
        "reasons": reasons,
        "identity_matrix": matrix,
    }


def is_workflow_contract_valid(value: Mapping[str, Any] | None) -> bool:
    return not workflow_contract_failures(value)


validate_golden_workflow_contract = validate_workflow_contract


def _timestamp(value: Mapping[str, Any]) -> int | None:
    """Return a timestamp in nanoseconds, preferring Golden wall time."""
    # Monotonic timestamps are useful for diagnostics, but cannot be compared
    # with host/remote wall boundaries and are never proof of a boundary.
    for key in ("wall_ns", "event_wall_ns", "boundary_wall_ns", "wall_timestamp_ns",
                "wall_unix_ns", "return_wall_unix_ns", "yield_wall_unix_ns",
                "client_receipt_wall_unix_ns", "client_receive_wall_unix_ns",
                "receipt_wall_unix_ns", "entry_wall_ns", "end_wall_ns",
                "entry_wall_unix_ns", "end_wall_unix_ns", "remote_python_resume_wall_ns",
                "remote_python_resume_wall_unix_ns", "python_resume_wall_unix_ns",
                "command_start_wall_unix_ns", "submission_wall_unix_ns",
                "modal_submission_attempt_wall_ns", "modal_submission_attempt_wall_unix_ns",
                "timestamp_ns", "time_ns"):
        raw = value.get(key)
        number = _number(raw)
        if number is not None:
            return int(number)
    return None


def _event_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("fields", "metadata", "details", "payload"):
        value = event.get(key)
        if isinstance(value, Mapping):
            result.update(value)
    result.update({k: v for k, v in event.items() if k not in {"fields", "metadata", "details", "payload"}})
    return result


def _walk_explicit(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    """Walk JSON containers without ever selecting profiler-labelled data."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if "profiler" in child_path.lower() or "legacy" in child_path.lower():
                continue
            yield child_path, child
            yield from _walk_explicit(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield child_path, child
            yield from _walk_explicit(child, child_path)


def load_artifact(source: Mapping[str, Any] | str | os.PathLike[str]) -> tuple[dict[str, Any], str]:
    """Load one mapping or JSON path and retain its raw reference."""
    if isinstance(source, Mapping):
        return dict(source), str(source.get("artifact_ref") or source.get("path") or "<mapping>")
    path = Path(source)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("artifact JSON must contain an object")
    return data, str(path)


def _golden_telemetry(data: Mapping[str, Any]) -> dict[str, Any] | None:
    """Find an explicit Golden telemetry document, not a profiler summary."""
    candidates: list[Any] = []
    if isinstance(data.get("stages"), list):
        candidates.append(data)
    for path, value in _walk_explicit(data):
        key = path.rsplit(".", 1)[-1].lower()
        if key in {"golden_telemetry", "golden", "telemetry"} and isinstance(value, Mapping):
            candidates.append(value)
    candidates.sort(key=lambda item: 0 if str(item.get("schema", "")).startswith("golden_") else 1)
    for candidate in candidates:
        stages = candidate.get("stages")
        if isinstance(stages, list) and any(
            isinstance(stage, Mapping) and (_stage_name(stage.get("name")) is not None)
            for stage in stages
        ):
            return dict(candidate)
        # Boundary extraction is independent from stage validation.  Retain an
        # explicitly Golden event document even when its stage list is absent;
        # validation will still fail the missing-stage proof.
        if isinstance(candidate.get("events"), list) and str(candidate.get("schema", "")).startswith("golden_"):
            return dict(candidate)
    return None


@dataclass(frozen=True)
class StageWall:
    name: str
    entry_ns: int
    end_ns: int
    ready_ns: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.entry_ns) / 1_000_000.0

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({
            "name": self.name, "entry_ns": self.entry_ns, "end_ns": self.end_ns,
            "ready_ns": self.ready_ns, "duration_ms": self.duration_ms, "details": self.details,
        })


@dataclass(frozen=True)
class Boundary:
    name: str
    timestamp_ns: int
    source: str
    event_name: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({
            "name": self.name, "timestamp_ns": self.timestamp_ns, "source": self.source,
            "event_name": self.event_name, "payload": self.payload,
        })


@dataclass(frozen=True)
class GoldenExpectations:
    deployment_hash: str = ""
    source_hash: str = ""
    snapshot_id: str = ""
    workflow_sha256: str = ""
    output_sha256: str = ""
    clip_name: str = CANONICAL_CLIP_NAME
    unet_name: str = CANONICAL_UNET_NAME
    vae_name: str = CANONICAL_VAE_NAME
    gpu: str = ""
    profile: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "GoldenExpectations":
        if not value:
            return cls()
        nested: dict[str, Any] = {}
        for key in ("identity", "source_identity", "deployment_identity", "target"):
            if isinstance(value.get(key), Mapping):
                nested.update(value[key])
        value = {**nested, **dict(value)}
        names = {"deployment_hash", "source_hash", "snapshot_id", "workflow_sha256", "output_sha256",
                 "clip_name", "unet_name", "vae_name", "gpu", "profile"}
        aliases = {"output_sha": "output_sha256", "expected_output_sha": "output_sha256",
                   "workflow_hash": "workflow_sha256", "deploy_fingerprint": "deployment_hash",
                   "deployment_combined_hash": "deployment_hash", "combined_hash": "source_hash",
                   "custom_node_hash": "source_hash", "gpu_type": "gpu", "profile_name": "profile",
                   "canonical_clip_name": "clip_name", "canonical_unet_name": "unet_name",
                   "canonical_vae_name": "vae_name", "expected_deployment_hash": "deployment_hash",
                   "expected_source_hash": "source_hash", "expected_snapshot_id": "snapshot_id",
                   "expected_workflow_sha256": "workflow_sha256"}
        values: dict[str, Any] = {}
        for key, item in value.items():
            target = aliases.get(str(key), str(key))
            if target in names:
                values[target] = str(item) if item is not None else ""
        return cls(**values)


def _stage_name(name: Any) -> str | None:
    normalized = _norm(name)
    if normalized in PRIMARY_STAGE_ORDER[1:]:
        return normalized
    return None


_RESTORE_START_FIELDS = (
    "restore_method_start_wall_unix_ns",
    "restore_method_start_wall_ns",
    "restore_start_wall_unix_ns",
    "restore_start_wall_ns",
    "start_wall_unix_ns",
    "start_wall_ns",
)
_RESTORE_END_FIELDS = (
    "restore_method_end_wall_unix_ns",
    "restore_method_end_wall_ns",
    "restore_end_wall_unix_ns",
    "restore_end_wall_ns",
    "end_wall_unix_ns",
    "end_wall_ns",
)


def _adapter_restore_wall(data: Mapping[str, Any], telemetry: Mapping[str, Any]) -> StageWall | None:
    """Return the adapter-owned restore interval, if one was persisted.

    ``golden_restore`` is a request-time observation in the Golden telemetry
    stream.  It is intentionally not a timing source.  Only an explicit
    external restore metadata container can populate the primary
    ``actual_restore`` row.
    """
    candidates: list[Mapping[str, Any]] = []
    for container, key in (
        (telemetry, "external_restore"),
        (data, "external_restore"),
        (data, "restore_metadata"),
    ):
        value = container.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
    for source in candidates:
        start = next((_number(source.get(key)) for key in _RESTORE_START_FIELDS
                      if _number(source.get(key)) is not None), None)
        end = next((_number(source.get(key)) for key in _RESTORE_END_FIELDS
                    if _number(source.get(key)) is not None), None)
        if start is None or end is None:
            continue
        start_ns, end_ns = int(start), int(end)
        if end_ns < start_ns:
            raise ValueError("invalid adapter external restore wall")
        return StageWall("actual_restore", start_ns, end_ns, details=dict(source))
    return None


def extract_stage_walls(artifact: Mapping[str, Any] | str | os.PathLike[str]) -> dict[str, StageWall]:
    """Extract Golden walls and an adapter-owned actual restore interval.

    P1 ``golden_restore`` intervals remain observable input, but are never
    promoted to ``actual_restore``.
    """
    data, _ = load_artifact(artifact)
    telemetry = _golden_telemetry(data)
    if telemetry is None:
        raise ValueError("golden telemetry missing")
    stages = telemetry.get("stages")
    if not isinstance(stages, list):
        raise ValueError("golden stages missing")
    found: dict[str, StageWall] = {}
    for raw in stages:
        if not isinstance(raw, Mapping):
            continue
        name = _stage_name(raw.get("name"))
        if name is None:
            continue
        if name in found:
            raise ValueError(f"duplicate Golden stage interval: {name}")
        entry = _number(raw.get("entry_wall_ns"))
        end = _number(raw.get("end_wall_ns"))
        if entry is None or end is None or int(end) < int(entry):
            raise ValueError(f"invalid Golden stage wall: {name}")
        ready = _number(raw.get("ready_wall_ns"))
        # ready_monotonic_ns is not a wall timestamp and must not be put on a
        # wall-clock Gantt axis.
        found[name] = StageWall(name, int(entry), int(end), int(ready) if ready is not None else None,
                                 dict(raw.get("details") or {}))
    actual_restore = _adapter_restore_wall(data, telemetry)
    if actual_restore is not None:
        found["actual_restore"] = actual_restore
    missing = [name for name in PRIMARY_STAGE_ORDER if name not in found]
    if missing:
        raise ValueError("missing Golden stage intervals: " + ",".join(missing))
    return {name: found[name] for name in PRIMARY_STAGE_ORDER}


def extract_teardown_wall(artifact: Mapping[str, Any] | str | os.PathLike[str]) -> StageWall:
    data, _ = load_artifact(artifact)
    telemetry = _golden_telemetry(data)
    if telemetry is None or not isinstance(telemetry.get("stages"), list):
        raise ValueError("golden telemetry missing")
    matches = [stage for stage in telemetry["stages"]
               if isinstance(stage, Mapping) and _norm(stage.get("name")) == TEARDOWN_STAGE]
    if len(matches) != 1:
        raise ValueError("missing Golden teardown interval")
    raw = matches[0]
    entry = _number(raw.get("entry_wall_ns"))
    end = _number(raw.get("end_wall_ns"))
    if entry is None or end is None or end < entry:
        raise ValueError("invalid Golden teardown wall")
    ready = _number(raw.get("ready_wall_ns"))
    return StageWall(TEARDOWN_STAGE, int(entry), int(end), int(ready) if ready is not None else None,
                     dict(raw.get("details") or {}))


extract_exact_stage_walls = extract_stage_walls


def _golden_units(telemetry: Mapping[str, Any], data: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    direct_events = data.get("events")
    if isinstance(direct_events, list):
        for index, event in enumerate(direct_events):
            if isinstance(event, Mapping):
                yield f"artifact.events[{index}]", _event_payload(event)
    for index, event in enumerate(telemetry.get("events", []) if isinstance(telemetry.get("events"), list) else []):
        if isinstance(event, Mapping):
            yield f"golden.events[{index}]", _event_payload(event)
    for index, stage in enumerate(telemetry.get("stages", []) if isinstance(telemetry.get("stages"), list) else []):
        if isinstance(stage, Mapping):
            payload = _event_payload(stage)
            payload.setdefault("entry_wall_ns", stage.get("entry_wall_ns"))
            payload.setdefault("end_wall_ns", stage.get("end_wall_ns"))
            yield f"golden.stages[{index}]", payload
    # Host boundary records are explicit artifact data, not profiler totals.
    for key in ("boundaries", "host_timeline", "timeline"):
        value = data.get(key)
        if isinstance(value, Mapping):
            for name, item in value.items():
                if isinstance(item, Mapping):
                    payload = _event_payload(item)
                    payload.setdefault("name", name)
                    yield f"artifact.{key}.{name}", payload
                else:
                    yield f"artifact.{key}.{name}", {"name": name, "timestamp_ns": item}
    for name in BOUNDARY_NAMES:
        for key in (name, name.upper(), f"{name}_ns", f"{name.upper()}_NS"):
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, Mapping):
                payload = _event_payload(value)
                payload.setdefault("name", name)
            else:
                payload = {"name": name, "timestamp_ns": value}
            yield f"artifact.{key}", payload

    # The adapter's terminal result and restore metadata are persisted as
    # unnamed mappings.  Project only these known fields into boundary events;
    # in particular, a generic result value is not evidence of a remote return
    # and a yield timestamp is not evidence of a client receipt.
    adapter_sources: list[tuple[str, Mapping[str, Any]]] = []
    for key in ("terminal", "terminal_timing", "restore_metadata"):
        value = data.get(key)
        if isinstance(value, Mapping):
            adapter_sources.append((f"artifact.{key}", value))
    external_restore = telemetry.get("external_restore")
    if isinstance(external_restore, Mapping):
        adapter_sources.append(("golden.external_restore", external_restore))
    for index, event in enumerate(telemetry.get("events", [])
                                  if isinstance(telemetry.get("events"), list) else []):
        if not isinstance(event, Mapping):
            continue
        if _norm(event.get("name") or event.get("event") or event.get("type")) == "actual_restore":
            adapter_sources.append((f"golden.events[{index}].actual_restore", _event_payload(event)))
    for index, event in enumerate(data.get("events", [])
                                  if isinstance(data.get("events"), list) else []):
        if not isinstance(event, Mapping):
            continue
        if _norm(event.get("name") or event.get("event") or event.get("type")) == "actual_restore":
            adapter_sources.append((f"artifact.events[{index}].actual_restore", _event_payload(event)))
    adapter_sources.append(("artifact.direct", data))

    def emit_named(field_names: Sequence[str], boundary_name: str) -> Iterable[tuple[str, Mapping[str, Any]]]:
        for source_path, source in adapter_sources:
            for field_name in field_names:
                value = source.get(field_name)
                if value not in (None, ""):
                    yield (f"{source_path}.{field_name}",
                           {"name": boundary_name, field_name: value})

    yield from emit_named(
        ("client_receipt_wall_unix_ns", "client_receive_wall_unix_ns", "receipt_wall_unix_ns"),
        "client_receipt",
    )
    yield from emit_named(
        ("remote_python_resume_wall_unix_ns", "remote_python_resume_wall_ns",
         "python_resume_wall_unix_ns"),
        "python_resume",
    )
    yield from emit_named(
        ("command_start_wall_unix_ns", "submission_wall_unix_ns",
         "modal_submission_attempt_wall_ns", "modal_submission_attempt_wall_unix_ns"),
        "command_start",
    )

    return_fields = ("return_wall_unix_ns",)
    has_return = any(source.get(field) not in (None, "")
                     for _, source in adapter_sources for field in return_fields)
    yield from emit_named(return_fields if has_return else ("yield_wall_unix_ns",), "remote_return")


def extract_boundaries(artifact: Mapping[str, Any] | str | os.PathLike[str]) -> dict[str, Boundary]:
    data, _ = load_artifact(artifact)
    telemetry = _golden_telemetry(data)
    if telemetry is None:
        telemetry = {}
    result: dict[str, Boundary] = {}
    for path, payload in _golden_units(telemetry, data):
        raw_name = _norm(payload.get("name") or payload.get("event") or payload.get("type"))
        if not raw_name:
            continue
        boundary_name = next((name for name, aliases in _BOUNDARY_ALIASES.items() if raw_name in aliases), None)
        if boundary_name is None:
            continue
        stamp = _timestamp(payload)
        if stamp is None:
            continue
        candidate = Boundary(boundary_name, stamp, path, str(payload.get("name") or raw_name), dict(payload))
        old = result.get(boundary_name)
        # A Golden first marker is authoritative; retain the earliest observed
        # evidence, never a legacy summary's last total.
        if old is None or candidate.timestamp_ns < old.timestamp_ns:
            result[boundary_name] = candidate
    return result


def _find_mapping(data: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    for path, value in _walk_explicit(data):
        if isinstance(value, Mapping):
            if any(key in value for key in keys) and path.rsplit(".", 1)[-1].lower() in {
                "identity", "source_identity", "snapshot_identity", "deployment_identity", "result", "golden",
            }:
                return dict(value)
    for key in ("identity", "source_identity", "snapshot_identity", "deployment_identity"):
        value = data.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _identity(data: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    # Explicit identity projections are merged, with source/snapshot fields
    # remaining separate so one hash cannot silently stand in for the other.
    for key in ("identity", "source_identity", "snapshot_identity", "deployment_identity", "target"):
        value = data.get(key)
        if isinstance(value, Mapping):
            result.update(value)
    if isinstance(data.get("result"), Mapping):
        result.update({key: value for key, value in data["result"].items()
                       if key not in {"models", "identity"} and not isinstance(value, (list, tuple, set))})
        if isinstance(data["result"].get("identity"), Mapping):
            result.update(data["result"]["identity"])
    models = data.get("models")
    if isinstance(models, Mapping):
        result.update(models)
    for container in (data.get("identity"), data.get("result")):
        if isinstance(container, Mapping) and isinstance(container.get("models"), Mapping):
            result.update(container["models"])
        if isinstance(container, Mapping):
            for key in ("config_identity", "frozen_config"):
                if isinstance(container.get(key), Mapping):
                    result.update(container[key])
    if isinstance(data.get("identity_frozen"), Mapping):
        result.update(data["identity_frozen"])
    result.update({k: data[k] for k in (
        "deployment_hash", "deployment_combined_hash", "source_hash", "combined_hash", "snapshot_id",
        "snapshot_identity", "workflow_sha256", "workflow_hash", "clip_name", "unet_name", "vae_name",
        "gpu", "profile", "fresh", "fresh_status", "instance_id", "container_session_id", "workflow",
        "config_hash", "config_identity", "frozen_config", "deployment_source_snapshot_workflow",
    ) if k in data and not isinstance(data[k], Mapping)})
    for key in ("config_identity", "frozen_config"):
        if isinstance(data.get(key), Mapping):
            result.update(data[key])
    for nested_key in ("deployment_identity", "source_identity", "snapshot_identity", "target"):
        nested = result.get(nested_key)
        if isinstance(nested, Mapping):
            result.update(nested)
            if nested_key == "deployment_identity" and "deployment_hash" not in result and nested.get("hash"):
                result["deployment_hash"] = nested["hash"]
            if nested_key == "source_identity" and "source_hash" not in result and nested.get("hash"):
                result["source_hash"] = nested["hash"]
            if nested_key == "snapshot_identity" and "snapshot_id" not in result and nested.get("id"):
                result["snapshot_id"] = nested["id"]
    workflow = result.get("workflow")
    if isinstance(workflow, Mapping):
        for key in ("sha256", "workflow_sha256", "hash"):
            if workflow.get(key):
                result.setdefault("workflow_sha256", workflow[key])
                break
    return result


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


@dataclass
class AttemptResult:
    attempt_number: int
    valid: bool
    reasons: list[str]
    phase: str
    exception: str | None
    raw_artifact_refs: list[str]
    raw_log_refs: list[str]
    identity: dict[str, Any] = field(default_factory=dict)
    stage_walls: dict[str, StageWall] = field(default_factory=dict)
    teardown_wall: StageWall | None = None
    boundaries: dict[str, Boundary] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    artifact: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({
            "attempt_number": self.attempt_number, "valid": self.valid, "reasons": self.reasons,
            "phase": self.phase, "exception": self.exception,
            "raw_artifact_refs": self.raw_artifact_refs, "raw_log_refs": self.raw_log_refs,
            "identity": self.identity,
            "stage_walls": {k: v.to_dict() for k, v in self.stage_walls.items()},
            "teardown_wall": self.teardown_wall.to_dict() if self.teardown_wall else None,
            "boundaries": {k: v.to_dict() for k, v in self.boundaries.items()},
            "metrics": self.metrics,
            "primary_function_table": primary_function_table(self),
        })


def primary_function_table(attempt: AttemptResult | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the display table built only from explicit Golden intervals."""
    if isinstance(attempt, AttemptResult):
        walls: Mapping[str, Any] = attempt.stage_walls
        teardown: Any = attempt.teardown_wall
    else:
        walls = attempt.get("stage_walls") or {}
        teardown_value = attempt.get("teardown_wall")
        teardown = teardown_value if isinstance(teardown_value, Mapping) else None

    rows: list[dict[str, Any]] = []
    for name in PRIMARY_FUNCTION_ORDER:
        wall: Any = teardown if name == TEARDOWN_STAGE else walls.get(name)
        if wall is None:
            continue
        if isinstance(wall, StageWall):
            wall_ms = wall.duration_ms
        elif isinstance(wall, Mapping):
            entry = _number(wall.get("entry_ns"))
            end = _number(wall.get("end_ns"))
            if entry is None or end is None or end < entry:
                continue
            wall_ms = (end - entry) / 1_000_000.0
        else:
            continue
        rows.append({"function": PRIMARY_FUNCTION_LABELS[name], "wall_ms": wall_ms})
    return rows


build_primary_function_table = primary_function_table


def render_primary_function_table(attempt: AttemptResult | Mapping[str, Any]) -> str:
    """Render a readable text form of :func:`primary_function_table`."""
    rows = primary_function_table(attempt)
    if not rows:
        return "GOLDEN PRIMARY FUNCTION TABLE unavailable: no Golden stage intervals"
    lines = ["GOLDEN PRIMARY FUNCTION TABLE", "function                       wall_ms"]
    lines.extend(f"{row['function']:<30} {row['wall_ms']:.3f}" for row in rows)
    return "\n".join(lines)


def _proof(data: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("snapshot_proof", "golden_snapshot_proof", "snapshot_content_proof"):
        value = data.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    telemetry = _golden_telemetry(data)
    if telemetry:
        for event in telemetry.get("events", []):
            if isinstance(event, Mapping) and _norm(event.get("name")) == "snapshot_proof_complete":
                payload = _event_payload(event)
                if isinstance(payload.get("proof"), Mapping):
                    return dict(payload["proof"])
                if any(key in payload for key in ("clip_model_bytes", "unet_model_bytes", "vae_model_bytes", "roles")):
                    return payload
    return {}


def _proof_pre_capture(data: Mapping[str, Any], telemetry: Mapping[str, Any],
                       proof: Mapping[str, Any]) -> bool:
    """Only an explicit Golden pre-capture PASS is snapshot evidence."""
    candidates: list[Any] = []
    for key in ("pre_capture", "golden_pre_capture", "pre_capture_proof", "pre_capture_status",
                "pre_capture_pass", "golden_pre_capture_pass"):
        if key in proof:
            candidates.append(proof[key])
        if key in data:
            candidates.append(data[key])
    events = telemetry.get("events", [])
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, Mapping):
                continue
            name = _norm(event.get("name") or event.get("event"))
            if "pre_capture" in name and "snapshot" in name:
                candidates.append(_event_payload(event))
    for value in candidates:
        if isinstance(value, Mapping):
            status = _pick(value, "status", "result", "outcome", "ok")
            if str(status or "").strip().upper() in {"PASS", "PASSED", "OK", "TRUE"}:
                return True
        elif str(value).strip().upper() in {"PASS", "PASSED", "OK", "TRUE"}:
            return True
    return False


def _value_any(mappings: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> tuple[bool, Any]:
    for mapping in mappings:
        value = _pick(mapping, *keys)
        if value is not None:
            return True, value
    return False, None


def _zero_proof(proof: Mapping[str, Any], reasons: list[str]) -> None:
    groups = {
        "clip_model_bytes": ("clip_model_bytes", "clip_bytes", "clip_parameter_bytes"),
        "unet_model_bytes": ("unet_model_bytes", "unet_bytes", "unet_parameter_bytes"),
        "vae_model_bytes": ("vae_model_bytes", "vae_bytes", "vae_parameter_bytes"),
        "QD owners": ("qd_owner_count", "qd_owners"),
        "QD readers": ("qd_reader_count", "qd_readers", "open_payload_reader_count"),
        "model preload workers": ("model_preload_worker_count", "preload_worker_count"),
        "futures": ("future_count", "unresolved_future_count", "futures_at_boundary"),
    }
    for label, keys in groups.items():
        present, value = _value_any((proof,), keys)
        if not present and label.endswith("model_bytes"):
            role = label.split("_", 1)[0].lower()
            roles = proof.get("roles")
            role_proof = roles.get(role) if isinstance(roles, Mapping) else None
            if isinstance(role_proof, Mapping):
                present, value = _value_any((role_proof,), ("model_bytes", "parameter_bytes",
                                                            "model_parameter_bytes"))
        if not present:
            reasons.append(f"snapshot proof missing {label}")
            continue
        if isinstance(value, Mapping):
            count = _pick(value, "count", "bytes", "total", "at_boundary")
            numbers = [_number(count)] if count is not None else [_number(v) for v in value.values()]
            bad = any(v is None or v != 0 for v in numbers)
        else:
            number = _number(value)
            bad = number is None or number != 0
        if bad:
            reasons.append(f"snapshot proof {label} is nonzero")


def _identity_failures(identity: Mapping[str, Any], expected: GoldenExpectations, reasons: list[str]) -> None:
    fields = {
        "deployment hash": ("deployment_hash", "deployment_combined_hash", "deployment_sha256", "deploy_hash"),
        "source hash": ("source_hash", "combined_hash", "source_sha256", "custom_node_hash", "runtime_hash"),
        "snapshot ID": ("snapshot_id", "snapshot", "snapshot_identity"),
        "workflow hash": ("workflow_sha256", "workflow_hash", "prompt_sha256", "workflow_sha256_hash", "workflow"),
        "clip name": ("clip_name", "clip_model", "clip_model_name", "canonical_clip_name"),
        "unet name": ("unet_name", "unet_model", "unet_model_name", "canonical_unet_name"),
        "vae name": ("vae_name", "vae_model", "vae_model_name", "canonical_vae_name"),
        "GPU": ("gpu", "gpu_type", "accelerator"),
        "profile": ("profile", "profile_name"),
    }
    expected_values = {
        "deployment hash": expected.deployment_hash, "source hash": expected.source_hash,
        "snapshot ID": expected.snapshot_id, "workflow hash": expected.workflow_sha256,
        "clip name": expected.clip_name, "unet name": expected.unet_name, "vae name": expected.vae_name,
        "GPU": expected.gpu, "profile": expected.profile,
    }
    for label, keys in fields.items():
        observed = _pick(identity, *keys)
        if observed in (None, "", {}) or isinstance(observed, (Mapping, list, tuple, set)):
            reasons.append(f"identity missing {label}")
        elif expected_values[label] and str(observed) != expected_values[label]:
            reasons.append(f"identity {label} mismatch")


def _execution_failures(data: Mapping[str, Any], telemetry: Mapping[str, Any], proof: Mapping[str, Any],
                        walls: Mapping[str, StageWall], teardown: StageWall | None,
                        reasons: list[str]) -> None:
    execution_value = data.get("execution")
    execution: Mapping[str, Any] = execution_value if isinstance(execution_value, Mapping) else {}
    sources: tuple[Mapping[str, Any], ...] = (execution, telemetry, proof)
    quiescence = _pick(execution, "stage_boundary_quiescence", "boundary_quiescence", "stage_boundaries")
    if not isinstance(quiescence, Mapping):
        reasons.append("execution stage-boundary quiescence proof missing")
    else:
        # actual_restore belongs to the adapter, not the Golden execution
        # runner.  It therefore cannot be satisfied by a Golden quiescence
        # record (and must not make an otherwise direct proof look complete).
        expected_stages = ({name for name in walls if name != "actual_restore"}
                           | ({TEARDOWN_STAGE} if teardown else set()))
        for stage in expected_stages:
            value = quiescence.get(stage)
            if not isinstance(value, Mapping):
                reasons.append(f"execution quiescence missing at {stage}")
                continue
            for label, keys in (("unresolved worker", ("unresolved_worker_count", "unresolved_workers", "workers")),
                                ("future at boundary", ("futures_at_boundary", "unresolved_future_count", "future_count", "futures"))):
                present, count = _value_any((value,), keys)
                if not present:
                    reasons.append(f"execution {label} missing at {stage}")
                elif not ((isinstance(count, bool) and not count) or _number(count) == 0):
                    reasons.append(f"execution {label} is nonzero at {stage}")
    present, fallback = _value_any(sources, ("fallback", "fallback_count", "fallbacks"))
    if not present:
        reasons.append("execution fallback proof missing")
    elif isinstance(fallback, Mapping):
        if not _zero(fallback):
            reasons.append("execution fallback is nonzero")
    elif not _zero(fallback):
        reasons.append("execution fallback is nonzero")
    present, lifecycle = _value_any((execution,), ("source_lifecycle_by_model", "source_lifecycles", "source_lifecycle"))
    if not present:
        reasons.append("execution per-model source lifecycle proof missing")
    elif isinstance(lifecycle, Mapping):
        role_values = []
        for role in ("clip", "unet", "vae"):
            role_names = {
                "clip": {role, "golden_clip", "clip_model", _norm(CANONICAL_CLIP_NAME)},
                "unet": {role, "golden_unet", "unet_model", _norm(CANONICAL_UNET_NAME)},
                "vae": {role, "golden_vae", "vae_model", _norm(CANONICAL_VAE_NAME)},
            }[role]
            value = next((v for k, v in lifecycle.items()
                          if (_norm(k) in role_names or role in _norm(k))
                          and not _norm(k).startswith("total")), None)
            if value is None:
                reasons.append(f"execution source lifecycle missing for {role}")
                continue
            if isinstance(value, (list, tuple)):
                count = len(value)
            else:
                count = _pick(value, "count", "lifecycle_count", "instances") if isinstance(value, Mapping) else value
            role_values.append(_number(count))
            if _number(count) != 1:
                reasons.append(f"execution requires exactly one source lifecycle for {role}")
        if not role_values and any(key in lifecycle for key in ("count", "lifecycle_count", "instances")):
            reasons.append("execution requires per-model, not global, source lifecycles")
    elif isinstance(lifecycle, list):
        reasons.append("execution requires per-model, not global, source lifecycles")
    else:
        reasons.append("execution requires per-model, not global, source lifecycles")
    present, duplicate = _value_any(sources, ("duplicate_model_sized_h2d", "duplicate_model_sized_h2d_count", "h2d_model_sized_count"))
    if not present:
        reasons.append("execution duplicate model-sized H2D proof missing")
    elif not _zero(duplicate):
        reasons.append("duplicate model-sized H2D observed")
    present, forward = _value_any((execution,), ("real_clip_forward", "real_clip_forward_observed"))
    if not present or not (forward is True or (isinstance(forward, Mapping)
                                               and _pick(forward, "real", "observed") is True)):
        reasons.append("real CLIP forward proof missing")


def _explicit_telemetry_event(telemetry: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    events = telemetry.get("events")
    if not isinstance(events, list):
        return None
    expected = _norm(name)
    for event in events:
        if not isinstance(event, Mapping):
            continue
        raw_name = _norm(event.get("name") or event.get("event") or event.get("type"))
        if raw_name == expected:
            return _event_payload(event)
    return None


def _persistence_status(value: Any, *, allow_status: bool = False) -> bool | None:
    """Interpret only explicit telemetry-persistence evidence."""
    if isinstance(value, Mapping):
        keys = ["telemetry_persisted", "golden_telemetry_persisted", "persisted"]
        if allow_status:
            keys.append("status")
        for key in keys:
            if key not in value:
                continue
            observed = value[key]
            return _truth(observed)
        path = _pick(value, "telemetry_path", "persisted_path")
        if path not in (None, ""):
            return True
        return None
    if value is None:
        return None
    return _truth(value)


def _telemetry_persistence_proof(data: Mapping[str, Any], telemetry: Mapping[str, Any],
                                 teardown: StageWall | None,
                                 teardown_event: Mapping[str, Any] | None) -> bool:
    """Require a direct, positive indication that complete telemetry was saved."""
    candidates: list[tuple[Any, bool]] = []
    for container in (data, telemetry):
        for key in ("telemetry_persistence", "golden_telemetry_persistence",
                    "telemetry_persisted", "golden_telemetry_persisted"):
            if key in container:
                candidates.append((container[key], True))
    if teardown_event is not None:
        candidates.append((teardown_event, False))
    if teardown is not None:
        candidates.append((teardown.details, False))
    return any(_persistence_status(value, allow_status=allow_status) is True
               for value, allow_status in candidates)


def validate_attempt(
    source: Mapping[str, Any] | str | os.PathLike[str],
    expectations: GoldenExpectations | Mapping[str, Any] | None = None,
    *,
    attempt_number: int | None = None,
) -> AttemptResult:
    """Validate one artifact.  Every absent proof is a failure."""
    ref = str(source) if not isinstance(source, Mapping) else str(source.get("artifact_ref") or "<mapping>")
    number = attempt_number
    if number is None and isinstance(source, Mapping):
        number = int(_number(source.get("attempt_number", source.get("run_index", 1))) or 1)
    number = number or 1
    try:
        data, ref = load_artifact(source)
    except Exception as exc:
        return AttemptResult(number, False, [f"artifact ingest failed: {type(exc).__name__}: {exc}"], "ingest",
                             f"{type(exc).__name__}: {exc}", [ref], [], artifact={})
    expected = expectations if isinstance(expectations, GoldenExpectations) else GoldenExpectations.from_mapping(expectations)
    if not expected.output_sha256 and data.get("expected_output_sha"):
        expected = GoldenExpectations.from_mapping({**expected.__dict__, "output_sha256": data["expected_output_sha"]})
    reasons: list[str] = []
    telemetry = _golden_telemetry(data)
    if telemetry is None:
        reasons.append("Golden telemetry missing; legacy profiler telemetry is not authoritative")
        telemetry = {}
    seriality = telemetry.get("seriality")
    if not isinstance(seriality, Mapping):
        reasons.append("Golden seriality proof missing")
    else:
        violations = seriality.get("violations")
        serial_ok = (isinstance(violations, list) and not violations) or _number(seriality.get("count")) == 0
        if seriality.get("ok") is not True or not serial_ok:
            reasons.append("Golden seriality proof reports a violation")
    try:
        walls = extract_stage_walls(data)
    except Exception as exc:
        walls = {}
        reasons.append(str(exc))
    boundaries = extract_boundaries(data)
    identity = _identity(data)
    identity_matrix = build_workflow_identity_matrix(data)
    identity.update({key: value for key, value in identity_matrix.items()
                     if key in WORKFLOW_IDENTITY_FIELDS and value})
    identity["workflow_identity_matrix"] = identity_matrix
    _identity_failures(identity, expected, reasons)
    # P2 artifacts did not carry this contract.  Retain their read
    # compatibility, but once a producer emits any contract field, accepting
    # it is fail-closed rather than silently falling back to ``workflow_hash``.
    contract_input = dict(data)
    contract_input["telemetry"] = telemetry
    contract_keys = WORKFLOW_CONTRACT_MARKERS
    if any(key in contract_input for key in contract_keys) or any(
        isinstance(container, Mapping) and any(key in container for key in contract_keys)
        for container in _identity_sources(contract_input)
    ):
        reasons.extend(workflow_contract_failures(contract_input))
    frozen = _pick(data, "identity_frozen", "frozen_identity", "frozen_identity_proof")
    if frozen is None:
        reasons.append("freshness frozen identity proof missing")
    elif isinstance(frozen, Mapping):
        if not frozen or frozen.get("ok") is False:
            reasons.append("freshness frozen identity proof is invalid")
    elif not _truth(frozen):
        reasons.append("freshness frozen identity proof is invalid")
    if _pick(identity, "config_hash", "config_sha256", "configuration_hash", "config_identity") in (None, "", {}):
        reasons.append("freshness frozen config identity missing")
    proof = _proof(data)
    if not proof:
        reasons.append("snapshot proof missing")
    elif not _proof_pre_capture(data, telemetry, proof):
        reasons.append("snapshot proof missing explicit Golden pre-capture PASS")
    _zero_proof(proof, reasons)

    if not data.get("backend_ok", True) or data.get("error"):
        reasons.append("backend attempt failed")
    required_boundaries = {
        "result_assembled", "output_encoded", "file_written", "volume_commit_start",
        "volume_commit_complete", "true_first_durable_result", "teardown_complete",
        "remote_return", "client_receipt", "command_start", "python_resume",
    }
    missing = sorted(required_boundaries - set(boundaries))
    reasons.extend(f"boundary missing {name}" for name in missing)
    teardown_event = _explicit_telemetry_event(telemetry, "teardown_complete")
    if teardown_event is None:
        reasons.append("Golden telemetry missing explicit TEARDOWN_COMPLETE event")
    for before, after in (("command_start", "python_resume"),
                          ("python_resume", "true_first_durable_result"),
                          ("true_first_durable_result", "result_assembled"),
                          ("result_assembled", "teardown_complete"),
                          ("teardown_complete", "remote_return"),
                          ("remote_return", "client_receipt"),
                          ("command_start", "client_receipt"),
                          ("output_encoded", "file_written"),
                          ("volume_commit_start", "volume_commit_complete"),
                          ("volume_commit_complete", "true_first_durable_result"),
                          # Process exit is an optional external tail.  If it
                          # is present, validate it; its absence is valid.
                          ("remote_return", "process_exit")):
        if before in boundaries and after in boundaries and boundaries[after].timestamp_ns < boundaries[before].timestamp_ns:
            reasons.append(f"boundary ordering is not serial: {before} -> {after}")
    for before, after in (("true_first_durable_result", "result_assembled"),
                          ("result_assembled", "teardown_complete"),
                          ("teardown_complete", "remote_return")):
        if before in boundaries and after in boundaries and boundaries[after].timestamp_ns <= boundaries[before].timestamp_ns:
            reasons.append(f"boundary ordering must be strict: {before} < {after}")

    # The Gantt and all primary timing rows come from Golden walls, never from
    # an elapsed/profiler total.  Check the complete function sequence here.
    teardown_wall: StageWall | None = None
    if walls:
        try:
            teardown_wall = extract_teardown_wall(data)
        except Exception as exc:
            reasons.append(str(exc))
        raw_stages = telemetry.get("stages")
        golden_stages: list[Any] = list(raw_stages) if isinstance(raw_stages, list) else []
        observed: list[StageWall] = []
        for raw in golden_stages:
            if not isinstance(raw, Mapping):
                continue
            name = _stage_name(raw.get("name"))
            if name is None and _norm(raw.get("name")) != TEARDOWN_STAGE:
                continue
            entry = _number(raw.get("entry_wall_ns"))
            end = _number(raw.get("end_wall_ns"))
            if entry is None or end is None:
                reasons.append(f"Golden stage wall timestamps missing: {raw.get('name')}")
                continue
            observed.append(StageWall(name or TEARDOWN_STAGE, int(entry), int(end)))
            if raw.get("ok") is not True:
                reasons.append(f"Golden stage failed: {raw.get('name')}")
        # Seriality is based on the observed wall intervals, not on P1's
        # historical function tuple.  This accepts both request->restore and
        # restore->request telemetry while still rejecting reordering/overlap.
        for previous, current in zip(observed, observed[1:]):
            if current.entry_ns < previous.entry_ns:
                reasons.append("Golden observed stage order is not serial")
            if current.entry_ns < previous.end_ns:
                reasons.append("Golden stage intervals overlap")
        ordered_primary = [walls[name] for name in PRIMARY_STAGE_ORDER if name in walls]
        for previous, current in zip(ordered_primary, ordered_primary[1:]):
            if current.entry_ns < previous.entry_ns:
                reasons.append("Golden primary interval order is not serial")
            if current.entry_ns < previous.end_ns:
                reasons.append("Golden primary intervals overlap")
        if "actual_restore" in walls and "python_resume" in boundaries:
            if walls["actual_restore"].entry_ns <= boundaries["python_resume"].timestamp_ns:
                reasons.append("adapter actual restore does not follow Python resume")
        if "actual_restore" in walls and "golden_request_setup" in walls:
            if walls["golden_request_setup"].entry_ns < walls["actual_restore"].end_ns:
                reasons.append("adapter actual restore overlaps request setup")
        if teardown_wall and observed:
            execution_end = max(item.end_ns for item in observed if item.name != TEARDOWN_STAGE)
            if teardown_wall.entry_ns < execution_end:
                reasons.append("Golden teardown interval overlaps the execution stages")

        # The adapter event is a point after the complete teardown function,
        # not a substitute for its interval.  RESULT_ASSEMBLED must likewise
        # precede teardown entry.
        if teardown_wall and "result_assembled" in boundaries:
            if boundaries["result_assembled"].timestamp_ns >= teardown_wall.entry_ns:
                reasons.append("RESULT_ASSEMBLED does not precede golden teardown")
        if teardown_wall and "teardown_complete" in boundaries:
            if boundaries["teardown_complete"].timestamp_ns <= teardown_wall.end_ns:
                reasons.append("TEARDOWN_COMPLETE precedes golden teardown end")

    # Re-evaluate persistence after teardown extraction so a direct teardown
    # interval detail can carry the proof when the event carries only a name.
    if not _telemetry_persistence_proof(data, telemetry, teardown_wall, teardown_event):
        reasons.append("telemetry persistence proof missing or not confirmed")

    _execution_failures(data, telemetry, proof, walls, teardown_wall, reasons)

    telemetry_events = telemetry.get("events", []) if isinstance(telemetry.get("events"), list) else []
    reopen = [
        _event_payload(event) for event in telemetry_events
        if isinstance(event, Mapping) and any(token in _norm(event.get("name"))
                                              for token in ("reopen", "re_open", "object_verified"))
    ]
    for container in (data.get("durability"), data.get("reopen_proof")):
        if isinstance(container, Mapping):
            candidate = container.get("reopen") or container.get("durable_reopen") or container.get("reopen_proof")
            if isinstance(candidate, Mapping):
                reopen.append(dict(candidate))
            elif any(key in container for key in ("ok", "verified", "reopened")):
                reopen.append(dict(container))
    result_container = data.get("result")
    if isinstance(result_container, Mapping):
        for key in ("reopen", "durable_reopen", "reopen_proof"):
            if isinstance(result_container.get(key), Mapping):
                reopen.append(dict(result_container[key]))
    standalone = data.get("boundaries")
    if isinstance(standalone, Mapping):
        for name, value in standalone.items():
            if "reopen" in _norm(name) or "object_verified" in _norm(name):
                item = _event_payload(value) if isinstance(value, Mapping) else {"timestamp_ns": value}
                item.setdefault("name", name)
                reopen.append(item)
    reopen_times = [_timestamp(item) for item in reopen]
    if not reopen:
        reasons.append("durability reopen proof missing")
    else:
        verified = [item for item in reopen if _truth(_pick(item, "ok", "verified", "reopened"))]
        if not verified:
            reasons.append("durability reopen proof is not verified")
        observed_reopen_sha = next((_pick(item, "sha256", "output_sha", "content_sha256") for item in reopen if _pick(item, "sha256", "output_sha", "content_sha256")), None)
        if expected.output_sha256 and not observed_reopen_sha:
            reasons.append("durability reopen hash missing")
        elif expected.output_sha256 and str(observed_reopen_sha).lower() != expected.output_sha256.lower():
            reasons.append("durability reopen hash mismatch")
        if not any(stamp is not None for stamp in reopen_times):
            reasons.append("durability reopen timestamp missing")
        elif "volume_commit_complete" in boundaries and not any(
                stamp > boundaries["volume_commit_complete"].timestamp_ns
                for stamp in reopen_times if stamp is not None):
            reasons.append("durability reopen did not follow commit complete")
        verified_times = [stamp for item, stamp in zip(reopen, reopen_times)
                          if stamp is not None and _truth(_pick(item, "ok", "verified", "reopened"))]
        if "true_first_durable_result" in boundaries and verified_times and not any(
                boundaries["true_first_durable_result"].timestamp_ns > stamp for stamp in verified_times):
            reasons.append("TRUE_FIRST_DURABLE_RESULT precedes verified reopen")

    fresh = _pick(identity, "fresh", "fresh_status")
    if str(fresh or "").strip().upper() != "FRESH:YES":
        reasons.append("freshness requires explicit Fresh:YES")
    instance = _pick(identity, "instance_id", "container_session_id", "container_task_id", "restored_instance_id")
    if not instance:
        reasons.append("freshness instance identity missing")
    output_sha = _pick(data, "output_sha", "output_sha256", "content_sha256")
    if output_sha is None and isinstance(data.get("result"), Mapping):
        output_sha = _pick(data["result"], "output_sha", "output_sha256", "content_sha256")
    if output_sha is None:
        for name in ("output_encoded", "file_written", "true_first_durable_result"):
            if name in boundaries:
                output_sha = _pick(boundaries[name].payload, "sha256", "output_sha", "content_sha256")
                if output_sha:
                    break
    if not expected.output_sha256:
        reasons.append("correctness expected output SHA missing")
    elif not output_sha:
        reasons.append("correctness output SHA missing")
    elif str(output_sha).lower() != expected.output_sha256.lower():
        reasons.append("correctness output SHA mismatch")

    phase = str(data.get("phase") or data.get("failed_phase") or ("complete" if not reasons else "validation"))
    raw_logs: list[str] = []
    for key in ("raw_log_ref", "raw_log_refs", "raw_logs", "console_capture", "log_path"):
        raw_value = data.get(key)
        if raw_value in (None, ""):
            continue
        raw_logs.extend(str(item) for item in (raw_value if isinstance(raw_value, list) else [raw_value]))
    exception = data.get("exception") or data.get("error")
    raw_refs = [ref]
    for key in ("raw_artifact_refs", "artifact_refs"):
        value = data.get(key)
        if isinstance(value, list):
            raw_refs.extend(str(item) for item in value)
        elif value not in (None, ""):
            raw_refs.append(str(value))
    metrics: dict[str, float] = {}
    if walls:
        metrics.update({f"{name}_ms": wall.duration_ms for name, wall in walls.items()})
        metrics["golden_stage_sum_ms"] = sum(walls[name].duration_ms for name in PRIMARY_STAGE_ORDER)
    if "actual_restore" in walls:
        metrics["restore_ms"] = walls["actual_restore"].duration_ms

    boundary_pairs = {
        "command_start_to_python_resume_ms": ("command_start", "python_resume"),
        "python_resume_to_true_first_durable_result_ms": ("python_resume", "true_first_durable_result"),
        "true_first_durable_result_to_result_assembled_ms": (
            "true_first_durable_result", "result_assembled"),
        "result_assembled_to_teardown_complete_ms": (
            "result_assembled", "teardown_complete"),
        "teardown_complete_to_remote_return_ms": (
            "teardown_complete", "remote_return"),
        "true_first_durable_result_to_remote_return_ms": (
            "true_first_durable_result", "remote_return"),
        "remote_return_to_client_receipt_ms": ("remote_return", "client_receipt"),
        "command_start_to_client_receipt_ms": ("command_start", "client_receipt"),
        # This is intentionally separate from the application tail above:
        # it spans all the way from durable output to host receipt.
        "true_first_durable_result_to_client_receipt_ms": (
            "true_first_durable_result", "client_receipt"),
    }
    for metric_name, (before, after) in boundary_pairs.items():
        if before in boundaries and after in boundaries:
            metrics[metric_name] = (boundaries[after].timestamp_ns - boundaries[before].timestamp_ns) / 1_000_000

    # Keep the P2 names as aliases while giving each boundary an explicit
    # canonical name.  In particular, post_durable_tail is durable -> remote,
    # never durable -> client.
    if "python_resume_to_true_first_durable_result_ms" in metrics:
        metrics["remote_python_resume_to_true_first_durable_result_ms"] = metrics[
            "python_resume_to_true_first_durable_result_ms"]
    if "true_first_durable_result_to_remote_return_ms" in metrics:
        metrics["post_durable_tail_ms"] = metrics["true_first_durable_result_to_remote_return_ms"]
    if "command_start_to_client_receipt_ms" in metrics:
        metrics["command_to_client_receipt_ms"] = metrics["command_start_to_client_receipt_ms"]
        metrics["command_to_result_ms"] = metrics["command_start_to_client_receipt_ms"]
        metrics["whole_path_ms"] = metrics["command_start_to_client_receipt_ms"]
        metrics["whole_path_command_start_to_client_receipt_ms"] = metrics[
            "command_start_to_client_receipt_ms"]
        metrics["whole_path_command_to_client_receipt_ms"] = metrics[
            "command_start_to_client_receipt_ms"]
    if "true_first_durable_result_to_client_receipt_ms" in metrics:
        metrics["whole_path_durable_to_client_receipt_ms"] = metrics[
            "true_first_durable_result_to_client_receipt_ms"]
        metrics["whole_path_durable_to_receipt_ms"] = metrics[
            "true_first_durable_result_to_client_receipt_ms"]
    if "python_resume_to_true_first_durable_result_ms" in metrics and "client_receipt" in boundaries:
        metrics["whole_path_python_resume_to_client_receipt_ms"] = (
            boundaries["client_receipt"].timestamp_ns - boundaries["python_resume"].timestamp_ns
        ) / 1_000_000
    if teardown_wall is not None:
        metrics["teardown_ms"] = teardown_wall.duration_ms
    return AttemptResult(number, not reasons, reasons, phase, str(exception) if exception else None,
                         raw_refs, raw_logs, identity, walls, teardown_wall, boundaries, metrics, data)


validate_golden_attempt = validate_attempt


P90_METHOD = "nearest_rank(ceil(0.90*n)); n=5=>rank5"
STATS_METHOD = P90_METHOD + "; stdev=sample; no trimming"


def _percentile_p90(values: Sequence[float]) -> float:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        raise ValueError("p90 requires values")
    # Explicit n=5 method: nearest rank, ceil(0.90*n).  Thus a five-run p90
    # is the fifth (maximum) observation, matching the existing variance
    # reports and avoiding an invented interpolation between runs.
    rank = max(1, math.ceil(0.90 * len(ordered)))
    return ordered[rank - 1]


def compute_stats(values: Sequence[float]) -> dict[str, Any]:
    numbers = [float(v) for v in values]
    if not numbers:
        return {
            "n": 0, "min": None, "max": None, "median": None, "mean": None,
            "p90": None, "stdev": None, "cv": None, "range": None,
            "values": [], "raw_values": [], "raw_observations": [],
            "observations": [], "raw": [], "sample_stdev": None,
            "coefficient_of_variation": None, "p90_method": P90_METHOD,
            "method": STATS_METHOD,
        }
    mean = statistics.mean(numbers)
    stdev = statistics.stdev(numbers) if len(numbers) > 1 else 0.0
    return {
        "n": len(numbers), "min": min(numbers), "max": max(numbers), "mean": mean,
        "median": statistics.median(numbers), "p90": _percentile_p90(numbers),
        "stdev": stdev, "cv": stdev / mean if mean else None, "range": max(numbers) - min(numbers),
        # Preserve every observation.  ``values`` is the P2 compatibility
        # spelling; the explicit names make it impossible for a renderer to
        # imply trimming or percentile-only input.
        "values": numbers, "raw_values": numbers, "raw_observations": numbers,
        "observations": numbers, "raw": numbers, "sample_stdev": stdev,
        "coefficient_of_variation": stdev / mean if mean else None,
        "p90_method": P90_METHOD, "method": STATS_METHOD,
    }


def render_golden_gantt(attempt: AttemptResult | Mapping[str, Any], *, width: int = 80,
                        include_qd_detail: bool = True) -> str:
    """Render actual timestamp-scaled Golden intervals with solid blocks."""
    if isinstance(attempt, AttemptResult):
        walls = attempt.stage_walls
        if attempt.teardown_wall is not None:
            walls = {**walls, TEARDOWN_STAGE: attempt.teardown_wall}
        boundaries = attempt.boundaries
        artifact = attempt.artifact
    else:
        walls = {}
        for name, value in (attempt.get("stage_walls") or {}).items():
            if isinstance(value, Mapping):
                walls[name] = StageWall(name, int(value["entry_ns"]), int(value["end_ns"]))
        teardown_value = attempt.get("teardown_wall")
        if isinstance(teardown_value, Mapping):
            walls[TEARDOWN_STAGE] = StageWall(TEARDOWN_STAGE, int(teardown_value["entry_ns"]),
                                              int(teardown_value["end_ns"]))
        boundaries = {}
        artifact = attempt
    if not walls:
        return "GOLDEN GANTT unavailable: no Golden stage intervals"
    start = min(w.entry_ns for w in walls.values())
    end = max(w.end_ns for w in walls.values())
    span = max(end - start, 1)
    width = max(1, int(width))
    lines = [f"GOLDEN GANTT start_ns {start} end_ns {end} width {width}"]
    for name in PRIMARY_STAGE_ORDER + (TEARDOWN_STAGE,):
        wall = walls.get(name)
        if wall is None:
            continue
        left = max(0, min(width - 1, int((wall.entry_ns - start) * width / span)))
        right = max(left + 1, min(width, int(math.ceil((wall.end_ns - start) * width / span))))
        lines.append(f"{name:<28} {(' ' * left) + (GANTT_BLOCK * (right - left))}")
    if include_qd_detail:
        telemetry = _golden_telemetry(artifact) if isinstance(artifact, Mapping) else None
        events = (telemetry or {}).get("events", [])
        qd = [event for event in events if isinstance(event, Mapping) and "qd" in _norm(event.get("name"))]
        child = [event for event in events if isinstance(event, Mapping) and any(
            token in _norm(event.get("name")) for token in ("qd", "construction", "adoption"))]
        if child:
            labels = [str(event.get("name")).replace("=", " ") for event in child]
            prefix = "QD child detail: " if any("qd" in _norm(event.get("name")) for event in child) else "child detail: "
            lines.append(prefix + ", ".join(labels))
    return "\n".join(lines)


def _cohort_identity_key(identity: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(_pick(identity, *keys) or "") for keys in (
        ("deployment_hash", "deployment_combined_hash", "deployment_sha256"),
        ("source_hash", "combined_hash", "source_sha256", "custom_node_hash"),
        ("snapshot_id", "snapshot_identity"), ("workflow_sha256", "workflow_hash"),
        ("clip_name", "clip_model"), ("unet_name", "unet_model"), ("vae_name", "vae_model"),
        ("gpu", "gpu_type"), ("profile", "profile_name"),
        ("config_hash", "config_sha256", "configuration_hash", "config_identity", "frozen_config"),
    ))


WHOLE_PATH_METRIC_NAMES = (
    "command_start_to_python_resume_ms",
    "python_resume_to_true_first_durable_result_ms",
    "true_first_durable_result_to_result_assembled_ms",
    "result_assembled_to_teardown_complete_ms",
    "teardown_complete_to_remote_return_ms",
    "true_first_durable_result_to_remote_return_ms",
    "remote_return_to_client_receipt_ms",
    "command_start_to_client_receipt_ms",
    "true_first_durable_result_to_client_receipt_ms",
    "remote_python_resume_to_true_first_durable_result_ms",
    "command_to_client_receipt_ms",
    "command_to_result_ms",
    "whole_path_ms",
    "whole_path_command_start_to_client_receipt_ms",
    "whole_path_command_to_client_receipt_ms",
    "whole_path_durable_to_client_receipt_ms",
    "whole_path_durable_to_receipt_ms",
    "whole_path_python_resume_to_client_receipt_ms",
    "restore_ms",
    "post_durable_tail_ms",
    "teardown_ms",
)


@dataclass
class CohortReport:
    attempts: list[AttemptResult]
    valid_attempts: list[AttemptResult]
    invalid_attempts: list[AttemptResult]
    valid: bool
    reasons: list[str]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({
            "schema": SCHEMA_VERSION, "valid": self.valid, "reasons": self.reasons,
            "attempts": [a.to_dict() for a in self.attempts],
            "valid_attempts": [a.to_dict() for a in self.valid_attempts],
            "invalid_attempts": [a.to_dict() for a in self.invalid_attempts], "stats": self.stats,
        })


def build_five_run_cohort(sources: Iterable[Mapping[str, Any] | str | os.PathLike[str]],
                          expectations: GoldenExpectations | Mapping[str, Any] | None = None) -> CohortReport:
    if isinstance(sources, (str, os.PathLike)):
        path = Path(sources)
        if path.is_dir():
            sources = sorted(path.glob("attempt_*.json"))
        else:
            sources = [path]
    attempts = [validate_attempt(source, expectations, attempt_number=index)
                for index, source in enumerate(sources, 1)]
    valid = [attempt for attempt in attempts if attempt.valid]
    reasons: list[str] = []
    instances = [_pick(attempt.identity, "instance_id", "container_session_id", "container_task_id", "restored_instance_id") for attempt in valid]
    if len(instances) != len(set(instances)):
        reasons.append("freshness requires distinct instance identities")
        seen: dict[str, AttemptResult] = {}
        for attempt, instance in zip(valid, instances):
            if instance in seen:
                attempt.valid = False
                attempt.reasons.append("freshness duplicate instance identity")
            else:
                seen[instance] = attempt
    keys = {_cohort_identity_key(attempt.identity) for attempt in valid}
    if len(keys) > 1:
        reasons.append("frozen identity changed across valid attempts")
        baseline = _cohort_identity_key(valid[0].identity) if valid else ()
        for attempt in valid:
            if _cohort_identity_key(attempt.identity) != baseline:
                attempt.valid = False
                attempt.reasons.append("freshness frozen identity changed")
    valid = [attempt for attempt in attempts if attempt.valid]
    invalid = [attempt for attempt in attempts if not attempt.valid]
    if len(valid) != 5:
        reasons.append(f"five-run cohort requires exactly 5 valid attempts, got {len(valid)}")
    stats: dict[str, Any] = {}
    if len(valid) == 5 and not reasons:
        stats["golden_stage_sum_ms"] = compute_stats([attempt.metrics["golden_stage_sum_ms"] for attempt in valid])
        for stage in PRIMARY_STAGE_ORDER:
            stats[stage] = compute_stats([attempt.stage_walls[stage].duration_ms for attempt in valid])
        stats[TEARDOWN_STAGE] = compute_stats([
            attempt.teardown_wall.duration_ms for attempt in valid
            if attempt.teardown_wall is not None
        ])
        metric_names = WHOLE_PATH_METRIC_NAMES
        for name in metric_names:
            values = [attempt.metrics.get(name) for attempt in valid]
            if all(value is not None for value in values):
                stats[name] = compute_stats([float(value) for value in values if value is not None])
    return CohortReport(attempts, valid, invalid, not reasons, reasons, stats)


five_run_cohort = build_five_run_cohort


def regenerate_report(sources: Iterable[Mapping[str, Any] | str | os.PathLike[str]],
                      expectations: GoldenExpectations | Mapping[str, Any] | None = None,
                      *, output_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    cohort = build_five_run_cohort(sources, expectations)
    report = cohort.to_dict()
    report["gantt"] = [render_golden_gantt(attempt) for attempt in cohort.valid_attempts]
    report["primary_function_tables"] = [
        {"attempt_number": attempt.attempt_number,
         "rows": primary_function_table(attempt),
         "text": render_primary_function_table(attempt)}
        for attempt in cohort.valid_attempts
    ]
    report["workflow_identity_matrices"] = [
        attempt.identity.get("workflow_identity_matrix", {})
        for attempt in cohort.attempts
    ]
    report["raw_artifact_refs"] = [ref for attempt in cohort.attempts for ref in attempt.raw_artifact_refs]
    report["raw_log_refs"] = [ref for attempt in cohort.attempts for ref in attempt.raw_log_refs]
    if output_path is not None:
        Path(output_path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


final_report = regenerate_report


def _comparison_input(value: Any) -> tuple[dict[str, Any], bool, int | None]:
    if isinstance(value, CohortReport):
        return value.stats, value.valid, len(value.valid_attempts)
    if isinstance(value, Mapping):
        stats = value.get("stats")
        if isinstance(stats, Mapping):
            valid = value.get("valid") is True
            count = value.get("valid_count")
            if count is None:
                counts: list[int] = []
                for item in stats.values():
                    if not isinstance(item, Mapping) or item.get("n") is None:
                        continue
                    try:
                        counts.append(int(item["n"]))
                    except (TypeError, ValueError):
                        continue
                count = min(counts) if counts else None
            try:
                count = int(count) if count is not None else None
            except (TypeError, ValueError):
                count = None
            return dict(stats), valid, count
    return {}, False, None


def _delta(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("n", "min", "max", "median", "mean", "p90", "stdev", "cv", "range"):
        left, right = candidate.get(key), baseline.get(key)
        result[key] = left - right if isinstance(left, (int, float)) and isinstance(right, (int, float)) else None
    return result


def _metric_comparison(name: str, baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    required = ("n", "median", "p90", "max", "cv", "range")
    missing = [key for key in required if candidate.get(key) is None or baseline.get(key) is None]
    if missing:
        return {"status": "UNVERIFIED", "reason": "missing statistic fields: " + ", ".join(missing),
                "baseline": dict(baseline), "candidate": dict(candidate), "delta": _delta(candidate, baseline)}
    try:
        baseline_n, candidate_n = int(baseline["n"]), int(candidate["n"])
    except (KeyError, TypeError, ValueError):
        return {"status": "UNVERIFIED", "reason": "invalid sample count",
                "baseline": dict(baseline), "candidate": dict(candidate), "delta": _delta(candidate, baseline)}
    if baseline_n < 2 or candidate_n < 2:
        return {"status": "UNVERIFIED", "reason": "one-run statistics cannot support a speed claim",
                "baseline": dict(baseline), "candidate": dict(candidate), "delta": _delta(candidate, baseline)}
    if baseline_n != candidate_n:
        return {"status": "UNVERIFIED", "reason": "baseline and candidate sample counts are incomparable",
                "baseline": dict(baseline), "candidate": dict(candidate), "delta": _delta(candidate, baseline)}

    base_median, cand_median = baseline["median"], candidate["median"]
    base_p90, cand_p90 = baseline["p90"], candidate["p90"]
    base_max, cand_max = baseline["max"], candidate["max"]
    base_cv, cand_cv = baseline["cv"], candidate["cv"]
    base_range, cand_range = baseline["range"], candidate["range"]
    is_sub10 = base_median < 10.0 and cand_median < 10.0
    is_restore_or_commit = name in {"actual_restore", "restore_ms", "golden_durable_commit"}
    if is_sub10:
        improved = cand_range < base_range
        not_worse = cand_range <= base_range
        rule = "both medians <10ms: compare absolute range"
    elif is_restore_or_commit:
        improved = cand_p90 < base_p90 and cand_max <= base_max
        not_worse = cand_p90 <= base_p90 and cand_max <= base_max
        rule = "long-tail stage: p90 must improve and max must not worsen"
    else:
        improved = (cand_median < base_median and cand_p90 <= base_p90
                    and cand_max <= base_max
                    and (base_cv is None or (cand_cv is not None and cand_cv <= base_cv)))
        not_worse = (cand_p90 <= base_p90 and cand_max <= base_max
                     and (base_cv is None or (cand_cv is not None and cand_cv <= base_cv)))
        rule = "median must improve; p90, max, and CV must not worsen"
    status = "IMPROVED" if improved else ("NOT_IMPROVED" if not_worse else "REGRESSION")
    deltas = _delta(candidate, baseline)
    return {
        "status": status, "rule": rule, "baseline": dict(baseline),
        "candidate": dict(candidate), "delta": deltas, "deltas": deltas,
        **{f"{key}_delta": value for key, value in deltas.items()},
    }


def compare_baseline_candidate(baseline: Any, candidate: Any) -> dict[str, Any]:
    """Compare two structurally valid cohorts without inventing thresholds.

    Structural validity is reported separately from the performance verdict.
    A missing proof, an invalid cohort, or a one-run/incomplete statistic can
    never become a positive performance claim.
    """
    baseline_stats, baseline_valid, baseline_count = _comparison_input(baseline)
    candidate_stats, candidate_valid, candidate_count = _comparison_input(candidate)
    structural = {
        "baseline_valid": baseline_valid, "candidate_valid": candidate_valid,
        "baseline_valid_count": baseline_count, "candidate_valid_count": candidate_count,
        "valid": baseline_valid and candidate_valid,
    }
    if not structural["valid"]:
        return {"verdict": "UNVERIFIED", "performance_verdict": "UNVERIFIED",
                "structural": structural, "structurally_valid": False,
                "performance": {"verdict": "UNVERIFIED", "metrics": {}}, "metrics": {},
                "reasons": ["baseline and candidate must both be structurally valid"]}
    names = sorted(set(baseline_stats) | set(candidate_stats))
    metrics: dict[str, Any] = {}
    reasons: list[str] = []
    for name in names:
        base = baseline_stats.get(name)
        cand = candidate_stats.get(name)
        if not isinstance(base, Mapping) or not isinstance(cand, Mapping):
            metrics[name] = {"status": "UNVERIFIED", "reason": "metric absent from baseline or candidate"}
        else:
            metrics[name] = _metric_comparison(name, base, cand)
        if metrics[name].get("status") == "UNVERIFIED":
            reasons.append(f"{name}: {metrics[name].get('reason', 'incomparable')}")
    if not metrics or reasons:
        verdict = "UNVERIFIED"
    elif any(item["status"] == "REGRESSION" for item in metrics.values()):
        verdict = "REGRESSION"
    elif all(item["status"] == "IMPROVED" for item in metrics.values()):
        verdict = "IMPROVED"
    else:
        verdict = "NOT_IMPROVED"
    return {"verdict": verdict, "performance_verdict": verdict,
            "structural": structural, "structurally_valid": True,
            "performance": {"verdict": verdict, "metrics": metrics},
            "metrics": metrics, "reasons": reasons,
            "rules": {"no_one_run_claims": True, "thresholds": "none"}}


compare_cohorts = compare_baseline_candidate
compare_golden_cohorts = compare_baseline_candidate
build_comparison_report = compare_baseline_candidate


@dataclass(frozen=True)
class SourceTreePreflight:
    ok: bool
    root: str
    changed_files: tuple[str, ...]
    tree_sha256: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(self.__dict__)


def source_tree_digest(root: str | os.PathLike[str]) -> str:
    """Hash every regular file below root (only .git metadata is excluded)."""
    root_path = Path(root).resolve()
    digest = hashlib.sha256()
    for path in sorted((p for p in root_path.rglob("*") if p.is_file() and ".git" not in p.parts), key=lambda p: str(p)):
        rel = path.relative_to(root_path).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(8, "big")); digest.update(rel)
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def preflight_source_tree(root: str | os.PathLike[str], *, expected_digest: str | None = None,
                          isolated_root: str | os.PathLike[str] | None = None) -> SourceTreePreflight:
    """Refuse arbitrary dirty source trees; never auto-allow changed files."""
    root_path = Path(isolated_root or root).resolve()
    if not root_path.is_dir():
        return SourceTreePreflight(False, str(root_path), (), "", "isolated source root missing")
    if isolated_root is not None and not expected_digest:
        return SourceTreePreflight(False, str(root_path), (), "", "isolated source digest required")
    changed: list[str] = []
    try:
        result = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=str(root_path),
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if result.returncode == 0:
            changed = [line[3:].strip() for line in result.stdout.splitlines() if len(line) >= 3 and line[:2] != "!!"]
        elif not isolated_root:
            return SourceTreePreflight(False, str(root_path), (), "", "git status unavailable")
    except (OSError, subprocess.SubprocessError) as exc:
        if not isolated_root:
            return SourceTreePreflight(False, str(root_path), (), "", f"git status unavailable: {exc}")
    digest = source_tree_digest(root_path)
    if expected_digest and digest != expected_digest:
        return SourceTreePreflight(False, str(root_path), tuple(changed), digest, "immutable source digest mismatch")
    if changed:
        return SourceTreePreflight(False, str(root_path), tuple(changed), digest,
                                   "source tree has changed files; isolated immutable input required")
    return SourceTreePreflight(True, str(root_path), (), digest, "ok")


def run_structural(artifact: Mapping[str, Any] | str | os.PathLike[str],
                   expectations: GoldenExpectations | Mapping[str, Any] | None = None,
                   *, source_root: str | os.PathLike[str] | None = None,
                   isolated_root: str | os.PathLike[str] | None = None,
                   expected_digest: str | None = None,
                   expected_source_digest: str | None = None) -> dict[str, Any]:
    if source_root is not None or isolated_root is not None:
        root = source_root if source_root is not None else isolated_root
        assert root is not None
        preflight = preflight_source_tree(root, isolated_root=isolated_root,
                                          expected_digest=expected_digest or expected_source_digest)
        if not preflight.ok:
            return {"schema": SCHEMA_VERSION, "valid": False, "reasons": ["source preflight refused: " + preflight.reason],
                    "source_preflight": preflight.to_dict()}
    return validate_attempt(artifact, expectations).to_dict()


structural_run = run_structural


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Golden observability report harness")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("structural-run", "five-run", "final-report"):
        command = sub.add_parser(name)
        command.add_argument("artifacts", nargs="+", type=Path)
        command.add_argument("--expected", type=Path)
        command.add_argument("--output", type=Path)
        if name == "structural-run":
            command.add_argument("--source-root", type=Path)
            command.add_argument("--isolated-root", type=Path)
            command.add_argument("--expected-source-digest")
    args = parser.parse_args(argv)
    expected = json.loads(args.expected.read_text(encoding="utf-8")) if args.expected else None
    if args.command == "structural-run":
        report: Any = run_structural(args.artifacts[0], expected,
                                     source_root=args.source_root,
                                     isolated_root=args.isolated_root,
                                     expected_digest=args.expected_source_digest)
    else:
        report = regenerate_report(args.artifacts, expected)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if report.get("valid") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
