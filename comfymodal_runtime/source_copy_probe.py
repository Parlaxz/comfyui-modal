"""Per-copy stall evidence for the mapped source owner.

The pathological source signature is a handful of individual 64 MiB
``libc.memmove`` calls taking 1-4+ seconds while other blocks in the *same*
run copy faster than normal.  Wall time alone cannot tell a backing-page stall
from thread descheduling from real CPU/memory-bandwidth work, so each copy
records what the kernel already knows about the calling thread:

    the exact memmove interval (not the wider pacer-wrapped one)
    CLOCK_THREAD_CPUTIME_ID  -> was the thread burning CPU or sleeping?
    RUSAGE_THREAD fault and block-I/O counters -> page acquisition?
    RUSAGE_THREAD context switches -> descheduling?
    sched_getcpu -> placement, explicitly unreliable under gVisor
    mincore() -> page residency, diagnostic-gated and off by default

Everything here is *observation only*.  Nothing in this module changes source
behaviour: no ``madvise``, no ``readahead``, no affinity, no geometry change.
When a probe cannot be taken it degrades to a sentinel and the copy proceeds
untouched -- model loading must never fail because a diagnostic is unavailable.
"""

from __future__ import annotations

import ctypes
import os
import time
from typing import Any

# Shared-memory operation records are unsigned 64-bit slots.  ``SENTINEL``
# marks "this probe was unavailable" and must never be confused with a real
# zero delta, because "zero major faults" and "no fault data" are exactly the
# two things the root-cause classification has to tell apart.
SENTINEL = (1 << 64) - 1

# Availability bits packed into the record's ``diag_flags`` field.
PROBE_RUSAGE = 1 << 0
PROBE_THREAD_CPU = 1 << 1
PROBE_CPU_ID = 1 << 2
PROBE_RESIDENT_PRE = 1 << 3
PROBE_RESIDENT_POST = 1 << 4

_PPM_SCALE = 1_000_000


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


class _RusageSnapshot:
    """Immutable point-in-time view of the calling thread's rusage counters."""

    __slots__ = ("minflt", "majflt", "inblock", "nvcsw", "nivcsw")

    def __init__(self, minflt: int, majflt: int, inblock: int,
                 nvcsw: int, nivcsw: int) -> None:
        self.minflt = minflt
        self.majflt = majflt
        self.inblock = inblock
        self.nvcsw = nvcsw
        self.nivcsw = nivcsw


