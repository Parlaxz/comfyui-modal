#!/usr/bin/env python3
"""Phase 1 C0 arena microbenchmark.

This is intentionally a stand-alone benchmark.  It does not import the
ComfyUI application or any comfy-modal production module.  The measured
operation is only a native ``libc.memcpy`` call; allocation, source
initialisation, process startup, SharedMemory attach, and barrier waits are
outside that call's timer.

The destination is private for ``*_private`` arms and is a per-worker slice of
one POSIX ``multiprocessing.shared_memory.SharedMemory`` object for ``*_shared``
arms.  Sources are always worker-private, deterministic, and touched during
setup so that the benchmark does not accidentally measure source page faults
from lazy allocation.

Examples (the full campaign is intentionally large)::

    python tools/phase1_c0_arena.py --help
    python tools/phase1_c0_arena.py --dry-run --size-mib 1 --copies 2 \
        --warmups 1 --samples 1 --output-dir .tmp/c0
    python tools/phase1_c0_arena.py --extend-to-50 --output-dir artifacts/c0

If the Modal SDK is installed, ``modal_benchmark`` is also exposed as an
H100 function.  This file never deploys or invokes it itself.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import csv
import json
import math
import multiprocessing as mp
import os
import platform
import queue
import random
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from typing import Any, Iterable


ARM_LABELS = {
    "thread_private": "THREAD->PRIVATE",
    "thread_shared": "THREAD->SHARED",
    "process_private": "PROCESS->PRIVATE",
    "process_shared": "PROCESS->SHARED",
    "fresh_process_mapping_shared": "FRESH PROCESS/MAPPING->SHARED",
}
ARM_CHOICES = tuple(ARM_LABELS)
DEFAULT_ARMS = list(ARM_CHOICES)
BASELINE_ARM = "thread_private"


def _now_ns() -> int:
    return time.perf_counter_ns()


def _rss_bytes() -> int | None:
    """Return current resident bytes where the host exposes a cheap answer."""
    try:
        if sys.platform.startswith("linux"):
            fields = Path("/proc/self/statm").read_text(encoding="ascii").split()
            return int(fields[1]) * int(getattr(os, "sysconf")("SC_PAGESIZE"))
        if sys.platform == "darwin":
            # resource.ru_maxrss is bytes on macOS, KiB on Linux/BSD.
            import resource

            return int(getattr(resource, "getrusage")(getattr(resource, "RUSAGE_SELF")).ru_maxrss)
    except Exception:
        pass
    try:
        import resource

        value = int(getattr(resource, "getrusage")(getattr(resource, "RUSAGE_SELF")).ru_maxrss)
        return value * 1024 if not sys.platform == "darwin" else value
    except Exception:
        return None


def _rusage() -> dict[str, int | None]:
    try:
        import resource

        usage = getattr(resource, "getrusage")(getattr(resource, "RUSAGE_SELF"))
        return {
            "minor_faults": int(getattr(usage, "ru_minflt", 0)),
            "major_faults": int(getattr(usage, "ru_majflt", 0)),
            "max_rss_bytes": _maxrss_bytes(getattr(usage, "ru_maxrss", None)),
        }
    except Exception:
        return {"minor_faults": None, "major_faults": None, "max_rss_bytes": None}


def _maxrss_bytes(value: Any) -> int | None:
    if value is None:
        return None
    try:
        value = int(value)
        return value if sys.platform == "darwin" else value * 1024
    except Exception:
        return None


def _mapping_evidence(token: str | None) -> dict[str, Any]:
    """Collect bounded mapping evidence without making it a required platform."""
    maps = Path("/proc/self/maps")
    if not maps.is_file():
        return {"available": False, "total_mappings": None, "token_matches": None, "sample": []}
    try:
        lines = maps.read_text(encoding="utf-8", errors="replace").splitlines()
        matches = [line for line in lines if token and token in line]
        return {
            "available": True,
            "total_mappings": len(lines),
            "token_matches": len(matches),
            "sample": matches[:3],
        }
    except Exception as exc:
        return {"available": False, "error": repr(exc), "total_mappings": None, "token_matches": None, "sample": []}


def _delta(after: Any, before: Any) -> int | None:
    if after is None or before is None:
        return None
    return max(0, int(after) - int(before))


class NativeMemcpy:
    """The only copy implementation used by the arena."""

    def __init__(self) -> None:
        candidates = []
        if os.name == "nt":
            candidates.extend(["msvcrt.dll"])
        else:
            candidates.extend([ctypes.util.find_library("c"), None, "libc.so.6", "libSystem.B.dylib"])
        self.library_name = None
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                lib = ctypes.CDLL(candidate) if candidate else ctypes.CDLL(None)
                fn = lib.memcpy
                fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
                fn.restype = ctypes.c_void_p
                memset = lib.memset
                memset.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
                memset.restype = ctypes.c_void_p
                self._lib = lib
                self._memcpy = fn
                self._memset = memset
                self.library_name = candidate or "process-default-libc"
                break
            except Exception as exc:  # pragma: no cover - platform-dependent candidates
                last_error = exc
        if self.library_name is None:
            raise RuntimeError(f"native libc memcpy is unavailable: {last_error}")

    def memset(self, address: int, value: int, size: int) -> None:
        self._memset(ctypes.c_void_p(address), value, size)

    def memcpy(self, destination: int, source: int, size: int) -> None:
        self._memcpy(ctypes.c_void_p(destination), ctypes.c_void_p(source), size)


def _source_pattern(worker_id: int) -> int:
    return (0x31 + worker_id * 0x47) & 0xFF


def _private_source(copy_impl: NativeMemcpy, worker_id: int, size: int) -> ctypes.Array[Any]:
    source = ctypes.create_string_buffer(size)
    copy_impl.memset(ctypes.addressof(source), _source_pattern(worker_id), size)
    return source


def _shared_slice(shm: SharedMemory, offset: int, size: int) -> tuple[Any, int]:
    view_type = ctypes.c_ubyte * size
    buffer = shm.buf
    assert buffer is not None
    view = view_type.from_buffer(buffer, offset)
    return view, ctypes.addressof(view)


def _telemetry_before(token: str | None) -> tuple[dict[str, Any], int | None, dict[str, Any]]:
    return _rusage(), _rss_bytes(), _mapping_evidence(token)


def _telemetry_after(token: str | None) -> tuple[dict[str, Any], int | None, dict[str, Any]]:
    return _rusage(), _rss_bytes(), _mapping_evidence(token)


def _copy_record(
    *,
    arm: str,
    workers: int,
    worker_id: int,
    sample_index: int,
    copy_index: int,
    destination: int,
    source: int,
    size: int,
    copy_impl: NativeMemcpy,
    mapping_token: str | None,
    pid: int,
    rusage_scope: str,
) -> dict[str, Any]:
    before_usage, before_rss, before_maps = _telemetry_before(mapping_token)
    started = _now_ns()
    copy_impl.memcpy(destination, source, size)
    ended = _now_ns()
    after_usage, after_rss, after_maps = _telemetry_after(mapping_token)
    expected = _source_pattern(worker_id)
    # Reading two bytes is outside the memcpy timer and catches invalid slices
    # without adding a checksum-sized second memory pass to every operation.
    first = ctypes.c_ubyte.from_address(destination).value
    last = ctypes.c_ubyte.from_address(destination + size - 1).value
    duration_ns = ended - started
    return {
        "arm": arm,
        "arm_label": ARM_LABELS[arm],
        "workers": workers,
        "worker_id": worker_id,
        "sample_index": sample_index,
        "copy_index": copy_index,
        "phase": "first" if copy_index == 0 else "steady",
        "pid": pid,
        "bytes": size,
        "duration_ns": duration_ns,
        "duration_ms": duration_ns / 1_000_000.0,
        "throughput_gib_s": size / (duration_ns / 1_000_000_000.0) / (1024**3),
        "native_copy": "ctypes libc.memcpy",
        "libc": copy_impl.library_name,
        "setup_excluded": True,
        "startup_excluded": True,
        "attach_excluded": True,
        "barrier_wait_excluded": True,
        "rusage_scope": rusage_scope,
        "minor_faults_delta": _delta(after_usage["minor_faults"], before_usage["minor_faults"]),
        "major_faults_delta": _delta(after_usage["major_faults"], before_usage["major_faults"]),
        "max_rss_before_bytes": before_usage["max_rss_bytes"],
        "max_rss_after_bytes": after_usage["max_rss_bytes"],
        "rss_before_bytes": before_rss,
        "rss_after_bytes": after_rss,
        "mapping_before": before_maps,
        "mapping_after": after_maps,
        "mapping_token": mapping_token,
        "verified": first == expected and last == expected,
        "expected_byte": expected,
        "first_byte": first,
        "last_byte": last,
        "status": "ok" if first == expected and last == expected else "verification_failed",
    }


def _barrier_wait(barrier: Any, timeout: float) -> None:
    barrier.wait(timeout=timeout)


def _persistent_process_worker(
    arm: str,
    worker_id: int,
    workers: int,
    size: int,
    copies_total: int,
    shared: bool,
    shm_name: str | None,
    barrier: Any,
    results: Any,
    barrier_timeout: float,
) -> None:
    shm = None
    destination_view = None
    try:
        copy_impl = NativeMemcpy()
        source = _private_source(copy_impl, worker_id, size)
        if shared:
            assert shm_name is not None
            shm = SharedMemory(name=shm_name)
            destination_view, destination = _shared_slice(shm, worker_id * size, size)
            mapping_token = shm.name
        else:
            destination_buffer = ctypes.create_string_buffer(size)
            destination = ctypes.addressof(destination_buffer)
            mapping_token = None
        _barrier_wait(barrier, barrier_timeout)  # setup/startup/attach boundary
        for absolute_copy in range(copies_total):
            _barrier_wait(barrier, barrier_timeout)
            record = _copy_record(
                arm=arm,
                workers=workers,
                worker_id=worker_id,
                sample_index=0,
                copy_index=absolute_copy,
                destination=destination,
                source=ctypes.addressof(source),
                size=size,
                copy_impl=copy_impl,
                mapping_token=mapping_token,
                pid=os.getpid(),
                rusage_scope="child_process",
            )
            results.put(record)
    except BaseException as exc:
        try:
            results.put({"status": "error", "worker_id": worker_id, "error": repr(exc)})
        finally:
            try:
                barrier.abort()
            except Exception:
                pass
    finally:
        destination_view = None
        if shm is not None:
            shm.close()


def _fresh_process_worker(
    worker_id: int,
    workers: int,
    size: int,
    shm_name: str,
    barrier: Any,
    results: Any,
    barrier_timeout: float,
    sample_index: int,
    copy_index: int,
) -> None:
    shm = None
    destination_view = None
    try:
        copy_impl = NativeMemcpy()
        source = _private_source(copy_impl, worker_id, size)
        shm = SharedMemory(name=shm_name)
        destination_view, destination = _shared_slice(shm, worker_id * size, size)
        mapping_token = shm.name
        _barrier_wait(barrier, barrier_timeout)  # process startup and attach excluded
        record = _copy_record(
            arm="fresh_process_mapping_shared",
            workers=workers,
            worker_id=worker_id,
            sample_index=sample_index,
            copy_index=copy_index,
            destination=destination,
            source=ctypes.addressof(source),
            size=size,
            copy_impl=copy_impl,
            mapping_token=mapping_token,
            pid=os.getpid(),
            rusage_scope="child_process",
        )
        results.put(record)
    except BaseException as exc:
        try:
            results.put({"status": "error", "worker_id": worker_id, "error": repr(exc)})
        finally:
            try:
                barrier.abort()
            except Exception:
                pass
    finally:
        destination_view = None
        if shm is not None:
            shm.close()


class PersistentProcessRunner:
    def __init__(self, arm: str, workers: int, size: int, copies_total: int, start_method: str, barrier_timeout: float) -> None:
        self.arm = arm
        self.workers = workers
        self.size = size
        self.copies_total = copies_total
        self.barrier_timeout = barrier_timeout
        self.ctx: Any = mp.get_context(start_method)
        self.shared = arm == "process_shared"
        self.shm = SharedMemory(create=True, size=size * workers) if self.shared else None
        self.barrier = self.ctx.Barrier(workers + 1)
        self.results = self.ctx.Queue()
        self.processes: list[Any] = []
        started = _now_ns()
        for worker_id in range(workers):
            process = self.ctx.Process(
                target=_persistent_process_worker,
                args=(arm, worker_id, workers, size, copies_total, self.shared, self.shm.name if self.shm else None, self.barrier, self.results, barrier_timeout),
            )
            process.start()
            self.processes.append(process)
        try:
            _barrier_wait(self.barrier, barrier_timeout)
        except Exception:
            self.close()
            raise
        self.setup_ms = (_now_ns() - started) / 1_000_000.0
        self._absolute_copy = 0

    def _collect(self) -> list[dict[str, Any]]:
        records = []
        for _ in range(self.workers):
            try:
                record = self.results.get(timeout=self.barrier_timeout)
            except queue.Empty as exc:
                raise RuntimeError("persistent process worker did not report") from exc
            if record.get("status") == "error":
                raise RuntimeError(record.get("error", "persistent process worker failed"))
            record["arm"] = self.arm
            record["arm_label"] = ARM_LABELS[self.arm]
            records.append(record)
        return sorted(records, key=lambda row: row["worker_id"])

    def run_sample(self, sample_index: int, copies: int, record: bool) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        all_records: list[dict[str, Any]] = []
        for copy_index in range(copies):
            _barrier_wait(self.barrier, self.barrier_timeout)
            records = self._collect()
            for row in records:
                row["sample_index"] = sample_index
                row["copy_index"] = copy_index
                row["phase"] = "first" if copy_index == 0 else "steady"
            all_records.extend(records)
            self._absolute_copy += 1
        return (_aggregate_sample(self.arm, self.workers, sample_index, copies, self.size, all_records, self.setup_ms) if record else None, all_records if record else [])

    def close(self) -> None:
        for process in self.processes:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        if self.shm is not None:
            self.shm.close()
            try:
                self.shm.unlink()
            except FileNotFoundError:
                pass
        try:
            self.results.close()
        except Exception:
            pass


def _persistent_thread_worker(
    arm: str,
    worker_id: int,
    workers: int,
    size: int,
    copies_total: int,
    shared: bool,
    shm: SharedMemory | None,
    barrier: threading.Barrier,
    results: queue.Queue[dict[str, Any]],
    barrier_timeout: float,
) -> None:
    destination_view = None
    try:
        copy_impl = NativeMemcpy()
        source = _private_source(copy_impl, worker_id, size)
        if shared:
            assert shm is not None
            destination_view, destination = _shared_slice(shm, worker_id * size, size)
            mapping_token = shm.name
        else:
            destination_buffer = ctypes.create_string_buffer(size)
            destination = ctypes.addressof(destination_buffer)
            mapping_token = None
        _barrier_wait(barrier, barrier_timeout)
        for absolute_copy in range(copies_total):
            _barrier_wait(barrier, barrier_timeout)
            record = _copy_record(
                arm=arm,
                workers=workers,
                worker_id=worker_id,
                sample_index=0,
                copy_index=absolute_copy,
                destination=destination,
                source=ctypes.addressof(source),
                size=size,
                copy_impl=copy_impl,
                mapping_token=mapping_token,
                pid=os.getpid(),
                rusage_scope="process_shared_threads" if shared else "process_threads",
            )
            results.put(record)
    except BaseException as exc:
        try:
            results.put({"status": "error", "worker_id": worker_id, "error": repr(exc)})
        finally:
            try:
                barrier.abort()
            except Exception:
                pass
    finally:
        destination_view = None


class PersistentThreadRunner:
    def __init__(self, arm: str, workers: int, size: int, copies_total: int, barrier_timeout: float) -> None:
        self.arm = arm
        self.workers = workers
        self.size = size
        self.copies_total = copies_total
        self.barrier_timeout = barrier_timeout
        self.shared = arm == "thread_shared"
        self.shm = SharedMemory(create=True, size=size * workers) if self.shared else None
        self.barrier = threading.Barrier(workers + 1)
        self.results: queue.Queue[dict[str, Any]] = queue.Queue()
        self.threads: list[threading.Thread] = []
        started = _now_ns()
        for worker_id in range(workers):
            thread = threading.Thread(
                target=_persistent_thread_worker,
                args=(arm, worker_id, workers, size, copies_total, self.shared, self.shm, self.barrier, self.results, barrier_timeout),
                name=f"c0-thread-{worker_id}",
            )
            thread.start()
            self.threads.append(thread)
        _barrier_wait(self.barrier, barrier_timeout)
        self.setup_ms = (_now_ns() - started) / 1_000_000.0

    def _collect(self) -> list[dict[str, Any]]:
        records = []
        for _ in range(self.workers):
            record = self.results.get(timeout=self.barrier_timeout)
            if record.get("status") == "error":
                raise RuntimeError(record.get("error", "thread worker failed"))
            record["arm"] = self.arm
            record["arm_label"] = ARM_LABELS[self.arm]
            records.append(record)
        return sorted(records, key=lambda row: row["worker_id"])

    def run_sample(self, sample_index: int, copies: int, record: bool) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        all_records: list[dict[str, Any]] = []
        for copy_index in range(copies):
            _barrier_wait(self.barrier, self.barrier_timeout)
            records = self._collect()
            for row in records:
                row["sample_index"] = sample_index
                row["copy_index"] = copy_index
                row["phase"] = "first" if copy_index == 0 else "steady"
            all_records.extend(records)
        return (_aggregate_sample(self.arm, self.workers, sample_index, copies, self.size, all_records, self.setup_ms) if record else None, all_records if record else [])

    def close(self) -> None:
        for thread in self.threads:
            thread.join(timeout=2)
        if self.shm is not None:
            self.shm.close()
            try:
                self.shm.unlink()
            except FileNotFoundError:
                pass


class FreshProcessRunner:
    def __init__(self, workers: int, size: int, start_method: str, barrier_timeout: float) -> None:
        self.workers = workers
        self.size = size
        self.ctx: Any = mp.get_context(start_method)
        self.barrier_timeout = barrier_timeout
        self.shm = SharedMemory(create=True, size=size * workers)

    def run_sample(self, arm: str, sample_index: int, copies: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        all_records: list[dict[str, Any]] = []
        setup_total_ns = 0
        for copy_index in range(copies):
            started = _now_ns()
            barrier = self.ctx.Barrier(self.workers + 1)
            results = self.ctx.Queue()
            processes = [
                self.ctx.Process(
                    target=_fresh_process_worker,
                    args=(worker_id, self.workers, self.size, self.shm.name, barrier, results, self.barrier_timeout, sample_index, copy_index),
                )
                for worker_id in range(self.workers)
            ]
            for process in processes:
                process.start()
            _barrier_wait(barrier, self.barrier_timeout)
            setup_total_ns += _now_ns() - started
            records = []
            for _ in range(self.workers):
                try:
                    record = results.get(timeout=self.barrier_timeout)
                except queue.Empty as exc:
                    raise RuntimeError("fresh process worker did not report") from exc
                if record.get("status") == "error":
                    raise RuntimeError(record.get("error", "fresh process worker failed"))
                records.append(record)
            for process in processes:
                process.join(timeout=self.barrier_timeout)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
            results.close()
            all_records.extend(sorted(records, key=lambda row: row["worker_id"]))
        sample = _aggregate_sample(arm, self.workers, sample_index, copies, self.size, all_records, setup_total_ns / 1_000_000.0)
        return sample, all_records

    def close(self) -> None:
        self.shm.close()
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass


def _aggregate_sample(arm: str, workers: int, sample_index: int, copies: int, size: int, records: list[dict[str, Any]], setup_ms: float) -> dict[str, Any]:
    by_copy: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        by_copy.setdefault(int(record["copy_index"]), []).append(record)
    copy_walls = [max(float(row["duration_ms"]) for row in by_copy[index]) for index in range(copies)]
    steady_walls = copy_walls[1:]
    steady_total_ms = sum(steady_walls)
    total_bytes = size * workers * copies
    steady_bytes = size * workers * max(0, copies - 1)
    return {
        "arm": arm,
        "arm_label": ARM_LABELS[arm],
        "workers": workers,
        "sample_index": sample_index,
        "copies_per_worker": copies,
        "bytes_per_copy": size,
        "total_bytes": total_bytes,
        "first_copy_ms": copy_walls[0],
        "steady_copy_ms": steady_walls,
        "steady_total_ms": steady_total_ms,
        "sample_copy_wall_ms": sum(copy_walls),
        "aggregate_gib_s": (steady_bytes / (steady_total_ms / 1000.0) / (1024**3)) if steady_total_ms else None,
        "max_operation_ms": max(copy_walls),
        "verified": all(bool(row.get("verified")) for row in records),
        "operation_count": len(records),
        "setup_excluded_ms": setup_ms,
        "startup_excluded": True,
        "attach_excluded": True,
        "barrier_wait_excluded": True,
    }


def _make_runner(arm: str, workers: int, size: int, copies_total: int, start_method: str, barrier_timeout: float) -> Any:
    if arm in ("thread_private", "thread_shared"):
        return PersistentThreadRunner(arm, workers, size, copies_total, barrier_timeout)
    if arm in ("process_private", "process_shared"):
        return PersistentProcessRunner(arm, workers, size, copies_total, start_method, barrier_timeout)
    return FreshProcessRunner(workers, size, start_method, barrier_timeout)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _stats(values: list[float], percentiles: Iterable[float], stall_ms: float, stall_ratio: float) -> dict[str, Any]:
    if not values:
        return {"n": 0, "min": None, "max": None, "mean": None, "median": None, "stdev": None, "percentiles": {}, "stall_count_absolute": 0, "stall_count_ratio": 0, "stall_threshold_ms": stall_ms, "stall_ratio_threshold": stall_ratio}
    median = statistics.median(values)
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": median,
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "percentiles": {f"p{p:g}": _percentile(values, p) for p in percentiles},
        "stall_count_absolute": sum(value > stall_ms for value in values),
        "stall_count_ratio": sum(value > median * stall_ratio for value in values),
        "stall_threshold_ms": stall_ms,
        "stall_ratio_threshold": stall_ratio,
    }


def _bootstrap_mean_ci(values: list[float], seed: int, iterations: int = 2000) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "ci95_low": None, "ci95_high": None, "iterations": 0}
    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        means.append(statistics.mean(values[rng.randrange(len(values))] for _ in values))
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "ci95_low": _percentile(means, 2.5),
        "ci95_high": _percentile(means, 97.5),
        "iterations": iterations,
    }


def _build_schedule(arms: list[str], workers: list[int], samples: int, seed: int) -> list[tuple[int, str, int]]:
    cells = [(sample_index, arm, worker_count) for sample_index in range(samples) for worker_count in workers for arm in arms]
    random.Random(seed).shuffle(cells)
    return cells


def _host_metadata(copy_impl: NativeMemcpy) -> dict[str, Any]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pid": os.getpid(),
        "cpu_count": os.cpu_count(),
        "native_copy": "ctypes libc.memcpy",
        "libc": copy_impl.library_name,
        "shared_memory": "multiprocessing.shared_memory.SharedMemory",
        "mapping_evidence": str(Path("/proc/self/maps")) if Path("/proc/self/maps").is_file() else None,
    }


def _write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flattened = {key: json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value for key, value in row.items()}
            writer.writerow(flattened)


def _write_outputs(output_dir: Path, manifest: dict[str, Any], samples: list[dict[str, Any]], operations: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "per_sample.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")
    (output_dir / "per_operation.json").write_text(json.dumps(operations, indent=2), encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_table(output_dir / "per_sample.csv", samples)
    _write_table(output_dir / "per_operation.csv", operations)


def _build_summary(samples: list[dict[str, Any]], percentiles: list[float], stall_ms: float, stall_ratio: float, bootstrap_seed: int) -> dict[str, Any]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for sample in samples:
        grouped.setdefault((sample["arm"], int(sample["workers"])), []).append(sample)
    arms_summary: dict[str, Any] = {}
    for (arm, workers), rows in sorted(grouped.items()):
        arms_summary[f"{arm}/{workers}"] = {
            "arm": arm,
            "arm_label": ARM_LABELS[arm],
            "workers": workers,
            "first_copy_ms": _stats([float(row["first_copy_ms"]) for row in rows], percentiles, stall_ms, stall_ratio),
            "steady_total_ms": _stats([float(row["steady_total_ms"]) for row in rows], percentiles, stall_ms, stall_ratio),
            "max_operation_ms": _stats([float(row["max_operation_ms"]) for row in rows], percentiles, stall_ms, stall_ratio),
            "aggregate_gib_s": _stats([float(row["aggregate_gib_s"]) for row in rows if row["aggregate_gib_s"] is not None], percentiles, stall_ms, stall_ratio),
            "verification_failures": sum(not row["verified"] for row in rows),
        }

    paired: dict[str, Any] = {}
    baseline_groups = {(int(row["workers"]), int(row["sample_index"])): row for row in samples if row["arm"] == BASELINE_ARM}
    for (arm, workers), rows in sorted(grouped.items()):
        if arm == BASELINE_ARM:
            continue
        differences = []
        ratios = []
        for row in rows:
            baseline = baseline_groups.get((workers, int(row["sample_index"])))
            if baseline is None:
                continue
            target = float(row["steady_total_ms"])
            base = float(baseline["steady_total_ms"])
            differences.append(target - base)
            ratios.append((target / base - 1.0) * 100.0 if base else None)
        ratios = [value for value in ratios if value is not None]
        key = f"{arm}/{workers}-vs-{BASELINE_ARM}/{workers}"
        paired[key] = {
            "metric": "steady_total_ms",
            "target_arm": arm,
            "baseline_arm": BASELINE_ARM,
            "workers": workers,
            "difference_ms": _bootstrap_mean_ci(differences, bootstrap_seed + workers + len(paired)),
            "relative_percent": _bootstrap_mean_ci(ratios, bootstrap_seed + 1000 + workers + len(paired)),
        }
    return {
        "sample_count": len(samples),
        "operation_count": None,
        "percentiles_requested": percentiles,
        "stall_thresholds": {"absolute_ms": stall_ms, "ratio_to_group_median": stall_ratio},
        "arms": arms_summary,
        "paired_differences": paired,
    }


@dataclass(frozen=True)
class BenchmarkConfig:
    size: int
    copies: int
    warmups: int
    samples: int
    arms: list[str]
    workers: list[int]
    seed: int
    start_method: str
    barrier_timeout: float
    percentiles: list[float]
    stall_ms: float
    stall_ratio: float


def run_benchmark(config: BenchmarkConfig, output_dir: Path | None = None) -> dict[str, Any]:
    copy_impl = NativeMemcpy()
    schedule = _build_schedule(config.arms, config.workers, config.samples, config.seed)
    samples: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    started = datetime.now(timezone.utc).isoformat()
    for schedule_index, (sample_index, arm, workers) in enumerate(schedule):
        # A separate runner per valid sample makes the order genuinely
        # interleaved while keeping persistent process/thread arms persistent
        # across all eight copies in that sample.  Warmups are setup warmups;
        # none of their operation rows enter the result tables.
        if arm == "fresh_process_mapping_shared":
            runner = FreshProcessRunner(workers, config.size, config.start_method, config.barrier_timeout)
            try:
                for _ in range(config.warmups):
                    runner.run_sample(arm, -1, config.copies)
                sample, rows = runner.run_sample(arm, sample_index, config.copies)
            finally:
                runner.close()
        else:
            runner = _make_runner(arm, workers, config.size, (config.warmups + 1) * config.copies, config.start_method, config.barrier_timeout)
            try:
                for warmup_index in range(config.warmups):
                    runner.run_sample(-1, config.copies, False)
                sample, rows = runner.run_sample(sample_index, config.copies, True)
            finally:
                runner.close()
        assert sample is not None
        sample["schedule_index"] = schedule_index
        sample["ordering"] = "balanced_interleaved"
        samples.append(sample)
        for row in rows:
            row["schedule_index"] = schedule_index
            row["ordering"] = "balanced_interleaved"
        operations.extend(rows)
        print(f"[{schedule_index + 1}/{len(schedule)}] {ARM_LABELS[arm]} workers={workers} sample={sample_index} steady={sample['steady_total_ms']:.3f} ms", flush=True)

    summary = _build_summary(samples, config.percentiles, config.stall_ms, config.stall_ratio, config.seed)
    summary["operation_count"] = len(operations)
    manifest = {
        "benchmark": "phase1_c0_arena",
        "phase": "Phase 1 C0",
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "size_bytes": config.size,
            "size_mib": config.size / (1024 * 1024),
            "copies_per_worker": config.copies,
            "warmups": config.warmups,
            "valid_samples": config.samples,
            "arms": config.arms,
            "workers": config.workers,
            "seed": config.seed,
            "start_method": config.start_method,
            "barrier_timeout_s": config.barrier_timeout,
        },
        "measurement_contract": {
            "copy": "native libc memcpy through ctypes",
            "sources": "deterministic resident private per-worker source",
            "first_copy_separate": True,
            "setup_startup_attach_excluded": True,
            "barriers": "parent/worker barrier before every timed memcpy",
            "shared_memory": "POSIX multiprocessing SharedMemory where supported",
        },
        "host": _host_metadata(copy_impl),
        "files": ["manifest.json", "per_sample.json", "per_sample.csv", "per_operation.json", "per_operation.csv", "summary.json"],
    }
    if output_dir is not None:
        _write_outputs(output_dir, manifest, samples, operations, summary)
    return {"manifest": manifest, "summary": summary, "samples": samples, "operations": operations}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--size-mib", type=float, default=128.0, help="bytes copied per worker per operation (default: 128)")
    parser.add_argument("--copies", type=int, default=8, help="copies per worker per sample (default: 8; copy 0 is reported separately)")
    parser.add_argument("--warmups", "--setup-warmups", dest="warmups", type=int, default=5, help="setup warmup samples excluded from output (default: 5)")
    parser.add_argument("--samples", "--valid-samples", dest="samples", type=int, default=30, help="valid samples (default: 30; maximum: 50)")
    parser.add_argument("--extend-to-50", action="store_true", help="set valid samples to 50")
    parser.add_argument("--arms", nargs="+", choices=ARM_CHOICES, default=DEFAULT_ARMS, help="arena arms (default: all five)")
    parser.add_argument("--workers", nargs="+", type=int, choices=(1, 4), default=[1, 4], help="worker counts (default: 1 4)")
    parser.add_argument("--seed", type=int, default=20260928, help="deterministic interleaving/bootstrap seed")
    parser.add_argument("--start-method", choices=("auto", "fork", "spawn"), default="auto", help="multiprocessing start method")
    parser.add_argument("--barrier-timeout", type=float, default=120.0, help="worker barrier/report timeout in seconds")
    parser.add_argument("--percentiles", nargs="+", type=float, default=[50.0, 90.0, 95.0, 99.0], help="summary percentiles")
    parser.add_argument("--stall-threshold-ms", type=float, default=100.0, help="absolute sample stall threshold")
    parser.add_argument("--stall-ratio", type=float, default=2.0, help="stall threshold as a multiple of group median")
    parser.add_argument("--output-dir", type=Path, default=None, help="write JSON/CSV artifacts here")
    parser.add_argument("--dry-run", action="store_true", help="bounded execution: one valid sample and one warmup unless explicitly smaller")
    args = parser.parse_args(argv)
    if args.extend_to_50:
        args.samples = 50
    if args.dry_run:
        args.samples = min(args.samples, 1)
        args.warmups = min(args.warmups, 1)
    if not 1 <= args.samples <= 50:
        parser.error("--samples must be between 1 and 50")
    if args.warmups < 0 or args.copies < 1 or args.size_mib <= 0:
        parser.error("--size-mib and --copies must be positive; --warmups cannot be negative")
    if any(percentile < 0 or percentile > 100 for percentile in args.percentiles):
        parser.error("percentiles must be in [0, 100]")
    if args.stall_threshold_ms <= 0 or args.stall_ratio <= 0 or args.barrier_timeout <= 0:
        parser.error("stall thresholds and barrier timeout must be positive")
    if args.start_method == "auto":
        args.start_method = "fork" if "fork" in mp.get_all_start_methods() else mp.get_start_method()
    return args


def _config_from_args(args: argparse.Namespace) -> BenchmarkConfig:
    size = int(args.size_mib * 1024 * 1024)
    if size < 1:
        raise ValueError("size rounds below one byte")
    return BenchmarkConfig(
        size=size,
        copies=args.copies,
        warmups=args.warmups,
        samples=args.samples,
        arms=list(args.arms),
        workers=list(dict.fromkeys(args.workers)),
        seed=args.seed,
        start_method=args.start_method,
        barrier_timeout=args.barrier_timeout,
        percentiles=list(args.percentiles),
        stall_ms=args.stall_threshold_ms,
        stall_ratio=args.stall_ratio,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config = _config_from_args(args)
    output_dir = args.output_dir
    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = Path("artifacts") / "phase1_c0_arena" / stamp
    result = run_benchmark(config, output_dir)
    print(json.dumps({"output_dir": str(output_dir), "summary": result["summary"]}, indent=2), flush=True)
    return 0


# Optional Modal surface.  Importing this benchmark locally does not require
# the Modal SDK; on a Modal host this is a normal H100 function and remains
# explicitly opt-in (``modal run tools/phase1_c0_arena.py``).
try:  # pragma: no cover - depends on optional Modal SDK
    import modal as _modal
except Exception:  # pragma: no cover - normal local environment
    _modal = None

if _modal is not None:  # pragma: no cover - exercised only by Modal
    app = _modal.App("phase1-c0-arena")
    image = _modal.Image.debian_slim(python_version="3.11")

    @app.function(image=image, gpu="H100", timeout=7200)
    def modal_benchmark(
        size_mib: float = 128.0,
        copies: int = 8,
        warmups: int = 5,
        samples: int = 30,
        seed: int = 20260928,
        arms: str = "",
    ) -> str:
        config = BenchmarkConfig(
            size=int(size_mib * 1024 * 1024),
            copies=copies,
            warmups=warmups,
            samples=samples,
            arms=[item for item in (arms.split(",") if arms else DEFAULT_ARMS) if item in ARM_CHOICES],
            workers=[1, 4],
            seed=seed,
            start_method="fork" if "fork" in mp.get_all_start_methods() else mp.get_start_method(),
            barrier_timeout=120.0,
            percentiles=[50.0, 90.0, 95.0, 99.0],
            stall_ms=100.0,
            stall_ratio=2.0,
        )
        return json.dumps(
            run_benchmark(config, Path("/tmp/phase1_c0_arena")),
            separators=(",", ":"),
        )
else:
    app = None


if __name__ == "__main__":
    raise SystemExit(main())
