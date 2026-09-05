"""Experiment 04 source ceiling oracle with a strict pure-source arm.

This module deliberately owns no model construction, ComfyUI execution, or
production loader state.  One call measures one checkpoint and one fixed arm.
"""

from __future__ import annotations

import hashlib
import concurrent.futures
import json
import os
import platform
import struct
import time
from pathlib import Path
from typing import Any, Mapping, cast

from .e27_source_mechanism import ActualSourceTelemetry
from .runtime_shape import runtime_shape_config


QD_BLOCK_BYTES = 256 * 1024 * 1024
QD_BLOCK_VALUES = tuple(value * 1024 * 1024 for value in (32, 64, 128, 256))
QD_VALUES = (1, 2, 4, 8)
SOURCE_ONLY_ARM = "source_only"
MODELS_ROOT = Path("/root/models")
QD_PRODUCERS = 4
QD_H2D_TARGET_BYTES = QD_BLOCK_BYTES
FASTSAFE_THREADS = 8
FASTSAFE_BBUF_KB = 512 * 1024
FASTSAFE_BLOCK_BYTES = {
    "clip": 64 * 1024 * 1024,
    "unet": QD_BLOCK_BYTES,
}
SOURCE_CAPACITY = 8
E04_DECLARED_MODAL_CPU = 4

# ``gpu_ready_dependency_controlling_source_slot_release`` is deliberately an
# absence proof: the pure-source arm must not have that dependency.  Keep it
# out of the positive proof aggregate so an expected ``False`` is not reported
# as a failed gate.
SOURCE_ONLY_POSITIVE_PROOF_KEYS = (
    "zero_cuda_h2d_submissions",
    "zero_cuda_transfer_events_on_measured_path",
    "no_h2d_dispatcher_participation",
    "source_workers_release_solely_from_source_completion",
    "source_workers_terminate_solely_from_source_completion",
    "source_qd_independent_of_h2d_or_staging_depth",
)
SOURCE_ONLY_ABSENCE_PROOF_KEYS = (
    "gpu_ready_dependency_controlling_source_slot_release",
)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _source_only_proof_all(proof: Mapping[str, Any]) -> bool:
    """Aggregate only positive pure-source predicates."""
    return all(proof.get(key) is True for key in SOURCE_ONLY_POSITIVE_PROOF_KEYS)


def _declared_modal_cpu() -> int:
    """Return the CPU declared on the dedicated E04 Modal function."""
    raw = os.environ.get("COMFYMODAL_E04_DECLARED_CPU", str(E04_DECLARED_MODAL_CPU))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("COMFYMODAL_E04_DECLARED_CPU must be an integer") from exc
    if value <= 0:
        raise ValueError("COMFYMODAL_E04_DECLARED_CPU must be positive")
    return value


def _identity() -> dict[str, Any]:
    try:
        shape = runtime_shape_config()
        cpu_request = int(shape.cpu_request)
        cpu_source = "runtime_shape_config.cpu_request"
        shape_fingerprint = shape.runtime_shape_fingerprint
    except Exception:
        # Preserve artifact creation if a malformed development environment is
        # present, while retaining the production identity key when available.
        try:
            cpu_request = int(os.environ.get("COMFYMODAL_V2_CPU_REQUEST", "0") or 0)
        except (TypeError, ValueError):
            cpu_request = 0
        cpu_source = "COMFYMODAL_V2_CPU_REQUEST"
        shape_fingerprint = None
    declared_modal_cpu = _declared_modal_cpu()
    allocation_match = declared_modal_cpu == cpu_request
    allocation_classification = "match" if allocation_match else "mismatch"
    return {
        "provider": os.environ.get("MODAL_CLOUD_PROVIDER", ""),
        "region": os.environ.get("MODAL_REGION", ""),
        "image_id": os.environ.get("MODAL_IMAGE_ID", ""),
        "container_session_id": (
            os.environ.get("CONTAINER_SESSION_ID", "")
            or os.environ.get("MODAL_TASK_ID", "")
        ),
        "hostname": platform.node(),
        "gpu": os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000"),
        "cpu": cpu_request,
        "cpu_request": cpu_request,
        "cpu_allocation": {
            "cpu_request": cpu_request,
            "declared_modal_function_cpu": declared_modal_cpu,
            "declared_modal_function_cpu_request": declared_modal_cpu,
            "observed_runtime_shape_cpu": cpu_request,
            "observed_runtime_shape_cpu_request": cpu_request,
            "identity_source": cpu_source,
            "runtime_shape_fingerprint": shape_fingerprint,
            "allocation_match": allocation_match,
            "allocation_match_classification": allocation_classification,
            "strict_allocation_match": allocation_match,
            "strict_allocation_classification": allocation_classification,
            "production_relevant": allocation_match,
            "production_relevance_classification": (
                "production_relevant"
                if allocation_match
                else "not_production_relevant_cpu_allocation_mismatch"
            ),
        },
        "cpu_allocation_match": allocation_match,
        "cpu_allocation_classification": allocation_classification,
    }


