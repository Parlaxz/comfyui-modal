"""Dedicated source-only Modal endpoint for the C9 recovery experiment.

This is intentionally separate from Golden and from the historical E04
campaign.  It reads only the safetensors payload from the read-only models
Volume and never imports torch or attaches an accelerator.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
from pathlib import Path
from typing import Any, Mapping, cast

import modal


SOURCE_BLOCK_BYTES = 32 * 1024 * 1024
SOURCE_QD_VALUES = (2, 4, 8)
SOURCE_ROLES = ("clip", "unet")
MODELS = {"clip": "qwen_3_4b.safetensors", "unet": "z_image_turbo_bf16.safetensors"}
MODELS_ROOT = "/root/models"
MODELS_VOLUME_NAME = "comfyui-models"
DECLARED_CPU = 4
DECLARED_MEMORY_MB = 8192
APP_NAME = os.environ.get(
    "COMFYMODAL_C9_RECOVERY_APP_NAME", "sept-unetclip-c9-recovery-source-only"
)

_ROOT = Path(__file__).resolve().parent

try:
    _image = (
        modal.Image.debian_slim(python_version="3.11")
        .entrypoint([])
        .add_local_python_source("comfymodal_runtime", copy=True)
        .add_local_file(str(_ROOT / "c9_recovery_modal.py"), "/root/c9_recovery_modal.py", copy=True)
    )
except Exception as exc:
    raise RuntimeError("C9 recovery source-only image construction failed") from exc

_models_volume = modal.Volume.from_name(MODELS_VOLUME_NAME, create_if_missing=False)
_models_mount = _models_volume.with_mount_options(read_only=True)
app = modal.App(APP_NAME, image=_image, include_source=False)


def _unescape_mountinfo(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\134", "\\")


def _filesystem_identity(path: Path) -> dict[str, Any]:
    """Record the host filesystem and mount containing *path*, best effort."""
    result: dict[str, Any] = {
        "path": str(path),
        "mount_read_only_requested": True,
        "stat": {},
        "statvfs": {},
        "mount": None,
    }
    try:
        info = path.stat()
        result["stat"] = {
            "device": getattr(info, "st_dev", None),
            "inode": getattr(info, "st_ino", None),
            "mode": stat.S_IMODE(info.st_mode),
        }
    except OSError as exc:
        result["stat_error"] = f"{type(exc).__name__}:{exc}"
    try:
        statvfs = getattr(os, "statvfs", None)
        if not callable(statvfs):
            raise OSError("statvfs_unavailable")
        vfs = cast(Any, statvfs(path))
        result["statvfs"] = {
            "filesystem_block_size": int(vfs.f_bsize),
            "fragment_size": int(vfs.f_frsize),
            "available_bytes": int(vfs.f_bavail * vfs.f_frsize),
        }
    except OSError as exc:
        result["statvfs_error"] = f"{type(exc).__name__}:{exc}"

    mountinfo = Path("/proc/self/mountinfo")
    best: tuple[int, dict[str, Any]] | None = None
    try:
        target = str(path.resolve())
        for line in mountinfo.read_text(encoding="utf-8").splitlines():
            left, separator, right = line.partition(" - ")
            if not separator:
                continue
            fields = left.split()
            if len(fields) < 6:
                continue
            mountpoint = _unescape_mountinfo(fields[4])
            if target != mountpoint and not target.startswith(mountpoint.rstrip("/") + "/"):
                continue
            right_fields = right.split()
            mount = {
                "mount_id": int(fields[0]),
                "parent_id": int(fields[1]),
                "major_minor": fields[2],
                "root": _unescape_mountinfo(fields[3]),
                "mountpoint": mountpoint,
                "mount_options": fields[5],
                "filesystem_type": right_fields[0] if right_fields else None,
                "source": right_fields[1] if len(right_fields) > 1 else None,
                "super_options": right_fields[2] if len(right_fields) > 2 else None,
                "read_only_observed": "ro" in fields[5].split(","),
            }
            if best is None or len(mountpoint) > best[0]:
                best = (len(mountpoint), mount)
    except (OSError, ValueError) as exc:
        result["mountinfo_error"] = f"{type(exc).__name__}:{exc}"
    if best is not None:
        result["mount"] = best[1]
    return result


def _identity(path: Path, evidence: Mapping[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        st = path.stat()
        info = {
            "path": str(path),
            "basename": path.name,
            "size_bytes": int(st.st_size),
            "device": getattr(st, "st_dev", None),
            "inode": getattr(st, "st_ino", None),
            "mtime_ns": getattr(st, "st_mtime_ns", None),
        }
    except OSError as exc:
        info = {"path": str(path), "error": f"{type(exc).__name__}:{exc}"}
    data_start = int(evidence.get("data_start") or 0)
    payload_bytes = int(evidence.get("payload_bytes") or 0)
    block_digests = [
        {
            "offset": item.get("source_offset"),
            "bytes": item.get("returned_bytes"),
            "sha256": item.get("sha256"),
        }
        for worker in evidence.get("workers", [])
        for item in worker.get("block_digests", [])
    ]
    manifest = json.dumps(sorted(block_digests, key=lambda item: int(item["offset"])), sort_keys=True, separators=(",", ":")).encode()
    return {
        "file_identity": info,
        "payload_identity": {
            "data_start": data_start,
            "payload_bytes": payload_bytes,
            "block_digest_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "hash_scope": "all measured payload blocks; no second payload scan",
        },
        "filesystem_identity": _filesystem_identity(path),
    }


def _normalize_evidence(result: dict[str, Any], role: str, model_name: str, qd: int) -> dict[str, Any]:
    """Add C9-specific evidence aliases without changing oracle semantics."""
    result["experiment"] = "c9_recovery"
    result["source_block_bytes"] = SOURCE_BLOCK_BYTES
    result["source_qd"] = qd
    result["gpu_attachment"] = {"attached": False, "requested": False, "reason": "source_only"}
    result["execution_contract"] = {
        "source_only": True,
        "torch_imported": False,
        "cuda_used": False,
        "h2d_used": False,
        "model_construction": False,
        "dispatcher_participation": False,
        "filesystem_mount": MODELS_ROOT,
        "mount_read_only": True,
        "fd_topology": "one read-only file descriptor per worker; positioned reads",
        "range_geometry": "static contiguous disjoint payload ranges",
        "workers_per_lane": 1,
        "block_bytes": SOURCE_BLOCK_BYTES,
        "qd_values": list(SOURCE_QD_VALUES),
    }
    raw_events = list(result.get("physical_syscall_telemetry") or [])
    reads = []
    for event in raw_events:
        reads.append({
            "worker_id": int(event.get("producer_id", -1)),
            "region_id": event.get("region_id"),
            "offset": int(event.get("source_offset", 0)),
            "source_offset": int(event.get("source_offset", 0)),
            "requested_bytes": int(event.get("requested_bytes", 0)),
            "returned_bytes": int(event.get("returned_bytes", 0)),
            "retry_number": int(event.get("retry_number", 0)),
            "short_read": bool(event.get("short_read", False)),
            "syscall_begin_ns": event.get("syscall_enter_monotonic_ns"),
            "syscall_end_ns": event.get("syscall_exit_monotonic_ns"),
            "error": event.get("error"),
        })
    result["physical_reads"] = reads
    result["active_reader_transitions"] = list(result.get("source_qd_timeline") or [])
    raw = result.get("actual_source") or {}
    result["qd_telemetry"] = {
        "max_achieved_qd": raw.get("max_actual_source_inflight"),
        "time_weighted_achieved_qd": raw.get("time_weighted_mean_qd"),
        "time_at_qd_ms": raw.get("time_at_qd_ms") or raw.get("milliseconds_at_qd"),
        "active_interval_start_ns": raw.get("source_active_interval_start_ns"),
        "active_interval_end_ns": raw.get("source_active_interval_end_ns"),
    }
    result["max_achieved_qd"] = result["qd_telemetry"]["max_achieved_qd"]
    result["time_weighted_achieved_qd"] = result["qd_telemetry"]["time_weighted_achieved_qd"]
    result["time_at_qd_ms"] = result["qd_telemetry"]["time_at_qd_ms"]
    requested = sum(item["requested_bytes"] for item in reads)
    returned = sum(item["returned_bytes"] for item in reads)
    result["byte_reconciliation"] = {
        "expected_payload_bytes": result.get("payload_bytes"),
        "requested_bytes": requested,
        "returned_bytes": returned,
        "read_count": len(reads),
        "returned_equals_expected": returned == int(result.get("payload_bytes") or 0),
        "offsets_recorded_per_physical_read": True,
    }
    by_id = {int(row.get("producer_id")): dict(row) for row in result.get("workers", [])}
    reads_by_worker: dict[int, list[dict[str, Any]]] = {}
    for read in reads:
        reads_by_worker.setdefault(int(read["worker_id"]), []).append(read)
    workers = []
    for region in result.get("regions", []):
        worker_id = int(region["producer_id"])
        row = by_id.get(worker_id, {})
        start = row.get("worker_started_ns")
        end = row.get("worker_terminated_ns")
        workers.append({
            "worker_id": worker_id,
            "region_id": int(region.get("region_id", worker_id)),
            "region_start": int(region["start"]),
            "region_end": int(region["end"]),
            "worker_started_ns": start,
            "worker_terminated_ns": end,
            "worker_wall_ms": (float(end - start) / 1_000_000.0) if start is not None and end is not None else None,
            "source_bytes": int(row.get("source_bytes", 0)),
            "source_requested_bytes": sum(item["requested_bytes"] for item in reads_by_worker.get(worker_id, [])),
            "source_read_count": int(row.get("source_read_count", 0)),
            "status": "ok" if row else "missing",
        })
    result["workers"] = workers
    path = Path(str(result.get("resolved_path", MODELS_ROOT)))
    result.update(_identity(path, result))
    result["provider_region"] = {
        "provider": (result.get("identity") or {}).get("provider"),
        "region": (result.get("identity") or {}).get("region"),
    }
    identity = result.setdefault("identity", {})
    if not identity.get("container_session_id"):
        identity["container_session_id"] = platform.node()
    result["container_session"] = {
        "session_id": identity.get("container_session_id"),
        "hostname": platform.node(),
        "single_use_container": True,
    }
    result["cpu_allocation"] = {
        **dict(result.get("cpu_allocation") or {}),
        "declared_modal_function_cpu": DECLARED_CPU,
        "declared_memory_mb": DECLARED_MEMORY_MB,
    }
    return result


@app.function(
    image=_image,
    cpu=DECLARED_CPU,
    memory=DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={MODELS_ROOT: _models_mount},
    env={
        "COMFYMODAL_C9_RECOVERY": "1",
        "COMFYMODAL_E04_DECLARED_CPU": str(DECLARED_CPU),
        "COMFYMODAL_V2_CPU_REQUEST": str(DECLARED_CPU),
        "COMFYMODAL_V2_MEMORY_REQUEST": str(DECLARED_MEMORY_MB),
        "COMFYMODAL_V2_MEMORY_MB": str(DECLARED_MEMORY_MB),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_c9_recovery(role: str, model_name: str, qd: int, attempt_id: str = "") -> dict[str, Any]:
    role = str(role).strip().lower()
    model_name = str(model_name).strip()
    qd = int(qd)
    if role not in SOURCE_ROLES:
        raise ValueError(f"unsupported_role:{role}")
    if qd not in SOURCE_QD_VALUES:
        raise ValueError(f"unsupported_qd:{qd}")
    if model_name != MODELS[role]:
        raise ValueError(f"unsupported_model:{role}:{model_name}")
    from comfymodal_runtime.source_ceiling_oracle import run_source_only

    result = run_source_only(
        role,
        model_name,
        qd=qd,
        block_bytes=SOURCE_BLOCK_BYTES,
        attempt_id=str(attempt_id),
    )
    result = _normalize_evidence(result, role, model_name, qd)
    fixed = result.get("fixed_config") or {}
    if fixed.get("source_block_bytes") != SOURCE_BLOCK_BYTES:
        raise RuntimeError("c9_block_bytes_not_enforced")
    return result
