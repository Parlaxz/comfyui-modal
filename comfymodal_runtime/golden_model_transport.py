"""Persistent, role-neutral safetensors transport for Golden model loads."""

from __future__ import annotations

import asyncio
import atexit
import collections
import ctypes
import json
import multiprocessing as mp
import os
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any

from . import m2_source_core
from . import source_race_gpu

QD = 4
BLOCK_BYTES = 64 * 1024 * 1024
STAGING_SLOTS = 1
STAGING_BYTES = QD * BLOCK_BYTES
LAYOUT_CACHE_LIMIT = 3
FD_CACHE_LIMIT = 4
TRANSFER_TIMEOUT_S = 300.0

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


class GpuAllocationLease:
    """An explicit active lease over one reusable generic CUDA allocation."""

    def __init__(self, pool: "GpuDestinationPool", tensor: Any, capacity: int, reused: bool):
        self._pool = pool
        self._tensor = tensor
        self.capacity_bytes = int(capacity)
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
        self._leases: list[GpuAllocationLease] = []
        self._lock = threading.Lock()
        self.growth_count = 0
        self.growth_ms = 0.0

    def acquire(self, required_bytes: int) -> GpuAllocationLease:
        required_bytes = int(required_bytes)
        if required_bytes < 1:
            raise ValueError("gpu_destination_bytes_must_be_positive")
        with self._lock:
            for lease in self._leases:
                if not lease.released and lease._tensor is not None:
                    continue
                if lease.capacity_bytes >= required_bytes:
                    lease.released = False
                    lease.reused = True
                    return lease
        import torch

        started = time.perf_counter()
        with torch.cuda.device(self.device):
            tensor = getattr(torch, "empty")(required_bytes, dtype=getattr(torch, "uint8"), device=self.device)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        lease = GpuAllocationLease(self, tensor, required_bytes, reused=False)
        with self._lock:
            self._leases.append(lease)
            self.growth_count += 1
            self.growth_ms += elapsed_ms
        return lease

    def release(self, lease: GpuAllocationLease) -> None:
        if lease not in self._leases:
            raise RuntimeError("gpu_allocation_lease_unknown")

    def telemetry(self) -> dict[str, Any]:
        with self._lock:
            capacities = [int(lease.capacity_bytes) for lease in self._leases]
            active = sum(1 for lease in self._leases if not lease.released)
        return {
            "allocation_count": len(capacities),
            "active_lease_count": active,
            "capacity_bytes": sum(capacities),
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


def _file_identity(path: str) -> tuple[int, int, int, int]:
    stat_result = os.stat(path)
    return (
        int(getattr(stat_result, "st_dev", 0)),
        int(getattr(stat_result, "st_ino", 0)),
        int(stat_result.st_size),
        int(getattr(stat_result, "st_mtime_ns", 0)),
    )


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


class GoldenModelTransport:
    """One persistent, path-driven M2 transport for all model roles."""

    def __init__(self, *, qd: int = QD, block_bytes: int = BLOCK_BYTES):
        if int(qd) != QD or int(block_bytes) != BLOCK_BYTES:
            raise ValueError("GoldenModelTransport geometry is fixed at QD4/64MiB")
        self.qd = QD
        self.block_bytes = BLOCK_BYTES
        self.staging_slots = (
            2
            if (
                str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING") or "").strip().lower()
                in {"1", "true", "yes", "on"}
                and str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY") or "").strip().lower()
                == "qd4_64"
            )
            else STAGING_SLOTS
        )
        self.staging_bytes = self.qd * self.staging_slots * self.block_bytes
        self.staging_backing = "posix" if self.staging_slots > 1 else "anonymous"
        self.staging: dict[str, Any] | None = None
        self._ctx: Any = None
        self._children: list[Any] = []
        self._connections: list[Any] = []
        self._prepared = False
        self._cuda_ready = False
        self._cuda: dict[str, Any] = {}
        self._event_pool: list[Any] = []
        self._layout_cache: collections.OrderedDict[str, SafetensorsLayout] = collections.OrderedDict()
        self._models_generation = ""
        self._generation = 0
        self._lock = threading.RLock()
        self._pool: GpuDestinationPool | None = None
        self._c0_runtime: Any = None
        self._c0_resources: Any = None
        self._c0_enabled = (
            str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING") or "").strip().lower()
            in {"1", "true", "yes", "on"}
            and str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE") or "").strip().lower()
            == "mmap_fresh"
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
                self._prepared = True
                return self.lifecycle_telemetry(reused=False)
            if os.name == "nt" or "fork" not in mp.get_all_start_methods():
                raise RuntimeError("persistent_m2_requires_fork")
            self._ctx = mp.get_context("fork")
            self.staging = source_race_gpu.build_staging(
                self.qd,
                self.staging_slots,
                self.block_bytes,
                prefault=False,
                backing=self.staging_backing,
            )
            for reader_id in range(self.qd):
                parent_conn, child_conn = self._ctx.Pipe(duplex=True)
                process = self._ctx.Process(
                    target=m2_source_core.persistent_reader_main,
                    args=(reader_id, child_conn, self.staging, FD_CACHE_LIMIT),
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
            if self._c0_enabled:
                from . import golden_io_process_v2 as c0
                from . import golden_qd_transport as qd_transport
                self._c0_runtime = c0.ensure_arena_runtime()
                self._c0_resources = qd_transport.GoldenTransferResources.create_shared(
                    slot_count=int(self._c0_runtime.slot_count),
                    slot_bytes=int(self._c0_runtime.slot_bytes),
                    device=target,
                )
                self._pool = GpuDestinationPool(target)
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
            self._cuda_ready = True
            return self.lifecycle_telemetry(reused=False)

    def update_models_generation(self, generation: str | None) -> None:
        selected = str(generation or "")
        if selected == self._models_generation:
            return
        self._models_generation = selected
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

    def inspect(self, path: str) -> SafetensorsLayout:
        normalized = os.path.abspath(str(path))
        identity = _file_identity(normalized)
        cached = self._layout_cache.get(normalized)
        if cached is not None and cached.identity == identity:
            self._layout_cache.move_to_end(normalized)
            return cached
        layout = _parse_layout(normalized, identity)
        self._layout_cache[normalized] = layout
        self._layout_cache.move_to_end(normalized)
        while len(self._layout_cache) > LAYOUT_CACHE_LIMIT:
            self._layout_cache.popitem(last=False)
        return layout

    async def load(self, path: str) -> LoadedSafetensors:
        return await asyncio.to_thread(self._load_sync, path)

    def load_sync(self, path: str) -> LoadedSafetensors:
        return self._load_sync(path)

    def _load_sync(self, path: str) -> LoadedSafetensors:
        if self._c0_enabled:
            return self._load_c0_sync(path)
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
            layout = self.inspect(path)
            layout_end_ns = time.perf_counter_ns()
            total_blocks = (layout.data_bytes + self.block_bytes - 1) // self.block_bytes
            lanes = [[] for _ in range(self.qd)]
            for block_id in range(total_blocks):
                lanes[block_id % self.qd].append(block_id)
            self._generation += 1
            generation = self._generation
            for lane in range(self.qd):
                staging["published"][lane].value = 0
                staging["consumed"][lane].value = 0
            identity = tuple(int(value) for value in layout.identity)
            for reader_id, connection in enumerate(self._connections):
                connection.send({
                    "command": "LOAD",
                    "generation": generation,
                    "path": layout.path,
                    "identity": identity,
                    "source_offset": layout.data_start,
                    "data_bytes": layout.data_bytes,
                    "read_bytes": self.block_bytes,
                    "block_ids": lanes[reader_id],
                })

            allocation_future = None
            allocation_executor = None
            if self._pool is not None:
                from concurrent.futures import ThreadPoolExecutor
                allocation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="golden-destination")
                allocation_future = allocation_executor.submit(self._pool.acquire, layout.data_bytes)
            self._cuda["lib"]["cuCtxSetCurrent"](self._cuda["ctx"])
            try:
                result = self._copy_until_complete(layout, generation, allocation_future)
            except BaseException:
                self._abort_transfer(generation)
                if allocation_future is not None:
                    try:
                        allocation_future.result().release_storage()
                    except BaseException:
                        pass
                self._poisoned = True
                raise
            finally:
                if allocation_executor is not None:
                    allocation_executor.shutdown(wait=True)
            owner = result["owner"]
            views = self._views(owner.gpu_tensor, layout.tensor_map)
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
                "reader_pool_reused": self._load_count > 0,
                "staging_reused": True,
                "host_registration_reused": self._load_count > 0,
                "cuda_stream_reused": self._load_count > 0,
                "destination_reused": bool(owner.reused),
                "transport_runtime_reused": self._load_count > 0,
                "layout_cache_hit": bool(layout_cache_hit),
                "fd_cache_hit": bool(result["fd_cache_hit"]),
                "layout_resolve_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "source_go_offset_ms": (source_start_ns - started_ns) / 1e6 if source_start_ns else None,
                "gpu_ready_wall_ms": (last_h2d_ns - started_ns) / 1e6 if last_h2d_ns else None,
                "gpu_ready_tail_ms": (last_h2d_ns - source_end_ns) / 1e6 if last_h2d_ns and source_end_ns else None,
                "destination_growth_ms": self._pool.growth_ms if self._pool else None,
                "new_capacity_bytes": owner.capacity_bytes if not owner.reused else None,
                "total_load_ms": (finished_ns - started_ns) / 1e6,
                "source": {
                    "source_first_enter_ns": source_start_ns,
                    "source_last_exit_ns": source_end_ns,
                    "readers": result["readers"],
                },
                "transport_lifecycle": self.lifecycle_telemetry(reused=self._load_count > 0),
            }
            self._load_count += 1
            return LoadedSafetensors(layout.path, views, owner, layout, stats)

    def _load_c0_sync(self, path: str) -> LoadedSafetensors:
        started_ns = time.perf_counter_ns()
        with self._lock:
            if self._poisoned:
                raise RuntimeError("persistent_model_transport_poisoned")
            self.prepare_cpu()
            self.initialize_cuda()
            assert self._pool is not None
            assert self._c0_runtime is not None
            assert self._c0_resources is not None
            from . import golden_qd_transport as qd_transport

            normalized_path = os.path.abspath(str(path))
            layout_cache_hit = normalized_path in self._layout_cache
            layout_started_ns = time.perf_counter_ns()
            layout = self.inspect(path)
            layout_end_ns = time.perf_counter_ns()
            owner = self._pool.acquire(layout.data_bytes)
            backend = qd_transport.CudaTransferBackend(
                owner.gpu_tensor, resources=self._c0_resources
            )
            config = qd_transport.TransportConfig(
                queue_depth=QD,
                block_bytes=BLOCK_BYTES,
                staging_slots=int(self._c0_runtime.slot_count),
                ready_queue_capacity=int(self._c0_runtime.slot_count),
                producer_workers=QD,
                capacity_class="c0-qd4-64m",
                h2d_target_bytes=BLOCK_BYTES,
                aggregation_enabled=False,
            )
            pool = self._c0_runtime.new_stage_pool()
            dispatcher = qd_transport.GoldenQDTransport(
                config,
                backend,
                arm="static_e27",
                pool=pool,
                diagnostics=False,
                resources=self._c0_resources,
            )
            ranges = []
            block_id = 0
            offset = layout.data_start
            remaining = layout.data_bytes
            while remaining > 0:
                length = min(BLOCK_BYTES, remaining)
                ranges.append(
                    qd_transport.SourceRange(
                        offset,
                        length,
                        block_id * BLOCK_BYTES,
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
            )
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
            source_wall_ms = float(getattr(source, "fill_wall_ns", 0) or 0) / 1e6
            source_gbps = (
                layout.data_bytes / ((source_wall_ms / 1000.0) * 1e9)
                if source_wall_ms > 0 else None
            )
            finished_ns = time.perf_counter_ns()
            stats = {
                "status": "ok",
                "source_engine": "c0_mmap_fresh_shared_arena",
                "execution_arm": "m2_mmap_process",
                "c0_arena_created": False,
                "source_read_count": int(getattr(source, "fills", 0) or len(ranges)),
                "source_read_bytes": layout.data_bytes,
                "bytes_read": layout.data_bytes,
                "gpu_bytes": layout.data_bytes,
                "h2d_submitted_bytes": int(result.submitted_bytes),
                "h2d_completed_bytes": int(result.completed_bytes),
                "source_wall_ms": source_wall_ms,
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
                "fd_cache_hit": bool(getattr(source, "fd_reuse_count", 0)),
                "layout_resolve_ms": (layout_end_ns - layout_started_ns) / 1e6,
                "source_go_offset_ms": (int(getattr(source, "first_source_read_start_mono_ns", 0) or 0) - started_ns) / 1e6,
                "gpu_ready_wall_ms": (finished_ns - started_ns) / 1e6,
                "gpu_ready_tail_ms": None,
                "destination_growth_ms": self._pool.growth_ms,
                "new_capacity_bytes": owner.capacity_bytes if not owner.reused else None,
                "total_load_ms": (finished_ns - started_ns) / 1e6,
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
        if self.staging is not None:
            for lane in range(self.qd):
                self.staging["consumed"][lane].value = int(self.staging["published"][lane].value)
        deadline = time.monotonic() + 30.0
        for reader_id, connection in enumerate(self._connections):
            while time.monotonic() < deadline:
                if connection.poll(0.05):
                    message = connection.recv()
                    if (
                        message.get("command") != "LOAD_DONE"
                        or int(message.get("generation", -1)) != generation
                    ):
                        raise RuntimeError(f"persistent_reader_abort_protocol:{reader_id}")
                    break

    def _copy_until_complete(self, layout: SafetensorsLayout, generation: int, allocation_future: Any) -> dict[str, Any]:
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
        fd_cache_hit = False
        deadline = time.monotonic() + TRANSFER_TIMEOUT_S
        h2d_ranges: list[tuple[int, int]] = []
        if allocation_future is None:
            raise RuntimeError("persistent_destination_missing")
        try:
            owner = allocation_future.result(timeout=TRANSFER_TIMEOUT_S)
        except TypeError:
            owner = allocation_future.result()
        destination_ptr = int(owner.gpu_tensor.data_ptr())

        def collect_done() -> None:
            nonlocal first_source, last_source, fd_cache_hit
            for reader_id, connection in enumerate(self._connections):
                if reader_id in done or not connection.poll():
                    continue
                message = connection.recv()
                if message.get("command") != "LOAD_DONE" or int(message.get("generation", -1)) != generation:
                    raise RuntimeError("persistent_reader_completion_generation_mismatch")
                done[reader_id] = message
                if message.get("status") != "ok":
                    raise RuntimeError(f"persistent_reader_failed:{message.get('error')}")
                enter = int(message.get("first_enter_ns") or 0)
                exit_ns = int(message.get("last_exit_ns") or 0)
                if enter:
                    first_source = enter if not first_source else min(first_source, enter)
                if exit_ns:
                    last_source = max(last_source, exit_ns)
                if message.get("fd_cache_hit"):
                    fd_cache_hit = True

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
        return {
            "owner": owner,
            "source_start_ns": first_source,
            "source_end_ns": last_source,
            "last_h2d_ns": last_h2d,
            "source_read_count": source_read_count,
            "fd_cache_hit": fd_cache_hit,
            "readers": done,
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
        return {
            "transport_runtime_reused": bool(reused),
            "reader_pool_reused": bool(reused and self._prepared),
            "staging_reused": bool(self.staging is not None),
            "host_registration_reused": bool(reused and self._cuda_ready),
            "cuda_stream_reused": bool(reused and self._cuda_ready),
            "event_pool_size": len(self._event_pool),
            "staging_bytes": self.staging_bytes,
            "models_generation": self._models_generation,
        }

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
            if self._cuda_ready:
                if self._c0_runtime is not None:
                    try:
                        self._c0_resources.close()
                    except BaseException:
                        pass
                    try:
                        from . import golden_io_process_v2 as c0
                        c0.close_runtime()
                    except BaseException:
                        pass
                    self._closed = True
                    return
                lib = self._cuda["lib"]
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
    "LoadedSafetensors",
    "SafetensorsLayout",
    "get_golden_model_transport",
]
