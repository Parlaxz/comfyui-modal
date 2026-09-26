"""Small production adapter around the canonical M2 source engine."""

from __future__ import annotations

import json
import os
import struct
import time
from typing import Any

from . import m2_source_core
from . import source_race_gpu

_QD = 4
_BLOCK_BYTES = 64 * 1024 * 1024
_SLOTS = 1

_DTYPE_NAMES = {
    "F64": "float64", "F32": "float32", "F16": "float16", "BF16": "bfloat16",
    "I64": "int64", "I32": "int32", "I16": "int16", "I8": "int8",
    "U8": "uint8", "BOOL": "bool",
}


def parse_safetensors_header(path: str) -> tuple[dict[str, Any], int, int]:
    """Return ``(tensor metadata, data section start, data bytes)``."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError("truncated_safetensors_header_length")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length <= 0 or header_length > size - 8:
            raise ValueError(f"invalid_safetensors_header_length:{header_length}")
        header_raw = handle.read(header_length)
    header = json.loads(header_raw.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("safetensors_header_not_object")
    data_start = 8 + int(header_length)
    data_bytes = size - data_start
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
        if dtype not in _DTYPE_NAMES:
            raise ValueError(f"unsupported_safetensors_dtype:{dtype}")
        ranges.append((start, end, str(name)))
    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if previous[1] > current[0]:
            raise ValueError(f"overlapping_tensor_ranges:{previous[2]}:{current[2]}")
    return header, data_start, data_bytes


def build_header_tensor_map(header: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, info in header.items():
        if name == "__metadata__":
            continue
        start, end = [int(value) for value in info["data_offsets"]]
        result.append({
            "key": str(name),
            "dtype": str(info["dtype"]),
            "shape": [int(value) for value in info["shape"]],
            "offset": start,
            "length": end - start,
        })
    return result


class M2GpuOwner:
    """Own the PyTorch destination that backs all published tensor views."""

    __slots__ = ("_gpu_tensor", "_staging", "device", "closed", "keys")

    def __init__(self, gpu_tensor: Any, staging: dict[str, Any] | None, device: str, keys: list[str]):
        self._gpu_tensor = gpu_tensor
        self._staging = staging
        self.device = str(device)
        self.closed = False
        self.keys = list(keys)

    @property
    def gpu_tensor(self) -> Any:
        return self._gpu_tensor

    @property
    def gpu_buf(self) -> Any:
        return self._gpu_tensor

    def release_staging(self) -> None:
        self._staging = None

    def release_storage(self, *, purge_allocator: bool = False) -> None:
        del purge_allocator
        if self.closed:
            return
        self.closed = True
        self._staging = None
        self._gpu_tensor = None

    def purge_allocator(self) -> None:
        self.release_storage()

    def close(self) -> None:
        self.release_storage()


def _tensor_views(gpu_tensor: Any, tensor_map: list[dict[str, Any]]) -> dict[str, Any]:
    import torch

    result: dict[str, Any] = {}
    for item in tensor_map:
        dtype_name = _DTYPE_NAMES[item["dtype"]]
        dtype = getattr(torch, dtype_name)
        element_size = int(torch.empty((), dtype=dtype).element_size())
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


def load_m2_safetensors(
    path: str,
    *,
    device: str | None = None,
    qd: int = _QD,
    block_bytes: int = _BLOCK_BYTES,
    trace: Any = None,
) -> dict[str, Any]:
    """Read one safetensors file into one PyTorch-owned CUDA allocation."""
    del trace
    import torch

    loader_start_ns = time.perf_counter_ns()
    if int(qd) != _QD or int(block_bytes) != _BLOCK_BYTES:
        raise ValueError("production M2 geometry is fixed at QD4 and 64 MiB")
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    target = device or f"cuda:{torch.cuda.current_device()}"
    header, data_start, data_bytes = parse_safetensors_header(path)
    tensor_map = build_header_tensor_map(header)
    staging_started = time.perf_counter()
    staging = source_race_gpu.build_staging(_QD, _SLOTS, _BLOCK_BYTES, prefault=False)
    staging_alloc_ms = (time.perf_counter() - staging_started) * 1000.0
    consumer, consumer_state = source_race_gpu.start_consumer(
        staging, _QD, _BLOCK_BYTES, "h2d", verify=False, file_path=path,
        diagnostics=False,
    )
    gpu_tensor_holder: dict[str, Any] = {}
    setup_timing: dict[str, float] = {}

    def on_ready() -> None:
        started = time.perf_counter()
        gpu_tensor = torch.empty(int(data_bytes), dtype=torch.uint8, device=target)
        gpu_tensor_holder["tensor"] = gpu_tensor
        setup = source_race_gpu.setup_current_torch_context(staging, "h2d", gpu_tensor)
        setup_timing.update(setup)
        setup_timing["total_ms"] = (time.perf_counter() - started) * 1000.0

    try:
        source = m2_source_core.run_mmap_source_probe(
            file_path=path,
            read_bytes=_BLOCK_BYTES,
            qd=_QD,
            mmap_mode="window",
            consume_mode="memcpy",
            staging=staging,
            on_ready=on_ready,
            min_launch_gap_ns=4_000_000,
            source_offset=data_start,
            source_size=data_bytes,
            ready_timeout_s=300.0,
            max_idle_s=120.0,
            diagnostics=False,
        )
        staging["alive"].value = 0
        consumer.join(timeout=300.0)
        if consumer.is_alive():
            raise RuntimeError("h2d_consumer_did_not_stop")
        if not source["coverage"]["covers_entire_file_exactly_once"]:
            raise RuntimeError(f"m2_source_coverage_failed:{source['coverage']}")
        if source.get("worker_errors"):
            raise RuntimeError(f"m2_reader_failed:{source['worker_errors']}")
        if consumer_state.get("error"):
            raise RuntimeError(f"m2_h2d_failed:{consumer_state['error']}")
        if not consumer_state.get("coverage_exact"):
            raise RuntimeError("m2_h2d_coverage_failed")
        if int(consumer_state.get("transfers", 0) or 0) != int(source["physical_reads"]):
            raise RuntimeError("m2_h2d_transfer_count_mismatch")
        if int(consumer_state.get("h2d_bytes", 0) or 0) != int(data_bytes):
            raise RuntimeError("m2_h2d_byte_count_mismatch")
        gpu_tensor = gpu_tensor_holder.get("tensor")
        if gpu_tensor is None:
            raise RuntimeError("m2_gpu_destination_missing")
        first_source = int(source.get("source_first_enter_ns") or 0)
        last_source = int(source.get("source_last_exit_ns") or 0)
        last_h2d = int(consumer_state.get("last_done_ns") or 0)
        tensor_views = _tensor_views(gpu_tensor, tensor_map)
        try:
            staging["_mm"].close()
        except Exception:
            pass
        owner = M2GpuOwner(gpu_tensor, None, target, list(tensor_views))
        source_stats = {
            "status": "ok",
            "source_read_count": int(source["physical_reads"]),
            "physical_attempts": int(source["physical_attempts"]),
            "source_read_bytes": int(data_bytes),
            "bytes_read": int(data_bytes),
            "source_wall_ms": float(source["full_file_wall_ms"]),
            "qd_source_io_wall_ms": float(source["full_file_wall_ms"]),
            "source_gbps": source.get("full_file_decimal_gbps"),
            "source_reads": {
                "bytes": int(data_bytes),
                "read_count": int(source["physical_reads"]),
                "wall_ms": float(source["full_file_wall_ms"]),
            },
            "gpu_bytes": int(data_bytes),
            "h2d_completed_bytes": int(data_bytes),
            "h2d_submitted_bytes": int(consumer_state.get("h2d_bytes", 0) or 0),
            "h2d_device_ms": None,
            "coverage": dict(source["coverage"]),
            "quiescence": {
                "workers_joined": True,
                "h2d_events_waited": True,
                "copies_complete": True,
                "operation_live": False,
            },
            "source_engine": "m2_mmap_process",
            "source_geometry": {"qd": _QD, "block_bytes": _BLOCK_BYTES},
            "reader_timing": list(source.get("reader_timing") or []),
            "staging_wait_ms": float(
                (source.get("staging") or {}).get("wait_ms_total_shared", 0.0) or 0.0
            ),
            "staging_wait_events": int(
                (source.get("staging") or {}).get("wait_events_total_shared", 0) or 0
            ),
        }
        return {
            "status": "ok",
            "sd": tensor_views,
            "owner": owner,
            "stats": source_stats,
            "tensor_map": tensor_map,
            "source": source,
            "staging": consumer_state,
            "timing": {
                "loader_wall_ms": (time.perf_counter_ns() - loader_start_ns) / 1e6,
                "source_wall_ms": float(source["full_file_wall_ms"]),
                "gpu_ready_wall_ms": ((last_h2d - first_source) / 1e6) if last_h2d and first_source else None,
                "exposed_h2d_tail_ms": ((last_h2d - last_source) / 1e6) if last_h2d and last_source else None,
                "staging_alloc_ms": staging_alloc_ms,
                "fork_ms": source["timing"].get("fork_ms"),
                "reader_ready_ms": source["timing"].get("ready_ms"),
                "cuda_setup_ms": setup_timing.get("total_ms"),
                "host_register_ms": setup_timing.get("register_ms"),
                "reader_completion_ms": source["timing"].get("join_ms"),
                "h2d_drain_ms": consumer_state.get("wall_ms"),
            },
            "ownership": {
                "destination": "torch.cuda.uint8",
                "destination_data_ptr": int(gpu_tensor.data_ptr()),
                "model_sized_second_copy": False,
                "context": setup_timing,
                "owner": owner,
            },
            "loader_entry_ns": loader_start_ns,
            "data_start": data_start,
            "data_bytes": data_bytes,
        }
    except BaseException:
        staging["alive"].value = 0
        consumer.join(timeout=30.0)
        raise


def bind_m2_clip(clip: Any, loaded: dict[str, Any]) -> dict[str, Any]:
    """Adopt views through Comfy's normal CLIP ``load_sd`` path."""
    if loaded.get("status") != "ok":
        raise RuntimeError("m2_load_not_ready")
    from .clip_fast_hydration import hydrate_clip_bind

    import torch

    started = time.perf_counter()
    ok, evidence = hydrate_clip_bind(
        clip,
        [loaded["sd"]],
        require_no_meta=True,
        expect_device=f"cuda:{torch.cuda.current_device()}",
    )
    if not ok:
        raise RuntimeError(f"m2_clip_bind_failed:{evidence}")
    owner = loaded["owner"]
    setattr(clip, "_comfymodal_m2_owner", owner)
    csm = getattr(clip, "cond_stage_model", None)
    if csm is not None:
        setattr(csm, "_comfymodal_m2_owner", owner)
    return {
        "ok": True,
        "evidence": evidence,
        "tensor_view_ms": (time.perf_counter() - started) * 1000.0,
        "comfy_bind_ms": (time.perf_counter() - started) * 1000.0,
        "owner_retained": True,
    }


__all__ = [
    "M2GpuOwner",
    "bind_m2_clip",
    "build_header_tensor_map",
    "load_m2_safetensors",
    "parse_safetensors_header",
]
