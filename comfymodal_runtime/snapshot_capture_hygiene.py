"""Capture-time allocator hygiene (R2a).

Immediately before Modal's snapshot capture boundary this module runs a
bounded hygiene pass: ``gc.collect()`` followed by glibc ``malloc_trim(0)``,
with hard before/after measurements of VmRSS / RssAnon / RssFile / VmSize /
VmData (from ``/proc/self/status``) and the cgroup memory current.  The
before/after VmRSS delta is a lower bound on anonymous pages returned to the
kernel by the pass (deltas are computed as *before − after*, so a positive
delta means bytes were returned/freed).

The pass is flag-gated: ``COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE``
(0 = disabled default, 1 = enabled).  It runs only at the snapshot capture
boundary and never touches models or runtime state — it only collects
garbage, trims the allocator and measures.  Measurements that are unavailable
are ``None`` (never fabricated zeros); on non-Linux platforms (e.g. Windows
dev) ``malloc_trim`` is reported as unavailable, which is the nonfatal path.
Everything here is bounded and never raises.
"""

from __future__ import annotations

import gc
import os
import time
from typing import Any

HYGIENE_GATE_KEY = "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE"
_TRUTHY = {"1", "true", "yes", "on"}

_FIELD_LINE_KEYS = ("VmRSS", "RssAnon", "RssFile", "VmSize", "VmData")
_FIELD_KEY_MAP = {
    "VmRSS": "rss_kb",
    "RssAnon": "rss_anon_kb",
    "RssFile": "rss_file_kb",
    "VmSize": "vmsize_kb",
    "VmData": "vmdata_kb",
}
_CGROUP_PATHS = (
    "/sys/fs/cgroup/memory.current",
    "/sys/fs/cgroup/memory/memory.usage_in_bytes",
)

_LATEST_HYGIENE: dict[str, Any] | None = None


def hygiene_enabled() -> bool:
    raw = os.environ.get(HYGIENE_GATE_KEY)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY


