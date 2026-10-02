#!/usr/bin/env python3
"""Local Phase-E staged-transfer microbenchmark.

The default synthetic provider exercises the transport mechanics without
importing any ComfyUI runtime code.  An unfinished E1 implementation can be
used with ``--mode e1 --e1-module package.module``.  The provider contract is
documented in ``V2_BATCH_E4_STAGED_TRANSPORT_BENCHMARK.md``.
"""

from __future__ import annotations

import argparse
import gc
import importlib
import inspect
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Callable, Iterable, Mapping


DEFAULT_PRODUCERS = 4
DEFAULT_BUCKET_BYTES = 256 * 1024 * 1024
DEFAULT_POOL_BYTES = 1024 * 1024 * 1024
DEFAULT_SMALL_COPY_BYTES = 4 * 1024 * 1024
DEFAULT_REPEATS = 3
DEFAULT_WARMUP = 1
DEFAULT_POOL_ALLOCATION_SAMPLES = 3


def _parse_bytes(value: str) -> int:
    text = str(value).strip().lower().replace(" ", "")
    units = (("gib", 1 << 30), ("gb", 10**9), ("mib", 1 << 20), ("mb", 10**6), ("kib", 1 << 10), ("kb", 10**3))
    for suffix, multiplier in units:
        if text.endswith(suffix):
            return int(float(text[: -len(suffix)]) * multiplier)
    return int(text)


def _median(samples: Iterable[float]) -> float | None:
    values = [float(value) for value in samples]
    return round(statistics.median(values), 3) if values else None


def _gbps(byte_count: int, milliseconds: float | None) -> float | None:
    if milliseconds is None or milliseconds <= 0:
        return None
    return round(byte_count / 1e9 / (milliseconds / 1000.0), 3)


def _format_number(value: Any) -> str:
    if value is None:
        return "UNAVAILABLE"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


@dataclass(frozen=True)
class BenchmarkConfig:
    producers: int = DEFAULT_PRODUCERS
    bucket_bytes: int = DEFAULT_BUCKET_BYTES
    pool_bytes: int = DEFAULT_POOL_BYTES
    small_copy_bytes: int = DEFAULT_SMALL_COPY_BYTES
    repeats: int = DEFAULT_REPEATS
    warmup: int = DEFAULT_WARMUP
    pool_allocation_samples: int = DEFAULT_POOL_ALLOCATION_SAMPLES
    device: str = "cuda:0"

    @property
    def total_bytes(self) -> int:
        return self.producers * self.bucket_bytes

    def as_dict(self) -> dict[str, Any]:
        return {
            "producers": self.producers,
            "bucket_bytes": self.bucket_bytes,
            "pool_bytes": self.pool_bytes,
            "small_copy_bytes": self.small_copy_bytes,
            "total_bytes": self.total_bytes,
            "repeats": self.repeats,
            "warmup": self.warmup,
            "pool_allocation_samples": self.pool_allocation_samples,
            "streams": 1,
            "device": self.device,
        }


def _ranges(total_bytes: int, chunk_bytes: int) -> list[tuple[int, int]]:
    if chunk_bytes <= 0:
        raise ValueError("copy size must be positive")
    return [
        (offset, min(chunk_bytes, total_bytes - offset))
        for offset in range(0, total_bytes, chunk_bytes)
    ]


