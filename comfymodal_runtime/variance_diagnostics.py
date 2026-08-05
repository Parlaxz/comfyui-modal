"""Flag-gated restore/UNET variance diagnostics.

Two independent gates, both default OFF so production behavior is unchanged:

  COMFYMODAL_V2_VARIANCE_DIAGNOSTICS  (default off)
      Detailed stage metrics: exact wall/monotonic timestamps, process and
      current worker-thread CPU time, minor/major faults, RSS plus
      smaps_rollup when available, /proc/self/io counters when available,
      NUMA data when available, bytes and effective GB/s, effective
      Torch/native thread counts, and a runtime fingerprint.  Records are
      JSON-safe and bounded.  When on, the unique CPU UNET storage registry
      (unique storage count, union bytes/pages) is recorded even when the
      pre-touch gate is off, and an optional CUDA synchronize is issued around
      the timed transfer (only when diagnostics are enabled).

  COMFYMODAL_V2_UNET_PRETOUCH  (default off)
      A diagnostic-only, explicit gated operation that real-reads every page
      of every retained CPU UNET storage range (bounded by a per-page read
      chunk and a page budget) and folds a 64-bit checksum proving the reads
      occurred.  Never uses CUDA sync, never alters production defaults, is
      exception-safe, and reports unsupported/alias/overlap details per entry.

All capture helpers are duck-typed so focused unit tests can run without
CUDA/Modal/torch and can use fake storage/model objects.
"""

from __future__ import annotations

import contextlib
import os
import platform
import time
from collections.abc import Iterator, Mapping
from typing import Any, Callable

from .cpu_snapshot_models import StorageRegistry, build_unique_storage_registry

_VARIANCE_ENV_KEY = "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"
_PRETOUCH_ENV_KEY = "COMFYMODAL_V2_UNET_PRETOUCH"

# Bounds keep every emitted record JSON-safe and bounded regardless of input.
_MAX_NUMA_PAGES_SAMPLED = 100_000
_MAX_IO_PAGE_TOUCHES = 1_000_000_000
_MAX_RECORD_RANGES = 512


def variance_diagnostics_enabled() -> bool:
    """True when ``COMFYMODAL_V2_VARIANCE_DIAGNOSTICS`` is enabled (default off)."""
    return _env_on(_VARIANCE_ENV_KEY)


def unet_pretouch_enabled() -> bool:
    """True when ``COMFYMODAL_V2_UNET_PRETOUCH`` is enabled (default off)."""
    return _env_on(_PRETOUCH_ENV_KEY)


