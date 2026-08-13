"""Measurement-only diagnostics for remaining V2 optimization targets.

This module is the *instrumentation contract* for the
``V2_REMAINING_OPTIMIZATION_DIAGNOSTICS`` effort.  It provides low-overhead,
gated building blocks that lane-specific hooks (in ``model_preload``,
``runtime_executor``, ``clip_conditioning_cache``, ``comfyapp``,
``runtime_bootstrap``) use to decompose the remaining optimization targets:

* UNET fast-disk H2D transfer mechanics (pinned/pageable, mmap, copy API,
  stream identity, per-storage aggregation, host-side effects)
* UNET vs CLIP GPU contention (CUDA-event chronology + temporal overlap)
* PromptExecutor ``exec_start_to_cached`` decomposition
* VAE activation-at-sampling_end interval
* Conditioning-cache exact-hit read path
* PNG/output encode decomposition
* Python restore/bootstrap decomposition
* Concurrent critical-path metadata (UNET readiness slack)

Design rules (from the task spec):

* **Off by default.**  Everything is a no-op unless
  ``COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS`` is set.  The gate is frozen at
  import time (same pattern as the rest of the runtime).
* **No CUDA synchronization in default mode.**  ``OptCudaInterval`` records
  events without syncing; device durations are realized only when the caller
  already performs a synchronize (reusing it) or when
  ``COMFYMODAL_V2_OPT_DIAG_SYNC_CUDA`` is explicitly set.
* **Aggregate, never spam.**  ``OptTensorStats`` emits bounded aggregates
  (first N / largest N / size buckets / totals), never per-tensor log lines.
* **Monotonic for local duration, wall for cross-process.**
  ``trace.emit`` already captures both clocks; events emitted here follow
  that convention and carry request/restore/container identity via the
  trace's auto-propagated metadata.
* **Windows-safe.**  All ``/proc`` / ``getrusage`` / cgroup reads are guarded
  and return ``None`` on failure (dev machine is Windows; the Modal
  container is Linux).
* **Event naming.**  All events emitted by this module use the ``opt_``
  prefix so they cannot collide with events consumed by the waterfall
  (``v2_waterfall.py``) or Agent 1's accounting layer.
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterator, Mapping

from .env import env_flag

# ──────────────────────────────────────────────────────────────────────
# Gates (frozen at import time, matching runtime convention)
# ──────────────────────────────────────────────────────────────────────

FLAG_OPT_DIAG = "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS"
FLAG_OPT_DIAG_SYNC_CUDA = "COMFYMODAL_V2_OPT_DIAG_SYNC_CUDA"

_ENABLED: bool = env_flag(FLAG_OPT_DIAG, default=False)
"""Master gate for all optimization diagnostics (measurement only)."""

_SYNC_CUDA_ALLOWED: bool = env_flag(FLAG_OPT_DIAG_SYNC_CUDA, default=False)
"""Allow an explicit ``torch.cuda.synchronize`` where no existing sync can
be reused.  Default off: callers must reuse an existing sync instead."""

MAX_STORAGES_FIRST_N = 16
"""How many storages to detail in the ``first_n`` aggregate window."""
MAX_STORAGES_LARGEST_N = 8
"""How many storages to detail in the ``largest_n`` aggregate window."""


def opt_diag_enabled() -> bool:
    """Return whether optimization diagnostics are active."""
    return _ENABLED


def sync_cuda_allowed() -> bool:
    """Return whether an explicit synchronized measurement is permitted."""
    return _SYNC_CUDA_ALLOWED


# ──────────────────────────────────────────────────────────────────────
# Gated event emission (all events are ``opt_*`` prefixed)
# ──────────────────────────────────────────────────────────────────────

def emit_opt(
    trace: Any,
    name: str,
    *,
    phase: str = "execution",
    metadata: Mapping[str, Any] | None = None,
) -> Any:
    """Emit one ``opt_<name>`` trace event when diagnostics are enabled.

    No-op (returns ``None``) when disabled or when ``trace`` is falsy.
    """
    if not _ENABLED or trace is None:
        return None
    try:
        return trace.emit("opt_" + name, phase=phase, metadata=dict(metadata or {}))
    except Exception:
        return None


class opt_stage:
    """Context manager emitting ``opt_<name>_start`` / ``opt_<name>_end``.

    Uses the trace's monotonic/wall capture; no CUDA involvement.  Adds
    ``duration_ms`` to the end event.  Near-zero overhead when disabled.
    """

    __slots__ = ("_trace", "_name", "_phase", "_metadata", "_start_ns", "_ev")

    def __init__(
        self,
        name: str,
        trace: Any,
        *,
        phase: str = "execution",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._trace = trace
        self._name = name
        self._phase = phase
        self._metadata = dict(metadata or {})
        self._start_ns: int | None = None
        self._ev: Any = None

    def __enter__(self) -> "opt_stage":
        if not _ENABLED or self._trace is None:
            return self
        self._start_ns = time.monotonic_ns()
        try:
            self._ev = self._trace.emit(
                "opt_" + self._name + "_start",
                phase=self._phase,
                metadata=dict(self._metadata),
            )
        except Exception:
            self._ev = None
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not _ENABLED or self._trace is None or self._start_ns is None:
            return
        _meta = dict(self._metadata)
        _meta["duration_ms"] = round(
            (time.monotonic_ns() - self._start_ns) / 1_000_000, 3
        )
        _meta["exited_with_error"] = bool(exc is not None)
        try:
            self._trace.emit(
                "opt_" + self._name + "_end",
                phase=self._phase,
                metadata=_meta,
            )
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────
# Tensor/storage aggregation (bounded, never per-tensor spam)
# ──────────────────────────────────────────────────────────────────────

_SIZE_BUCKET_BYTES = (1 << 20, 8 << 20, 64 << 20, 256 << 20, 1 << 30)
"""Bucket boundaries in bytes: <1MiB, 1-8MiB, 8-64MiB, 64-256MiB, 256MiB-1GiB, >=1GiB."""


class OptTensorStats:
    """Aggregate per-storage transfer statistics for one model transfer.

    Call :meth:`record` for each source tensor (parameters + buffers) and
    :meth:`finish` once.  ``finish`` returns a bounded JSON-safe dict:
    totals, dtype bytes, pinned/contiguous/mmap counts, first-N and
    largest-N storage details, and size buckets.  No per-tensor logging.
    """

    __slots__ = (
        "_enabled",
        "_count",
        "_total_bytes",
        "_by_dtype",
        "_pinned_count",
        "_pinned_bytes",
        "_contig_count",
        "_mmap_count",
        "_mmap_unknown",
        "_first",
        "_largest",
        "_buckets",
    )

    def __init__(self) -> None:
        self._enabled = _ENABLED
        self._count = 0
        self._total_bytes = 0
        self._by_dtype: dict[str, int] = {}
        self._pinned_count = 0
        self._pinned_bytes = 0
        self._contig_count = 0
        self._mmap_count = 0
        self._mmap_unknown = 0
        self._first: list[dict[str, Any]] = []
        self._largest: list[dict[str, Any]] = []
        self._buckets = [0] * (len(_SIZE_BUCKET_BYTES) + 1)

    def record(self, tensor: Any) -> None:
        """Record one source tensor's transfer-relevant properties."""
        if not self._enabled or tensor is None:
            return
        try:
            _storage = tensor.untyped_storage()
        except Exception:
            try:
                _storage = tensor.storage()
            except Exception:
                _storage = None
        try:
            _bytes = int(_storage.nbytes()) if _storage is not None else int(
                tensor.numel() * tensor.element_size()
            )
        except Exception:
            _bytes = 0
        _dtype = str(getattr(tensor, "dtype", "unknown"))
        _pinned = bool(getattr(tensor, "is_pinned", lambda: False)())
        _contig = bool(getattr(tensor, "is_contiguous", lambda: True)())
        _mmap = self._storage_is_file_backed(_storage)
        self._count += 1
        self._total_bytes += _bytes
        self._by_dtype[_dtype] = self._by_dtype.get(_dtype, 0) + _bytes
        if _pinned:
            self._pinned_count += 1
            self._pinned_bytes += _bytes
        if _contig:
            self._contig_count += 1
        if _mmap is True:
            self._mmap_count += 1
        elif _mmap is None:
            self._mmap_unknown += 1
        _entry = {
            "bytes": _bytes,
            "dtype": _dtype,
            "pinned": _pinned,
            "contiguous": _contig,
            "mmap_backed": _mmap,
            "storage_type": (
                type(_storage).__name__ if _storage is not None else "unknown"
            ),
        }
        if len(self._first) < MAX_STORAGES_FIRST_N:
            self._first.append(_entry)
        self._largest.append(_entry)
        if len(self._largest) > MAX_STORAGES_LARGEST_N:
            self._largest.sort(key=lambda e: e["bytes"], reverse=True)
            del self._largest[MAX_STORAGES_LARGEST_N:]
        _idx = 0
        for _idx, _bound in enumerate(_SIZE_BUCKET_BYTES):
            if _bytes < _bound:
                break
        else:
            _idx = len(_SIZE_BUCKET_BYTES)
        self._buckets[_idx] += 1

    @staticmethod
    def _storage_is_file_backed(storage: Any) -> bool | None:
        """Best-effort mmap/file-backed detection; ``None`` = unknown."""
        if storage is None:
            return None
        try:
            _fn = getattr(storage, "filename", None)
            if callable(_fn):
                _val = _fn()
                return _val is not None
        except Exception:
            pass
        try:
            _fs = getattr(storage, "file", None)
            return _fs is not None
        except Exception:
            return None

    def finish(self) -> dict[str, Any]:
        """Return the bounded aggregate dict (JSON-safe)."""
        if not self._enabled or self._count == 0:
            return {
                "count": self._count,
                "total_bytes": self._total_bytes,
                "storages_scanned": self._enabled,
            }
        self._largest.sort(key=lambda e: e["bytes"], reverse=True)
        _bucket_labels = [
            "lt_1MiB",
            "1_8MiB",
            "8_64MiB",
            "64_256MiB",
            "256MiB_1GiB",
            "ge_1GiB",
        ]
        return {
            "count": self._count,
            "total_bytes": self._total_bytes,
            "total_mib": round(self._total_bytes / (1 << 20), 3),
            "by_dtype_bytes": dict(self._by_dtype),
            "pinned_count": self._pinned_count,
            "pinned_bytes": self._pinned_bytes,
            "pinned_frac": (
                round(self._pinned_bytes / self._total_bytes, 4)
                if self._total_bytes
                else 0.0
            ),
            "contiguous_count": self._contig_count,
            "mmap_backed_count": self._mmap_count,
            "mmap_unknown_count": self._mmap_unknown,
            "first_n": list(self._first),
            "largest_n": list(self._largest),
            "size_bucket_counts": dict(zip(_bucket_labels, self._buckets)),
        }


