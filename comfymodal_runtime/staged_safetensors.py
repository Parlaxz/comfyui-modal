"""Generic bounded staged loading for safetensors checkpoints.

The module intentionally stops at a transferred, unbound state dictionary.
Callers retain their existing loader as the fallback and bind only after a
successful :func:`commit` result.
"""

from __future__ import annotations

import json as _json
import os as _os
import queue as _queue
import struct as _struct
import threading as _threading
import time as _time
from concurrent.futures import Future as _Future
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path
from typing import Any, Callable, Mapping

from .env import env_flag as _env_flag
from . import source_order_safetensors as _source_order


_MIB = 1024 * 1024
_DEFAULT_PRODUCERS = 4
_DEFAULT_POOL_MB = 1024
_DEFAULT_BUCKET_MB = 256
_NATIVE_PIN_LOCK = _threading.Lock()


def _now_ns() -> int:
    return _time.perf_counter_ns()


def _safe_int(name: str, default: int) -> int:
    raw = _os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _torch_dtype(value: Any) -> Any:
    try:
        import torch as _torch
    except Exception:
        return None
    if isinstance(value, str):
        key = value.strip().lower().replace(" ", "")
        names = {
            "bf16": _torch.bfloat16,
            "bfloat16": _torch.bfloat16,
            "float16": _torch.float16,
            "fp16": _torch.float16,
            "f16": _torch.float16,
            "float32": _torch.float32,
            "fp32": _torch.float32,
            "f32": _torch.float32,
            "float64": _torch.float64,
            "fp64": _torch.float64,
        }
        return names.get(key)
    return value if isinstance(value, _torch.dtype) else None


def _source_dtype_table() -> dict[str, Any]:
    try:
        import torch as _torch
    except Exception:
        return {}
    table: dict[str, Any] = {}
    for name, attr in (
        ("BOOL", "bool"),
        ("U8", "uint8"),
        ("I8", "int8"),
        ("I16", "int16"),
        ("I32", "int32"),
        ("I64", "int64"),
        ("F16", "float16"),
        ("BF16", "bfloat16"),
        ("F32", "float32"),
        ("F64", "float64"),
    ):
        dtype = getattr(_torch, attr, None)
        if dtype is not None:
            table[name] = dtype
    return table


def _dtype_itemsize(dtype: Any) -> int:
    import torch as _torch

    return int(_torch.empty((), dtype=dtype).element_size())


@_dataclass(frozen=True)
class StagedConfig:
    enabled: bool = False
    producers: int = _DEFAULT_PRODUCERS
    pool_mb: int = _DEFAULT_POOL_MB
    bucket_mb: int = _DEFAULT_BUCKET_MB
    cpu_cast: bool = True
    async_h2d: bool = True
    contiguous_gpu_buckets: bool = False
    source_order_enabled: bool = False

    @property
    def slab_count(self) -> int:
        if self.bucket_mb <= 0:
            return 0
        return self.pool_mb // self.bucket_mb

    @property
    def pool_bytes(self) -> int:
        return max(0, self.slab_count) * max(0, self.bucket_mb) * _MIB


def config_from_env() -> StagedConfig:
    return StagedConfig(
        enabled=_env_flag("COMFYMODAL_V2_STAGED_SAFETENSORS", default=False),
        producers=_safe_int("COMFYMODAL_V2_STAGED_PRODUCERS", _DEFAULT_PRODUCERS),
        pool_mb=_safe_int("COMFYMODAL_V2_STAGED_POOL_MB", _DEFAULT_POOL_MB),
        bucket_mb=_safe_int("COMFYMODAL_V2_STAGED_BUCKET_MB", _DEFAULT_BUCKET_MB),
        cpu_cast=_env_flag("COMFYMODAL_V2_STAGED_CPU_CAST", default=True),
        async_h2d=_env_flag("COMFYMODAL_V2_STAGED_ASYNC_H2D", default=True),
        contiguous_gpu_buckets=_env_flag(
            "COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS", default=False
        ),
        source_order_enabled=_env_flag(
            "COMFYMODAL_V2_STAGED_SOURCE_ORDER", default=False
        ),
    )


@_dataclass(frozen=True)
class TensorSpec:
    name: str
    source_dtype_name: str
    source_dtype: Any
    output_dtype: Any
    shape: tuple[int, ...]
    nbytes: int
    offset: int
    converted: bool = False
    source_nbytes: int | None = None
    source_checkpoint: _Path | None = None
    source_data_start: int = 0


@_dataclass(frozen=True)
class StagePlan:
    checkpoint: _Path
    config: StagedConfig
    target_device: Any = None
    target_dtype: Any = None
    specs: tuple[TensorSpec, ...] = ()
    checkpoint_bytes: int = 0
    fallback_reason: str | None = None
    checkpoints: tuple[_Path, ...] = ()
    source_layout: Any = None
    source_files: tuple[Any, ...] = ()
    source_order_eligible: bool = False
    source_order_fallback_reason: str | None = None
    alignment_fallback_tensor_count: int = 0

    @property
    def supported(self) -> bool:
        return self.fallback_reason is None

    @property
    def enabled(self) -> bool:
        return self.config.enabled and self.supported

    @property
    def total_tensor_bytes(self) -> int:
        return sum(spec.nbytes for spec in self.specs)