def _header(path: str) -> tuple[int, dict[str, Any], int]:
    with open(path, "rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError("safetensors_header_length_missing")
        header_length = struct.unpack("<Q", raw_length)[0]
        header = json.loads(handle.read(header_length))
    if not isinstance(header, dict):
        raise ValueError("safetensors_header_not_object")
    data_start = 8 + int(header_length)
    payload_bytes = os.path.getsize(path) - data_start
    return data_start, header, payload_bytes


def _source_regions(data_start: int, payload_bytes: int, qd: int) -> list[dict[str, int]]:
    """Return balanced, contiguous source ownership for the pure-source arm."""
    base, remainder = divmod(payload_bytes, qd)
    regions: list[dict[str, int]] = []
    cursor = data_start
    for producer_id in range(qd):
        length = base + (1 if producer_id < remainder else 0)
        regions.append({
            "producer_id": producer_id,
            "region_id": producer_id,
            "start": cursor,
            "end": cursor + length,
        })
        cursor += length
    return regions


def _physical_source_read(
    fd: int,
    target: bytearray,
    offset: int,
    telemetry: ActualSourceTelemetry,
    producer_id: int,
    retry_number: int,
) -> int:
    """Perform one physical positioned read and retain its exact byte counts."""
    requested = len(target)
    call = telemetry.syscall_enter(
        producer_id,
        offset,
        requested,
        retry_number=retry_number,
        region_id=producer_id,
    )
    try:
        preadv = cast(Any, getattr(os, "preadv", None))
        pread = cast(Any, getattr(os, "pread", None))
        if callable(preadv):
            value: Any = preadv(fd, [memoryview(target)], int(offset))
            returned = int(value)
        elif callable(pread):
            data: Any = pread(fd, requested, int(offset))
            returned = len(data)
            target[:returned] = data
        else:
            os.lseek(fd, int(offset), os.SEEK_SET)
            data = cast(Any, os.read(fd, requested))
            returned = len(data)
            target[:returned] = data
        telemetry.syscall_exit(call, returned)
        return returned
    except BaseException as exc:
        telemetry.syscall_exit(call, 0, error=exc)
        raise


def _read_source_region(
    path: str,
    region: Mapping[str, int],
    block_bytes: int,
    telemetry: ActualSourceTelemetry,
) -> dict[str, Any]:
    """Read one fixed region, retrying short reads without hiding any syscall."""
    producer_id = int(region["producer_id"])
    worker_started_ns = time.monotonic_ns()
    cursor = int(region["start"])
    end = int(region["end"])
    bytes_read = 0
    read_count = 0
    block_count = 0
    block_digests: list[dict[str, Any]] = []
    fd = os.open(path, os.O_RDONLY)
    try:
        while cursor < end:
            block_start = cursor
            block_end = min(end, cursor + block_bytes)
            block_digest = hashlib.sha256()
            block_bytes_read = 0
            retry_number = 0
            while cursor < block_end:
                requested = block_end - cursor
                target = bytearray(requested)
                returned = _physical_source_read(
                    fd, target, cursor, telemetry, producer_id, retry_number
                )
                if returned <= 0:
                    raise IOError(f"short_source_read:{cursor}:{requested}:{returned}")
                block_digest.update(memoryview(target)[:returned])
                cursor += returned
                bytes_read += returned
                block_bytes_read += returned
                read_count += 1
                retry_number += 1
            block_count += 1
            block_digests.append({
                "source_offset": block_start,
                "requested_bytes": block_end - block_start,
                "returned_bytes": block_bytes_read,
                "sha256": block_digest.hexdigest(),
            })
    finally:
        os.close(fd)
    source_completion_ns = time.monotonic_ns()
    worker_terminated_ns = time.monotonic_ns()
    return {
        "producer_id": producer_id,
        "region_start": int(region["start"]),
        "region_end": end,
        "source_bytes": bytes_read,
        "source_read_count": read_count,
        "source_block_count": block_count,
        "block_digests": block_digests,
        "worker_started_ns": worker_started_ns,
        "source_completion_ns": source_completion_ns,
        "worker_terminated_ns": worker_terminated_ns,
        "worker_wall_ms": (worker_terminated_ns - worker_started_ns) / 1_000_000.0,
        "worker_release_ns": source_completion_ns,
        "source_slot_release_ns": source_completion_ns,
        "release_reason": "source_completion",
        "termination_reason": "source_completion",
    }


def _coverage_from_events(
    events: list[Mapping[str, Any]], expected_start: int, expected_end: int
) -> dict[str, Any]:
    """Check exact source coverage from returned syscall ranges, not counters."""
    spans = sorted(
        (int(event["source_offset"]), int(event["source_offset"]) + int(event["returned_bytes"]))
        for event in events if int(event["returned_bytes"]) > 0
    )
    cursor = expected_start
    gaps = 0
    overlaps = 0
    returned = 0
    requested = 0
    for start, end in spans:
        returned += end - start
        if start < cursor:
            overlaps += 1
        elif start > cursor:
            gaps += 1
        cursor = max(cursor, end)
    requested = sum(int(event.get("requested_bytes", 0)) for event in events)
    if cursor < expected_end:
        gaps += 1
    expected = expected_end - expected_start
    return {
        "ok": returned == expected and cursor == expected_end and gaps == 0 and overlaps == 0,
        "expected_bytes": expected,
        "requested_bytes": requested,
        "returned_bytes": returned,
        "gap_count": gaps,
        "overlap_count": overlaps,
        "syscall_count": len(events),
    }


def _run_source_only(
    path: str,
    role: str,
    qd: int,
    block_bytes: int,
    *,
    source_capacity: int = SOURCE_CAPACITY,
) -> dict[str, Any]:
    """Read checkpoint bytes only; this arm intentionally has no torch/CUDA path."""
    data_start, header, payload_bytes = _header(path)
    if payload_bytes <= 0:
        raise ValueError("safetensors_payload_missing")
    if isinstance(source_capacity, bool) or not isinstance(source_capacity, int) or source_capacity < 1:
        raise ValueError("source_capacity must be a positive integer")
    regions = _source_regions(data_start, payload_bytes, qd)
    expected_ranges = [(row["start"], row["end"]) for row in regions]
    telemetry = ActualSourceTelemetry(
        arm=SOURCE_ONLY_ARM,
        producer_count=qd,
        regions=regions,
        expected_ranges=expected_ranges,
    )
    telemetry.mark_physical_syscall_provenance("source_ceiling_oracle._physical_source_read")
    started_ns = time.monotonic_ns()
    worker_rows: list[dict[str, Any]] = []
    worker_errors: list[str] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=qd, thread_name_prefix="source-only"
        ) as executor:
            futures = [
                executor.submit(_read_source_region, path, region, block_bytes, telemetry)
                for region in regions
            ]
            for future in futures:
                try:
                    worker_rows.append(future.result())
                except Exception as exc:
                    worker_errors.append(f"{type(exc).__name__}:{exc}")
    finally:
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0

    raw = telemetry.report()
    events = list(raw.get("actual_source_events") or [])
    source_wall_ms = raw.get("SOURCE_TOTAL_WALL_MS")
    if source_wall_ms is None or float(source_wall_ms) <= 0:
        source_wall_ms = elapsed_ms
    if float(source_wall_ms) <= 0:
        source_wall_ms = 0.000001
    coverage = _coverage_from_events(events, data_start, data_start + payload_bytes)
    source_bytes = sum(int(event.get("returned_bytes", 0)) for event in events)
    source_requested_bytes = sum(int(event.get("requested_bytes", 0)) for event in events)
    effective_gbps = (
        source_bytes / (float(source_wall_ms) * 1_000_000.0)
        if source_wall_ms and float(source_wall_ms) > 0 else None
    )
    topology = {
        "producer_count": qd,
        "fixed_contiguous_regions": True,
        "fixed_ownership": all(
            int(event.get("producer_id", -1)) < qd for event in events
        ),
        "monotonic_reads": all(
            all(
                int(left.get("source_offset", 0)) <= int(right.get("source_offset", 0))
                for left, right in zip(
                    [event for event in events if int(event.get("producer_id", -1)) == producer],
                    [event for event in events if int(event.get("producer_id", -1)) == producer][1:],
                )
            )
            for producer in range(qd)
        ),
        "coverage_exact": coverage["ok"],
        "regions": regions,
    }
    fixed = {
        "execution_arm": SOURCE_ONLY_ARM,
        "configured_qd": qd,
        "configured_source_qd": qd,
        "configured_source_capacity": source_capacity,
        "source_capacity_semantics": "buffering_work_capacity_only",
        "producer_count": qd,
        "source_block_bytes": block_bytes,
        "h2d_target_bytes": None,
        "aggregation_enabled": False,
        "cuda_used": False,
        "h2d_used": False,
        "model_construction": False,
        "h2d_submission_count": 0,
        "h2d_submit_count": 0,
        "h2d_events": [],
        "cuda_transfer_events": [],
        "h2d_transfer_events": [],
        "cuda_transfer_event_count": 0,
        "h2d_dispatcher_participation": False,
        "h2d_dispatcher_started": False,
        "no_h2d_dispatcher_participation": True,
    }
    source_qd_timeline = list(raw.get("actual_source_transitions") or [])
    proof: dict[str, Any] = {
        "zero_cuda_h2d_submissions": True,
        "zero_cuda_transfer_events_on_measured_path": True,
        "no_h2d_dispatcher_participation": True,
        "gpu_ready_dependency_controlling_source_slot_release": False,
        "source_workers_release_solely_from_source_completion": all(
            row.get("release_reason") == "source_completion" for row in worker_rows
        ) and len(worker_rows) == qd and not worker_errors,
        "source_workers_terminate_solely_from_source_completion": all(
            row.get("termination_reason") == "source_completion"
            and row.get("worker_terminated_ns", 0) >= row.get("source_completion_ns", 0)
            for row in worker_rows
        ) and len(worker_rows) == qd and not worker_errors,
        "source_qd_independent_of_h2d_or_staging_depth": True,
    }
    proof["absence_predicates"] = {
        f"no_{key}": not proof[key] for key in SOURCE_ONLY_ABSENCE_PROOF_KEYS
    }
    proof["failed_positive_predicates"] = [
        key for key in SOURCE_ONLY_POSITIVE_PROOF_KEYS if proof.get(key) is not True
    ]
    proof["all"] = _source_only_proof_all(proof)
    wait_dimensions = {
        "source_capacity_wait_ms": 0.0,
        "source_capacity_wait_count": 0,
        "ready_queue_wait_ms": 0.0,
        "ready_queue_wait_count": 0,
        "h2d_capacity_wait_ms": 0.0,
        "h2d_capacity_wait_count": 0,
        "gpu_ready_wait_ms": 0.0,
        "gpu_ready_wait_count": 0,
    }
    return {
        "status": "ok" if coverage["ok"] and not worker_errors and proof["all"] else "error",
        "error": (
            ";".join(worker_errors)
            if worker_errors
            else "source_only_proof_failed:" + ",".join(proof["failed_positive_predicates"])
            if not proof["all"]
            else None
        ),
        "arm": SOURCE_ONLY_ARM,
        "execution_arm": SOURCE_ONLY_ARM,
        "source_only": True,
        "model_construction": False,
        "torch_imported": False,
        "cuda_used": False,
        "h2d_used": False,
        "FILE_TO_CUDA_WALL_MS": None,
        "SOURCE_WALL_MS": source_wall_ms,
        "source_wall_ms": source_wall_ms,
        "effective_gbps": effective_gbps,
        "effective_GBps": effective_gbps,
        "source_effective_gbps": effective_gbps,
        "source_bytes": source_bytes,
        "source_read_count": len(events),
        "source_requested_bytes": source_requested_bytes,
        "source_returned_bytes": source_bytes,
        "SOURCE_SYSCALL_UNION_BUSY_MS": raw.get("SOURCE_SYSCALL_UNION_BUSY_MS"),
        "max_actual_source_inflight": raw.get("max_actual_source_inflight"),
        "achieved_mean_qd": raw.get("time_weighted_mean_qd"),
        "achieved_source_qd_mean": raw.get("time_weighted_mean_qd"),
        "achieved_source_qd_max": raw.get("max_actual_source_inflight"),
        "source_qd_timeline": source_qd_timeline,
        "achieved_source_qd_timeline": source_qd_timeline,
        "configured_source_qd": qd,
        "configured_source_capacity": source_capacity,
        "source_capacity_semantics": "buffering_work_capacity_only",
        "wait_dimensions": wait_dimensions,
        "source_only_proof": proof,
        "source_workers_release_solely_from_source_completion": proof[
            "source_workers_release_solely_from_source_completion"
        ],
        "source_workers_terminate_solely_from_source_completion": proof[
            "source_workers_terminate_solely_from_source_completion"
        ],
        "h2d_submission_count": 0,
        "h2d_submit_count": 0,
        "h2d_events": [],
        "cuda_transfer_events": [],
        "h2d_transfer_events": [],
        "h2d_transfer_event_count": 0,
        "cuda_transfer_event_count": 0,
        "h2d_dispatcher_participation": False,
        "h2d_dispatcher_started": False,
        "no_h2d_dispatcher_participation": True,
        "source_slot_release_dependency": "source_completion",
        "source_worker_release_trigger": "source_completion",
        "source_worker_termination_trigger": "source_completion",
        "gpu_ready_dependency": False,
        "gpu_ready_dependency_controlling_source_slot_release": False,
        "timing_scope": "first physical source syscall -> final physical source syscall; payload only",
        "file_size_bytes": os.path.getsize(path),
        "data_start": data_start,
        "payload_bytes": payload_bytes,
        "header_tensor_count": len([key for key in header if key != "__metadata__"]),
        "fixed_config": fixed,
        "fixed_config_expected": dict(fixed),
        "byte_validation": {
            **coverage,
            "source_ranges_exact": coverage["ok"],
            "requested_bytes": source_requested_bytes,
            "returned_bytes": source_bytes,
        },
        "coverage": coverage,
        "regions": regions,
        "workers": sorted(worker_rows, key=lambda row: row["producer_id"]),
        "worker_errors": worker_errors,
        "physical_syscall_provenance": raw.get("physical_syscall_provenance"),
        "physical_syscall_telemetry": events,
        "actual_source": raw,
        "transport_stats": {
            "execution_arm": SOURCE_ONLY_ARM,
            "configured_qd": qd,
            "producer_count": qd,
            "source_block_bytes": block_bytes,
            "source_bytes": source_bytes,
            "source_read_count": len(events),
            "source_requested_bytes": source_requested_bytes,
            "source_returned_bytes": source_bytes,
            "configured_source_qd": qd,
            "configured_source_capacity": source_capacity,
            "source_qd_timeline": source_qd_timeline,
            "wait_dimensions": wait_dimensions,
            "source_only_proof": proof,
            "h2d_submission_count": 0,
            "h2d_transfer_event_count": 0,
            "cuda_transfer_event_count": 0,
            "h2d_dispatcher_participation": False,
            "no_h2d_dispatcher_participation": True,
            "source_wall_ms": source_wall_ms,
            "effective_gbps": effective_gbps,
            "h2d_used": False,
            "cuda_used": False,
            "physical_syscall_provenance": raw.get("physical_syscall_provenance"),
            "physical_syscall_telemetry": events,
            "topology": topology,
        },
        "metrics": {
            "SOURCE_WALL_MS": source_wall_ms,
            "source_wall_ms": source_wall_ms,
            "effective_gbps": effective_gbps,
            "effective_GBps": effective_gbps,
            "source_bytes": source_bytes,
            "source_read_count": len(events),
            "H2D_WALL_MS": None,
            "FILE_TO_CUDA_WALL_MS": None,
            "cuda_used": False,
            "h2d_used": False,
        },
        "E27_SOURCE_MECHANISM_PROVEN": "NO",
        "e27_proof_classification": "proof-NO",
        "e27_source_mechanism_line": "E27_SOURCE_MECHANISM_PROVEN=NO",
        "e27_source_mechanism_failed_predicates": ["source_only_no_h2d_mechanism"],
        "e27_source_mechanism_evaluation": {
            "proven": False,
            "emitted_line": "E27_SOURCE_MECHANISM_PROVEN=NO",
            "E27_SOURCE_MECHANISM_PROVEN": "NO",
            "predicates": {"source_only_no_h2d_mechanism": False},
            "failed_predicates": ["source_only_no_h2d_mechanism"],
            "classification": "proof-NO",
        },
    }


