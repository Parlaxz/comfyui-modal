"""Diagnostic-only per-thread CPU delta sampler for the UNET transfer A/B.

Reads ``/proc/self/task/*/stat`` (utime/stime jiffies per thread),
``/proc/self/task/*/comm`` (native thread names), ``/proc/self/stat``
(process utime/stime + current processor), ``/proc/self/status`` (native
thread count, CPU/memory affinity lists) and ``/sys/devices/system/node/online``
(NUMA nodes) while the synchronized CPU->GPU transfer is running.

Diagnostic-only: instantiated exclusively by the request-scoped
``COMFYMODAL_V2_UNET_QUIESCED_TRANSFER`` path (default off).  All procfs
reads are best-effort and bounded; on non-Linux hosts or any read failure
the sampler degrades gracefully to "unavailable" values and never raises.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

#: Approximate sample cadence (seconds) — the task protocol samples every ~100 ms.
_DEFAULT_INTERVAL_S = 0.1
#: Upper bound on retained per-interval samples (memory bound; ~12 s transfer
#: at 100 ms cadence produces ~120 samples).
_MAX_INTERVAL_SAMPLES = 500
#: Top-N threads retained per interval sample.
_TOP_THREADS_PER_SAMPLE = 5


def _clk_tck() -> int:
    """Jiffies-per-second clock rate (default 100 when unavailable)."""
    _sysconf = getattr(os, "sysconf", None)
    if callable(_sysconf):
        try:
            _tck = _sysconf("SC_CLK_TCK")
            if isinstance(_tck, (int, float)) and _tck > 0:
                return int(_tck)
        except (AttributeError, OSError, ValueError, TypeError):
            pass
    return 100


def parse_proc_stat(line: str) -> dict[str, Any]:
    """Parse one ``/proc/<pid>/task/<tid>/stat`` line into fields.

    Returns a dict with ``tid``, ``comm``, ``state``, ``utime_jiffies``,
    ``stime_jiffies``, ``processor`` (current CPU, when present) and ``ok``.
    The comm field may contain spaces/parens, so the first field is split at
    the FIRST ``(`` and the name ends at the LAST ``)``.  Never raises;
    returns ``{"ok": False}`` for unparsable lines.
    """
    if not isinstance(line, str) or not line:
        return {"ok": False}
    try:
        _lparen = line.find("(")
        _rparen = line.rfind(")")
        if _lparen < 0 or _rparen <= _lparen:
            return {"ok": False}
        _tid_str = line[:_lparen].strip()
        _comm = line[_lparen + 1:_rparen]
        _rest = line[_rparen + 1:].strip()
        _fields = _rest.split()
        if len(_fields) < 13:
            return {"ok": False}
        # After ``(comm)``, field 3 (state) is index 0 of _fields; utime is
        # field 14 -> index 11; stime field 15 -> index 12; processor is
        # field 39 -> index 36.
        _utime = _fields[11]
        _stime = _fields[12]
        if not (_utime.isdigit() and _stime.isdigit()):
            return {"ok": False}
        _result: dict[str, Any] = {
            "ok": True,
            "tid": int(_tid_str) if _tid_str.isdigit() else None,
            "comm": _comm,
            "state": _fields[0] if _fields else "",
            "utime_jiffies": int(_utime),
            "stime_jiffies": int(_stime),
            "processor": None,
        }
        if len(_fields) > 36 and _fields[36].isdigit():
            _result["processor"] = int(_fields[36])
        return _result
    except Exception:  # noqa: BLE001 - diagnostic helper never raises
        return {"ok": False}


def _read_proc_file(path: str, max_bytes: int = 65536) -> str:
    """Read a small procfs file; returns ``""`` on any failure."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as _fh:
            return _fh.read(max_bytes)
    except (OSError, IOError, ValueError):
        return ""


def _cpu_ms(jiffies_delta: int, clk_tck: int) -> float:
    """Convert a jiffies delta into CPU milliseconds."""
    if clk_tck <= 0:
        return 0.0
    return round(jiffies_delta * 1000.0 / clk_tck, 3)