@_dataclass
class StageResult:
    success: bool
    tensors: dict[str, Any]
    checkpoint_bytes: int
    disk_to_stage_ms: float | None
    cpu_cast_ms: float | None
    h2d_enqueue_ms: float | None
    h2d_device_ms: float | None
    bind_independent_transfer: bool
    peak_pinned_bytes: int
    producer_wait_ms: float
    consumer_wait_ms: float
    effective_h2d_gbps: float | None
    fallback_reason: str | None = None
    error: str = ""
    cpu_cast_bytes: int = 0
    exact_copy_bytes: int = 0
    non_blocking: bool = False
    stream_count: int = 1
    copy_count: int = 0
    bucket_bytes: int = 0
    producer_count: int = 0
    native_pin_budget_available: bool | None = None
    local_bounded_budget_used: bool = False
    native_pin_budget_rejected: bool = False
    host_slab_is_pinned: bool | None = None
    host_slab_is_pinned_all: bool | None = None
    host_slab_is_pinned_per_slot: tuple[bool | None, ...] = ()
    h2d_stream_span_ms: float | None = None
    h2d_dma_busy_ms: float | None = None
    h2d_stream_idle_estimate_ms: float | None = None
    h2d_dma_gbps: float | None = None
    h2d_span_gbps: float | None = None
    packed_model_bytes: int = 0
    host_bucket_bytes_configured: int = 0
    host_slab_count: int = 0
    gpu_bucket_count: int = 0
    h2d_bucket_count: int = 0
    h2d_full_bucket_count: int = 0
    h2d_final_bucket_bytes: int = 0
    min_h2d_copy_bytes: int | None = None
    median_h2d_copy_bytes: int | None = None
    max_h2d_copy_bytes: int | None = None
    slab_reuse_wait_ms: float = 0.0
    tensor_count: int = 0
    source_read_ms: float = 0.0
    source_materialization_ms: float = 0.0
    bucket_pack_cpu_ms: float = 0.0
    bucket_ready_wait_ms: float = 0.0
    source_order_enabled: bool = False
    source_order_eligible: bool = False
    source_order_fallback_reason: str | None = None
    source_file_count: int = 0
    source_tensor_count: int = 0
    source_model_bytes: int = 0
    source_read_calls: int = 0
    source_read_min_bytes: int | None = None
    source_read_median_bytes: int | None = None
    source_read_max_bytes: int | None = None
    source_sequential_bytes: int = 0
    source_repack_bytes: int = 0
    source_read_wall_ms: float = 0.0
    source_read_worker_accumulated_ms: float = 0.0
    source_to_pinned_copy_bytes: int = 0
    source_to_pinned_copy_ms: float = 0.0
    alignment_fallback_tensor_count: int = 0
    _owner: Any = None
    _gpu_owner: Any = None

    @property
    def ok(self) -> bool:
        return self.success

    @property
    def fallback(self) -> str | None:
        return self.fallback_reason

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "checkpoint_bytes": self.checkpoint_bytes,
            "disk_to_stage_ms": self.disk_to_stage_ms,
            "cpu_cast_ms": self.cpu_cast_ms,
            "cpu_cast_bytes": self.cpu_cast_bytes,
            "exact_copy_bytes": self.exact_copy_bytes,
            "h2d_enqueue_ms": self.h2d_enqueue_ms,
            "h2d_device_ms": self.h2d_device_ms,
            "bind_independent_transfer": self.bind_independent_transfer,
            "peak_pinned_bytes": self.peak_pinned_bytes,
            "producer_wait_ms": self.producer_wait_ms,
            "consumer_wait_ms": self.consumer_wait_ms,
            "effective_h2d_gbps": self.effective_h2d_gbps,
            "pool_bytes": self.peak_pinned_bytes,
            "bucket_bytes": self.bucket_bytes,
            "producer_count": self.producer_count,
            "copy_count": self.copy_count,
            "non_blocking": self.non_blocking,
            "stream_count": self.stream_count,
            "fallback_reason": self.fallback_reason,
            "pinned_fast_path_active": bool(self.success),
            "native_pin_budget_available": self.native_pin_budget_available,
            "local_bounded_budget_used": self.local_bounded_budget_used,
            "native_pin_budget_rejected": self.native_pin_budget_rejected,
            "host_slab_is_pinned": self.host_slab_is_pinned,
            "host_slab_is_pinned_all": self.host_slab_is_pinned_all,
            "host_slab_is_pinned_per_slot": list(self.host_slab_is_pinned_per_slot),
            "contiguous_gpu_buckets_active": bool(
                self.success
                and self._owner is not None
                and self._owner.plan.config.contiguous_gpu_buckets
            ),
            "h2d_stream_span_ms": self.h2d_stream_span_ms,
            "h2d_dma_busy_ms": self.h2d_dma_busy_ms,
            "h2d_stream_idle_estimate_ms": self.h2d_stream_idle_estimate_ms,
            "h2d_dma_gbps": self.h2d_dma_gbps,
            "h2d_span_gbps": self.h2d_span_gbps,
            "packed_model_bytes": self.packed_model_bytes,
            "host_bucket_bytes_configured": self.host_bucket_bytes_configured,
            "host_slab_count": self.host_slab_count,
            "gpu_bucket_count": self.gpu_bucket_count,
            "h2d_bucket_count": self.h2d_bucket_count,
            "h2d_full_bucket_count": self.h2d_full_bucket_count,
            "h2d_final_bucket_bytes": self.h2d_final_bucket_bytes,
            "min_h2d_copy_bytes": self.min_h2d_copy_bytes,
            "median_h2d_copy_bytes": self.median_h2d_copy_bytes,
            "max_h2d_copy_bytes": self.max_h2d_copy_bytes,
            "slab_reuse_wait_ms": self.slab_reuse_wait_ms,
            "tensor_count": self.tensor_count,
            "source_read_ms": self.source_read_ms,
            "source_materialization_ms": self.source_materialization_ms,
            "bucket_pack_cpu_ms": self.bucket_pack_cpu_ms,
            "bucket_ready_wait_ms": self.bucket_ready_wait_ms,
            "source_order_enabled": self.source_order_enabled,
            "source_order_eligible": self.source_order_eligible,
            "source_order_fallback_reason": self.source_order_fallback_reason,
            "source_file_count": self.source_file_count,
            "source_tensor_count": self.source_tensor_count,
            "source_model_bytes": self.source_model_bytes,
            "source_read_calls": self.source_read_calls,
            "source_read_min_bytes": self.source_read_min_bytes,
            "source_read_median_bytes": self.source_read_median_bytes,
            "source_read_max_bytes": self.source_read_max_bytes,
            "source_sequential_bytes": self.source_sequential_bytes,
            "source_repack_bytes": self.source_repack_bytes,
            "source_read_wall_ms": self.source_read_wall_ms,
            "source_read_worker_accumulated_ms": self.source_read_worker_accumulated_ms,
            "source_to_pinned_copy_bytes": self.source_to_pinned_copy_bytes,
            "source_to_pinned_copy_ms": self.source_to_pinned_copy_ms,
            "alignment_fallback_tensor_count": self.alignment_fallback_tensor_count,
        }

    def close(self) -> None:
        owner = self._owner
        self._owner = None
        self._gpu_owner = None
        if owner is not None:
            owner.close()

    def __del__(self):  # pragma: no cover - interpreter shutdown is variable
        try:
            self.close()
        except Exception:
            pass


def fallback(reason: str, *, checkpoint_bytes: int = 0, error: str = "") -> StageResult:
    """Return a failed result; the caller must invoke its existing loader."""
    return StageResult(
        success=False,
        tensors={},
        checkpoint_bytes=int(checkpoint_bytes or 0),
        disk_to_stage_ms=None,
        cpu_cast_ms=None,
        h2d_enqueue_ms=None,
        h2d_device_ms=None,
        bind_independent_transfer=True,
        peak_pinned_bytes=0,
        producer_wait_ms=0.0,
        consumer_wait_ms=0.0,
        effective_h2d_gbps=None,
        fallback_reason=str(reason or "unknown"),
        error=str(error or "")[:300],
    )


def _invalid_config(config: StagedConfig) -> str | None:
    if config.producers < 1:
        return "invalid_config:producers"
    if config.pool_mb < 1:
        return "invalid_config:pool_mb"
    if config.bucket_mb < 1:
        return "invalid_config:bucket_mb"
    if config.pool_mb < config.bucket_mb:
        return "invalid_config:pool_lt_bucket"
    if config.slab_count < 1:
        return "invalid_config:no_slabs"
    return None


