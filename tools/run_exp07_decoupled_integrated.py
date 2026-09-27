#!/usr/bin/env python
"""Build and resume the local Phase-3 decoupled Golden campaign.

This module is deliberately a manifest runner, not a Modal runner.  It only
creates local JSON and prints the public control-plane commands which an
operator may execute later.  Artifact ingestion always takes an explicit path;
there is no directory scan or "newest artifact" selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


APP = "exp-golden-p1-decoupled"
PROFILE = "golden_p1"
PROFILE_PREFIX = "golden_p1_direct_exp07"
CONTRACT_CLASS = "ModalRuntimeEntrypointV2"
CONTRACT_METHOD = "run_golden_serial_stream"
TRANSPORT = "decoupled"
SOURCE_QD = 8
SOURCE_CAPACITY = 8
CPU_ALLOCATION = 4
MEMORY_MB = 8192
SOURCE_BLOCKS_MIB = (256, 64)
H2D_COPY_EXTENTS_MIB = (128, 256)
H2D_INFLIGHT_DEPTHS = (1, 2)
OBSERVATIONS_PER_CELL = 10
MODELS = ("clip", "unet")
CELL_COUNT = 8
REQUEST_COUNT = CELL_COUNT * OBSERVATIONS_PER_CELL
MODEL_OBSERVATIONS_PER_REQUEST = len(MODELS)
OBSERVATION_COUNT = REQUEST_COUNT * MODEL_OBSERVATIONS_PER_REQUEST
SCHEMA_VERSION = 1

POST_DIAGNOSTIC_BLOCKS_MIB = (32, 256)
POST_DIAGNOSTIC_QDS = (2, 4, 8)

_TERMINAL_STATUSES = {"ELIGIBLE", "INVALID", "FAILED"}
_PROOF_NO_VALUES = {"NO", "PROOF_NO", "PROOF-NO", "NOT_PROVEN", "UNPROVEN"}
_PROVEN_VALUES = {"PROVEN", "YES", "PASS", "TRUE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bytes(mib: int) -> int:
    return mib * 1024 * 1024


def cell_id(source_block_mib: int, h2d_copy_mib: int, h2d_depth: int) -> str:
    return f"source_b{source_block_mib}_h2d{h2d_copy_mib}_depth{h2d_depth}"


def cell_profile_name(source_block_mib: int, h2d_copy_mib: int, h2d_depth: int) -> str:
    """Return the accepted, deterministic Golden profile for one cell."""
    return f"{PROFILE_PREFIX}_b{source_block_mib}_h2d{h2d_copy_mib}_d{h2d_depth}"


def deploy_baked_environment(config: Mapping[str, Any]) -> dict[str, str]:
    """Return the exact deploy-baked environment recorded for a cell."""
    return {
        "COMFYMODAL_GOLDEN_QD_TRANSPORT": TRANSPORT,
        "COMFYMODAL_GOLDEN_SOURCE_QD": str(SOURCE_QD),
        "COMFYMODAL_GOLDEN_SOURCE_BLOCK_BYTES": str(config["source_block_bytes"]),
        "COMFYMODAL_GOLDEN_H2D_COPY_BYTES": str(config["h2d_copy_bytes"]),
        "COMFYMODAL_GOLDEN_H2D_INFLIGHT_DEPTH": str(config["h2d_inflight_depth"]),
        "COMFYMODAL_GOLDEN_SOURCE_CAPACITY": str(SOURCE_CAPACITY),
    }


def experiment_cells() -> list[dict[str, Any]]:
    """Return the eight fixed cells in deterministic manifest order."""
    cells: list[dict[str, Any]] = []
    index = 0
    for source_block in SOURCE_BLOCKS_MIB:
        for copy_extent in H2D_COPY_EXTENTS_MIB:
            for depth in H2D_INFLIGHT_DEPTHS:
                index += 1
                config = {
                    "source_block_mib": source_block,
                    "source_block_bytes": _bytes(source_block),
                    "source_qd": SOURCE_QD,
                    "source_capacity": SOURCE_CAPACITY,
                    "h2d_copy_mib": copy_extent,
                    "h2d_copy_bytes": _bytes(copy_extent),
                    "h2d_inflight_depth": depth,
                }
                cid = cell_id(source_block, copy_extent, depth)
                profile = cell_profile_name(source_block, copy_extent, depth)
                cells.append(
                    {
                        "cell_index": index,
                        "cell_id": cid,
                        "models": list(MODELS),
                        "configuration": config,
                        "deployment_manifest": {
                            "app": APP,
                            "profile": profile,
                            "cell_id": cid,
                            "class": CONTRACT_CLASS,
                            "method": CONTRACT_METHOD,
                            "resources": {
                                "cpu": CPU_ALLOCATION,
                                "memory_mb": MEMORY_MB,
                            },
                            "deploy_baked_environment": deploy_baked_environment(config),
                            "profile_strategy": "deterministic_derived_profile_per_cell",
                        },
                        "deployment_identity": {
                            "expected": expected_identity(config),
                            "actual": None,
                        },
                    }
                )
    return cells


def expected_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return identity/config fields that may not be mixed across cells."""
    profile = cell_profile_name(
        int(config["source_block_mib"]),
        int(config["h2d_copy_mib"]),
        int(config["h2d_inflight_depth"]),
    )
    return {
        "app": APP,
        "profile": profile,
        "class": CONTRACT_CLASS,
        "method": CONTRACT_METHOD,
        "transport": TRANSPORT,
        "source_block_mib": int(config["source_block_mib"]),
        "source_qd": int(config["source_qd"]),
        "source_capacity": int(config["source_capacity"]),
        "h2d_copy_mib": int(config["h2d_copy_mib"]),
        "h2d_inflight_depth": int(config["h2d_inflight_depth"]),
    }


