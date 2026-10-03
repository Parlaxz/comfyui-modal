"""Compact aggregation and evidence-based classification of source copy stalls.

Wall time alone cannot distinguish a backing-page stall from thread
descheduling from real memory-bandwidth work.  This module reduces the raw
per-copy probe evidence to bounded telemetry and then labels each slow copy
*only* from what the counters actually show.

Two rules govern the whole module:

1.  **Never force a label.**  When the counters do not discriminate, the copy is
    ``UNRESOLVED``.  A missing probe is reported as unavailable, never as a
    zero, because "zero major faults" and "no fault data" are the two things
    the classification exists to separate.
2.  **Stay bounded.**  Normal telemetry carries aggregates plus at most the top
    eight slowest copies.  No raw dump ever reaches a request payload.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .statistics import percentile
from .source_copy_probe import (
    PROBE_CPU_ID,
    PROBE_RESIDENT_PRE,
    PROBE_RUSAGE,
    PROBE_THREAD_CPU,
    SENTINEL,
)

# A copy slower than this counts as "slow" for classification and for the
# per-class aggregates.  It sits above the healthy p90 (~78 ms) and well below
# the pathological regime (>=1 s) so the label is not applied to noise.
SLOW_MS = 100.0
# Resident-fraction scale used by the probe.
_PPM = 1_000_000
# top-N slowest copies retained in compact telemetry.
TOP_N = 8

CLASSIFICATIONS = (
    "PAGE_IO_STALL",
    "DESCHEDULE_STALL",
    "CPU_MEMORY_STALL",
    "MIXED",
    "UNRESOLVED",
)

# Aggregation inputs that, when they rise, point at page/IO acquisition rather
# than at the CPU or the scheduler.
_IO_SIGNALS = ("majflt_delta", "inblock_delta")
# Context switches point at descheduling.
_SCHED_SIGNALS = ("nvcsw_delta", "nivcsw_delta")
# A healthy multi-second copy takes a handful of context switches incidentally.
# Only a genuinely large switch count is evidence of descheduling; a bare
# ``nvcsw_delta == 1`` is noise and must not manufacture a DESCHEDULE label.
MIN_SCHED_SWITCHES = 64


def _int_or_none(value: Any) -> int | None:
    """Unwrap a ring field, mapping the unavailable sentinel to ``None``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return None if value == SENTINEL else int(value)


def _delta(record: Mapping[str, Any], field: str) -> int | None:
    value = _int_or_none(record.get(field))
    if value is None or value < 0:
        return None
    return value


def _summary(values: Sequence[float]) -> dict[str, float | None]:
    return {
        "p50": percentile(values, 50) if values else None,
        "p90": percentile(values, 90) if values else None,
        "p95": percentile(values, 95) if values else None,
        "p99": percentile(values, 99) if values else None,
        "max": max(values) if values else None,
    }


def copy_wall_ms(record: Mapping[str, Any]) -> float | None:
    """The probe's own memmove interval, falling back to the legacy span.

    The probe brackets the memmove alone; the legacy
    ``memcpy_end_ns - memcpy_start_ns`` span also contains pacer bookkeeping,
    so it is only used when the probe did not run.
    """
    wall = _int_or_none(record.get("copy_wall_ns"))
    if wall is not None and wall > 0:
        return wall / 1e6
    start = _int_or_none(record.get("memcpy_start_ns"))
    end = _int_or_none(record.get("memcpy_end_ns"))
    if start is None or end is None or end < start:
        return None
    return (end - start) / 1e6


def thread_cpu_ms(record: Mapping[str, Any]) -> float | None:
    """CPU actually consumed inside the copy, or ``None`` if unavailable."""
    before = _int_or_none(record.get("thread_cpu_ns_before"))
    after = _int_or_none(record.get("thread_cpu_ns_after"))
    if before is None or after is None or after < before:
        return None
    return (after - before) / 1e6


def wall_cpu_ratio(record: Mapping[str, Any]) -> float | None:
    """Wall divided by thread CPU.

    Near 1 means the thread was busy the whole time (real CPU/memory work);
    near 0 means it was mostly not running (stalled or descheduled).  Returns
    ``None`` when either side is unavailable or CPU time is zero, so the caller
    never divides by zero or reports a fabricated ratio.
    """
    wall = copy_wall_ms(record)
    cpu = thread_cpu_ms(record)
    if wall is None or cpu is None or cpu <= 0 or wall <= 0:
        return None
    return wall / cpu