def _read_header(path: _Path) -> tuple[int, dict[str, Any]]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        raw = handle.read(8)
        if len(raw) != 8:
            raise ValueError("short_header_length")
        header_len = _struct.unpack("<Q", raw)[0]
        if header_len <= 0 or header_len > size - 8:
            raise ValueError("invalid_header_length")
        header_raw = handle.read(header_len)
    header = _json.loads(header_raw.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("header_not_object")
    return size, header


def _plan_specs(
    header: Mapping[str, Any],
    *,
    data_start: int,
    file_bytes: int,
    target_dtype: Any,
    cpu_cast: bool,
    source_checkpoint: _Path | None = None,
) -> tuple[tuple[TensorSpec, ...], str | None]:
    dtype_table = _source_dtype_table()
    specs: list[TensorSpec] = []
    for name, info in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(name, str) or not isinstance(info, dict):
            return (), "invalid_header:tensor_entry"
        dtype_name = str(info.get("dtype", ""))
        source_dtype = dtype_table.get(dtype_name)
        if source_dtype is None:
            return (), f"unsupported_dtype:{dtype_name or 'missing'}"
        shape_raw = info.get("shape")
        offsets = info.get("data_offsets")
        if not isinstance(shape_raw, list) or not isinstance(offsets, list) or len(offsets) != 2:
            return (), f"invalid_header:{name}"
        try:
            shape = tuple(int(value) for value in shape_raw)
            if any(value < 0 for value in shape):
                raise ValueError
            start, end = int(offsets[0]), int(offsets[1])
            if start < 0 or end < start:
                raise ValueError
            elements = 1
            for value in shape:
                elements *= value
            expected_bytes = elements * _dtype_itemsize(source_dtype)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return (), f"invalid_header:{name}"
        if end - start != expected_bytes or data_start + end > file_bytes:
            return (), f"invalid_header:offsets:{name}"
        output_dtype = source_dtype if target_dtype is None else target_dtype
        output_nbytes = elements * _dtype_itemsize(output_dtype)
        converted = output_dtype != source_dtype
        if converted:
            if source_dtype is not _source_dtype_table().get("F32"):
                return (), "dtype_conversion_unsupported"
            if output_dtype not in (dtype_table.get("BF16"), dtype_table.get("F16")):
                return (), "dtype_conversion_unsupported"
            if not cpu_cast:
                return (), "cpu_cast_disabled"
        specs.append(
            TensorSpec(
                name=name,
                source_dtype_name=dtype_name,
                source_dtype=source_dtype,
                output_dtype=output_dtype,
                shape=shape,
                nbytes=output_nbytes,
                offset=data_start + start,
                source_nbytes=expected_bytes,
                converted=converted,
                source_checkpoint=source_checkpoint,
                source_data_start=data_start,
            )
        )
    return tuple(specs), None


def _normalize_checkpoints(checkpoint: Any) -> tuple[_Path, ...]:
    if isinstance(checkpoint, (_Path, str)):
        return (_Path(checkpoint),)
    if isinstance(checkpoint, (tuple, list)):
        return tuple(_Path(value) for value in checkpoint)
    return (_Path(checkpoint),)


def _packed_layout(
    specs: tuple[TensorSpec, ...],
) -> tuple[dict[str, int], int] | tuple[None, str]:
    cursor = 0
    layout: dict[str, int] = {}
    for spec in specs:
        try:
            element_size = _dtype_itemsize(spec.output_dtype)
            elements = 1
            for dimension in spec.shape:
                elements *= dimension
            if element_size not in (1, 2, 4, 8):
                return None, "E1_CONTIGUOUS_BUCKETS_DEFERRED"
            if spec.nbytes != elements * element_size:
                return None, "E1_CONTIGUOUS_BUCKETS_DEFERRED"
            cursor = (cursor + element_size - 1) // element_size * element_size
            layout[spec.name] = cursor
            cursor += spec.nbytes
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None, "E1_CONTIGUOUS_BUCKETS_DEFERRED"
    return layout, cursor


def _packed_bucket_plan(
    specs: tuple[TensorSpec, ...],
    layout: Mapping[str, int],
    packed_bytes: int,
    bucket_bytes: int,
) -> tuple[tuple[int, int, tuple[tuple[str, int, int, int], ...]], ...]:
    """Build ordered source-to-bucket ranges over the packed GPU layout.

    Each range is ``(tensor_name, source_offset, bucket_offset, size)``.  Gap
    bytes intentionally have no range: they are not exposed by any tensor
    view and are therefore not needlessly initialized in the host stream.
    """
    packed_bytes = int(packed_bytes)
    bucket_bytes = int(bucket_bytes)
    if packed_bytes < 0 or bucket_bytes <= 0:
        raise ValueError("invalid packed bucket geometry")
    bucket_count = (packed_bytes + bucket_bytes - 1) // bucket_bytes
    buckets: list[list[tuple[str, int, int, int]]] = [
        [] for _ in range(bucket_count)
    ]
    for spec in specs:
        if spec.nbytes <= 0:
            continue
        start = int(layout[spec.name])
        end = start + int(spec.nbytes)
        cursor = start
        while cursor < end:
            bucket_index = cursor // bucket_bytes
            bucket_start = bucket_index * bucket_bytes
            overlap_end = min(end, bucket_start + bucket_bytes)
            buckets[bucket_index].append(
                (
                    spec.name,
                    cursor - start,
                    cursor - bucket_start,
                    overlap_end - cursor,
                )
            )
            cursor = overlap_end
    return tuple(
        (
            index * bucket_bytes,
            min(bucket_bytes, packed_bytes - index * bucket_bytes),
            tuple(ranges),
        )
        for index, ranges in enumerate(buckets)
    )


def _partition_packed_buckets(
    bucket_plan: tuple[Any, ...], producer_count: int
) -> tuple[tuple[Any, ...], ...]:
    """Split bucket work into balanced, disjoint producer ranges."""
    if not bucket_plan:
        return ()
    worker_count = min(max(1, int(producer_count)), len(bucket_plan))
    base, remainder = divmod(len(bucket_plan), worker_count)
    partitions: list[tuple[Any, ...]] = []
    start = 0
    for index in range(worker_count):
        size = base + int(index < remainder)
        partitions.append(bucket_plan[start:start + size])
        start += size
    return tuple(partitions)


def plan(
    checkpoint: str | _Path | tuple[str | _Path, ...] | list[str | _Path],
    *,
    target_dtype: Any = None,
    dtype: Any = None,
    device: Any = None,
    config: StagedConfig | None = None,
) -> StagePlan:
    """Inspect a generic safetensors file without loading tensor values."""
    paths = _normalize_checkpoints(checkpoint)
    path = paths[0] if paths else _Path("")
    cfg = config if config is not None else config_from_env()
    requested_dtype = target_dtype if target_dtype is not None else dtype
    checkpoint_bytes = 0
    for candidate in paths:
        try:
            checkpoint_bytes += candidate.stat().st_size
        except OSError:
            pass
    if not cfg.enabled:
        return StagePlan(
            path, cfg, device, None, checkpoint_bytes=checkpoint_bytes,
            fallback_reason="flag_off", checkpoints=paths,
        )
    config_reason = _invalid_config(cfg)
    if config_reason:
        return StagePlan(
            path, cfg, device, None, fallback_reason=config_reason,
            checkpoints=paths,
        )
    normalized_dtype = None
    if requested_dtype is not None:
        normalized_dtype = _torch_dtype(requested_dtype)
        if normalized_dtype is None:
            return StagePlan(
                path, cfg, device, None, fallback_reason="unsupported_target_dtype",
                checkpoints=paths,
            )
    try:
        all_specs: list[TensorSpec] = []
        total_bytes = 0
        source_file_specs: dict[_Path, dict[str, Any]] = {}
        for candidate in paths:
            file_bytes, header = _read_header(candidate)
            with candidate.open("rb") as handle:
                header_len = _struct.unpack("<Q", handle.read(8))[0]
            data_start = 8 + header_len
            specs, reason = _plan_specs(
                header,
                data_start=data_start,
                file_bytes=file_bytes,
                target_dtype=normalized_dtype,
                cpu_cast=cfg.cpu_cast,
                source_checkpoint=candidate,
            )
            if reason:
                return StagePlan(
                    path, cfg, device, normalized_dtype,
                    checkpoint_bytes=checkpoint_bytes, fallback_reason=reason,
                    checkpoints=paths,
                )
            names = {spec.name for spec in all_specs}
            if any(spec.name in names for spec in specs):
                return StagePlan(
                    path, cfg, device, normalized_dtype,
                    checkpoint_bytes=checkpoint_bytes,
                    fallback_reason="duplicate_tensor_key",
                    checkpoints=paths,
                )
            all_specs.extend(specs)
            total_bytes += file_bytes
            source_file_specs[candidate] = {
                "data_start": data_start,
                "file_size": file_bytes,
                "expected_dtypes": {
                    spec.name: spec.source_dtype_name for spec in specs
                },
                "tensors": {
                    spec.name: {
                        "dtype": spec.source_dtype_name,
                        "shape": list(spec.shape),
                        "data_offsets": [
                            spec.offset - spec.source_data_start,
                            spec.offset - spec.source_data_start
                            + int(spec.source_nbytes or 0),
                        ],
                    }
                    for spec in specs
                },
            }
        specs_tuple = tuple(all_specs)
        source_layout = None
        source_order_eligible = False
        source_order_fallback_reason = None
        alignment_fallback_tensor_count = 0
        if cfg.source_order_enabled:
            try:
                item_sizes = {
                    spec.name: _dtype_itemsize(spec.output_dtype)
                    for spec in specs_tuple
                }
                source_layout = _source_order.build_layout(
                    source_file_specs, paths, item_sizes
                )
                eligibility = _source_order.assess_eligibility(
                    source_file_specs, source_layout, item_sizes
                )
                source_order_eligible = (
                    eligibility.all_direct
                    and not any(spec.converted for spec in specs_tuple)
                )
                alignment_fallback_tensor_count = eligibility.reason_counts.get(
                    "unsafe-alignment", 0
                )
                if not source_order_eligible:
                    reasons = eligibility.reason_counts
                    if reasons.get("unsafe-alignment", 0):
                        source_order_fallback_reason = (
                            "source_order_alignment_failure"
                        )
                    elif reasons.get("dtype-mismatch", 0) or any(
                        spec.converted for spec in specs_tuple
                    ):
                        source_order_fallback_reason = (
                            "source_order_dtype_cast_required"
                            if any(spec.converted for spec in specs_tuple)
                            else "source_order_dtype_mismatch"
                        )
                    else:
                        source_order_fallback_reason = "source_order_invalid_layout"
            except Exception as exc:
                source_order_fallback_reason = (
                    f"source_order_layout_invalid:{type(exc).__name__}"
                )
        if cfg.contiguous_gpu_buckets:
            packed_layout = _packed_layout(specs_tuple)
            if packed_layout[0] is None:
                return StagePlan(
                    path, cfg, device, normalized_dtype,
                    checkpoint_bytes=total_bytes, fallback_reason=packed_layout[1],
                    checkpoints=paths,
                )
        return StagePlan(
            path, cfg, device, normalized_dtype, specs_tuple,
            checkpoint_bytes=total_bytes, checkpoints=paths,
            source_layout=source_layout,
            source_files=(
                tuple(source_layout.files) if source_layout is not None else ()
            ),
            source_order_eligible=source_order_eligible,
            source_order_fallback_reason=source_order_fallback_reason,
            alignment_fallback_tensor_count=alignment_fallback_tensor_count,
        )
    except FileNotFoundError:
        return StagePlan(
            path, cfg, device, normalized_dtype,
            fallback_reason="checkpoint_not_found", checkpoints=paths,
        )
    except (OSError, UnicodeError, ValueError, TypeError, _json.JSONDecodeError) as exc:
        return StagePlan(
            path, cfg, device, normalized_dtype,
            fallback_reason=f"invalid_checkpoint:{type(exc).__name__}",
            checkpoints=paths,
        )


class _StageAbort(RuntimeError):
    pass


@_dataclass
class _Slab:
    tensor: Any
    pending_event: Any = None
    in_use: bool = False


class _PinnedSlabPool:
    def __init__(
        self,
        slab_count: int,
        slab_bytes: int,
        *,
        allocator: Callable[[int], Any] | None = None,
        on_close: Callable[[], None] | None = None,
    ):
        self.slab_bytes = int(slab_bytes)
        self._condition = _threading.Condition()
        self._aborted = False
        self._closed = False
        self._on_close = on_close
        self._slabs = [
            _Slab((allocator or _allocate_pinned)(self.slab_bytes))
            for _ in range(int(slab_count))
        ]
        self._host_slab_is_pinned_per_slot = self._inspect_pinned_states()
        self._host_slab_is_pinned = self._inspect_pinned_state()
        self.wait_ms = 0.0
        self._peak_in_use = 0

    def _inspect_pinned_states(self) -> tuple[bool | None, ...]:
        states: list[bool | None] = []
        for slab in self._slabs:
            check = getattr(slab.tensor, "is_pinned", None)
            if not callable(check):
                states.append(None)
                continue
            try:
                states.append(bool(check()))
            except Exception:
                states.append(None)
        return tuple(states)

    def _inspect_pinned_state(self) -> bool | None:
        states = self._host_slab_is_pinned_per_slot
        if not states or any(state is None for state in states):
            return None
        return all(states)

    @property
    def host_slab_is_pinned(self) -> bool | None:
        return self._host_slab_is_pinned

    @property
    def host_slab_is_pinned_per_slot(self) -> tuple[bool | None, ...]:
        return self._host_slab_is_pinned_per_slot

    @property
    def slabs(self) -> tuple[_Slab, ...]:
        return tuple(self._slabs)

    @property
    def allocated_bytes(self) -> int:
        return len(self._slabs) * self.slab_bytes

    @property
    def peak_in_use(self) -> int:
        return self._peak_in_use

    def _try_reclaim(self) -> _Slab | None:
        with self._condition:
            for slab in self._slabs:
                if slab.in_use:
                    continue
                event = slab.pending_event
                if event is None:
                    slab.in_use = True
                    in_use = sum(1 for item in self._slabs if item.in_use)
                    self._peak_in_use = max(self._peak_in_use, in_use)
                    return slab
                try:
                    complete = bool(event.query())
                except Exception:
                    complete = False
                if complete:
                    slab.pending_event = None
                    slab.in_use = True
                    in_use = sum(1 for item in self._slabs if item.in_use)
                    self._peak_in_use = max(self._peak_in_use, in_use)
                    return slab
        return None

    def acquire(self) -> _Slab:
        wait_start = None
        while True:
            with self._condition:
                if self._aborted:
                    raise _StageAbort("pool_aborted")
            slab = self._try_reclaim()
            if slab is not None:
                if wait_start is not None:
                    with self._condition:
                        self.wait_ms += (_now_ns() - wait_start) / 1_000_000
                return slab
            if wait_start is None:
                wait_start = _now_ns()
            pending = None
            with self._condition:
                for item in self._slabs:
                    if item.pending_event is not None and not item.in_use:
                        pending = item.pending_event
                        break
            if pending is not None:
                pending.synchronize()
            else:
                _time.sleep(0.001)

    def release(self, slab: _Slab, event: Any) -> None:
        with self._condition:
            slab.in_use = False
            slab.pending_event = event
            self._condition.notify_all()

    def abort(self) -> None:
        with self._condition:
            self._aborted = True
            self._condition.notify_all()

    def close(self) -> None:
        on_close = None
        with self._condition:
            if self._closed:
                return
            self._closed = True
            for slab in self._slabs:
                slab.tensor = None
                slab.pending_event = None
                slab.in_use = False
            self._slabs.clear()
            on_close = self._on_close
            self._on_close = None
        if on_close is not None:
            on_close()


def _allocate_pinned(size: int) -> Any:
    import torch as _torch

    return _torch.empty(int(size), dtype=_torch.uint8, pin_memory=True)


@_dataclass
class _Chunk:
    name: str
    offset: int
    size: int
    slab: _Slab
    destination_offset: int | None = None


class PreparedStage:
    """In-flight CPU staging state owned until commit or close."""

    def __init__(self, stage_plan: StagePlan, *, reason: str | None = None):
        self.plan = stage_plan
        self.ready = reason is None
        self.fallback_reason = reason
        self.queue: _queue.Queue[_Chunk] = _queue.Queue(
            maxsize=max(1, stage_plan.config.slab_count)
        )
        self.pool: _PinnedSlabPool | None = None
        self.executor: _ThreadPoolExecutor | None = None
        self.futures: list[_Future[Any]] = []
        self.copy_stream: Any = None
        self._gpu_owner: Any = None
        self._abort_event = _threading.Event()
        self._closed = False
        self._finished = False
        self._stage_start_ns = _now_ns()
        self._stage_end_ns: int | None = None
        self._cpu_cast_ns = 0
        self._cpu_cast_bytes = 0
        self._exact_copy_bytes = 0
        self._source_read_ns = 0
        self._source_read_calls = 0
        self._source_read_sizes: list[int] = []
        self._source_sequential_bytes = 0
        self._source_read_first_ns: int | None = None
        self._source_read_last_ns: int | None = None
        self._source_repack_bytes = 0
        self._source_to_pinned_copy_ns = 0
        self._source_to_pinned_copy_bytes = 0
        self._source_materialization_ns = 0
        self._bucket_pack_cpu_ns = 0
        self._counted_transfer_names: set[str] = set()
        self._copy_count = 0
        self._copy_sizes: list[int] = []
        self._packed_final_bucket_offset = -1
        self._packed_final_bucket_bytes = 0
        self._dma_event_pairs: list[tuple[Any, Any]] = []
        self._h2d_stream_span_ms: float | None = None
        self._h2d_dma_busy_ms: float | None = None
        self._h2d_stream_idle_estimate_ms: float | None = None
        self._packed_model_bytes = 0
        self._gpu_bucket_count = 0
        self._host_slab_count = 0
        self._non_blocking = False
        self._lock = _threading.Lock()
        self._peak_pinned_bytes = 0
        self.native_pin_budget_available: bool | None = None
        self.local_bounded_budget_used = False
        self.native_pin_budget_rejected = False
        self.native_pin_budget_reason = ""
        self.host_slab_is_pinned: bool | None = None
        self.host_slab_is_pinned_per_slot: tuple[bool | None, ...] = ()

    @property
    def producer_count(self) -> int:
        return self.plan.config.producers

    @property
    def pool_bytes(self) -> int:
        return self.pool.allocated_bytes if self.pool is not None else 0

    @property
    def in_flight(self) -> bool:
        return self.ready and not self._finished and not self._closed

    @property
    def queue_depth(self) -> int:
        return self.queue.qsize()

    def snapshot(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "fallback_reason": self.fallback_reason,
            "producer_count": self.producer_count,
            "pool_bytes": self.pool_bytes,
            "queue_depth": self.queue_depth,
            "in_flight": self.in_flight,
        }

    def add_cpu_cast_ns(self, value: int) -> None:
        with self._lock:
            self._cpu_cast_ns += int(value)

    def add_source_read_ns(self, value: int) -> None:
        with self._lock:
            self._source_read_ns += int(value)

    def record_source_read(self, size: int, elapsed_ns: int) -> None:
        now = _now_ns()
        with self._lock:
            self._source_read_ns += int(elapsed_ns)
            self._source_read_calls += 1
            self._source_read_sizes.append(int(size))
            self._source_sequential_bytes += int(size)
            if self._source_read_first_ns is None:
                self._source_read_first_ns = now - int(elapsed_ns)
            self._source_read_last_ns = now

    def record_source_to_pinned_copy(self, size: int, elapsed_ns: int) -> None:
        with self._lock:
            self._source_to_pinned_copy_bytes += int(size)
            self._source_to_pinned_copy_ns += int(elapsed_ns)

    def add_source_materialization_ns(self, value: int) -> None:
        with self._lock:
            self._source_materialization_ns += int(value)

    def add_bucket_pack_cpu_ns(self, value: int) -> None:
        with self._lock:
            self._bucket_pack_cpu_ns += int(value)

    def add_transfer_bytes(self, *, cast: int = 0, exact: int = 0) -> None:
        with self._lock:
            self._cpu_cast_bytes += int(cast)
            self._exact_copy_bytes += int(exact)

    def _record_transfer_bytes_once(self, spec: TensorSpec) -> None:
        with self._lock:
            if spec.name in self._counted_transfer_names:
                return
            self._counted_transfer_names.add(spec.name)
            if spec.converted:
                self._cpu_cast_bytes += spec.nbytes
            else:
                self._exact_copy_bytes += spec.nbytes

    @property
    def cpu_cast_ms(self) -> float:
        with self._lock:
            return self._cpu_cast_ns / 1_000_000

    @property
    def cpu_cast_bytes(self) -> int:
        with self._lock:
            return self._cpu_cast_bytes

    @property
    def exact_copy_bytes(self) -> int:
        with self._lock:
            return self._exact_copy_bytes

    @property
    def source_read_ms(self) -> float:
        with self._lock:
            return self._source_read_ns / 1_000_000

    @property
    def source_materialization_ms(self) -> float:
        with self._lock:
            return self._source_materialization_ns / 1_000_000

    @property
    def bucket_pack_cpu_ms(self) -> float:
        with self._lock:
            return self._bucket_pack_cpu_ns / 1_000_000

    def close(self) -> None:
        _close_prepared(self)

    def abort(self) -> None:
        _abort_prepared(self)

    def __del__(self):  # pragma: no cover - interpreter shutdown is variable
        try:
            self.close()
        except Exception:
            pass

    def _put(self, chunk: _Chunk) -> None:
        while True:
            if self._abort_event.is_set():
                raise _StageAbort("prepare_aborted")
            try:
                self.queue.put(chunk, timeout=0.01)
                return
            except _queue.Full:
                continue

    def _read_source_bytes(self, spec: TensorSpec) -> Any:
        reader = None
        materialization_start = _now_ns()
        try:
            reader = _open_reader(spec.source_checkpoint or self.plan.checkpoint)
            with reader:
                source = reader.get_tensor(spec.name)
            import torch as _torch

            if source.device.type != "cpu":
                raise TypeError("source_not_cpu")
            if source.dtype != spec.source_dtype or tuple(source.shape) != spec.shape:
                raise TypeError("source_metadata_mismatch")
            if not source.is_contiguous():
                source = source.contiguous()
            source_bytes = source.view(_torch.uint8).reshape(-1)
            self.record_source_read(
                int(source_bytes.numel()), _now_ns() - materialization_start
            )
            expected_source_nbytes = (
                spec.source_nbytes if spec.source_nbytes is not None else spec.nbytes
            )
            if source_bytes.numel() != expected_source_nbytes:
                raise TypeError("source_byte_count_mismatch")
            if spec.converted:
                cast_start = _now_ns()
                source = _cpu_convert(source, spec.output_dtype, self.plan.config.cpu_cast)
                self.add_cpu_cast_ns(_now_ns() - cast_start)
                source_bytes = source.view(_torch.uint8).reshape(-1)
            if source_bytes.numel() != spec.nbytes:
                raise TypeError("output_byte_count_mismatch")
            self._record_transfer_bytes_once(spec)
            return source_bytes
        finally:
            self.add_source_materialization_ns(_now_ns() - materialization_start)
            reader = None

    def _read_source_range(
        self, spec: TensorSpec, source_offset: int, size: int, handle: Any
    ) -> Any:
        if spec.converted:
            raise TypeError("converted_range_unsupported")
        source_nbytes = (
            spec.source_nbytes if spec.source_nbytes is not None else spec.nbytes
        )
        source_offset = int(source_offset)
        size = int(size)
        if source_offset < 0 or size < 0 or source_offset + size > source_nbytes:
            raise TypeError("source_range_out_of_bounds")
        read_start = _now_ns()
        handle.seek(int(spec.offset) + source_offset)
        raw = bytearray(size)
        read_count = handle.readinto(raw)
        self.record_source_read(size, _now_ns() - read_start)
        if read_count != size:
            raise TypeError("source_range_short_read")
        import torch as _torch

        return _torch.frombuffer(raw, dtype=_torch.uint8, count=size)

    def _produce_source_order(self, source_jobs: _queue.Queue[Any]) -> None:
        source_handles: dict[_Path, Any] = {}
        try:
            while True:
                try:
                    block = source_jobs.get_nowait()
                except _queue.Empty:
                    return
                slab = None
                try:
                    slab = self.pool.acquire() if self.pool is not None else None
                    if slab is None:
                        raise RuntimeError("pool_unavailable")
                    checkpoint = _Path(block.file)
                    handle = source_handles.get(checkpoint)
                    if handle is None:
                        handle = checkpoint.open("rb")
                        source_handles[checkpoint] = handle
                    read_start = _now_ns()
                    read_count = _source_order.read_into(
                        handle, slab.tensor, int(block.size), int(block.file_offset)
                    )
                    self.record_source_read(
                        int(read_count), _now_ns() - read_start
                    )
                    self._put(
                        _Chunk(
                            "",
                            0,
                            int(block.size),
                            slab,
                            destination_offset=int(block.gpu_offset),
                        )
                    )
                    slab = None
                finally:
                    if slab is not None and self.pool is not None:
                        with self.pool._condition:
                            slab.in_use = False
                            slab.pending_event = None
                            self.pool._condition.notify_all()
                    source_jobs.task_done()
        finally:
            for handle in source_handles.values():
                try:
                    handle.close()
                except Exception:
                    pass
            with self._lock:
                self._stage_end_ns = max(self._stage_end_ns or 0, _now_ns())

    def _produce(self, spec: TensorSpec) -> None:
        try:
            source_bytes = self._read_source_bytes(spec)
            for offset in range(0, spec.nbytes, self.plan.config.bucket_mb * _MIB):
                size = min(self.plan.config.bucket_mb * _MIB, spec.nbytes - offset)
                slab = self.pool.acquire() if self.pool is not None else None
                if slab is None:
                    raise RuntimeError("pool_unavailable")
                try:
                    copy_start = _now_ns()
                    slab.tensor[:size].copy_(source_bytes[offset:offset + size])
                    self.record_source_to_pinned_copy(
                        size, _now_ns() - copy_start
                    )
                    self._put(_Chunk(spec.name, offset, size, slab))
                except Exception:
                    with self.pool._condition:
                        slab.in_use = False
                        slab.pending_event = None
                        self.pool._condition.notify_all()
                    raise
        finally:
            with self._lock:
                self._stage_end_ns = max(self._stage_end_ns or 0, _now_ns())

    def _produce_packed(self, bucket_plan: tuple[Any, ...] | None = None) -> None:
        source_handles: dict[_Path, Any] = {}
        materialized_sources: dict[str, Any] = {}
        try:
            if bucket_plan is None:
                packed_layout = _packed_layout(self.plan.specs)
                if packed_layout[0] is None:
                    raise _StageAbort(packed_layout[1])
                layout, packed_bytes = packed_layout
                bucket_plan = _packed_bucket_plan(
                    self.plan.specs,
                    layout,
                    packed_bytes,
                    self.plan.config.bucket_mb * _MIB,
                )
            specs_by_name = {spec.name: spec for spec in self.plan.specs}
            if isinstance(bucket_plan, _queue.Queue):
                def jobs():
                    while True:
                        try:
                            yield bucket_plan.get_nowait()
                        except _queue.Empty:
                            return
            else:
                def jobs():
                    yield from bucket_plan
            for bucket_start, bucket_size, ranges in jobs():
                slab = self.pool.acquire() if self.pool is not None else None
                if slab is None:
                    raise RuntimeError("pool_unavailable")
                try:
                    for name, source_offset, bucket_offset, size in ranges:
                        spec = specs_by_name[name]
                        if spec.converted:
                            source_bytes = materialized_sources.get(name)
                            if source_bytes is None:
                                source_bytes = self._read_source_bytes(spec)
                                materialized_sources[name] = source_bytes
                            source_view = source_bytes[source_offset:source_offset + size]
                        else:
                            checkpoint = spec.source_checkpoint or self.plan.checkpoint
                            handle = source_handles.get(checkpoint)
                            if handle is None:
                                handle = checkpoint.open("rb")
                                source_handles[checkpoint] = handle
                            source_view = self._read_source_range(
                                spec, source_offset, size, handle
                            )
                        pack_start = _now_ns()
                        slab.tensor[bucket_offset:bucket_offset + size].copy_(source_view)
                        self.add_bucket_pack_cpu_ns(_now_ns() - pack_start)
                        self.record_source_to_pinned_copy(
                            size, _now_ns() - pack_start
                        )
                        with self._lock:
                            self._source_repack_bytes += int(size)
                        if not spec.converted:
                            self._record_transfer_bytes_once(spec)
                    self._put(
                        _Chunk(
                            "",
                            0,
                            bucket_size,
                            slab,
                            destination_offset=bucket_start,
                        )
                    )
                except Exception:
                    with self.pool._condition:
                        slab.in_use = False
                        slab.pending_event = None
                        self.pool._condition.notify_all()
                    raise
        finally:
            for handle in source_handles.values():
                try:
                    handle.close()
                except Exception:
                    pass
            with self._lock:
                self._stage_end_ns = max(self._stage_end_ns or 0, _now_ns())


def _open_reader(path: _Path) -> Any:
    try:
        from safetensors import safe_open
    except Exception as exc:
        raise RuntimeError("safetensors_unavailable") from exc
    return safe_open(str(path), framework="pt", device="cpu")


def _cpu_convert(source: Any, output_dtype: Any, allow_cast: bool) -> Any:
    import torch as _torch

    if source.dtype == output_dtype:
        return source
    if not allow_cast:
        raise TypeError("cpu_cast_disabled")
    if source.dtype is not _torch.float32 or output_dtype not in (
        _torch.bfloat16, _torch.float16
    ):
        raise TypeError("dtype_conversion_unsupported")
    return source.to(dtype=output_dtype)


def _new_copy_stream(device: Any) -> Any:
    model_management = _native_model_management()
    native_stream = (
        getattr(model_management, "get_offload_stream", None)
        if model_management is not None else None
    )
    if callable(native_stream):
        try:
            stream = native_stream(device)
            if stream is not None:
                return stream
        except Exception:
            pass
    import torch as _torch

    return _torch.cuda.Stream(device=device)


def _new_event(*, timing: bool = False) -> Any:
    import torch as _torch

    return _torch.cuda.Event(enable_timing=timing)


def _cuda_available() -> bool:
    try:
        import torch as _torch

        return bool(_torch.cuda.is_available())
    except Exception:
        return False


def _native_model_management() -> Any:
    try:
        import comfy.model_management as _model_management

        return _model_management
    except Exception:
        return None


def _native_pin_budget_status(
    size: int,
) -> tuple[Callable[[], None] | bool | None, bool, bool, str]:
    model_management = _native_model_management()
    if model_management is None:
        return None, False, False, "native_pin_api_unavailable"
    ensure_budget = getattr(model_management, "ensure_pin_budget", None)
    ensure_registerable = getattr(model_management, "ensure_pin_registerable", None)
    if not callable(ensure_budget) and not callable(ensure_registerable):
        return None, False, False, "native_pin_api_unavailable"
    max_pinned = getattr(model_management, "MAX_PINNED_MEMORY", None)
    try:
        if max_pinned is None or float(max_pinned) <= 0:
            return None, False, False, "native_pin_budget_uninitialized"
    except (TypeError, ValueError):
        return None, False, False, "native_pin_budget_uninitialized"
    try:
        with _NATIVE_PIN_LOCK:
            if callable(ensure_budget) and not bool(ensure_budget(size)):
                return False, True, True, "native_pin_budget_rejected"
            if callable(ensure_registerable) and not bool(ensure_registerable(size)):
                return False, True, True, "native_pin_budget_rejected"
            previous = int(getattr(model_management, "TOTAL_PINNED_MEMORY", 0) or 0)
            model_management.TOTAL_PINNED_MEMORY = previous + int(size)
    except Exception as exc:
        return False, True, True, f"native_pin_budget_rejected:{type(exc).__name__}"

    released = False

    def release() -> None:
        nonlocal released
        if released:
            return
        released = True
        try:
            with _NATIVE_PIN_LOCK:
                current = int(
                    getattr(model_management, "TOTAL_PINNED_MEMORY", 0) or 0
                )
                model_management.TOTAL_PINNED_MEMORY = max(0, current - int(size))
        except Exception:
            pass

    return release, True, False, "native_pin_budget_reserved"


def _native_pin_reservation(size: int) -> Callable[[], None] | bool | None:
    return _native_pin_budget_status(size)[0]


def _native_non_blocking(device: Any) -> bool | None:
    model_management = _native_model_management()
    gate = (
        getattr(model_management, "device_supports_non_blocking", None)
        if model_management is not None else None
    )
    if not callable(gate):
        return None
    try:
        return bool(gate(device))
    except Exception:
        return False


def _device_of(value: Any) -> Any:
    import torch as _torch

    if value is None:
        return _torch.device("cuda")
    return _torch.device(value)


def prepare(stage_plan: StagePlan) -> PreparedStage:
    """Start bounded producers and return their owned staging state."""
    if not isinstance(stage_plan, StagePlan):
        return PreparedStage(
            StagePlan(_Path(""), StagedConfig(), fallback_reason="invalid_plan"),
            reason="invalid_plan",
        )
    if not stage_plan.supported:
        return PreparedStage(stage_plan, reason=stage_plan.fallback_reason)
    if not stage_plan.enabled:
        return PreparedStage(stage_plan, reason="flag_off")
    try:
        import safetensors
    except Exception:
        return PreparedStage(stage_plan, reason="safetensors_unavailable")
    prepared = PreparedStage(stage_plan)
    pool_bytes = stage_plan.config.pool_bytes
    reservation, native_available, native_rejected, native_reason = (
        _native_pin_budget_status(pool_bytes)
    )
    prepared.native_pin_budget_available = native_available
    prepared.native_pin_budget_rejected = native_rejected
    prepared.native_pin_budget_reason = native_reason
    if reservation is False:
        prepared.fallback_reason = native_reason
        prepared.ready = False
        return prepared
    if reservation is None:
        prepared.local_bounded_budget_used = True
    try:
        pool = _PinnedSlabPool(
            stage_plan.config.slab_count,
            stage_plan.config.bucket_mb * _MIB,
            on_close=reservation if callable(reservation) else None,
        )
    except Exception as exc:
        if callable(reservation):
            reservation()
        prepared.fallback_reason = f"pinned_memory_unavailable:{type(exc).__name__}"
        prepared.ready = False
        return prepared
    prepared.pool = pool
    prepared._peak_pinned_bytes = pool.allocated_bytes
    prepared.host_slab_is_pinned = pool.host_slab_is_pinned
    prepared.host_slab_is_pinned_per_slot = pool.host_slab_is_pinned_per_slot
    prepared._host_slab_count = len(pool.slabs)
    if prepared.host_slab_is_pinned is not True:
        pool.close()
        prepared.fallback_reason = "pinned_memory_unconfirmed"
        prepared.ready = False
        return prepared
    try:
        prepared.executor = _ThreadPoolExecutor(
            max_workers=stage_plan.config.producers,
            thread_name_prefix="staged-safetensors",
        )
        if stage_plan.source_order_eligible:
            source_blocks = tuple(
                _source_order.iter_blocks(
                    stage_plan.source_layout,
                    stage_plan.config.bucket_mb * _MIB,
                )
            )
            source_jobs: _queue.Queue[Any] = _queue.Queue()
            for block in source_blocks:
                source_jobs.put(block)
            prepared.futures = [
                prepared.executor.submit(
                    prepared._produce_source_order, source_jobs
                )
                for _ in range(
                    min(stage_plan.config.producers, len(source_blocks))
                )
            ]
        elif stage_plan.config.contiguous_gpu_buckets:
            packed_layout = _packed_layout(stage_plan.specs)
            if packed_layout[0] is None:
                _shutdown_executor(prepared, wait=True)
                pool.close()
                prepared.fallback_reason = packed_layout[1]
                prepared.ready = False
                return prepared
            layout, packed_bytes = packed_layout
            bucket_plan = _packed_bucket_plan(
                stage_plan.specs,
                layout,
                packed_bytes,
                stage_plan.config.bucket_mb * _MIB,
            )
            bucket_jobs: _queue.Queue[Any] = _queue.Queue()
            for bucket in bucket_plan:
                bucket_jobs.put(bucket)
            prepared.futures = [
                prepared.executor.submit(
                    prepared._produce_packed, bucket_jobs
                )
                for _ in range(
                    min(stage_plan.config.producers, len(bucket_plan))
                )
            ]
        else:
            prepared.futures = [
                prepared.executor.submit(prepared._produce, spec)
                for spec in stage_plan.specs
            ]
        if not prepared.futures:
            prepared._stage_end_ns = _now_ns()
            prepared._finished = True
            prepared.executor.shutdown(wait=True)
            prepared.executor = None
        return prepared
    except Exception as exc:
        prepared.abort()
        prepared.fallback_reason = f"prepare_exception:{type(exc).__name__}"
        prepared.ready = False
        return prepared


def _future_errors(prepared: PreparedStage) -> list[BaseException]:
    errors: list[BaseException] = []
    for future in prepared.futures:
        try:
            future.result()
        except BaseException as exc:  # preserve exact fallback type, not traceback
            errors.append(exc)
    return errors


def _drain_queue(prepared: PreparedStage) -> None:
    while True:
        try:
            chunk = prepared.queue.get_nowait()
        except _queue.Empty:
            return
        try:
            if prepared.pool is not None:
                with prepared.pool._condition:
                    chunk.slab.in_use = False
                    chunk.slab.pending_event = None
        finally:
            prepared.queue.task_done()


def _shutdown_executor(prepared: PreparedStage, *, wait: bool) -> None:
    executor = prepared.executor
    prepared.executor = None
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=not wait)