def _sample_keys(header: Mapping[str, Any]) -> list[str]:
    keys = [str(key) for key in header if key != "__metadata__"]
    if len(keys) <= 4:
        return keys
    return list(dict.fromkeys(keys[:2] + keys[-2:]))


def _source_bytes(path: str, start: int, length: int) -> bytes:
    with open(path, "rb") as handle:
        handle.seek(int(start))
        data = handle.read(int(length))
    if len(data) != int(length):
        raise ValueError(f"short_source_sample:{len(data)}:{length}")
    return data


def _tensor_bytes(tensor: Any, torch: Any) -> bytes:
    # Byte views preserve BF16/F16 bit patterns; converting through float would
    # make a validity check compare values rather than the source payload.
    raw = tensor.detach().contiguous().view(torch.uint8).cpu()
    return raw.numpy().tobytes()


def _validate_samples(path: str, data_start: int, header: Mapping[str, Any], tensors: Mapping[str, Any], torch: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    all_ok = True
    for key in _sample_keys(header):
        info = header.get(key) or {}
        offsets = info.get("data_offsets") or []
        if len(offsets) != 2:
            checks.append({"key": key, "ok": False, "reason": "invalid_data_offsets"})
            all_ok = False
            continue
        start, end = int(offsets[0]), int(offsets[1])
        source = _source_bytes(path, data_start + start, end - start)
        tensor = tensors.get(key)
        if tensor is None:
            checks.append({"key": key, "ok": False, "reason": "missing_tensor"})
            all_ok = False
            continue
        device = _tensor_bytes(tensor, torch)
        ok = source == device
        checks.append({
            "key": key,
            "bytes": len(source),
            "source_sha16": hashlib.sha256(source).hexdigest()[:16],
            "device_sha16": hashlib.sha256(device).hexdigest()[:16],
            "ok": ok,
        })
        all_ok = all_ok and ok
    return {"ok": all_ok, "checks": checks}


def _run_qd(path: str, role: str, qd: int, block_bytes: int) -> dict[str, Any]:
    import torch

    from .golden_qd_transport import GoldenTransferResources
    from .golden_serial import read_file_qd_gpu

    # static_e27 intentionally requires the request-owned resource arena. Keep
    # eight logical slots while varying the per-slot source/H2D block size.
    resources = GoldenTransferResources.create(
        device="cuda:0",
        slot_count=8,
        slot_bytes=block_bytes,
    )
    owner = None
    try:
        result = read_file_qd_gpu(
            path,
            role=role,
            device="cuda:0",
            qd=qd,
            block_bytes=block_bytes,
            diagnostics=True,
            transport_arm="static_e27",
            transport_resources=resources,
        )
        owner = result.get("owner")
        stats = dict(result.get("stats") or {})
        tensors = result.get("sd") or {}
        data_start, header, payload_bytes = _header(path)
        samples = _validate_samples(path, data_start, header, tensors, torch)
        actual = stats.get("actual_source") or stats.get("actual_source_telemetry") or {}
        timing_ms = actual.get("SOURCE_TO_GPU_READY_MS")
        metrics = {
            "SOURCE_WALL_MS": actual.get("SOURCE_TOTAL_WALL_MS"),
            "FILE_TO_CUDA_WALL_MS": timing_ms,
            "source_bytes": stats.get("source_bytes") or stats.get("bytes_read"),
            "source_read_count": stats.get("source_read_count"),
            "achieved_mean_qd": actual.get("time_weighted_mean_qd"),
            "achieved_max_qd": actual.get("max_actual_source_inflight"),
            "syscall_union_ms": actual.get("SOURCE_SYSCALL_UNION_BUSY_MS"),
            "H2D_WALL_MS": actual.get("H2D_TOTAL_WALL_MS"),
            "true_gpu_active_copy_ms": stats.get("GPU_COPY_ACTIVE_UNION_MS"),
            "gpu_stream_span_ms": stats.get("GPU_COPY_STREAM_SPAN_MS"),
            "gpu_idle_ms": stats.get("GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS"),
            "fallback": stats.get("fallback"),
            "proof": {
                "E27_SOURCE_MECHANISM_PROVEN": stats.get("E27_SOURCE_MECHANISM_PROVEN"),
                "e27_source_mechanism_line": stats.get("e27_source_mechanism_line"),
                "e27_source_mechanism_failed_predicates": stats.get("e27_source_mechanism_failed_predicates"),
            },
            "provider": stats.get("provider"),
            "region": stats.get("region"),
            "block_bytes": block_bytes,
            "nominal_outstanding_source_bytes": block_bytes * qd,
        }
        fixed = {
            "execution_arm": stats.get("execution_arm"),
            "configured_qd": stats.get("configured_qd"),
            "producer_count": len(stats.get("producer_ids") or []),
            "source_block_bytes": stats.get("source_block_bytes"),
            "h2d_target_bytes": stats.get("h2d_target_bytes"),
            "aggregation_enabled": stats.get("aggregation_enabled"),
            "physical_syscall_provenance": actual.get("physical_syscall_provenance"),
            "source_mechanism_proven": stats.get("E27_SOURCE_MECHANISM_PROVEN"),
        }
        expected = {
            "execution_arm": "static_e27",
            "configured_qd": qd,
            "producer_count": qd,
            "source_block_bytes": block_bytes,
            "h2d_target_bytes": block_bytes,
            "aggregation_enabled": False,
        }
        fixed_ok = all(fixed.get(key) == value for key, value in expected.items())
        if not timing_ms or not fixed_ok or not samples["ok"]:
            raise RuntimeError(
                f"qd_oracle_gate_failed:fixed={fixed_ok}:timing={timing_ms is not None}:samples={samples['ok']}"
            )
        return {
            "status": "ok",
            "arm": f"qd{qd}",
            "FILE_TO_CUDA_WALL_MS": float(timing_ms),
            "timing_scope": (
                "first physical source syscall -> final required H2D event completion; "
                "header/layout/allocation excluded"
            ),
            "file_size_bytes": os.path.getsize(path),
            "payload_bytes": payload_bytes,
            "fixed_config": fixed,
            "fixed_config_expected": expected,
            "byte_validation": samples,
            "metrics": metrics,
            "transport_stats": _json_safe(stats),
        }
    finally:
        if owner is not None:
            owner.close()
        resources.close()


def _run_fastsafe(path: str, role: str) -> dict[str, Any]:
    import torch
    from fastsafetensors import SafeTensorsFileLoader

    data_start, header, payload_bytes = _header(path)
    device = "cuda:0"
    block_bytes = FASTSAFE_BLOCK_BYTES[role]
    loader = SafeTensorsFileLoader(
        None,
        device=device,
        max_threads=FASTSAFE_THREADS,
        bbuf_size_kb=FASTSAFE_BBUF_KB,
        nogds=True,
        disable_cache=True,
    )
    fb = None
    try:
        loader.add_filenames({0: [str(path)]})
        started_ns = time.perf_counter_ns()
        fb = loader.copy_files_to_device(
            use_buf_register=False,
            max_copy_block_size=block_bytes,
        )
        # copy_files_to_device may enqueue asynchronous work.  The oracle's
        # ready boundary is after all destination bytes are consumable.
        torch.cuda.synchronize(device)
        ready_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
        keys = list(loader.get_keys())
        tensors = {key: fb.get_tensor(key) for key in keys}
        samples = _validate_samples(path, data_start, header, tensors, torch)
        fixed = {
            "loader": "fastsafetensors.SafeTensorsFileLoader",
            "threads": FASTSAFE_THREADS,
            "bbuf_size_kb": FASTSAFE_BBUF_KB,
            "nogds": True,
            "use_buf_register": False,
            "disable_cache": True,
            "max_copy_block_size": block_bytes,
        }
        expected = dict(fixed)
        if not samples["ok"]:
            raise RuntimeError("fastsafe_oracle_byte_validation_failed")
        first_key = keys[0] if keys else ""
        first_tensor = tensors.get(first_key)
        return {
            "status": "ok",
            "arm": "fastsafe",
            "FILE_TO_CUDA_WALL_MS": round(ready_ms, 4),
            "timing_scope": (
                "copy_files_to_device entry -> required torch.cuda.synchronize return; "
                "header/add_filenames and post-ready validation excluded"
            ),
            "file_size_bytes": os.path.getsize(path),
            "payload_bytes": payload_bytes,
            "tensor_count": len(keys),
            "fixed_config": fixed,
            "fixed_config_expected": expected,
            "byte_validation": samples,
            "ownership": {
                "first_key": first_key,
                "first_key_data_ptr": int(first_tensor.data_ptr()) if first_tensor is not None else None,
                "device": str(first_tensor.device) if first_tensor is not None else None,
            },
            "model_construction": False,
        }
    finally:
        try:
            loader.close()
        finally:
            if fb is not None:
                fb.close()


def run_source_ceiling_oracle(
    role: str,
    model_name: str,
    arm: str,
    attempt_id: str = "",
    qd: int = 4,
    block_bytes: int = QD_BLOCK_BYTES,
    source_capacity: int = SOURCE_CAPACITY,
) -> dict[str, Any]:
    """Measure one fixed arm/model and return JSON-safe evidence."""
    started_ns = time.perf_counter_ns()
    role = str(role).strip().lower()
    model_name = str(model_name).strip()
    arm = str(arm).strip().lower()
    result: dict[str, Any] = {
        "probe": "exp04_source_ceiling_oracle",
        "attempt_id": str(attempt_id),
        "role": role,
        "model_name": model_name,
        "arm": arm,
        "identity": _identity(),
        "status": "error",
        "model_construction": False,
    }
    if arm == SOURCE_ONLY_ARM:
        result["identity"]["gpu"] = None
        result["identity"]["accelerator"] = "none"
    try:
        if role not in FASTSAFE_BLOCK_BYTES:
            raise ValueError(f"unsupported_role:{role}")
        if block_bytes not in QD_BLOCK_VALUES:
            raise ValueError(f"unsupported_block_bytes:{block_bytes}")
        if arm not in {SOURCE_ONLY_ARM, "fastsafe", *(f"qd{value}" for value in QD_VALUES)}:
            raise ValueError(f"unsupported_arm:{arm}")
        if (arm.startswith("qd") or arm == SOURCE_ONLY_ARM) and qd not in QD_VALUES:
            raise ValueError(f"unsupported_qd:{qd}")
        if not model_name or Path(model_name).name != model_name:
            raise ValueError("model_name_must_be_a_basename")
        folder = "text_encoders" if role == "clip" else "diffusion_models"
        path = MODELS_ROOT / folder / model_name
        if not path.is_file():
            raise FileNotFoundError(str(path))
        result["resolved_path"] = str(path)
        result["path_resolution"] = "fixed_read_only_models_mount"
        result["snapshot_capture"] = {"applicable": False, "counted": False}
        if arm == SOURCE_ONLY_ARM:
            evidence = _run_source_only(
                str(path), role, int(qd), int(block_bytes), source_capacity=int(source_capacity)
            )
        elif arm.startswith("qd"):
            evidence = _run_qd(str(path), role, int(arm[2:]), int(block_bytes))
        else:
            evidence = _run_fastsafe(str(path), role)
        result.update(evidence)
        result["cpu_request"] = result["identity"].get("cpu_request")
        result["cpu_allocation"] = dict(result["identity"].get("cpu_allocation") or {})
        if isinstance(result.get("metrics"), dict):
            result["metrics"].update({
                "provider": result["identity"].get("provider"),
                "region": result["identity"].get("region"),
            })
        if evidence.get("status") == "ok":
            result["status"] = "ok"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:300]}"
    result["oracle_wall_ms"] = round((time.perf_counter_ns() - started_ns) / 1_000_000.0, 4)
    return _json_safe(result)


def run_source_only(
    role: str,
    model_name: str,
    qd: int = 4,
    block_bytes: int = QD_BLOCK_BYTES,
    attempt_id: str = "",
    source_capacity: int = SOURCE_CAPACITY,
) -> dict[str, Any]:
    """Public pure-source API; the historical integrated arms are unchanged."""
    return run_source_ceiling_oracle(
        role, model_name, SOURCE_ONLY_ARM, attempt_id, qd, block_bytes, source_capacity
    )
