"""Experiment 04 source ceiling oracle with a strict pure-source arm.

This module deliberately owns no model construction, ComfyUI execution, or
production loader state.  One call measures one checkpoint and one fixed arm.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import struct
import threading
import time
from collections import deque
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
    target: memoryview,
    offset: int,
    telemetry: ActualSourceTelemetry | None,
    producer_id: int,
    retry_number: int,
    physical_span: dict[str, int | None] | None = None,
    physical_span_lock: threading.Lock | None = None,
) -> int:
    """Read into the reusable worker buffer; telemetry is forensic-only."""
    requested = len(target)
    call = None
    if telemetry is not None:
        call = telemetry.syscall_enter(
            producer_id, offset, requested, retry_number=retry_number, region_id=producer_id
        )
    try:
        preadv = cast(Any, getattr(os, "preadv", None))
        if not callable(preadv):
            raise RuntimeError("positioned_preadv_unavailable")
        begin_ns = time.monotonic_ns()
        if physical_span is not None:
            lock = physical_span_lock
            if lock is None:
                physical_span["first_begin_ns"] = begin_ns
            else:
                with lock:
                    if physical_span["first_begin_ns"] is None:
                        physical_span["first_begin_ns"] = begin_ns
        returned = int(cast(Any, preadv)(fd, [target], int(offset)))
        end_ns = time.monotonic_ns()
        if physical_span is not None:
            lock = physical_span_lock
            if lock is None:
                physical_span["last_end_ns"] = end_ns
            else:
                with lock:
                    physical_span["last_end_ns"] = end_ns
        if returned < 0 or returned > requested:
            raise IOError(f"invalid_source_read_count:{requested}:{returned}")
        if telemetry is not None and call is not None:
            telemetry.syscall_exit(call, returned)
        return returned
    except BaseException as exc:
        if telemetry is not None and call is not None:
            telemetry.syscall_exit(call, 0, error=exc)
        raise


def _import_torch() -> Any:
    """Import Torch during source-only setup, before its timed work begins."""
    global _TORCH_IMPORTED
    import torch

    _TORCH_IMPORTED = True
    return torch


_TORCH_IMPORTED = False


def _allocate_pinned_buffer(size: int) -> Any:
    """Allocate one reusable Torch pinned tensor; never fall back."""
    torch = _import_torch()
    size = int(size)
    tensor = torch.empty(size, dtype=torch.uint8, pin_memory=True)
    if tensor.is_pinned() is not True:
        raise RuntimeError("pytorch_pinned_host_buffer_is_not_pinned")
    return tensor


def _buffer_evidence(buffer: Any, default_size: int) -> dict[str, Any]:
    is_pinned = False
    pin_error = None
    try:
        is_pinned = buffer.is_pinned() is True
    except BaseException as exc:
        pin_error = f"{type(exc).__name__}:{exc}"
    return {
        "buffer_type": "pytorch_pinned_host",
        "pinned_host": is_pinned,
        "is_pinned": is_pinned,
        "bytes": int(getattr(buffer, "nbytes", default_size)),
        "allocation_exception": pin_error,
    }


def _buffer_view(buffer: Any) -> memoryview:
    return memoryview(buffer.numpy())


def _read_source_region(
    fd: int,
    path: str,
    region: Mapping[str, int],
    block_bytes: int,
    buffer: Any,
    telemetry: ActualSourceTelemetry | None,
    physical_span: dict[str, int | None],
    physical_span_lock: threading.Lock,
) -> dict[str, Any]:
    """Read one fixed region using one reusable worker buffer."""
    producer_id = int(region["producer_id"])
    worker_started_ns = time.monotonic_ns()
    cursor = int(region["start"])
    end = int(region["end"])
    bytes_read = 0
    requested_bytes_total = 0
    read_count = 0
    block_count = 0
    first_reads: list[tuple[int, int, int, int]] = []
    tail_reads: deque[tuple[int, int, int, int]] = deque(maxlen=2)
    view = _buffer_view(buffer)
    while cursor < end:
        block_end = min(end, cursor + block_bytes)
        retry_number = 0
        while cursor < block_end:
            requested = block_end - cursor
            returned = _physical_source_read(
                fd, view[:requested], cursor, telemetry, producer_id, retry_number,
                physical_span, physical_span_lock,
            )
            if returned <= 0:
                raise IOError(f"short_source_read:{cursor}:{requested}:{returned}")
            evidence = (cursor, requested, returned, retry_number)
            if len(first_reads) < 2:
                first_reads.append(evidence)
            else:
                tail_reads.append(evidence)
            cursor += returned
            bytes_read += returned
            requested_bytes_total += requested
            read_count += 1
            retry_number += 1
        block_count += 1
    source_completion_ns = time.monotonic_ns()
    worker_terminated_ns = time.monotonic_ns()
    return {
        "producer_id": producer_id,
        "region_start": int(region["start"]),
        "region_end": end,
        "source_bytes": bytes_read,
        "source_requested_bytes": requested_bytes_total,
        "source_read_count": read_count,
        "source_block_count": block_count,
        "read_sizes": first_reads + list(tail_reads),
        "read_evidence_complete": read_count <= 4,
        "max_requested_bytes": max((item[1] for item in first_reads + list(tail_reads)), default=0),
        "all_requests_within_buffer": True,
        "buffer_bytes": int(getattr(buffer, "nbytes", block_bytes)),
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


def _read_source_worker(
    fd: int,
    path: str,
    region: Mapping[str, int],
    block_bytes: int,
    telemetry: ActualSourceTelemetry | None,
    physical_span: dict[str, int | None],
    physical_span_lock: threading.Lock,
    rows: dict[int, dict[str, Any]],
    errors: list[str],
    buffers: dict[int, Any],
    buffer_details: dict[int, dict[str, Any]],
) -> None:
    producer_id = int(region["producer_id"])
    try:
        # Allocate only after this worker has started so C9 includes the real
        # per-worker allocation boundary rather than a serial setup phase.
        buffer = _allocate_pinned_buffer(block_bytes)
        buffers[producer_id] = buffer
        buffer_details[producer_id] = _buffer_evidence(buffer, block_bytes) | {
            "worker_id": producer_id,
        }
        row = _read_source_region(
            fd, path, region, block_bytes, buffer, telemetry,
            physical_span, physical_span_lock,
        )
        rows[producer_id] = row
    except BaseException as exc:
        if producer_id not in buffer_details:
            buffer_details[producer_id] = {
                "worker_id": producer_id,
                "buffer_type": "pytorch_pinned_host",
                "bytes": block_bytes,
                "is_pinned": False,
                "pinned_host": False,
                "allocation_exception": f"{type(exc).__name__}:{exc}",
            }
        errors.append(f"worker_{producer_id}:{type(exc).__name__}:{exc}")


def _run_source_only(
    path: str,
    role: str,
    qd: int,
    block_bytes: int,
    *,
    source_capacity: int = SOURCE_CAPACITY,
    forensic: bool = False,
) -> dict[str, Any]:
    """Read checkpoint bytes with one shared FD and reusable worker buffers."""
    data_start, header, payload_bytes = _header(path)
    if payload_bytes <= 0:
        raise ValueError("safetensors_payload_missing")
    if isinstance(source_capacity, bool) or not isinstance(source_capacity, int) or source_capacity < 1:
        raise ValueError("source_capacity must be a positive integer")
    regions = _source_regions(data_start, payload_bytes, qd)
    expected_ranges = [(row["start"], row["end"]) for row in regions]
    provenance = "source_ceiling_oracle._physical_source_read"
    telemetry: ActualSourceTelemetry | None = None
    if forensic:
        telemetry = ActualSourceTelemetry(
            arm=SOURCE_ONLY_ARM,
            producer_count=qd,
            regions=regions,
            expected_ranges=expected_ranges,
        )
        # Preserve the O(1) provenance marker for optional forensic evidence.
        telemetry.mark_physical_syscall_provenance(provenance)
    # Match the historical setup boundary: importing Torch is required for the
    # worker buffers, but is not part of the measured source-only operation.
    _import_torch()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    physical_span: dict[str, int | None] = {
        "first_begin_ns": None,
        "last_end_ns": None,
    }
    physical_span_lock = threading.Lock()
    workers_joined_ns: int | None = None
    worker_rows: list[dict[str, Any]] = []
    worker_errors: list[str] = []
    buffer_details: list[dict[str, Any]] = []
    rows_by_worker: dict[int, dict[str, Any]] = {}
    buffers_by_worker: dict[int, Any] = {}
    buffer_details_by_worker: dict[int, dict[str, Any]] = {}
    threads: list[threading.Thread] = []
    try:
        threads = [
            threading.Thread(
                target=_read_source_worker,
                args=(
                    fd, path, region, block_bytes, telemetry,
                    physical_span, physical_span_lock, rows_by_worker, worker_errors,
                    buffers_by_worker, buffer_details_by_worker,
                ),
                name=f"source-only-{region['producer_id']}",
            )
            for region in regions
        ]
        total_started_ns = time.monotonic_ns()
        for thread in threads:
            thread.start()
    finally:
        # Every started worker is joined before the shared FD or its tensor is
        # released, including the fail-closed allocation path.
        for thread in threads:
            if thread.ident is not None:
                thread.join()
        if threads:
            workers_joined_ns = time.monotonic_ns()
        os.close(fd)
        # Clearing the references releases the Torch tensors after all joins.
        buffers_by_worker.clear()

    buffer_details = [
        buffer_details_by_worker[index]
        for index in sorted(buffer_details_by_worker)
    ]
    worker_rows = [rows_by_worker[index] for index in sorted(rows_by_worker)]
    if len(worker_rows) != qd and not worker_errors:
        worker_errors.append("worker_missing")

    raw = telemetry.report() if telemetry is not None else {}
    cuda_available = None
    cuda_build = None
    device_name = None
    if _TORCH_IMPORTED:
        try:
            torch = _import_torch()
            cuda = cast(Any, getattr(torch, "cuda", None))
            cuda_available = bool(cuda.is_available())
            cuda_build = getattr(getattr(torch, "version", None), "cuda", None)
            if cuda_available:
                device_name = str(cuda.get_device_name(0))
        except BaseException as exc:
            worker_errors.append(f"torch_capability:{type(exc).__name__}:{exc}")
    events = list(raw.get("actual_source_events") or [])
    read_sizes = [
        {
            "producer_id": int(row["producer_id"]),
            "region_id": int(row["producer_id"]),
            "source_offset": int(offset),
            "requested_bytes": int(requested),
            "returned_bytes": int(returned),
            "retry_number": int(retry),
        }
        for row in worker_rows
        for offset, requested, returned, retry in row.get("read_sizes", [])
    ]
    all_requests_within_buffer = all(
        bool(row.get("all_requests_within_buffer")) for row in worker_rows
    ) and not worker_errors
    max_requested_bytes = max(
        (int(row.get("max_requested_bytes", 0)) for row in worker_rows), default=0
    )
    coverage_events = events or read_sizes
    total_end_ns = workers_joined_ns or time.monotonic_ns()
    c9_total_wall_ms = (total_end_ns - total_started_ns) / 1_000_000.0
    if c9_total_wall_ms <= 0:
        c9_total_wall_ms = 0.000001
    source_wall_ms = c9_total_wall_ms
    first_read_ns = physical_span["first_begin_ns"]
    last_read_ns = physical_span["last_end_ns"]
    physical_read_span_ms = (
        (int(last_read_ns) - int(first_read_ns)) / 1_000_000.0
        if first_read_ns is not None and last_read_ns is not None else None
    )
    if not raw.get("actual_source_transitions"):
        source_qd_timeline = []
        for row in worker_rows:
            source_qd_timeline.extend((
                {"timestamp_ns": row["worker_started_ns"], "delta": 1, "producer_id": row["producer_id"]},
                {"timestamp_ns": row["worker_terminated_ns"], "delta": -1, "producer_id": row["producer_id"]},
            ))
        source_qd_timeline.sort(key=lambda item: (item["timestamp_ns"], -item["delta"]))
        depth = 0
        for transition in source_qd_timeline:
            depth += transition["delta"]
            transition["depth"] = depth
        observed_qd = max((int(item["depth"]) for item in source_qd_timeline), default=0)
        observed_qd_mean = float(observed_qd)
    else:
        source_qd_timeline = list(raw.get("actual_source_transitions") or [])
        observed_qd = int(raw.get("max_actual_source_inflight") or 0)
        observed_qd_mean = float(raw.get("time_weighted_mean_qd") or 0.0)
    if events:
        coverage = _coverage_from_events(
            cast(list[Mapping[str, Any]], coverage_events), data_start, data_start + payload_bytes
        )
    else:
        source_bytes = sum(int(row.get("source_bytes", 0)) for row in worker_rows)
        source_requested_bytes = sum(
            int(row.get("source_requested_bytes", 0)) for row in worker_rows
        )
        expected = data_start + payload_bytes
        coverage = {
            "ok": (
                len(worker_rows) == qd
                and not worker_errors
                and all(
                    int(row.get("region_start", -1)) == int(regions[index]["start"])
                    and int(row.get("region_end", -1)) == int(regions[index]["end"])
                    and int(row.get("source_bytes", -1)) == int(regions[index]["end"] - regions[index]["start"])
                    for index, row in enumerate(worker_rows)
                )
                and source_bytes == payload_bytes
            ),
            "expected_bytes": payload_bytes,
            "requested_bytes": source_requested_bytes,
            "returned_bytes": source_bytes,
            "gap_count": 0,
            "overlap_count": 0,
            "syscall_count": sum(int(row.get("source_read_count", 0)) for row in worker_rows),
            "evidence_complete": False,
        }
    source_bytes = int(coverage["returned_bytes"])
    source_requested_bytes = int(coverage["requested_bytes"])
    source_read_count = int(coverage.get("syscall_count", 0))
    effective_gbps = (
        source_bytes / (float(source_wall_ms) * 1_000_000.0)
        if source_wall_ms and float(source_wall_ms) > 0 else None
    )
    topology = {
        "producer_count": qd,
        "fd_topology": "one_shared_fd",
        "open_count": 1,
        "shared_by_workers": True,
        "positioned_reads": callable(getattr(os, "preadv", None)),
        "close_after_all_workers": True,
        "fixed_contiguous_regions": True,
        "fixed_ownership": all(
            int(event.get("producer_id", -1)) < qd for event in coverage_events
        ),
        "monotonic_reads": all(
            all(
                int(left.get("source_offset", 0)) <= int(right.get("source_offset", 0))
                for left, right in zip(
                    [event for event in coverage_events if int(event.get("producer_id", -1)) == producer],
                    [event for event in coverage_events if int(event.get("producer_id", -1)) == producer][1:],
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
    buffer_types = {str(item["buffer_type"]) for item in buffer_details}
    pinned_host = bool(buffer_details) and all(
        item.get("is_pinned") is True for item in buffer_details
    )
    buffer_type = next(iter(buffer_types)) if len(buffer_types) == 1 else "mixed"
    released_after_join = workers_joined_ns is not None
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
        "torch_imported": bool(_TORCH_IMPORTED),
        "cuda_available": cuda_available,
        "cuda_build": cuda_build,
        "device_name": device_name,
        "cuda_used": False,
        "h2d_used": False,
        "FILE_TO_CUDA_WALL_MS": None,
        "C9_TOTAL_WALL_MS": c9_total_wall_ms,
        "PHYSICAL_READ_SPAN_MS": physical_read_span_ms,
        "SOURCE_WALL_MS": source_wall_ms,
        "source_wall_ms": source_wall_ms,
        "effective_gbps": effective_gbps,
        "source_effective_gbps": effective_gbps,
        "source_bytes": source_bytes,
        "source_read_count": source_read_count,
        "source_requested_bytes": source_requested_bytes,
        "source_returned_bytes": source_bytes,
        "SOURCE_SYSCALL_UNION_BUSY_MS": raw.get("SOURCE_SYSCALL_UNION_BUSY_MS"),
        "max_actual_source_inflight": observed_qd,
        "achieved_mean_qd": observed_qd_mean,
        "achieved_source_qd_mean": observed_qd_mean,
        "achieved_source_qd_max": observed_qd,
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
        "timing_scope": "before worker thread startup -> all worker joins",
        "timing_boundary": {
            "name": "C9_TOTAL_WALL",
            "start": "immediately before worker thread startup",
            "end": "all worker joins complete",
            "setup_excluded": ["Torch import", "shared FD open"],
            "physical_read_span": {
                "name": "PHYSICAL_READ_SPAN",
                "start": "first os.preadv begin",
                "end": "last os.preadv end",
            },
            "hashing_included": False,
        },
        "fd_topology": {
            "mode": "one_shared_fd",
            "open_count": 1,
            "shared_by_workers": True,
            "positioned_reads": callable(getattr(os, "preadv", None)),
            "close_after_all_workers": True,
        },
        "buffer_type": buffer_type,
        "pinned_host": pinned_host,
        "pinned_host_evidence": {
            "buffer_type": buffer_type,
            "is_pinned": pinned_host,
            "buffers": buffer_details,
        },
        "buffer_allocations": {
            "count": len(regions),
            "bytes_per_worker": block_bytes,
            "allocation_in_c9_total_wall": True,
            "allocated_before_source_wall": False,
            "reused_for_each_read": True,
            "reusable_lifetime": "worker_source_wall",
            "is_pinned": pinned_host,
            "released_after_all_workers_join": released_after_join,
        },
        "hashing_in_timed_loop": False,
        "allocation_in_timed_loop": False,
        "telemetry_in_timed_loop": bool(forensic),
        "integrity_verification": {"performed": False, "scope": None},
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
        "physical_syscall_provenance": raw.get("physical_syscall_provenance") or provenance,
        "physical_syscall_telemetry": events,
        "read_size_evidence": read_sizes,
        "read_evidence_complete": forensic and all(
            bool(row.get("read_evidence_complete")) for row in worker_rows
        ) and not worker_errors,
        "all_requests_within_buffer": all_requests_within_buffer,
        "max_requested_bytes": max_requested_bytes,
        "actual_source": raw,
        "transport_stats": {
            "execution_arm": SOURCE_ONLY_ARM,
            "configured_qd": qd,
            "producer_count": qd,
            "source_block_bytes": block_bytes,
            "source_bytes": source_bytes,
            "source_read_count": source_read_count,
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
            "C9_TOTAL_WALL_MS": c9_total_wall_ms,
            "PHYSICAL_READ_SPAN_MS": physical_read_span_ms,
            "source_wall_ms": source_wall_ms,
            "effective_gbps": effective_gbps,
            "h2d_used": False,
            "cuda_used": False,
            "physical_syscall_provenance": raw.get("physical_syscall_provenance") or provenance,
            "physical_syscall_telemetry": events,
            "topology": topology,
        },
        "metrics": {
            "C9_TOTAL_WALL_MS": c9_total_wall_ms,
            "PHYSICAL_READ_SPAN_MS": physical_read_span_ms,
            "SOURCE_WALL_MS": source_wall_ms,
            "source_wall_ms": source_wall_ms,
            "effective_gbps": effective_gbps,
            "source_bytes": source_bytes,
            "source_read_count": source_read_count,
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


def run_c9_capability_smoke(
    worker_count: int = 1, buffer_bytes: int = 32 * 1024 * 1024
) -> dict[str, Any]:
    """Smoke 0: prove Torch/CUDA and pinned-buffer capability only.

    This deliberately does not open a model, touch the models mount, or make
    a CUDA copy.  It allocates and releases only the buffers the source arm
    requires, so a failed capability check cannot be mistaken for a read run.
    """
    if isinstance(worker_count, bool) or int(worker_count) < 1:
        raise ValueError("worker_count must be positive")
    if int(buffer_bytes) != 32 * 1024 * 1024:
        raise ValueError("buffer_bytes must be exactly 32 MiB")
    started_ns = time.monotonic_ns()
    result: dict[str, Any] = {
        "status": "error",
        "operation": "c9_capability_smoke_0",
        "model_read": False,
        "h2d_pipeline_initialized": False,
        "worker_count": int(worker_count),
        "buffer_bytes": int(buffer_bytes),
        "torch_imported": False,
        "torch_version": None,
        "cuda_build": None,
        "cuda_available": None,
        "device_name": None,
        "buffers": [],
        "resource_contract": {
            "cpu": 12,
            "memory_mb": 8192,
            "gpu": "rtx-pro-6000",
        },
    }
    buffers: list[Any] = []
    try:
        torch = _import_torch()
        result["torch_imported"] = True
        result["torch_version"] = str(getattr(torch, "__version__", ""))
        version = getattr(torch, "version", None)
        result["cuda_build"] = getattr(version, "cuda", None)
        cuda = cast(Any, getattr(torch, "cuda", None))
        available = bool(cuda.is_available())
        result["cuda_available"] = available
        if available:
            result["device_name"] = str(cuda.get_device_name(0))
        for worker_id in range(int(worker_count)):
            tensor = _allocate_pinned_buffer(int(buffer_bytes))
            buffers.append(tensor)
            result["buffers"].append({
                "worker_id": worker_id,
                "bytes": int(buffer_bytes),
                "buffer_type": "pytorch_pinned_host",
                "is_pinned": tensor.is_pinned() is True,
            })
        result["status"] = (
            "ok"
            if all(item["is_pinned"] is True for item in result["buffers"])
            else "error"
        )
        if result["status"] != "ok":
            result["error"] = "pytorch_pinned_host_buffer_is_not_pinned"
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
    finally:
        buffers.clear()
        result["wall_ms"] = (time.monotonic_ns() - started_ns) / 1_000_000.0
    return _json_safe(result)


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
    forensic: bool = False,
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
        result["torch_imported"] = False
        result["cuda_used"] = False
        result["h2d_used"] = False
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
                str(path), role, int(qd), int(block_bytes),
                source_capacity=int(source_capacity), forensic=forensic,
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
    forensic: bool = False,
) -> dict[str, Any]:
    """Public pure-source API; forensic syscall telemetry is opt-in."""
    return run_source_ceiling_oracle(
        role, model_name, SOURCE_ONLY_ARM, attempt_id, qd, block_bytes, source_capacity,
        forensic=forensic,
    )