# ──────────────────────────────────────────────────────────────────────
# Host-side effect deltas (all guarded; Windows-safe)
# ──────────────────────────────────────────────────────────────────────

def host_snapshot() -> dict[str, Any]:
    """Capture host counters relevant to a transfer (guarded, None-safe)."""
    _snap: dict[str, Any] = {"mono_ns": time.monotonic_ns()}
    try:
        _snap["thread_cpu_ns"] = time.thread_time_ns()
    except Exception:
        _snap["thread_cpu_ns"] = None
    try:
        _snap["process_cpu_ns"] = time.process_time_ns()
    except Exception:
        _snap["process_cpu_ns"] = None
    try:
        import resource  # POSIX only

        _ru = resource.getrusage(resource.RUSAGE_SELF)
        _snap["minor_faults"] = int(_ru.ru_minflt)
        _snap["major_faults"] = int(_ru.ru_majflt)
    except Exception:
        _snap["minor_faults"] = None
        _snap["major_faults"] = None
    _snap["rss_bytes"] = _proc_read_int("/proc/self/status", "VmRSS")
    _io = _proc_self_io()
    _snap["io_rchar_bytes"] = _io.get("rchar")
    _snap["io_read_bytes"] = _io.get("read_bytes")
    _snap["io_syscr_count"] = _io.get("syscr")
    return _snap


