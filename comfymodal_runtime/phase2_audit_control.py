"""Bounded Phase-2 source/H2D audit control plane.

The default entry point only builds a deterministic plan.  It never imports
Modal, discovers a newest artifact, or changes any existing Phase-2 evidence.
The remote endpoint lives in :mod:`phase2_audit_modal` and is intentionally a
separate experimental app.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import stat
import struct
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, cast

try:
    from .preplanned_extent_transport import (
        ExtentTransportError,
        PreplannedExtentTransport,
        plan_preplanned_extents,
    )
except ImportError:  # direct ``python comfymodal_runtime/phase2_audit_control.py``
    _ROOT = Path(__file__).resolve().parents[1]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from comfymodal_runtime.preplanned_extent_transport import (
        ExtentTransportError,
        PreplannedExtentTransport,
        plan_preplanned_extents,
    )

PHASE = "phase_2"
PHASE_3_STATUS = "stopped"
CONTROL_APP_NAME = "comfy-modal-phase2-audit-control"
CONTROL_PROFILE = "phase2-source-h2d-control"
MODELS_VOLUME_NAME = "comfyui-models"
MODELS_MOUNT = "/root/models"
GPU = "rtx-pro-6000"
CPU = 4
MEMORY_MB = 8192
ROLES = ("clip", "unet")
QD_VALUES = (2, 8)
BLOCK_MIB = 256
SOURCE_ONLY_MATRIX_QD_VALUES = (1, 2, 4, 8)
SOURCE_ONLY_MATRIX_BLOCK_MIB = (32, 64, 128, 256)
SOURCE_CAPACITY = 8
REPETITIONS = 3
# Model-sized source reads need a bounded deadline materially larger than the
# transport's general-purpose one-second cleanup default.  This remains a
# finite cooperative join/cleanup bound, rather than an unbounded join.
CONTROL_OPERATION_TIMEOUT_SECONDS = 300.0
SOURCE_ONLY_ARM = "source_only_same_path"
INTEGRATED_ARM = "decoupled_integrated_control"
ARMS = (SOURCE_ONLY_ARM, INTEGRATED_ARM)
MODEL_NAMES = {
    "clip": "qwen_3_4b.safetensors",
    "unet": "z_image_turbo_bf16.safetensors",
}

_CONTROL_TRANSPORT_PATCH_LOCK = threading.RLock()
STAGING_BUFFER_ALLOCATION_IDENTITY = "one_contiguous_pinned_cpu_uint8_arena"


@dataclass(frozen=True)
class AuditGeometry:
    role: str
    qd: int
    block_mib: int = BLOCK_MIB

    @property
    def block_bytes(self) -> int:
        return self.block_mib * 1024 * 1024

    @property
    def geometry_id(self) -> str:
        return f"{self.role}_b{self.block_mib}_qd{self.qd}"


def control_identity() -> dict[str, Any]:
    """Return the immutable identity shared by every planned request."""
    return {
        "app": CONTROL_APP_NAME,
        "profile": CONTROL_PROFILE,
        "phase": PHASE,
        "phase_3_status": PHASE_3_STATUS,
        "gpu": GPU,
        "cpu": CPU,
        "memory_mb": MEMORY_MB,
        "models_volume": MODELS_VOLUME_NAME,
        "models_mount": MODELS_MOUNT,
        "models_mount_read_only": True,
        "model_path_resolution": "fixed_read_only_models_mount",
        "source_worker_path": "PreplannedExtentTransport",
        "source_block_bytes": BLOCK_MIB * 1024 * 1024,
        "source_capacity": SOURCE_CAPACITY,
        "configured_source_capacity": SOURCE_CAPACITY,
        "source_capacity_semantics": "buffering_work_capacity_only",
        "resources": {"gpu": GPU, "cpu": CPU, "memory_mb": MEMORY_MB},
        "producer_implementation": "preplanned_extent_source_worker",
        "control_operation_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
        "transport_cleanup_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
        "timing_boundary": "SOURCE_WALL=source worker path entry to all source workers joined",
    }


def audit_geometries() -> tuple[AuditGeometry, ...]:
    return tuple(
        AuditGeometry(role, qd)
        for role in ROLES
        for qd in QD_VALUES
    )


def source_only_matrix_geometries() -> tuple[AuditGeometry, ...]:
    """Return the corrected source-only matrix in deterministic cell order."""
    return tuple(
        AuditGeometry(role, qd, block_mib)
        for role in ROLES
        for block_mib in SOURCE_ONLY_MATRIX_BLOCK_MIB
        for qd in SOURCE_ONLY_MATRIX_QD_VALUES
    )


def build_schedule(
    *,
    repetitions: int = REPETITIONS,
    geometries: Iterable[AuditGeometry] | None = None,
) -> list[dict[str, Any]]:
    """Build the fixed serial, geometry-local arm-interleaved schedule."""
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be positive")
    selected = tuple(geometries or audit_geometries())
    schedule: list[dict[str, Any]] = []
    index = 0
    for geometry in selected:
        if geometry.block_mib != BLOCK_MIB or geometry.qd not in QD_VALUES or geometry.role not in ROLES:
            raise ValueError("schedule geometry is outside the Phase-2 control matrix")
        for repetition in range(1, repetitions + 1):
            for arm in ARMS:
                index += 1
                schedule.append({
                    "request_index": index,
                    "geometry_id": geometry.geometry_id,
                    "role": geometry.role,
                    "model_name": MODEL_NAMES[geometry.role],
                    "qd": geometry.qd,
                    "source_qd": geometry.qd,
                    "source_capacity": SOURCE_CAPACITY,
                    "block_mib": geometry.block_mib,
                    "block_bytes": geometry.block_bytes,
                    "source_block_bytes": geometry.block_bytes,
                    "h2d_copy_bytes": geometry.block_bytes,
                    "h2d_inflight_depth": geometry.qd,
                    "gpu": GPU,
                    "cpu": CPU,
                    "memory_mb": MEMORY_MB,
                    "models_mount": MODELS_MOUNT,
                    "models_mount_read_only": True,
                    "source_worker_path": "PreplannedExtentTransport",
                    "arm": arm,
                    "repetition": repetition,
                    "attempt_id": f"{geometry.geometry_id}_{arm}_R{repetition}",
                    "serial": True,
                })
    return schedule


def build_source_only_matrix_schedule(
    *, repetitions: int = REPETITIONS,
) -> list[dict[str, Any]]:
    """Build the bounded 96-request source-only matrix schedule.

    Unlike :func:`build_schedule`, this deliberately has one arm per cell:
    the matrix is a source-only audit, not the 24-request causal control.
    """
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be positive")
    schedule: list[dict[str, Any]] = []
    index = 0
    for geometry in source_only_matrix_geometries():
        for repetition in range(1, repetitions + 1):
            index += 1
            schedule.append({
                "request_index": index,
                "geometry_id": geometry.geometry_id,
                "role": geometry.role,
                "model_name": MODEL_NAMES[geometry.role],
                "qd": geometry.qd,
                "source_qd": geometry.qd,
                "source_capacity": SOURCE_CAPACITY,
                "block_mib": geometry.block_mib,
                "block_bytes": geometry.block_bytes,
                "source_block_bytes": geometry.block_bytes,
                "h2d_copy_bytes": geometry.block_bytes,
                "h2d_inflight_depth": geometry.qd,
                "gpu": GPU,
                "cpu": CPU,
                "memory_mb": MEMORY_MB,
                "models_mount": MODELS_MOUNT,
                "models_mount_read_only": True,
                "source_worker_path": "PreplannedExtentTransport",
                "arm": SOURCE_ONLY_ARM,
                "repetition": repetition,
                "attempt_id": f"{geometry.geometry_id}_{SOURCE_ONLY_ARM}_R{repetition}",
                "serial": True,
            })
    return schedule


def build_plan() -> dict[str, Any]:
    schedule = build_schedule()
    return {
        "plan_version": 1,
        "execution": "opt_in_only",
        "remote_calls": False,
        "deployment": False,
        "identity": control_identity(),
        "arm_schemas": {
            SOURCE_ONLY_ARM: "source-only completion; shared pinned CPU uint8 staging; no dispatcher or CUDA transfer event",
            INTEGRATED_ARM: "current preplanned source->H2D path with the same pinned CPU uint8 staging and real CUDA backend",
        },
        "request_count": len(schedule),
        "eligible_runs_per_arm": 3,
        "schedule": schedule,
        "remote_command": remote_command(),
        "limitations": [
            "Phase 3 remains stopped.",
            "The plan does not deploy or invoke Modal.",
            "Existing Phase-2 artifacts and frozen reports are read-only inputs.",
        ],
    }


def build_source_only_matrix_plan() -> dict[str, Any]:
    """Return the zero-spend plan for the corrected full source-only matrix."""
    schedule = build_source_only_matrix_schedule()
    return {
        "plan_version": 1,
        "execution": "opt_in_only",
        "mode": "source-only-matrix",
        "remote_calls": False,
        "deployment": False,
        "identity": control_identity(),
        "arm_schemas": {
            SOURCE_ONLY_ARM: "source-only completion; shared pinned CPU uint8 staging; no dispatcher or CUDA transfer event",
        },
        "request_count": len(schedule),
        "eligible_runs_per_cell": REPETITIONS,
        "cell_count": len(source_only_matrix_geometries()),
        "schedule": schedule,
        "remote_command": remote_command("source-only-matrix"),
        "limitations": [
            "Phase 3 remains stopped.",
            "The plan does not deploy or invoke Modal.",
            "Existing Phase-2 artifacts and frozen reports are read-only inputs.",
        ],
    }


def remote_command(mode: str = "control") -> str:
    """Return the exact command for the parent remote operator."""
    if mode == "source-only-matrix":
        return (
            "python tools/phase2_audit_control.py --execute-remote "
            "--mode source-only-matrix "
            f"--app {CONTROL_APP_NAME} --out-dir phase2_source_only_matrix_runs "
            "--state phase2_source_only_matrix_runs/ledger.json"
        )
    return (
        "modal deploy phase2_audit_modal.py && python tools/phase2_audit_control.py "
        f"--execute-remote --app {CONTROL_APP_NAME} --out-dir <NEW-AUDIT-DIR> "
        f"--state <NEW-AUDIT-DIR>/ledger.json"
    )


def _header(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        raw = handle.read(8)
        if len(raw) != 8:
            raise ValueError("safetensors_header_length_missing")
        header_length = struct.unpack("<Q", raw)[0]
        header = json.loads(handle.read(header_length))
    if not isinstance(header, dict):
        raise ValueError("safetensors_header_not_object")
    payload = path.stat().st_size - 8 - int(header_length)
    if payload <= 0:
        raise ValueError("safetensors_payload_missing")
    return 8 + int(header_length), payload


class _PositionedReader:
    """A per-producer descriptor adapter over Golden Serial's reader."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fds: dict[int, int] = {}

    def readinto(self, target: Any, offset: int, producer_id: int | None = None) -> int:
        if producer_id is None:
            raise ExtentTransportError("producer_id_required")
        fd = self._fds.get(producer_id)
        if fd is None:
            fd = os.open(str(self.path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
            self._fds[producer_id] = fd
        # Keep the control arm on the exact production physical-read helper.
        # The transport owns syscall intervals; this adapter owns only fd
        # lifetime and delegates all positioned-read behavior to Golden Serial.
        import importlib

        golden_serial = importlib.import_module("comfymodal_runtime.golden_serial")
        return int(golden_serial._read_at(
            fd,
            golden_serial._writable_bytes_view(target),
            int(offset),
            producer_id=producer_id,
        ))

    def close(self) -> None:
        fds, self._fds = tuple(self._fds.values()), {}
        for fd in fds:
            os.close(fd)


def _filesystem_identity(path: Path) -> dict[str, Any]:
    try:
        info = path.stat()
        result: dict[str, Any] = {
            "path": str(path),
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
            "mode": stat.S_IMODE(info.st_mode),
        }
        statvfs = getattr(os, "statvfs", None)
        if callable(statvfs):
            volume = cast(Any, statvfs)(path)
            result.update({"fs_block_size": int(volume.f_bsize), "fs_name": "statvfs"})
        mountinfo = Path("/proc/self/mountinfo")
        if mountinfo.is_file():
            resolved = str(path.resolve())
            candidates: list[dict[str, str]] = []
            for line in mountinfo.read_text(encoding="utf-8", errors="replace").splitlines():
                fields = line.split(" - ", 1)
                left = fields[0].split()
                right = fields[1].split() if len(fields) == 2 else []
                if len(left) < 6 or len(right) < 2:
                    continue
                mountpoint = left[4].replace(r"\040", " ").replace(r"\011", "\t")
                if resolved == mountpoint or resolved.startswith(mountpoint.rstrip("/") + "/"):
                    candidates.append({
                        "mountpoint": mountpoint,
                        "filesystem_type": right[0],
                        "source": right[1],
                        "super_options": ",".join(right[2:]),
                    })
            if candidates:
                result["mount"] = max(candidates, key=lambda row: len(row["mountpoint"]))
        return result
    except (OSError, UnicodeError, ValueError) as exc:
        return {"path": str(path), "error": f"{type(exc).__name__}:{exc}"}


def _runtime_identity() -> dict[str, Any]:
    return {
        "provider": os.environ.get("MODAL_CLOUD_PROVIDER", ""),
        "region": os.environ.get("MODAL_REGION", ""),
        "image_id": os.environ.get("MODAL_IMAGE_ID", ""),
        "container_session_id": os.environ.get("CONTAINER_SESSION_ID", "") or os.environ.get("MODAL_TASK_ID", ""),
        "hostname": platform.node(),
        "cpu_request": CPU,
        "cpu_allocation": {"requested": CPU, "declared": CPU, "source": "phase2_control_identity"},
    }


def _strict_control_proof(
    arm: str,
    telemetry: Mapping[str, Any],
    payload_bytes: int,
) -> dict[str, Any]:
    reads = telemetry.get("physical_reads")
    reads_ok = isinstance(reads, list) and bool(reads) and all(
        isinstance(row, Mapping)
        and isinstance(row.get("requested_bytes"), int)
        and isinstance(row.get("returned_bytes"), int)
        and 0 <= row["returned_bytes"] <= row["requested_bytes"]
        for row in reads
    )
    read_rows = reads if isinstance(reads, list) else []
    source_ok = reads_ok and sum(
        int(cast(Mapping[str, Any], row)["returned_bytes"])
        for row in read_rows if isinstance(row, Mapping)
    ) == payload_bytes
    configured_h2d_depth = telemetry.get("configured_h2d_inflight_depth")
    configured_h2d_bytes = telemetry.get("configured_h2d_copy_bytes")
    predicates: dict[str, bool] = {
        "physical_syscall_bytes_retained": reads_ok,
        "source_payload_reconciled": source_ok,
        "source_workers_joined": bool(telemetry.get("source_worker_timing")),
        "source_capacity_fixed": telemetry.get("configured_source_capacity") == SOURCE_CAPACITY,
        "shared_positioned_read_helper": (
            telemetry.get("physical_read_provenance") == "golden_serial._read_at"
            and telemetry.get("physical_syscall_provenance") == "golden_serial._read_at"
        ),
        "writable_byte_view_contract": (
            telemetry.get("writable_byte_view_contract")
            == "golden_serial._writable_bytes_view"
        ),
        "pinned_cpu_uint8_staging": (
            telemetry.get("staging_buffer_kind")
            == "torch_cpu_uint8_pinned_contiguous_arena"
            and telemetry.get("staging_buffer_dtype") == "torch.uint8"
            and telemetry.get("staging_buffer_device") == "cpu"
            and telemetry.get("staging_buffer_pinned") is True
            and telemetry.get("staging_buffer_contiguous") is True
            and telemetry.get("staging_buffer_allocation_count") == 1
        ),
        "staging_buffer_geometry": (
            isinstance(configured_h2d_depth, int)
            and not isinstance(configured_h2d_depth, bool)
            and isinstance(configured_h2d_bytes, int)
            and not isinstance(configured_h2d_bytes, bool)
            and telemetry.get("staging_buffer_extent_count")
            == configured_h2d_depth
            and telemetry.get("staging_buffer_extent_shape")
            == [configured_h2d_bytes]
            and telemetry.get("staging_buffer_shape")
            == [configured_h2d_depth * configured_h2d_bytes]
        ),
        "staging_buffer_allocation_identity": (
            telemetry.get("staging_buffer_allocation_identity")
            == STAGING_BUFFER_ALLOCATION_IDENTITY
        ),
        "staging_buffer_observed": telemetry.get("staging_buffer_observed") is True,
    }
    if arm == SOURCE_ONLY_ARM:
        predicates.update({
            "no_h2d_dispatcher": telemetry.get("h2d_dispatcher_started") is False,
            "no_h2d_dispatcher_participation": telemetry.get("h2d_dispatcher_participation") is False,
            "zero_h2d_events": telemetry.get("h2d_copy_count") == 0,
            "zero_h2d_bytes": (
                telemetry.get("h2d_submitted_bytes", 0) == 0
                and telemetry.get("h2d_completed_bytes", 0) == 0
            ),
            "source_completion_releases_workers": (
                telemetry.get("execution_mode") == "source_only"
                and bool(telemetry.get("source_worker_timing"))
                and all(
                    row.get("release_reason") == "source_completion"
                    for row in telemetry["source_worker_timing"].values()
                )
            ),
        })
    else:
        predicates.update({
            "h2d_dispatcher_started": telemetry.get("h2d_dispatcher_started") is True,
            "h2d_payload_reconciled": (
                telemetry.get("h2d_submitted_bytes") == payload_bytes
                and telemetry.get("h2d_completed_bytes") == payload_bytes
            ),
        })
    failed = [name for name, value in predicates.items() if value is not True]
    proven = not failed
    return {
        "scope": "phase2_control_path_invariants",
        "strict": True,
        "proven": proven,
        "classification": "PROVEN" if proven else "proof-NO",
        "E27_SOURCE_MECHANISM_PROVEN": "YES" if proven else "NO",
        "line": f"E27_SOURCE_MECHANISM_PROVEN={'YES' if proven else 'NO'}",
        "predicates": predicates,
        "failed_predicates": failed,
    }


def _base_result(
    *,
    role: str,
    model_name: str,
    qd: int,
    block_bytes: int,
    arm: str,
    attempt_id: str,
    path: Path,
    payload_bytes: int,
    data_start: int,
    staging_buffer: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    staging = dict(staging_buffer or _staging_buffer_artifact(qd, block_bytes))
    return {
        "probe": "phase2_source_h2d_audit_control",
        "phase": PHASE,
        "phase_3_status": PHASE_3_STATUS,
        "attempt_id": attempt_id,
        "role": role,
        "model_name": model_name,
        "arm": arm,
        "geometry": {"role": role, "qd": qd, "block_bytes": block_bytes, "block_mib": block_bytes // (1024 * 1024)},
        "identity": {**control_identity(), **_runtime_identity()},
        "resolved_path": str(path),
        "path_resolution": "fixed_read_only_models_mount",
        "filesystem_mount_identity": _filesystem_identity(path),
        "file_size_bytes": path.stat().st_size,
        "data_start": data_start,
        "payload_bytes": payload_bytes,
        "source_worker_path": "PreplannedExtentTransport",
        "source_qd": qd,
        "source_capacity": SOURCE_CAPACITY,
        "source_block_bytes": block_bytes,
        "h2d_copy_bytes": block_bytes,
        "h2d_inflight_depth": qd,
        "configured_source_qd": qd,
        "configured_source_capacity": SOURCE_CAPACITY,
        "source_capacity": SOURCE_CAPACITY,
        "source_capacity_semantics": "buffering_work_capacity_only",
        "configured_source_block_bytes": block_bytes,
        "configured_h2d_copy_bytes": block_bytes,
        "configured_h2d_inflight_depth": qd,
        "h2d_settings": {
            "copy_bytes": block_bytes,
            "inflight_depth": qd,
        },
        "timing_scopes": {
            "SOURCE_WALL": "source path entry -> all source workers joined",
            "H2D_READY": "first H2D submit -> final required H2D completion; integrated only",
        },
        "comparison_contract": {
            "only_intended_arm_difference": "h2d_participation",
            "staging_buffer_allocation_identity": STAGING_BUFFER_ALLOCATION_IDENTITY,
        },
        "staging_buffer": staging,
        "staging_buffer_kind": staging["kind"],
        "staging_buffer_dtype": staging["dtype"],
        "staging_buffer_device": staging["device"],
        "staging_buffer_pinned": staging["pinned"],
        "staging_buffer_contiguous": staging["contiguous"],
        "staging_buffer_shape": staging["shape"],
        "staging_buffer_extent_shape": staging["extent_shape"],
        "staging_buffer_extent_count": staging["extent_count"],
        "staging_buffer_arena_bytes": staging["arena_bytes"],
        "staging_buffer_physical_allocation_count": staging["physical_allocation_count"],
        "staging_buffer_allocation_count": staging["physical_allocation_count"],
        "staging_buffer_allocation_identity": staging["allocation_identity"],
    }


def _staging_buffer_artifact(
    h2d_inflight_depth: int,
    h2d_copy_bytes: int,
    *,
    arena_bytes: int | None = None,
    physical_allocation_count: int = 1,
) -> dict[str, Any]:
    """Describe the common pinned staging allocation without exposing pointers.

    A pointer is request-local and cannot establish cross-arm comparability.
    This stable identity instead records the allocation topology and tensor
    contract that must be equal in both arms.
    """
    extent_count = max(1, int(h2d_inflight_depth))
    expected_bytes = extent_count * int(h2d_copy_bytes)
    if arena_bytes is not None and int(arena_bytes) != expected_bytes:
        raise ValueError("staging_buffer_arena_shape_mismatch")
    return {
        "kind": "torch_cpu_uint8_pinned_contiguous_arena",
        "dtype": "torch.uint8",
        "device": "cpu",
        "pinned": True,
        "contiguous": True,
        "shape": [expected_bytes],
        "extent_shape": [int(h2d_copy_bytes)],
        "extent_count": extent_count,
        "arena_bytes": expected_bytes,
        "physical_allocation_count": int(physical_allocation_count),
        "allocation_identity": STAGING_BUFFER_ALLOCATION_IDENTITY,
    }


def _allocate_pinned_staging_buffers(
    h2d_inflight_depth: int,
    h2d_copy_bytes: int,
) -> tuple[Any, tuple[Any, ...], dict[str, Any]]:
    """Allocate the exact CPU staging topology used by integrated Golden Serial."""
    import torch

    extent_count = max(1, int(h2d_inflight_depth))
    extent_arena = cast(Any, torch).empty(
        extent_count * int(h2d_copy_bytes),
        dtype=cast(Any, torch).uint8,
        pin_memory=True,
    )
    extent_buffers = tuple(
        extent_arena[index * h2d_copy_bytes : (index + 1) * h2d_copy_bytes]
        for index in range(extent_count)
    )
    if (
        str(extent_arena.dtype) != "torch.uint8"
        or str(extent_arena.device) != "cpu"
        or not bool(extent_arena.is_pinned())
        or not bool(extent_arena.is_contiguous())
        or any(not bool(buffer.is_contiguous()) for buffer in extent_buffers)
    ):
        raise ExtentTransportError("invalid_pinned_staging_buffer_contract")
    artifact = _staging_buffer_artifact(
        h2d_inflight_depth,
        h2d_copy_bytes,
        arena_bytes=int(extent_arena.numel()),
    )
    return extent_arena, extent_buffers, artifact


def _run_source_only(path: Path, *, role: str, qd: int, block_bytes: int, attempt_id: str) -> dict[str, Any]:
    data_start, payload_bytes = _header(path)
    extents = plan_preplanned_extents(
        payload_bytes, block_bytes, block_bytes,
        source_offset=data_start, destination_offset=0,
    )
    reader = _PositionedReader(path)
    extent_arena, extent_buffers, staging_buffer = _allocate_pinned_staging_buffers(qd, block_bytes)
    try:
        transport = PreplannedExtentTransport(
            source_qd=qd,
            source_block_bytes=block_bytes,
            h2d_copy_bytes=block_bytes,
            h2d_inflight_depth=qd,
            source_capacity=SOURCE_CAPACITY,
            # Match integrated Golden Serial: one contiguous pinned CPU uint8
            # arena, sliced into the configured H2D extent depth.
            buffers=extent_buffers,
            metadata={
                "arm": SOURCE_ONLY_ARM,
                "control_profile": CONTROL_PROFILE,
                "physical_read_provenance": "golden_serial._read_at",
                "physical_syscall_provenance": "golden_serial._read_at",
                "writable_byte_view_contract": "golden_serial._writable_bytes_view",
                "staging_buffer_observed": True,
                **{
                    f"staging_buffer_{key}": value
                    for key, value in {
                        "kind": staging_buffer["kind"],
                        "dtype": staging_buffer["dtype"],
                        "device": staging_buffer["device"],
                        "pinned": staging_buffer["pinned"],
                        "contiguous": staging_buffer["contiguous"],
                        "shape": staging_buffer["shape"],
                        "extent_shape": staging_buffer["extent_shape"],
                        "extent_count": staging_buffer["extent_count"],
                        "allocation_count": staging_buffer["physical_allocation_count"],
                        "allocation_identity": staging_buffer["allocation_identity"],
                    }.items()
                },
                "staging_buffer": staging_buffer,
                "control_operation_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
                "transport_cleanup_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
            },
            cleanup_timeout=CONTROL_OPERATION_TIMEOUT_SECONDS,
        )
        result = transport.execute_source_only(
            extents, reader, total_bytes=payload_bytes,
            source_offset=data_start, destination_offset=0,
        )
    finally:
        reader.close()
    telemetry = dict(result["telemetry"])
    proof = _strict_control_proof(SOURCE_ONLY_ARM, telemetry, payload_bytes)
    base = _base_result(
        role=role, model_name=path.name, qd=qd, block_bytes=block_bytes,
        arm=SOURCE_ONLY_ARM, attempt_id=attempt_id, path=path,
        payload_bytes=payload_bytes, data_start=data_start,
        staging_buffer=staging_buffer,
    )
    base.update({
        "status": "ok" if proof["proven"] else "error",
        "execution_arm": SOURCE_ONLY_ARM,
        "source_only": True,
        "cuda_used": False,
        "h2d_used": False,
        "SOURCE_WALL_MS": telemetry.get("source_wall_ms"),
        "source_wall_ms": telemetry.get("source_wall_ms"),
        "H2D_READY_MS": None,
        "h2d_ready_ms": None,
        "configured_qd": qd,
        "configured_source_qd": qd,
        "source_qd": qd,
        "configured_source_capacity": SOURCE_CAPACITY,
        "source_capacity": SOURCE_CAPACITY,
        "control_operation_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
        "transport_cleanup_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
        "configured_source_block_bytes": block_bytes,
        "configured_h2d_copy_bytes": block_bytes,
        "configured_h2d_inflight_depth": qd,
        "achieved_h2d_inflight_depth_max": 0,
        "achieved_h2d_inflight_depth": 0,
        "h2d_settings": {
            "copy_bytes": block_bytes,
            "inflight_depth": qd,
        },
        "achieved_qd_mean": telemetry.get("achieved_source_qd_mean"),
        "achieved_qd_max": telemetry.get("achieved_source_qd_max"),
        "achieved_source_qd_mean": telemetry.get("achieved_source_qd_mean"),
        "achieved_source_qd_max": telemetry.get("achieved_source_qd_max"),
        "source_qd_timeline": telemetry.get("source_qd_timeline", []),
        "source_worker_timing": telemetry.get("source_worker_timing", {}),
        "physical_syscall_telemetry": telemetry.get("physical_reads", []),
        "physical_read_telemetry": telemetry.get("physical_reads", []),
        "source_read_count": telemetry.get("source_read_count"),
        "source_read_bytes": telemetry.get("source_read_bytes"),
        "source_requested_bytes": telemetry.get("source_requested_bytes"),
        "source_returned_bytes": telemetry.get("source_returned_bytes"),
        "physical_read_provenance": telemetry.get("physical_read_provenance"),
        "physical_syscall_provenance": telemetry.get("physical_syscall_provenance"),
        "source_active_interval_start_ns": telemetry.get("source_active_interval_start_ns"),
        "source_active_interval_end_ns": telemetry.get("source_active_interval_end_ns"),
        "source_active_wall_ns": telemetry.get("source_active_wall_ns"),
        "source_active_wall_ms": telemetry.get("source_active_wall_ms"),
        "source_active_start_ns": telemetry.get("source_active_start_ns"),
        "source_active_end_ns": telemetry.get("source_active_end_ns"),
        "source_active_duration_ns": telemetry.get("source_active_duration_ns"),
        "source_active_duration_ms": telemetry.get("source_active_duration_ms"),
        "qd_occupancy_ns": telemetry.get("qd_occupancy_ns"),
        "qd_occupancy_ms": telemetry.get("qd_occupancy_ms"),
        "time_at_qd_ns": telemetry.get("time_at_qd_ns"),
        "time_at_qd_ms": telemetry.get("time_at_qd_ms"),
        "source_worker_busy_ns": telemetry.get("source_worker_busy_ns"),
        "source_worker_busy_ms": telemetry.get("source_worker_busy_ms"),
        "payload_reconciliation": {
            "payload_bytes": payload_bytes,
            "requested_bytes": telemetry.get("source_requested_bytes"),
            "returned_bytes": telemetry.get("source_returned_bytes"),
            "ok": telemetry.get("source_returned_bytes") == payload_bytes,
        },
        "h2d_dispatcher": {"started": False, "participated": False, "events": []},
        "transport_telemetry": telemetry,
        "staging_buffer": staging_buffer,
        "strict_e27_proof": proof,
        "E27_SOURCE_MECHANISM_PROVEN": proof["E27_SOURCE_MECHANISM_PROVEN"],
        "classification": "ELIGIBLE" if proof["proven"] else "proof-NO",
    })
    return base


@contextmanager
def _decoupled_environment(qd: int, block_bytes: int):
    names = {
        "COMFYMODAL_GOLDEN_SOURCE_QD": str(qd),
        "COMFYMODAL_GOLDEN_SOURCE_BLOCK_BYTES": str(block_bytes),
        "COMFYMODAL_GOLDEN_H2D_COPY_BYTES": str(block_bytes),
        "COMFYMODAL_GOLDEN_H2D_INFLIGHT_DEPTH": str(qd),
        # Capacity is buffering/work capacity, not the selected source QD.
        "COMFYMODAL_GOLDEN_SOURCE_CAPACITY": str(SOURCE_CAPACITY),
    }
    old = {name: os.environ.get(name) for name in names}
    os.environ.update(names)
    try:
        yield
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextmanager
def _control_integrated_transport_timeout():
    """Give the existing integrated producer path the control deadline.

    ``golden_serial`` deliberately owns the production call path and its
    transport constructor currently uses the transport default.  Temporarily
    specialize that constructor for this control request so source-only and
    integrated arms use the same bounded worker/dispatcher join contract,
    without changing the production path or making joins unbounded.
    """
    import importlib

    transport_module = cast(Any, importlib.import_module("comfymodal_runtime.golden_qd_transport"))

    with _CONTROL_TRANSPORT_PATCH_LOCK:
        original_transport = transport_module.PreplannedExtentTransport

        class _ControlPreplannedExtentTransport(original_transport):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                metadata = dict(kwargs.get("metadata") or {})
                metadata["control_operation_timeout_seconds"] = CONTROL_OPERATION_TIMEOUT_SECONDS
                kwargs["metadata"] = metadata
                kwargs["cleanup_timeout"] = CONTROL_OPERATION_TIMEOUT_SECONDS
                super().__init__(*args, **kwargs)

        transport_module.PreplannedExtentTransport = _ControlPreplannedExtentTransport
        try:
            yield
        finally:
            transport_module.PreplannedExtentTransport = original_transport


def _run_integrated(path: Path, *, role: str, qd: int, block_bytes: int, attempt_id: str) -> dict[str, Any]:
    # This is deliberately the existing production preplanned reader, not a
    # second CUDA implementation owned by the audit harness.
    from .golden_serial import read_file_qd_gpu

    with _control_integrated_transport_timeout():
        with _decoupled_environment(qd, block_bytes):
            result = read_file_qd_gpu(
                str(path), role=role, device="cuda:0", qd=qd,
                block_bytes=block_bytes, diagnostics=True, transport_arm="decoupled",
            )
    owner = result.get("owner")
    try:
        stats = dict(result.get("stats") or {})
    finally:
        if owner is not None:
            owner.close()
    stats["control_operation_timeout_seconds"] = CONTROL_OPERATION_TIMEOUT_SECONDS
    stats["transport_cleanup_timeout_seconds"] = CONTROL_OPERATION_TIMEOUT_SECONDS
    actual = dict(stats.get("actual_source") or stats.get("actual_source_telemetry") or {})
    pipeline = dict(stats.get("pipeline_telemetry") or {})
    data_start = int(stats.get("source_base", 0))
    payload_bytes = int(stats.get("file_bytes", 0))
    # ActualSourceTelemetry is the authoritative physical-read evidence plane;
    # the pipeline copy is retained only as a fallback for older runtimes.
    physical_reads = actual.get("actual_source_events") or pipeline.get("physical_reads") or []
    pinned_arena_bytes = stats.get("pinned_bytes", pipeline.get("pinned_arena_bytes"))
    pinned_allocation_count = stats.get(
        "pinned_arena_physical_allocation_count",
        pipeline.get("pinned_arena_physical_allocation_count", 0),
    )
    staging_buffer = _staging_buffer_artifact(
        qd,
        block_bytes,
        arena_bytes=pinned_arena_bytes,
        physical_allocation_count=int(pinned_allocation_count),
    )
    telemetry = {
        **pipeline,
        "control_operation_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
        "physical_reads": physical_reads,
        "source_requested_bytes": sum(int(row.get("requested_bytes", 0)) for row in physical_reads if isinstance(row, Mapping)),
        "source_returned_bytes": sum(int(row.get("returned_bytes", 0)) for row in physical_reads if isinstance(row, Mapping)),
        "physical_read_provenance": actual.get("physical_syscall_provenance"),
        "physical_syscall_provenance": actual.get("physical_syscall_provenance"),
        "writable_byte_view_contract": "golden_serial._writable_bytes_view",
        "staging_buffer_observed": pinned_arena_bytes is not None,
        "configured_h2d_copy_bytes": block_bytes,
        "configured_h2d_inflight_depth": qd,
        "staging_buffer": staging_buffer,
        **{
            f"staging_buffer_{key}": value
            for key, value in {
                "kind": staging_buffer["kind"],
                "dtype": staging_buffer["dtype"],
                "device": staging_buffer["device"],
                "pinned": staging_buffer["pinned"],
                "contiguous": staging_buffer["contiguous"],
                "shape": staging_buffer["shape"],
                "extent_shape": staging_buffer["extent_shape"],
                "extent_count": staging_buffer["extent_count"],
                "allocation_count": staging_buffer["physical_allocation_count"],
                "allocation_identity": staging_buffer["allocation_identity"],
            }.items()
        },
        "h2d_dispatcher_started": True,
        "h2d_submitted_bytes": actual.get("h2d_submitted_bytes", stats.get("h2d_submitted_bytes")),
        "h2d_completed_bytes": actual.get("h2d_completed_bytes", stats.get("h2d_completed_bytes")),
        "execution_mode": "integrated",
    }
    proof = _strict_control_proof(INTEGRATED_ARM, telemetry, payload_bytes)
    base = _base_result(
        role=role, model_name=path.name, qd=qd, block_bytes=block_bytes,
        arm=INTEGRATED_ARM, attempt_id=attempt_id, path=path,
        payload_bytes=payload_bytes, data_start=data_start,
        staging_buffer=staging_buffer,
    )
    base.update({
        "status": "ok" if proof["proven"] else "error",
        "execution_arm": INTEGRATED_ARM,
        "source_only": False,
        "cuda_used": True,
        "h2d_used": True,
        "SOURCE_WALL_MS": actual.get("SOURCE_TOTAL_WALL_MS", stats.get("SOURCE_TOTAL_WALL_MS")),
        "source_wall_ms": actual.get("SOURCE_TOTAL_WALL_MS", stats.get("SOURCE_TOTAL_WALL_MS")),
        "H2D_READY_MS": actual.get("SOURCE_TO_GPU_READY_MS", stats.get("SOURCE_TO_GPU_READY_MS")),
        "h2d_ready_ms": actual.get("SOURCE_TO_GPU_READY_MS", stats.get("SOURCE_TO_GPU_READY_MS")),
        "H2D_TOTAL_WALL_MS": actual.get("H2D_TOTAL_WALL_MS", stats.get("H2D_TOTAL_WALL_MS")),
        "configured_qd": qd,
        "configured_source_qd": qd,
        "source_qd": qd,
        "configured_source_capacity": SOURCE_CAPACITY,
        "control_operation_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
        "transport_cleanup_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
        "source_capacity": SOURCE_CAPACITY,
        "configured_source_block_bytes": block_bytes,
        "configured_h2d_copy_bytes": block_bytes,
        "configured_h2d_inflight_depth": qd,
        "achieved_h2d_inflight_depth_max": pipeline.get(
            "achieved_h2d_inflight_depth_max", 0
        ),
        "achieved_h2d_inflight_depth": pipeline.get(
            "achieved_h2d_inflight_depth_max", 0
        ),
        "h2d_settings": {
            "copy_bytes": block_bytes,
            "inflight_depth": qd,
        },
        "achieved_qd_mean": pipeline.get("achieved_source_qd_mean", actual.get("time_weighted_mean_qd")),
        "achieved_qd_max": pipeline.get("achieved_source_qd_max", actual.get("max_actual_source_inflight")),
        "achieved_source_qd_mean": pipeline.get("achieved_source_qd_mean", actual.get("time_weighted_mean_qd")),
        "achieved_source_qd_max": pipeline.get("achieved_source_qd_max", actual.get("max_actual_source_inflight")),
        "source_qd_timeline": pipeline.get("source_qd_timeline", actual.get("actual_source_transitions", [])),
        "source_worker_timing": pipeline.get("source_worker_timing", {}),
        "physical_syscall_telemetry": physical_reads,
        "physical_read_telemetry": physical_reads,
        "source_read_count": telemetry.get("source_read_count"),
        "source_read_bytes": telemetry.get("source_read_bytes"),
        "source_requested_bytes": telemetry.get("source_requested_bytes"),
        "source_returned_bytes": telemetry.get("source_returned_bytes"),
        "physical_read_provenance": telemetry.get("physical_read_provenance"),
        "physical_syscall_provenance": telemetry.get("physical_syscall_provenance"),
        "source_active_interval_start_ns": pipeline.get("source_active_interval_start_ns", actual.get("source_active_interval_start_ns")),
        "source_active_interval_end_ns": pipeline.get("source_active_interval_end_ns", actual.get("source_active_interval_end_ns")),
        "source_active_wall_ns": pipeline.get("source_active_wall_ns", actual.get("source_active_wall_ns")),
        "source_active_wall_ms": pipeline.get("source_active_wall_ms", actual.get("source_active_wall_ms")),
        "source_active_start_ns": pipeline.get("source_active_start_ns", actual.get("source_active_start_ns")),
        "source_active_end_ns": pipeline.get("source_active_end_ns", actual.get("source_active_end_ns")),
        "source_active_duration_ns": pipeline.get("source_active_duration_ns", actual.get("source_active_duration_ns")),
        "source_active_duration_ms": pipeline.get("source_active_duration_ms", actual.get("source_active_duration_ms")),
        "qd_occupancy_ns": pipeline.get("qd_occupancy_ns", actual.get("qd_occupancy_ns")),
        "qd_occupancy_ms": pipeline.get("qd_occupancy_ms", actual.get("qd_occupancy_ms")),
        "time_at_qd_ns": pipeline.get("time_at_qd_ns", actual.get("time_at_qd_ns")),
        "time_at_qd_ms": pipeline.get("time_at_qd_ms", actual.get("time_at_qd_ms")),
        "source_worker_busy_ns": pipeline.get("source_worker_busy_ns"),
        "source_worker_busy_ms": pipeline.get("source_worker_busy_ms"),
        "payload_reconciliation": {
            "payload_bytes": payload_bytes,
            "requested_bytes": telemetry["source_requested_bytes"],
            "returned_bytes": telemetry["source_returned_bytes"],
            "h2d_submitted_bytes": telemetry["h2d_submitted_bytes"],
            "h2d_completed_bytes": telemetry["h2d_completed_bytes"],
            "ok": proof["proven"],
        },
        "h2d_dispatcher": {
            "started": True,
            "participated": True,
            "events": actual.get("h2d_events", stats.get("h2d_events", [])),
        },
        "transport_telemetry": {**stats, "staging_buffer": staging_buffer},
        "staging_buffer": staging_buffer,
        "strict_e27_proof": proof,
        "E27_SOURCE_MECHANISM_PROVEN": proof["E27_SOURCE_MECHANISM_PROVEN"],
        "classification": "ELIGIBLE" if proof["proven"] else "proof-NO",
    })
    return base


def run_phase2_audit_request(
    role: str,
    model_name: str,
    arm: str,
    qd: int,
    block_bytes: int,
    attempt_id: str = "",
    *,
    models_root: str | Path = MODELS_MOUNT,
) -> dict[str, Any]:
    """Execute one request in a remote container or a local fixture."""
    role = str(role).lower().strip()
    arm = str(arm).strip()
    supported_block_bytes = tuple(value * 1024 * 1024 for value in SOURCE_ONLY_MATRIX_BLOCK_MIB)
    geometry_supported = (
        qd in SOURCE_ONLY_MATRIX_QD_VALUES
        and block_bytes in supported_block_bytes
        if arm == SOURCE_ONLY_ARM
        else qd in QD_VALUES and block_bytes == BLOCK_MIB * 1024 * 1024
    )
    if (
        role not in ROLES
        or arm not in ARMS
        or not geometry_supported
    ):
        return {"status": "error", "classification": "INVALID", "error": "unsupported_control_geometry"}
    model = Path(str(model_name))
    if model.name != str(model_name):
        return {"status": "error", "classification": "INVALID", "error": "model_name_must_be_basename"}
    path = Path(models_root) / ("text_encoders" if role == "clip" else "diffusion_models") / model.name
    try:
        if not path.is_file():
            raise FileNotFoundError(str(path))
        if arm == SOURCE_ONLY_ARM:
            return _run_source_only(path, role=role, qd=qd, block_bytes=block_bytes, attempt_id=attempt_id)
        return _run_integrated(path, role=role, qd=qd, block_bytes=block_bytes, attempt_id=attempt_id)
    except Exception as exc:
        return {
            "status": "error", "classification": "FAILED", "attempt_id": attempt_id,
            "role": role, "model_name": model.name, "arm": arm, "qd": qd,
            "identity": control_identity(),
            "control_operation_timeout_seconds": CONTROL_OPERATION_TIMEOUT_SECONDS,
            "block_bytes": block_bytes, "error": f"{type(exc).__name__}:{str(exc)[:300]}",
        }


def validate_artifact(data: Mapping[str, Any], expected: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Fail closed on identity, raw-byte, reconciliation, or proof omissions."""
    failures: list[str] = []
    geometry = data.get("geometry")
    geometry = geometry if isinstance(geometry, Mapping) else {}
    for key in ("attempt_id", "role", "model_name", "arm", "qd", "block_bytes"):
        if data.get(key, geometry.get(key)) != expected.get(key):
            failures.append(f"{key}_mismatch")
    for key in ("source_qd", "source_capacity"):
        if key in expected and data.get(key, geometry.get(key)) != expected[key]:
            failures.append(f"{key}_mismatch")
    if data.get("status") != "ok":
        failures.append("status_not_ok")
    if data.get("classification") != "ELIGIBLE":
        failures.append("not_eligible")
    proof = data.get("strict_e27_proof")
    if not isinstance(proof, Mapping) or proof.get("strict") is not True or proof.get("proven") is not True:
        failures.append("strict_e27_proof_NO")
    reads = data.get("physical_syscall_telemetry")
    if not isinstance(reads, list) or not reads:
        failures.append("physical_syscall_telemetry_missing")
    else:
        for row in reads:
            if not isinstance(row, Mapping) or not isinstance(row.get("requested_bytes"), int) or not isinstance(row.get("returned_bytes"), int) or not 0 <= row["returned_bytes"] <= row["requested_bytes"]:
                failures.append("physical_syscall_byte_counts_invalid")
                break
    if data.get("configured_source_capacity") != SOURCE_CAPACITY:
        failures.append("source_capacity_mismatch")
    staging = data.get("staging_buffer")
    try:
        expected_staging = _staging_buffer_artifact(
            int(expected.get("qd", data.get("qd", 0))),
            int(expected.get("block_bytes", data.get("block_bytes", 0))),
        )
    except (TypeError, ValueError):
        expected_staging = None
        failures.append("staging_buffer_geometry_invalid")
    if not isinstance(staging, Mapping):
        failures.append("staging_buffer_missing")
    elif expected_staging is not None and dict(staging) != expected_staging:
        failures.append("staging_buffer_contract_mismatch")
    if isinstance(staging, Mapping):
        flat_staging_fields = {
            "staging_buffer_kind": "kind",
            "staging_buffer_dtype": "dtype",
            "staging_buffer_device": "device",
            "staging_buffer_pinned": "pinned",
            "staging_buffer_contiguous": "contiguous",
            "staging_buffer_shape": "shape",
            "staging_buffer_extent_shape": "extent_shape",
            "staging_buffer_extent_count": "extent_count",
            "staging_buffer_arena_bytes": "arena_bytes",
            "staging_buffer_physical_allocation_count": "physical_allocation_count",
            "staging_buffer_allocation_identity": "allocation_identity",
        }
        for flat_key, nested_key in flat_staging_fields.items():
            if data.get(flat_key) != staging.get(nested_key):
                failures.append(f"{flat_key}_mismatch")
    reconciliation = data.get("payload_reconciliation")
    if not isinstance(reconciliation, Mapping) or reconciliation.get("ok") is not True:
        failures.append("payload_reconciliation_failed")
    return not failures, failures


def classify_artifact(data: Mapping[str, Any], expected: Mapping[str, Any]) -> str:
    if data.get("classification") == "proof-NO" or (
        isinstance(data.get("strict_e27_proof"), Mapping)
        and data["strict_e27_proof"].get("proven") is not True
    ):
        return "proof-NO"
    if data.get("status") in {"failed", "error"} and not data.get("physical_syscall_telemetry"):
        return "FAILED"
    valid, _ = validate_artifact(data, expected)
    return "ELIGIBLE" if valid else "INVALID"


def ingest_artifact(path: str | Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    """Read exactly ``path`` and retain its classification; never relabel raw data."""
    artifact = Path(path)
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("artifact_not_object")
        classification = classify_artifact(data, expected)
        valid, failures = validate_artifact(data, expected)
        return {"path": str(artifact), "classification": classification, "valid": valid, "failures": failures, "artifact": data}
    except Exception as exc:
        return {"path": str(artifact), "classification": "FAILED", "valid": False, "failures": [f"{type(exc).__name__}:{exc}"], "artifact": None}


def summarize_artifacts(paths: Iterable[str | Path]) -> dict[str, Any]:
    """Produce an offline report from explicit artifact paths only."""
    rows: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append({"path": str(path), "classification": "FAILED", "error": f"{type(exc).__name__}:{exc}"})
            continue
        if not isinstance(data, dict):
            rows.append({"path": str(path), "classification": "INVALID", "error": "artifact_not_object"})
            continue
        proof = data.get("strict_e27_proof")
        geometry = data.get("geometry")
        geometry = geometry if isinstance(geometry, Mapping) else {}
        staging = data.get("staging_buffer")
        staging = staging if isinstance(staging, Mapping) else {}
        rows.append({
            "path": str(path),
            "attempt_id": data.get("attempt_id"),
            "role": data.get("role"),
            "arm": data.get("arm"),
            "qd": data.get("qd", geometry.get("qd")),
            "source_qd": data.get("source_qd", data.get("configured_source_qd")),
            "source_capacity": data.get("source_capacity", data.get("configured_source_capacity")),
            "block_bytes": data.get("block_bytes", geometry.get("block_bytes")),
            "h2d_copy_bytes": data.get("configured_h2d_copy_bytes"),
            "h2d_inflight_depth": data.get("configured_h2d_inflight_depth"),
            "achieved_source_qd_max": data.get("achieved_source_qd_max"),
            "achieved_h2d_inflight_depth_max": data.get("achieved_h2d_inflight_depth_max"),
            "status": data.get("status"),
            "classification": data.get("classification") or (proof or {}).get("classification"),
            "SOURCE_WALL_MS": data.get("SOURCE_WALL_MS"),
            "H2D_READY_MS": data.get("H2D_READY_MS"),
            "requested_bytes": (data.get("payload_reconciliation") or {}).get("requested_bytes"),
            "returned_bytes": (data.get("payload_reconciliation") or {}).get("returned_bytes"),
            "physical_read_count": len(data.get("physical_syscall_telemetry") or []),
            "staging_buffer": data.get("staging_buffer"),
            "staging_buffer_kind": staging.get("kind"),
            "staging_buffer_shape": staging.get("shape"),
            "staging_buffer_extent_shape": staging.get("extent_shape"),
            "staging_buffer_allocation_identity": staging.get("allocation_identity"),
            "staging_buffer_physical_allocation_count": staging.get("physical_allocation_count"),
            "provider": (data.get("identity") or {}).get("provider"),
            "region": (data.get("identity") or {}).get("region"),
            "filesystem_mount_identity": data.get("filesystem_mount_identity"),
            "strict_e27_proof": proof,
        })
    return {"report": "phase2_control_audit", "artifact_count": len(rows), "rows": rows, "limitations": ["Only explicitly supplied paths were read."]}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="print the zero-spend plan (default)")
    parser.add_argument("--report", nargs="*", metavar="ARTIFACT", help="summarize explicit artifact paths")
    parser.add_argument("--execute-remote", action="store_true", help="reserved for the parent remote operator")
    parser.add_argument("--app", default=CONTROL_APP_NAME)
    parser.add_argument("--output", type=Path, help="write the deterministic plan JSON")
    args = parser.parse_args(argv)
    if args.execute_remote:
        print("remote execution is parent-operator-only; use the exact command in the plan", file=sys.stderr)
        return 2
    if args.report is not None and args.report:
        print(json.dumps(summarize_artifacts(args.report), indent=2, sort_keys=True))
    else:
        plan = build_plan()
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "ARMS", "AuditGeometry", "BLOCK_MIB", "CONTROL_APP_NAME", "INTEGRATED_ARM",
    "MODEL_NAMES", "PHASE_3_STATUS", "SOURCE_CAPACITY", "SOURCE_ONLY_ARM", "SOURCE_ONLY_MATRIX_BLOCK_MIB", "SOURCE_ONLY_MATRIX_QD_VALUES", "audit_geometries",
    "CONTROL_OPERATION_TIMEOUT_SECONDS", "STAGING_BUFFER_ALLOCATION_IDENTITY", "build_plan", "build_schedule", "build_source_only_matrix_plan", "build_source_only_matrix_schedule", "classify_artifact", "control_identity",
    "ingest_artifact", "run_phase2_audit_request", "summarize_artifacts",
    "source_only_matrix_geometries", "validate_artifact",
]