def read_process_status_fields() -> dict[str, int | None]:
    """Parse VmRSS/RssAnon/RssFile/VmSize/VmData (kB ints) from
    ``/proc/self/status`` once.  Any parse failure → None for that field;
    an unreadable file → all fields None.  Never raises."""
    out: dict[str, int | None] = {
        "rss_kb": None,
        "rss_anon_kb": None,
        "rss_file_kb": None,
        "vmsize_kb": None,
        "vmdata_kb": None,
    }
    try:
        with open("/proc/self/status", "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read(1 << 20)
    except Exception:
        return out
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        out_key = _FIELD_KEY_MAP.get(key)
        if out_key is None:
            continue
        tokens = value.strip().split()
        if not tokens:
            continue
        try:
            out[out_key] = int(tokens[0])
        except Exception:
            out[out_key] = None
    return out


def read_cgroup_memory_current_bytes() -> int | None:
    """cgroup v2 ``memory.current`` with v1 ``usage_in_bytes`` fallback.
    Returns int bytes, or None when unreadable.  Never raises."""
    for path in _CGROUP_PATHS:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read(4096)
            if not raw:
                continue
            return int(raw.strip().split()[0])
        except Exception:
            continue
    return None


def _malloc_trim() -> tuple[bool, int | None]:
    """Guarded libc ``malloc_trim(0)``.  Returns ``(available, result)``;
    ``(False, None)`` on unsupported platforms or any failure.  Never raises."""
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.malloc_trim.argtypes = [ctypes.c_size_t]
        libc.malloc_trim.restype = ctypes.c_int
        ret = libc.malloc_trim(0)
        return (True, int(ret))
    except (AttributeError, OSError):
        return (False, None)
    except Exception:
        return (False, None)


def _delta(before: int | None, after: int | None) -> int | None:
    if isinstance(before, int) and isinstance(after, int):
        return before - after
    return None


def _print_event(event: dict[str, Any]) -> None:
    try:
        fields = " ".join(
            f"{key}={'unavailable' if value is None else value}"
            for key, value in event.items()
        )
        print(f"[v2.snapshot_capture_hygiene] {fields}", flush=True)
    except Exception:
        pass


def run_capture_hygiene(*, manifest_captured: bool = False) -> dict[str, Any]:
    """Run the full capture-boundary hygiene sequence and return the event
    dict (never raises):

    1. measure before (process status fields + cgroup memory current), t0;
    2. ``gc.collect()`` (return value = objects collected);
    3. ``malloc_trim(0)`` (guarded, nonfatal when unavailable);
    4. t1, measure after (process status fields + cgroup memory current);
    5. build + store the event under ``_LATEST_HYGIENE``, print a compact
       ``[v2.snapshot_capture_hygiene]`` line, return the event dict.
    """
    global _LATEST_HYGIENE
    before = read_process_status_fields()
    cgroup_before = read_cgroup_memory_current_bytes()
    t0 = time.monotonic_ns()
    gc_collected = gc.collect()
    trim_available, trim_result = _malloc_trim()
    t1 = time.monotonic_ns()
    after = read_process_status_fields()
    cgroup_after = read_cgroup_memory_current_bytes()

    before_rss = before.get("rss_kb")
    after_rss = after.get("rss_kb")
    before_anon = before.get("rss_anon_kb")
    after_anon = after.get("rss_anon_kb")
    before_file = before.get("rss_file_kb")
    after_file = after.get("rss_file_kb")
    before_vmsize = before.get("vmsize_kb")
    after_vmsize = after.get("vmsize_kb")
    before_vmdata = before.get("vmdata_kb")
    after_vmdata = after.get("vmdata_kb")

    event: dict[str, Any] = {
        "enabled": 1 if hygiene_enabled() else 0,
        "gc_collected": gc_collected,
        "malloc_trim_available": trim_available,
        "malloc_trim_result": trim_result,
        "hygiene_wall_ms": round((t1 - t0) / 1_000_000, 3),
        "before_rss_kb": before_rss,
        "after_rss_kb": after_rss,
        "delta_rss_kb": _delta(before_rss, after_rss),
        "before_rss_anon_kb": before_anon,
        "after_rss_anon_kb": after_anon,
        "delta_rss_anon_kb": _delta(before_anon, after_anon),
        "before_rss_file_kb": before_file,
        "after_rss_file_kb": after_file,
        "delta_rss_file_kb": _delta(before_file, after_file),
        "before_vmsize_kb": before_vmsize,
        "after_vmsize_kb": after_vmsize,
        "delta_vmsize_kb": _delta(before_vmsize, after_vmsize),
        "before_vmdata_kb": before_vmdata,
        "after_vmdata_kb": after_vmdata,
        "delta_vmdata_kb": _delta(before_vmdata, after_vmdata),
        "cgroup_memory_current_before_bytes": cgroup_before,
        "cgroup_memory_current_after_bytes": cgroup_after,
        "cgroup_memory_current_delta_bytes": _delta(cgroup_before, cgroup_after),
        "manifest_status": "captured" if manifest_captured else "not_captured",
        "anonymous_measurement_status": (
            "ok" if before_anon is not None or after_anon is not None else "unavailable"
        ),
        "file_backed_measurement_status": (
            "ok" if before_file is not None or after_file is not None else "unavailable"
        ),
        "before_mono_ns": t0,
        "after_mono_ns": t1,
    }
    _LATEST_HYGIENE = event
    _print_event(event)
    return event


def latest_hygiene_event() -> dict[str, Any] | None:
    return _LATEST_HYGIENE


def prove_snapshot_quiescence(
    *, timeout_s: float = 10.0, passive: bool = False
) -> dict[str, Any]:
    """Prove cache and registered executor work are quiescent.

    This is deliberately fail-closed.  Executor enumeration is shared with
    the snapshot manifest so the proof and the diagnostic describe the same
    global executor registry.  The default path retains the historical
    mutating cache quiescence behavior.  ``passive=True`` is for Golden
    capture: it only observes already-clean surfaces and never stops work,
    flushes persistence, or changes cache state.
    """
    checks: list[dict[str, Any]] = []
    try:
        from .clip_conditioning_cache import (
            inspect_for_snapshot,
            quiesce_for_snapshot,
        )

        if passive:
            cache_result = inspect_for_snapshot()
        else:
            cache_result = quiesce_for_snapshot(timeout_s=timeout_s)
    except Exception as exc:
        cache_result = {
            "quiesced": False,
            "joined_workers": 0,
            "pending_dropped": 0,
            "details": [f"conditioning cache proof failed: {type(exc).__name__}: {exc}"],
        }
    checks.append({"name": "exact_clip_conditioning_cache", **cache_result})

    try:
        from .snapshot_build_manifest import enumerate_registered_executors

        executors = enumerate_registered_executors()
    except Exception as exc:
        checks.append({
            "name": "registered_executors",
            "proven": False,
            "details": [f"executor registry enumeration failed: {type(exc).__name__}: {exc}"],
        })
        executors = []

    for item in executors:
        executor = item.get("object")
        pending: int | None = None
        observations: list[str] = []
        try:
            work_queue = getattr(executor, "_work_queue", None)
            if work_queue is not None and callable(getattr(work_queue, "qsize", None)):
                pending = int(work_queue.qsize())
                observations.append("work_queue")
        except Exception:
            pending = None
        try:
            pending_items = getattr(executor, "_pending_work_items", None)
            if pending_items is not None:
                count = len(pending_items)
                pending = max(pending or 0, count)
                observations.append("pending_work_items")
        except Exception:
            pass
        proven = pending == 0
        if pending is None:
            proven = False
            observations.append("pending_work_unobservable")
        checks.append({
            "name": f"{item.get('module', '')}.{item.get('attr', '')}",
            "type": item.get("type"),
            "pending_work": pending,
            "proven": proven,
            "observations": observations,
        })

    if not executors:
        checks.append({
            "name": "registered_executors",
            "registered": 0,
            "pending_work": 0,
            "proven": True,
        })
    def _check_ok(check: dict[str, Any]) -> bool:
        # Checks report their boolean under different semantic keys:
        # cache quiesce uses "quiesced", executor proofs use "proven".
        # (E40 hotfix: aggregating on "proven" alone made every proof
        # False whenever the conditioning-cache check was present.)
        if "proven" in check:
            return bool(check["proven"])
        if "quiesced" in check:
            return bool(check["quiesced"])
        return False

    return {
        "proven": all(_check_ok(check) for check in checks),
        "passive": bool(passive),
        "checks": checks,
    }
