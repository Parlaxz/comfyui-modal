"""Guarded, stdlib-only host hardware & pressure telemetry for Modal/gVisor.

Two-tier design:

- TIER A (always-on, healthy path): in-process only, NO subprocesses.  The
  one-shot fingerprint (gVisor-exposed CPUID-derived identity, python
  topology, static GPU probe, one-time PSI/cgroup capability probes) and the
  per-phase resource snapshots (rusage + /proc/self/stat + cached capability
  state + deltas) target single-digit ms so steady-state telemetry overhead
  stays negligible.
- TIER B (forensic, slow-H2D trigger or ``COMFYMODAL_V2_HOST_DIAGNOSTICS=1``):
  ``nvidia-smi`` and ``lscpu`` subprocesses (``nvidia_gpu_snapshot``,
  ``read_lscpu``) run only after a slow H2D is observed, via
  ``emit_slow_h2d_forensics``.

gVisor (runsc) context: vendor and feature flags in ``/proc/cpuinfo`` are
gVisor-exposed CPUID-derived values - useful for worker-class grouping, but
physical brand/class and physical topology are NOT resolved (model name and
stepping are hardcoded ``unknown``, siblings/cores/physical-id are synthetic).
``cpuinfo_fingerprint_hash`` is a worker-class grouping key, not physical-host
identity.  cgroupfs is sentry-internal, never the outer worker cgroup, and
``/proc/pressure/*`` is typically absent (ENOENT).

GPU: Tier A static identity (``gpu_name`` + torch capability/memory/SM counts)
comes from the already-loaded torch module - a ctypes NVML probe was removed
from the healthy path because ``nvmlInit``/library load is slow under gVisor
(~400 ms measured) and the max-link NVML calls are unsupported under nvproxy.
PCIe link gen/width, UUID and driver version are Tier B only (via
``nvidia-smi``, which works there) and surface in the slow-H2D forensics event.

Every probe is guarded individually and the module never raises: optional
dependencies (torch, psutil, pynvml, cpuinfo, cpuid) are imported lazily
inside the functions that use them (Tier A only consults torch/psutil when
the runtime already loaded them, so a cold import can never blow the healthy
path budget), subprocess probes use hard timeouts, and every failure path
degrades to ``None``/``"unavailable"``.

Trace events: ``host_hardware_fingerprint`` (phase="host"),
``host_resource_snapshot`` (phase=phase) and ``host_forensic_slow_h2d``
(phase="host").  Metadata is always flat JSON-safe scalars
(str/int/float/bool/None).

H2D classification note: enqueue ~= cuda_elapsed does NOT prove the copy was
device-bound - synchronous/pageable copies can block the host.  Classification
describes where time went; root-cause claims must be paired with the Tier B
PCIe/pstate/clocks data and the CPU fingerprint.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_TRACE: Any = None
_fingerprint_emitted = False
_LAST_SNAPSHOT: Any = None
_LAST_SNAPSHOT_WALL_MONO: float | None = None
_GPU_CACHE: Any = None
_GPU_CACHE_AT: float = 0.0
_GPU_CACHE_TTL_S = 2.0
_GPU_FAIL_TTL_S = 5.0

# Capability cache: psi/cgroup sources are probed ONCE (first caller wins)
# and honored by every later snapshot so per-phase file reads never repeat.
_CAP_CACHE: dict[str, Any] = {
    "psi_done": False,
    "psi": None,
    "cgroup_done": False,
    "cgroup": None,
}

_LSCPU_TIMEOUT_S = 8
_NVIDIA_SMI_TIMEOUT_S = 10

_FEATURE_TOKEN_MAP: dict[str, tuple[str, ...]] = {
    "avx": ("avx",),
    "avx2": ("avx2",),
    "avx512f": ("avx512f",),
    "avx512bw": ("avx512bw",),
    "avx512vl": ("avx512vl",),
    "avx512dq": ("avx512dq",),
    "avx512_vnni": ("avx512_vnni", "avx512vnni"),
    "fma": ("fma",),
    "bmi1": ("bmi1",),
    "bmi2": ("bmi2",),
}

_CPUINFO_FIELD_ALIASES: dict[str, str] = {
    "vendor_id": "vendor_id",
    "cpu family": "cpu_family",
    "model": "cpu_model",
    "model name": "cpu_model_name",
    "stepping": "cpu_stepping",
    "microcode": "cpu_microcode",
    "cpu MHz": "cpu_mhz",
    "cache size": "cpu_cache_size",
    "siblings": "cpu_siblings",
    "cpu cores": "cpu_cores",
    "physical id": "cpu_physical_id",
    "core id": "cpu_core_id",
    "flags": "cpu_flags",
}

_LSCPU_TO_CANONICAL: dict[str, str] = {
    "Architecture": "architecture",
    "CPU": "cpu_count",
    "On-line CPU list": "online_cpu_list",
    "Vendor ID": "vendor_id",
    "Model name": "model_name",
    "CPU family": "cpu_family",
    "Model": "cpu_model",
    "Thread per core": "threads_per_core",
    "Core per socket": "cores_per_socket",
    "Socket": "sockets",
    "NUMA node": "numa_nodes",
    "NUMA node0 CPU": "numa_node0_cpus",
    "L1d cache": "cache_l1d",
    "L1i cache": "cache_l1i",
    "L2 cache": "cache_l2",
    "L3 cache": "cache_l3",
    "Hypervisor vendor": "hypervisor_vendor",
    "Flags": "flags",
}

_SMI_QUERY_FULL = (
    "name,uuid,driver_version,index,pci.bus_id,"
    "pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,"
    "pcie.link.width.max,pstate,clocks.sm,clocks.mem,power.draw,"
    "utilization.gpu,utilization.memory,memory.bar1.used"
)
_SMI_QUERY_CORE = (
    "name,uuid,driver_version,pci.bus_id,pstate,clocks.sm,clocks.mem,"
    "power.draw,utilization.gpu,utilization.memory"
)
_SMI_QUERY_MINIMAL = "name,uuid,driver_version"
_SMI_QUERY_PCIE = "pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max"

# nvidia-smi fallback chain: first level whose subprocess exits 0 and yields a
# usable CSV row wins.  Fields absent from the winning level stay None.
_SMI_QUERIES = (
    ("full", _SMI_QUERY_FULL),
    ("core", _SMI_QUERY_CORE),
    ("minimal", _SMI_QUERY_MINIMAL),
)

# (csv field index, output key, kind) per query level.  kind is one of
# str/uuid/int/num/util/bar1; num/util/bar1 tolerate N/A and unit suffixes.
_SMI_FIELD_MAPS = {
    "full": (
        (0, "gpu_name", "str"),
        (1, "gpu_uuid_hash", "uuid"),
        (2, "gpu_driver_version", "str"),
        (3, "gpu_index", "int"),
        (4, "gpu_pci_bus", "str"),
        (5, "gpu_pcie_gen_current", "num"),
        (6, "gpu_pcie_gen_max", "num"),
        (7, "gpu_pcie_width_current", "num"),
        (8, "gpu_pcie_width_max", "num"),
        (9, "gpu_pstate", "str"),
        (10, "gpu_sm_clock_mhz", "num"),
        (11, "gpu_mem_clock_mhz", "num"),
        (12, "gpu_power_w", "num"),
        (13, "gpu_util", "util"),
        (14, "gpu_mem_util", "util"),
        (15, "gpu_bar1_used_mib", "bar1"),
    ),
    "core": (
        (0, "gpu_name", "str"),
        (1, "gpu_uuid_hash", "uuid"),
        (2, "gpu_driver_version", "str"),
        (3, "gpu_pci_bus", "str"),
        (4, "gpu_pstate", "str"),
        (5, "gpu_sm_clock_mhz", "num"),
        (6, "gpu_mem_clock_mhz", "num"),
        (7, "gpu_power_w", "num"),
        (8, "gpu_util", "util"),
        (9, "gpu_mem_util", "util"),
    ),
    "minimal": (
        (0, "gpu_name", "str"),
        (1, "gpu_uuid_hash", "uuid"),
        (2, "gpu_driver_version", "str"),
    ),
    "pcie": (
        (0, "gpu_pcie_gen_current", "num"),
        (1, "gpu_pcie_gen_max", "num"),
        (2, "gpu_pcie_width_current", "num"),
        (3, "gpu_pcie_width_max", "num"),
    ),
}

_GPU_KEYS = (
    "gpu_source", "gpu_query_wall_ms", "gpu_uuid_hash", "gpu_name",
    "gpu_driver_version", "gpu_index", "gpu_pci_bus", "gpu_pcie_gen_current",
    "gpu_pcie_gen_max", "gpu_pcie_width_current", "gpu_pcie_width_max",
    "gpu_pstate", "gpu_sm_clock_mhz", "gpu_mem_clock_mhz", "gpu_power_w",
    "gpu_util", "gpu_mem_util", "gpu_bar1_used_mib", "gpu_error", "gpu_pcie_error",
)

# Tier A static GPU identity output (already-loaded torch only; no driver calls).
_TORCH_GPU_KEYS = (
    "gpu_name", "gpu_static_source",
    "torch_device_capability", "torch_total_memory_bytes",
    "torch_multi_processor_count",
)

# Tier B forensic snapshot: exact subset of nvidia_gpu_snapshot() surfaced in
# the slow-H2D forensics event.
_FORENSIC_GPU_KEYS = (
    "gpu_source", "gpu_name", "gpu_uuid_hash", "gpu_pcie_gen_current",
    "gpu_pcie_gen_max", "gpu_pcie_width_current", "gpu_pcie_width_max",
    "gpu_pstate", "gpu_sm_clock_mhz", "gpu_mem_clock_mhz", "gpu_power_w",
    "gpu_util", "gpu_mem_util", "gpu_error", "gpu_pcie_error",
)

_PSI_SOURCES = ("cpu", "memory", "io")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def set_trace(trace) -> None:
    """Store the module-level trace reference for later emits (no-op if None)."""
    global _TRACE
    if trace is not None:
        _TRACE = trace


def _diagnostics_enabled() -> bool:
    """True when the Tier B diagnostic flag is set (1/true/yes/on)."""
    return os.environ.get("COMFYMODAL_V2_HOST_DIAGNOSTICS", "").strip().lower() in {"1", "true", "yes", "on"}


def _slow_h2d_threshold() -> float:
    try:
        return float(os.environ.get("COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS", "4000.0"))
    except (TypeError, ValueError):
        return 4000.0


def _torch_if_loaded() -> Any:
    """Return the already-imported torch module, or None.

    Tier A must stay single-digit ms: importing torch from scratch can cost
    ~1-2s, so we only consult torch when the runtime already loaded it (always
    true inside a ComfyUI container).
    """
    return sys.modules.get("torch")


def _cap_psi() -> dict:
    """Once-per-process cached read_psi() result (first caller probes)."""
    if not _CAP_CACHE["psi_done"]:
        _CAP_CACHE["psi"] = read_psi()
        _CAP_CACHE["psi_done"] = True
    return _CAP_CACHE["psi"] or {}


def _cap_cgroup() -> dict:
    """Once-per-process cached read_cgroup_fields() result (first caller probes)."""
    if not _CAP_CACHE["cgroup_done"]:
        _CAP_CACHE["cgroup"] = read_cgroup_fields()
        _CAP_CACHE["cgroup_done"] = True
    return _CAP_CACHE["cgroup"] or {}


def collect_host_fingerprint() -> dict:
    """One-shot Tier A host fingerprint; never raises, no subprocesses."""
    wall_start = time.monotonic()
    result: dict[str, Any] = {}

    cpuinfo_text = _read_proc_cpuinfo()
    parsed = parse_cpuinfo(cpuinfo_text)
    _flatten_cpuinfo(parsed, result)
    result["cpuinfo_fingerprint_hash"] = cpuinfo_fingerprint_hash(parsed)

    _add_topology_env(result)

    cpuid = try_direct_cpuid()
    _flatten_cpuid(cpuid, result)

    torch_gpu = _torch_gpu_identity()
    for key in _TORCH_GPU_KEYS:
        result[key] = torch_gpu.get(key)

    psi = _cap_psi()
    result["psi_status"] = psi.get("psi_status")

    cgroup = _cap_cgroup()
    result["cgroup_source"] = cgroup.get("cgroup_source")
    result["cgroup_likely_virtualized"] = cgroup.get("cgroup_likely_virtualized")
    result["cgroup_lines_snippet"] = cgroup.get("cgroup_lines_snippet")

    result["provider"] = os.environ.get("MODAL_CLOUD_PROVIDER")
    result["region"] = os.environ.get("MODAL_REGION")
    result["modal_image_id"] = os.environ.get("MODAL_IMAGE_ID")
    result["modal_task_id"] = os.environ.get("MODAL_TASK_ID")

    # lscpu is Tier B: only run its subprocess in diagnostic mode, else defer.
    if _diagnostics_enabled():
        lscpu = read_lscpu()
        _flatten_lscpu(lscpu, result)
    else:
        lscpu = {"lscpu_status": "deferred"}
        result["lscpu_status"] = "deferred"

    result["cpu_identity_sources_agree"] = _cpu_identity_sources_agree(parsed, lscpu, cpuid)
    result["cpu_count_sources_agree"] = _cpu_count_sources_agree(parsed, result, lscpu)
    result["cpu_features_source"] = _cpu_features_source(parsed, cpuid)
    result["cpu_identity_confidence"] = _cpu_identity_confidence(parsed, result)

    result["probe_statuses"] = _build_probe_statuses(parsed, lscpu, cpuid, psi, cgroup, torch_gpu)
    result["probe_wall_ms"] = round((time.monotonic() - wall_start) * 1000, 2)
    return result


def emit_host_fingerprint(trace=None) -> None:
    """Emit the fingerprint trace event + one concise print line, once per process."""
    global _fingerprint_emitted
    if _fingerprint_emitted:
        return
    _fingerprint_emitted = True
    try:
        fingerprint = collect_host_fingerprint()
    except Exception:
        return
    active = trace if trace is not None else _TRACE
    if active is not None:
        try:
            active.emit("host_hardware_fingerprint", phase="host", metadata=fingerprint)
        except Exception:
            pass
    keys = (
        "cpu_vendor", "cpu_model_name", "cpu_family", "cpu_model",
        "cpu_count_os", "cpu_identity_confidence", "gpu_name",
        "gpu_pcie_gen_current", "gpu_pcie_width_current", "provider", "region",
        "probe_wall_ms",
    )
    parts = ["[v2.host_hardware_fingerprint]"]
    for key in keys:
        value = fingerprint.get(key)
        if value is not None:
            parts.append(f"{key}={value}")
    try:
        print(" ".join(parts), flush=True)
    except Exception:
        pass


def classify_h2d(record: dict) -> str:
    """Classify where slow H2D wall time went.

    Returns one of ``TRAILING_SYNC_STALL`` / ``COPY_INTERVAL_SLOW`` /
    ``HOST_OVERHEAD_AROUND_COPY`` / ``UNKNOWN/MIXED``.  Note this describes
    where time went, NOT a root cause: enqueue ~= cuda_elapsed does not prove
    the copy was device-bound (synchronous/pageable copies can block the host).
    """
    c = record.get("h2d_cuda_elapsed_ms")
    e = record.get("h2d_enqueue_host_ms")
    s = record.get("h2d_sync_wait_host_ms")
    if (not isinstance(c, (int, float)) or isinstance(c, bool) or c <= 0
            or not isinstance(e, (int, float)) or isinstance(e, bool) or e <= 0
            or not isinstance(s, (int, float)) or isinstance(s, bool) or s < 0):
        return "UNKNOWN/MIXED"
    c = float(c)
    e = float(e)
    s = float(s)
    if s > max(200.0, 0.05 * c):
        return "TRAILING_SYNC_STALL"
    if e > 1.2 * c + 50.0:
        return "HOST_OVERHEAD_AROUND_COPY"
    if e >= 0.8 * c:
        return "COPY_INTERVAL_SLOW"
    return "UNKNOWN/MIXED"


def should_trigger_slow_probe(h2d_wall_ms: float) -> bool:
    """True when a slow-H2D forensic probe should run.

    Threshold comes from ``COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS`` (default
    4000.0); the diagnostic flag ``COMFYMODAL_V2_HOST_DIAGNOSTICS`` always
    forces a probe.
    """
    try:
        above = h2d_wall_ms >= _slow_h2d_threshold()
    except TypeError:
        above = False
    return above or _diagnostics_enabled()


def emit_slow_h2d_forensics(record: dict, trace=None) -> dict:
    """Tier B forensic capture after a slow H2D; never raises.

    Runs the nvidia-smi and lscpu subprocesses, composes a flat metadata dict,
    emits ``host_forensic_slow_h2d`` (phase="host") and prints one concise
    ``[v2.forensic_slow_h2d]`` line.  Returns the metadata dict.
    """
    meta: dict[str, Any] = {}
    for key in ("h2d_to_wall_ms", "h2d_cuda_elapsed_ms", "h2d_enqueue_host_ms",
                "h2d_sync_wait_host_ms", "h2d_copy_count", "h2d_total_bytes"):
        value = record.get(key)
        if value is not None:
            meta[key] = value
    meta["h2d_classification"] = classify_h2d(record)
    wall = record.get("h2d_to_wall_ms")
    if isinstance(wall, (int, float)) and not isinstance(wall, bool) and wall >= _slow_h2d_threshold():
        meta["trigger_reason"] = "h2d_threshold"
    else:
        meta["trigger_reason"] = "diag_flag"

    probe_start = time.monotonic()
    try:
        gpu = nvidia_gpu_snapshot()
        for key in _FORENSIC_GPU_KEYS:
            if gpu.get(key) is not None:
                meta[key] = gpu.get(key)
    except Exception:  # noqa: BLE001
        pass
    try:
        lscpu = read_lscpu()
        for key in ("architecture", "cpu_count", "vendor_id", "model_name", "hypervisor_vendor"):
            if lscpu.get(key) is not None:
                meta[f"lscpu_{key}"] = lscpu.get(key)
    except Exception:  # noqa: BLE001
        pass
    meta["probe_wall_ms"] = round((time.monotonic() - probe_start) * 1000, 2)

    active = trace if trace is not None else _TRACE
    if active is not None:
        try:
            active.emit("host_forensic_slow_h2d", phase="host", metadata=meta)
        except Exception:  # noqa: BLE001
            pass

    parts = ["[v2.forensic_slow_h2d]"]
    for key in ("h2d_to_wall_ms", "h2d_classification", "gpu_name",
                "gpu_pcie_gen_current", "gpu_pcie_width_current",
                "lscpu_architecture", "lscpu_model_name", "trigger_reason",
                "probe_wall_ms"):
        value = meta.get(key)
        if value is not None:
            parts.append(f"{key}={value}")
    try:
        print(" ".join(parts), flush=True)
    except Exception:  # noqa: BLE001
        pass
    return meta


def capture_resource_snapshot(phase: str, trace=None) -> dict:
    """Capture a cheap Tier A per-phase resource snapshot; never raises.

    In-process only: rusage + /proc/self/stat + delta accounting against the
    previous snapshot.  PSI/cgroup values come from the once-per-process
    capability cache (never re-read per phase); GPU dynamic state is Tier B
    and intentionally absent here.
    """
    global _LAST_SNAPSHOT, _LAST_SNAPSHOT_WALL_MONO
    wall_start = time.monotonic()
    snap: dict[str, Any] = {"phase": phase}

    rusage = rusage_snapshot()
    for key in ("ru_utime", "ru_stime", "ru_minflt", "ru_majflt", "ru_nvcsw", "ru_nivcsw", "ru_maxrss"):
        snap[key] = rusage.get(key)

    proc = read_proc_self_stat()
    ticks_per_sec = proc.get("ticks_per_sec") or 100.0
    snap["minflt"] = proc.get("minflt")
    snap["majflt"] = proc.get("majflt")
    snap["utime_ms"] = _ticks_to_ms(proc.get("utime_ticks"), ticks_per_sec)
    snap["stime_ms"] = _ticks_to_ms(proc.get("stime_ticks"), ticks_per_sec)
    snap["num_threads"] = proc.get("num_threads")

    psi = _cap_psi()
    if psi.get("psi_status") == "available":
        for key in ("cpu_psi_some_avg10", "memory_psi_some_avg10", "io_psi_some_avg10",
                    "cpu_psi_some_total", "memory_psi_some_total", "io_psi_some_total"):
            if psi.get(key) is not None:
                snap[key] = psi.get(key)

    cgroup = _cap_cgroup()
    if cgroup.get("cgroup_source") == "v2":
        snap["cgroup_nr_throttled"] = cgroup.get("cgroup_cpu_nr_throttled")
        snap["cgroup_throttled_usec"] = cgroup.get("cgroup_cpu_throttled_usec")

    _delta_keys = ("delta_minflt", "delta_majflt", "delta_nvcsw", "delta_nivcsw",
                   "delta_utime_ms", "delta_stime_ms")
    prev = _LAST_SNAPSHOT
    if prev is None:
        for key in _delta_keys:
            snap[key] = None
        snap["delta_wall_ms"] = None
    else:
        snap["delta_minflt"] = _delta(prev.get("minflt"), snap.get("minflt"))
        snap["delta_majflt"] = _delta(prev.get("majflt"), snap.get("majflt"))
        snap["delta_nvcsw"] = _delta(prev.get("ru_nvcsw"), snap.get("ru_nvcsw"))
        snap["delta_nivcsw"] = _delta(prev.get("ru_nivcsw"), snap.get("ru_nivcsw"))
        snap["delta_utime_ms"] = _delta(prev.get("utime_ms"), snap.get("utime_ms"))
        snap["delta_stime_ms"] = _delta(prev.get("stime_ms"), snap.get("stime_ms"))
        snap["delta_wall_ms"] = _wall_delta_ms(_LAST_SNAPSHOT_WALL_MONO, wall_start)

    snap["probe_wall_ms"] = round((time.monotonic() - wall_start) * 1000, 2)

    active = trace if trace is not None else _TRACE
    if active is not None:
        try:
            active.emit("host_resource_snapshot", phase=phase, metadata=dict(snap))
        except Exception:  # noqa: BLE001
            pass

    _LAST_SNAPSHOT = dict(snap)
    _LAST_SNAPSHOT_WALL_MONO = wall_start
    return snap

# ---------------------------------------------------------------------------
# 1A. /proc/cpuinfo
# ---------------------------------------------------------------------------

def parse_cpuinfo(text: str) -> dict:
    """Parse /proc/cpuinfo: first block fields, entry count, homogeneity, flags.

    Missing keys are omitted; malformed input never raises.  Returns at least
    ``cpu_count_proc`` and ``cpu_entries_homogeneous`` (None when unparseable).
    """
    result: dict[str, Any] = {"cpu_count_proc": 0, "cpu_entries_homogeneous": None}
    if not isinstance(text, str) or not text.strip():
        return result

    blocks: list[list[str]] = []
    current: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("processor"):
            current = []
            blocks.append(current)
        if current is not None:
            current.append(line)

    parsed_blocks: list[dict[str, str]] = []
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block:
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        if "processor" in fields:
            parsed_blocks.append(fields)

    result["cpu_count_proc"] = len(parsed_blocks)
    if not parsed_blocks:
        return result

    first = parsed_blocks[0]
    for source_key, dest_key in _CPUINFO_FIELD_ALIASES.items():
        if source_key not in first:
            continue
        value = first[source_key]
        if dest_key == "cpu_mhz":
            try:
                result[dest_key] = round(float(value), 3)
            except (TypeError, ValueError):
                pass
        else:
            result[dest_key] = value

    flags = result.get("cpu_flags")
    flag_tokens = flags.split() if flags else []
    for feature, tokens in _FEATURE_TOKEN_MAP.items():
        if flag_tokens:
            result[feature] = any(token in flag_tokens for token in tokens)
        else:
            result[feature] = None

    identities: list[tuple[str, str, str]] = []
    for block in parsed_blocks:
        identity = (block.get("vendor_id", ""), block.get("cpu family", ""), block.get("model", ""))
        if any(identity):
            identities.append(identity)
    if identities:
        result["cpu_entries_homogeneous"] = len(set(identities)) == 1
    return result


def cpuinfo_fingerprint_hash(cpuinfo_parsed: dict) -> str:
    """sha256 hexdigest over stable identity fields only.

    Canonical string uses vendor_id, cpu_family, cpu_model, cpu_stepping,
    cpu_microcode and sorted cpu_flags tokens.  NEVER includes cpu MHz or the
    model name.  Missing fields contribute an empty segment.
    """
    segments = [
        str(cpuinfo_parsed.get("vendor_id") or ""),
        str(cpuinfo_parsed.get("cpu_family") or ""),
        str(cpuinfo_parsed.get("cpu_model") or ""),
        str(cpuinfo_parsed.get("cpu_stepping") or ""),
        str(cpuinfo_parsed.get("cpu_microcode") or ""),
    ]
    flags = cpuinfo_parsed.get("cpu_flags")
    flag_tokens = sorted(flags.split()) if flags else []
    segments.append(" ".join(flag_tokens))
    canonical = "|".join(segments)
    return hashlib.sha256(canonical.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# 1B. Python topology + env
# ---------------------------------------------------------------------------

def _read_proc_cpuinfo() -> str:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def _get_affinity() -> list[int] | None:
    try:
        return sorted(os.sched_getaffinity(0))
    except Exception:
        return None


def _add_topology_env(result: dict[str, Any]) -> None:
    try:
        result["cpu_count_os"] = os.cpu_count()
    except Exception:
        result["cpu_count_os"] = None

    affinity = _get_affinity()
    if affinity is not None:
        result["cpu_affinity_count"] = len(affinity)
        if affinity:
            result["cpu_affinity_min"] = min(affinity)
            result["cpu_affinity_max"] = max(affinity)

    try:
        import multiprocessing
        result["cpu_count_multiprocessing"] = multiprocessing.cpu_count()
    except Exception:
        result["cpu_count_multiprocessing"] = None

    psutil_logical: Any = None
    psutil_physical: Any = None
    # Tier A budget: only consult psutil when the runtime already loaded it.
    psutil_mod = sys.modules.get("psutil")
    if psutil_mod is not None:
        try:
            psutil_logical = psutil_mod.cpu_count(logical=True)
            psutil_physical = psutil_mod.cpu_count(logical=False)
        except Exception:  # noqa: BLE001
            pass
    result["cpu_count_psutil_logical"] = psutil_logical
    result["cpu_count_psutil_physical"] = psutil_physical

    torch_threads: Any = None
    torch_interop: Any = None
    torch_mod = _torch_if_loaded()
    if torch_mod is not None:
        try:
            torch_threads = torch_mod.get_num_threads()
            torch_interop = torch_mod.get_num_interop_threads()
        except Exception:  # noqa: BLE001
            pass
    result["torch_threads"] = torch_threads
    result["torch_interop_threads"] = torch_interop

    for env_key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        result[env_key.lower()] = os.environ.get(env_key)


# ---------------------------------------------------------------------------
# 1C. lscpu
# ---------------------------------------------------------------------------

def _sanitize_lscpu_field(name: str) -> str:
    name = (name or "").strip()
    if name.endswith(":"):
        name = name[:-1].strip()
    if name.endswith("(s)"):
        name = name[:-3].strip()
    return name


def read_lscpu() -> dict:
    """Run ``lscpu -J`` (timeout 8s) and extract key fields; never raises."""
    try:
        proc = subprocess.run(
            ["lscpu", "-J"],
            timeout=_LSCPU_TIMEOUT_S,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {"lscpu_status": "unavailable", "lscpu_reason": "FileNotFoundError"}
    except subprocess.TimeoutExpired:
        return {"lscpu_status": "unavailable", "lscpu_reason": "TimeoutExpired"}
    except OSError as exc:
        return {"lscpu_status": "unavailable", "lscpu_reason": f"OSError:{exc.__class__.__name__}"}
    if proc.returncode != 0:
        return {"lscpu_status": "unavailable", "lscpu_reason": f"nonzero_exit:{proc.returncode}"}

    try:
        payload = json.loads(proc.stdout or "")
    except Exception:
        return {"lscpu_status": "unavailable", "lscpu_reason": "json_parse_error"}

    entries = payload.get("lscpu") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return {"lscpu_status": "unavailable", "lscpu_reason": "unexpected_shape"}

    parsed_fields: dict[str, Any] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field")
        data = entry.get("data")
        if field is None:
            continue
        parsed_fields[_sanitize_lscpu_field(str(field))] = data

    out: dict[str, Any] = {"lscpu_status": "available"}
    for sanitized, canonical in _LSCPU_TO_CANONICAL.items():
        if sanitized in parsed_fields:
            out[canonical] = parsed_fields[sanitized]
    return out


# ---------------------------------------------------------------------------
# 1D. Direct CPUID (cheap probes only; no /dev/cpu, no native builds)
# ---------------------------------------------------------------------------

def _quiet_call(fn, *args: Any, **kwargs: Any) -> Any:
    """Call *fn* with stdout/stderr suppressed; returns None on any error."""
    sink = io.StringIO()
    try:
        with redirect_stdout(sink), redirect_stderr(sink):
            return fn(*args, **kwargs)
    except Exception:
        return None


def try_direct_cpuid() -> dict:
    """Best-effort CPUID identity via the cpuinfo/cpuid modules; never raises."""
    out: dict[str, Any] = {
        "cpuid_status": "unavailable",
        "cpuid_source": None,
        "cpuid_vendor": None,
        "cpuid_brand": None,
        "cpuid_family": None,
        "cpuid_model": None,
        "cpuid_stepping": None,
        "cpuid_flags": None,
    }

    if importlib.util.find_spec("cpuinfo") is not None:
        info = _quiet_call(_py_cpuinfo_query)
        if isinstance(info, dict) and info.get("brand_raw"):
            flags = info.get("flags")
            if isinstance(flags, str):
                flags = flags.split()
            if not isinstance(flags, (list, tuple)):
                flags = []
            out.update({
                "cpuid_status": "available",
                "cpuid_source": "cpuinfo",
                "cpuid_vendor": info.get("vendor_id_raw") or None,
                "cpuid_brand": info.get("brand_raw") or None,
                "cpuid_family": info.get("family") or None,
                "cpuid_model": info.get("model") or None,
                "cpuid_stepping": info.get("stepping") or None,
                "cpuid_flags": ",".join(str(flag) for flag in flags) if flags else None,
            })
            return out

    if importlib.util.find_spec("cpuid") is not None:
        info = _quiet_call(_cpuid_module_query)
        if isinstance(info, dict) and (info.get("brand") or info.get("vendor")):
            flags = info.get("flags")
            if isinstance(flags, str):
                flags = flags.split()
            if not isinstance(flags, (list, tuple)):
                flags = []
            out.update({
                "cpuid_status": "available",
                "cpuid_source": "cpuid",
                "cpuid_vendor": info.get("vendor") or info.get("vendor_id") or None,
                "cpuid_brand": info.get("brand") or info.get("brand_raw") or None,
                "cpuid_family": info.get("family") or None,
                "cpuid_model": info.get("model") or None,
                "cpuid_stepping": info.get("stepping") or None,
                "cpuid_flags": ",".join(str(flag) for flag in flags) if flags else None,
            })
    return out


def _py_cpuinfo_query() -> Any:
    import cpuinfo
    return cpuinfo.get_cpu_info()


def _cpuid_module_query() -> Any:
    import cpuid
    return cpuid.cpu_info()


# ---------------------------------------------------------------------------
# 2. Identity comparison + confidence
# ---------------------------------------------------------------------------

def _norm_identity(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _cpu_identity_sources_agree(parsed: dict, lscpu: dict, cpuid: dict) -> bool | None:
    sources: list[dict[str, Any]] = []
    if any(parsed.get(key) is not None for key in ("vendor_id", "cpu_family", "cpu_model")):
        sources.append({
            "vendor": parsed.get("vendor_id"),
            "family": parsed.get("cpu_family"),
            "model": parsed.get("cpu_model"),
        })
    if lscpu.get("lscpu_status") == "available" and any(
            lscpu.get(key) is not None for key in ("vendor_id", "cpu_family", "cpu_model")):
        sources.append({
            "vendor": lscpu.get("vendor_id"),
            "family": lscpu.get("cpu_family"),
            "model": lscpu.get("cpu_model"),
        })
    if cpuid.get("cpuid_status") == "available":
        sources.append({
            "vendor": cpuid.get("cpuid_vendor"),
            "family": cpuid.get("cpuid_family"),
            "model": cpuid.get("cpuid_model"),
        })
    if len(sources) < 2:
        return None
    comparable = 0
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            left, right = sources[i], sources[j]
            for field in ("vendor", "family", "model"):
                lv = _norm_identity(left.get(field))
                rv = _norm_identity(right.get(field))
                if lv is None or rv is None:
                    continue
                comparable += 1
                if lv != rv:
                    return False
    if comparable == 0:
        return None
    return True


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _cpu_count_sources_agree(parsed: dict, result: dict, lscpu: dict) -> bool | None:
    values: list[int] = []
    proc_count = _to_int(parsed.get("cpu_count_proc"))
    if proc_count is not None:
        values.append(proc_count)
    os_count = _to_int(result.get("cpu_count_os"))
    if os_count is not None:
        values.append(os_count)
    lscpu_count = _to_int(lscpu.get("cpu_count"))
    if lscpu_count is not None:
        values.append(lscpu_count)
    if len(values) < 2:
        return None
    return len(set(values)) == 1


def _cpu_features_source(parsed: dict, cpuid: dict) -> str:
    if cpuid.get("cpuid_status") == "available" and cpuid.get("cpuid_flags"):
        return "cpuid"
    if parsed.get("cpu_flags"):
        return "proc_cpuinfo"
    return "none"


def _detect_synthetic(parsed: dict) -> bool:
    model_name = parsed.get("cpu_model_name")
    if isinstance(model_name, str) and model_name.strip().lower() == "unknown":
        return True
    siblings = parsed.get("cpu_siblings")
    count = parsed.get("cpu_count_proc")
    physical_id = parsed.get("cpu_physical_id")
    if siblings is not None and count is not None and _to_int(siblings) == _to_int(count):
        if physical_id is not None and str(physical_id).strip() == "0":
            return True
    return False


def _cpu_identity_confidence(parsed: dict, result: dict) -> str:
    has_cpuinfo = any(
        parsed.get(key) is not None for key in ("vendor_id", "cpu_family", "cpu_model")
    )
    if not has_cpuinfo:
        return "unavailable"
    if _detect_synthetic(parsed):
        return "virtualized_or_inconsistent"

    agree = result.get("cpu_identity_sources_agree")
    if agree is True:
        return "multi_source_consistent"
    if agree is False:
        return "virtualized_or_inconsistent"

    sources_present = 1
    if result.get("lscpu_status") == "available" and any(
            result.get(key) is not None for key in ("lscpu_vendor_id", "lscpu_cpu_family", "lscpu_cpu_model")):
        sources_present += 1
    if result.get("cpuid_status") == "available":
        sources_present += 1
    if sources_present <= 1:
        return "proc_only"
    return "virtualized_or_inconsistent"


# ---------------------------------------------------------------------------
# 3. GPU / PCIe
# ---------------------------------------------------------------------------

def _hash16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def _torch_gpu_identity() -> dict:
    """Tier A static GPU identity from already-loaded torch; zero driver calls.

    torch is warm in the container (sys.modules gate), so this is microsecond
    work.  A ctypes NVML probe was removed from the healthy path because
    nvmlInit/library load is slow under gVisor (~400 ms measured) and the
    max-link NVML calls are unsupported under nvproxy.  PCIe gen/width, UUID
    and driver version are Tier B only (via nvidia-smi, which works there).
    Never raises.
    """
    torch_mod = _torch_if_loaded()
    result: dict[str, Any] = {
        "gpu_name": None,
        "gpu_static_source": "unavailable",
        "torch_device_capability": None,
        "torch_total_memory_bytes": None,
        "torch_multi_processor_count": None,
    }
    if torch_mod is None:
        return result
    try:
        if not torch_mod.cuda.is_available():
            return result
        name = torch_mod.cuda.get_device_name(0)
        props = torch_mod.cuda.get_device_properties(0)
        result["gpu_static_source"] = "torch_only"
        if name:
            result["gpu_name"] = str(name)
        result["torch_device_capability"] = f"{props.major}.{props.minor}"
        result["torch_total_memory_bytes"] = int(props.total_memory)
        result["torch_multi_processor_count"] = int(props.multi_processor_count)
    except Exception:  # noqa: BLE001
        pass
    return result


def nvidia_gpu_snapshot() -> dict:
    """GPU snapshot via pynvml or the nvidia-smi fallback chain.

    Successful snapshots are cached 2s; failures (gpu_source unavailable) are
    cached 5s so the next phase snapshot retries the probe.
    """
    global _GPU_CACHE, _GPU_CACHE_AT
    now = time.monotonic()
    if _GPU_CACHE is not None:
        ttl = _GPU_FAIL_TTL_S if _GPU_CACHE.get("gpu_source") == "unavailable" else _GPU_CACHE_TTL_S
        if now - _GPU_CACHE_AT < ttl:
            return dict(_GPU_CACHE)
    result = _nvidia_gpu_query_now()
    _GPU_CACHE = result
    _GPU_CACHE_AT = now
    return dict(result)


def _empty_gpu_snapshot() -> dict[str, Any]:
    return {
        "gpu_source": "unavailable",
        "gpu_query_wall_ms": 0.0,
        "gpu_error": None,
        "gpu_pcie_error": None,
        "gpu_uuid_hash": None,
        "gpu_name": None,
        "gpu_driver_version": None,
        "gpu_index": None,
        "gpu_pci_bus": None,
        "gpu_pcie_gen_current": None,
        "gpu_pcie_gen_max": None,
        "gpu_pcie_width_current": None,
        "gpu_pcie_width_max": None,
        "gpu_pstate": None,
        "gpu_sm_clock_mhz": None,
        "gpu_mem_clock_mhz": None,
        "gpu_power_w": None,
        "gpu_util": None,
        "gpu_mem_util": None,
        "gpu_bar1_used_mib": None,
    }


def _nvidia_gpu_query_now() -> dict:
    wall_start = time.monotonic()
    nvml_error: str | None = None
    try:
        nvml_result = _nvml_query()
        if nvml_result.get("gpu_source") == "nvml":
            nvml_result["gpu_query_wall_ms"] = round((time.monotonic() - wall_start) * 1000, 2)
            return nvml_result
        nvml_error = nvml_result.get("gpu_error")
    except Exception:
        pass
    result = _nvidia_smi_query()
    result["gpu_query_wall_ms"] = round((time.monotonic() - wall_start) * 1000, 2)
    if result.get("gpu_source") == "unavailable" and not result.get("gpu_error") and nvml_error:
        result["gpu_error"] = f"nvml:{nvml_error}"
    return result


def _nvml_query() -> dict:
    out = _empty_gpu_snapshot()
    try:
        import pynvml
    except Exception:
        out["gpu_error"] = "nvml unavailable (pynvml import failed)"
        return out
    try:
        pynvml.nvmlInit()
    except Exception:
        out["gpu_error"] = "nvml init failed"
        return out
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    except Exception:
        out["gpu_error"] = "nvml device handle failed"
        return out
    out["gpu_source"] = "nvml"
    out["gpu_index"] = 0

    try:
        out["gpu_name"] = str(pynvml.nvmlDeviceGetName(handle))
    except Exception:
        pass
    try:
        raw_uuid = str(pynvml.nvmlDeviceGetUUID(handle))
        if raw_uuid:
            out["gpu_uuid_hash"] = _hash16(raw_uuid)
    except Exception:
        pass
    try:
        pci = pynvml.nvmlDeviceGetPciInfo(handle)
        out["gpu_pci_bus"] = str(pci.busId)
    except Exception:
        pass

    gen_curr = getattr(pynvml, "nvmlDeviceGetCurrLinkGen", None)
    if gen_curr is None:
        gen_curr = getattr(pynvml, "nvmlDeviceGetPciLinkGen", None)
    try:
        if gen_curr is not None:
            out["gpu_pcie_gen_current"] = int(gen_curr(handle))
    except Exception:
        pass
    gen_max = getattr(pynvml, "nvmlDeviceGetMaxLinkGen", None)
    try:
        if gen_max is not None:
            out["gpu_pcie_gen_max"] = int(gen_max(handle))
    except Exception:
        pass
    try:
        out["gpu_pcie_width_current"] = int(pynvml.nvmlDeviceGetPciLinkWidth(handle))
    except Exception:
        pass
    try:
        out["gpu_pcie_width_max"] = int(pynvml.nvmlDeviceGetMaxPciLinkWidth(handle))
    except Exception:
        pass

    try:
        pstate = pynvml.nvmlDeviceGetCurrentPstate(handle)
        out["gpu_pstate"] = "P{}".format(int(pstate))
    except Exception:
        pass
    try:
        out["gpu_sm_clock_mhz"] = float(pynvml.nvmlDeviceGetClockInfo(handle, 1))
    except Exception:
        pass
    try:
        out["gpu_mem_clock_mhz"] = float(pynvml.nvmlDeviceGetClockInfo(handle, 2))
    except Exception:
        pass
    try:
        out["gpu_power_w"] = round(float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0, 2)
    except Exception:
        pass
    try:
        rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
        out["gpu_util"] = int(rates.gpu)
        out["gpu_mem_util"] = int(rates.memory)
    except Exception:
        pass
    try:
        bar1 = pynvml.nvmlDeviceGetBAR1MemoryInfo(handle)
        out["gpu_bar1_used_mib"] = round(float(bar1.bar1Used) / (1024.0 * 1024.0), 2)
    except Exception:
        pass
    try:
        out["gpu_driver_version"] = str(pynvml.nvmlDeviceGetDriverVersion())
    except Exception:
        pass
    return out


def _parse_nvidia_number(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    lowered = text.lower()
    if not text or lowered in ("n/a", "[n/a]", "[not supported]", "unknown", "[unknown error]"):
        return None
    if "unknown error" in lowered:
        return None
    for suffix in (" mib", "mib", " w", "w"):
        if text.lower().endswith(suffix):
            text = text[:-len(suffix)].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _truncate_error(message: str | None) -> str | None:
    if not message:
        return None
    return str(message)[-300:]


def _smi_row_usable(fields: list[str]) -> bool:
    stripped = [field.strip() for field in fields]
    if len(stripped) < 2:
        return False
    return bool(stripped[0] or stripped[1])


def _apply_smi_fields(out: dict, level: str, fields: list[str]) -> None:
    for index, key, kind in _SMI_FIELD_MAPS[level]:
        if index >= len(fields):
            continue
        raw = fields[index].strip()
        if not raw or raw.lower() in ("n/a", "[n/a]", "[not supported]", "unknown", "[unknown error]"):
            continue
        if "unknown error" in raw.lower():
            continue
        if kind == "str":
            out[key] = raw
        elif kind == "uuid":
            out[key] = _hash16(raw)
        elif kind == "int":
            parsed = _parse_nvidia_number(raw)
            if parsed is not None:
                out[key] = int(parsed)
        elif kind in ("num", "util", "bar1"):
            parsed = _parse_nvidia_number(raw)
            if parsed is not None:
                if kind == "util":
                    out[key] = int(parsed)
                elif kind == "bar1":
                    out[key] = round(float(parsed), 2)
                else:
                    out[key] = parsed


def _maybe_probe_pcie(out: dict) -> None:
    """Standalone PCIe probe when the winning level carried no PCIe data.

    Runs exactly once, only when ``gpu_pcie_gen_current`` is still None after
    a successful nvidia-smi level.  Never raises; on any failure the pcie
    fields stay None and ``gpu_pcie_error`` explains why.  A usable row sets
    the pcie fields and leaves ``gpu_pcie_error`` at None.
    """
    if out.get("gpu_source") != "nvidia_smi" or out.get("gpu_pcie_gen_current") is not None:
        return
    try:
        proc = subprocess.run(
            ["nvidia-smi", f"--query-gpu={_SMI_QUERY_PCIE}", "--format=csv,noheader,nounits"],
            timeout=_NVIDIA_SMI_TIMEOUT_S,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        out["gpu_pcie_error"] = "nvidia-smi not found"
        return
    except subprocess.TimeoutExpired:
        out["gpu_pcie_error"] = "timeout"
        return
    except (OSError, subprocess.SubprocessError) as exc:
        out["gpu_pcie_error"] = _truncate_error(f"subprocess error: {exc.__class__.__name__}")
        return

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "").strip()
        stdout_tail = (proc.stdout or "").strip()
        detail = _truncate_error(stderr_tail) or _truncate_error(stdout_tail)
        out["gpu_pcie_error"] = detail or f"exit {proc.returncode}"
        return

    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if not lines:
        out["gpu_pcie_error"] = "nvidia-smi empty output"
        return
    fields = [field.strip() for field in lines[0].split(",")]
    if len(fields) < 4:
        out["gpu_pcie_error"] = "nvidia-smi unparseable output"
        return
    _apply_smi_fields(out, "pcie", fields)
    if out.get("gpu_pcie_gen_current") is None:
        out["gpu_pcie_error"] = "pcie fields unavailable"


def _nvidia_smi_query() -> dict:
    """nvidia-smi with a FULL -> CORE -> MINIMAL fallback chain + PCIe probe.

    Each level runs once (timeout 10s).  Nonzero exit or an unparseable row
    falls through to the next level, remembering the last stderr for
    ``gpu_error``.  FileNotFoundError/timeout abort immediately.  The first
    level yielding a usable row wins (at most 3 spawns); when that level
    carried no usable PCIe data a single standalone PCIe probe runs.
    """
    out = _empty_gpu_snapshot()
    last_error: str | None = None

    for level, query in _SMI_QUERIES:
        try:
            proc = subprocess.run(
                ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
                timeout=_NVIDIA_SMI_TIMEOUT_S,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            out["gpu_error"] = "nvidia-smi not found"
            return out
        except subprocess.TimeoutExpired:
            out["gpu_error"] = "timeout"
            return out
        except (OSError, subprocess.SubprocessError) as exc:
            out["gpu_error"] = _truncate_error(f"subprocess error: {exc.__class__.__name__}")
            return out

        if proc.returncode != 0:
            stderr_tail = (proc.stderr or "").strip()
            stdout_tail = (proc.stdout or "").strip()
            detail = _truncate_error(stderr_tail) or _truncate_error(stdout_tail)
            last_error = detail or f"nvidia-smi exit {proc.returncode}"
            continue

        lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
        if not lines:
            last_error = "nvidia-smi empty output"
            continue
        fields = [field.strip() for field in lines[0].split(",")]
        if not _smi_row_usable(fields):
            last_error = "nvidia-smi unparseable output"
            continue

        out["gpu_source"] = "nvidia_smi"
        _apply_smi_fields(out, level, fields)
        if last_error is not None:
            out["gpu_error"] = last_error
        _maybe_probe_pcie(out)
        return out

    out["gpu_source"] = "unavailable"
    out["gpu_error"] = _truncate_error(last_error)
    return out


# ---------------------------------------------------------------------------
# 4. PSI
# ---------------------------------------------------------------------------

def _parse_pressure(text: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        section = parts[0]
        if section not in ("some", "full"):
            continue
        fields: dict[str, Any] = {}
        for token in parts[1:]:
            if "=" not in token:
                continue
            key, _, value = token.partition("=")
            if key in ("avg10", "avg60", "avg300"):
                try:
                    fields[key] = float(value)
                except ValueError:
                    fields[key] = None
            elif key == "total":
                try:
                    fields[key] = int(value)
                except ValueError:
                    fields[key] = None
        if fields:
            out[section] = fields
    return out


def _read_pressure_once(path: str) -> tuple[dict | None, str | None]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return None, f"OSError:{exc.__class__.__name__}:{getattr(exc, 'errno', '?')}"
    except Exception as exc:
        return None, exc.__class__.__name__
    parsed = _parse_pressure(text)
    if not parsed:
        return None, "unparseable"
    return parsed, None


def read_psi() -> dict:
    """Read /proc/pressure/*; absent sources are 'unavailable', never zeros.

    On gVisor the whole /proc/pressure tree is absent, so a single
    ``os.path.exists`` gate replaces three ENOENT opens (one stat vs three
    syscalls under runsc).  When the tree exists the three files are read as
    before.  Also performs one cheap synthetic-detection check (two reads
    200 ms apart) and reports ``psi_looks_synthetic`` when all totals are
    identical.
    """
    out: dict[str, Any] = {}
    try:
        pressure_tree_present = os.path.exists("/proc/pressure")
    except Exception:  # noqa: BLE001
        pressure_tree_present = False
    if not pressure_tree_present:
        for source in _PSI_SOURCES:
            out[f"{source}_psi_status"] = "unavailable"
            out[f"{source}_psi_reason"] = "OSError:FileNotFoundError:2"
        out["psi_looks_synthetic"] = False
        out["psi_status"] = "unavailable"
        return out

    first_read: dict[str, dict | None] = {}

    for source in _PSI_SOURCES:
        path = f"/proc/pressure/{source}"
        parsed, reason = _read_pressure_once(path)
        if parsed is None:
            out[f"{source}_psi_status"] = "unavailable"
            out[f"{source}_psi_reason"] = reason
            first_read[source] = None
        else:
            out[f"{source}_psi_status"] = "available"
            for section in ("some", "full"):
                if section in parsed:
                    for key, value in parsed[section].items():
                        out[f"{source}_psi_{section}_{key}"] = value
            first_read[source] = parsed

    available = [source for source in _PSI_SOURCES if first_read.get(source) is not None]
    psi_looks_synthetic = False
    if available:
        try:
            time.sleep(0.2)
        except Exception:
            pass
        compared = 0
        all_identical = True
        for source in available:
            second, _ = _read_pressure_once(f"/proc/pressure/{source}")
            if second is None:
                continue
            first = first_read.get(source) or {}
            for section in ("some", "full"):
                first_total = (first.get(section) or {}).get("total")
                second_total = (second.get(section) or {}).get("total")
                if first_total is None or second_total is None:
                    continue
                compared += 1
                if first_total != second_total:
                    all_identical = False
        if compared and all_identical:
            psi_looks_synthetic = True
    out["psi_looks_synthetic"] = psi_looks_synthetic
    out["psi_status"] = "available" if available else "unavailable"
    return out


# ---------------------------------------------------------------------------
# 5. cgroup discovery (v2 preferred, v1 best-effort)
# ---------------------------------------------------------------------------

def _read_lines(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return [line.rstrip("\n") for line in fh]
    except Exception:
        return []


def _read_keyval_file(path: str) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2:
                    try:
                        out[parts[0]] = int(parts[1])
                    except ValueError:
                        out[parts[0]] = None
    except Exception:
        return None
    return out if out else None


def _read_int_file(path: str) -> int | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return int(fh.read().strip())
    except Exception:
        return None


def _read_head_snippet(path: str, nlines: int = 3, trunc: int = 200) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [line.strip() for line in fh if line.strip()]
    except Exception:
        return None
    if not lines:
        return None
    return " | ".join(line[:trunc] for line in lines[:nlines])


def _find_cgroup2_mount(mountinfo_lines: list[str]) -> str | None:
    for line in mountinfo_lines:
        parts = line.split()
        if len(parts) < 6:
            continue
        mount_point = parts[4]
        try:
            sep = line.index(" - ")
        except ValueError:
            continue
        after = line[sep + 3:].split()
        if after and after[0] == "cgroup2":
            return mount_point
    return None


def _cgroup_v2_rel_path(cgroup_lines: list[str]) -> str | None:
    for raw_line in cgroup_lines:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(":")
        if len(parts) == 3 and parts[0] == "0":
            return parts[2]
        if "::" in line:
            return line.split("::", 1)[1]
    return None


def _is_v1_style_with_path(cgroup_lines: list[str]) -> bool:
    """True when /proc/self/cgroup is v1-style (N:controllers:/path).

    Modal/gVisor serves sentry-internal v1-style lines whose paths are always
    non-empty, so this single-file check replaces the mountinfo + per-controller
    reads that carry no host signal there.
    """
    for raw_line in cgroup_lines:
        line = raw_line.strip()
        if not line or line.startswith("0::"):
            continue
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[0].strip().isdigit() and parts[0].strip() != "0":
            if parts[2]:
                return True
    return False


def _read_v2_fields(base: str, out: dict[str, Any]) -> None:
    cpu_stat = _read_keyval_file(os.path.join(base, "cpu.stat"))
    if cpu_stat is not None:
        for key in ("usage_usec", "user_usec", "system_usec", "nr_periods", "nr_throttled", "throttled_usec"):
            if cpu_stat.get(key) is not None:
                out[f"cgroup_cpu_{key}"] = cpu_stat.get(key)
    mem_current = _read_int_file(os.path.join(base, "memory.current"))
    if mem_current is not None:
        out["cgroup_memory_current"] = mem_current
    mem_events = _read_keyval_file(os.path.join(base, "memory.events"))
    if mem_events is not None:
        for key in ("low", "high", "max", "oom", "oom_kill"):
            if mem_events.get(key) is not None:
                out[f"cgroup_memory_events_{key}"] = mem_events.get(key)
    mem_stat = _read_keyval_file(os.path.join(base, "memory.stat"))
    if mem_stat is not None:
        for key in ("anon", "file", "pgfault", "pgmajfault"):
            if mem_stat.get(key) is not None:
                out[f"cgroup_memory_{key}"] = mem_stat.get(key)
    io_snippet = _read_head_snippet(os.path.join(base, "io.stat"), 3, 200)
    if io_snippet is not None:
        out["cgroup_io_stat_snippet"] = io_snippet


def read_cgroup_fields() -> dict:
    """Discover cgroup v2/v1; never raises.

    Healthy-path v1 detection uses /proc/self/cgroup ALONE: v1-style lines
    (``N:controllers:/path``) with a non-empty path are sentry-virtualized
    under Modal/gVisor, so we record the v1 signal and return WITHOUT reading
    mountinfo or per-controller files (they carry no host signal there).  v2
    (a ``0::/path`` line) does the full discovery: the cgroup2 mount from
    mountinfo plus the cpu.stat/memory.* subset as before.  Unreadable or
    unparseable -> ``cgroup_source="unavailable"``.
    """
    out: dict[str, Any] = {
        "cgroup_source": "unavailable",
        "cgroup_likely_virtualized": True,
        "cgroup_virtualization_reason": (
            "gVisor runsc serves sentry-internal cgroupfs; outer worker cgroup not visible"
        ),
        "cgroup_lines_snippet": None,
        "cgroup_rel_path": None,
        "cgroup_mount_point": None,
    }

    cgroup_lines = _read_lines("/proc/self/cgroup")
    if cgroup_lines:
        snippet_lines = [line.strip()[:200] for line in cgroup_lines[:2] if line.strip()]
        if snippet_lines:
            out["cgroup_lines_snippet"] = " | ".join(snippet_lines)

    if _is_v1_style_with_path(cgroup_lines):
        out["cgroup_source"] = "v1"
        return out

    v2_rel = _cgroup_v2_rel_path(cgroup_lines)
    if v2_rel is not None:
        mountinfo_lines = _read_lines("/proc/self/mountinfo")
        v2_mount = _find_cgroup2_mount(mountinfo_lines)
        if v2_mount is not None:
            out["cgroup_rel_path"] = v2_rel
            out["cgroup_mount_point"] = v2_mount
            base = os.path.join(v2_mount, v2_rel.lstrip("/")) if v2_rel != "/" else v2_mount
            out["cgroup_source"] = "v2"
            _read_v2_fields(base, out)
            return out
    return out


# ---------------------------------------------------------------------------
# 6. getrusage + /proc/self/stat
# ---------------------------------------------------------------------------

def rusage_snapshot() -> dict:
    """RUSAGE_SELF snapshot; every field is individually None on failure."""
    base: dict[str, Any] = {
        "rusage_status": "unavailable",
        "ru_utime": None, "ru_stime": None, "ru_minflt": None, "ru_majflt": None,
        "ru_nvcsw": None, "ru_nivcsw": None, "ru_maxrss": None,
    }
    try:
        import resource
    except Exception:
        return base
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
    except Exception:
        return base
    out: dict[str, Any] = {"rusage_status": "available"}
    for field in ("ru_utime", "ru_stime", "ru_minflt", "ru_majflt", "ru_nvcsw", "ru_nivcsw", "ru_maxrss"):
        try:
            value = getattr(usage, field)
            if field in ("ru_utime", "ru_stime"):
                out[field] = float(value)
            else:
                out[field] = int(value)
        except Exception:
            out[field] = None
    return out


def read_proc_self_stat() -> dict:
    """Parse /proc/self/stat (fields per proc_pid_stat(5)); never raises.

    After ``comm`` is stripped via rfind(')'), the split list starts at field 3
    (state), so each index is field_number - 3:
    minflt=10->7, majflt=12->9, utime=14->11, stime=15->12, num_threads=20->17.
    """
    out: dict[str, Any] = {
        "status": "unavailable",
        "pid": None, "comm": None, "state": None, "ppid": None,
        "minflt": None, "majflt": None, "utime_ticks": None, "stime_ticks": None,
        "num_threads": None,
        "ticks_per_sec": None,
    }
    try:
        ticks_per_sec = float(os.sysconf("SC_CLK_TCK"))
    except Exception:
        ticks_per_sec = 100.0
    out["ticks_per_sec"] = ticks_per_sec

    try:
        with open("/proc/self/stat", "r", encoding="utf-8") as fh:
            data = fh.read()
    except Exception:
        return out

    open_paren = data.find("(")
    close_paren = data.rfind(")")
    if open_paren < 0 or close_paren <= open_paren:
        return out
    try:
        pid_part = data[:open_paren].split()
        pid = int(pid_part[0]) if pid_part else None
    except Exception:
        pid = None
    comm = data[open_paren + 1:close_paren]
    after = data[close_paren + 1:].split()

    def _field(index: int) -> Any:
        try:
            return int(after[index])
        except Exception:
            return None

    out.update({
        "status": "available",
        "pid": pid,
        "comm": comm or None,
        "state": after[0] if len(after) > 0 else None,
        "ppid": _field(1),
        "minflt": _field(7),
        "majflt": _field(9),
        "utime_ticks": _field(11),
        "stime_ticks": _field(12),
        "num_threads": _field(17),
    })
    return out


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _ticks_to_ms(ticks: Any, ticks_per_sec: Any) -> float | None:
    if ticks is None or ticks_per_sec is None:
        return None
    try:
        return round(float(ticks) / float(ticks_per_sec) * 1000.0, 3)
    except Exception:
        return None


def _delta(previous: Any, current: Any) -> Any:
    if previous is None or current is None:
        return None
    try:
        return current - previous
    except Exception:
        return None


def _wall_delta_ms(previous_mono: float | None, current_mono: float) -> float | None:
    if previous_mono is None:
        return None
    return round((current_mono - previous_mono) * 1000.0, 2)


# ---------------------------------------------------------------------------
# Fingerprint helpers
# ---------------------------------------------------------------------------

def _flatten_cpuinfo(parsed: dict, result: dict[str, Any]) -> None:
    mapping = {
        "vendor_id": "cpu_vendor",
        "cpu_family": "cpu_family",
        "cpu_model": "cpu_model",
        "cpu_model_name": "cpu_model_name",
        "cpu_stepping": "cpu_stepping",
        "cpu_microcode": "cpu_microcode",
        "cpu_mhz": "cpu_mhz",
        "cpu_cache_size": "cpu_cache_size",
        "cpu_siblings": "cpu_siblings",
        "cpu_cores": "cpu_cores",
        "cpu_physical_id": "cpu_physical_id",
        "cpu_core_id": "cpu_core_id",
        "cpu_count_proc": "cpu_count_proc",
        "cpu_entries_homogeneous": "cpu_entries_homogeneous",
    }
    for source_key, dest_key in mapping.items():
        if parsed.get(source_key) is not None:
            result[dest_key] = parsed.get(source_key)
    flags = parsed.get("cpu_flags")
    result["cpu_flags"] = flags
    if flags:
        result["cpu_flags_hash"] = hashlib.sha256(flags.encode("utf-8", errors="replace")).hexdigest()[:16]
    else:
        result["cpu_flags_hash"] = None
    for feature in _FEATURE_TOKEN_MAP:
        result[feature] = parsed.get(feature)


def _flatten_lscpu(lscpu: dict, result: dict[str, Any]) -> None:
    mapping = {
        "architecture": "lscpu_architecture",
        "cpu_count": "lscpu_cpu_count",
        "vendor_id": "lscpu_vendor_id",
        "model_name": "lscpu_model_name",
        "cpu_family": "lscpu_cpu_family",
        "cpu_model": "lscpu_cpu_model",
        "threads_per_core": "lscpu_threads_per_core",
        "cores_per_socket": "lscpu_cores_per_socket",
        "sockets": "lscpu_sockets",
        "numa_nodes": "lscpu_numa_nodes",
        "numa_node0_cpus": "lscpu_numa_node0_cpus",
        "cache_l1d": "lscpu_cache_l1d",
        "cache_l1i": "lscpu_cache_l1i",
        "cache_l2": "lscpu_cache_l2",
        "cache_l3": "lscpu_cache_l3",
        "hypervisor_vendor": "lscpu_hypervisor_vendor",
        "flags": "lscpu_flags",
    }
    for source_key, dest_key in mapping.items():
        if lscpu.get(source_key) is not None:
            result[dest_key] = lscpu.get(source_key)
    result["lscpu_status"] = lscpu.get("lscpu_status")
    if lscpu.get("lscpu_status") != "available" and lscpu.get("lscpu_reason"):
        result["lscpu_reason"] = lscpu.get("lscpu_reason")


def _flatten_cpuid(cpuid: dict, result: dict[str, Any]) -> None:
    for key in ("cpuid_status", "cpuid_vendor", "cpuid_brand", "cpuid_family",
                "cpuid_model", "cpuid_stepping", "cpuid_flags", "cpuid_source"):
        result[key] = cpuid.get(key)


def _model_unknown(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() == "unknown"


def _build_probe_statuses(parsed: dict, lscpu: dict, cpuid: dict, psi: dict,
                          cgroup: dict, static_gpu: dict) -> str:
    has_proc = (parsed.get("cpu_count_proc") or 0) > 0 or any(
        parsed.get(key) is not None for key in ("vendor_id", "cpu_family", "cpu_model")
    )
    if not has_proc:
        proc_status = "UNAVAILABLE"
    elif _model_unknown(parsed.get("cpu_model_name")):
        proc_status = "AMBIGUOUS"
    else:
        proc_status = "AVAILABLE"

    if lscpu.get("lscpu_status") == "deferred":
        lscpu_status = "DEFERRED"
    elif lscpu.get("lscpu_status") == "available":
        lscpu_status = "AMBIGUOUS" if _model_unknown(lscpu.get("model_name")) else "AVAILABLE"
    else:
        lscpu_status = "BLOCKED"

    cpuid_status = "AVAILABLE" if cpuid.get("cpuid_status") == "available" else "UNAVAILABLE"
    psi_status = "AVAILABLE" if psi.get("psi_status") == "available" else "UNAVAILABLE"
    cgroup_status = str(cgroup.get("cgroup_source") or "UNAVAILABLE")
    gpu_status = "AVAILABLE" if static_gpu.get("gpu_static_source") == "torch_only" else "UNAVAILABLE"
    if lscpu.get("lscpu_status") == "deferred":
        numa_status = "DEFERRED"
    else:
        numa_status = "AVAILABLE" if lscpu.get("numa_nodes") is not None else "UNAVAILABLE"

    return ";".join([
        f"proc_cpuinfo={proc_status}",
        f"lscpu={lscpu_status}",
        f"cpuid={cpuid_status}",
        f"psi={psi_status}",
        f"cgroup={cgroup_status}",
        f"gpu_static={gpu_status}",
        f"numa={numa_status}",
    ])