def _abort_prepared(prepared: PreparedStage) -> None:
    if prepared._closed:
        return
    prepared._abort_event.set()
    if prepared.pool is not None:
        prepared.pool.abort()
    stream = prepared.copy_stream
    if stream is not None:
        try:
            stream.synchronize()
        except Exception:
            pass
    _shutdown_executor(prepared, wait=True)
    _drain_queue(prepared)
    if prepared.pool is not None:
        prepared.pool.close()
    prepared._gpu_owner = None
    prepared._closed = True
    prepared._finished = True


def _close_prepared(prepared: PreparedStage) -> None:
    if prepared._closed:
        return
    if prepared.copy_stream is not None:
        try:
            prepared.copy_stream.synchronize()
        except Exception:
            pass
    prepared._abort_event.set()
    if prepared.pool is not None:
        prepared.pool.abort()
    _shutdown_executor(prepared, wait=True)
    _drain_queue(prepared)
    if prepared.pool is not None:
        prepared.pool.close()
    prepared._gpu_owner = None
    prepared._closed = True


def _result_from(prepared: PreparedStage, *, success: bool, tensors: dict[str, Any],
                 disk_ms: float | None, enqueue_ms: float | None,
                 device_ms: float | None, consumer_wait_ms: float,
                 fallback_reason: str | None = None, error: str = "",
                 gpu_owner: Any = None) -> StageResult:
    pool = prepared.pool
    producer_wait_ms = pool.wait_ms if pool is not None else 0.0
    bytes_transferred = prepared.plan.total_tensor_bytes
    peak_pinned_bytes = max(
        prepared._peak_pinned_bytes,
        pool.allocated_bytes if pool is not None else 0,
    )
    gbps = None
    if device_ms is not None and device_ms > 0:
        gbps = (bytes_transferred / (1024.0 ** 3)) / (device_ms / 1000.0)
    copy_sizes = tuple(prepared._copy_sizes)
    packed_bytes = int(prepared._packed_model_bytes or 0)
    span_ms = prepared._h2d_stream_span_ms
    dma_busy_ms = prepared._h2d_dma_busy_ms
    if span_ms is None:
        span_ms = device_ms
    h2d_dma_gbps = None
    h2d_span_gbps = None
    if packed_bytes > 0 and dma_busy_ms is not None and dma_busy_ms > 0:
        h2d_dma_gbps = (packed_bytes / (1024.0 ** 3)) / (dma_busy_ms / 1000.0)
    if packed_bytes > 0 and span_ms is not None and span_ms > 0:
        h2d_span_gbps = (packed_bytes / (1024.0 ** 3)) / (span_ms / 1000.0)
    median_copy_bytes = None
    if copy_sizes:
        ordered_sizes = sorted(copy_sizes)
        middle = len(ordered_sizes) // 2
        median_copy_bytes = (
            ordered_sizes[middle]
            if len(ordered_sizes) % 2
            else (ordered_sizes[middle - 1] + ordered_sizes[middle]) // 2
        )
    source_sizes = tuple(prepared._source_read_sizes)
    source_read_wall_ms = 0.0
    if (
        prepared._source_read_first_ns is not None
        and prepared._source_read_last_ns is not None
    ):
        source_read_wall_ms = max(
            0.0,
            (prepared._source_read_last_ns - prepared._source_read_first_ns)
            / 1_000_000,
        )
    source_model_bytes = sum(
        int(spec.source_nbytes if spec.source_nbytes is not None else spec.nbytes)
        for spec in prepared.plan.specs
    )
    return StageResult(
        success=success,
        tensors=tensors if success else {},
        checkpoint_bytes=prepared.plan.checkpoint_bytes,
        disk_to_stage_ms=disk_ms,
        cpu_cast_ms=prepared.cpu_cast_ms,
        h2d_enqueue_ms=enqueue_ms,
        h2d_device_ms=device_ms,
        bind_independent_transfer=True,
        peak_pinned_bytes=peak_pinned_bytes,
        producer_wait_ms=producer_wait_ms,
        consumer_wait_ms=consumer_wait_ms,
        effective_h2d_gbps=gbps,
        fallback_reason=fallback_reason,
        error=error[:300],
        cpu_cast_bytes=prepared.cpu_cast_bytes,
        exact_copy_bytes=prepared.exact_copy_bytes,
        non_blocking=prepared._non_blocking,
        stream_count=1,
        copy_count=prepared._copy_count,
        bucket_bytes=prepared.plan.config.bucket_mb * _MIB,
        producer_count=prepared.plan.config.producers,
        native_pin_budget_available=prepared.native_pin_budget_available,
        local_bounded_budget_used=prepared.local_bounded_budget_used,
        native_pin_budget_rejected=prepared.native_pin_budget_rejected,
        host_slab_is_pinned=prepared.host_slab_is_pinned,
        host_slab_is_pinned_all=prepared.host_slab_is_pinned,
        host_slab_is_pinned_per_slot=prepared.host_slab_is_pinned_per_slot,
        h2d_stream_span_ms=span_ms,
        h2d_dma_busy_ms=dma_busy_ms,
        h2d_stream_idle_estimate_ms=prepared._h2d_stream_idle_estimate_ms,
        h2d_dma_gbps=h2d_dma_gbps,
        h2d_span_gbps=h2d_span_gbps,
        packed_model_bytes=packed_bytes,
        host_bucket_bytes_configured=prepared.plan.config.bucket_mb * _MIB,
        host_slab_count=prepared._host_slab_count,
        gpu_bucket_count=prepared._gpu_bucket_count,
        h2d_bucket_count=len(copy_sizes),
        h2d_full_bucket_count=sum(
            1 for size in copy_sizes
            if size == prepared.plan.config.bucket_mb * _MIB
        ),
        h2d_final_bucket_bytes=(
            prepared._packed_final_bucket_bytes or (copy_sizes[-1] if copy_sizes else 0)
            if packed_bytes
            else (copy_sizes[-1] if copy_sizes else 0)
        ),
        min_h2d_copy_bytes=min(copy_sizes) if copy_sizes else None,
        median_h2d_copy_bytes=median_copy_bytes,
        max_h2d_copy_bytes=max(copy_sizes) if copy_sizes else None,
        slab_reuse_wait_ms=producer_wait_ms,
        tensor_count=len(prepared.plan.specs),
        source_read_ms=prepared.source_read_ms,
        source_materialization_ms=prepared.source_materialization_ms,
        bucket_pack_cpu_ms=prepared.bucket_pack_cpu_ms,
        bucket_ready_wait_ms=consumer_wait_ms,
        source_order_enabled=prepared.plan.config.source_order_enabled,
        source_order_eligible=prepared.plan.source_order_eligible,
        source_order_fallback_reason=prepared.plan.source_order_fallback_reason,
        source_file_count=len(prepared.plan.checkpoints),
        source_tensor_count=len(prepared.plan.specs),
        source_model_bytes=source_model_bytes,
        source_read_calls=prepared._source_read_calls,
        source_read_min_bytes=min(source_sizes) if source_sizes else None,
        source_read_median_bytes=(
            sorted(source_sizes)[len(source_sizes) // 2]
            if len(source_sizes) % 2
            else (
                (sorted(source_sizes)[len(source_sizes) // 2 - 1]
                 + sorted(source_sizes)[len(source_sizes) // 2]) // 2
                if source_sizes else None
            )
        ),
        source_read_max_bytes=max(source_sizes) if source_sizes else None,
        source_sequential_bytes=prepared._source_sequential_bytes,
        source_repack_bytes=prepared._source_repack_bytes,
        source_read_wall_ms=source_read_wall_ms,
        source_read_worker_accumulated_ms=prepared.source_read_ms,
        source_to_pinned_copy_bytes=prepared._source_to_pinned_copy_bytes,
        source_to_pinned_copy_ms=prepared._source_to_pinned_copy_ns / 1_000_000,
        alignment_fallback_tensor_count=(
            prepared.plan.alignment_fallback_tensor_count
        ),
        _owner=prepared if success else None,
        _gpu_owner=gpu_owner if success else None,
    )


def _prepared_failure(
    prepared: PreparedStage, reason: str, *, error: str = ""
) -> StageResult:
    prepared.abort()
    return _result_from(
        prepared,
        success=False,
        tensors={},
        disk_ms=None,
        enqueue_ms=None,
        device_ms=None,
        consumer_wait_ms=0.0,
        fallback_reason=reason,
        error=error,
    )


def commit(
    prepared: PreparedStage,
    device: Any = None,
    *,
    target_device: Any = None,
) -> StageResult:
    """Transfer prepared slabs to CUDA and return an unbound state dictionary."""
    if not isinstance(prepared, PreparedStage):
        return fallback("invalid_prepared")
    if prepared.fallback_reason:
        committed = _result_from(
            prepared,
            success=False,
            tensors={},
            disk_ms=None,
            enqueue_ms=None,
            device_ms=None,
            consumer_wait_ms=0.0,
            fallback_reason=prepared.fallback_reason,
        )
        prepared.close()
        return committed
    if prepared._closed or not prepared.ready:
        return fallback("prepared_unavailable", checkpoint_bytes=prepared.plan.checkpoint_bytes)
    if prepared._finished and prepared.copy_stream is None and not prepared.plan.specs:
        return _result_from(
            prepared, success=True, tensors={}, disk_ms=0.0, enqueue_ms=0.0,
            device_ms=0.0, consumer_wait_ms=0.0,
        )
    if not _cuda_available():
        return _prepared_failure(prepared, "cuda_unavailable")
    try:
        if device is None:
            device = target_device
        target = _device_of(device if device is not None else prepared.plan.target_device)
        if target.type != "cuda":
            return _prepared_failure(prepared, "target_not_cuda")
        native_non_blocking = _native_non_blocking(target)
        if prepared.plan.config.async_h2d and native_non_blocking is False:
            return _prepared_failure(prepared, "non_blocking_unsupported")
        prepared._non_blocking = (
            prepared.plan.config.async_h2d
            if native_non_blocking is None
            else bool(prepared.plan.config.async_h2d and native_non_blocking)
        )
        import torch as _torch

        prepared.copy_stream = _new_copy_stream(target)
        outputs: dict[str, Any] = {}
        packed_owner = None
        with _torch.cuda.stream(prepared.copy_stream):
            source_layout = prepared.plan.source_layout
            if prepared.plan.source_order_eligible:
                if source_layout is None:
                    return _prepared_failure(
                        prepared, "source_order_layout_unavailable"
                    )
                packed_bytes = int(source_layout.storage_bytes)
                prepared._packed_model_bytes = packed_bytes
                prepared._gpu_bucket_count = 1 if packed_bytes else 0
                packed_owner = _torch.empty(
                    max(1, packed_bytes), dtype=_torch.uint8, device=target
                )
                if packed_bytes and packed_owner.data_ptr() % int(
                    source_layout.alignment
                ):
                    return _prepared_failure(
                        prepared, "source_order_alignment_failure"
                    )
                source_offsets = {
                    tensor.name: tensor.dest_offset
                    for tensor in source_layout.tensors
                }
                for spec in prepared.plan.specs:
                    if spec.nbytes == 0:
                        outputs[spec.name] = _torch.empty(
                            spec.shape, dtype=spec.output_dtype, device=target
                        )
                        continue
                    destination_offset = source_offsets.get(spec.name)
                    if destination_offset is None:
                        return _prepared_failure(
                            prepared, "source_order_tensor_offset_unavailable"
                        )
                    raw = packed_owner.narrow(
                        0, int(destination_offset), spec.nbytes
                    )
                    view = raw.view(spec.output_dtype).reshape(spec.shape)
                    if view.numel() * view.element_size() != spec.nbytes:
                        return _prepared_failure(
                            prepared, "source_order_alignment_failure"
                        )
                    outputs[spec.name] = view
            elif prepared.plan.config.contiguous_gpu_buckets:
                packed_layout = _packed_layout(prepared.plan.specs)
                if packed_layout[0] is None:
                    return _prepared_failure(prepared, packed_layout[1])
                layout, packed_bytes = packed_layout
                prepared._packed_model_bytes = packed_bytes
                prepared._gpu_bucket_count = 1 if packed_bytes else 0
                packed_owner = _torch.empty(
                    max(1, packed_bytes), dtype=_torch.uint8, device=target
                )
                max_alignment = max(
                    (_dtype_itemsize(spec.output_dtype)
                     for spec in prepared.plan.specs),
                    default=1,
                )
                if packed_bytes and packed_owner.data_ptr() % max_alignment:
                    return _prepared_failure(
                        prepared, "E1_CONTIGUOUS_BUCKETS_DEFERRED"
                    )
                for spec in prepared.plan.specs:
                    if spec.nbytes == 0:
                        outputs[spec.name] = _torch.empty(
                            spec.shape, dtype=spec.output_dtype, device=target
                        )
                        continue
                    raw = packed_owner.narrow(0, layout[spec.name], spec.nbytes)
                    view = raw.view(spec.output_dtype).reshape(spec.shape)
                    if view.numel() * view.element_size() != spec.nbytes:
                        return _prepared_failure(
                            prepared, "E1_CONTIGUOUS_BUCKETS_DEFERRED"
                        )
                    outputs[spec.name] = view
            else:
                for spec in prepared.plan.specs:
                    outputs[spec.name] = _torch.empty(
                        spec.shape, dtype=spec.output_dtype, device=target
                    )
        start_event = _new_event(timing=True)
        end_event = _new_event(timing=True)
        enqueue_start = _now_ns()
        consumer_wait_ns = 0
        with _torch.cuda.stream(prepared.copy_stream):
            start_event.record(prepared.copy_stream)
            while True:
                bucket_wait_start_ns = _now_ns()
                try:
                    chunk = prepared.queue.get(timeout=0.01)
                except _queue.Empty:
                    consumer_wait_ns += _now_ns() - bucket_wait_start_ns
                    if all(future.done() for future in prepared.futures) and prepared.queue.empty():
                        break
                    continue
                try:
                    if chunk.destination_offset is None:
                        dst = outputs[chunk.name].view(_torch.uint8).reshape(-1)
                        destination_offset = chunk.offset
                    else:
                        if packed_owner is None:
                            raise RuntimeError("packed_gpu_owner_unavailable")
                        dst = packed_owner
                        destination_offset = chunk.destination_offset
                    dma_start_event = None
                    dma_end_event = None
                    if chunk.destination_offset is not None:
                        dma_start_event = _new_event(timing=True)
                        dma_end_event = _new_event(timing=True)
                        dma_start_event.record(prepared.copy_stream)
                    dst[destination_offset:destination_offset + chunk.size].copy_(
                        chunk.slab.tensor[:chunk.size],
                        non_blocking=prepared._non_blocking,
                    )
                    if dma_end_event is not None:
                        dma_end_event.record(prepared.copy_stream)
                        prepared._dma_event_pairs.append(
                            (dma_start_event, dma_end_event)
                        )
                        event = dma_end_event
                    else:
                        event = _new_event(timing=False)
                        event.record(prepared.copy_stream)
                    if prepared.pool is not None:
                        prepared.pool.release(chunk.slab, event)
                    prepared._copy_count += 1
                    prepared._copy_sizes.append(chunk.size)
                    if (
                        chunk.destination_offset is not None
                        and chunk.destination_offset
                        > prepared._packed_final_bucket_offset
                    ):
                        prepared._packed_final_bucket_offset = chunk.destination_offset
                        prepared._packed_final_bucket_bytes = chunk.size
                finally:
                    prepared.queue.task_done()
            end_event.record(prepared.copy_stream)
        errors = _future_errors(prepared)
        _shutdown_executor(prepared, wait=True)
        prepared._stage_end_ns = prepared._stage_end_ns or _now_ns()
        prepared._finished = True
        current_stream = _torch.cuda.current_stream(device=target)
        current_stream.wait_stream(prepared.copy_stream)
        device_ms = None
        try:
            if bool(end_event.query()):
                device_ms = round(float(start_event.elapsed_time(end_event)), 3)
        except Exception:
            device_ms = None
        prepared._h2d_stream_span_ms = device_ms
        if prepared._dma_event_pairs and device_ms is not None:
            try:
                dma_busy_ms = sum(
                    float(start.elapsed_time(end))
                    for start, end in prepared._dma_event_pairs
                )
                prepared._h2d_dma_busy_ms = round(dma_busy_ms, 3)
                prepared._h2d_stream_idle_estimate_ms = round(
                    max(0.0, device_ms - prepared._h2d_dma_busy_ms), 3
                )
            except Exception:
                prepared._h2d_dma_busy_ms = None
                prepared._h2d_stream_idle_estimate_ms = None
        disk_ms = max(0.0, (prepared._stage_end_ns - prepared._stage_start_ns) / 1_000_000)
        enqueue_ms = (_now_ns() - enqueue_start) / 1_000_000
        if errors:
            reason = f"producer_exception:{type(errors[0]).__name__}"
            error = str(errors[0])
            _abort_prepared(prepared)
            return _result_from(
                prepared, success=False, tensors={}, disk_ms=disk_ms,
                enqueue_ms=enqueue_ms, device_ms=device_ms,
                consumer_wait_ms=consumer_wait_ns / 1_000_000,
                fallback_reason=reason, error=error,
            )
        if prepared.plan.source_order_eligible:
            for spec in prepared.plan.specs:
                prepared._record_transfer_bytes_once(spec)
        prepared._gpu_owner = packed_owner
        return _result_from(
            prepared, success=True, tensors=outputs, disk_ms=disk_ms,
            enqueue_ms=enqueue_ms, device_ms=device_ms,
            consumer_wait_ms=consumer_wait_ns / 1_000_000,
            gpu_owner=packed_owner,
        )
    except Exception as exc:
        _abort_prepared(prepared)
        return _result_from(
            prepared, success=False, tensors={}, disk_ms=None, enqueue_ms=None,
            device_ms=None, consumer_wait_ms=0.0,
            fallback_reason=f"commit_exception:{type(exc).__name__}",
            error=str(exc),
        )


def result(committed: StageResult) -> StageResult:
    """Return the committed transfer for adapters with an explicit result phase."""
    return committed


__all__ = [
    "PreparedStage",
    "StagePlan",
    "StageResult",
    "StagedConfig",
    "TensorSpec",
    "commit",
    "config_from_env",
    "fallback",
    "plan",
    "prepare",
    "result",
]
