"""Lightweight 50 ms cgroup-wide CPU/RAM telemetry for resource experiments.

Reads cgroup v2 counters on a fixed sampling loop:

- ``/sys/fs/cgroup/cpu.stat``    (``usage_usec`` / ``user_usec`` / ``system_usec``)
- ``/sys/fs/cgroup/memory.current``
- ``/sys/fs/cgroup/memory.peak``

The telemetry is cgroup-wide (the whole container, not just the Python
process), attributed to pipeline stages via the trace-event wall timestamps
already emitted by the runtime (``build_stage_boundaries``), and summarized
into a compact JSON-safe dict:

- CPU cores (average / peak / p95) derived from delta(usage_usec)/delta(wall)
- CPU utilization peaks over 50 / 100 / 250 / 500 / 1000 ms windows
- RAM peak (cgroup high-water + sampled current), RAM p95
- per-stage cores/RAM/duration with wall boundaries

Overhead is minimal (two small file reads per tick).  The sampler is a no-op
when ``COMFYMODAL_V2_RESOURCE_TELEMETRY`` is not enabled (default off) and
never raises: every failure path degrades to ``{"status": "unavailable"}``.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

INTERVAL_MS = 50
WINDOWS_MS: tuple[int, ...] = (50, 100, 250, 500, 1000)
_ENV_FLAG = "COMFYMODAL_V2_RESOURCE_TELEMETRY"
_DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup"


def telemetry_enabled() -> bool:
    """True when the opt-in telemetry env flag is set (default off)."""
    return os.environ.get(_ENV_FLAG, "0").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_cgroup_v2_base(
    mountinfo_path: str = "/proc/self/mountinfo",
    cgroup_path: str = "/proc/self/cgroup",
) -> str | None:
    """Resolve the process cgroup v2 directory from procfs metadata.

    Mirrors the runtime's own resolver (full_execution_trace): the cgroup
    mount point from ``/proc/self/mountinfo`` (matching ``cgroup2`` in the
    mount options, or a ``cgroup`` mount at ``/sys/fs/cgroup``) joined with
    the last ``0::`` entry from ``/proc/self/cgroup``.  Returns ``None`` on
    any error (the caller falls back to ``/sys/fs/cgroup``).
    """
    mount_point: str | None = None
    try:
        with open(mountinfo_path, "r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 6:
                    candidate = parts[4]
                    rest = " ".join(parts[5:])
                    if "cgroup2" in rest or ("cgroup" in rest and candidate == "/sys/fs/cgroup"):
                        mount_point = candidate
                        break
    except Exception:
        return None
    if not mount_point:
        return None

    cgroup_rel: str | None = None
    try:
        with open(cgroup_path, "r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        if not lines:
            return None
        cg_line = lines[-1]
        cg_parts = cg_line.split(":")
        if len(cg_parts) < 3:
            return None
        cgroup_rel = cg_parts[-1]
    except Exception:
        return None
    if cgroup_rel in ("", "/"):
        return mount_point
    return os.path.join(mount_point, cgroup_rel.lstrip("/"))


def _resolve_cgroup_root() -> str:
    """Best-effort cgroup v2 base, falling back to the default mount."""
    base = _resolve_cgroup_v2_base()
    if base is not None and os.path.isdir(base):
        return base
    return _DEFAULT_CGROUP_ROOT


def _read_proc_self_cpu_ticks() -> dict[str, int] | None:
    """Read process utime/stime clock ticks from /proc/self/stat.

    Fallback when the cgroup ``cpu.stat`` is not readable (Modal/gVisor):
    fields 14 (utime) and 15 (stime) of ``/proc/self/stat``, in clock ticks.
    """
    try:
        with open("/proc/self/stat", "r", encoding="utf-8") as fh:
            data = fh.read()
        # comm may contain spaces/parens; the fields after the last ')' are
        # reliably indexed from the end.
        idx = data.rfind(")")
        if idx < 0:
            return None
        rest = data[idx + 1:].split()
        # rest[0] == state; utime=rest[11], stime=rest[12] (fields 14/15).
        if len(rest) < 13:
            return None
        utime = int(rest[11])
        stime = int(rest[12])
        return {"utime_ticks": utime, "stime_ticks": stime}
    except Exception:
        return None


_CLK_TCK: float | None = None


def _clock_ticks_per_sec() -> float:
    global _CLK_TCK
    if _CLK_TCK is None:
        try:
            _sysconf = getattr(os, "sysconf", None)
            if _sysconf is not None:
                _CLK_TCK = float(_sysconf("SC_CLK_TCK"))
            else:
                _CLK_TCK = 100.0
        except Exception:
            _CLK_TCK = 100.0
    return _CLK_TCK


def _read_int(path: str) -> int | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return int(fh.read().strip())
    except Exception:
        return None


def _read_cpu_stat(cgroup_root: str) -> dict[str, int] | None:
    """Parse ``cpu.stat`` into {usage_usec, user_usec, system_usec, ...}."""
    try:
        with open(os.path.join(cgroup_root, "cpu.stat"), "r", encoding="utf-8") as fh:
            out: dict[str, int] = {}
            for line in fh:
                parts = line.split()
                if len(parts) == 2:
                    key = str(parts[0]).strip()
                    try:
                        out[key] = int(str(parts[1]).strip())
                    except ValueError:
                        pass
        if "usage_usec" not in out:
            return None
        return out
    except Exception:
        return None


def _read_memory(cgroup_root: str) -> dict[str, Any] | None:
    current = _read_int(os.path.join(cgroup_root, "memory.current"))
    peak = _read_int(os.path.join(cgroup_root, "memory.peak"))
    if current is None:
        return None
    return {"current": current, "peak": peak}


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank: ceil(pct/100 * n) - 1 (1-indexed rank -> 0-indexed idx).
    idx = int(pct / 100.0 * len(ordered) + 0.999999)
    idx = min(len(ordered) - 1, max(0, idx - 1))
    return ordered[idx]


class ResourceTelemetry:
    """50 ms cgroup CPU/RAM sampler with stage attribution + aggregation."""

    def __init__(self, interval_ms: int = INTERVAL_MS, cgroup_root: str | None = None):
        self._interval = max(10, int(interval_ms)) / 1000.0
        self._cgroup_root = cgroup_root or _resolve_cgroup_root()
        self._lock = threading.Lock()
        self._samples: list[dict[str, Any]] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._status = "unavailable"
        self._sampling_interval_ms = max(10, int(interval_ms))

    # -- lifecycle ----------------------------------------------------------

    def _read_once(self) -> dict[str, Any] | None:
        cpu = _read_cpu_stat(self._cgroup_root)
        mem = _read_memory(self._cgroup_root)
        proc = _read_proc_self_cpu_ticks()
        if cpu is None and mem is None and proc is None:
            return None
        sample: dict[str, Any] = {
            "wall_ns": time.time_ns(),
            "mono_ns": time.monotonic_ns(),
            "mem_current": mem.get("current") if mem else None,
            "mem_peak": mem.get("peak") if mem else None,
            "proc_utime_ticks": proc.get("utime_ticks") if proc else None,
            "proc_stime_ticks": proc.get("stime_ticks") if proc else None,
        }
        if cpu is not None:
            sample["usage_usec"] = cpu.get("usage_usec")
            sample["user_usec"] = cpu.get("user_usec")
            sample["system_usec"] = cpu.get("system_usec")
        return sample

    def start(self) -> None:
        """Start the sampling loop.  Fails closed when cgroup files are absent."""
        baseline = self._read_once()
        if baseline is None:
            self._status = "unavailable"
            return
        self._status = "measured"
        with self._lock:
            self._samples = [baseline]
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="resource-telemetry", daemon=True,
        )
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            sample = self._read_once()
            if sample is None:
                continue
            with self._lock:
                self._samples.append(sample)

    def stop(self) -> None:
        """Stop the loop and append one final sample (best effort)."""
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2.0)
            self._thread = None
        final = self._read_once()
        if final is not None:
            with self._lock:
                self._samples.append(final)

    # -- aggregation --------------------------------------------------------

    @staticmethod
    def _window_peaks(samples: list[dict[str, Any]], cpu_source: str) -> dict[str, float | None]:
        """Max average cores over any sub-window of each requested duration.

        ``cpu_source`` selects the per-pair CPU delta source: ``cgroup``
        (usage_usec) or ``process`` (utime+stime clock ticks).
        """
        out: dict[str, float | None] = {}
        n = len(samples)
        for window_ms in WINDOWS_MS:
            best: float | None = None
            left = 0
            window_ns = window_ms * 1_000_000
            for right in range(1, n):
                while samples[right]["wall_ns"] - samples[left]["wall_ns"] > window_ns:
                    left += 1
                if right > left:
                    dw = samples[right]["wall_ns"] - samples[left]["wall_ns"]
                    if dw > 0:
                        if cpu_source == "cgroup":
                            a = samples[left]["usage_usec"]
                            b = samples[right]["usage_usec"]
                            if a is None or b is None:
                                continue
                            du = b - a
                            cores = (du / 1_000_000.0) / (dw / 1_000_000_000.0)
                        else:
                            a_t = (samples[left]["proc_utime_ticks"] or 0) + (samples[left]["proc_stime_ticks"] or 0)
                            b_t = (samples[right]["proc_utime_ticks"] or 0) + (samples[right]["proc_stime_ticks"] or 0)
                            cores = ((b_t - a_t) / _clock_ticks_per_sec()) / (dw / 1_000_000_000.0)
                        if best is None or cores > best:
                            best = cores
            out[str(window_ms)] = round(best, 3) if best is not None else None
        return out

    def summarize(self, stage_boundaries: dict[str, dict[str, int]] | None = None) -> dict[str, Any]:
        """Aggregate the captured samples into a compact JSON-safe summary."""
        with self._lock:
            samples = list(self._samples)
        if self._status != "measured" or len(samples) < 2:
            return {
                "status": "unavailable",
                "sampling_interval_ms": self._sampling_interval_ms,
                "reason": "no_valid_samples",
            }
        first, last = samples[0], samples[-1]
        wall_ns = last["wall_ns"] - first["wall_ns"]

        has_usage = any(s.get("usage_usec") is not None for s in samples)
        has_ticks = any(
            s.get("proc_utime_ticks") is not None or s.get("proc_stime_ticks") is not None
            for s in samples
        )
        cpu_source = "cgroup" if has_usage else ("process" if has_ticks else "none")

        def _pair_cores(i: int) -> float | None:
            dw = samples[i]["wall_ns"] - samples[i - 1]["wall_ns"]
            if dw <= 0:
                return None
            if cpu_source == "cgroup":
                a = samples[i - 1]["usage_usec"]
                b = samples[i]["usage_usec"]
                if a is None or b is None:
                    return None
                return ((b - a) / 1_000_000.0) / (dw / 1_000_000_000.0)
            if cpu_source == "process":
                a_t = (samples[i - 1].get("proc_utime_ticks") or 0) + (samples[i - 1].get("proc_stime_ticks") or 0)
                b_t = (samples[i].get("proc_utime_ticks") or 0) + (samples[i].get("proc_stime_ticks") or 0)
                return ((b_t - a_t) / _clock_ticks_per_sec()) / (dw / 1_000_000_000.0)
            return None

        cores_per_pair: list[tuple[float, int]] = []
        for i in range(1, len(samples)):
            cores = _pair_cores(i)
            if cores is not None:
                cores_per_pair.append((cores, i))

        cpu_payload: dict[str, Any] = {"source": cpu_source}
        if cpu_source == "cgroup":
            usage_usec = (last.get("usage_usec") or 0) - (first.get("usage_usec") or 0)
            user_usec = (last.get("user_usec") or 0) - (first.get("user_usec") or 0)
            system_usec = (last.get("system_usec") or 0) - (first.get("system_usec") or 0)
            cpu_payload.update({
                "usage_usec": usage_usec,
                "user_usec": user_usec,
                "system_usec": system_usec,
                "average_cores": round(usage_usec / max(1, wall_ns) * 1000.0, 3)
                if wall_ns > 0 else None,
            })
        elif cpu_source == "process":
            t0 = (first.get("proc_utime_ticks") or 0) + (first.get("proc_stime_ticks") or 0)
            t1 = (last.get("proc_utime_ticks") or 0) + (last.get("proc_stime_ticks") or 0)
            cpu_payload.update({
                "proc_ticks_delta": t1 - t0,
                "average_cores": round(((t1 - t0) / _clock_ticks_per_sec()) / (wall_ns / 1_000_000_000.0), 3)
                if wall_ns > 0 else None,
            })
        if cores_per_pair:
            cpu_payload["peak_cores"] = max(c for c, _ in cores_per_pair)
            cpu_payload["p95_cores"] = percentile([c for c, _ in cores_per_pair], 95.0)
        else:
            cpu_payload["peak_cores"] = None
            cpu_payload["p95_cores"] = None
        cpu_payload["peak_cores_over_window_ms"] = self._window_peaks(samples, cpu_source)

        mem_current = [s["mem_current"] for s in samples if s.get("mem_current") is not None]
        mem_peak_values = [s["mem_peak"] for s in samples if s.get("mem_peak") is not None]
        mem_peak_cgroup = max(mem_peak_values) if mem_peak_values else None
        ram_payload: dict[str, Any] = {}
        if mem_current:
            ram_payload.update({
                "cgroup_peak_bytes": mem_peak_cgroup,
                "sampled_peak_bytes": max(mem_current),
                "p95_bytes": percentile(mem_current, 95.0),
                "end_bytes": mem_current[-1],
            })

        summary: dict[str, Any] = {
            "status": "measured",
            "sampling_interval_ms": self._sampling_interval_ms,
            "samples": len(samples),
            "duration_ms": round(wall_ns / 1_000_000.0, 1),
            "wall_start_unix_ns": first["wall_ns"],
            "wall_end_unix_ns": last["wall_ns"],
            "cpu": cpu_payload,
            "ram": ram_payload,
        }

        # -- per-stage attribution -----------------------------------------
        stages: dict[str, Any] = {}
        if stage_boundaries:
            ordered = sorted(
                stage_boundaries.items(), key=lambda kv: kv[1].get("start_unix_ns", 0),
            )
            for name, bounds in ordered:
                start_ns = bounds.get("start_unix_ns")
                end_ns = bounds.get("end_unix_ns")
                if start_ns is None or end_ns is None or end_ns < start_ns:
                    continue
                in_stage = [
                    s for s in samples
                    if start_ns <= s["wall_ns"] < end_ns
                ]
                pair_cores: list[float] = []
                for i in range(1, len(samples)):
                    if start_ns <= samples[i]["wall_ns"] < end_ns:
                        cores = _pair_cores(i)
                        if cores is not None:
                            pair_cores.append(cores)
                stage_entry: dict[str, Any] = {
                    "start_unix_ns": start_ns,
                    "end_unix_ns": end_ns,
                    "duration_ms": round((end_ns - start_ns) / 1_000_000.0, 1),
                    "samples": len(in_stage),
                }
                stage_mem = [s["mem_current"] for s in in_stage if s.get("mem_current") is not None]
                if stage_mem:
                    stage_entry["ram_peak_bytes"] = max(stage_mem)
                    stage_entry["ram_end_bytes"] = stage_mem[-1]
                if pair_cores:
                    stage_entry["average_cores"] = round(sum(pair_cores) / len(pair_cores), 3)
                    stage_entry["peak_cores"] = round(max(pair_cores), 3)
                stages[name] = stage_entry
        summary["stages"] = stages
        summary["stage_boundaries"] = stage_boundaries
        return summary


def build_stage_boundaries(
    events: list[dict[str, Any]] | None,
    restore_timing: dict[str, Any] | None,
) -> dict[str, dict[str, int]]:
    """Map the runtime trace events to stage wall boundaries (unix ns).

    Uses only boundaries already available in the trace/restore timing:
    python resume (restore lifecycle), method first line, prompt executor
    invoke, TWO-LANE lane wait, sampler, VAE decode, output collection and
    terminal return.  Missing events fold the stage into the previous one;
    never raises.
    """
    events = events or []
    restore_timing = restore_timing or {}

    def _num(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and value:
            return int(value)
        return None

    def _first_event(name: str) -> int | None:
        for ev in events:
            if isinstance(ev, dict) and ev.get("name") == name:
                wall = _num(ev.get("wall_unix_ns"))
                if wall is not None:
                    return wall
        return None

    def _last_event(name: str) -> int | None:
        found: int | None = None
        for ev in events:
            if isinstance(ev, dict) and ev.get("name") == name:
                wall = _num(ev.get("wall_unix_ns"))
                if wall is not None:
                    found = wall
        return found

    resume = _num(restore_timing.get("remote_python_resume_wall_unix_ns"))
    method_first = (
        _first_event("run_plan_method_first_line")
        or _first_event("remote_method_entry")
    )
    exec_invoke = _first_event("prompt_executor_invoke_start")
    lane_start = _first_event("sampler_lane_wait_start") or _first_event("gpu_lane_wait_start")
    lane_end = (
        _last_event("sampler_lane_wait_end")
        or _last_event("gpu_lane_wait_end")
        or _first_event("unet_early_activation_completed")
    )
    sampler_start = _first_event("sampler_start")
    sampler_end = _last_event("sampler_end") or _last_event("sampling_end")
    vae_start = _first_event("vae_decode_start")
    vae_end = _last_event("vae_decode_end")
    output_start = _first_event("output_collect_start")
    terminal = (
        _last_event("remote_return_start")
        or _last_event("output_persist_end")
        or _last_event("prepared_result_consumed")
    )

    # Anchor: python resume (when known) or the first captured python line.
    anchor = resume or method_first
    if anchor is None:
        return {}

    boundaries: dict[str, dict[str, int]] = {}
    prev_name: str | None = None
    prev_end = anchor

    def _push(name: str, start_ns: int | None, end_ns: int | None) -> None:
        nonlocal prev_name, prev_end
        if start_ns is None:
            start_ns = prev_end
        if end_ns is None or end_ns < start_ns:
            end_ns = start_ns
        if end_ns > prev_end or name == "python_resume":
            boundaries[name] = {"start_unix_ns": start_ns, "end_unix_ns": end_ns}
            prev_name = name
            prev_end = end_ns

    if resume is not None and method_first is not None and method_first >= resume:
        _push("python_resume", resume, method_first)
    _push("bootstrap_setup", prev_end if prev_name else method_first, exec_invoke)
    _push("clip_graph_preparation", None, lane_start)
    _push("two_lane_activation", None, lane_end)
    _push("sampler_preparation", None, sampler_start)
    _push("sampling", None, sampler_end)
    _push("vae", None, vae_end)
    _push("output_result", None, terminal)

    # Drop empty/degenerate stages, keep the last observed boundary honest.
    return {
        name: bounds
        for name, bounds in boundaries.items()
        if bounds["end_unix_ns"] > bounds["start_unix_ns"]
    }