def classify_copy(record: Mapping[str, Any]) -> dict[str, Any]:
    """Label one copy from its counters, or decline to label it."""
    wall = copy_wall_ms(record)
    cpu = thread_cpu_ms(record)
    ratio = wall_cpu_ratio(record)

    majflt = _delta(record, "majflt_delta")
    inblock = _delta(record, "inblock_delta")
    nvcsw = _delta(record, "nvcsw_delta")
    nivcsw = _delta(record, "nivcsw_delta")
    minflt = _delta(record, "minflt_delta")
    resident_pre = _int_or_none(record.get("resident_pre_ppm"))

    io_evidence = bool(majflt) or bool(inblock)
    # A single incidental switch is not descheduling evidence.
    sched_evidence = (nvcsw or 0) + (nivcsw or 0) >= MIN_SCHED_SWITCHES
    # A low pre-copy residency is corroborating, not decisive, evidence.
    low_residency = resident_pre is not None and resident_pre < int(0.25 * _PPM)

    evidence = {
        "memcpy_wall_ms": wall,
        "thread_cpu_ms": cpu,
        "wall_cpu_ratio": ratio,
        "minflt_delta": minflt,
        "majflt_delta": majflt,
        "inblock_delta": inblock,
        "nvcsw_delta": nvcsw,
        "nivcsw_delta": nivcsw,
        "pre_resident_fraction": (
            resident_pre / _PPM if resident_pre is not None else None
        ),
    }

    if wall is None or cpu is None or ratio is None:
        return {"classification": "UNRESOLVED", "reason": "cpu_or_wall_unavailable", **evidence}

    # "Stalled" means the thread was not busy for most of the wall interval.
    stalled = ratio >= 4.0
    # "Busy" means CPU time tracked wall time closely.
    busy = ratio <= 1.5

    if stalled and io_evidence:
        classification = "PAGE_IO_STALL"
    elif stalled and sched_evidence:
        classification = "DESCHEDULE_STALL"
    elif busy and not io_evidence:
        classification = "CPU_MEMORY_STALL"
    elif stalled and low_residency:
        classification = "PAGE_IO_STALL"
    elif busy and io_evidence:
        classification = "MIXED"
    else:
        classification = "UNRESOLVED"

    return {
        "classification": classification,
        "reason": _reason(classification, ratio, io_evidence, sched_evidence),
        **evidence,
    }


def _reason(classification: str, ratio: float | None, io: bool, sched: bool) -> str:
    if classification == "PAGE_IO_STALL":
        return f"wall/cpu={ratio:.1f} with page-acquisition evidence"
    if classification == "DESCHEDULE_STALL":
        return f"wall/cpu={ratio:.1f} with context-switch evidence and no I/O faults"
    if classification == "CPU_MEMORY_STALL":
        return f"wall/cpu={ratio:.1f} means the thread was busy copying"
    if classification == "MIXED":
        return "thread was busy copying while I/O evidence also rose"
    return "counters do not discriminate"


def _compact_copy(record: Mapping[str, Any], ordinal: Any, detail: Mapping[str, Any]) -> dict[str, Any]:
    """One bounded top-slow entry: compact fields only, never a raw record."""
    return {
        "ordinal": ordinal,
        "reader_id": _int_or_none(record.get("reader_id")),
        "source_offset": _int_or_none(record.get("source_offset")),
        "nbytes": _int_or_none(record.get("nbytes")),
        "memcpy_wall_ms": detail.get("memcpy_wall_ms"),
        "thread_cpu_ms": detail.get("thread_cpu_ms"),
        "wall_cpu_ratio": detail.get("wall_cpu_ratio"),
        "minflt_delta": detail.get("minflt_delta"),
        "majflt_delta": detail.get("majflt_delta"),
        "inblock_delta": detail.get("inblock_delta"),
        "nvcsw_delta": detail.get("nvcsw_delta"),
        "nivcsw_delta": detail.get("nivcsw_delta"),
        "start_cpu": _int_or_none(record.get("start_cpu")),
        "end_cpu": _int_or_none(record.get("end_cpu")),
        "pre_resident_fraction": detail.get("pre_resident_fraction"),
        "classification": detail.get("classification"),
    }