def _env_on(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on")


def cuda_sync_if_enabled() -> bool:
    """Best-effort CUDA ``synchronize``; only when variance diagnostics are on.

    Never initializes CUDA when diagnostics are disabled (default), so the
    production path is unchanged.  Returns ``True`` when a synchronize was
    actually issued.  Never raises (diagnostic-only).
    """
    if not variance_diagnostics_enabled():
        return False
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            return True
    except Exception:
        pass
    return False


def _page_size() -> int:
    try:
        size = os.sysconf("SC_PAGE_SIZE")
        return int(size) if size and int(size) > 0 else 4096
    except Exception:
        return 4096


def _capture_tid() -> int:
    try:
        import threading
        return int(threading.get_native_id())
    except Exception:
        return 0


def _capture_faults() -> dict[str, int | None]:
    try:
        import resource as _r
        ru = _r.getrusage(_r.RUSAGE_SELF)
        return {"major_faults": int(ru.ru_majflt), "minor_faults": int(ru.ru_minflt)}
    except Exception:
        return {"major_faults": None, "minor_faults": None}


def _capture_rss_bytes() -> int | None:
    if not os.path.exists("/proc/self/status"):
        return None
    try:
        with open("/proc/self/status") as _f:
            for _line in _f:
                if _line.startswith("VmRSS:"):
                    return int(_line.split()[1]) * 1024
    except Exception:
        pass
    return None


def _capture_smaps_rollup() -> dict[str, int] | None:
    if not os.path.exists("/proc/self/smaps_rollup"):
        return None
    try:
        result: dict[str, int] = {}
        with open("/proc/self/smaps_rollup") as _f:
            for _line in _f:
                _key, _, _val = _line.strip().partition(":")
                if _key in ("Rss", "Pss", "RssAnon", "RssFile", "RssShmem"):
                    _num = _val.strip().split()
                    if _num:
                        result[_key] = int(_num[0]) * 1024
        return result if result else None
    except Exception:
        return None


def _capture_proc_self_io() -> dict[str, int] | None:
    if not os.path.exists("/proc/self/io"):
        return None
    try:
        result: dict[str, int] = {}
        with open("/proc/self/io") as _f:
            for _line in _f:
                _key, _, _val = _line.strip().partition(":")
                if _key in ("rchar", "wchar", "syscr", "syscw", "read_bytes",
                            "write_bytes", "cancelled_write_bytes"):
                    result[_key] = int(_val.strip())
        return result if result else None
    except Exception:
        return None


def _capture_numa() -> dict[str, Any] | None:
    if not os.path.exists("/proc/self/numa_maps"):
        return None
    try:
        nodes: dict[str, int] = {}
        pages = 0
        with open("/proc/self/numa_maps") as _f:
            for _line in _f:
                for _tok in _line.split()[1:]:
                    if _tok.startswith("N") and "=" in _tok:
                        _node, _, _count = _tok.partition("=")
                        if _count.isdigit():
                            nodes[_node] = nodes.get(_node, 0) + int(_count)
                            pages += 1
                if pages >= _MAX_NUMA_PAGES_SAMPLED:
                    break
        return {"nodes": nodes, "pages_sampled": pages}
    except Exception:
        return None


def _capture_torch_thread_counts() -> dict[str, Any]:
    result: dict[str, Any] = {
        "torch_available": False,
        "torch_intraop_threads": None,
        "torch_interop_threads": None,
    }
    try:
        import torch
        result["torch_available"] = True
        result["torch_intraop_threads"] = int(torch.get_num_threads())
        result["torch_interop_threads"] = int(torch.get_num_interop_threads())
    except Exception:
        pass
    return result


def _capture_native_thread_count() -> int | None:
    if platform.system() == "Linux":
        try:
            with open("/proc/self/status") as _f:
                for _line in _f:
                    if _line.startswith("Threads:"):
                        return int(_line.split()[1])
        except Exception:
            pass
    try:
        import threading
        return len(threading.enumerate())
    except Exception:
        return None


def _runtime_fingerprint() -> dict[str, str]:
    fp: dict[str, str] = {
        "pid": str(os.getpid()),
        "native_tid": str(_capture_tid()),
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
    }
    try:
        import torch
        fp["torch_version"] = str(torch.__version__)
        try:
            fp["cuda_version"] = str(torch.version.cuda or "")
        except Exception:
            fp["cuda_version"] = ""
    except Exception:
        fp["torch_version"] = ""
        fp["cuda_version"] = ""
    return fp


def capture_metric_snapshot() -> dict[str, Any]:
    """Capture one full, JSON-safe variance metric snapshot at a boundary.

    Returns flat scalar fields plus nested, bounded dicts for the
    system-level counters that are unavailable on some platforms (``None``
    means truthfully absent — never invented zeroes).
    """
    return {
        "mono_ns": int(time.monotonic_ns()),
        "wall_unix_ns": int(time.time_ns()),
        "process_cpu_ns": int(time.process_time_ns()) if hasattr(time, "process_time_ns") else None,
        "thread_cpu_ns": int(time.thread_time_ns()) if hasattr(time, "thread_time_ns") else None,
        "native_tid": _capture_tid(),
        "faults": _capture_faults(),
        "rss_bytes": _capture_rss_bytes(),
        "smaps_rollup": _capture_smaps_rollup(),
        "io": _capture_proc_self_io(),
        "numa": _capture_numa(),
        "threads": _capture_torch_thread_counts(),
        "native_thread_count": _capture_native_thread_count(),
        "fingerprint": _runtime_fingerprint(),
    }


def _same_tid(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> bool:
    return bool(
        before and after
        and isinstance(before.get("native_tid"), int)
        and before.get("native_tid") == after.get("native_tid")
    )


def _nonneg(before: Any, after: Any) -> int | None:
    if isinstance(before, int) and isinstance(after, int):
        return max(0, after - before)
    return None


def _subdelta(before: Any, after: Any) -> dict[str, Any]:
    """Merge per-counter deltas from two nested counter dicts."""
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key in before:
        if isinstance(before[key], Mapping) and isinstance(after.get(key), Mapping):
            out[key] = _subdelta(before[key], after[key])
        else:
            delta = _nonneg(before[key], after.get(key))
            if delta is not None:
                out[key] = delta
    return out


def compute_metric_deltas(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    bytes_: int | None = None,
) -> dict[str, Any]:
    """Compute non-negative deltas between two metric snapshots.

    Wall and process-CPU deltas are valid whenever both snapshots exist.
    Thread-bounded deltas (thread CPU, per-thread faults/io) are only valid
    when the native thread id matches, else reported truthfully as ``None``.
    ``effective_gb_per_s`` is derived from ``bytes_`` (raw transfer bytes)
    over the measured wall time.
    """
    result: dict[str, Any] = {}
    if not before or not after:
        return result

    b_mono = before.get("mono_ns")
    a_mono = after.get("mono_ns")
    if isinstance(b_mono, int) and isinstance(a_mono, int):
        wall_ms = round(max(0, a_mono - b_mono) / 1_000_000, 3)
        result["wall_ms"] = wall_ms
    else:
        wall_ms = None

    b_pt = before.get("process_cpu_ns")
    a_pt = after.get("process_cpu_ns")
    if isinstance(b_pt, int) and isinstance(a_pt, int):
        result["process_cpu_ms"] = round(max(0, a_pt - b_pt) / 1_000_000, 3)
    else:
        result["process_cpu_ms"] = None

    if _same_tid(before, after):
        b_tt = before.get("thread_cpu_ns")
        a_tt = after.get("thread_cpu_ns")
        if isinstance(b_tt, int) and isinstance(a_tt, int):
            result["thread_cpu_ms"] = round(max(0, a_tt - b_tt) / 1_000_000, 3)
        else:
            result["thread_cpu_ms"] = None
        result["minor_faults"] = _nonneg(
            (before.get("faults") or {}).get("minor_faults"),
            (after.get("faults") or {}).get("minor_faults"),
        )
        result["major_faults"] = _nonneg(
            (before.get("faults") or {}).get("major_faults"),
            (after.get("faults") or {}).get("major_faults"),
        )
        result["io_deltas"] = _subdelta(before.get("io"), after.get("io"))
    else:
        result["thread_cpu_ms"] = None
        result["minor_faults"] = None
        result["major_faults"] = None
        result["io_deltas"] = None

    b_rss = before.get("rss_bytes")
    a_rss = after.get("rss_bytes")
    if isinstance(b_rss, int) and isinstance(a_rss, int):
        result["rss_delta_bytes"] = max(0, a_rss - b_rss)
    else:
        result["rss_delta_bytes"] = None

    if isinstance(bytes_, int) and bytes_ >= 0:
        result["bytes"] = bytes_
        result["effective_gb_per_s"] = (
            round((bytes_ / 1_000_000_000.0) / (wall_ms / 1000.0), 3)
            if wall_ms and wall_ms > 0 else None
        )
    return result


def _json_safe(value: Any) -> Any:
    """Coerce nested values into plain JSON-safe scalars (bounded)."""
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if value is None:
        return None
    return str(value)


def bounded_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy of *record*, truncating any range list to the bound."""
    safe = _json_safe(dict(record))
    ranges = safe.get("ranges")
    if isinstance(ranges, list) and len(ranges) > _MAX_RECORD_RANGES:
        safe["ranges"] = ranges[:_MAX_RECORD_RANGES]
        safe["ranges_truncated"] = len(ranges) - _MAX_RECORD_RANGES
    return safe


def snapshot_evidence(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Clearly-named before/after snapshot evidence from two metric snapshots.

    Retains the absolute start/end RSS, smaps_rollup, /proc/self/io, NUMA,
    thread-count, and runtime-fingerprint values (not only deltas), plus the
    exact wall/monotonic timestamps already captured.  All fields are
    JSON-safe and bounded.  ``None`` means truthfully absent on that platform.
    """
    b = before or {}
    a = after or {}
    return {
        "before_wall_unix_ns": b.get("wall_unix_ns"),
        "after_wall_unix_ns": a.get("wall_unix_ns"),
        "before_mono_ns": b.get("mono_ns"),
        "after_mono_ns": a.get("mono_ns"),
        "before_rss_bytes": b.get("rss_bytes"),
        "after_rss_bytes": a.get("rss_bytes"),
        "before_smaps_rollup": b.get("smaps_rollup"),
        "after_smaps_rollup": a.get("smaps_rollup"),
        "before_io": b.get("io"),
        "after_io": a.get("io"),
        "before_numa": b.get("numa"),
        "after_numa": a.get("numa"),
        "before_threads": b.get("threads"),
        "after_threads": a.get("threads"),
        "before_native_thread_count": b.get("native_thread_count"),
        "after_native_thread_count": a.get("native_thread_count"),
        "before_fingerprint": b.get("fingerprint"),
        "after_fingerprint": a.get("fingerprint"),
    }


def _merge_evidence(record: dict[str, Any], before: Mapping[str, Any] | None,
                    after: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge clearly-named snapshot evidence into *record* (JSON-safe)."""
    record.update(snapshot_evidence(before, after))
    return bounded_record(record)


def deltas_with_evidence(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    bytes_: int | None = None,
) -> dict[str, Any]:
    """Combine metric deltas with clearly-named before/after snapshot evidence.

    Returns a JSON-safe, bounded dict carrying both the deltas and the
    absolute before/after snapshots so a caller can distinguish sub-stages
    (e.g. CPU page traversal vs GPU transfer) without re-capturing.
    """
    out = compute_metric_deltas(before, after, bytes_=bytes_)
    out.update(snapshot_evidence(before, after))
    return bounded_record(out)


# ── Storage-page traversal / pre-touch (real reads) ──────────────────

_PRETOUCH_READ_CHUNK = 4096  # bytes read per page (bounded real read)
_FNV_PRIME = 1099511628211
_FNV_OFFSET = 0xF000000000000000


def _is_power_of_two(value: int) -> bool:
    return int(value) > 0 and (int(value) & (int(value) - 1)) == 0


def page_size_is_valid(page_size: int | None) -> bool:
    """True when *page_size* is a positive power of two (reject non-PoT)."""
    return isinstance(page_size, int) and _is_power_of_two(page_size)


def fold_checksum(data: bytes, seed: int = _FNV_OFFSET) -> int:
    """FNV-1a fold of *data* into a 64-bit checksum (proves reads happened)."""
    _h = int(seed) & 0xFFFFFFFFFFFFFFFF
    for _b in data:
        _h ^= _b
        _h = (_h * _FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return _h


def _default_page_reader(address: int, length: int) -> bytes:
    """Read *length* bytes from *address* — a real read that proves the page."""
    import ctypes as _ctypes
    _buf = (_ctypes.c_ubyte * int(length)).from_address(int(address))
    return bytes(_buf)


def page_aligned_ranges(registry: StorageRegistry, *, page_size: int | None = None) -> list[tuple[int, int]]:
    """Return ``(start_aligned, page_count)`` for each merged storage range.

    Range start is aligned down and end aligned up so traversal covers whole
    pages, mirroring the mincore/advise helpers in cpu_snapshot_models.  An
    invalid (non-positive or non-power-of-two) page size is represented
    truthfully as an empty result — it is never silently normalized.
    """
    ps = _page_size() if page_size is None else int(page_size)
    if not page_size_is_valid(ps):
        return []
    out: list[tuple[int, int]] = []
    for _r in registry.ranges:
        _start_aligned = _r.address & ~(ps - 1)
        _end = _r.address + _r.length
        _end_aligned = (_end + ps - 1) & ~(ps - 1)
        _pages = (_end_aligned - _start_aligned) // ps
        if _pages > 0:
            out.append((_start_aligned, _pages))
    return out


def read_storage_pages(
    registry: StorageRegistry,
    *,
    reader: Callable[[int, int], Any] | None = None,
    page_size: int | None = None,
    max_pages: int = _MAX_IO_PAGE_TOUCHES,
    read_chunk: int = _PRETOUCH_READ_CHUNK,
) -> dict[str, Any]:
    """Real-read every page of every merged range and fold a checksum.

    Reads up to *read_chunk* bytes per page (bounded real read across pages —
    not one-byte fault-only touches) and accumulates a 64-bit FNV-1a checksum
    proving reads occurred.  A page counts as touched ONLY when a non-empty
    read succeeds; failed reads are counted in ``failed_pages`` (never fatal)
    and are excluded from the checksum/bytes proof.  Returns a JSON-safe dict
    with status, page size, expected/touched/failed page counts, total unique
    bytes, bytes read, page overcoverage, and the checksum.  A non-positive or
    non-power-of-two page size is rejected truthfully
    (``status="invalid_page_size"``, no traversal).  Bounded by *max_pages*
    attempts so a request can never loop without limit.
    """
    ps = _page_size() if page_size is None else int(page_size)
    if not page_size_is_valid(ps):
        return {"status": "invalid_page_size", "page_size": ps,
                "expected_pages": 0, "touched_pages": 0, "failed_pages": 0,
                "total_bytes": 0, "bytes_read": 0,
                "page_overcoverage_bytes": 0, "checksum": None}
    _read = reader if reader is not None else _default_page_reader
    _ranges = page_aligned_ranges(registry, page_size=ps)
    _expected = sum(_p for _, _p in _ranges)
    _total_bytes = int(registry.total_bytes or 0)
    _budget = max(0, int(max_pages))
    _chunk = max(1, int(read_chunk))
    _checksum = _FNV_OFFSET
    _bytes_read = 0
    _touched = 0
    _failed = 0
    for _start, _pages in _ranges:
        for _i in range(_pages):
            if _touched + _failed >= _budget:
                break
            _addr = _start + _i * ps
            _len = min(_chunk, ps)
            try:
                _data = _read(_addr, _len)
            except Exception:
                _failed += 1
                continue
            if _data:
                _checksum = fold_checksum(_data, _checksum)
                _bytes_read += len(_data)
                _touched += 1
            else:
                _failed += 1
        if _touched + _failed >= _budget:
            break
    if _expected == 0:
        _status = "empty"
    elif _touched == _expected:
        _status = "ok"
    elif _touched + _failed >= _budget and _touched + _failed < _expected:
        _status = "bounded"
    elif _touched == 0:
        _status = "failed"
    else:
        _status = "partial"
    return {
        "status": _status,
        "page_size": ps,
        "expected_pages": _expected,
        "touched_pages": _touched,
        "failed_pages": _failed,
        "total_bytes": _total_bytes,
        "bytes_read": _bytes_read,
        "page_overcoverage_bytes": max(0, _expected * ps - _total_bytes),
        "checksum": _checksum if _touched > 0 else None,
    }


def registry_accounting(model_or_registry: Any) -> dict[str, Any]:
    """Return JSON-safe unique-registry accounting WITHOUT performing any reads.

    Builds (or accepts) the ``StorageRegistry`` and reports unique storage
    count, union bytes, alias/overlap/unsupported details, and the expected
    page-aligned page count at the real page size.  Used so diagnostics-on /
    pretouch-off still records the complete unique CPU UNET storage registry
    while the pre-touch itself stays an explicit, separately gated real-read
    operation.  Never raises on unfamiliar entries (they are reported).
    """
    if isinstance(model_or_registry, StorageRegistry):
        _registry = model_or_registry
    else:
        _registry = build_unique_storage_registry(model_or_registry)
    _ps = _page_size()
    _pages = sum(_p for _, _p in page_aligned_ranges(_registry, page_size=_ps))
    return {
        "unique_storage_count": int(_registry.unique_storage_count),
        "raw_byte_count": int(_registry.raw_byte_count),
        "alias_count": int(_registry.alias_count),
        "overlap_count": int(_registry.overlap_count),
        "overlap_bytes": int(_registry.overlap_bytes),
        "unsupported_count": int(_registry.unsupported_count),
        "unsupported_entries": list(_registry.unsupported_entries)[:_MAX_RECORD_RANGES],
        "total_bytes": int(_registry.total_bytes or 0),
        "expected_pages": _pages,
        "page_size": _ps,
    }


def pretouch_unet_storage(model_or_registry: Any) -> dict[str, Any]:
    """Diagnostic-only pre-touch of retained CPU UNET storage ranges.

    Real-reads every page of every merged storage range (bounded by a page
    budget and per-page read chunk) and folds a checksum.  Gated by
    ``COMFYMODAL_V2_UNET_PRETOUCH``.  Never uses CUDA sync, never mutates
    models, is exception-safe, and reports unsupported/alias/overlap details
    per-entry (never run-fatal).  Returns a JSON-safe, bounded record.
    """
    record: dict[str, Any] = {
        "gate": _PRETOUCH_ENV_KEY,
        "status": "pending",
        "page_size": None,
        "unique_storage_count": 0,
        "raw_byte_count": 0,
        "alias_count": 0,
        "overlap_count": 0,
        "overlap_bytes": 0,
        "unsupported_count": 0,
        "unsupported_entries": [],
        "expected_pages": 0,
        "touched_pages": 0,
        "failed_pages": 0,
        "total_pages": 0,
        "total_bytes": 0,
        "bytes_read": 0,
        "bytes": 0,
        "page_overcoverage_bytes": 0,
        "checksum": None,
        "effective_gb_per_s": None,
        "duration_ms": 0.0,
        "error": "",
    }
    before = capture_metric_snapshot()
    _start_mono = time.monotonic_ns()
    try:
        if isinstance(model_or_registry, StorageRegistry):
            registry = model_or_registry
        else:
            registry = build_unique_storage_registry(model_or_registry)
        record.update({
            "unique_storage_count": int(registry.unique_storage_count),
            "raw_byte_count": int(registry.raw_byte_count),
            "alias_count": int(registry.alias_count),
            "overlap_count": int(registry.overlap_count),
            "overlap_bytes": int(registry.overlap_bytes),
            "unsupported_count": int(registry.unsupported_count),
            "unsupported_entries": list(registry.unsupported_entries)[:_MAX_RECORD_RANGES],
        })
        _result = read_storage_pages(registry)
        for _k in ("status", "page_size", "expected_pages", "touched_pages",
                   "failed_pages", "total_bytes", "bytes_read",
                   "page_overcoverage_bytes", "checksum"):
            record[_k] = _result.get(_k)
        # Report-compatible aliases: tools/variance_report.py reads
        # ``total_pages`` and ``bytes`` from the pretouch event.
        record["total_pages"] = record.get("expected_pages")
        record["bytes"] = record.get("bytes_read")
    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        record["duration_ms"] = round((time.monotonic_ns() - _start_mono) / 1_000_000, 3)
    after = capture_metric_snapshot()
    _bytes = int(record.get("bytes_read") or record.get("total_bytes") or 0)
    deltas = compute_metric_deltas(before, after, bytes_=_bytes)
    record.update(deltas)
    return _merge_evidence(record, before, after)


# ── Loader reconciliation math (wall / substage sum / residual / quality) ──

_RECONCILE_OVERLAP = "overlap"
_RECONCILE_GAP = "unmeasured_gap"
_RECONCILE_COMPLETE = "complete"
_RECONCILE_INCOMPLETE = "incomplete"


def reconciliation_fields(
    total_wall_ms: float | None,
    substage_ms: Mapping[str, Any],
    *,
    tolerance_ms: float = 1.0,
) -> dict[str, Any]:
    """Compute loader wall / substage sum / residual / reconciliation quality.

    ``substage_ms`` maps an explicit stage label to a wall-ms value (or
    ``None`` when that stage was not measured).  Returns:
      loader_wall_ms, substage_sum_ms, residual_ms, reconciliation_status.
    ``residual = loader_wall_ms - substage_sum_ms``.  Missing substages or a
    missing total yield ``None`` and ``reconciliation_status="incomplete"``;
    a residual beyond +tolerance yields ``"unmeasured_gap"`` and beyond
    -tolerance ``"overlap"``; otherwise ``"complete"``.  Labels are kept
    truthful — each substage is a non-overlapping, explicitly-named stage.
    """
    _sum: float | None = None
    _all_measured = True
    _parts: list[float] = []
    for _v in substage_ms.values():
        if isinstance(_v, (int, float)) and _v >= 0:
            _parts.append(float(_v))
        else:
            _all_measured = False
    if _parts:
        _sum = round(sum(_parts), 3)
    result: dict[str, Any] = {
        "loader_wall_ms": total_wall_ms,
        "substage_sum_ms": _sum,
        "residual_ms": None,
        "reconciliation_status": _RECONCILE_INCOMPLETE,
    }
    if not isinstance(total_wall_ms, (int, float)) or _sum is None or not _all_measured:
        return result
    _residual = round(float(total_wall_ms) - _sum, 3)
    result["residual_ms"] = _residual
    if _residual < -tolerance_ms:
        result["reconciliation_status"] = _RECONCILE_OVERLAP
    elif _residual > tolerance_ms:
        result["reconciliation_status"] = _RECONCILE_GAP
    else:
        result["reconciliation_status"] = _RECONCILE_COMPLETE
    return result


def timed_transfer_partition(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    bytes_: int | None = None,
    label: str = "cpu_to_gpu_transfer",
) -> dict[str, Any]:
    """Per-stage deltas + before/after evidence for a timed substage.

    Returns a JSON-safe, bounded dict carrying an explicit ``stage`` label so
    substages (page hydration vs synchronized transfer vs bookkeeping) are
    non-overlapping and named, with bytes/effective GB/s when *bytes_* is set.
    """
    out = deltas_with_evidence(before, after, bytes_=bytes_)
    out["stage"] = label
    return out


# ── Stage-variance event helpers ─────────────────────────────────────


def build_stage_variance_record(
    stage: str,
    event: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    bytes_: int | None = None,
) -> dict[str, Any]:
    """Assemble a JSON-safe variance record for one restore/bootstrap stage."""
    record: dict[str, Any] = {
        "stage": stage,
        "event": event,
        "gate": _VARIANCE_ENV_KEY,
        "start_wall_unix_ns": before.get("wall_unix_ns") if before else None,
        "end_wall_unix_ns": after.get("wall_unix_ns") if after else None,
        "start_mono_ns": before.get("mono_ns") if before else None,
        "end_mono_ns": after.get("mono_ns") if after else None,
        "native_tid": after.get("native_tid") if after else None,
        "native_thread_count": after.get("native_thread_count") if after else None,
    }
    record.update(compute_metric_deltas(before, after, bytes_=bytes_))
    if before:
        record["fingerprint"] = before.get("fingerprint")
    if after:
        record["end_threads"] = after.get("threads")
    return _merge_evidence(record, before, after)


def emit_stage_variance(
    trace: Any,
    *,
    stage: str,
    event: str,
    phase: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    bytes_: int | None = None,
) -> None:
    """Emit one ``variance_stage`` event on *trace* when the gate is on."""
    if trace is None or not variance_diagnostics_enabled():
        return
    record = build_stage_variance_record(stage, event, before, after, bytes_=bytes_)
    trace.emit(f"variance_{stage}_{event}", phase=phase, metadata=record)


@contextlib.contextmanager
def variance_stage(
    trace: Any,
    *,
    stage: str,
    phase: str = "restore",
) -> Iterator[None]:
    """Wrap one restore/bootstrap sub-stage with a metric snapshot pair.

    Emits a dedicated variance event only when the variance gate is on.
    When the gate is off this is a pure pass-through (no behavior change).
    """
    if trace is None or not variance_diagnostics_enabled():
        yield
        return
    before = capture_metric_snapshot()
    try:
        yield
    finally:
        after = capture_metric_snapshot()
        try:
            emit_stage_variance(trace, stage=stage, event="end", phase=phase,
                                before=before, after=after)
        except Exception:
            pass


# ── Sampler activation-wait helper (reads existing event boundaries) ──


def _event_mono_ns(trace: Any, name: str) -> int | None:
    for event in trace.events:
        if event.name == name:
            return int(event.monotonic_ns)
    return None


def activation_wait(trace: Any) -> tuple[float | None, str]:
    """Return ``(activation_wait_ms, source)`` from existing trace boundaries.

    Source precedence (first present wins):
      ``early_activation_graph_join``  — join start/end pair (early modes)
      ``demand_to_first_forward``      — ``unet_gpu_demand_start`` →
                                        ``unet_first_cuda_op`` monotonic delta
      ``first_cuda_op_elapsed_ms``     — ``unet_first_cuda_op.metadata.elapsed_ms``
      ``unavailable``                  — none of the above present

    Reads only already-emitted events — never adds CUDA sync or alters sampler
    semantics, and returns ``unavailable`` truthfully when no boundary exists.
    """
    if trace is None:
        return None, "unavailable"
    # 1. Early-activation graph join boundaries.
    _start = _event_mono_ns(trace, "unet_early_activation_graph_join_start")
    _end = _event_mono_ns(trace, "unet_early_activation_graph_join_end")
    if _start is not None and _end is not None and _end >= _start:
        return round((_end - _start) / 1_000_000, 3), "early_activation_graph_join"
    # 2. Demand -> first CUDA op (monotonic delta).
    _demand = _event_mono_ns(trace, "unet_gpu_demand_start")
    _first = _event_mono_ns(trace, "unet_first_cuda_op")
    if _demand is not None and _first is not None and _first >= _demand:
        return round((_first - _demand) / 1_000_000, 3), "demand_to_first_forward"
    # 3. unet_first_cuda_op metadata elapsed_ms (already derived from demand).
    for event in trace.events:
        if event.name == "unet_first_cuda_op":
            _el = event.metadata.get("elapsed_ms")
            if isinstance(_el, (int, float)) and _el >= 0:
                return float(round(_el, 3)), "first_cuda_op_elapsed_ms"
    return None, "unavailable"


def activation_join_wait_ms(trace: Any) -> float | None:
    """Backward-compatible wrapper returning only the activation wait ms.

    Delegates to :func:`activation_wait`; use that when you also need the
    explicit ``activation_wait_source`` label.
    """
    wait, _ = activation_wait(trace)
    return wait


def activation_publication_ms(trace: Any) -> tuple[float | None, str]:
    """Return ``(publication_ms, source)`` for activation-future publication.

    Reads only already-emitted trace boundaries.  Source precedence:
      ``early_activation_completed``  — ``unet_early_activation_scheduled`` →
                                       ``unet_early_activation_completed``
      ``early_activation_after_load`` — ``unet_early_activation_load_end`` →
                                       ``unet_early_activation_completed``
      ``unavailable``                 — none of the above present

    In late (default) mode no early-activation events exist, so this returns
    ``(None, "unavailable")`` truthfully rather than guessing.
    """
    if trace is None:
        return None, "unavailable"
    _done = _event_mono_ns(trace, "unet_early_activation_completed")
    if _done is not None:
        _sched = _event_mono_ns(trace, "unet_early_activation_scheduled")
        if _sched is not None and _done >= _sched:
            return round((_done - _sched) / 1_000_000, 3), "early_activation_completed"
        _load_end = _event_mono_ns(trace, "unet_early_activation_load_end")
        if _load_end is not None and _done >= _load_end:
            return round((_done - _load_end) / 1_000_000, 3), "early_activation_after_load"
    return None, "unavailable"


def emit_sampler_variance(
    trace: Any,
    *,
    node_id: str,
    node_class: str,
    steps: int,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    sampling_duration_ms: float | None,
) -> None:
    """Emit one ``sampler_variance`` event separating activation wait from
    sampling duration.  Reads the activation-join wait from existing trace
    boundaries; no semantic change to the sampler or activation."""
    if trace is None or not variance_diagnostics_enabled():
        return
    _wait_ms, _wait_source = activation_wait(trace)
    record: dict[str, Any] = {
        "stage": "sampler",
        "event": "variance",
        "gate": _VARIANCE_ENV_KEY,
        "node_id": node_id,
        "node_class": node_class,
        "steps": steps,
        "sampling_duration_ms": sampling_duration_ms,
        "activation_wait_ms": _wait_ms,
        "activation_wait_source": _wait_source,
    }
    record.update(compute_metric_deltas(before, after))
    trace.emit("sampler_variance", phase="execution",
               metadata=_merge_evidence(record, before, after))