class ThreadCpuSampler:
    """Best-effort per-thread CPU delta sampler for the current process.

    Samples on an internal daemon thread every ``interval_s`` seconds while
    running.  ``stop()`` returns a bounded summary: per-interval samples
    (top CPU consumers each), per-thread cumulative CPU totals across the
    window, process CPU total, native thread count, affinity and NUMA nodes.
    """

    def __init__(
        self,
        *,
        interval_s: float = _DEFAULT_INTERVAL_S,
        max_interval_samples: int = _MAX_INTERVAL_SAMPLES,
        pid: int | None = None,
    ) -> None:
        self._interval_s = max(0.02, float(interval_s))
        self._max_samples = max(1, int(max_interval_samples))
        self._pid = int(pid) if pid is not None else os.getpid()
        self._clk_tck = _clk_tck()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._samples: list[dict[str, Any]] = []
        self._thread_totals: dict[int, dict[str, Any]] = {}
        self._process_start: dict[str, Any] | None = None
        self._summary: dict[str, Any] | None = None
        self._start_mono_ns: int = 0
        self._end_mono_ns: int = 0

    # ── procfs readers (each best-effort, never raises) ──────────────

    def _task_dir(self) -> str:
        return f"/proc/{self._pid}/task"

    def _read_process_stat(self) -> dict[str, Any]:
        """Process-level utime/stime + current processor from /proc/self/stat."""
        _raw = _read_proc_file(f"/proc/{self._pid}/stat")
        if not _raw:
            _raw = _read_proc_file("/proc/self/stat")
        if not _raw:
            return {}
        try:
            _rparen = _raw.rfind(")")
            _rest = _raw[_rparen + 1:].strip().split()
        except Exception:  # noqa: BLE001
            return {}
        if len(_rest) < 37:
            return {}
        _utime = _rest[11]
        _stime = _rest[12]
        if not (_utime.isdigit() and _stime.isdigit()):
            return {}
        _out: dict[str, Any] = {
            "utime_jiffies": int(_utime),
            "stime_jiffies": int(_stime),
            "processor": None,
        }
        if len(_rest) > 36 and _rest[36].isdigit():
            _out["processor"] = int(_rest[36])
        return _out

    def _read_status(self) -> dict[str, Any]:
        """Native thread count + CPU/memory affinity lists from status."""
        _raw = _read_proc_file(f"/proc/{self._pid}/status")
        if not _raw:
            _raw = _read_proc_file("/proc/self/status")
        _out: dict[str, Any] = {}
        for _line in _raw.splitlines():
            if _line.startswith("Threads:"):
                _v = _line.split(":", 1)[1].strip()
                if _v.isdigit():
                    _out["threads"] = int(_v)
            elif _line.startswith("Cpus_allowed_list:"):
                _out["cpus_allowed"] = _line.split(":", 1)[1].strip()
            elif _line.startswith("Mems_allowed_list:"):
                _out["mems_allowed"] = _line.split(":", 1)[1].strip()
        return _out

    def _read_numa_nodes(self) -> str:
        """Comma/range list of online NUMA nodes, or ``""`` when unavailable."""
        return _read_proc_file("/sys/devices/system/node/online", 4096).strip()

    def _read_threads(self) -> dict[int, dict[str, Any]]:
        """Read every thread's stat + comm; returns {tid: parsed}."""
        _out: dict[int, dict[str, Any]] = {}
        try:
            _tids = [
                _e for _e in os.listdir(self._task_dir())
                if _e.isdigit()
            ]
        except (OSError, IOError):
            return _out
        for _tid_str in _tids:
            try:
                _stat = parse_proc_stat(
                    _read_proc_file(f"{self._task_dir()}/{_tid_str}/stat", 16384)
                )
            except Exception:  # noqa: BLE001
                _stat: dict[str, Any] = {"ok": False}
            if not _stat.get("ok"):
                continue
            _comm = _stat.get("comm", "")
            if not _comm:
                _comm = _read_proc_file(
                    f"{self._task_dir()}/{_tid_str}/comm", 256
                ).strip()
            _stat["comm"] = _comm
            try:
                _out[int(_tid_str)] = _stat
            except (TypeError, ValueError):
                continue
        return _out

    # ── sample loop ──────────────────────────────────────────────────

    def _sample_once(self) -> dict[str, Any]:
        _threads = self._read_threads()
        _proc = self._read_process_stat()
        _status = self._read_status()
        _mono = time.monotonic_ns()
        _wall = int(time.time() * 1_000_000_000)
        _utime_sum = sum(
            int(_t.get("utime_jiffies", 0) or 0) for _t in _threads.values()
        )
        _stime_sum = sum(
            int(_t.get("stime_jiffies", 0) or 0) for _t in _threads.values()
        )
        _sample: dict[str, Any] = {
            "mono_ns": _mono,
            "wall_ns": _wall,
            "process_utime_jiffies": int(_proc.get("utime_jiffies", 0) or 0),
            "process_stime_jiffies": int(_proc.get("stime_jiffies", 0) or 0),
            "thread_utime_jiffies": _utime_sum,
            "thread_stime_jiffies": _stime_sum,
            "native_thread_count": int(_status.get("threads", len(_threads)) or len(_threads)),
            "current_cpu": _proc.get("processor"),
            "cpus_allowed": _status.get("cpus_allowed", ""),
            "mems_allowed": _status.get("mems_allowed", ""),
            "numa_nodes": self._read_numa_nodes(),
            "threads": _threads,
        }
        return _sample

    def _loop(self) -> None:
        _prev: dict[str, Any] | None = None
        while not self._stop.is_set():
            try:
                _sample = self._sample_once()
            except Exception:  # noqa: BLE001
                _sample = None
            if _sample is not None:
                with self._lock:
                    if _prev is not None:
                        self._accumulate(_prev, _sample)
                        self._samples.append(self._interval_record(_prev, _sample))
                    else:
                        self._samples.append(self._interval_record(None, _sample))
                    if len(self._samples) > self._max_samples:
                        # Bound memory: keep the most recent samples.
                        del self._samples[:-self._max_samples]
                _prev = _sample
            self._stop.wait(self._interval_s)

    def _accumulate(self, prev: dict[str, Any], cur: dict[str, Any]) -> None:
        """Accumulate per-thread CPU deltas between two samples."""
        _prev_threads = prev.get("threads", {}) or {}
        _cur_threads = cur.get("threads", {}) or {}
        for _tid, _cur_t in _cur_threads.items():
            _prev_t = _prev_threads.get(_tid)
            if not isinstance(_prev_t, dict):
                continue
            _dut = int(_cur_t.get("utime_jiffies", 0) or 0) - int(
                _prev_t.get("utime_jiffies", 0) or 0
            )
            _dst = int(_cur_t.get("stime_jiffies", 0) or 0) - int(
                _prev_t.get("stime_jiffies", 0) or 0
            )
            if _dut < 0 or _dst < 0:
                continue  # thread restarted / jiffies wrapped; skip the delta
            _entry = self._thread_totals.setdefault(
                _tid,
                {"tid": _tid, "comm": _cur_t.get("comm", ""),
                 "cpu_ms": 0.0, "samples_active": 0},
            )
            if _dut + _dst > 0:
                _entry["cpu_ms"] += _cpu_ms(_dut + _dst, self._clk_tck)
                _entry["samples_active"] += 1
            if _cur_t.get("comm"):
                _entry["comm"] = _cur_t.get("comm", "")

    def _interval_record(self, prev: Optional[dict[str, Any]], cur: dict[str, Any]) -> dict[str, Any]:
        """Compact per-interval record: process delta + top CPU consumers."""
        _rec: dict[str, Any] = {
            "mono_ns": cur.get("mono_ns"),
            "wall_ns": cur.get("wall_ns"),
            "native_thread_count": cur.get("native_thread_count"),
            "current_cpu": cur.get("current_cpu"),
            "cpus_allowed": cur.get("cpus_allowed", ""),
            "numa_nodes": cur.get("numa_nodes", ""),
        }
        _proc_delta_ms: float | None = None
        _thread_delta_ms: float | None = None
        if isinstance(prev, dict):
            _dut = int(cur.get("process_utime_jiffies", 0) or 0) - int(
                prev.get("process_utime_jiffies", 0) or 0
            )
            _dst = int(cur.get("process_stime_jiffies", 0) or 0) - int(
                prev.get("process_stime_jiffies", 0) or 0
            )
            if _dut >= 0 and _dst >= 0:
                _proc_delta_ms = _cpu_ms(_dut + _dst, self._clk_tck)
            _tdut = int(cur.get("thread_utime_jiffies", 0) or 0) - int(
                prev.get("thread_utime_jiffies", 0) or 0
            )
            _tdst = int(cur.get("thread_stime_jiffies", 0) or 0) - int(
                prev.get("thread_stime_jiffies", 0) or 0
            )
            if _tdut >= 0 and _tdst >= 0:
                _thread_delta_ms = _cpu_ms(_tdut + _tdst, self._clk_tck)
        if _proc_delta_ms is not None:
            _rec["process_cpu_delta_ms"] = _proc_delta_ms
        if _thread_delta_ms is not None:
            _rec["thread_cpu_delta_ms"] = _thread_delta_ms
        _top = sorted(
            self._thread_totals.values(), key=lambda e: e.get("cpu_ms", 0.0),
            reverse=True,
        )[:_TOP_THREADS_PER_SAMPLE]
        _rec["top_threads"] = [
            {
                "tid": _t.get("tid"),
                "comm": _t.get("comm", ""),
                "cpu_ms": round(float(_t.get("cpu_ms", 0.0)), 3),
                # Current CPU of that specific thread (from its own
                # /proc/self/task/<tid>/stat field 39), when readable.
                "current_cpu": (
                    (cur.get("threads") or {}).get(_t.get("tid"), {}).get("processor")
                    if isinstance(cur.get("threads"), dict) else None
                ),
            }
            for _t in _top
        ]
        return _rec

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the sampling thread (idempotent)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._start_mono_ns = time.monotonic_ns()
            self._samples.clear()
            self._thread_totals.clear()
            self._process_start = None
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="v2-thread-cpu-sampler", daemon=True,
            )
            self._thread.start()

    def stop(self, *, transfer_duration_ms: float | None = None,
             transfer_bytes: int | None = None) -> dict[str, Any]:
        """Stop sampling and return the bounded summary.

        ``transfer_duration_ms``/``transfer_bytes`` (optional) are folded into
        the summary for the A/B report (synchronized transfer wall + bytes).
        """
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(2.0, self._interval_s * 3))
        with self._lock:
            self._end_mono_ns = time.monotonic_ns()
            _samples = list(self._samples)
            _totals = sorted(
                self._thread_totals.values(), key=lambda e: e.get("cpu_ms", 0.0),
                reverse=True,
            )
            _proc_delta_ms = None
            _thread_delta_ms = None
            if len(_samples) >= 2:
                _first = _samples[0]
                _last = _samples[-1]
                if _first.get("process_cpu_delta_ms") is not None:
                    _proc_delta_ms = round(
                        sum(float(s.get("process_cpu_delta_ms", 0.0) or 0.0)
                            for s in _samples[1:]), 3,
                    )
                if _first.get("thread_cpu_delta_ms") is not None:
                    _thread_delta_ms = round(
                        sum(float(s.get("thread_cpu_delta_ms", 0.0) or 0.0)
                            for s in _samples[1:]), 3,
                    )
            _summary: dict[str, Any] = {
                "duration_ms": round((self._end_mono_ns - self._start_mono_ns) / 1_000_000, 3),
                "sample_count": len(_samples),
                "interval_s": self._interval_s,
                "process_cpu_ms": _proc_delta_ms,
                "thread_cpu_ms": _thread_delta_ms,
                "native_thread_count": (
                    max(int(s.get("native_thread_count", 0) or 0) for s in _samples)
                    if _samples else None
                ),
                "affinity_cpus_allowed": (
                    next((s.get("cpus_allowed", "") for s in reversed(_samples) if s.get("cpus_allowed")), "") or ""
                ),
                "numa_nodes": (
                    next((s.get("numa_nodes", "") for s in reversed(_samples) if s.get("numa_nodes")), "") or ""
                ),
                "current_cpu": (
                    next((s.get("current_cpu") for s in reversed(_samples) if s.get("current_cpu") is not None), None)
                ),
                # Distinct CPUs observed across the window (from per-thread
                # stat field 39 of the sampled top threads), best-effort.
                "cpus_seen": sorted({
                    _cpu_v
                    for _s in _samples
                    for _tt in (_s.get("top_threads") or [])
                    for _cpu_v in ([(int(_tt["current_cpu"]))]
                                   if isinstance(_tt, dict)
                                   and isinstance(_tt.get("current_cpu"), (int, float))
                                   else [])
                }) or None,
                "per_thread_totals": [
                    {"tid": _t.get("tid"), "comm": _t.get("comm", ""),
                     "cpu_ms": round(float(_t.get("cpu_ms", 0.0)), 3),
                     "samples_active": int(_t.get("samples_active", 0))}
                    for _t in _totals
                ],
                "per_interval_samples": _samples,
            }
            if transfer_duration_ms is not None:
                _summary["transfer_duration_ms"] = round(float(transfer_duration_ms), 3)
            if transfer_bytes is not None:
                _summary["transfer_bytes"] = int(transfer_bytes)
                if transfer_duration_ms:
                    _summary["effective_gb_per_s"] = round(
                        (int(transfer_bytes) / 1_000_000_000.0)
                        / (float(transfer_duration_ms) / 1000.0), 3,
                    )
            self._summary = _summary
            return dict(_summary)
