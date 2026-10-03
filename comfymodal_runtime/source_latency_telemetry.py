"""Compact, diagnostic-only source latency and placement telemetry."""

from __future__ import annotations

import ctypes
import importlib
import os
import re
from collections import defaultdict
from typing import Any, Mapping, Sequence, cast

from .statistics import percentile


_PLACEMENT_CACHE: dict[str, Any] | None = None
PROC_ROOT = "/proc"
SYSFS_ROOT = "/sys"
# A real PCI address looks like ``0000:41:00.0``.  Anything else from a
# realpath is a directory name, not evidence of a bus id.
_PCI_ADDRESS = re.compile(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.\d+")


def _integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    return None


def _milliseconds(value: Any) -> float | None:
    integer = _integer(value)
    return integer / 1e6 if integer is not None else None


def _duration_ms(record: Mapping[str, Any]) -> float | None:
    start = _integer(record.get("memcpy_start_ns"))
    end = _integer(record.get("memcpy_end_ns"))
    if start is None or end is None or end < start:
        return None
    return (end - start) / 1e6


def _summary(values: Sequence[float]) -> dict[str, float | None]:
    return {
        "min": min(values) if values else None,
        "p50": percentile(values, 50) if values else None,
        "p90": percentile(values, 90) if values else None,
        "p95": percentile(values, 95) if values else None,
        "max": max(values) if values else None,
        "mean": sum(values) / len(values) if values else None,
    }


def _source_value(
    source_span: Mapping[str, Any],
    counters_source: Mapping[str, Any],
    *names: str,
) -> Any:
    for name in names:
        value = source_span.get(name)
        if value is not None:
            return value
        value = counters_source.get(name)
        if value is not None:
            return value
    return None


def summarize_source_operations(
    operations: Sequence[Mapping[str, Any]] | None,
    *,
    source_span: Mapping[str, Any] | None = None,
    counters_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reduce source operation records to bounded, JSON-friendly evidence."""
    span = source_span if isinstance(source_span, Mapping) else {}
    counters = counters_source if isinstance(counters_source, Mapping) else {}
    normalized: list[tuple[int, Mapping[str, Any], float | None]] = []
    for operation in operations or ():
        if not isinstance(operation, Mapping):
            continue
        ordinal = _integer(operation.get("ordinal"))
        if ordinal is None:
            continue
        normalized.append((ordinal, operation, _duration_ms(operation)))
    normalized.sort(key=lambda item: item[0])
    durations = [duration for _, _, duration in normalized if duration is not None]

    per_reader_data: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"operation_count": 0, "bytes": 0, "durations": []}
    )
    for _, operation, duration in normalized:
        reader_id = _integer(operation.get("reader_id"))
        if reader_id is None:
            continue
        aggregate = per_reader_data[reader_id]
        aggregate["operation_count"] += 1
        nbytes = _integer(operation.get("nbytes"))
        if nbytes is not None:
            aggregate["bytes"] += nbytes
        if duration is not None:
            aggregate["durations"].append(duration)
    per_reader = []
    for reader_id in sorted(per_reader_data):
        aggregate = per_reader_data[reader_id]
        reader_durations = aggregate["durations"]
        per_reader.append({
            "reader_id": reader_id,
            "operation_count": aggregate["operation_count"],
            "bytes": aggregate["bytes"],
            "memcpy_total_ms": sum(reader_durations) if reader_durations else None,
            "memcpy_mean_ms": (
                sum(reader_durations) / len(reader_durations)
                if reader_durations else None
            ),
            "memcpy_max_ms": max(reader_durations) if reader_durations else None,
        })

    first_operations = []
    for ordinal, operation, duration in normalized[:8]:
        first_operations.append({
            "ordinal": ordinal,
            "reader_id": _integer(operation.get("reader_id")),
            "source_offset": _integer(operation.get("source_offset")),
            "memcpy_ms": duration,
            "slot_wait_ms": _milliseconds(operation.get("slot_wait_ns")),
            "pacing_wait_ms": _milliseconds(operation.get("pacing_wait_ns")),
        })

    thirds: dict[str, dict[str, float | None]] = {}
    names = ("first_third", "middle_third", "final_third")
    count = len(normalized)
    if count < 3:
        sizes = [1 if index < count else 0 for index in range(3)]
    else:
        base, remainder = divmod(count, 3)
        sizes = [base + (index < remainder) for index in range(3)]
    cursor = 0
    for name, size in zip(names, sizes):
        values = [
            duration for _, _, duration in normalized[cursor:cursor + size]
            if duration is not None
        ]
        thirds[name] = {
            "p50": percentile(values, 50) if values else None,
            "max": max(values) if values else None,
        }
        cursor += size

    time_weighted = counters.get("time_weighted_reader_concurrency")
    if not isinstance(time_weighted, Mapping):
        time_weighted = {}
    source_start = _integer(span.get("source_start_ns"))
    ready_times: list[int] = []
    for _, operation, _ in normalized:
        ready_ns = _integer(operation.get("ready_ns"))
        if ready_ns is not None:
            ready_times.append(ready_ns)
    first_completed = None
    if source_start is not None and ready_times:
        first_completed = (min(ready_times) - source_start) / 1e6

    result: dict[str, Any] = {
        "operation_count": len(normalized),
        "memcpy_duration_ms": _summary(durations),
        "memcpy_counts": {
            "gt_50ms": sum(value > 50 for value in durations),
            "gt_100ms": sum(value > 100 for value in durations),
            "gt_250ms": sum(value > 250 for value in durations),
            "gt_500ms": sum(value > 500 for value in durations),
            "gt_1000ms": sum(value > 1000 for value in durations),
        },
        "per_reader": per_reader,
        "first_8_operations": first_operations,
        "thirds": thirds,
        "first_operation_memcpy_ms": normalized[0][2] if normalized else None,
        "first_completed_operation_ms_from_source_start": first_completed,
        "memcpy_interval_note": (
            "The memcpy interval includes native mapped-page acquisition that "
            "occurs while libc is touching/copying mmap pages."
        ),
        "source_wall_ms": _source_value(span, counters, "source_wall_ms"),
        "source_gbps": _source_value(span, counters, "source_gbps"),
        "effective_reader_concurrency": _source_value(
            span, counters, "effective_reader_concurrency"
        ),
        "time_weighted_effective_concurrency": time_weighted.get("effective_concurrency"),
        "below_four_reader_ms": _milliseconds(time_weighted.get("below_four_reader_ns")),
        "longest_zero_reader_ms": _milliseconds(time_weighted.get("longest_zero_reader_ns")),
        "slot_wait_ms": _milliseconds(counters.get("slot_acquire_wait_ns")),
        "slot_wait_count": counters.get("slot_acquire_wait_count"),
        "all_slots_occupied_count": counters.get("all_slots_occupied_count"),
        "capacity_wait_ms": _milliseconds(counters.get("capacity_wait_ns")),
        "capacity_wait_count": counters.get("capacity_wait_count"),
        "ready_queue_wait_ms": _milliseconds(counters.get("ready_queue_wait_ns")),
        "ready_queue_wait_count": counters.get("ready_queue_wait_count"),
        "pacing_wait_count": counters.get("pacing_wait_count"),
        "pacing_zero_delay_count": counters.get("pacing_zero_delay_count"),
        "min_source_gap_ms": _milliseconds(counters.get("min_source_gap_ns")),
        "pacer_gap_violation_count": counters.get("pacer_gap_violation_count"),
        "source_final_byte_complete_ns": _source_value(
            span, counters, "source_final_byte_complete_ns"
        ),
        "final_h2d_submit_ns": counters.get("final_h2d_submit_ns"),
        "final_h2d_completion_observed_ns": counters.get(
            "final_h2d_completion_observed_ns"
        ),
        "gpu_ready_tail_ms": counters.get("gpu_ready_tail_ms"),
    }
    return result


def summarize_first_h2d(
    operations: Sequence[Mapping[str, Any]] | None,
    *,
    source_start_ns: Any,
    first_h2d_submit_ns: Any,
    first_h2d_completion_ns: Any,
) -> dict[str, float | None]:
    """Summarize source start to the first H2D submit and completion."""
    source_start = _integer(source_start_ns)
    first_submit = _integer(first_h2d_submit_ns)
    first_completion = _integer(first_h2d_completion_ns)
    ready_times: list[int] = []
    for operation in operations or ():
        if not isinstance(operation, Mapping):
            continue
        ready_ns = _integer(operation.get("ready_ns"))
        if ready_ns is not None:
            ready_times.append(ready_ns)
    first_ready = min(ready_times) if ready_times else None
    return {
        "source_start_to_first_ready_ms": (
            (first_ready - source_start) / 1e6
            if first_ready is not None and source_start is not None else None
        ),
        "source_start_to_first_h2d_submit_ms": (
            (first_submit - source_start) / 1e6
            if first_submit is not None and source_start is not None else None
        ),
        "first_h2d_submit_to_completion_ms": (
            (first_completion - first_submit) / 1e6
            if first_completion is not None and first_submit is not None else None
        ),
    }


def _parse_cpu_list(value: str) -> list[int] | None:
    cpus: set[int] = set()
    try:
        for part in value.strip().split(","):
            if not part:
                continue
            if "-" in part:
                first, last = (int(item) for item in part.split("-", 1))
                cpus.update(range(first, last + 1))
            else:
                cpus.add(int(part))
        return sorted(cpus) if cpus else None
    except (TypeError, ValueError):
        return None


def _read_allowed_cpus(pid: int) -> list[int] | None:
    with open(os.path.join(PROC_ROOT, str(pid), "status"), encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("Cpus_allowed_list:"):
                return _parse_cpu_list(line.split(":", 1)[1])
    return None


def _current_cpu() -> int | None:
    try:
        libc = ctypes.CDLL(None)
        sched_getcpu = libc.sched_getcpu
        sched_getcpu.restype = ctypes.c_int
        value = int(sched_getcpu())
        return value if value >= 0 else None
    except Exception:
        return None


def _read_thread_cpu(pid: int, tid: int) -> int | None:
    with open(os.path.join(PROC_ROOT, str(pid), "task", str(tid), "stat"), encoding="utf-8") as handle:
        raw = handle.read()
    tail = raw.rsplit(")", 1)[-1].split()
    value = int(tail[36])
    return value if value >= 0 else None


def _reader_threads(pid: int, unavailable: list[str]) -> list[dict[str, Any]] | None:
    try:
        tids = sorted(int(item) for item in os.listdir(os.path.join(PROC_ROOT, str(pid), "task")))
    except Exception:
        unavailable.append("source.reader_threads")
        return None
    threads = []
    for tid in tids:
        try:
            with open(os.path.join(PROC_ROOT, str(pid), "task", str(tid), "comm"), encoding="utf-8") as handle:
                name = handle.read().strip()
        except Exception:
            name = str(tid)
        try:
            cpu = _read_thread_cpu(pid, tid)
        except Exception:
            cpu = None
            unavailable.append("source.reader_thread_cpu")
        threads.append({"name": name, "cpu": cpu})
    return threads


def _arena_numa_pages(arena_name: str | None) -> dict[str, int] | None:
    if not arena_name:
        return None
    needle = str(arena_name).lstrip("/")
    nodes: dict[str, int] = {}
    with open(os.path.join(PROC_ROOT, "self", "numa_maps"), encoding="utf-8") as handle:
        for line in handle:
            if needle not in line and f"/dev/shm/{needle}" not in line:
                continue
            for token in line.split()[1:]:
                if token.startswith("N") and "=" in token:
                    node, count = token.split("=", 1)
                    if count.isdigit():
                        nodes[node[1:]] = nodes.get(node[1:], 0) + int(count)
    return nodes or None


def _sysfs_gpu(index: int) -> tuple[str | None, int | None]:
    device = os.path.join(SYSFS_ROOT, "class", "drm", f"card{index}", "device")
    pci = None
    numa = None
    try:
        with open(os.path.join(device, "uevent"), encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PCI_SLOT_NAME="):
                    pci = line.split("=", 1)[1].strip() or None
    except Exception:
        pass
    if pci is None:
        # Only accept a realpath basename that actually looks like a PCI
        # address.  Anything else (for example a bare "device" on a host with
        # no DRM class) is a guess, and a guess is worse than None here.
        try:
            candidate = os.path.basename(os.path.realpath(device))
        except Exception:
            candidate = ""
        if _PCI_ADDRESS.fullmatch(candidate or ""):
            pci = candidate
    try:
        with open(os.path.join(device, "numa_node"), encoding="utf-8") as handle:
            value = int(handle.read().strip())
            numa = value if value >= 0 else None
    except Exception:
        pass
    return pci, numa


def _gpu_telemetry(unavailable: list[str]) -> dict[str, Any]:
    gpu: dict[str, Any] = {
        "device_count": None, "index": None, "name": None, "capability": None,
        "pci_bus_id": None, "gpu_numa_node": None, "nvml": None,
    }
    torch = None
    try:
        import torch as torch_module
        torch = torch_module
        gpu["device_count"] = int(torch.cuda.device_count())
        if gpu["device_count"]:
            gpu["index"] = int(torch.cuda.current_device())
            gpu["name"] = str(torch.cuda.get_device_name(gpu["index"]))
            capability = torch.cuda.get_device_capability(gpu["index"])
            gpu["capability"] = f"{int(capability[0])}.{int(capability[1])}"
    except Exception:
        unavailable.append("gpu.device_count")
    if gpu["device_count"]:
        try:
            gpu["pci_bus_id"], gpu["gpu_numa_node"] = _sysfs_gpu(gpu["index"])
        except Exception:
            pass

    nvml = None
    try:
        pynvml = importlib.import_module("pynvml")
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(int(gpu["index"] or 0))
        nvml = {
            "sm_clock_mhz": int(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_SM)),
            "mem_clock_mhz": int(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)),
            "performance_state": str(pynvml.nvmlDeviceGetPerformanceState(handle)),
            "power_draw_w": float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0,
            "power_limit_w": float(pynvml.nvmlDeviceGetPowerManagementLimit(handle)) / 1000.0,
            "pcie_generation": int(pynvml.nvmlDeviceGetCurrPcieLinkGeneration(handle)),
            "pcie_width": int(pynvml.nvmlDeviceGetCurrPcieLinkWidth(handle)),
        }
        if gpu["pci_bus_id"] is None:
            gpu["pci_bus_id"] = str(pynvml.nvmlDeviceGetPciInfo(handle).busId)
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    except Exception:
        pass
    if gpu["device_count"] is None:
        unavailable.append("gpu.device_count")
    if not gpu["device_count"]:
        unavailable.append("gpu.index")
        unavailable.append("gpu.name")
        unavailable.append("gpu.capability")
    if gpu["pci_bus_id"] is None:
        unavailable.append("gpu.pci_bus_id")
    if gpu["gpu_numa_node"] is None:
        unavailable.append("gpu.gpu_numa_node")
    if nvml is None:
        unavailable.append("gpu.nvml")
    else:
        for key, value in nvml.items():
            if value is None:
                unavailable.append(f"gpu.nvml.{key}")
    gpu["nvml"] = nvml
    return gpu


def _collect_placement_telemetry_uncached(
    *,
    arena_name: str | None = None,
    arena_bytes: int | None = None,
    source_child_pid: int | None = None,
) -> dict[str, Any]:
    """Collect one best-effort placement snapshot and memoize it per process."""
    unavailable: list[str] = []
    pid = os.getpid()
    parent_affinity = None
    try:
        get_affinity: Any = getattr(os, "sched_getaffinity", None)
        if not callable(get_affinity):
            raise OSError("sched_getaffinity unavailable")
        parent_affinity = sorted(int(cpu) for cpu in cast(Any, get_affinity)(0))
    except Exception:
        unavailable.append("parent.cpu_affinity")
    current_cpu = _current_cpu()
    if current_cpu is None:
        unavailable.append("parent.current_cpu")
    try:
        from .host_hardware_telemetry import read_cgroup_fields
        cgroup_cpu = read_cgroup_fields()
        if (
            not isinstance(cgroup_cpu, Mapping)
            or not cgroup_cpu
            or cgroup_cpu.get("cgroup_source") == "unavailable"
        ):
            unavailable.append("parent.cgroup_cpu")
            cgroup_cpu = None
    except Exception:
        cgroup_cpu = None
        unavailable.append("parent.cgroup_cpu")

    source_pid = _integer(source_child_pid)
    if source_pid is None:
        unavailable.append("source.child_pid")
    allowed_cpus = None
    reader_threads = None
    if source_pid is not None:
        try:
            allowed_cpus = _read_allowed_cpus(source_pid)
        except Exception:
            unavailable.append("source.allowed_cpus")
        reader_threads = _reader_threads(source_pid, unavailable)
    else:
        unavailable.extend(("source.allowed_cpus", "source.reader_threads"))

    valid_arena_bytes = _integer(arena_bytes)
    if valid_arena_bytes is None:
        unavailable.append("arena.arena_bytes")
    if arena_name is None:
        unavailable.append("arena.shared_memory_name")
    try:
        numa_pages = _arena_numa_pages(arena_name)
    except Exception:
        numa_pages = None
        unavailable.append("arena.numa_node_pages")
    if numa_pages is None and "arena.numa_node_pages" not in unavailable:
        unavailable.append("arena.numa_node_pages")

    gpu = _gpu_telemetry(unavailable)
    result = {
        "status": "degraded" if unavailable else "ok",
        "unavailable": sorted(set(unavailable)),
        "parent": {
            "cpu_affinity": parent_affinity,
            "cpu_affinity_count": len(parent_affinity) if parent_affinity is not None else None,
            "current_cpu": current_cpu,
            "cgroup_cpu": cgroup_cpu,
            "pid": pid,
        },
        "source": {
            "child_pid": source_pid,
            "allowed_cpus": allowed_cpus,
            "reader_threads": reader_threads,
        },
        "arena": {
            "shared_memory_name": str(arena_name) if arena_name is not None else None,
            "arena_bytes": valid_arena_bytes,
            "numa_node_pages": numa_pages,
            "numa": "observed" if numa_pages is not None else "unavailable",
        },
        "gpu": gpu,
    }
    return result


def collect_placement_telemetry(
    *,
    arena_name: str | None = None,
    arena_bytes: int | None = None,
    source_child_pid: int | None = None,
) -> dict[str, Any]:
    """Collect once per process; an unexpected probe failure still degrades."""
    global _PLACEMENT_CACHE
    if _PLACEMENT_CACHE is not None:
        return _PLACEMENT_CACHE
    try:
        result = _collect_placement_telemetry_uncached(
            arena_name=arena_name,
            arena_bytes=arena_bytes,
            source_child_pid=source_child_pid,
        )
    except BaseException:
        try:
            pid = int(os.getpid())
        except BaseException:
            pid = 0
        result = {
            "status": "degraded",
            "unavailable": [
                "placement_collection", "parent.cpu_affinity", "parent.current_cpu",
                "parent.cgroup_cpu", "source.allowed_cpus", "source.reader_threads",
                "arena.shared_memory_name", "arena.arena_bytes", "arena.numa_node_pages",
                "gpu.device_count", "gpu.index", "gpu.name",
                "gpu.capability", "gpu.pci_bus_id", "gpu.gpu_numa_node", "gpu.nvml",
            ],
            "parent": {
                "cpu_affinity": None,
                "cpu_affinity_count": None,
                "current_cpu": None,
                "cgroup_cpu": None,
                "pid": pid,
            },
            "source": {
                "child_pid": _integer(source_child_pid),
                "allowed_cpus": None,
                "reader_threads": None,
            },
            "arena": {
                "shared_memory_name": str(arena_name) if arena_name is not None else None,
                "arena_bytes": _integer(arena_bytes),
                "numa_node_pages": None,
                "numa": "unavailable",
            },
            "gpu": {
                "device_count": None,
                "index": None,
                "name": None,
                "capability": None,
                "pci_bus_id": None,
                "gpu_numa_node": None,
                "nvml": None,
            },
        }
    _PLACEMENT_CACHE = result
    return result