def _view_bytes(tensor: Any, offset: int, size: int) -> Any:
    element_size = int(tensor.element_size())
    if offset % element_size or size % element_size:
        raise ValueError("copy range is not aligned to the tensor dtype")
    return tensor.narrow(0, offset // element_size, size // element_size)


def _summarize(
    label: str,
    samples: Sequence[Mapping[str, Any]],
    byte_count: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": label,
        "supported": bool(samples),
        "bytes": byte_count,
        "samples": list(samples),
    }
    for field in ("wall_ms", "cuda_ms", "enqueue_ms", "stage_ms", "cast_ms", "total_ms"):
        values = [float(sample[field]) for sample in samples if sample.get(field) is not None]
        if values:
            result[field] = _median(values)
    if result.get("cuda_ms") is not None:
        result["gbps"] = _gbps(byte_count, result["cuda_ms"])
    if result.get("wall_ms") is not None:
        result["wall_gbps"] = _gbps(byte_count, result["wall_ms"])
    if result.get("total_ms") is not None:
        result["total_gbps"] = _gbps(byte_count, result["total_ms"])
    return result


def _call_with_supported_kwargs(factory: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return factory(**kwargs)
    if any(parameter.kind == parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return factory(**kwargs)
    accepted = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return factory(**accepted)


def _load_e1_provider(module_spec: str, config: BenchmarkConfig) -> Any:
    module_name, separator, factory_name = module_spec.partition(":")
    module = importlib.import_module(module_name)
    candidates = [factory_name] if separator and factory_name else []
    candidates.extend(("create_local_transport", "create_staged_transport", "StagedTransport"))
    factory = next((getattr(module, name, None) for name in candidates if name), None)
    if factory is None:
        raise AttributeError(
            f"{module_name} has no E1 factory; expected create_local_transport, "
            "create_staged_transport, or StagedTransport"
        )
    kwargs = {
        "config": config,
        "producers": config.producers,
        "bucket_bytes": config.bucket_bytes,
        "pool_bytes": config.pool_bytes,
        "streams": 1,
        "stream_count": 1,
        "device": config.device,
    }
    try:
        return _call_with_supported_kwargs(factory, kwargs)
    except TypeError:
        return factory(config)


def _run_e1_provider(provider: Any, config: BenchmarkConfig) -> dict[str, Any]:
    methods = ("benchmark_local", "run_local_benchmark", "benchmark", "run_microbenchmark")
    method = next((getattr(provider, name, None) for name in methods if hasattr(provider, name)), None)
    if method is None and callable(provider):
        method = provider
    if method is None:
        raise AttributeError(
            "E1 provider must expose benchmark_local, run_local_benchmark, "
            "benchmark, run_microbenchmark, or be callable"
        )
    kwargs = {
        "config": config,
        "producers": config.producers,
        "bucket_bytes": config.bucket_bytes,
        "pool_bytes": config.pool_bytes,
        "streams": 1,
        "stream_count": 1,
        "device": config.device,
        "repeats": config.repeats,
        "warmup": config.warmup,
    }
    try:
        raw = _call_with_supported_kwargs(method, kwargs)
    except TypeError:
        raw = method(config)
    if not isinstance(raw, Mapping):
        raise TypeError("E1 benchmark method must return a mapping")
    result = dict(raw)
    result.setdefault("mode", "e1")
    result.setdefault("config", config.as_dict())
    result.setdefault("modal_deploys", 0)
    result.setdefault("modal_requests", 0)
    return result


class SyntheticPinnedBufferBenchmark:
    def __init__(self, config: BenchmarkConfig) -> None:
        import torch

        self.torch: Any = torch
        self.config = config
        self.dtype: Any = getattr(torch, "bfloat16")
        self.pool_base: Any = None
        self.pool: Any = None
        self.pageable: Any = None
        self.destination: Any = None

    def _allocate_pool(self) -> Any:
        return self.torch.empty(
            self.config.pool_bytes,
            dtype=self.torch.uint8,
            pin_memory=True,
        )

    def _allocation_cost(self) -> dict[str, Any]:
        samples: list[float] = []
        error = ""
        for _ in range(self.config.pool_allocation_samples):
            started = time.perf_counter_ns()
            try:
                allocation = self._allocate_pool()
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                break
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            samples.append(elapsed)
            del allocation
            gc.collect()
        return {
            "supported": bool(samples),
            "samples_ms": [round(value, 3) for value in samples],
            "cold_ms": round(samples[0], 3) if samples else None,
            "steady_ms": _median(samples[1:]) if len(samples) > 1 else None,
            "median_ms": _median(samples),
            "error": error,
            "bytes": self.config.pool_bytes,
        }

    def _copy_ranges(
        self,
        source: Any,
        destination: Any,
        ranges: list[tuple[int, int]],
        stream: Any,
        non_blocking: bool,
    ) -> dict[str, Any]:
        torch: Any = self.torch
        start_event = torch.cuda.Event(enable_timing=True)
        end_event = torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        wall_started = time.perf_counter_ns()
        with torch.cuda.stream(stream):
            start_event.record(stream)
            for offset, size in ranges:
                destination_view = _view_bytes(destination, offset, size)
                source_view = _view_bytes(source, offset, size)
                destination_view.copy_(source_view, non_blocking=non_blocking)
            end_event.record(stream)
        enqueue_ms = (time.perf_counter_ns() - wall_started) / 1_000_000
        end_event.synchronize()
        wall_ms = (time.perf_counter_ns() - wall_started) / 1_000_000
        cuda_ms = float(start_event.elapsed_time(end_event))
        return {
            "wall_ms": round(wall_ms, 3),
            "enqueue_ms": round(enqueue_ms, 3),
            "cuda_ms": round(cuda_ms, 3),
            "copy_count": len(ranges),
            "gbps": _gbps(self.config.total_bytes, cuda_ms),
        }

    def _stage_ranges(
        self,
        ranges: list[tuple[int, int]],
        workers: int,
    ) -> float:
        started = time.perf_counter_ns()

        def stage_one(item: tuple[int, int]) -> None:
            offset, size = item
            _view_bytes(self.pool, offset, size).copy_(_view_bytes(self.pageable, offset, size))

        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(ranges)))) as executor:
            list(executor.map(stage_one, ranges))
        return round((time.perf_counter_ns() - started) / 1_000_000, 3)

    def _repeat_copy(
        self,
        label: str,
        source: Any,
        ranges: list[tuple[int, int]],
        stream: Any,
        non_blocking: bool,
    ) -> dict[str, Any]:
        for _ in range(self.config.warmup):
            self._copy_ranges(source, self.destination, ranges, stream, non_blocking)
        samples = [
            self._copy_ranges(source, self.destination, ranges, stream, non_blocking)
            for _ in range(self.config.repeats)
        ]
        result = _summarize(label, samples, self.config.total_bytes)
        result["copy_count"] = len(ranges)
        result["non_blocking"] = non_blocking
        is_pinned = getattr(source, "is_pinned", None)
        result["dma_source_pinned_fraction"] = 1.0 if callable(is_pinned) and is_pinned() else 0.0
        return result

    def _repeat_staged(
        self,
        label: str,
        ranges: list[tuple[int, int]],
        stream: Any,
    ) -> dict[str, Any]:
        def one() -> dict[str, Any]:
            stage_ms = self._stage_ranges(ranges, self.config.producers)
            copy = self._copy_ranges(self.pool, self.destination, ranges, stream, True)
            total_ms = stage_ms + float(copy["wall_ms"])
            return {
                "stage_ms": stage_ms,
                "wall_ms": round(total_ms, 3),
                "total_ms": round(total_ms, 3),
                "cuda_ms": copy["cuda_ms"],
                "enqueue_ms": copy["enqueue_ms"],
                "copy_count": len(ranges),
            }

        for _ in range(self.config.warmup):
            one()
        samples = [one() for _ in range(self.config.repeats)]
        result = _summarize(label, samples, self.config.total_bytes)
        result["copy_count"] = len(ranges)
        result["non_blocking"] = True
        result["stage_workers"] = self.config.producers
        result["dma_source_pinned_fraction"] = 1.0
        return result

    def _repeat_cast(self, stream: Any) -> dict[str, Any]:
        torch: Any = self.torch
        fp32 = torch.empty(
            self.config.total_bytes // self.dtype.itemsize,
            dtype=torch.float32,
        )
        fp32.zero_()

        def one() -> dict[str, Any]:
            started = time.perf_counter_ns()
            cast = fp32.to(dtype=self.dtype)
            cast_ms = (time.perf_counter_ns() - started) / 1_000_000
            copy = self._copy_ranges(cast, self.destination, [(0, self.config.total_bytes)], stream, False)
            total_ms = cast_ms + float(copy["wall_ms"])
            del cast
            return {
                "cast_ms": round(cast_ms, 3),
                "wall_ms": round(total_ms, 3),
                "total_ms": round(total_ms, 3),
                "cuda_ms": copy["cuda_ms"],
                "enqueue_ms": copy["enqueue_ms"],
                "copy_count": 1,
            }

        try:
            for _ in range(self.config.warmup):
                one()
            samples = [one() for _ in range(self.config.repeats)]
        finally:
            del fp32
            gc.collect()
        result = _summarize("fp32_cast_then_h2d", samples, self.config.total_bytes)
        result["copy_count"] = 1
        result["non_blocking"] = False
        result["dma_source_pinned_fraction"] = 0.0
        return result

    def run(self) -> dict[str, Any]:
        torch: Any = self.torch
        if not torch.cuda.is_available():
            return {
                "mode": "synthetic",
                "status": "UNAVAILABLE",
                "reason": "CUDA is not available",
                "config": self.config.as_dict(),
                "modal_deploys": 0,
                "modal_requests": 0,
            }
        if self.config.pool_bytes < self.config.total_bytes:
            raise ValueError("pool_bytes must cover producers * bucket_bytes")
        if self.config.total_bytes % self.dtype.itemsize:
            raise ValueError("bucketed transfer size must be dtype aligned")

        allocation = self._allocation_cost()
        if not allocation["supported"]:
            return {
                "mode": "synthetic",
                "status": "UNAVAILABLE",
                "reason": "pinned pool allocation failed",
                "pool_allocation": allocation,
                "config": self.config.as_dict(),
                "modal_deploys": 0,
                "modal_requests": 0,
            }

        stream = torch.cuda.Stream()
        self.pageable = torch.empty(self.config.total_bytes // self.dtype.itemsize, dtype=self.dtype)
        self.pageable.zero_()
        self.destination = torch.empty_like(self.pageable, device=self.config.device)
        self.pool_base = self._allocate_pool()
        self.pool = self.pool_base[: self.config.total_bytes].view(self.dtype)
        setup_started = time.perf_counter_ns()
        self.pool.copy_(self.pageable)
        setup_stage_ms = round((time.perf_counter_ns() - setup_started) / 1_000_000, 3)

        bucket_ranges = _ranges(self.config.total_bytes, self.config.bucket_bytes)
        small_ranges = _ranges(self.config.total_bytes, self.config.small_copy_bytes)
        results: dict[str, Any] = {
            "mode": "synthetic",
            "status": "OK",
            "config": self.config.as_dict(),
            "dtype": str(self.dtype),
            "pool_allocation": allocation,
            "pool_setup_stage_ms": setup_stage_ms,
            "pool_is_pinned": bool(self.pool.is_pinned()),
            "bucket_supported": True,
            "stream_count": 1,
        }
        try:
            results["pageable_h2d"] = self._repeat_copy(
                "pageable_h2d", self.pageable, [(0, self.config.total_bytes)], stream, False
            )
            results["preallocated_pinned_h2d"] = self._repeat_copy(
                "preallocated_pinned_h2d", self.pool, [(0, self.config.total_bytes)], stream, True
            )
            results["pinned_many_small_h2d"] = self._repeat_copy(
                "pinned_many_small_h2d", self.pool, small_ranges, stream, True
            )
            results["pinned_bucketed_h2d"] = self._repeat_copy(
                "pinned_bucketed_h2d", self.pool, bucket_ranges, stream, True
            )
            results["staged_same_dtype_many_small"] = self._repeat_staged(
                "staged_same_dtype_many_small", small_ranges, stream
            )
            results["staged_same_dtype_bucketed"] = self._repeat_staged(
                "staged_same_dtype_bucketed", bucket_ranges, stream
            )
            results["fp32_cast_then_h2d"] = self._repeat_cast(stream)
        finally:
            torch.cuda.synchronize()
            del stream
            del self.destination
            del self.pool
            del self.pool_base
            del self.pageable
            gc.collect()
            torch.cuda.empty_cache()
        results.update(_decision_fields(results))
        results["modal_deploys"] = 0
        results["modal_requests"] = 0
        return results


def _decision_fields(result: Mapping[str, Any]) -> dict[str, Any]:
    pageable = result.get("pageable_h2d", {})
    pinned = result.get("preallocated_pinned_h2d", {})
    if not pageable.get("supported") or not pinned.get("supported"):
        fast_path = "UNAVAILABLE"
        pinned_gbps = None
        pageable_gbps = None
    else:
        pinned_gbps = pinned.get("gbps")
        pageable_gbps = pageable.get("gbps")
        host_issue_fast = float(pinned.get("enqueue_ms", 0)) < float(pinned.get("cuda_ms", 0)) * 0.5
        bandwidth_win = float(pinned_gbps or 0) >= float(pageable_gbps or 0) * 1.10
        fast_path = "YES" if host_issue_fast and bandwidth_win else "NO"

    many = result.get("staged_same_dtype_many_small", {})
    bucketed = result.get("staged_same_dtype_bucketed", {})
    if not many.get("supported") or not bucketed.get("supported"):
        bucketing = "UNAVAILABLE"
    else:
        many_ms = float(many.get("total_ms", many.get("wall_ms", 0)))
        bucketed_ms = float(bucketed.get("total_ms", bucketed.get("wall_ms", 0)))
        reduction = 1.0 - bucketed_ms / many_ms if many_ms > 0 else 0.0
        bucketing = (
            f"MATERIAL_GAIN ({reduction * 100:.1f}% lower end_to_end)"
            if reduction >= 0.10
            else f"NO_MATERIAL_GAIN ({reduction * 100:.1f}% lower end_to_end)"
        )
    cast = result.get("fp32_cast_then_h2d", {})
    return {
        "LOCAL_PINNED_FAST_PATH_CONFIRMED": fast_path,
        "PINNED_GBPS": pinned_gbps,
        "PAGEABLE_GBPS": pageable_gbps,
        "CPU_CAST_COST": cast.get("cast_ms") if cast.get("supported") else None,
        "BUCKETING_RESULT": bucketing,
    }


def _print_result(result: Mapping[str, Any]) -> None:
    print(f"mode={result.get('mode', 'unknown')} status={result.get('status', 'UNKNOWN')}")
    config = result.get("config", {})
    print(
        "config="
        f"producers:{config.get('producers')} "
        f"bucket:{config.get('bucket_bytes')}B "
        f"pool:{config.get('pool_bytes')}B streams:{config.get('streams', 1)}"
    )
    for key in (
        "pageable_h2d",
        "preallocated_pinned_h2d",
        "pinned_many_small_h2d",
        "pinned_bucketed_h2d",
        "staged_same_dtype_many_small",
        "staged_same_dtype_bucketed",
        "fp32_cast_then_h2d",
    ):
        value = result.get(key)
        if not isinstance(value, Mapping):
            continue
        print(
            f"{key}: wall_ms={_format_number(value.get('wall_ms'))} "
            f"cuda_ms={_format_number(value.get('cuda_ms'))} "
            f"gbps={_format_number(value.get('gbps'))} "
            f"total_ms={_format_number(value.get('total_ms'))} "
            f"stage_ms={_format_number(value.get('stage_ms'))} "
            f"copies={value.get('copy_count', 'UNAVAILABLE')}"
        )
    allocation = result.get("pool_allocation")
    if isinstance(allocation, Mapping):
        print(f"pool_allocation_ms={_format_number(allocation.get('median_ms'))}")
    print(f"LOCAL_PINNED_FAST_PATH_CONFIRMED={result.get('LOCAL_PINNED_FAST_PATH_CONFIRMED', 'UNAVAILABLE')}")
    print(f"PINNED_GBPS={_format_number(result.get('PINNED_GBPS'))}")
    print(f"PAGEABLE_GBPS={_format_number(result.get('PAGEABLE_GBPS'))}")
    cast_cost = result.get("CPU_CAST_COST")
    print(f"CPU_CAST_COST={_format_number(cast_cost)} ms")
    print(f"BUCKETING_RESULT={result.get('BUCKETING_RESULT', 'UNAVAILABLE')}")
    print("MODAL_DEPLOYS=0")
    print("MODAL_REQUESTS=0")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("auto", "synthetic", "e1"), default="auto")
    parser.add_argument("--e1-module", help="E1 provider module, optionally module:factory")
    parser.add_argument("--producers", type=int, default=DEFAULT_PRODUCERS)
    parser.add_argument("--bucket-bytes", type=_parse_bytes, default=DEFAULT_BUCKET_BYTES)
    parser.add_argument("--pool-bytes", type=_parse_bytes, default=DEFAULT_POOL_BYTES)
    parser.add_argument("--small-copy-bytes", type=_parse_bytes, default=DEFAULT_SMALL_COPY_BYTES)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--pool-allocation-samples", type=int, default=DEFAULT_POOL_ALLOCATION_SAMPLES)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.producers <= 0 or args.repeats <= 0 or args.warmup < 0 or args.pool_allocation_samples <= 0:
        raise SystemExit("producers, repeats, and pool-allocation-samples must be positive; warmup must be non-negative")
    config = BenchmarkConfig(
        producers=args.producers,
        bucket_bytes=args.bucket_bytes,
        pool_bytes=args.pool_bytes,
        small_copy_bytes=args.small_copy_bytes,
        repeats=args.repeats,
        warmup=args.warmup,
        pool_allocation_samples=args.pool_allocation_samples,
        device=args.device,
    )

    result: dict[str, Any]
    if args.mode in ("auto", "e1") and args.e1_module:
        try:
            result = _run_e1_provider(_load_e1_provider(args.e1_module, config), config)
        except Exception as exc:
            if args.mode == "e1":
                print(f"E1 provider failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                return 2
            print(f"E1 provider unavailable; using synthetic mode: {type(exc).__name__}: {exc}", file=sys.stderr)
            result = SyntheticPinnedBufferBenchmark(config).run()
    elif args.mode == "e1":
        print("--mode e1 requires --e1-module", file=sys.stderr)
        return 2
    else:
        result = SyntheticPinnedBufferBenchmark(config).run()

    if "LOCAL_PINNED_FAST_PATH_CONFIRMED" not in result:
        result.update(_decision_fields(result))
    _print_result(result)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result.get("status") in ("OK", None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
