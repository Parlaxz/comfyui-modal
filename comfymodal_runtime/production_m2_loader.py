"""Small production adapter around the canonical M2 source engine."""

from __future__ import annotations

import json
import os
import struct
import time
from typing import Any

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
    transport: Any = None,
) -> dict[str, Any]:
    """Compatibility adapter to the container-lifetime generic transport."""
    del device, trace
    if int(qd) != _QD or int(block_bytes) != _BLOCK_BYTES:
        raise ValueError("production M2 geometry is fixed at QD4 and 64 MiB")
    if transport is None:
        from .golden_model_transport import get_golden_model_transport
        transport = get_golden_model_transport()
    loaded = transport.load_sync(path)
    return {
        "status": "ok",
        "sd": loaded.views,
        "owner": loaded.owner,
        "stats": loaded.stats,
        "tensor_map": list(loaded.layout.tensor_map),
        "source": loaded.stats.get("source") or {},
        "timing": {
            "loader_wall_ms": loaded.stats.get("total_load_ms"),
            "source_wall_ms": loaded.stats.get("source_wall_ms"),
            "gpu_ready_wall_ms": loaded.stats.get("gpu_ready_wall_ms"),
            "exposed_h2d_tail_ms": loaded.stats.get("gpu_ready_tail_ms"),
            "layout_resolve_ms": loaded.stats.get("layout_resolve_ms"),
        },
        "data_start": loaded.layout.data_start,
        "data_bytes": loaded.layout.data_bytes,
    }


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