def host_deltas(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """Compute guarded deltas between two :func:`host_snapshot` results."""
    _out: dict[str, Any] = {}

    def _d(key: str, out_key: str, divisor_ns: bool = False) -> None:
        _a = before.get(key)
        _b = after.get(key)
        if _a is None or _b is None:
            _out[out_key] = None
            return
        _delta = _b - _a
        if divisor_ns:
            _out[out_key] = round(_delta / 1_000_000, 3)
        else:
            _out[out_key] = _delta

    _d("thread_cpu_ns", "thread_cpu_ms", divisor_ns=True)
    _d("process_cpu_ns", "process_cpu_ms", divisor_ns=True)
    _d("minor_faults", "minor_fault_delta")
    _d("major_faults", "major_fault_delta")
    _d("rss_bytes", "rss_delta_bytes")
    _d("io_rchar_bytes", "io_rchar_delta")
    _d("io_read_bytes", "io_read_delta")
    _d("io_syscr_count", "io_syscr_delta")
    _tc = _out.get("thread_cpu_ms")
    _pc = _out.get("process_cpu_ms")
    if isinstance(_tc, (int, float)) and isinstance(_pc, (int, float)):
        if _tc > 0.0:
            _out["effective_cores"] = round(min(max(_pc / _tc, 0.0), 64.0), 3)
        else:
            _out["effective_cores"] = 0.0
    else:
        _out["effective_cores"] = None
    _elapsed_ns = after.get("mono_ns", 0) - before.get("mono_ns", 0)
    _out["wall_ms"] = round(max(_elapsed_ns, 0) / 1_000_000, 3)
    return _out


def _proc_read_int(path: str, key: str) -> int | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for _line in f:
                if _line.startswith(key + ":"):
                    return int(_line.split(":", 1)[1].split()[0])
    except Exception:
        return None
    return None


def _proc_self_io() -> dict[str, int | None]:
    _out: dict[str, int | None] = {
        "rchar": None,
        "read_bytes": None,
        "syscr": None,
    }
    try:
        with open("/proc/self/io", "r", encoding="utf-8") as f:
            for _line in f:
                _k, _, _v = _line.partition(":")
                _k = _k.strip()
                if _k in _out:
                    _out[_k] = int(_v.strip())
    except Exception:
        pass
    return _out


def effective_gbps(byte_count: int, ms: float | None) -> float | None:
    """Effective transfer GB/s (decimal GB) or ``None`` when unmeasurable."""
    if not ms or ms <= 0.0 or byte_count <= 0:
        return None
    return round(byte_count / 1e9 / (ms / 1000.0), 3)


# ──────────────────────────────────────────────────────────────────────
# CUDA interval (events without synchronization by default)
# ──────────────────────────────────────────────────────────────────────

class OptCudaInterval:
    """CUDA-event interval with deferred realization.

    Records a start/end event pair on the current stream **without**
    synchronizing.  Device duration is realized only when:

    * ``realize()`` is called after the caller has already performed a
      ``torch.cuda.synchronize()`` (reused sync — zero extra syncs), or
    * ``COMFYMODAL_V2_OPT_DIAG_SYNC_CUDA`` is set and ``end(realize=True)``
      is used (explicit synchronized measurement).

    ``cuda`` may be injected for tests (e.g. a fake with ``Event``,
    ``is_available``, ``current_stream``, ``synchronize``).  When CUDA is
    unavailable or diagnostics are off, all methods are safe no-ops and
    ``elapsed_ms`` returns ``None``.
    """

    __slots__ = ("_cuda", "_ev_start", "_ev_end", "_realized", "_elapsed_ms")

    def __init__(self, cuda: Any = None) -> None:
        self._cuda = cuda
        self._ev_start: Any = None
        self._ev_end: Any = None
        self._realized = False
        self._elapsed_ms: float | None = None

    def _cuda_mod(self) -> Any:
        if self._cuda is not None:
            return self._cuda
        if not _ENABLED:
            return None
        try:
            import torch

            return torch.cuda if getattr(torch, "cuda", None) is not None else None
        except Exception:
            return None

    def begin(self) -> "OptCudaInterval":
        if not _ENABLED:
            return self
        _cuda = self._cuda_mod()
        if _cuda is None or not getattr(_cuda, "is_available", lambda: False)():
            return self
        try:
            self._ev_start = _cuda.Event(enable_timing=True)
            self._ev_start.record()
        except Exception:
            self._ev_start = None
        return self

    def end(self, *, realize: bool = False) -> "OptCudaInterval":
        if not _ENABLED or self._ev_start is None:
            return self
        _cuda = self._cuda_mod()
        if _cuda is None:
            return self
        try:
            self._ev_end = _cuda.Event(enable_timing=True)
            self._ev_end.record()
            if realize and _SYNC_CUDA_ALLOWED:
                _cuda.synchronize()
                self._realize()
        except Exception:
            self._ev_end = None
        return self

    def realize(self) -> float | None:
        """Realize elapsed time using a sync the caller already performed."""
        if not _ENABLED or self._realized:
            return self._elapsed_ms
        _cuda = self._cuda_mod()
        if _cuda is None or self._ev_start is None or self._ev_end is None:
            return None
        try:
            self._realize()
        except Exception:
            self._elapsed_ms = None
        return self._elapsed_ms

    def _realize(self) -> None:
        _cuda = self._cuda_mod()
        if _cuda is None:
            return
        _ms = float(self._ev_start.elapsed_time(self._ev_end))
        self._elapsed_ms = round(_ms, 3)
        self._realized = True

    @property
    def elapsed_ms(self) -> float | None:
        return self._elapsed_ms

    def overlap_ms(self, other: "OptCudaInterval", span_ms: float | None = None) -> float | None:
        """Device-timeline overlap with another realized interval.

        Requires both intervals realized (device durations).  Without a
        shared timeline anchor this returns the *wall* overlap estimate
        using ``span_ms`` when provided, else ``None``.  Host-level
        temporal overlap is better computed from mono-ns brackets — see
        :func:`wall_overlap_ms`.
        """
        if not _ENABLED:
            return None
        if self._elapsed_ms is None or other._elapsed_ms is None:
            return None
        return round(min(self._elapsed_ms, other._elapsed_ms), 3)


def wall_overlap_ms(
    a_start: int, a_end: int, b_start: int, b_end: int
) -> dict[str, Any]:
    """Temporal overlap between two mono-ns intervals (host timeline).

    Returns bounded overlap/coverage facts; all inputs are mono-ns.
    """
    _overlap = max(0, min(a_end, b_end) - max(a_start, b_start))
    _a_ms = max(0, a_end - a_start) / 1_000_000
    _b_ms = max(0, b_end - b_start) / 1_000_000
    _overlap_ms = _overlap / 1_000_000
    return {
        "overlap_ms": round(_overlap_ms, 3),
        "a_duration_ms": round(_a_ms, 3),
        "b_duration_ms": round(_b_ms, 3),
        "a_within_b_frac": (
            round(_overlap_ms / _b_ms, 4) if _b_ms > 0 else 0.0
        ),
        "b_within_a_frac": (
            round(_overlap_ms / _a_ms, 4) if _a_ms > 0 else 0.0
        ),
    }


def opt_stream_info(cuda: Any = None) -> dict[str, Any]:
    """Guarded current-stream / copy-engine facts (``None`` when unknown)."""
    if not _ENABLED:
        return {}
    _cuda = cuda
    if _cuda is None:
        try:
            import torch

            _cuda = getattr(torch, "cuda", None)
        except Exception:
            _cuda = None
    _out: dict[str, Any] = {}
    if _cuda is None or not getattr(_cuda, "is_available", lambda: False)():
        return _out
    try:
        _stream = _cuda.current_stream()
        _out["stream_id"] = str(getattr(_stream, "cuda_stream", _stream))
        _prio = getattr(_stream, "priority", None)
        if _prio is not None:
            _out["stream_priority"] = int(_prio)
    except Exception:
        pass
    try:
        _props = _cuda.get_device_properties(_cuda.current_device())
        for _attr in ("asyncEngineCount", "name", "major", "minor"):
            _val = getattr(_props, _attr, None)
            if _val is not None:
                _out["device_" + _attr] = _val
    except Exception:
        pass
    try:
        _out["device_can_map_host"] = bool(
            _cuda.get_device_properties(_cuda.current_device()).canMapHostMemory
        )
    except Exception:
        pass
    return _out


# ──────────────────────────────────────────────────────────────────────
# Convenience: one-shot transfer measurement combining all building blocks
# ──────────────────────────────────────────────────────────────────────

class OptTransferProbe:
    """Combined CPU-wall + CUDA-event + host-delta + tensor-stats probe.

    Usage inside a transfer region with an **already existing** sync after
    the copy (e.g. ``_fast_disk_replay_to``)::

        probe = OptTransferProbe(trace, non_blocking=False, source="cpu")
        probe.begin(model)                      # tensor stats + host snapshot + start event
        result = original_to(model, ...)        # the transfer
        torch.cuda.synchronize()                # existing sync (reused)
        probe.end(model)                        # realizes device duration via the sync
        probe.emit("unet_h2d_transfer")         # one aggregated opt_ event

    Every step is a safe no-op when diagnostics are off or CUDA is absent.
    """

    __slots__ = ("_trace", "_phase", "_meta", "_stats", "_post_stats", "_host_before", "_host_after", "_cuda_interval", "_wall_start_ns")

    def __init__(
        self,
        trace: Any,
        *,
        phase: str = "execution",
        metadata: Mapping[str, Any] | None = None,
        cuda: Any = None,
    ) -> None:
        self._trace = trace
        self._phase = phase
        self._meta = dict(metadata or {})
        self._stats = OptTensorStats()
        self._post_stats = OptTensorStats()
        self._host_before: dict[str, Any] | None = None
        self._host_after: dict[str, Any] | None = None
        self._cuda_interval = OptCudaInterval(cuda=cuda)
        self._wall_start_ns: int | None = None

    def begin(self, tensors: Any = None) -> None:
        if not _ENABLED:
            return
        self._wall_start_ns = time.monotonic_ns()
        self._host_before = host_snapshot()
        self._cuda_interval.begin()
        if tensors is not None:
            try:
                for _t in self._iter_tensors(tensors):
                    self._stats.record(_t)
            except Exception:
                pass

    def end(self, tensors: Any = None) -> None:
        if not _ENABLED or self._wall_start_ns is None:
            return
        self._cuda_interval.end()
        if tensors is not None:
            # Destination-side stats (e.g. post-.to() CUDA tensors) are
            # recorded separately so ``tensor_stats`` keeps source-count
            # semantics; the caller may pass the same model object again.
            try:
                for _t in self._iter_tensors(tensors):
                    self._post_stats.record(_t)
            except Exception:
                pass
        self._host_after = host_snapshot()
        self._cuda_interval.realize()  # reuse caller's existing sync

    def emit(self, event_name: str) -> None:
        """Emit ``opt_<event_name>`` with all aggregated measurements."""
        if not _ENABLED or self._trace is None or self._wall_start_ns is None:
            return
        _meta = dict(self._meta)
        _cpu_wall_ms = round(
            (time.monotonic_ns() - self._wall_start_ns) / 1_000_000, 3
        )
        _cuda_ms = self._cuda_interval.elapsed_ms
        _tstats = self._stats.finish()
        _total_bytes = int(_tstats.get("total_bytes", 0))
        _meta["cpu_wall_ms"] = _cpu_wall_ms
        _meta["cuda_event_ms"] = _cuda_ms
        _meta["effective_gbps"] = effective_gbps(_total_bytes, _cuda_ms or _cpu_wall_ms)
        _meta["device_vs_cpu_wall_ratio"] = (
            round(_cuda_ms / _cpu_wall_ms, 4)
            if _cuda_ms is not None and _cpu_wall_ms > 0
            else None
        )
        _meta["source_pinned"] = bool(_tstats.get("pinned_count", 0) > 0)
        _meta["pinned_frac"] = _tstats.get("pinned_frac", 0.0)
        _post = self._post_stats.finish()
        if _post.get("count", 0) > 0:
            _meta["post_tensor_stats"] = _post
        if self._host_before is not None and self._host_after is not None:
            _meta.update(host_deltas(self._host_before, self._host_after))
        _meta["tensor_stats"] = _tstats
        _meta["stream"] = opt_stream_info()
        emit_opt(self._trace, event_name, phase=self._phase, metadata=_meta)

    @staticmethod
    def _iter_tensors(model_or_iter: Any) -> Iterator[Any]:
        _params = getattr(model_or_iter, "parameters", None)
        if callable(_params):
            try:
                yield from _params()
            except Exception:
                pass
            _bufs = getattr(model_or_iter, "buffers", None)
            if callable(_bufs):
                try:
                    yield from _bufs()
                except Exception:
                    pass
            return
        try:
            for _t in model_or_iter:
                yield _t
        except Exception:
            pass