def summarize_copy_stalls(operations: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Bounded per-model source stall telemetry and classification counts."""
    records = [item for item in (operations or ()) if isinstance(item, Mapping)]

    walls: list[float] = []
    cpus: list[float] = []
    ratios: list[float] = []
    totals = {"minflt": 0, "majflt": 0, "inblock": 0, "nvcsw": 0, "nivcsw": 0}
    availability = {"rusage": False, "thread_cpu": False, "cpu_id": False, "resident": False}
    ranked: list[tuple[float, Any, Mapping[str, Any], Mapping[str, Any]]] = []
    counts = {"gt_100ms": 0, "gt_250ms": 0, "gt_500ms": 0, "gt_1000ms": 0}
    class_counts = {name: 0 for name in CLASSIFICATIONS}
    slow_classes: dict[str, dict[str, Any]] = {}

    for record in records:
        flags = record.get("diag_flags")
        flags = flags if isinstance(flags, int) and not isinstance(flags, bool) else 0
        availability["rusage"] |= bool(flags & PROBE_RUSAGE)
        availability["thread_cpu"] |= bool(flags & PROBE_THREAD_CPU)
        availability["cpu_id"] |= bool(flags & PROBE_CPU_ID)
        availability["resident"] |= bool(flags & PROBE_RESIDENT_PRE)

        detail = classify_copy(record)
        wall = detail.get("memcpy_wall_ms")
        cpu = detail.get("thread_cpu_ms")
        ratio = detail.get("wall_cpu_ratio")
        if wall is not None:
            walls.append(wall)
            ranked.append((wall, record.get("ordinal"), record, detail))
            for name, limit in (("gt_100ms", 100), ("gt_250ms", 250),
                                ("gt_500ms", 500), ("gt_1000ms", 1000)):
                if wall > limit:
                    counts[name] += 1
        if cpu is not None:
            cpus.append(cpu)
        if ratio is not None:
            ratios.append(ratio)

        for key, field in (("minflt", "minflt_delta"), ("majflt", "majflt_delta"),
                           ("inblock", "inblock_delta"), ("nvcsw", "nvcsw_delta"),
                           ("nivcsw", "nivcsw_delta")):
            value = _delta(record, field)
            if value is not None:
                totals[key] += value

        label = str(detail.get("classification"))
        if label in class_counts:
            class_counts[label] += 1
        if wall is not None and wall > SLOW_MS:
            bucket = slow_classes.setdefault(
                label, {"count": 0, "cpu_total_ms": 0.0, "cpu_max_ms": 0.0,
                        "majflt_total": 0, "inblock_total": 0,
                        "nvcsw_total": 0, "nivcsw_total": 0}
            )
            bucket["count"] += 1
            if cpu is not None:
                bucket["cpu_total_ms"] += cpu
                bucket["cpu_max_ms"] = max(bucket["cpu_max_ms"], cpu)
            for key, field in (("majflt_total", "majflt_delta"),
                               ("inblock_total", "inblock_delta"),
                               ("nvcsw_total", "nvcsw_delta"),
                               ("nivcsw_total", "nivcsw_delta")):
                value = _delta(record, field)
                if value is not None:
                    bucket[key] += value

    for bucket in slow_classes.values():
        bucket["cpu_mean_ms"] = (
            bucket["cpu_total_ms"] / bucket["count"] if bucket["count"] else None
        )

    ranked.sort(key=lambda item: item[0], reverse=True)
    top_slow = [
        _compact_copy(record, ordinal, detail)
        for _, ordinal, record, detail in ranked[:TOP_N]
    ]

    return {
        "copy_count": len(records),
        "memcpy_wall_ms": _summary(walls),
        "thread_cpu_ms": _summary(cpus),
        "wall_cpu_ratio": _summary(ratios),
        "fault_and_context_totals": totals,
        "slow_copy_counts": counts,
        "probe_availability": availability,
        "classification_counts": class_counts,
        "slow_class_breakdown": slow_classes,
        "top_8_slowest": top_slow,
        "slow_threshold_ms": SLOW_MS,
        "top_n_limit": TOP_N,
    }


__all__ = [
    "CLASSIFICATIONS",
    "SLOW_MS",
    "TOP_N",
    "classify_copy",
    "copy_wall_ms",
    "summarize_copy_stalls",
    "thread_cpu_ms",
    "wall_cpu_ratio",
]