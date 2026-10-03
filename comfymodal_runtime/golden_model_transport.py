"""Persistent, role-neutral safetensors transport for Golden model loads."""

from __future__ import annotations

import asyncio
import functools
import atexit
import collections
import ctypes
import json
import multiprocessing as mp
import os
import struct
import sys
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Optional

from . import m2_source_core
from . import source_race_gpu
from . import golden_source_threads
from . import golden_model_metadata_cache
from .source_latency_telemetry import (
    collect_placement_telemetry,
    summarize_first_h2d,
    summarize_source_operations,
)


class _DeferredC0Backend:
    """Restore-owned backend shell; a model only binds its CUDA destination."""

    def __init__(self) -> None:
        self._backend: Any = None

    @property
    def destination(self) -> Any:
        return getattr(self._backend, "destination", None)

    def bind(self, backend: Any) -> None:
        self._backend = backend

    def submit_h2d(self, source: Any, destination_offset: int) -> Any:
        return self._require().submit_h2d(source, destination_offset)

    def poll_event(self, event: Any) -> Any:
        return self._require().poll_event(event)

    def cancel_event(self, event: Any) -> None:
        self._require().cancel_event(event)

    def _require(self) -> Any:
        if self._backend is None:
            raise RuntimeError("c0_backend_not_bound")
        return self._backend

    def __getattr__(self, name: str) -> Any:
        backend = self._backend
        if backend is None:
            raise RuntimeError("c0_backend_not_bound")
        return getattr(backend, name)

QD = 4
BLOCK_BYTES = 64 * 1024 * 1024
STAGING_SLOTS = 1
STAGING_BYTES = QD * BLOCK_BYTES
MIN_LAUNCH_GAP_NS = 4_000_000
MAX_SOURCE_BLOCKS = 65_536
DESTINATION_RESERVE_FRACTION = 0.30
DESTINATION_ALIGNMENT = 256
LAYOUT_CACHE_LIMIT = 3
FD_CACHE_LIMIT = 4
TRANSFER_TIMEOUT_S = 300.0
ABORT_TIMEOUT_S = 5.0

DTYPE_NAMES = {
    "F64": "float64", "F32": "float32", "F16": "float16", "BF16": "bfloat16",
    "I64": "int64", "I32": "int32", "I16": "int16", "I8": "int8",
    "U8": "uint8", "U16": "uint16", "U32": "uint32", "U64": "uint64",
    "BOOL": "bool", "F8_E4M3": "float8_e4m3fn", "F8_E5M2": "float8_e5m2",
}


@dataclass(frozen=True)
class SafetensorsLayout:
    path: str
    identity: tuple[int, int, int, int]
    header: dict[str, Any]
    data_start: int
    data_bytes: int
    tensor_map: tuple[dict[str, Any], ...]
    cache_source: str = "runtime_parse"
    metadata_cache_entry_hit: bool = False
    metadata_cache_identity_match: bool = False
    metadata_cache_hydration_ms: float = 0.0
    metadata_cache_lookup_ms: float = 0.0


@dataclass
class _GpuDestinationSlot:
    tensor: Any
    capacity_bytes: int
    reserved: bool
    active_lease: Any = None
    use_count: int = 0


class GpuAllocationLease:
    """An explicit active lease over one reusable generic CUDA allocation."""

    def __init__(
        self,
        pool: "GpuDestinationPool",
        slot: _GpuDestinationSlot,
        required_bytes: int,
        reused: bool,
    ):
        self._pool = pool
        self._slot = slot
        self._tensor = slot.tensor
        self.capacity_bytes = int(slot.capacity_bytes)
        self.required_bytes = int(required_bytes)
        self.reused = bool(reused)
        self.released = False

    @property
    def gpu_tensor(self) -> Any:
        if self.released:
            raise RuntimeError("gpu_allocation_lease_released")
        return self._tensor

    @property
    def gpu_buf(self) -> Any:
        return self.gpu_tensor

    @property
    def device(self) -> str:
        return str(self.gpu_tensor.device)

    def release_storage(self, *, purge_allocator: bool = False) -> None:
        del purge_allocator
        if not self.released:
            self.released = True
            self._pool.release(self)

    def release_staging(self) -> None:
        return None

    def purge_allocator(self) -> None:
        self.release_storage()

    def close(self) -> None:
        self.release_storage()


class GpuDestinationPool:
    def __init__(self, device: str):
        self.device = str(device)
        self._slots: list[_GpuDestinationSlot] = []
        self._lock = threading.Lock()
        self.reserve_count = 0
        self.reserve_ms = 0.0
        self.growth_count = 0
        self.growth_ms = 0.0

    @staticmethod
    def _allocate(device: str, capacity_bytes: int) -> Any:
        import torch

        with torch.cuda.device(device):
            return getattr(torch, "empty")(
                int(capacity_bytes), dtype=getattr(torch, "uint8"), device=device
            )

    def reserve(self, capacities: list[int]) -> None:
        capacities = [int(value) for value in capacities if int(value) > 0]
        if not capacities:
            return
        started = time.perf_counter()
        slots = [
            _GpuDestinationSlot(
                tensor=self._allocate(self.device, capacity),
                capacity_bytes=capacity,
                reserved=True,
            )
            for capacity in capacities
        ]
        with self._lock:
            self._slots.extend(slots)
            self.reserve_count += len(slots)
            self.reserve_ms += (time.perf_counter() - started) * 1000.0

    def acquire(self, required_bytes: int) -> GpuAllocationLease:
        required_bytes = int(required_bytes)
        if required_bytes < 1:
            raise ValueError("gpu_destination_bytes_must_be_positive")
        with self._lock:
            candidates = [
                slot
                for slot in self._slots
                if slot.active_lease is None and slot.capacity_bytes >= required_bytes
            ]
            if candidates:
                slot = min(candidates, key=lambda candidate: candidate.capacity_bytes)
                lease = GpuAllocationLease(self, slot, required_bytes, reused=True)
                slot.active_lease = lease
                slot.use_count += 1
                return lease

            started = time.perf_counter()
            tensor = self._allocate(self.device, required_bytes)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            slot = _GpuDestinationSlot(
                tensor=tensor,
                capacity_bytes=required_bytes,
                reserved=False,
                use_count=1,
            )
            lease = GpuAllocationLease(self, slot, required_bytes, reused=False)
            slot.active_lease = lease
            self._slots.append(slot)
            self.growth_count += 1
            self.growth_ms += elapsed_ms
        return lease

    def release(self, lease: GpuAllocationLease) -> None:
        with self._lock:
            slot = lease._slot
            if not any(candidate is slot for candidate in self._slots) or slot.active_lease is not lease:
                raise RuntimeError("gpu_allocation_lease_unknown")
            slot.active_lease = None

    def telemetry(self) -> dict[str, Any]:
        with self._lock:
            capacities = [int(slot.capacity_bytes) for slot in self._slots]
            active = sum(1 for slot in self._slots if slot.active_lease is not None)
            reserved = sum(
                int(slot.capacity_bytes) for slot in self._slots if slot.reserved
            )
        return {
            "allocation_count": len(capacities),
            "active_lease_count": active,
            "capacity_bytes": sum(capacities),
            "reserved_capacity_bytes": reserved,
            "destination_reserve_count": self.reserve_count,
            "destination_reserve_ms": self.reserve_ms,
            "destination_growth_count": self.growth_count,
            "destination_growth_ms": self.growth_ms,
        }


@dataclass
class LoadedSafetensors:
    path: str
    views: dict[str, Any]
    owner: GpuAllocationLease
    layout: SafetensorsLayout
    stats: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        if key == "sd":
            return self.views
        if key == "owner":
            return self.owner
        if key == "stats":
            return self.stats
        if key == "tensor_map":
            return list(self.layout.tensor_map)
        if key == "data_start":
            return self.layout.data_start
        if key == "data_bytes":
            return self.layout.data_bytes
        if key == "source":
            return self.stats.get("source")
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass
class LayoutPreresolve:
    """Evidence holder for one background safetensors layout resolution."""

    path: str
    started_ns: Optional[int]
    finished_ns: Optional[int]
    done: threading.Event
    result: Any = None
    error: Optional[BaseException] = None

    @property
    def ms(self) -> Optional[float]:
        if self.started_ns is None or self.finished_ns is None:
            return None
        return (self.finished_ns - self.started_ns) / 1e6

    @property
    def completed(self) -> bool:
        """True once the background resolution has finished, successfully or not."""
        return self.done.is_set()


# The pre-resolve is an optimization, not a dependency: golden_unet_load's own
# inspect() remains the canonical parse, and it reproduces the identical
# deterministic failure if the pre-resolve did not finish.  Measured cost on a
# healthy run is ~15 ms while CLIP bytes are still moving, so a generous budget
# keeps the win and still bounds the wait.  It must be bounded: this join runs
# synchronously on the request's event loop, and an unbounded wait would put
# the whole request behind one header read on a host that stalls.
LAYOUT_PRERESOLVE_JOIN_BUDGET_S = 2.0


def _file_identity(path: str) -> tuple[int, int, int, int]:
    stat_result = os.stat(path)
    return (
        int(getattr(stat_result, "st_dev", 0)),
        int(getattr(stat_result, "st_ino", 0)),
        int(stat_result.st_size),
        int(getattr(stat_result, "st_mtime_ns", 0)),
    )


def _sticky_lane_ranges(total_blocks: int, qd: int = QD) -> tuple[tuple[int, int], ...]:
    base, extra = divmod(int(total_blocks), int(qd))
    cursor = 0
    ranges: list[tuple[int, int]] = []
    for lane in range(int(qd)):
        count = base + (1 if lane < extra else 0)
        ranges.append((cursor, cursor + count))
        cursor += count
    return tuple(ranges)