def campaign_schedule(
    start_round: int = 1,
    rounds: int = OBSERVATIONS_PER_CELL,
    cells: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Create a round-major schedule, interleaving every cell each round."""
    if start_round < 1 or rounds < 1:
        raise ValueError("start_round and rounds must be positive")
    source = [dict(item) for item in (cells if cells is not None else experiment_cells())]
    if len(source) != CELL_COUNT:
        raise ValueError(f"expected {CELL_COUNT} cells, got {len(source)}")
    schedule: list[dict[str, Any]] = []
    order = 0
    for round_number in range(start_round, start_round + rounds):
        for cell in source:
            order += 1
            schedule.append(
                {
                    "manifest_index": order,
                    "request_id": f"exp07-r{round_number:02d}-c{int(cell['cell_index']):02d}",
                    "round": round_number,
                    "cell_index": cell["cell_index"],
                    "cell_id": cell["cell_id"],
                    "models": list(MODELS),
                    "configuration": dict(cell["configuration"]),
                    "deployment_identity_expected": dict(cell["deployment_identity"]["expected"]),
                    "invocation_command": (
                        f"python tools/v2ctl.py --profile "
                        f"{cell['deployment_manifest']['profile']} golden run --app {APP}"
                    ),
                    "status": "PENDING",
                    "attempts": [],
                }
            )
    return schedule


def expected_accounting(rounds: int = OBSERVATIONS_PER_CELL) -> dict[str, int]:
    if rounds < 1:
        raise ValueError("rounds must be positive")
    requests = CELL_COUNT * rounds
    return {
        "cell_count": CELL_COUNT,
        "observations_per_cell": rounds,
        "request_count": requests,
        "model_observations_per_request": MODEL_OBSERVATIONS_PER_REQUEST,
        "observation_count": requests * MODEL_OBSERVATIONS_PER_REQUEST,
    }


def post_decoupling_diagnostic_plan(
    *,
    h2d_copy_extents_mib: Sequence[int] | None = None,
    h2d_inflight_depths: Sequence[int] | None = None,
    observations_per_cell: int | None = None,
) -> dict[str, Any]:
    """Describe OLD-vs-NEW diagnostics without silently making them runnable.

    Steering did not specify H2D geometry or sample count for this later
    diagnostic.  Supplying all three parameters makes the arithmetic explicit;
    the default plan remains a fail-closed TODO and is never scheduled.
    """
    cells = [
        {"role": role, "source_block_mib": block, "source_qd": qd}
        for block in POST_DIAGNOSTIC_BLOCKS_MIB
        for qd in POST_DIAGNOSTIC_QDS
        for role in MODELS
    ]
    geometry_supplied = h2d_copy_extents_mib is not None and h2d_inflight_depths is not None
    count_supplied = observations_per_cell is not None
    if geometry_supplied and count_supplied:
        extents = [int(value) for value in h2d_copy_extents_mib or ()]
        depths = [int(value) for value in h2d_inflight_depths or ()]
        if not extents or not depths or observations_per_cell < 1:
            raise ValueError("diagnostic H2D geometry and observations must be non-empty/positive")
        request_count = len(cells) * len(extents) * len(depths) * observations_per_cell
        return {
            "status": "CONFIGURED_NOT_EXECUTED",
            "cells": cells,
            "required_h2d_geometry": {
                "copy_extents_mib": extents,
                "inflight_depths": depths,
            },
            "observations_per_cell": observations_per_cell,
            "request_count": request_count,
            "observation_count": request_count * MODEL_OBSERVATIONS_PER_REQUEST,
        }
    return {
        "status": "TODO_FAIL_CLOSED",
        "cells": cells,
        "required_h2d_geometry": {
            "copy_extents_mib": None,
            "inflight_depths": None,
        },
        "observations_per_cell": None,
        "request_count": None,
        "observation_count": None,
        "todo": "Specify H2D copy extents, H2D inflight depths, and observations_per_cell before executing OLD-vs-NEW diagnostics.",
    }


def public_commands(profile: str, app: str = APP) -> list[str]:
    """Commands the parent may execute later, in the required control-plane."""
    prefix = "python tools/v2ctl.py"
    return [
        f"{prefix} --profile {profile} golden status --app {app}",
        f"{prefix} --profile {profile} golden doctor --app {app}",
        f"{prefix} --profile {profile} golden deploy --app {app}",
        f"{prefix} --profile {profile} --app {app} source-probe",
        f"{prefix} --profile {profile} golden run --app {app}",
    ]


def new_manifest(rounds: int = OBSERVATIONS_PER_CELL) -> dict[str, Any]:
    """Build an unexecuted local plan; no profile or remote state is changed."""
    cells = experiment_cells()
    commands_by_cell = {
        cell["cell_id"]: public_commands(cell["deployment_manifest"]["profile"])
        for cell in cells
    }
    profile_names = [cell["deployment_manifest"]["profile"] for cell in cells]
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": "exp07_decoupled_integrated",
        "phase": "phase_3_decoupled_integrated",
        "execution_policy": {
            "local_only": True,
            "subprocesses_launched": False,
            "modal_api_called": False,
            "serial": True,
            "artifact_selection": "explicit_path_only",
            "deploy_baked_dimensions_per_cell": True,
            "homogeneous_cohort_scope": "one_cell_identity_only",
            "profile_strategy": "deterministic_derived_profile_per_cell",
            "subprocess_policy": "none_by_default",
            "public_run_requests_per_invocation": 1,
            "schedule_order": "round_major_interleaved",
        },
        "contract": {
            "app": APP,
            "baseline_profile": PROFILE,
            "accepted_profile_prefix": "golden_p1_direct",
            "class": CONTRACT_CLASS,
            "method": CONTRACT_METHOD,
            "transport": TRANSPORT,
        },
        "profile_strategy": {
            "kind": "deterministic_derived_profile_per_cell",
            "baseline_profile": PROFILE,
            "profile_names": profile_names,
            "accepted_public_profile_rule": "golden_p1 or names beginning golden_p1_direct",
            "baseline_preserved": True,
            "restoration_required": True,
            "restoration_requirement": (
                "After Phase 3, restore operator/default profile selection to golden_p1; "
                "never mutate or delete golden_p1.toml."
            ),
        },
        "shared_source_configurations": [
            {
                "phase_2_rank": rank,
                "phase_2_rank_label": "winner" if rank == 1 else "runner_up",
                "source_block_mib": block,
                "source_qd": SOURCE_QD,
                "applies_to": list(MODELS),
            }
            for rank, block in enumerate(SOURCE_BLOCKS_MIB, start=1)
        ],
        "source_capacity": SOURCE_CAPACITY,
        "source_queue_contract": {
            "source_qd": SOURCE_QD,
            "source_capacity": SOURCE_CAPACITY,
            "independent": True,
        },
        "cpu_allocation_configured": CPU_ALLOCATION,
        "h2d_copy_extents_mib": list(H2D_COPY_EXTENTS_MIB),
        "h2d_inflight_depths": list(H2D_INFLIGHT_DEPTHS),
        "models_per_request": list(MODELS),
        "resources": {"cpu": CPU_ALLOCATION, "memory_mb": MEMORY_MB},
        "accounting": expected_accounting(rounds),
        "cells": cells,
        "schedule": campaign_schedule(rounds=rounds, cells=cells),
        # Keep the historical flat command list for simple consumers while
        # retaining the cell/profile association for the Phase-3 operator.
        "public_commands_for_parent": [
            command for commands in commands_by_cell.values() for command in commands
        ],
        "public_commands_by_cell": commands_by_cell,
        "post_decoupling_old_vs_new_diagnostics": post_decoupling_diagnostic_plan(),
    }


def build_plan(rounds: int = OBSERVATIONS_PER_CELL) -> dict[str, Any]:
    """Alias kept as the obvious API for callers that only need a plan."""
    return new_manifest(rounds)


def _cell_by_id(manifest: Mapping[str, Any], value: str) -> dict[str, Any]:
    for cell in manifest.get("cells", []):
        if cell.get("cell_id") == value:
            return cell
    raise KeyError(f"unknown cell: {value}")


def bind_cell_identity(
    manifest: dict[str, Any], cell: str, deployment_identity: Mapping[str, Any]
) -> None:
    """Bind one cell to one observed deployment/source identity.

    A later identity may be recorded for another cell, but a cell cannot be
    silently rebound.  This is the guard against mixing deploy-baked geometry
    under one homogeneous cohort.
    """
    target = _cell_by_id(manifest, cell)
    expected = target["deployment_identity"]["expected"]
    for key, value in expected.items():
        if deployment_identity.get(key) != value:
            raise ValueError(f"deployment identity mismatch for {cell}: {key}")
    actual = target["deployment_identity"].get("actual")
    incoming = dict(deployment_identity)
    if actual is not None and actual != incoming:
        raise ValueError(f"deployment identity already bound for {cell}")
    target["deployment_identity"]["actual"] = incoming


def _identity(data: Mapping[str, Any]) -> dict[str, Any]:
    value = data.get("identity")
    result = dict(value) if isinstance(value, Mapping) else {}
    target = data.get("target")
    if isinstance(target, Mapping):
        for key in ("app", "profile", "class", "method"):
            if key in target and key not in result:
                result[key] = target[key]
    for key in ("app", "profile", "class", "method", "transport", "deployment_id", "source_identity"):
        if key in data and key not in result:
            result[key] = data[key]
    if "deployment_id" not in result:
        for key in ("deployment_fingerprint", "deploy_fingerprint", "deployment_combined_hash"):
            if data.get(key) is not None:
                result["deployment_id"] = data[key]
                break
    return result


def _config(data: Mapping[str, Any]) -> dict[str, Any]:
    value = data.get("configuration") or data.get("config")
    result = dict(value) if isinstance(value, Mapping) else {}
    for key in (
        "source_block_mib",
        "source_qd",
        "source_capacity",
        "h2d_copy_mib",
        "h2d_inflight_depth",
    ):
        if key in data and key not in result:
            result[key] = data[key]
    byte_aliases = {
        "source_block_mib": "configured_source_block_bytes",
        "h2d_copy_mib": "configured_h2d_copy_bytes",
    }
    for mib_key, byte_key in byte_aliases.items():
        if mib_key not in result and isinstance(data.get(byte_key), int):
            value = data[byte_key]
            if value % (1024 * 1024) == 0:
                result[mib_key] = value // (1024 * 1024)
    aliases = {
        "source_qd": "configured_source_qd",
        "source_capacity": "configured_source_capacity",
        "h2d_inflight_depth": "configured_h2d_inflight_depth",
    }
    for target, source in aliases.items():
        if target not in result and source in data:
            result[target] = data[source]
    return result


def _proof_classification(data: Mapping[str, Any]) -> str:
    value: Any = data.get("e27_proof_classification")
    if value is None:
        value = data.get("E27_proof_classification")
    if value is None:
        value = data.get("E27_SOURCE_MECHANISM_PROVEN")
    if value is None and isinstance(data.get("e27"), Mapping):
        value = data["e27"].get("proof_classification")
    if value is None and isinstance(data.get("e27_source_mechanism_evaluation"), Mapping):
        proven = data["e27_source_mechanism_evaluation"].get("proven")
        if proven is True:
            value = "PROVEN"
        elif proven is False:
            value = "PROOF_NO"
    normalized = str(value or "UNKNOWN").strip().upper().replace(" ", "_")
    if normalized in _PROOF_NO_VALUES:
        return "PROOF_NO"
    if normalized in _PROVEN_VALUES:
        return "PROVEN"
    return "UNKNOWN"


def _physical_reads(data: Mapping[str, Any]) -> tuple[list[dict[str, int]], list[str]]:
    raw = data.get("physical_reads")
    if raw is None:
        raw = data.get("physical_syscall_telemetry")
    if raw is None and isinstance(data.get("actual_source"), Mapping):
        source = data["actual_source"]
        raw = source.get("physical_reads") or source.get("physical_syscall_telemetry") or source.get("events")
    failures: list[str] = []
    events: list[dict[str, int]] = []
    if not isinstance(raw, list) or not raw:
        return [], ["physical_read_bytes_missing"]
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            failures.append(f"physical_read_{index}_not_object")
            continue
        requested = item.get("requested_bytes")
        returned = item.get("returned_bytes")
        if not isinstance(requested, int) or not isinstance(returned, int):
            failures.append(f"physical_read_{index}_not_exact_integers")
            continue
        if requested < 0 or returned < 0 or returned > requested:
            failures.append(f"physical_read_{index}_out_of_range")
            continue
        events.append({"requested_bytes": requested, "returned_bytes": returned})
    return events, failures


def classify_artifact(
    artifact: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify one explicit artifact, failing closed on missing evidence."""
    failures: list[str] = []
    identity = _identity(artifact)
    configuration = _config(artifact)
    for key in ("app", "profile", "class", "method", "transport"):
        if identity.get(key) != expected.get(key):
            failures.append(f"identity_{key}_mismatch")
    for key in (
        "source_block_mib",
        "source_qd",
        "source_capacity",
        "h2d_copy_mib",
        "h2d_inflight_depth",
    ):
        if configuration.get(key) != expected.get(key):
            failures.append(f"configuration_{key}_mismatch")

    status = str(artifact.get("status", "")).upper()
    if status in {"FAILED", "ERROR", "DNF", "PLATFORM_FAILURE"}:
        return {
            "status": "FAILED",
            "result_classification": "FAILED",
            "mechanism_proven": False,
            "e27_proof_classification": _proof_classification(artifact),
            "reasons": ["artifact_status_failed"],
        }

    if identity.get("deployment_id") is None:
        failures.append("identity_deployment_id_missing")
    if identity.get("source_identity") is None:
        failures.append("identity_source_identity_missing")

    timeline = artifact.get("source_qd_timeline")
    if timeline is None:
        timeline = artifact.get("achieved_source_qd_timeline")
    if timeline is None and isinstance(artifact.get("actual_source"), Mapping):
        source = artifact["actual_source"]
        timeline = source.get("source_qd_timeline") or source.get("achieved_source_qd_timeline")
    if not isinstance(timeline, list) or not timeline:
        failures.append("source_qd_timeline_missing")
    else:
        normalized_timeline: list[dict[str, Any]] = []
        for index, item in enumerate(timeline):
            if not isinstance(item, Mapping):
                failures.append(f"source_qd_timeline_{index}_not_object")
                continue
            configured = item.get("configured_qd", item.get("configured"))
            achieved = item.get("achieved_qd", item.get("achieved"))
            # Runtime transport reports transitions as {depth, timestamp_ns}.
            # The configured value is supplied by the cell in that form.
            if achieved is None:
                achieved = item.get("depth")
            if configured is None:
                configured = expected.get("source_qd")
            if configured != expected.get("source_qd"):
                failures.append(f"source_qd_timeline_{index}_configured_mismatch")
            if not isinstance(achieved, int) or achieved < 0:
                failures.append(f"source_qd_timeline_{index}_achieved_missing")
            row = dict(item)
            row["configured_qd"] = configured
            row["achieved_qd"] = achieved
            normalized_timeline.append(row)
        timeline = normalized_timeline

    achieved_depth = artifact.get("achieved_h2d_depth")
    if achieved_depth is None:
        achieved_depth = artifact.get("achieved_h2d_inflight_depth_max")
    if not isinstance(achieved_depth, int) or achieved_depth < 0:
        failures.append("achieved_h2d_depth_missing")
    wait_dimensions = artifact.get("wait_dimensions")
    if wait_dimensions is None:
        wait_dimensions = {
            key: artifact[key]
            for key in (
                "source_capacity_wait_ms",
                "ready_queue_wait_ms",
                "h2d_capacity_wait_ms",
                "cuda_readiness_wait_ms",
            )
            if key in artifact
        }
    if not isinstance(wait_dimensions, Mapping) or not wait_dimensions:
        failures.append("wait_dimensions_missing")
    cpu_allocation = artifact.get("cpu_allocation")
    if cpu_allocation is None and isinstance(artifact.get("resources"), Mapping):
        cpu_allocation = artifact["resources"].get("cpu")
    if cpu_allocation is None:
        failures.append("cpu_allocation_missing")
    reads, read_failures = _physical_reads(artifact)
    failures.extend(read_failures)
    proof = _proof_classification(artifact)
    if proof == "PROOF_NO":
        # Preserve this artifact, but it can never satisfy this mechanism gate.
        return {
            "status": "INVALID",
            "result_classification": "PROOF_NO",
            "mechanism_proven": False,
            "e27_proof_classification": proof,
            "identity": identity,
            "configuration": configuration,
            "source_qd_timeline": timeline,
            "achieved_h2d_depth": achieved_depth,
            "wait_dimensions": dict(wait_dimensions) if isinstance(wait_dimensions, Mapping) else None,
            "cpu_allocation": cpu_allocation,
            "physical_read_bytes": {
                "events": reads,
                "requested_total": sum(item["requested_bytes"] for item in reads),
                "returned_total": sum(item["returned_bytes"] for item in reads),
            },
            "reasons": failures + ["e27_proof_no_not_mechanism_proven"],
        }
    if proof != "PROVEN":
        failures.append("e27_proof_classification_unknown")
    if failures:
        return {
            "status": "INVALID",
            "result_classification": "INVALID",
            "mechanism_proven": False,
            "e27_proof_classification": proof,
            "identity": identity,
            "configuration": configuration,
            "source_qd_timeline": timeline,
            "achieved_h2d_depth": achieved_depth,
            "wait_dimensions": dict(wait_dimensions) if isinstance(wait_dimensions, Mapping) else None,
            "cpu_allocation": cpu_allocation,
            "physical_read_bytes": {
                "events": reads,
                "requested_total": sum(item["requested_bytes"] for item in reads),
                "returned_total": sum(item["returned_bytes"] for item in reads),
            },
            "reasons": failures,
        }
    return {
        "status": "ELIGIBLE",
        "result_classification": "ELIGIBLE",
        "mechanism_proven": True,
        "e27_proof_classification": proof,
        "identity": identity,
        "configuration": configuration,
        "source_qd_timeline": timeline,
        "achieved_h2d_depth": achieved_depth,
        "wait_dimensions": dict(wait_dimensions) if isinstance(wait_dimensions, Mapping) else {},
        "cpu_allocation": cpu_allocation,
        "physical_read_bytes": {
            "events": reads,
            "requested_total": sum(item["requested_bytes"] for item in reads),
            "returned_total": sum(item["returned_bytes"] for item in reads),
        },
        "slow_valid": bool(artifact.get("slow_valid", False)),
        "reasons": [],
    }


def record_artifact(manifest: dict[str, Any], request_id: str, artifact_path: Path) -> dict[str, Any]:
    """Record the artifact at exactly ``artifact_path`` and return its summary."""
    artifact_path = Path(artifact_path)
    request = next((item for item in manifest["schedule"] if item["request_id"] == request_id), None)
    if request is None:
        raise KeyError(f"unknown request: {request_id}")
    if request["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"request already terminal: {request_id}")
    if request["status"] == "PENDING":
        pending = next_pending_request(manifest)
        if pending is not None and pending["request_id"] != request_id:
            raise ValueError("requests must be recorded in manifest order")
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("artifact must be a JSON object")
    cell = _cell_by_id(manifest, request["cell_id"])
    expected = cell["deployment_identity"]["expected"]
    summary = classify_artifact(data, expected)
    if data.get("request_id") not in (None, request_id):
        summary["status"] = "INVALID"
        summary["result_classification"] = "INVALID"
        summary["mechanism_proven"] = False
        summary.setdefault("reasons", []).append("request_id_mismatch")
    identity = _identity(data)
    configuration = _config(data)
    bound_identity = {**identity, **configuration}
    if (
        data.get("request_id") in (None, request_id)
        and identity
        and all(bound_identity.get(key) == expected.get(key) for key in expected)
    ):
        bind_cell_identity(manifest, request["cell_id"], bound_identity)
    attempt = {
        "request_id": request_id,
        "artifact_path": str(artifact_path),
        "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        "recorded_at": _now(),
        "observation_count": MODEL_OBSERVATIONS_PER_REQUEST,
        "classification": summary,
    }
    request["attempts"].append(attempt)
    request["status"] = summary["status"]
    request["artifact_path"] = str(artifact_path)
    return summary


def start_request(manifest: dict[str, Any], request_id: str) -> dict[str, Any]:
    """Reserve the next serial request without launching anything."""
    request = next((item for item in manifest["schedule"] if item["request_id"] == request_id), None)
    if request is None:
        raise KeyError(f"unknown request: {request_id}")
    if request.get("status") != "PENDING":
        raise ValueError(f"request is not pending: {request_id}")
    if any(item.get("status") == "RUNNING" for item in manifest["schedule"]):
        raise RuntimeError("a serial request is already running")
    pending = next_pending_request(manifest)
    if pending is not None and pending["request_id"] != request_id:
        raise ValueError("requests must be started in manifest order")
    request["status"] = "RUNNING"
    return dict(request)


def resume_manifest(manifest: dict[str, Any]) -> int:
    """Close interrupted requests while retaining their attempt records."""
    changed = 0
    for request in manifest.get("schedule", []):
        if request.get("status") != "RUNNING":
            continue
        request["status"] = "FAILED"
        request.setdefault("attempts", []).append(
            {
                "request_id": request["request_id"],
                "recorded_at": _now(),
                "observation_count": 0,
                "classification": {
                    "status": "FAILED",
                    "result_classification": "INTERRUPTED",
                    "mechanism_proven": False,
                    "e27_proof_classification": "UNKNOWN",
                    "reasons": ["interrupted_before_artifact"],
                },
            }
        )
        changed += 1
    return changed


def next_pending_request(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    for request in manifest.get("schedule", []):
        if request.get("status") == "PENDING":
            return dict(request)
    return None


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    plan = sub.add_parser("plan", help="print or write a local manifest")
    plan.add_argument("--rounds", type=int, default=OBSERVATIONS_PER_CELL)
    plan.add_argument("--output", type=Path)
    status = sub.add_parser("status", help="show status for an explicit manifest")
    status.add_argument("manifest", type=Path)
    record = sub.add_parser("record", help="record one explicit artifact path")
    record.add_argument("manifest", type=Path)
    record.add_argument("request_id")
    record.add_argument("artifact", type=Path)
    resume = sub.add_parser("resume", help="close interrupted records in an explicit manifest")
    resume.add_argument("manifest", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = args.command or "plan"
    if command == "plan":
        document = new_manifest(args.rounds if hasattr(args, "rounds") else OBSERVATIONS_PER_CELL)
        if getattr(args, "output", None):
            _atomic_write(args.output, document)
        else:
            print(json.dumps(document, indent=2, sort_keys=True))
        return 0
    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("manifest must be a JSON object")
    if command == "status":
        counts: dict[str, int] = {}
        for item in document.get("schedule", []):
            counts[item.get("status", "UNKNOWN")] = counts.get(item.get("status", "UNKNOWN"), 0) + 1
        print(json.dumps({"accounting": document.get("accounting"), "statuses": counts}, sort_keys=True))
        return 0
    if command == "record":
        summary = record_artifact(document, args.request_id, args.artifact)
        _atomic_write(args.manifest, document)
        print(json.dumps(summary, sort_keys=True))
        return 0
    if command == "resume":
        changed = resume_manifest(document)
        _atomic_write(args.manifest, document)
        print(json.dumps({"interrupted_closed": changed}, sort_keys=True))
        return 0
    raise ValueError(f"unknown command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