class SourceCopyProbe:
    """Around-the-memmove evidence for exactly one source block copy.

    One instance is created per reader thread before any copy runs, so every
    capability question (``RUSAGE_THREAD``, ``sched_getcpu``, ``mincore``) is
    answered once at construction instead of per block.  When the probe is
    disabled or degraded, :meth:`begin`/:meth:`end` cost a single boolean test
    and the copy path is byte-for-byte the un-instrumented path.
    """

    __slots__ = (
        "enabled", "_rusage", "_thread_cpu", "_cpu_id", "_mincore",
        "_page_size", "_libc", "notes",
    )

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._rusage = None
        self._thread_cpu = None
        self._cpu_id = None
        self._mincore = None
        self._page_size = 0
        self._libc: Any = None
        self.notes: list[str] = []
        self.enabled = _env_flag("COMFYMODAL_GOLDEN_SOURCE_COPY_PROBE") if enabled is None else bool(enabled)
        if not self.enabled:
            return
        self._resolve()

    # ── capability resolution (once per reader) ───────────────────────────
    def _resolve(self) -> None:
        try:
            import resource  # noqa: PLC0415 - POSIX-only, resolved lazily

            if hasattr(resource, "RUSAGE_THREAD"):
                self._rusage = resource
            else:
                self.notes.append("rusage_thread_unavailable")
        except Exception as exc:  # pragma: no cover - platform dependent
            self.notes.append(f"rusage_import_failed:{type(exc).__name__}")

        if hasattr(time, "thread_time_ns"):
            self._thread_cpu = time.thread_time_ns
        else:
            self.notes.append("thread_time_ns_unavailable")

        if hasattr(os, "sched_getcpu"):
            self._cpu_id = os.sched_getcpu
        else:
            self.notes.append("sched_getcpu_unavailable")

        # mincore() is strictly opt-in on top of the probe gate.  Under gVisor
        # its residency semantics on a mounted Volume are unverified, so it
        # stays off unless a run explicitly asks for it.
        if _env_flag("COMFYMODAL_GOLDEN_SOURCE_COPY_PROBE_MINCORE"):
            self._resolve_mincore()

    def _resolve_mincore(self) -> None:
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            libc.mincore.restype = ctypes.c_int
            libc.mincore.argtypes = [
                ctypes.c_void_p, ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
            ]
            self._libc = libc
            self._page_size = int(os.sysconf("SC_PAGE_SIZE"))
            self.notes.append("mincore_enabled")
        except Exception as exc:
            self._mincore = None
            self.notes.append(f"mincore_unavailable:{type(exc).__name__}")

    # ── hot path ──────────────────────────────────────────────────────────
    def begin(self, copy_address: int, length: int) -> tuple:
        """Snapshot everything available immediately before the memmove."""
        if not self.enabled:
            return ()
        wall_start = time.monotonic_ns()
        rusage = self._read_rusage()
        cpu_before = self._thread_cpu() if self._thread_cpu is not None else None
        resident_pre = self._residency(copy_address, length)
        return (wall_start, rusage, cpu_before, resident_pre)

    def end(self, state: tuple) -> dict[str, int]:
        """Collect the after-side evidence and derive per-copy deltas."""
        if not self.enabled or not state:
            return sentinel_record()
        wall_start, rusage, cpu_before, resident_pre = state
        wall_ns = max(0, time.monotonic_ns() - wall_start)
        cpu_after = self._thread_cpu() if self._thread_cpu is not None else None
        rusage_after = self._read_rusage()

        flags = 0
        if cpu_before is not None and cpu_after is not None:
            flags |= PROBE_THREAD_CPU
        if rusage is not None and rusage_after is not None:
            flags |= PROBE_RUSAGE

        start_cpu = end_cpu = SENTINEL
        if self._cpu_id is not None:
            try:
                end_cpu = int(self._cpu_id())
                flags |= PROBE_CPU_ID
            except Exception:
                end_cpu = SENTINEL

        def _delta(field: str) -> int:
            if rusage is None or rusage_after is None:
                return SENTINEL
            return max(0, getattr(rusage_after, field) - getattr(rusage, field))

        resident_pre_ppm = SENTINEL
        if resident_pre is not None:
            resident_pre_ppm = int(round(resident_pre * _PPM_SCALE))
            flags |= PROBE_RESIDENT_PRE

        return {
            "copy_wall_ns": wall_ns,
            "thread_cpu_ns_before": SENTINEL if cpu_before is None else int(cpu_before),
            "thread_cpu_ns_after": SENTINEL if cpu_after is None else int(cpu_after),
            "minflt_delta": _delta("minflt"),
            "majflt_delta": _delta("majflt"),
            "inblock_delta": _delta("inblock"),
            "nvcsw_delta": _delta("nvcsw"),
            "nivcsw_delta": _delta("nivcsw"),
            "start_cpu": start_cpu,
            "end_cpu": end_cpu,
            "diag_flags": flags,
            "resident_pre_ppm": resident_pre_ppm,
        }

    # ── helpers ───────────────────────────────────────────────────────────
    def _read_rusage(self) -> _RusageSnapshot | None:
        if self._rusage is None:
            return None
        try:
            usage = self._rusage.getrusage(self._rusage.RUSAGE_THREAD)
        except Exception:
            return None
        return _RusageSnapshot(
            int(usage.ru_minflt), int(usage.ru_majflt), int(usage.ru_inblock),
            int(usage.ru_nvcsw), int(usage.ru_nivcsw),
        )

    def _residency(self, address: int, length: int) -> float | None:
        """Resident fraction of a mapped range, without faulting it in.

        ``mincore`` inspects page tables directly, so it does not populate the
        range.  The address is aligned down and the length up so the vector
        covers whole pages, and the count runs in C (``bytes.count``) rather
        than a Python loop over 16K page entries.
        """
        if self._libc is None or length <= 0:
            return None
        page = self._page_size
        start = address & ~(page - 1)
        end = (address + length + page - 1) & ~(page - 1)
        pages = (end - start) // page
        if pages <= 0:
            return None
        vector = (ctypes.c_ubyte * pages)()
        if self._libc.mincore(
            ctypes.c_void_p(start), ctypes.c_size_t(end - start), vector
        ) != 0:
            self.notes.append(f"mincore_failed:errno{ctypes.get_errno()}")
            self._libc = None
            return None
        resident = bytes(vector).count(1)
        return resident / pages


def sentinel_record() -> dict[str, int]:
    """The all-unavailable record. Every field is the sentinel, flags are 0."""
    return {
        "copy_wall_ns": 0,
        "thread_cpu_ns_before": SENTINEL,
        "thread_cpu_ns_after": SENTINEL,
        "minflt_delta": SENTINEL,
        "majflt_delta": SENTINEL,
        "inblock_delta": SENTINEL,
        "nvcsw_delta": SENTINEL,
        "nivcsw_delta": SENTINEL,
        "start_cpu": SENTINEL,
        "end_cpu": SENTINEL,
        "diag_flags": 0,
        "resident_pre_ppm": SENTINEL,
    }


__all__ = [
    "PROBE_CPU_ID",
    "PROBE_RESIDENT_POST",
    "PROBE_RESIDENT_PRE",
    "PROBE_RUSAGE",
    "PROBE_THREAD_CPU",
    "SENTINEL",
    "SourceCopyProbe",
    "sentinel_record",
]