def _destination_reserve_capacities(free_bytes: int, total_bytes: int) -> tuple[int, ...]:
    available = min(int(free_bytes), int(total_bytes))
    budget = int(available * DESTINATION_RESERVE_FRACTION)
    unit = (budget // 6 // DESTINATION_ALIGNMENT) * DESTINATION_ALIGNMENT
    if unit < DESTINATION_ALIGNMENT:
        return ()
    return (3 * unit, 2 * unit, unit)


def _parse_layout(path: str, identity: tuple[int, int, int, int]) -> SafetensorsLayout:
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError("truncated_safetensors_header_length")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length <= 0 or header_length > size - 8:
            raise ValueError(f"invalid_safetensors_header_length:{header_length}")
        raw_header = handle.read(header_length)
    header = json.loads(raw_header.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("safetensors_header_not_object")
    data_start = 8 + int(header_length)
    data_bytes = size - data_start
    tensor_map: list[dict[str, Any]] = []
    ranges: list[tuple[int, int, str]] = []
    for name, info in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(info, dict):
            raise ValueError(f"invalid_tensor_metadata:{name}")
        offsets = info.get("data_offsets")
        shape = info.get("shape")
        dtype = str(info.get("dtype", ""))
        if not isinstance(offsets, list) or len(offsets) != 2 or not isinstance(shape, list):
            raise ValueError(f"invalid_tensor_metadata:{name}")
        start, end = int(offsets[0]), int(offsets[1])
        if start < 0 or end <= start or end > data_bytes:
            raise ValueError(f"tensor_offset_out_of_range:{name}")
        if dtype not in DTYPE_NAMES:
            raise ValueError(f"unsupported_safetensors_dtype:{dtype}")
        ranges.append((start, end, str(name)))
        tensor_map.append({
            "key": str(name),
            "dtype": dtype,
            "shape": [int(value) for value in shape],
            "offset": start,
            "length": end - start,
        })
    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if previous[1] > current[0]:
            raise ValueError(f"overlapping_tensor_ranges:{previous[2]}:{current[2]}")
    return SafetensorsLayout(
        path=os.path.abspath(path),
        identity=identity,
        header=header,
        data_start=data_start,
        data_bytes=data_bytes,
        tensor_map=tuple(tensor_map),
    )


C0_TRANSPORT_GEOMETRY_ENV = "COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY"
C0_WINDOW_TRACE_ENV = "COMFYMODAL_GOLDEN_C0_WINDOW_TRACE"
_C0_TRANSPORT_GEOMETRIES = ("qd4_64", "qd2_128", "qd4_64_h2d128", "qd4_128")
_C0_WINDOW_TRACE_LIMIT = 4096


def _c0_window_trace_enabled() -> bool:
    return str(os.environ.get(C0_WINDOW_TRACE_ENV) or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def resolve_c0_transport_geometry(value: Any = None) -> dict[str, Any]:
    """Resolve the C0 source/H2D scheduling geometry (deploy-baked selector).

    Geometry describes scheduling/window usage only; the C0 arena size is
    never decided here.  ``qd2_128`` requires 128 MiB C0 slots (control
    geometry); anything else requires 64 MiB slots (treatment geometry).
    Unknown selectors fail closed.
    """
    selected = (
        os.environ.get(C0_TRANSPORT_GEOMETRY_ENV) if value is None else value
    )
    selected = str(selected if selected is not None else "qd4_64").strip().lower()
    if selected not in _C0_TRANSPORT_GEOMETRIES:
        raise ValueError(
            f"invalid C0 transport geometry {selected!r}; "
            f"expected one of {_C0_TRANSPORT_GEOMETRIES}"
        )
    if selected == "qd2_128":
        return {
            "name": selected,
            "queue_depth": 2,
            "block_bytes": 128 * 1024 * 1024,
            "producer_workers": 2,
            "aggregation_enabled": False,
            "h2d_target_bytes": 128 * 1024 * 1024,
            "capacity_class": "c0-qd2-128m",
            "required_slot_bytes": 128 * 1024 * 1024,
        }
    if selected == "qd4_64_h2d128":
        return {
            "name": selected,
            "queue_depth": QD,
            "block_bytes": BLOCK_BYTES,
            "producer_workers": QD,
            "aggregation_enabled": True,
            "h2d_target_bytes": 128 * 1024 * 1024,
            "capacity_class": "c0-qd4-64m",
            "required_slot_bytes": 64 * 1024 * 1024,
        }
    if selected == "qd4_128":
        return {
            "name": selected,
            "queue_depth": QD,
            "block_bytes": 128 * 1024 * 1024,
            "producer_workers": QD,
            "aggregation_enabled": False,
            "h2d_target_bytes": 128 * 1024 * 1024,
            "capacity_class": "c0-qd4-128m",
            "required_slot_bytes": 128 * 1024 * 1024,
        }
    return {
        "name": selected,
        "queue_depth": QD,
        "block_bytes": BLOCK_BYTES,
        "producer_workers": QD,
        "aggregation_enabled": False,
        "h2d_target_bytes": BLOCK_BYTES,
        "capacity_class": "c0-qd4-64m",
        "required_slot_bytes": 64 * 1024 * 1024,
    }


def _percentile_summary(values: list[Any]) -> dict[str, Any]:
    """Compact count/min/p50/p90/max/sum over plain-int samples (ms assumed)."""
    samples = sorted(
        int(value) for value in values
        if isinstance(value, int) and not isinstance(value, bool)
    )
    if not samples:
        return {"count": 0}
    def at(frac: float) -> float:
        pos = frac * (len(samples) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(samples) - 1)
        return samples[lo] + (samples[hi] - samples[lo]) * (pos - lo)
    total = sum(samples)
    return {
        "count": len(samples),
        "min_ms": samples[0] / 1e6,
        "p50_ms": at(0.50) / 1e6,
        "p90_ms": at(0.90) / 1e6,
        "max_ms": samples[-1] / 1e6,
        "sum_ms": total / 1e6,
        "mean_ms": (total / len(samples)) / 1e6,
    }


def _summarize_dma_stage(values: Any) -> dict[str, Any]:
    """Extended distribution for SHM->pinned stage copies (Exp. 3).

    Median/p90/p95/p99/max plus the mandatory >=5/10/20 ms counters.
    """
    samples = sorted(
        int(value) for value in (values or [])
        if isinstance(value, int) and not isinstance(value, bool)
    )
    if not samples:
        return {"count": 0}
    def at(frac: float) -> float:
        pos = frac * (len(samples) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(samples) - 1)
        return samples[lo] + (samples[hi] - samples[lo]) * (pos - lo)
    total = sum(samples)
    return {
        "count": len(samples),
        "min_ms": samples[0] / 1e6,
        "p50_ms": at(0.50) / 1e6,
        "p90_ms": at(0.90) / 1e6,
        "p95_ms": at(0.95) / 1e6,
        "p99_ms": at(0.99) / 1e6,
        "max_ms": samples[-1] / 1e6,
        "sum_ms": total / 1e6,
        "mean_ms": (total / len(samples)) / 1e6,
        "ge_5ms": sum(1 for v in samples if v >= 5_000_000),
        "ge_10ms": sum(1 for v in samples if v >= 10_000_000),
        "ge_20ms": sum(1 for v in samples if v >= 20_000_000),
    }


def _mean_ns(values: Any) -> float | None:
    samples = [
        int(value) for value in (values or [])
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    if not samples:
        return None
    return (sum(samples) / len(samples)) / 1e6


def _summarize_cpu_windows(windows: Any) -> dict[str, Any]:
    """Sum per-(pid, counter) first/last deltas into per-counter totals (ms).

    The child reports cumulative process counters; only the delta consumed
    during this load is meaningful.  Malformed entries degrade to None.
    """
    totals: dict[str, float] = {}
    per_pid: dict[str, dict[str, float]] = {}
    if isinstance(windows, dict):
        for key, bounds in windows.items():
            if (
                not isinstance(key, tuple) or len(key) != 2
                or not isinstance(bounds, (list, tuple)) or len(bounds) != 2
            ):
                continue
            pid, name = key
            first, last = bounds
            if not isinstance(first, int) or not isinstance(last, int):
                continue
            delta_ms = max(0, last - first) / 1e6
            totals[str(name)] = totals.get(str(name), 0.0) + delta_ms
            per_pid.setdefault(str(pid), {})[str(name)] = delta_ms
    out: dict[str, Any] = {"per_pid": per_pid}
    for short, full in (
        ("utime_ms", "mmap_ru_utime_ns"),
        ("stime_ms", "mmap_ru_stime_ns"),
        ("sched_run_ms", "mmap_sched_run_ns"),
        ("sched_wait_ms", "mmap_sched_wait_ns"),
    ):
        out[short] = totals.get(full)
    return out


def arena_ensure_detail(runtime: Any) -> dict[str, Any]:
    """Report C0 arena establishment cost (Part 4 restore decomposition).

    Reads already-recorded SharedArenaRing fields; performs no I/O and no
    synchronization.  The arena is ensured once per container (at restore);
    later loads reread the same establishment evidence.
    """
    def _get(name: str, default: Any = None) -> Any:
        try:
            return getattr(runtime, name, default)
        except BaseException:
            return default

    start_ns = _get("child_start_ns")
    ready_ns = _get("child_ready_ns")
    detail: dict[str, Any] = {
        "arena_bytes": _get("size_bytes"),
        "slot_count": _get("slot_count"),
        "slot_bytes": _get("slot_bytes"),
        "backing_create_ms": _get("backing_create_ms"),
        "register_ms": _get("register_ms"),
        "registration_diagnostic": _get("registration_diagnostic"),
        "registration_order": _get("registration_order"),
        "registered": _get("registered"),
        "shm_populate_enabled": _get("shm_populate_enabled"),
        "dma_ring_enabled": _get("dma_ring_enabled"),
        "five_slots_enabled": _get("five_slots_enabled"),
        "startup_marks": _get("startup_marks"),
        "pinned_alloc_ms": _get("pinned_alloc_ms"),
        "populate_ms": _get("populate_ms"),
        "populate_cpu_ms": _get("populate_cpu_ms"),
        "populate_workers": _get("populate_workers"),
        "child_pid": _get("child_pid"),
        "child_ready_evidence": _get("child_ready_evidence"),
        "child_startup_ms": (
            (ready_ns - start_ns) / 1e6
            if isinstance(start_ns, int) and isinstance(ready_ns, int)
            and ready_ns >= start_ns else None
        ),
    }
    return detail


def summarize_c0_reader(source: Any) -> dict[str, Any]:
    """Summarize one load's C0 reader evidence (Stages A-D measurement).

    Reads only already-accumulated reader/ring counters; performs no I/O and
    no synchronization.  Missing attributes degrade to None/empty, never raise.
    """
    def _get(name: str, default: Any = None) -> Any:
        try:
            return getattr(source, name, default)
        except BaseException:
            return default

    ring = _get("_ring")
    def _ring(name: str, default: Any = None) -> Any:
        try:
            return getattr(ring, name, default) if ring is not None else default
        except BaseException:
            return default

    summary: dict[str, Any] = {
        "fills": int(_get("fills", 0) or 0),
        "fill_wall_ms": float(_get("fill_wall_ns", 0) or 0) / 1e6,
        "fd_open": int(_get("fd_open_count", 0) or 0),
        "fd_reuse": int(_get("fd_reuse_count", 0) or 0),
        "fd_close": int(_get("fd_close_count", 0) or 0),
        "ring_backpressure_blocks": int(_ring("backpressure_block_count", 0) or 0),
        "ring_backpressure_ms": float(_ring("backpressure_block_ns", 0) or 0) / 1e6,
        "ring_fills_submitted": int(_ring("fills_submitted", 0) or 0),
        "ring_fills_ready": int(_ring("fills_ready", 0) or 0),
        "map": _percentile_summary(_get("_mmap_map_ns", [])),
        "memcpy": _percentile_summary(_get("_mmap_memcpy_ns", [])),
        "munmap": _percentile_summary(_get("_mmap_munmap_ns", [])),
        "pipe_rtt": _percentile_summary(_get("_mmap_pipe_rtt_ns", [])),
        "gate_wait": _percentile_summary(_get("_mmap_gate_wait_ns", [])),
        "dma_stage_copy": _summarize_dma_stage(_get("_dma_stage_ns", [])),
        "dma_acquire_wait": _summarize_dma_stage(_get("_dma_acquire_wait_ns", [])),
        "memcpy_first_ms": _mean_ns(_get("_mmap_memcpy_first_ns", [])),
        "memcpy_reuse_ms": _mean_ns(_get("_mmap_memcpy_reuse_ns", [])),
        "map_first_ms": _mean_ns(_get("_mmap_map_first_ns", [])),
        "map_reuse_ms": _mean_ns(_get("_mmap_map_reuse_ns", [])),
        "minflt_total": sum(
            int(v) for v in (_get("_mmap_minflt", []) or []) if isinstance(v, int)
        ),
        "majflt_total": sum(
            int(v) for v in (_get("_mmap_majflt", []) or []) if isinstance(v, int)
        ),
        "cpu": _summarize_cpu_windows(_get("_mmap_cpu_windows", {})),
        "reader_pids": sorted(int(p) for p in (_get("_mmap_reader_pids", set()) or set())),
    }
    worst: dict[str, Any] | None = None
    for record in (_get("_mmap_read_records", []) or []):
        if not isinstance(record, dict):
            continue
        op_ns = record.get("mmap_op_ns")
        if not isinstance(op_ns, int) or isinstance(op_ns, bool):
            continue
        if worst is None or op_ns > worst["mmap_op_ns"]:
            worst = {
                "mmap_op_ns": op_ns,
                "producer_id": record.get("producer_id"),
                "reader_pid": record.get("reader_pid"),
                "source_range": record.get("source_range"),
                "mmap_map_ns": record.get("mmap_map_ns"),
                "source_touch_copy_ns": record.get("source_touch_copy_ns"),
                "mmap_munmap_ns": record.get("mmap_munmap_ns"),
                "mmap_pipe_rtt_ns": record.get("mmap_pipe_rtt_ns"),
            }
    summary["worst_window"] = worst
    return summary


def summarize_dispatcher(dispatcher: Any) -> dict[str, Any]:
    """Summarize dispatcher slot/H2D/QD telemetry (Stage A measurement).

    Reads only already-recorded telemetry fields; never synchronizes.
    """
    def _get(obj: Any, name: str, default: Any = None) -> Any:
        try:
            return getattr(obj, name, default)
        except BaseException:
            return default

    telemetry = _get(dispatcher, "telemetry")
    out: dict[str, Any] = {
        "producer_capacity_block_ms": (
            float(_get(telemetry, "producer_capacity_block_wall_ns", 0) or 0) / 1e6
            if _get(telemetry, "producer_capacity_block_wall_ns") is not None else None
        ),
        "producer_capacity_block_count": _get(telemetry, "producer_capacity_block_count"),
        "ready_queue_block_ms": (
            float(_get(telemetry, "ready_queue_block_wall_ns", 0) or 0) / 1e6
            if _get(telemetry, "ready_queue_block_wall_ns") is not None else None
        ),
        "min_free_slots": _get(telemetry, "min_free_slots"),
        "source_qd_target": _get(telemetry, "source_qd_target"),
        "affinity_breaks": _get(telemetry, "affinity_breaks", 0),
        "h2d_submitted": _get(telemetry, "h2d_submitted_bytes"),
        "h2d_completed": _get(telemetry, "h2d_completed_bytes"),
        "gpu_copy_active_union_ms": _get(telemetry, "gpu_copy_active_union_ms"),
        "gpu_copy_idle_inside_span_ms": _get(telemetry, "gpu_copy_idle_inside_stream_span_ms"),
        "producer_read_counts": dict(_get(telemetry, "producer_read_counts", {}) or {}),
        "drain_ms": None,
    }
    start = _get(telemetry, "final_drain_start_ns")
    end = _get(telemetry, "final_drain_end_ns")
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        out["drain_ms"] = (end - start) / 1e6
    depths = [
        int(item.get("depth", 0)) for item in (_get(telemetry, "source_qd_timeline", []) or [])
        if isinstance(item, dict)
    ]
    out["qd_depth_max"] = max(depths) if depths else None
    out["qd_depth_transitions"] = len(depths)
    latencies = [
        int(v) for v in (_get(telemetry, "h2d_latencies_ns", []) or [])
        if isinstance(v, int) and not isinstance(v, bool)
    ]
    out["h2d_latency"] = _percentile_summary(latencies)
    try:
        _pool = _get(dispatcher, "pool")
        _snapshot = getattr(_pool, "pressure_snapshot", None)
        out["slot_pressure"] = dict(_snapshot()) if callable(_snapshot) else None
    except BaseException:
        out["slot_pressure"] = None
    return out


class GoldenModelTransport:
    """One persistent, path-driven M2 transport for all model roles."""

    def __init__(self, *, qd: int = QD, block_bytes: int = BLOCK_BYTES):
        if int(qd) != QD or int(block_bytes) != BLOCK_BYTES:
            raise ValueError("GoldenModelTransport geometry is fixed at QD4/64MiB")
        self.qd = QD
        self.block_bytes = BLOCK_BYTES
        self.staging_slots = STAGING_SLOTS
        self.staging_bytes = self.qd * self.staging_slots * self.block_bytes
        self.staging_backing = "anonymous"
        self.staging: dict[str, Any] | None = None
        self._ctx: Any = None
        self._children: list[Any] = []
        self._connections: list[Any] = []
        self._ownership: Any = None
        self._completed: Any = None
        self._failed: Any = None
        self._scheduler_lock: Any = None
        self._last_start: Any = None
        self._pacer_lock: Any = None
        self._prepared = False
        self._cuda_ready = False
        self._cuda: dict[str, Any] = {}
        self._event_pool: list[Any] = []
        self._layout_cache: collections.OrderedDict[str, SafetensorsLayout] = collections.OrderedDict()
        self._layout_lock = threading.Lock()
        self._layout_preresolve: Optional[LayoutPreresolve] = None
        self._models_generation = ""
        self._generation = 0
        self._reader_done: set[int] = set()
        self._lock = threading.RLock()
        self._pool: GpuDestinationPool | None = None
        # C0 shared-arena selection (deploy-baked, read once).  When the C0
        # streaming arena + frozen exact-window mmap engine are both selected,
        # this transport is a thin dispatcher over the persistent C0
        # arena: no M2 staging is built, no reader processes are forked, and no
        # extra CUDA context/registration/stream is created here.  M2 owns only
        # the source byte-producer semantics inside the C0 child workers.
        self._c0_runtime: Any = None
        self._c0_resources: Any = None
        self._c0_source_transport: Any = None
        self._c0_source_pool: Any = None
        self._c0_source_backend = _DeferredC0Backend()
        self._c0_restore_setup_marks: dict[str, int] = {}
        c0_streaming = (
            str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING") or "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        source_engine = str(
            os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE") or ""
        ).strip().lower()
        self._c0_source_threads_enabled = golden_source_threads.enabled()
        # The C0 source-owner arm declares its own source kernel: native libc
        # mmap + memmove over MAP_PRIVATE, with its own explicit, fail-closed
        # fresh|whole lifecycle.  Requiring the historical M2 engine string
        # here would force that arm to publish a source identity it does not
        # have, so gate it on the streaming request it actually needs.
        self._c0_enabled = c0_streaming and (
            source_engine == "mmap_fresh" or self._c0_source_threads_enabled
        )
        if self._c0_source_threads_enabled and not c0_streaming:
            raise RuntimeError(
                "golden_c0_source_threads_requires_c0_streaming"
            )
        if c0_streaming and not self._c0_enabled:
            # Fail closed: C0 streaming is armed, so the caller requested the
            # C0 shared arena.  Running the standalone M2 execution arm here
            # would silently execute the wrong architecture.  Either select
            # the frozen exact-window engine (mmap_fresh), enable the C0
            # source-owner arm, or do not enter this transport at all.
            raise RuntimeError(
                "golden_model_transport_c0_streaming_requires_mmap_fresh"
            )
        self._load_count = 0
        self._closed = False
        self._poisoned = False

    @property
    def layout_cache(self) -> collections.OrderedDict[str, SafetensorsLayout]:
        return self._layout_cache

    def prepare_cpu(self) -> dict[str, Any]:
        with self._lock:
            if self._prepared:
                return self.lifecycle_telemetry(reused=True)
            if self._c0_enabled:
                # C0 owns its child/worker lifecycle via the shared arena
                # runtime; nothing is forked or staged here (restore stays
                # C0-driven, so this is a cheap no-op, not second setup work).
                self._prepared = True
                return self.lifecycle_telemetry(reused=False)
            if os.name == "nt" or "fork" not in mp.get_all_start_methods():
                raise RuntimeError("persistent_m2_requires_fork")
            torch_module = sys.modules.get("torch")
            cuda_module = getattr(torch_module, "cuda", None)
            is_initialized = getattr(cuda_module, "is_initialized", None)
            if callable(is_initialized) and is_initialized():
                raise RuntimeError("persistent_m2_readers_must_fork_before_cuda")
            self._ctx = mp.get_context("fork")
            self.staging = source_race_gpu.build_staging(
                self.qd,
                self.staging_slots,
                self.block_bytes,
                prefault=False,
                backing=self.staging_backing,
            )
            self._ownership = self._ctx.Array("b", MAX_SOURCE_BLOCKS, lock=False)
            self._completed = self._ctx.Value("i", 0, lock=False)
            self._failed = self._ctx.Value("i", 0, lock=False)
            self._scheduler_lock = self._ctx.Lock()
            self._last_start = self._ctx.Value("q", 0)
            self._pacer_lock = self._last_start.get_lock()
            for reader_id in range(self.qd):
                parent_conn, child_conn = self._ctx.Pipe(duplex=True)
                process = self._ctx.Process(
                    target=m2_source_core.persistent_reader_main,
                    args=(
                        reader_id,
                        child_conn,
                        self.staging,
                        FD_CACHE_LIMIT,
                        self._ownership,
                        self._completed,
                        self._failed,
                        self._scheduler_lock,
                        self._last_start,
                        self._pacer_lock,
                    ),
                    daemon=True,
                )
                process.start()
                child_conn.close()
                self._connections.append(parent_conn)
                self._children.append(process)
            for reader_id, connection in enumerate(self._connections):
                if not connection.poll(30.0):
                    raise RuntimeError(f"persistent_reader_not_ready:{reader_id}")
                ready = connection.recv()
                if ready.get("command") != "READY":
                    raise RuntimeError(f"persistent_reader_bad_ready:{reader_id}")
            self._prepared = True
            return self.lifecycle_telemetry(reused=False)

    def initialize_cuda(self, device: str | None = None) -> dict[str, Any]:
        with self._lock:
            self.prepare_cpu()
            if self._cuda_ready:
                return self.lifecycle_telemetry(reused=True)
            import torch

            if not torch.cuda.is_available():
                raise RuntimeError("cuda_unavailable")
            device_index = int(torch.cuda.current_device())
            target = device or f"cuda:{device_index}"
            target_device = getattr(torch, "device")(target)
            target_index = device_index if target_device.index is None else int(target_device.index)
            if target_device.type != "cuda" or target_index != device_index:
                raise RuntimeError(
                    f"persistent_transport_device_mismatch:{target}!={device_index}"
                )
            if self._c0_enabled:
                # Reuse the persistent C0 arena + shared dispatcher resources.
                # No new staging, registration, stream, or context is created:
                # the C0 arena runtime already owns all of them.
                from . import golden_io_process_v2 as c0
                from . import golden_qd_transport as qd_transport
                self._c0_runtime = c0.ensure_arena_runtime()
                _c0marks = getattr(self, "_c0_setup_marks", None)
                if isinstance(_c0marks, dict):
                    _c0marks["transfer_resources_begin"] = time.monotonic_ns()
                self._c0_resources = qd_transport.GoldenTransferResources.create_shared(
                    slot_count=int(self._c0_runtime.slot_count),
                    slot_bytes=int(self._c0_runtime.slot_bytes),
                    device=target,
                )
                if isinstance(_c0marks, dict):
                    _c0marks["transfer_resources_end"] = time.monotonic_ns()

                self._pool = GpuDestinationPool(target)
                if self._c0_source_threads_enabled:
                    config = qd_transport.TransportConfig(
                        queue_depth=golden_source_threads.THREAD_COUNT,
                        block_bytes=golden_source_threads.SLOT_BYTES,
                        staging_slots=golden_source_threads.SLOT_COUNT,
                        ready_queue_capacity=golden_source_threads.SLOT_COUNT,
                        producer_workers=golden_source_threads.THREAD_COUNT,
                        capacity_class="source-threads-qd4-64m",
                        h2d_target_bytes=golden_source_threads.SLOT_BYTES,
                        aggregation_enabled=False,
                        cleanup_timeout=10.0,
                    )
                    self._c0_source_pool = self._c0_runtime.new_stage_pool(config.capacity_class)
                    # The dispatcher and its worker are restore/container
                    # resources.  A model load only binds a destination and
                    # resets operation telemetry.
                    self._c0_source_transport = qd_transport.GoldenQDTransport(
                        config, self._c0_source_backend, pool=self._c0_source_pool,
                        diagnostics=True, resources=self._c0_resources,
                        persistent_dispatcher=True,
                    )
                    self._c0_source_transport.start(destination_size=None)
                    self._c0_restore_setup_marks["source_transport_created_once"] = time.monotonic_ns()
                self._cuda = {
                    "device": target,
                    "device_index": device_index,
                    "c0": True,
                }
                self._cuda_ready = True
                return self.lifecycle_telemetry(reused=False)
            assert self.staging is not None
            lib = source_race_gpu._load_driver()
            current = ctypes.c_void_p()
            source_race_gpu._check(lib["cuCtxGetCurrent"](ctypes.byref(current)), "cuCtxGetCurrent")
            if not current.value:
                raise RuntimeError("torch_cuda_context_not_current")
            source_race_gpu._check(
                lib["cuCtxSetCurrent"](current), "cuCtxSetCurrent"
            )
            source_race_gpu._check(
                lib["cuMemHostRegister_v2"](
                    ctypes.c_void_p(int(self.staging["seg_base"])),
                    ctypes.c_size_t(int(self.staging["bytes"])),
                    ctypes.c_uint(0),
                ),
                "cuMemHostRegister",
            )
            stream = ctypes.c_void_p()
            source_race_gpu._check(
                lib["cuStreamCreate"](ctypes.byref(stream), ctypes.c_uint(1)),
                "cuStreamCreate",
            )
            event_count = self.qd * self.staging_slots
            events: list[Any] = []
            for _ in range(event_count):
                event = ctypes.c_void_p()
                source_race_gpu._check(
                    lib["cuEventCreate"](ctypes.byref(event), ctypes.c_uint(0)),
                    "cuEventCreate",
                )
                events.append(event)
            self._cuda = {
                "lib": lib,
                "ctx": current,
                "stream": stream,
                "device": target,
                "device_index": device_index,
                "host_registered": True,
            }
            self._event_pool = events
            self._pool = GpuDestinationPool(target)
            free_bytes, total_bytes = torch.cuda.mem_get_info(target_index)
            self._pool.reserve(list(_destination_reserve_capacities(free_bytes, total_bytes)))
            self._cuda_ready = True
            return self.lifecycle_telemetry(reused=False)

    def update_models_generation(self, generation: str | None) -> None:
        selected = str(generation or "")
        if selected == self._models_generation:
            return
        self._models_generation = selected
        with self._layout_lock:
            self._layout_cache.clear()
        if self._prepared:
            for connection in self._connections:
                connection.send({"command": "INVALIDATE_FDS"})
            for connection in self._connections:
                if not connection.poll(30.0):
                    raise RuntimeError("persistent_reader_fd_invalidation_timeout")
                response = connection.recv()
                if response.get("command") != "INVALIDATE_FDS_DONE":
                    raise RuntimeError("persistent_reader_fd_invalidation_failed")

    def inspect(self, path: str, *, role: str = "model") -> SafetensorsLayout:
        normalized = os.path.abspath(str(path))
        identity = _file_identity(normalized)
        persistent_lookup = None
        persistent_started = time.perf_counter_ns()
        if str(role).startswith("clip"):
            persistent_lookup = golden_model_metadata_cache.lookup(normalized)
            if persistent_lookup.get("entry") is not None:
                entry = persistent_lookup["entry"]
                layout = SafetensorsLayout(
                    path=normalized,
                    identity=identity,
                    header={},
                    data_start=int(entry["data_start"]),
                    data_bytes=int(entry["data_bytes"]),
                    tensor_map=tuple(
                        {
                            "key": str(item[0]),
                            "dtype": str(item[1]),
                            "shape": [int(value) for value in item[2]],
                            "offset": int(item[3]),
                            "length": int(item[4]),
                        }
                        for item in entry["tensors"]
                    ),
                    cache_source="persistent",
                    metadata_cache_entry_hit=True,
                    metadata_cache_identity_match=True,
                    metadata_cache_hydration_ms=float(persistent_lookup.get("hydration_ms") or 0.0),
                    metadata_cache_lookup_ms=(time.perf_counter_ns() - persistent_started) / 1e6,
                )
                with self._layout_lock:
                    self._layout_cache[normalized] = layout
                    self._layout_cache.move_to_end(normalized)
                    while len(self._layout_cache) > LAYOUT_CACHE_LIMIT:
                        self._layout_cache.popitem(last=False)
                return layout
        with self._layout_lock:
            cached = self._layout_cache.get(normalized)
            if cached is not None and cached.identity == identity:
                self._layout_cache.move_to_end(normalized)
                return cached
        layout = _parse_layout(normalized, identity)
        if persistent_lookup is not None:
            layout = replace(
                layout,
                metadata_cache_entry_hit=bool(persistent_lookup.get("entry_hit")),
                metadata_cache_identity_match=bool(persistent_lookup.get("identity_match")),
                metadata_cache_hydration_ms=float(persistent_lookup.get("hydration_ms") or 0.0),
                metadata_cache_lookup_ms=(time.perf_counter_ns() - persistent_started) / 1e6,
            )
        with self._layout_lock:
            self._layout_cache[normalized] = layout
            self._layout_cache.move_to_end(normalized)
            while len(self._layout_cache) > LAYOUT_CACHE_LIMIT:
                self._layout_cache.popitem(last=False)
        return layout

    def begin_layout_preresolve(self, path: str) -> LayoutPreresolve:
        """Start, or join, one background resolution of ``path``'s layout."""
        normalized = os.path.abspath(str(path))
        with self._layout_lock:
            existing = self._layout_preresolve
            if existing is not None and existing.path == normalized:
                return existing
            holder = LayoutPreresolve(
                path=normalized,
                started_ns=time.perf_counter_ns(),
                finished_ns=None,
                done=threading.Event(),
            )
            self._layout_preresolve = holder

        def resolve() -> None:
            try:
                try:
                    holder.result = self.inspect(normalized)
                except BaseException as exc:
                    holder.error = exc
            except BaseException as exc:
                # The worker is evidence-only and must never escape into the
                # interpreter's thread exception machinery.
                holder.error = exc
            finally:
                holder.finished_ns = time.perf_counter_ns()
                holder.done.set()

        try:
            threading.Thread(
                target=resolve,
                name="golden-unet-layout-preresolve",
                daemon=True,
            ).start()
        except BaseException as exc:
            holder.error = exc
            holder.finished_ns = time.perf_counter_ns()
            holder.done.set()
        return holder

    def join_layout_preresolve(
        self, path: str, *, timeout_s: float = LAYOUT_PRERESOLVE_JOIN_BUDGET_S
    ) -> LayoutPreresolve:
        """Wait briefly for a started pre-resolve; never raises, never blocks forever.

        Returns the holder when one exists for this path, otherwise a holder
        with ``started_ns is None``.  An ``error`` on the holder is deliberately
        NOT raised here: the caller's own inspect() call remains the canonical
        operation and will reproduce the identical deterministic failure.

        The wait is bounded by ``timeout_s``.  On expiry the holder is returned
        unfinished and the caller's inspect() simply does the parse itself,
        which is exactly the pre-pre-resolve behaviour.  A caller can tell the
        two apart with ``holder.completed``.
        """
        normalized = os.path.abspath(str(path))
        with self._layout_lock:
            holder = self._layout_preresolve
            if holder is None or holder.path != normalized:
                not_started = LayoutPreresolve(
                    path=normalized,
                    started_ns=None,
                    finished_ns=None,
                    done=threading.Event(),
                )
                not_started.done.set()
                return not_started
        holder.done.wait(timeout=max(0.0, float(timeout_s)))
        return holder

    async def load(self, path: str, *, role: str = "model") -> LoadedSafetensors:
        # The transport body, including the C0 source-thread fan-out, runs on
        # an asyncio executor worker whose thread predates
        # enable_thread_tracing(), so without this handoff it records nothing.
        # Measured on trace a4a4eaaf52fe456cbcd3583527068891: this path drives
        # 184 source reads (clip_load's 120) and produced zero frames. Imported
        # lazily so this module stays importable without the trace runtime.
        try:
            from .full_execution_trace import thread_traced
            target = thread_traced(functools.partial(self._load_sync, role=role))
        except BaseException:
            return await asyncio.to_thread(self._load_sync, path, role=role)
        return await asyncio.to_thread(target, path)

    def load_sync(self, path: str, *, role: str = "model") -> LoadedSafetensors:
        return self._load_sync(path, role=role)

    def _load_sync(self, path: str, *, role: str = "model") -> LoadedSafetensors:
        if self._c0_enabled:
            return self._load_c0_sync(path, role=role)
        started_ns = time.perf_counter_ns()
        with self._lock:
            if self._poisoned:
                raise RuntimeError("persistent_model_transport_poisoned")
            self.prepare_cpu()
            self.initialize_cuda()
            assert self.staging is not None
            assert self._pool is not None
            staging = self.staging
            normalized_path = os.path.abspath(str(path))
            layout_cache_hit = normalized_path in self._layout_cache
            layout_started_ns = time.perf_counter_ns()
            layout = self.inspect(path, role=role)
            layout_end_ns = time.perf_counter_ns()
            total_blocks = (layout.data_bytes + self.block_bytes - 1) // self.block_bytes
            if total_blocks > MAX_SOURCE_BLOCKS:
                raise RuntimeError(
                    f"persistent_source_block_capacity_exceeded:{total_blocks}>{MAX_SOURCE_BLOCKS}"
                )
            lane_ranges = _sticky_lane_ranges(total_blocks, self.qd)
            assert self._ownership is not None
            assert self._completed is not None
            assert self._failed is not None
            assert self._scheduler_lock is not None
            assert self._last_start is not None
            assert self._pacer_lock is not None
            self._generation += 1
            generation = self._generation
            self._reader_done.clear()
            for lane in range(self.qd):
                staging["published"][lane].value = 0
                staging["consumed"][lane].value = 0
            with self._scheduler_lock:
                for block_id in range(total_blocks):
                    self._ownership[block_id] = 0
                self._completed.value = 0
                self._failed.value = 0
            with self._pacer_lock:
                self._last_start.value = 0
            identity = tuple(int(value) for value in layout.identity)
            for connection in self._connections:
                connection.send({
                    "command": "LOAD",
                    "generation": generation,
                    "path": layout.path,
                    "identity": identity,
                    "source_offset": layout.data_start,
                    "data_bytes": layout.data_bytes,
                    "read_bytes": self.block_bytes,
                    "total_blocks": total_blocks,
                    "lane_ranges": lane_ranges,
                    "min_launch_gap_ns": MIN_LAUNCH_GAP_NS,
                })

            owner = None
            growth_ms_before = self._pool.growth_ms
            source_race_gpu._check(
                self._cuda["lib"]["cuCtxSetCurrent"](self._cuda["ctx"]),
                "cuCtxSetCurrent",
            )
            try:
                owner = self._pool.acquire(layout.data_bytes)
                result = self._copy_until_complete(layout, generation, owner)
            except BaseException as exc:
                try:
                    self._abort_transfer(generation)
                except BaseException as abort_exc:
                    add_note = getattr(exc, "add_note", None)
                    if callable(add_note):
                        add_note(f"transport_abort_failed:{type(abort_exc).__name__}:{abort_exc}")
                if owner is not None:
                    owner.release_storage()
                self._poisoned = True
                raise
            try:
                views = self._views(owner.gpu_tensor, layout.tensor_map)
            except BaseException:
                owner.release_storage()
                raise
            finished_ns = time.perf_counter_ns()
            source_start_ns = result["source_start_ns"]
            source_end_ns = result["source_end_ns"]
            last_h2d_ns = result["last_h2d_ns"]
            source_wall_ms = (
                (source_end_ns - source_start_ns) / 1e6
                if source_start_ns and source_end_ns else None
            )
            source_gbps = (
                layout.data_bytes / ((source_wall_ms / 1000.0) * 1e9)
                if source_wall_ms and source_wall_ms > 0 else None
            )
            stats = {
                "status": "ok",
                "source_engine": "m2_mmap_process_persistent",
                "execution_arm": "m2_mmap_process",
                "c0_arena_created": False,
                "source_read_count": int(result["source_read_count"]),
                "source_read_bytes": layout.data_bytes,
                "bytes_read": layout.data_bytes,
                "gpu_bytes": layout.data_bytes,
                "h2d_submitted_bytes": layout.data_bytes,
                "h2d_completed_bytes": layout.data_bytes,
                "source_wall_ms": source_wall_ms,
                "source_child_wall_ms": source_wall_ms,
                "source_fill_wall_ms": None,
                "qd_source_io_wall_ms": source_wall_ms,
                "source_gbps": source_gbps,
                "coverage": {
                    "ok": True,
                    "covers_entire_file_exactly_once": True,
                    "source_bytes": layout.data_bytes,
                    "source_blocks": result["source_read_count"],
                },
                "h2d_coverage": {
                    "ok": True,
                    "bytes": layout.data_bytes,
                    "blocks": result["source_read_count"],
                },
                "fallback": {"count": 0, "reason": None},
                "quiescence": {
                    "workers_joined": False,
                    "reader_pool_persistent": True,
                    "h2d_events_waited": True,
                    "copies_complete": True,
                    "operation_live": False,
                },
                "reader_pool_reused": True,
                "staging_reused": True,
                "host_registration_reused": True,
                "cuda_stream_reused": True,
                "destination_reused": bool(owner.reused),
                "transport_runtime_reused": True,
                "layout_cache_hit": bool(layout_cache_hit),
                "layout_cache_source": layout.cache_source,
                "metadata_cache_entry_hit": layout.metadata_cache_entry_hit,
                "metadata_cache_identity_match": layout.metadata_cache_identity_match,
                "metadata_cache_hydration_ms": layout.metadata_cache_hydration_ms,
                "metadata_cache_lookup_ms": layout.metadata_cache_lookup_ms,
                "layout_lookup_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "fd_cache_hit": bool(result["fd_cache_hit"]),
                "source_scheduler": result["source_scheduler"],
                "layout_resolve_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "source_go_offset_ms": (source_start_ns - started_ns) / 1e6 if source_start_ns else None,
                "gpu_ready_wall_ms": (last_h2d_ns - started_ns) / 1e6 if last_h2d_ns else None,
                "gpu_ready_tail_ms": (last_h2d_ns - source_end_ns) / 1e6 if last_h2d_ns and source_end_ns else None,
                "destination_growth_ms": self._pool.growth_ms - growth_ms_before,
                "new_capacity_bytes": owner.capacity_bytes if not owner.reused else None,
                "total_load_ms": (finished_ns - started_ns) / 1e6,
                "source": {
                    "source_first_enter_ns": source_start_ns,
                    "source_last_exit_ns": source_end_ns,
                    "readers": result["readers"],
                },
                "transport_lifecycle": self.lifecycle_telemetry(reused=True),
            }
            self._load_count += 1
            return LoadedSafetensors(layout.path, views, owner, layout, stats)

    def _load_c0_source_threads_sync(self, path: str, *, role: str = "model") -> LoadedSafetensors:
        """Load through the restore-created source process and shared arena."""
        started_ns = time.perf_counter_ns()
        started_mono_ns = time.monotonic_ns()
        self._c0_setup_marks = marks = {"load_enter": int(started_mono_ns)}
        from . import golden_io_process_v2 as c0
        from . import golden_qd_transport as qd_transport

        with self._lock:
            if self._poisoned:
                raise RuntimeError("persistent_model_transport_poisoned")
            runtime = self._c0_runtime
            resources = self._c0_resources
            manager = getattr(runtime, "_source_thread_process", None)
            transport = self._c0_source_transport
            if runtime is None or resources is None or manager is None or transport is None:
                raise RuntimeError("source_threads_runtime_not_ready")
            if (
                int(runtime.slot_count) != golden_source_threads.SLOT_COUNT
                or int(runtime.slot_bytes) != golden_source_threads.SLOT_BYTES
            ):
                raise RuntimeError("source_threads_geometry_mismatch")
            if c0.resolve_c0_mmap_lifecycle() not in {"fresh", "whole"}:
                raise RuntimeError("source_threads_unsupported_mmap_lifecycle")

            normalized_path = os.path.abspath(str(path))
            layout_cache_hit = normalized_path in self._layout_cache
            layout_started_ns = time.perf_counter_ns()
            marks["layout_resolve_begin"] = time.monotonic_ns()
            layout = self.inspect(path, role=role)
            marks["layout_resolve_end"] = time.monotonic_ns()
            layout_end_ns = time.perf_counter_ns()
            owner = self._pool.acquire(layout.data_bytes)
            backend = qd_transport.CudaTransferBackend(owner.gpu_tensor, resources=resources)
            self._c0_source_backend.bind(backend)
            transport.begin_operation(backend, destination_size=layout.data_bytes)
            # The range plan is the actual work of sizing every 64 MiB source
            # extent and its destination offset, so the stamps must bracket it.
            marks["range_plan_begin"] = time.monotonic_ns()
            ranges = []
            offset = layout.data_start
            destination = 0
            ordinal = 0
            while destination < layout.data_bytes:
                length = min(golden_source_threads.SLOT_BYTES, layout.data_bytes - destination)
                ranges.append(qd_transport.SourceRange(offset, length, destination, ordinal))
                offset += length
                destination += length
                ordinal += 1
            marks["range_plan_end"] = time.monotonic_ns()
            resources.transport_enter()
            try:
                bridge = golden_source_threads.SourcePlanBridge(manager, transport)
                # PLAN publication only.  It must not imply the source span.
                marks["plan_install_begin"] = time.monotonic_ns()
                published = bridge.publish_all(
                    ranges,
                    generation=self._load_count + 1,
                    path=layout.path,
                    identity=layout.identity,
                    destination_size=layout.data_bytes,
                    role=role,
                )
                marks["plan_install_end"] = time.monotonic_ns()
                # The source pipeline span covers every range published through
                # the last H2D submit.  It is not "plan publication".
                source_pipeline_end_ns = time.monotonic_ns()
                marks["source_pipeline_end"] = source_pipeline_end_ns
                # Hand the source owner's authoritative span to the dispatcher
                # telemetry before it snapshots, so source_final_byte_complete_ns
                # and gpu_ready_tail_ms are real numbers rather than nulls.
                source_span = golden_source_threads.canonical_source_span(
                    manager.snapshot().get("source_operation_records") or []
                )
                transport.note_external_source_span(
                    source_span.get("source_start_ns"), source_span.get("source_end_ns")
                )
                result = transport.finalize_external_ready(
                    ranges, destination_size=layout.data_bytes, materialize_output=False,
                )
                marks["final_drain_end"] = time.monotonic_ns()
                resources.finish_span()
            except BaseException:
                # Abort is bounded.  GoldenQDTransport remains the sole owner
                # of submitted H2D tickets; release the destination only after
                # it proves no event/lease is live.  Otherwise poison and keep
                # the owner reachable rather than unregistering live storage.
                transport._owner_lifetime = owner
                try:
                    transport.cancel(timeout=5.0)
                except BaseException:
                    self._poisoned = True
                try:
                    manager.wait_quiescent(timeout_s=5.0)
                except BaseException:
                    self._poisoned = True
                finally:
                    # The control segment is owned by the runtime ring, which
                    # owns the source process; stop it even when quiescence
                    # could not be proven, or the segment is leaked for the
                    # lifetime of the process.
                    try:
                        manager.stop()
                    except BaseException:
                        self._poisoned = True
                resources.transport_exit(poisoned=True)
                if not self._poisoned and transport.backend_owner_release_allowed():
                    owner.release_storage()
                else:
                    self._poisoned = True
                raise
            resources.transport_exit(poisoned=transport.pool.poisoned)
            # The dispatcher has released every source-process slot only after
            # completion events.  This gate proves no source ownership crosses
            # the model boundary.
            manager.wait_quiescent()
            source_telemetry = manager.snapshot()
            views = self._views(owner.gpu_tensor, layout.tensor_map)
            views_ready_ns = time.monotonic_ns()
            finished_ns = time.perf_counter_ns()
            exact = (
                result.submitted_bytes == layout.data_bytes
                and result.completed_bytes == layout.data_bytes
                and len(result.records) == len(ranges)
            )
            if not exact:
                raise qd_transport.ReconciliationError("source_threads_exact_coverage_failed")
            # Canonical model-level source boundaries.  Operation records are
            # appended on completion, so the first record is NOT the first
            # source start: derive the span from the minimum actual source start
            # and the maximum actual source completion, in one monotonic clock
            # domain, exactly as _load_c0_sync does for the historical reader.
            span = golden_source_threads.canonical_source_span(
                source_telemetry.get("source_operation_records") or []
            )
            source_operation_records = source_telemetry.get("source_operation_records") or []
            source_telemetry_compact = dict(source_telemetry)
            source_telemetry_compact.pop("source_operation_records", None)
            source_start_ns = span.get("source_start_ns")
            source_end_ns = span.get("source_end_ns")
            source_wall_ms = span.get("source_wall_ms")
            source_child_wall_ms = source_wall_ms
            source_gbps = (
                layout.data_bytes / ((source_wall_ms / 1000.0) * 1e9)
                if source_wall_ms and source_wall_ms > 0 else None
            )
            dispatcher_timing = result.telemetry if isinstance(result.telemetry, dict) else {}
            source_final_byte_complete_ns = dispatcher_timing.get(
                "source_final_byte_complete_ns", source_end_ns
            )
            final_h2d_submit_ns = dispatcher_timing.get("final_h2d_submit_ns")
            final_h2d_completion_observed_ns = dispatcher_timing.get(
                "final_h2d_completion_observed_ns"
            )
            first_h2d_submit_ns = dispatcher_timing.get("first_h2d_submit_ns")
            first_h2d_completion_ns = dispatcher_timing.get(
                "first_h2d_completion_observed_ns"
            )
            source_latency_counters = {
                **source_telemetry,
                "source_gbps": source_gbps,
                "source_final_byte_complete_ns": source_final_byte_complete_ns,
                "final_h2d_submit_ns": final_h2d_submit_ns,
                "final_h2d_completion_observed_ns": final_h2d_completion_observed_ns,
                "gpu_ready_tail_ms": (
                    (final_h2d_completion_observed_ns - source_final_byte_complete_ns) / 1e6
                    if final_h2d_completion_observed_ns and source_final_byte_complete_ns
                    else None
                ),
            }
            # Placement is collected from live handles, once per process.  The
            # source owner keeps its child on ``_proc``; ``SharedArenaRing``
            # mirrors the same pid onto ``child_pid`` when it adopts the owner.
            source_owner = getattr(runtime, "_source_thread_process", None)
            source_child_pid = getattr(getattr(source_owner, "_proc", None), "pid", None)
            source_child_pid = source_child_pid or getattr(runtime, "child_pid", None)
            arena_shm = getattr(runtime, "_shm", None)
            arena_name = getattr(arena_shm, "name", None)
            stats = {
                "status": "ok",
                "execution_architecture": "c0_parallel",
                "execution_arm": "c0_parallel",
                "source_engine": "c0_source_owner",
                "source_worker_kind": manager.worker_kind,
                "h2d_engine": "c0_dispatcher_async",
                "mmap_lifecycle": c0.resolve_c0_mmap_lifecycle(),
                "fallback": {"count": 0, "reason": None},
                "c0_arena_bytes": int(runtime.size_bytes),
                "c0_arena_created": bool(runtime.created),
                "c0_arena_reused": bool(self._load_count > 0),
                "source_read_count": published,
                "source_read_bytes": layout.data_bytes,
                "bytes_read": layout.data_bytes,
                "gpu_bytes": layout.data_bytes,
                "h2d_submitted_bytes": int(result.submitted_bytes),
                "h2d_completed_bytes": int(result.completed_bytes),
                "source_wall_ms": source_wall_ms,
                "source_child_wall_ms": source_child_wall_ms,
                "qd_source_io_wall_ms": source_wall_ms,
                "source_gbps": source_gbps,
                "source_go_offset_ms": (
                    (source_start_ns - started_ns) / 1e6 if source_start_ns else None
                ),
                "source_final_byte_complete_ns": source_final_byte_complete_ns,
                "final_h2d_submit_ns": final_h2d_submit_ns,
                "final_h2d_completion_observed_ns": final_h2d_completion_observed_ns,
                "gpu_ready_ns": final_h2d_completion_observed_ns,
                "gpu_ready_wall_ms": (
                    (final_h2d_completion_observed_ns - started_mono_ns) / 1e6
                    if final_h2d_completion_observed_ns else None
                ),
                "gpu_ready_tail_ms": (
                    (final_h2d_completion_observed_ns - source_final_byte_complete_ns) / 1e6
                    if final_h2d_completion_observed_ns and source_final_byte_complete_ns
                    else None
                ),
                "coverage": {
                    "ok": True,
                    "covers_entire_file_exactly_once": True,
                    "source_bytes": layout.data_bytes,
                    "source_blocks": len(ranges),
                },
                "h2d_coverage": {
                    "ok": True,
                    "bytes": int(result.completed_bytes),
                    "blocks": len(result.records),
                },
                "source_thread_telemetry": {
                    **source_telemetry_compact,
                    "source_operation_record_count": len(source_operation_records),
                },
                "source_detail": {
                    "arena_ensure": arena_ensure_detail(runtime),
                    "dispatcher": result.telemetry,
                    "load_setup_marks": {
                        **dict(self._c0_restore_setup_marks), **dict(marks),
                    },
                    "lifecycle": c0.resolve_c0_mmap_lifecycle(),
                    # Scalar-only source concurrency summary.  The full
                    # per-operation record set is far too large to persist, and
                    # these are the numbers that decide whether the source side
                    # is actually running four readers wide or effectively one.
                    "source_concurrency": {
                        "source_operations": int(source_telemetry.get("source_operations") or 0),
                        "effective_reader_concurrency": source_telemetry.get(
                            "effective_reader_concurrency"
                        ),
                        "effective_reader_concurrency_distribution": source_telemetry.get(
                            "effective_reader_concurrency_distribution"
                        ),
                        "time_weighted_effective_concurrency": (
                            source_telemetry.get("time_weighted_reader_concurrency") or {}
                        ).get("effective_concurrency"),
                        "time_weighted_levels_ms": {
                            key: ((value or {}).get("ns") or 0) / 1e6
                            for key, value in (
                                (source_telemetry.get("time_weighted_reader_concurrency") or {}).get(
                                    "levels"
                                ) or {}
                            ).items()
                        },
                        "longest_zero_reader_ms": (
                            (source_telemetry.get("time_weighted_reader_concurrency") or {}).get(
                                "longest_zero_reader_ns"
                            ) or 0
                        ) / 1e6,
                        "below_four_reader_ms": (
                            (source_telemetry.get("time_weighted_reader_concurrency") or {}).get(
                                "below_four_reader_ns"
                            ) or 0
                        ) / 1e6,
                        "slot_wait_ms": (source_telemetry.get("slot_acquire_wait_ns") or 0) / 1e6,
                        "slot_wait_count": source_telemetry.get("slot_acquire_wait_count"),
                        "all_slots_occupied_count": source_telemetry.get(
                            "all_slots_occupied_count"
                        ),
                        "capacity_wait_ms": (source_telemetry.get("capacity_wait_ns") or 0) / 1e6,
                        "capacity_wait_count": source_telemetry.get("capacity_wait_count"),
                        "ready_queue_wait_ms": (source_telemetry.get("ready_queue_wait_ns") or 0) / 1e6,
                        "ready_queue_wait_count": source_telemetry.get("ready_queue_wait_count"),
                        "release_count": source_telemetry.get("release_count"),
                        "pacing_wait_count": source_telemetry.get("pacing_wait_count"),
                        "pacing_zero_delay_count": source_telemetry.get("pacing_zero_delay_count"),
                        "min_source_gap_ms": (source_telemetry.get("min_source_gap_ns") or 0) / 1e6,
                        "pacer_gap_violation_count": source_telemetry.get(
                            "pacer_gap_violation_count"
                        ),
                        "mmap_map_count": source_telemetry.get("mmap_map_count"),
                        "mmap_unmap_count": source_telemetry.get("mmap_unmap_count"),
                        "source_span_ms": span.get("source_wall_ms"),
                    },
                    "source_latency": summarize_source_operations(
                        source_operation_records,
                        source_span=span,
                        counters_source=source_latency_counters,
                    ),
                    "first_h2d": summarize_first_h2d(
                        source_operation_records,
                        source_start_ns=source_start_ns,
                        first_h2d_submit_ns=first_h2d_submit_ns,
                        first_h2d_completion_ns=first_h2d_completion_ns,
                    ),
                    "placement": collect_placement_telemetry(
                        arena_name=arena_name,
                        arena_bytes=getattr(runtime, "size_bytes", None),
                        source_child_pid=source_child_pid,
                    ),
                },
                "quiescence": {
                    "workers_joined": False,
                    "reader_pool_persistent": True,
                    "h2d_events_waited": True,
                    "copies_complete": True,
                    "operation_live": False,
                    "source_slots_free": True,
                },
                "reader_pool_reused": True,
                "staging_reused": True,
                "host_registration_reused": bool(self._load_count > 0),
                "cuda_stream_reused": bool(self._load_count > 0),
                "destination_reused": bool(owner.reused),
                "transport_runtime_reused": True,
                "layout_cache_hit": bool(layout_cache_hit),
                "layout_cache_source": layout.cache_source,
                "metadata_cache_entry_hit": layout.metadata_cache_entry_hit,
                "metadata_cache_identity_match": layout.metadata_cache_identity_match,
                "metadata_cache_hydration_ms": layout.metadata_cache_hydration_ms,
                "metadata_cache_lookup_ms": layout.metadata_cache_lookup_ms,
                "layout_lookup_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "layout_resolve_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "views_ready_ns": views_ready_ns,
                "total_load_ms": (finished_ns - started_ns) / 1e6,
                "source": {
                    "source_first_enter_ns": source_start_ns,
                    "source_last_exit_ns": source_end_ns,
                    "readers": source_telemetry.get("reader_identities", []),
                },
                "transport_lifecycle": self.lifecycle_telemetry(reused=self._load_count > 0),
            }
            self._load_count += 1
            return LoadedSafetensors(layout.path, views, owner, layout, stats)

    def _load_c0_sync(self, path: str, *, role: str = "model") -> LoadedSafetensors:
        """Load one checkpoint through the persistent C0 shared arena.

        C0 body, M2 engines: the C0 arena stays the backing resource,
        the C0 child workers produce bytes with the frozen exact-window mmap
        engine (``mmap_fresh`` selection), and the shared dispatcher submits
        H2D asynchronously over the C0-registered mapping with per-transfer
        completion gating.  No M2 staging arena is built, no reader processes
        are forked here, and no standalone M2 loader wrapper is entered.
        """
        if self._c0_source_threads_enabled:
            return self._load_c0_source_threads_sync(path, role=role)
        started_ns = time.perf_counter_ns()
        started_mono_ns = time.monotonic_ns()
        # Passive per-load setup waterfall (observation-only monotonic_ns).
        self._c0_setup_marks = marks = {}
        marks["load_enter"] = int(started_mono_ns)

        with self._lock:
            if self._poisoned:
                raise RuntimeError("persistent_model_transport_poisoned")
            self.prepare_cpu()
            self.initialize_cuda()
            assert self._pool is not None
            assert self._c0_runtime is not None
            assert self._c0_resources is not None
            from . import golden_qd_transport as qd_transport
            from . import golden_io_process_v2 as c0

            geo = resolve_c0_transport_geometry()
            if int(self._c0_runtime.slot_bytes) != int(geo["required_slot_bytes"]):
                raise RuntimeError(
                    "c0_transport_geometry_unsupported:"
                    f"slot_bytes={int(self._c0_runtime.slot_bytes)}"
                    f"!=required_slot_bytes={int(geo['required_slot_bytes'])}"
                    f"for {geo['name']}"
                )
            normalized_path = os.path.abspath(str(path))
            layout_cache_hit = normalized_path in self._layout_cache
            layout_started_ns = time.perf_counter_ns()
            marks["layout_resolve_begin"] = int(time.monotonic_ns())
            layout = self.inspect(path, role=role)
            marks["layout_resolve_end"] = int(time.monotonic_ns())
            layout_end_ns = time.perf_counter_ns()
            marks["owner_acquire_begin"] = int(time.monotonic_ns())
            owner = self._pool.acquire(layout.data_bytes)
            marks["owner_acquire_end"] = int(time.monotonic_ns())
            marks["backend_create_begin"] = int(time.monotonic_ns())
            backend = qd_transport.CudaTransferBackend(
                owner.gpu_tensor, resources=self._c0_resources
            )
            marks["backend_create_end"] = int(time.monotonic_ns())

            config = qd_transport.TransportConfig(
                queue_depth=int(geo["queue_depth"]),
                block_bytes=int(geo["block_bytes"]),
                staging_slots=int(self._c0_runtime.slot_count),
                ready_queue_capacity=int(self._c0_runtime.slot_count),
                producer_workers=int(geo["producer_workers"]),
                capacity_class=str(geo["capacity_class"]),
                h2d_target_bytes=int(geo["h2d_target_bytes"]),
                aggregation_enabled=(
                    False if c0.c0_dma_ring_enabled()
                    else bool(geo["aggregation_enabled"])
                ),
            )
            marks["pool_create_begin"] = int(time.monotonic_ns())
            pool = self._c0_runtime.new_stage_pool()
            marks["pool_create_end"] = int(time.monotonic_ns())

            marks["dispatcher_create_begin"] = int(time.monotonic_ns())
            dispatcher = qd_transport.GoldenQDTransport(
                config,
                backend,
                arm="static_e27",
                pool=pool,
                diagnostics=True,
                resources=self._c0_resources,
            )
            marks["dispatcher_create_end"] = int(time.monotonic_ns())

            ranges = []
            block_id = 0
            offset = layout.data_start
            remaining = layout.data_bytes
            while remaining > 0:
                length = min(int(geo["block_bytes"]), remaining)
                ranges.append(
                    qd_transport.SourceRange(
                        offset,
                        length,
                        block_id * int(geo["block_bytes"]),
                        block_id,
                    )
                )
                block_id += 1
                offset += length
                remaining -= length
            source = self._c0_runtime.stage_reader(
                role="model",
                pool=pool,
                source=layout.path,
                source_identity=tuple(int(value) for value in layout.identity),
                mmap_lifecycle=c0.resolve_c0_mmap_lifecycle(),
            )
            marks["range_plan_begin"] = int(time.monotonic_ns())
            # NOTE: ranges list built above; mark covers plan assembly.
            marks["range_plan_end"] = int(time.monotonic_ns())
            marks["dispatcher_execute_enter"] = int(time.monotonic_ns())
            result = dispatcher.execute(
                ranges,
                source,
                destination_size=layout.data_bytes,
                materialize_output=False,
                parse_count=1,
                owner=owner,
                owner_count=1,
                adoption_result="transport_backing_pending",
            )
            dispatcher.snapshot_quiescence()
            views = self._views(owner.gpu_tensor, layout.tensor_map)
            views_ready_ns = time.monotonic_ns()
            qd_timing = result.telemetry if isinstance(result.telemetry, dict) else {}
            # Stages A-D measurement: summarize already-accumulated reader +
            # dispatcher evidence (no I/O, no synchronization).  Full
            # Per-fill raw lifecycle records ride only the explicit window-trace
            # selector; OFF does not allocate or retain this evidence.
            source_detail: dict[str, Any] = {
                "transport_geometry": str(geo["name"]),
                "load_setup_marks": dict(marks),
                "arena_ensure": arena_ensure_detail(self._c0_runtime),
                "reader": summarize_c0_reader(source),
                "dispatcher": summarize_dispatcher(dispatcher),
            }
            if bool(getattr(source, "_window_trace_enabled", False)):
                try:
                    snapshot = getattr(source, "window_trace_snapshot", None)
                    if callable(snapshot):
                        records, dropped = snapshot()
                    else:
                        records = list(getattr(source, "_window_trace_records", []) or [])
                        dropped = int(getattr(source, "_window_trace_dropped", 0) or 0)
                    source_detail["window_trace"] = records[:_C0_WINDOW_TRACE_LIMIT]
                    source_detail["window_trace_truncated"] = (
                        len(records) > _C0_WINDOW_TRACE_LIMIT or dropped > 0
                    )
                    source_detail["window_trace_dropped"] = int(dropped)
                    _first_op = None
                    for _rec in records:
                        if isinstance(_rec, dict) and _rec.get("operation_ordinal") == 0:
                            _first_op = {
                                "first_control_request_publish_ns": _rec.get("control_submit_ns"),
                                "first_control_enqueue_ns": _rec.get("control_enqueue_ns"),
                                "first_work_available_ns": _rec.get("work_available_ns"),
                                "first_reader_claim_ns": _rec.get("reader_claim_ns"),
                                "first_mmap_begin_ns": _rec.get("mmap_start_ns"),
                                "first_memcpy_begin_ns": _rec.get("memcpy_start_ns"),
                                "first_source_done_ns": _rec.get("copy_end_ns"),
                                "first_reader": _rec.get("reader"),
                                "first_lane": _rec.get("lane"),
                            }
                            break
                    source_detail["first_op_marks"] = _first_op
                except BaseException:
                    source_detail["window_trace"] = None
            child_start_ns = int(getattr(source, "first_child_read_start_mono_ns", 0) or 0)
            child_end_ns = int(getattr(source, "last_child_read_end_mono_ns", 0) or 0)
            source_child_wall_ms = (
                (child_end_ns - child_start_ns) / 1e6
                if child_start_ns and child_end_ns and child_end_ns >= child_start_ns
                else None
            )
            source_fill_wall_ms = float(getattr(source, "fill_wall_ns", 0) or 0) / 1e6
            source_wall_ms = source_child_wall_ms or source_fill_wall_ms
            source_gbps = (
                layout.data_bytes / ((source_wall_ms / 1000.0) * 1e9)
                if source_wall_ms and source_wall_ms > 0 else None
            )
            finished_ns = time.perf_counter_ns()
            total_load_ms = (finished_ns - started_ns) / 1e6
            source_final_byte_complete_ns = qd_timing.get(
                "source_final_byte_complete_ns",
                child_end_ns or None,
            )
            final_h2d_submit_ns = qd_timing.get("final_h2d_submit_ns")
            final_h2d_completion_observed_ns = qd_timing.get(
                "final_h2d_completion_observed_ns"
            )
            stats = {
                "status": "ok",
                # Identity: C0 execution body, M2 source kernel, C0 shared
                # dispatch for H2D.  Never report the M2 execution arm here.
                "execution_architecture": "c0_parallel",
                "execution_arm": "c0_parallel",
                "source_engine": "m2_exact_window",
                "h2d_engine": "c0_dispatcher_async",
                "c0_arena_bytes": int(self._c0_runtime.size_bytes),
                "c0_arena_created": bool(self._c0_runtime.created),
                "c0_arena_reused": bool(self._load_count > 0),
                "source_detail": source_detail,
                "source_read_count": int(getattr(source, "fills", 0) or len(ranges)),
                "source_read_bytes": layout.data_bytes,
                "bytes_read": layout.data_bytes,
                "gpu_bytes": layout.data_bytes,
                "h2d_submitted_bytes": int(result.submitted_bytes),
                "h2d_completed_bytes": int(result.completed_bytes),
                "source_wall_ms": source_wall_ms,
                "source_child_wall_ms": source_child_wall_ms,
                "source_fill_wall_ms": source_fill_wall_ms,
                "qd_source_io_wall_ms": source_wall_ms,
                "source_gbps": source_gbps,
                "coverage": {
                    "ok": int(result.completed_bytes) == layout.data_bytes,
                    "covers_entire_file_exactly_once": int(result.completed_bytes) == layout.data_bytes,
                    "source_bytes": layout.data_bytes,
                    "source_blocks": len(ranges),
                },
                "h2d_coverage": {
                    "ok": int(result.completed_bytes) == layout.data_bytes,
                    "bytes": int(result.completed_bytes),
                    "blocks": len(result.records),
                },
                "fallback": {"count": 0, "reason": None},
                "quiescence": {
                    "workers_joined": False,
                    "reader_pool_persistent": True,
                    "h2d_events_waited": True,
                    "copies_complete": True,
                    "operation_live": False,
                },
                "reader_pool_reused": self._load_count > 0,
                "staging_reused": True,
                "host_registration_reused": self._load_count > 0,
                "cuda_stream_reused": self._load_count > 0,
                "destination_reused": bool(owner.reused),
                "transport_runtime_reused": self._load_count > 0,
                "layout_cache_hit": bool(layout_cache_hit),
                "layout_cache_source": layout.cache_source,
                "metadata_cache_entry_hit": layout.metadata_cache_entry_hit,
                "metadata_cache_identity_match": layout.metadata_cache_identity_match,
                "metadata_cache_hydration_ms": layout.metadata_cache_hydration_ms,
                "metadata_cache_lookup_ms": layout.metadata_cache_lookup_ms,
                "layout_lookup_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "fd_cache_hit": bool(getattr(source, "fd_reuse_count", 0)),
                "layout_resolve_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "source_go_offset_ms": (int(getattr(source, "first_source_read_start_mono_ns", 0) or 0) - started_ns) / 1e6,
                "source_final_byte_complete_ns": source_final_byte_complete_ns,
                "final_h2d_submit_ns": final_h2d_submit_ns,
                "final_h2d_completion_observed_ns": final_h2d_completion_observed_ns,
                "gpu_ready_ns": final_h2d_completion_observed_ns,
                "views_ready_ns": views_ready_ns,
                "gpu_ready_wall_ms": (
                    (final_h2d_completion_observed_ns - started_mono_ns) / 1e6
                    if final_h2d_completion_observed_ns else None
                ),
                "gpu_ready_tail_ms": (
                    (final_h2d_completion_observed_ns - source_final_byte_complete_ns) / 1e6
                    if final_h2d_completion_observed_ns and source_final_byte_complete_ns
                    else None
                ),
                "destination_growth_ms": self._pool.growth_ms,
                "new_capacity_bytes": owner.capacity_bytes if not owner.reused else None,
                "total_load_ms": total_load_ms,
                "source": {
                    "source_first_enter_ns": getattr(source, "first_child_read_start_mono_ns", None),
                    "source_last_exit_ns": getattr(source, "last_child_read_end_mono_ns", None),
                    "readers": [],
                },
                "transport_lifecycle": self.lifecycle_telemetry(reused=self._load_count > 0),
            }
            self._load_count += 1
            return LoadedSafetensors(layout.path, views, owner, layout, stats)

    def _abort_transfer(self, generation: int) -> None:
        if self._failed is not None:
            if self._scheduler_lock is None:
                self._failed.value = 1
            else:
                with self._scheduler_lock:
                    self._failed.value = 1
        if self.staging is not None:
            for lane in range(self.qd):
                self.staging["consumed"][lane].value = int(self.staging["published"][lane].value)
        outstanding = {
            reader_id
            for reader_id in range(self.qd)
            if reader_id not in self._reader_done
        }
        deadline = time.monotonic() + ABORT_TIMEOUT_S
        while outstanding and time.monotonic() < deadline:
            for reader_id in tuple(outstanding):
                process = self._children[reader_id]
                if not process.is_alive():
                    outstanding.remove(reader_id)
                    continue
                connection = self._connections[reader_id]
                if not connection.poll(0.05):
                    continue
                message = connection.recv()
                if (
                    message.get("command") != "LOAD_DONE"
                    or int(message.get("generation", -1)) != generation
                ):
                    raise RuntimeError(f"persistent_reader_abort_protocol:{reader_id}")
                self._reader_done.add(reader_id)
                outstanding.remove(reader_id)
        if outstanding:
            for reader_id in outstanding:
                process = self._children[reader_id]
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=1.0)
            raise RuntimeError(f"persistent_reader_abort_timeout:{sorted(outstanding)}")

    def _copy_until_complete(
        self,
        layout: SafetensorsLayout,
        generation: int,
        owner: GpuAllocationLease,
    ) -> dict[str, Any]:
        assert self.staging is not None
        staging = self.staging
        lib = self._cuda["lib"]
        stream = self._cuda["stream"]
        pending: collections.deque[tuple[int, int, int, int, int]] = collections.deque()
        next_issue = [0] * self.qd
        consumed = [0] * self.qd
        done: dict[int, dict[str, Any]] = {}
        event_cursor = 0
        first_source = 0
        last_source = 0
        last_h2d = 0
        deadline = time.monotonic() + TRANSFER_TIMEOUT_S
        h2d_ranges: list[tuple[int, int]] = []
        destination_ptr = int(owner.gpu_tensor.data_ptr())

        def collect_done() -> None:
            nonlocal first_source, last_source
            for reader_id, connection in enumerate(self._connections):
                if reader_id in done or not connection.poll():
                    continue
                message = connection.recv()
                if message.get("command") != "LOAD_DONE" or int(message.get("generation", -1)) != generation:
                    raise RuntimeError("persistent_reader_completion_generation_mismatch")
                done[reader_id] = message
                self._reader_done.add(reader_id)
                if message.get("status") != "ok":
                    raise RuntimeError(f"persistent_reader_failed:{message.get('error')}")
                enter = int(message.get("first_enter_ns") or 0)
                exit_ns = int(message.get("last_exit_ns") or 0)
                if enter:
                    first_source = enter if not first_source else min(first_source, enter)
                if exit_ns:
                    last_source = max(last_source, exit_ns)

        def complete_oldest() -> None:
            nonlocal last_h2d
            event_index, lane, sequence, destination_offset, length = pending.popleft()
            event = self._event_pool[event_index]
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not source_race_gpu._wait_event(lib, event, remaining):
                raise RuntimeError("persistent_h2d_event_timeout")
            consumed[lane] = sequence + 1
            staging["consumed"][lane].value = sequence + 1
            last_h2d = time.perf_counter_ns()

        while len(done) < self.qd or pending or any(
            next_issue[lane] < int(staging["published"][lane].value)
            for lane in range(self.qd)
        ):
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"persistent_transport_timeout:done={len(done)}/{self.qd}:pending={len(pending)}"
                )
            dead_readers = [
                reader_id
                for reader_id, process in enumerate(self._children)
                if not process.is_alive()
            ]
            if dead_readers:
                raise RuntimeError(f"persistent_reader_process_died:{dead_readers}")
            collect_done()
            issued = False
            for lane in range(self.qd):
                published = int(staging["published"][lane].value)
                while next_issue[lane] < published:
                    if len(pending) >= len(self._event_pool):
                        complete_oldest()
                    sequence = next_issue[lane]
                    slot = sequence % self.staging_slots
                    destination_offset = int(staging["slot_off"][lane][slot])
                    length = int(staging["slot_len"][lane][slot])
                    host = int(staging["seg_base"]) + lane * int(staging["lane_bytes"]) + slot * self.block_bytes
                    event_index = event_cursor % len(self._event_pool)
                    event_cursor += 1
                    event = self._event_pool[event_index]
                    source_race_gpu._check(
                        lib["cuMemcpyHtoDAsync_v2"](
                            ctypes.c_uint64(destination_ptr + destination_offset),
                            ctypes.c_void_p(host),
                            ctypes.c_size_t(length),
                            stream,
                        ),
                        "cuMemcpyHtoDAsync",
                    )
                    source_race_gpu._check(lib["cuEventRecord"](event, stream), "cuEventRecord")
                    pending.append((event_index, lane, sequence, destination_offset, length))
                    h2d_ranges.append((destination_offset, length))
                    next_issue[lane] += 1
                    issued = True
            if pending and (not issued or len(pending) >= len(self._event_pool) or len(done) == self.qd):
                complete_oldest()
            elif not issued:
                time.sleep(0.0002)

        while pending:
            complete_oldest()
        total_blocks = (layout.data_bytes + self.block_bytes - 1) // self.block_bytes
        source_records = [
            record
            for message in done.values()
            for record in (message.get("records") or [])
        ]
        expected_ranges = [
            (block_id * self.block_bytes, min(self.block_bytes, layout.data_bytes - block_id * self.block_bytes))
            for block_id in range(total_blocks)
        ]
        actual_source_ranges = sorted(
            (int(record.get("offset", -1)), int(record.get("length", -1)))
            for record in source_records
        )
        if actual_source_ranges != expected_ranges:
            raise RuntimeError("persistent_source_coverage_range_mismatch")
        if sorted(h2d_ranges) != expected_ranges:
            raise RuntimeError("persistent_h2d_coverage_range_mismatch")
        source_read_count = len(source_records)
        if source_read_count != total_blocks:
            raise RuntimeError("persistent_source_coverage_count_mismatch")
        claims = sorted(int(record["gate_claim_ns"]) for record in source_records)
        claim_gaps_ms = [
            (claims[index] - claims[index - 1]) / 1e6
            for index in range(1, len(claims))
        ]
        if claim_gaps_ms and min(claim_gaps_ms) < MIN_LAUNCH_GAP_NS / 1e6:
            raise RuntimeError("persistent_source_launch_gap_violation")
        return {
            "owner": owner,
            "source_start_ns": first_source,
            "source_end_ns": last_source,
            "last_h2d_ns": last_h2d,
            "source_read_count": source_read_count,
            "fd_cache_hit": bool(done) and all(
                bool(message.get("fd_cache_hit")) for message in done.values()
            ),
            "readers": done,
            "source_scheduler": {
                "selfservice": True,
                "sticky_lanes": True,
                "lane_ranges": [list(bounds) for bounds in _sticky_lane_ranges(total_blocks)],
                "affinity_breaks": sum(
                    int(message.get("affinity_breaks") or 0) for message in done.values()
                ),
                "configured_min_gap_ms": MIN_LAUNCH_GAP_NS / 1e6,
                "observed_min_global_claim_gap_ms": min(claim_gaps_ms) if claim_gaps_ms else None,
            },
        }

    @staticmethod
    def _views(gpu_tensor: Any, tensor_map: tuple[dict[str, Any], ...]) -> dict[str, Any]:
        import torch

        result: dict[str, Any] = {}
        for item in tensor_map:
            dtype = getattr(torch, DTYPE_NAMES[item["dtype"]])
            element_size = int(getattr(torch, "empty")((), dtype=dtype).element_size())
            offset = int(item["offset"])
            length = int(item["length"])
            if offset % element_size or length % element_size:
                raise RuntimeError(f"unaligned_tensor_view:{item['key']}")
            expected = element_size
            for dimension in item["shape"]:
                expected *= int(dimension)
            if expected != length:
                raise RuntimeError(f"tensor_byte_length_mismatch:{item['key']}")
            result[item["key"]] = gpu_tensor[offset:offset + length].view(dtype).view(tuple(item["shape"]))
        return result

    def lifecycle_telemetry(self, *, reused: bool) -> dict[str, Any]:
        result = {
            "transport_runtime_reused": bool(reused),
            "reader_pool_reused": bool(reused and self._prepared),
            "staging_reused": bool(self.staging is not None),
            "host_registration_reused": bool(reused and self._cuda_ready),
            "cuda_stream_reused": bool(reused and self._cuda_ready),
            "event_pool_size": len(self._event_pool),
            "staging_bytes": self.staging_bytes,
            "source_qd": self.qd,
            "source_block_bytes": self.block_bytes,
            "source_min_launch_gap_ms": MIN_LAUNCH_GAP_NS / 1e6,
            "models_generation": self._models_generation,
        }
        if self._pool is not None:
            result["destination_pool"] = self._pool.telemetry()
        return result

    def release_lease(self, owner: Any) -> None:
        if self._pool is not None and getattr(owner, "_pool", None) is self._pool:
            owner.release_storage()

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            for connection in self._connections:
                try:
                    connection.send({"command": "EXIT"})
                except BaseException:
                    pass
            for process in self._children:
                process.join(timeout=30.0)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5.0)
            if self._cuda_ready and self._c0_runtime is not None:
                # C0 teardown: release the shared dispatcher resources and the
                # arena runtime.  No M2 staging/registration/stream exists here.
                try:
                    if self._c0_source_transport is not None:
                        self._c0_source_transport.shutdown(timeout=10.0)
                except BaseException as exc:
                    # Do not unregister the shared arena while a dispatcher
                    # may still own a CUDA event/ticket.  Retain every owner
                    # reachable for a later bounded cleanup attempt.
                    self._poisoned = True
                    raise RuntimeError("c0_source_transport_shutdown_unproven") from exc
                try:
                    self._c0_resources.close()
                except BaseException as exc:
                    self._poisoned = True
                    raise RuntimeError("c0_transfer_resources_close_unproven") from exc
                try:
                    from . import golden_io_process_v2 as c0
                    c0.close_runtime()
                except BaseException:
                    self._poisoned = True
                    raise
                self._closed = True
                return
            if self._cuda_ready:
                lib = self._cuda["lib"]
                source_race_gpu._check(
                    lib["cuCtxSetCurrent"](self._cuda["ctx"]),
                    "cuCtxSetCurrent",
                )
                for event in self._event_pool:
                    lib["cuEventDestroy_v2"](event)
                lib["cuStreamDestroy_v2"](self._cuda["stream"])
                if self.staging is not None:
                    lib["cuMemHostUnregister"](ctypes.c_void_p(int(self.staging["seg_base"])))
            if self.staging is not None:
                try:
                    self.staging["_mm"].close()
                except BaseException:
                    pass
                shm = self.staging.get("_shm")
                if shm is not None:
                    try:
                        shm.close()
                    except BaseException:
                        pass
                    try:
                        shm.unlink()
                    except BaseException:
                        pass
            self._closed = True


_TRANSPORT: GoldenModelTransport | None = None
_TRANSPORT_LOCK = threading.Lock()


def get_golden_model_transport() -> GoldenModelTransport:
    global _TRANSPORT
    with _TRANSPORT_LOCK:
        if _TRANSPORT is None or _TRANSPORT._closed:
            _TRANSPORT = GoldenModelTransport()
        return _TRANSPORT


def _shutdown_transport() -> None:
    if _TRANSPORT is not None:
        try:
            _TRANSPORT.shutdown()
        except BaseException:
            pass


atexit.register(_shutdown_transport)


__all__ = [
    "BLOCK_BYTES",
    "GpuAllocationLease",
    "GpuDestinationPool",
    "GoldenModelTransport",
    "LayoutPreresolve",
    "LoadedSafetensors",
    "SafetensorsLayout",
    "get_golden_model_transport",
]
