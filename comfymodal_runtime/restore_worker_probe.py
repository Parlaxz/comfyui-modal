"""Restore-worker diagnostics: runtime fingerprint, watcher, snapshot capture/restore.

stdlib + /proc only — no psutil/numpy/pandas/torch/transformers imports.
Best-effort, narrow try/except, missing → absent/unavailable.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import platform
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# ── Module-level snapshot capture fingerprint ─────────────────────────
_V2_SNAPSHOT_CAPTURE_FINGERPRINT: dict[str, Any] = {}

# ── Restore entry one-shot lock ───────────────────────────────────────
_RESTORE_ONE_SHOT_LOCK: threading.Lock = threading.Lock()
_RESTORE_ONE_SHOT_CLAIMED: bool = False


# ── Process identity ──────────────────────────────────────────────────

@dataclass
class ProcessIdentity:
    pid: int | None = None
    ppid: int | None = None
    sid: int | None = None
    process_group: int | None = None
    hostname: str = ""
    boot_id: str = ""
    modal_task_id: str = ""
    modal_image_id: str = ""
    modal_cloud_provider: str = ""
    modal_region: str = ""
    container_session_id: str = ""


@dataclass
class CpuIdentity:
    affinity: list[int] = field(default_factory=list)
    affinity_count: int = 0
    machine: str = ""
    kernel: str = ""
    cpu_model: str = ""
    cpu_model_clean: str = ""
    cpu_model_hash: str = ""
    cpu_model_hash_full: str = ""
    cpu_flags_hash: str = ""
    cpu_flags_hash_full: str = ""


@dataclass
class NativeLibInfo:
    basenames: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class ThreadInfo:
    tid: int
    starttime_ticks: int = 0


@dataclass
class ProcessInfo:
    pid: int
    nspid: list[int] = field(default_factory=list)
    cmdline: str = ""
    starttime_ticks: int | None = None


@dataclass
class RuntimeFingerprint:
    identity: ProcessIdentity = field(default_factory=ProcessIdentity)
    cpu: CpuIdentity = field(default_factory=CpuIdentity)
    env: dict[str, str] = field(default_factory=dict)
    torch_version: str = ""
    torch_state: dict[str, Any] = field(default_factory=dict)
    native_libs: NativeLibInfo = field(default_factory=NativeLibInfo)
    python_threads: list[dict[str, Any]] = field(default_factory=list)
    proc_task_records: list[dict[str, Any]] = field(default_factory=list)
    visible_processes: list[ProcessInfo] = field(default_factory=list)
    coordinator_state: dict[str, Any] = field(default_factory=dict)
    bridge_snapshot: dict[str, Any] = field(default_factory=dict)
    rusage: dict[str, Any] = field(default_factory=dict)
    memory_status: dict[str, Any] = field(default_factory=dict)
    wall_unix_ns: int = 0
    mono_ns: int = 0


# ── Phase tracking (thread-safe) ──────────────────────────────────────

_PHASE_LOCK: threading.Lock = threading.Lock()
_CURRENT_PHASE: str = "probe_initialized"


def _get_phase() -> str:
    with _PHASE_LOCK:
        return _CURRENT_PHASE


# Phase constants for set_restore_worker_probe_phase
_PHASE_RESTORE_ENTRY = "restore_entry"
_PHASE_CONFIGURE_RUNTIME = "configure_runtime"
_PHASE_RESTORE_PLAN_READ = "restore_plan_read"
_PHASE_BOOTSTRAP_RESTORE = "bootstrap_restore"
_PHASE_SNAPSHOT_IDENTITY_VALIDATION = "snapshot_identity_validation"
_PHASE_SNAPSHOT_RETARGET = "snapshot_retarget"
_PHASE_SNAPSHOT_BRIDGE_ACTIVATION = "snapshot_bridge_activation"
_PHASE_RESTORE_FINALIZATION = "restore_finalization"
_PHASE_RESTORE_RETURNED = "restore_returned"
_PHASE_RUN_PLAN_STREAM_ENTRY = "run_plan_stream_entry"
_PHASE_PLAN_MATERIALIZATION = "plan_materialization"
_PHASE_PROMPT_EXECUTOR_ENTRY = "prompt_executor_entry"
_PHASE_CLIP_ENCODE = "clip_encode"
_PHASE_UNET_GPU_ACTIVATION = "unet_gpu_activation"
_PHASE_SAMPLER = "sampler"
_PHASE_PROBE_COMPLETE = "probe_complete"


# ── /proc stat parser (robust, handles spaces/parentheses in comm) ─---

def _parse_proc_stat(text: str) -> dict[str, Any] | None:
    """Parse /proc/.../stat robustly despite parens/spaces in comm."""
    try:
        close_paren = text.rfind(")")
        if close_paren == -1:
            return None
        # Extract comm from between last '(' and last ')'
        open_paren = text.find("(")
        if open_paren == -1 or open_paren >= close_paren:
            comm_str = ""
        else:
            comm_str = text[open_paren + 1:close_paren]
        body = text[close_paren + 2:]
        parts = body.split()
        if len(parts) < 44:
            return None
        out: dict[str, Any] = {}
        try:
            out["pid"] = int(text[:text.find(" ")].strip())
        except (ValueError, IndexError):
            out["pid"] = None
        # state = parts[0] (single char after ") ")
        out["state"] = parts[0] if len(parts) > 0 else ""
        out["comm"] = comm_str[:64]
        try:
            out["ppid"] = int(parts[1])
        except (ValueError, IndexError):
            out["ppid"] = None
        try:
            out["pgrp"] = int(parts[2])
        except (ValueError, IndexError):
            out["pgrp"] = None
        try:
            out["session"] = int(parts[3])
        except (ValueError, IndexError):
            out["session"] = None
        try:
            out["utime"] = int(parts[11])
        except (ValueError, IndexError):
            out["utime"] = None
        try:
            out["stime"] = int(parts[12])
        except (ValueError, IndexError):
            out["stime"] = None
        try:
            out["starttime"] = int(parts[19])
        except (ValueError, IndexError):
            out["starttime"] = None
        try:
            out["thread_nr"] = int(parts[17])
        except (ValueError, IndexError):
            out["thread_nr"] = None
        # processor = parts[38] on Linux 3.x+, fallback to -1
        try:
            out["processor"] = int(parts[38])
        except (ValueError, IndexError):
            out["processor"] = -1
        return out
    except Exception:
        return None


def _read_proc_stat_file(path: str) -> dict[str, Any] | None:
    try:
        with open(path) as f:
            return _parse_proc_stat(f.read())
    except Exception:
        return None


def _read_nspid(pid: int) -> list[int]:
    """Read NSpid from /proc/<pid>/status."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("NSpid:"):
                    parts = line.split()
                    return [int(p) for p in parts[1:] if p.isdigit()]
    except Exception:
        pass
    return []


def _read_cmdline(pid: int, max_len: int = 120) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read(512)
        cmd = raw.replace(b"\x00", b" ").decode("ascii", errors="replace")
        cmd = " ".join(cmd.split())
        if len(cmd) > max_len:
            cmd = cmd[: max_len - 3] + "..."
        return cmd
    except Exception:
        return ""


def _get_affinity() -> tuple[list[int], int]:
    try:
        aff = sorted(os.sched_getaffinity(0))
        return aff, len(aff)
    except Exception:
        return [], os.cpu_count() or 0


def _get_boot_id() -> str:
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()[:36]
    except Exception:
        return ""


def _get_sc_clk_tck() -> int:
    try:
        return os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    except Exception:
        return 100


# ── Safe torch inspection (sys.modules only) ──────────────────────────

def _safe_torch_version() -> str:
    try:
        torch_mod = sys.modules.get("torch")
        if torch_mod is not None:
            return str(getattr(torch_mod, "__version__", ""))
    except Exception:
        pass
    return ""


def _collect_torch_state() -> dict[str, Any]:
    """Fingerprint already-loaded torch from sys.modules only.
    Returns sanitized/truncated values including version, cuda, parallel_info,
    get_num_threads/get_num_interop_threads. Never touches CUDA APIs."""
    state: dict[str, Any] = {}
    try:
        torch_mod = sys.modules.get("torch")
        if torch_mod is None:
            return {"status": "absent"}
        state["version"] = str(getattr(torch_mod, "__version__", ""))[:40]
        # Thread counts
        try:
            state["num_threads"] = int(getattr(torch_mod, "get_num_threads", lambda: -1)())
        except Exception:
            state["num_threads"] = -1
        try:
            state["num_interop_threads"] = int(getattr(torch_mod, "get_num_interop_threads", lambda: -1)())
        except Exception:
            state["num_interop_threads"] = -1
        # CUDA info (torch.version.cuda only, no cuda.is_available())
        torch_version = getattr(torch_mod, "__version__", None)
        state["cuda_version"] = str(getattr(getattr(torch_mod, "version", None), "cuda", ""))[:24]
        # Parallel info via torch.__config__.parallel_info()
        config_mod = getattr(torch_mod, "__config__", None)
        if config_mod is not None:
            pi_fn = getattr(config_mod, "parallel_info", None)
            if callable(pi_fn):
                try:
                    state["parallel_info"] = str(pi_fn())[:120]
                except Exception:
                    state["parallel_info"] = ""
            else:
                state["parallel_info"] = ""
        # Fallback: direct parallel_info on torch module
        if not state.get("parallel_info"):
            parallel_info = getattr(torch_mod, "parallel_info", None)
            if callable(parallel_info):
                try:
                    state["parallel_info"] = str(parallel_info())[:120]
                except Exception:
                    state["parallel_info"] = ""
        # Backend info - truncated/hashed counts
        backends = getattr(torch_mod, "backends", None)
        if backends is not None:
            backends_info: dict[str, Any] = {}
            for bname in ("cudnn", "mkl", "mkldnn", "openmp", "nccl", "xpu"):
                bmod = getattr(backends, bname, None)
                if bmod is not None:
                    b_avail = getattr(bmod, "is_available", None)
                    if callable(b_avail):
                        try:
                            backends_info[bname] = bool(b_avail())
                        except Exception:
                            backends_info[bname] = None
            if backends_info:
                state["backends"] = backends_info
        state["status"] = "loaded"
    except Exception:
        state = {"status": "error"}
    return state


# ── Native library basenames from /proc/self/maps ──────────────────────

_MAX_MAP_LIBS = 256


def _collect_native_libs() -> NativeLibInfo:
    """Collect unique native library basenames from /proc/self/maps."""
    seen: set[str] = set()
    truncated = False
    try:
        with open("/proc/self/maps") as f:
            for line in f:
                if len(seen) >= _MAX_MAP_LIBS:
                    truncated = True
                    break
                parts = line.split()
                if len(parts) >= 6:
                    path = parts[-1].strip()
                    if path and path != "0" and "/" in path:
                        base = path.rsplit("/", 1)[-1]
                        if base and base not in seen and not base.startswith("libpython"):
                            seen.add(base)
        return NativeLibInfo(basenames=sorted(seen), truncated=truncated)
    except Exception:
        return NativeLibInfo()


# ── Python thread enumeration ─────────────────────────────────────────

def _enumerate_python_threads() -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    try:
        for t in threading.enumerate():
            threads.append({
                "name": str(t.name)[:80],
                "ident": t.ident,
                "native_id": t.native_id,
                "daemon": t.daemon,
                "alive": t.is_alive(),
            })
    except Exception:
        pass
    return threads


# ── /proc/self/task enumeration ────────────────────────────────────────

_MAX_TASK_ENTRIES = 512


def _enumerate_proc_task(clk_tck: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        for entry in os.listdir("/proc/self/task"):
            if len(records) >= _MAX_TASK_ENTRIES:
                break
            tid = entry
            stat = _read_proc_stat_file(f"/proc/self/task/{tid}/stat")
            if stat is not None:
                rec: dict[str, Any] = {
                    "tid": tid,
                    "comm": stat.get("comm", ""),
                    "state": stat.get("state", ""),
                    "ppid": stat.get("ppid"),
                    "utime": stat.get("utime"),
                    "stime": stat.get("stime"),
                    "starttime": stat.get("starttime"),
                    "processor": stat.get("processor", -1),
                    "cpu_ms": round(((stat.get("utime", 0) or 0) + (stat.get("stime", 0) or 0)) * 1000.0 / clk_tck, 3) if clk_tck else None,
                }
                # Read task children
                try:
                    with open(f"/proc/self/task/{tid}/children") as cf:
                        child_text = cf.read().strip()
                        if child_text:
                            rec["children"] = [int(x) for x in child_text.split() if x.isdigit()]
                        else:
                            rec["children"] = []
                except Exception:
                    rec["children"] = []
                records.append(rec)
    except Exception:
        pass
    return records


# ── Visible /proc processes ───────────────────────────────────────────

_MAX_VISIBLE_PIDS = 256


def _enumerate_visible_processes(pid: int, clk_tck: int) -> list[ProcessInfo]:
    infos: list[ProcessInfo] = []
    try:
        for entry in os.listdir("/proc/"):
            if not entry.isdigit():
                continue
            if len(infos) >= _MAX_VISIBLE_PIDS:
                break
            opid = int(entry)
            # Keep self in visible process tree per fingerprint spec;
            # caller can differentiate via ProcessIdentity.pid
            stat = _read_proc_stat_file(f"/proc/{opid}/stat")
            nspid = _read_nspid(opid)
            cmdline = _read_cmdline(opid, max_len=160)
            starttime = stat.get("starttime") if stat else None
            state = stat.get("state", "") if stat else ""
            comm = stat.get("comm", "") if stat else ""
            ppid = stat.get("ppid") if stat else None
            infos.append(ProcessInfo(
                pid=opid,
                nspid=nspid,
                cmdline=cmdline[:160],
                starttime_ticks=starttime,
            ))
            # Extend info dict for richer records
            if hasattr(infos[-1], "__dict__"):
                infos[-1].__dict__["state"] = state
                infos[-1].__dict__["comm"] = comm
                infos[-1].__dict__["ppid"] = ppid
    except Exception:
        pass
    return infos


# ── Memory and rusage ─────────────────────────────────────────────────

def _collect_rusage() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF)
        out["utime_s"] = round(ru.ru_utime, 6)
        out["stime_s"] = round(ru.ru_stime, 6)
        out["maxrss_kb"] = ru.ru_maxrss
        out["minflt"] = ru.ru_minflt
        out["majflt"] = ru.ru_majflt
        out["nvcsw"] = ru.ru_nvcsw
        out["nivcsw"] = ru.ru_nivcsw
        out["ru_maxrss"] = ru.ru_maxrss
        out["ru_minflt"] = ru.ru_minflt
        out["ru_majflt"] = ru.ru_majflt
        out["ru_nvcsw"] = ru.ru_nvcsw
        out["ru_nivcsw"] = ru.ru_nivcsw
    except Exception:
        pass
    return out


def _collect_memory_status() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        with open("/proc/self/status") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    if key == "VmRSS":
                        info["vm_rss_kb"] = int(parts[1])
                        info["VmRSS"] = int(parts[1])
                    elif key == "VmSize":
                        info["vm_size_kb"] = int(parts[1])
                        info["VmSize"] = int(parts[1])
                    elif key == "VmPeak":
                        info["vm_peak_kb"] = int(parts[1])
                    elif key == "VmSwap":
                        info["vm_swap_kb"] = int(parts[1])
                        info["VmSwap"] = int(parts[1])
                    elif key == "VmHWM":
                        info["vm_hwm_kb"] = int(parts[1])
                    elif key == "Threads":
                        info["threads"] = int(parts[1])
                        info["Threads"] = int(parts[1])
                    elif key == "FDSize":
                        info["fd_size"] = int(parts[1])
                    elif key == "RssAnon":
                        info["rss_anon_kb"] = int(parts[1])
                    elif key == "RssFile":
                        info["rss_file_kb"] = int(parts[1])
                    elif key == "RssShmem":
                        info["rss_shmem_kb"] = int(parts[1])
    except Exception:
        pass
    return info


# ── CPU model/flags hashes (hashlib.sha256 on normalized values) ──────

def _cpu_model_hash(model_str: str) -> tuple[str, str]:
    """Return (full_hash, short_hash) of normalized CPU model string."""
    try:
        normalized = model_str.strip().lower()
        h = hashlib.sha256(normalized.encode("utf-8"))
        full = h.hexdigest()
        return full, full[:16]
    except Exception:
        return "", ""


def _cpu_flags_hash() -> tuple[str, str]:
    """Return (full_hash, short_hash) of sorted CPU flags."""
    try:
        with open("/proc/cpuinfo") as f:
            flags_raw = ""
            for line in f:
                if line.startswith("flags"):
                    flags_raw = line.partition(":")[2].strip()
                    break
        if not flags_raw:
            return "", ""
        sorted_flags = " ".join(sorted(flags_raw.strip().split()))
        h = hashlib.sha256(sorted_flags.encode("utf-8"))
        full = h.hexdigest()
        return full, full[:16]
    except Exception:
        return "", ""


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════


def capture_runtime_fingerprint(
    *,
    coordinator_state: dict[str, Any] | None = None,
    bridge_snapshot: dict[str, Any] | None = None,
) -> RuntimeFingerprint:
    """Capture a best-effort runtime fingerprint using only stdlib + /proc."""
    now_wall = time.time_ns()
    now_mono = time.monotonic_ns()
    pid = os.getpid()
    ppid: int | None = None
    sid: int | None = None
    pgrp: int | None = None
    try:
        self_stat = _read_proc_stat_file("/proc/self/stat")
        if self_stat:
            ppid = self_stat.get("ppid")
            sid = self_stat.get("session")
            pgrp = self_stat.get("pgrp")
    except Exception:
        pass

    affinity, aff_count = _get_affinity()
    cpu_model = ""
    cpu_model_clean = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu_model = line.partition(":")[2].strip()
                    cpu_model_clean = cpu_model.strip().lower()
                    break
    except Exception:
        pass

    cpu_model_hash_full, cpu_model_hash = _cpu_model_hash(cpu_model)
    cpu_flags_hash_full, cpu_flags_hash = _cpu_flags_hash()

    env_snapshot: dict[str, str] = {}
    for k in (
        "MODAL_TASK_ID", "MODAL_IMAGE_ID", "MODAL_CLOUD_PROVIDER", "MODAL_REGION",
        "MODAL_ENVIRONMENT", "COMFYMODAL_RUNTIME",
        "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "COMFYMODAL_ENABLE_GPU_SNAPSHOT",
        "COMFYMODAL_V2_APP_NAME", "COMFYMODAL_MODELS_VOLUME",
        "COMFYMODAL_RUNTIME_STATE_VOLUME", "COMFYMODAL_V2_PREFILL_LANES",
        "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS",
        "COMFYMODAL_V2_DEEP_MODEL_DIAG",
        "COMFYMODAL_V2_MEMORY_MB",
        "COMFYMODAL_V2_FULL_TRACE",
    ):
        v = os.environ.get(k, "")
        if v:
            env_snapshot[k] = v[:120]
    # Required native env variables: exactly the prompt-required names, each value or "absent"
    for k in (
        "OMP_NUM_THREADS", "OMP_DYNAMIC", "OMP_WAIT_POLICY", "OMP_PROC_BIND",
        "GOMP_CPU_AFFINITY", "MKL_NUM_THREADS", "MKL_DYNAMIC", "MKL_SERVICE_FORCE_INTEL",
        "OPENBLAS_NUM_THREADS", "OPENBLAS_MAIN_FREE", "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS", "KMP_BLOCKTIME", "KMP_SETTINGS",
        "KMP_AFFINITY", "KMP_HW_SUBSET", "TORCH_NUM_THREADS", "TOKENIZERS_PARALLELISM",
        "HF_ENABLE_PARALLEL_LOADING", "HF_PARALLEL_LOADING_WORKERS", "RAYON_NUM_THREADS",
        "MALLOC_ARENA_MAX",
    ):
        v = os.environ.get(k)
        if v is not None:
            env_snapshot[k] = v[:120]
        else:
            env_snapshot[k] = "absent"
    # Always include container_session_id if present
    csi = os.environ.get("COMFYMODAL_CONTAINER_SESSION_ID", "")
    if csi:
        env_snapshot["COMFYMODAL_CONTAINER_SESSION_ID"] = csi[:36]

    clk_tck = _get_sc_clk_tck()

    fp = RuntimeFingerprint(
        identity=ProcessIdentity(
            pid=pid,
            ppid=ppid,
            sid=sid,
            process_group=pgrp,
            hostname=platform.node()[:64],
            boot_id=_get_boot_id(),
            modal_task_id=os.environ.get("MODAL_TASK_ID", "") or "",
            modal_image_id=os.environ.get("MODAL_IMAGE_ID", "") or "",
            modal_cloud_provider=os.environ.get("MODAL_CLOUD_PROVIDER", "") or "",
            modal_region=os.environ.get("MODAL_REGION", "") or "",
            container_session_id=os.environ.get("COMFYMODAL_CONTAINER_SESSION_ID", "") or "",
        ),
        cpu=CpuIdentity(
            affinity=affinity,
            affinity_count=aff_count,
            machine=platform.machine()[:32],
            kernel=platform.release()[:64],
            cpu_model=cpu_model[:80],
            cpu_model_clean=cpu_model_clean[:80],
            cpu_model_hash=cpu_model_hash,
            cpu_model_hash_full=cpu_model_hash_full,
            cpu_flags_hash=cpu_flags_hash,
            cpu_flags_hash_full=cpu_flags_hash_full,
        ),
        env=env_snapshot,
        torch_version=_safe_torch_version(),
        torch_state=_collect_torch_state(),
        native_libs=_collect_native_libs(),
        python_threads=_enumerate_python_threads(),
        proc_task_records=_enumerate_proc_task(clk_tck),
        visible_processes=_enumerate_visible_processes(pid, clk_tck),
        coordinator_state=dict(coordinator_state or {}),
        bridge_snapshot=dict(bridge_snapshot or {}),
        rusage=_collect_rusage(),
        memory_status=_collect_memory_status(),
        wall_unix_ns=now_wall,
        mono_ns=now_mono,
    )
    return fp


def _fingerprint_summary(fp: RuntimeFingerprint) -> str:
    """One-line compact [v2.snapshot_fingerprint] summary."""
    fields: list[str] = []
    fields.append(f"pid={fp.identity.pid}")
    fields.append(f"ppid={fp.identity.ppid}")
    fields.append(f"hostname={fp.identity.hostname[:24]}")
    fields.append(f"boot_id={fp.identity.boot_id[:16]}")
    fields.append(f"container_session_id={fp.identity.container_session_id[:16] or 'absent'}")
    fields.append(f"modal_task_id={fp.identity.modal_task_id[:16] or 'absent'}")
    fields.append(f"machine={fp.cpu.machine}")
    fields.append(f"affinity={fp.cpu.affinity_count}")
    fields.append(f"cpu_model=\"{fp.cpu.cpu_model[:48]}\"")
    fields.append(f"cpu_model_hash={fp.cpu.cpu_model_hash or 'absent'}")
    fields.append(f"cpu_model_hash_full={fp.cpu.cpu_model_hash_full or 'absent'}")
    fields.append(f"cpu_flags_hash={fp.cpu.cpu_flags_hash or 'absent'}")
    fields.append(f"cpu_flags_hash_full={fp.cpu.cpu_flags_hash_full or 'absent'}")
    fields.append(f"kernel={fp.cpu.kernel}")
    torch_ver = fp.torch_version or 'absent'
    ts = fp.torch_state
    if ts.get("status") == "loaded":
        torch_ver = ts.get("version", torch_ver)
        nt = ts.get("num_threads")
        if nt is not None and nt >= 0:
            torch_ver += f"/thr={nt}"
        ni = ts.get("num_interop_threads")
        if ni is not None and ni >= 0:
            torch_ver += f"/int={ni}"
        cu = ts.get("cuda_version", "")
        if cu:
            torch_ver += f"/cuda={cu}"
    fields.append(f"torch={torch_ver}")
    nlibs = len(fp.native_libs.basenames)
    nlibs_trunc = "t" if fp.native_libs.truncated else ""
    fields.append(f"native_libs={nlibs}{nlibs_trunc}")
    nthreads = len(fp.proc_task_records)
    fields.append(f"task_threads={nthreads}")
    nprocs = len(fp.visible_processes)
    fields.append(f"visible_pids={nprocs}")
    maxrss = fp.rusage.get("maxrss_kb")
    if maxrss is not None:
        fields.append(f"maxrss_mib={round(maxrss / 1024, 1)}")
    fields.append(f"wall_unix_ns={fp.wall_unix_ns}")
    fields.append(f"mono_ns={fp.mono_ns}")
    return " ".join(fields)


def _diff_fingerprints(
    capture: RuntimeFingerprint,
    restore: RuntimeFingerprint,
    *,
    _capture_fp_for_tid_set: RuntimeFingerprint | None = None,
    _restore_fp_for_tid_set: RuntimeFingerprint | None = None,
) -> str:
    """One-line [v2.snapshot_fingerprint_diff] with every specified comparison field."""
    diff: list[str] = []

    def _cmp(label: str, a_val: Any, r_val: Any) -> None:
        if a_val != r_val:
            diff.append(f"{label}_changed=true")
            diff.append(f"{label}_capture={a_val}")
            diff.append(f"{label}_restore={r_val}")
        else:
            diff.append(f"{label}_changed=false")

    cap = capture
    res = restore

    # ── Required comparison fields ──
    diff.append(f"capture_pid={cap.identity.pid}")
    diff.append(f"restore_pid={res.identity.pid}")
    capture_thread_count = len(cap.proc_task_records)
    restore_thread_count = len(res.proc_task_records)
    diff.append(f"capture_thread_count={capture_thread_count}")
    diff.append(f"restore_thread_count={restore_thread_count}")
    capture_native_tid_count = len(cap.proc_task_records)
    restore_native_tid_count = len(res.proc_task_records)
    diff.append(f"capture_native_tid_count={capture_native_tid_count}")
    diff.append(f"restore_native_tid_count={restore_native_tid_count}")
    capture_visible_pid_count = len(cap.visible_processes)
    restore_visible_pid_count = len(res.visible_processes)
    diff.append(f"capture_visible_pid_count={capture_visible_pid_count}")
    diff.append(f"restore_visible_pid_count={restore_visible_pid_count}")

    # Pool exists
    cap_pool_exists = cap.coordinator_state.get("pool_exists", False)
    res_pool_exists = res.coordinator_state.get("pool_exists", False)
    diff.append(f"capture_pool_exists={int(cap_pool_exists)}")
    diff.append(f"restore_pool_exists={int(res_pool_exists)}")
    cap_pool_wc = cap.coordinator_state.get("pool_worker_count", 0)
    res_pool_wc = res.coordinator_state.get("pool_worker_count", 0)
    diff.append(f"capture_pool_worker_count={cap_pool_wc}")
    diff.append(f"restore_pool_worker_count={res_pool_wc}")

    # Exact TID preservation
    cap_tids_set = set()
    for tr in cap.proc_task_records:
        t = tr.get("tid")
        if t is not None:
            cap_tids_set.add(str(t))
    res_tids_set = set()
    for tr in res.proc_task_records:
        t = tr.get("tid")
        if t is not None:
            res_tids_set.add(str(t))
    exact_tids_preserved = cap_tids_set & res_tids_set
    new_tids = res_tids_set - cap_tids_set
    missing_tids = cap_tids_set - res_tids_set
    diff.append(f"exact_tids_preserved={','.join(sorted(exact_tids_preserved)[:32]) or 'none'}")
    diff.append(f"new_tids={','.join(sorted(new_tids)[:16]) or 'none'}")
    diff.append(f"missing_tids={','.join(sorted(missing_tids)[:16]) or 'none'}")

    # Thread names
    cap_names = {tr.get("tid", ""): tr.get("comm", "") for tr in cap.proc_task_records}
    res_names = {tr.get("tid", ""): tr.get("comm", "") for tr in res.proc_task_records}
    new_thread_names = []
    missing_thread_names = []
    for tid in new_tids:
        nm = res_names.get(tid, "")
        if nm:
            new_thread_names.append(f"{tid}:{nm}")
    for tid in missing_tids:
        nm = cap_names.get(tid, "")
        if nm:
            missing_thread_names.append(f"{tid}:{nm}")
    diff.append(f"new_thread_names={','.join(new_thread_names[:16]) or 'none'}")
    diff.append(f"missing_thread_names={','.join(missing_thread_names[:16]) or 'none'}")

    def _match(label: str, capture_value: Any, restore_value: Any) -> None:
        if not capture_value or not restore_value:
            diff.append(f"{label}=unknown")
        else:
            diff.append(f"{label}={'true' if capture_value == restore_value else 'false'}")

    # Changed thread env (env diff)
    added_env = sorted(set(res.env) - set(cap.env))
    removed_env = sorted(set(cap.env) - set(res.env))
    changed_env = sorted(k for k in set(cap.env) & set(res.env) if cap.env[k] != res.env[k])
    if added_env or removed_env or changed_env:
        diff.append(f"changed_thread_env=1 "
                     f"added={','.join(added_env[:6]) or 'none'} "
                     f"removed={','.join(removed_env[:6]) or 'none'} "
                     f"changed={','.join(changed_env[:6]) or 'none'}")
    else:
        diff.append("changed_thread_env=0")

    # Changed torch thread counts
    cap_tc = cap.torch_state.get("num_threads", -1)
    res_tc = res.torch_state.get("num_threads", -1)
    cap_ic = cap.torch_state.get("num_interop_threads", -1)
    res_ic = res.torch_state.get("num_interop_threads", -1)
    if cap_tc != res_tc or cap_ic != res_ic:
        diff.append(f"changed_torch_thread_counts=1 "
                     f"capture_threads={cap_tc} restore_threads={res_tc} "
                     f"capture_interop={cap_ic} restore_interop={res_ic}")
    else:
        diff.append("changed_torch_thread_counts=0")

    # Changed loaded thread libraries (native libs)
    cap_lib_set = set(cap.native_libs.basenames)
    res_lib_set = set(res.native_libs.basenames)
    if cap_lib_set != res_lib_set:
        lib_added = sorted(res_lib_set - cap_lib_set)[:8]
        lib_removed = sorted(cap_lib_set - res_lib_set)[:8]
        diff.append(f"changed_loaded_thread_libraries=1 "
                     f"added={','.join(lib_added) or 'none'} "
                     f"removed={','.join(lib_removed) or 'none'}")
    else:
        diff.append("changed_loaded_thread_libraries=0")

    # CPU model/flag/kernel/boot comparison
    _cmp("cpu_model_hash", cap.cpu.cpu_model_hash, res.cpu.cpu_model_hash)
    _cmp("cpu_flags_hash", cap.cpu.cpu_flags_hash, res.cpu.cpu_flags_hash)
    _cmp("kernel", cap.cpu.kernel, res.cpu.kernel)
    _cmp("boot_id", cap.identity.boot_id, res.identity.boot_id)
    _match("cpu_model_hash_match", cap.cpu.cpu_model_hash, res.cpu.cpu_model_hash)
    _match("kernel_match", cap.cpu.kernel, res.cpu.kernel)
    _match("boot_id_match", cap.identity.boot_id, res.identity.boot_id)

    # Required fingerprint comparison: cpu_flags_hash snapshot/restore/match
    diff.append(f"snapshot_cpu_flags_hash={cap.cpu.cpu_flags_hash or 'absent'}")
    diff.append(f"restore_cpu_flags_hash={res.cpu.cpu_flags_hash or 'absent'}")
    if cap.cpu.cpu_flags_hash and res.cpu.cpu_flags_hash:
        _flags_match = "true" if cap.cpu.cpu_flags_hash == res.cpu.cpu_flags_hash else "false"
    elif not cap.cpu.cpu_flags_hash and not res.cpu.cpu_flags_hash:
        _flags_match = "true"
    else:
        _flags_match = "unknown"
    diff.append(f"cpu_flags_hash_match={_flags_match}")

    # Torch thread counts: snapshot vs restore
    cap_nt = cap.torch_state.get("num_threads", -1)
    res_nt = res.torch_state.get("num_threads", -1)
    cap_ni = cap.torch_state.get("num_interop_threads", -1)
    res_ni = res.torch_state.get("num_interop_threads", -1)
    diff.append(f"snapshot_torch_num_threads={cap_nt}")
    diff.append(f"restore_torch_num_threads={res_nt}")
    diff.append(f"snapshot_torch_num_interop_threads={cap_ni}")
    diff.append(f"restore_torch_num_interop_threads={res_ni}")

    # Legacy comparison fields (backward compat)
    _cmp("pid", cap.identity.pid, res.identity.pid)
    _cmp("ppid", cap.identity.ppid, res.identity.ppid)
    _cmp("hostname", cap.identity.hostname[:32], res.identity.hostname[:32])
    _cmp("machine", cap.cpu.machine, res.cpu.machine)
    _cmp("torch_version", cap.torch_version[:32], res.torch_version[:32])

    # Container session identity
    _cmp("container_session_id",
         cap.identity.container_session_id,
         res.identity.container_session_id)
    _cmp("modal_task_id",
         cap.identity.modal_task_id[:16],
         res.identity.modal_task_id[:16])

    # Coordinator/Bridge state
    _cmp("bridge_preparation_exists",
         cap.bridge_snapshot.get("current_preparation_exists"),
         res.bridge_snapshot.get("current_preparation_exists"))
    _cmp("bridge_executor_exists",
         cap.bridge_snapshot.get("executor_exists"),
         res.bridge_snapshot.get("executor_exists"))

    return " ".join(diff)


# ── One-shot restore entry ────────────────────────────────────────────

_RESTORE_WALL_NS: int = 0
_RESTORE_MONO_NS: int = 0
_RESTORE_FINGERPRINT: RuntimeFingerprint | None = None
_RESTORE_CAPTURE_FALLBACK: RuntimeFingerprint | None = None
_V2_RESTORE_FINGERPRINT: dict[str, Any] = {}
"""Module-level restore fingerprint store, populated before watcher start.
Accessed by _RestoreCpuWatcher._emit_final_summary for comparison keys."""


def claim_restore_entry() -> bool:
    """Atomically claim one-shot restore entry (not consumed by startup).

    Returns True if this is the first restore call in this process.
    """
    global _RESTORE_ONE_SHOT_CLAIMED, _RESTORE_WALL_NS, _RESTORE_MONO_NS
    with _RESTORE_ONE_SHOT_LOCK:
        if _RESTORE_ONE_SHOT_CLAIMED:
            return False
        _RESTORE_ONE_SHOT_CLAIMED = True
        _RESTORE_WALL_NS = time.time_ns()
        _RESTORE_MONO_NS = time.monotonic_ns()
        return True


# ── Watcher ───────────────────────────────────────────────────────────

_RESTORE_WATCHER_INSTANCE: "_RestoreCpuWatcher | None" = None


@dataclass
class _SampleSnapshot:
    wall_ns: int
    mono_ns: int
    proc_stat: dict[str, Any] | None
    task_stats: list[dict[str, Any]]
    proc_stats: dict[str, dict[str, Any] | None]


def _python_thread_name_for_native_tid(native_tid: int) -> str:
    """Look up a Python thread name by native TID via threading.enumerate()."""
    for t in threading.enumerate():
        if t.native_id == native_tid:
            return str(t.name)[:80]
    return "?"


def _native_tids_from_capture_fingerprint() -> set[str]:
    """Return native TID strings that were present in the snapshot capture fingerprint."""
    tids: set[str] = set()
    fp = _V2_SNAPSHOT_CAPTURE_FINGERPRINT.get("_fp_object")
    if fp is None:
        return tids
    try:
        for rec in getattr(fp, "proc_task_records", []):
            tid = rec.get("tid")
            if tid is not None:
                tids.add(str(tid))
    except Exception:
        pass
    return tids


class _RestoreCpuWatcher:
    """10s daemon watcher with 10ms samples, 250ms aggregate logs."""

    _CLK_TCK: int = _get_sc_clk_tck()
    _SAMPLE_INTERVAL_S: float = 0.010  # 10ms
    _WATCH_DURATION_S: float = 10.0
    _LOG_INTERVAL_S: float = 0.250  # 250ms
    _MAX_TID_RECORDS: int = 512
    _MAX_PID_RECORDS: int = 256

    def __init__(self, entry_mono_ns: int, entry_wall_ns: int) -> None:
        self._entry_mono_ns: int = entry_mono_ns
        self._entry_wall_ns: int = entry_wall_ns
        self._pid: int = os.getpid()
        self._thread: threading.Thread | None = None
        self._stop: threading.Event = threading.Event()
        self._phase: str = "restore_entry"
        self._phase_lock: threading.Lock = threading.Lock()
        self._previous_sample: _SampleSnapshot | None = None
        self._started: bool = False

        # Per-interval accumulator
        self._interval_samples: list[_SampleSnapshot] = []
        self._last_log_mono_ns: int = entry_mono_ns
        self._interval_count: int = 0

        # Known TIDs/PIDs with starttime for create/exit detection
        self._known_tids: dict[str, int] = {}
        self._known_pids: dict[str, int] = {}
        self._records_truncated: int = 0
        self._total_intervals: int = 0
        self._total_samples: int = 0

        # Capture native TIDs for captured_in_snapshot comparison
        self._capture_native_tids: set[str] = _native_tids_from_capture_fingerprint()

        # Lifetime create/exit tracking
        self._all_seen_created_tids: dict[str, dict[str, Any]] = {}
        self._all_seen_exited_tids: dict[str, dict[str, Any]] = {}
        self._all_seen_created_pids: dict[str, dict[str, Any]] = {}
        self._all_seen_exited_pids: dict[str, dict[str, Any]] = {}
        self._cpu_by_tid_identity: dict[str, float] = {}
        self._cpu_by_pid_identity: dict[str, float] = {}
        self._peak_cores_by_tid: dict[str, float] = {}
        self._peak_cores_by_pid: dict[str, float] = {}
        self._seen_tid_identities: set[str] = set()
        self._seen_pid_identities: set[str] = set()

        # Watcher probe thread CPU (delta)
        self._probe_thread_cpu_start_ns: int | None = None
        self._probe_thread_cpu_total_ns: int = 0

    def set_phase(self, phase: str) -> None:
        with self._phase_lock:
            self._phase = phase

    @property
    def phase(self) -> str:
        with self._phase_lock:
            return self._phase

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop.clear()
        # Emit required first marker
        print(
            f"[v2.restore_worker_probe] event=started "
            f"wall_unix_ns={self._entry_wall_ns} "
            f"monotonic_ns={self._entry_mono_ns} "
            f"pid={self._pid} "
            f"duration_ms={int(self._WATCH_DURATION_S * 1000)} "
            f"sample_interval_ms={int(self._SAMPLE_INTERVAL_S * 1000)}",
            flush=True,
        )
        self._thread = threading.Thread(target=self._run, daemon=True, name="comfymodal-restore-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _sample(self) -> _SampleSnapshot:
        now_wall = time.time_ns()
        now_mono = time.monotonic_ns()
        proc_stat = _read_proc_stat_file("/proc/self/stat")
        task_stats: list[dict[str, Any]] = []
        truncated_tids = False
        try:
            for entry in os.listdir(f"/proc/{self._pid}/task"):
                if len(task_stats) >= self._MAX_TID_RECORDS:
                    truncated_tids = True
                    break
                stat = _read_proc_stat_file(f"/proc/{self._pid}/task/{entry}/stat")
                if stat is not None:
                    stat["_tid"] = entry
                    # Read task children (<tid>/children list)
                    try:
                        with open(f"/proc/{self._pid}/task/{entry}/children") as cf:
                            child_text = cf.read().strip()
                            if child_text:
                                stat["children"] = [int(x) for x in child_text.split() if x.isdigit()]
                            else:
                                stat["children"] = []
                    except Exception:
                        stat["children"] = []
                    task_stats.append(stat)
        except Exception:
            pass
        if truncated_tids:
            self._records_truncated = 1
        proc_stats: dict[str, dict[str, Any] | None] = {}
        truncated_pids = False
        try:
            for entry in os.listdir("/proc/"):
                if not entry.isdigit():
                    continue
                if len(proc_stats) >= self._MAX_PID_RECORDS:
                    truncated_pids = True
                    break
                if entry == str(self._pid):
                    continue
                stat = _read_proc_stat_file(f"/proc/{entry}/stat")
                if stat is not None:
                    stat["nspid"] = _read_nspid(int(entry))
                    stat["cmdline"] = _read_cmdline(int(entry), max_len=160)
                proc_stats[entry] = stat
        except Exception:
            pass
        if truncated_pids:
            self._records_truncated = 1
        return _SampleSnapshot(
            wall_ns=now_wall,
            mono_ns=now_mono,
            proc_stat=proc_stat,
            task_stats=task_stats,
            proc_stats=proc_stats,
        )

    def _detect_create_exit(
        self,
        previous: _SampleSnapshot,
        current: _SampleSnapshot,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        created: list[dict[str, Any]] = []
        exited: list[dict[str, Any]] = []

        # TIDs: identity is (tid,starttime_ticks)
        prev_tids: dict[str, int] = {}
        for ts in previous.task_stats:
            tid = str(ts.get("_tid", ts.get("pid", "")))
            st = ts.get("starttime")
            key = f"{tid}:{st}" if st is not None else tid
            if tid:
                prev_tids[key] = 1
        curr_tids: dict[str, int] = {}
        for ts in current.task_stats:
            tid = str(ts.get("_tid", ts.get("pid", "")))
            st = ts.get("starttime")
            key = f"{tid}:{st}" if st is not None else tid
            if tid:
                curr_tids[key] = 1

        # Newly created threads
        for key in set(curr_tids) - set(prev_tids):
            parts = key.split(":")
            tid = parts[0]
            st = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            # Find comm from current sample
            comm = ""
            for ts in current.task_stats:
                if str(ts.get("_tid", ts.get("pid", ""))) == tid:
                    comm = ts.get("comm", "") or ""
                    break
            created.append({"type": "thread", "tid": int(tid), "starttime": st, "comm": comm})

        # Exited threads
        for key in set(prev_tids) - set(curr_tids):
            parts = key.split(":")
            tid = parts[0]
            # Find comm from previous sample
            comm = ""
            for ts in previous.task_stats:
                if str(ts.get("_tid", ts.get("pid", ""))) == tid:
                    comm = ts.get("comm", "") or ""
                    break
            exited.append({"type": "thread", "tid": int(tid), "comm": comm})

        # PIDs: identity is (pid,starttime_ticks)
        prev_pids: dict[str, int] = {}
        for opid, stat in previous.proc_stats.items():
            if stat is None:
                continue
            st = stat.get("starttime")
            key = f"{opid}:{st}" if st is not None else opid
            prev_pids[key] = 1
        curr_pids_dict: dict[str, int] = {}
        for opid, stat in current.proc_stats.items():
            if stat is None:
                continue
            st = stat.get("starttime")
            key = f"{opid}:{st}" if st is not None else opid
            curr_pids_dict[key] = 1

        for key in set(curr_pids_dict) - set(prev_pids):
            parts = key.split(":")
            opid = int(parts[0])
            st = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            # Find comm/cmdline from current sample
            stat = current.proc_stats.get(str(opid))
            comm = stat.get("comm", "") if stat else ""
            ppid = stat.get("ppid") if stat else None
            cmdline = _read_cmdline(opid, max_len=120)
            created.append({"type": "process", "pid": opid, "starttime": st, "comm": comm, "ppid": ppid, "cmdline": cmdline})

        for key in set(prev_pids) - set(curr_pids_dict):
            parts = key.split(":")
            opid = int(parts[0])
            stat = previous.proc_stats.get(str(opid))
            comm = stat.get("comm", "") if stat else ""
            ppid = stat.get("ppid") if stat else None
            cmdline = _read_cmdline(opid, max_len=120)
            exited.append({"type": "process", "pid": opid, "comm": comm, "ppid": ppid, "cmdline": cmdline})

        return created, exited

    def _compute_interval_cpu_deltas(
        self,
        previous: _SampleSnapshot,
        current: _SampleSnapshot,
    ) -> dict[str, Any]:
        ms_per_tick = 1000.0 / self._CLK_TCK
        wall_delta_ms = (current.mono_ns - previous.mono_ns) / 1_000_000.0
        if wall_delta_ms <= 0:
            return {}

        def _get_ticks(stat: dict[str, Any] | None, key: str) -> int:
            if stat is None:
                return 0
            val = stat.get(key)
            return int(val) if val is not None else 0

        # Main process
        p_prev_ticks = _get_ticks(previous.proc_stat, "utime") + _get_ticks(previous.proc_stat, "stime")
        p_curr_ticks = _get_ticks(current.proc_stat, "utime") + _get_ticks(current.proc_stat, "stime")
        proc_delta_ticks = max(0, p_curr_ticks - p_prev_ticks)
        proc_cpu_ms = proc_delta_ticks * ms_per_tick
        proc_eff = (proc_cpu_ms * 1_000_000.0) / (current.mono_ns - previous.mono_ns) if current.mono_ns > previous.mono_ns else 0.0

        # Per-tid (identity key = tid:starttime)
        tid_deltas: list[tuple[str, float, str]] = []
        prev_tid_map: dict[str, dict[str, Any]] = {}
        for ts in previous.task_stats:
            key = f"{ts.get('_tid', ts.get('pid', ''))}:{ts.get('starttime', 0)}"
            prev_tid_map[key] = ts
        curr_tid_map: dict[str, dict[str, Any]] = {}
        for ts in current.task_stats:
            key = f"{ts.get('_tid', ts.get('pid', ''))}:{ts.get('starttime', 0)}"
            curr_tid_map[key] = ts
        all_tid_keys = set(prev_tid_map) | set(curr_tid_map)
        self._seen_tid_identities.update(all_tid_keys)
        for key in all_tid_keys:
            pt = prev_tid_map.get(key)
            ct = curr_tid_map.get(key)
            prev_t = _get_ticks(pt, "utime") + _get_ticks(pt, "stime")
            curr_t = _get_ticks(ct, "utime") + _get_ticks(ct, "stime")
            delta_t = max(0, curr_t - prev_t)
            if delta_t > 0:
                delta_cpu = delta_t * ms_per_tick
                tid = key.split(":")[0]
                comm = (ct or pt or {}).get("comm", "") or ""
                tid_deltas.append((tid, delta_cpu, comm))
            # Track cumulative CPU and peak by identity
            if key not in self._cpu_by_tid_identity:
                self._cpu_by_tid_identity[key] = 0.0
            if ct is not None:
                t_curr_t = _get_ticks(ct, "utime") + _get_ticks(ct, "stime")
                if pt is not None:
                    t_prev_t = _get_ticks(pt, "utime") + _get_ticks(pt, "stime")
                else:
                    t_prev_t = 0
                t_delta = max(0, t_curr_t - t_prev_t) * ms_per_tick
                self._cpu_by_tid_identity[key] += t_delta
                # Effective cores this interval
                this_eff = (t_delta * 1_000_000.0) / (current.mono_ns - previous.mono_ns) if current.mono_ns > previous.mono_ns else 0.0
                if this_eff > self._peak_cores_by_tid.get(key, 0.0):
                    self._peak_cores_by_tid[key] = this_eff

        tid_deltas.sort(key=lambda x: x[1], reverse=True)

        # Per-pid (visible others) - identity = pid:starttime
        pid_deltas: list[tuple[str, float, str]] = []
        prev_pid_map: dict[str, dict[str, Any] | None] = {}
        for opid, stat in previous.proc_stats.items():
            st = stat.get("starttime") if stat else 0
            key = f"{opid}:{st}"
            prev_pid_map[key] = stat
        curr_pid_map: dict[str, dict[str, Any] | None] = {}
        for opid, stat in current.proc_stats.items():
            st = stat.get("starttime") if stat else 0
            key = f"{opid}:{st}"
            curr_pid_map[key] = stat
        all_pid_keys = set(prev_pid_map) | set(curr_pid_map)
        self._seen_pid_identities.update(all_pid_keys)
        for key in all_pid_keys:
            pp = prev_pid_map.get(key)
            cp = curr_pid_map.get(key)
            prev_pt = _get_ticks(pp, "utime") + _get_ticks(pp, "stime")
            curr_pt = _get_ticks(cp, "utime") + _get_ticks(cp, "stime")
            delta_pt = max(0, curr_pt - prev_pt)
            if delta_pt > 0:
                delta_cpu = delta_pt * ms_per_tick
                pid = key.split(":")[0]
                comm = (cp or pp or {}).get("comm", "") if (cp or pp) else ""
                pid_deltas.append((pid, delta_cpu, comm))
            # Track cumulative CPU and peak
            if key not in self._cpu_by_pid_identity:
                self._cpu_by_pid_identity[key] = 0.0
            if cp is not None:
                p_t_curr = _get_ticks(cp, "utime") + _get_ticks(cp, "stime")
                if pp is not None:
                    p_t_prev = _get_ticks(pp, "utime") + _get_ticks(pp, "stime")
                else:
                    p_t_prev = 0
                p_delta = max(0, p_t_curr - p_t_prev) * ms_per_tick
                self._cpu_by_pid_identity[key] += p_delta
                p_this_eff = (p_delta * 1_000_000.0) / (current.mono_ns - previous.mono_ns) if current.mono_ns > previous.mono_ns else 0.0
                if p_this_eff > self._peak_cores_by_pid.get(key, 0.0):
                    self._peak_cores_by_pid[key] = p_this_eff

        pid_deltas.sort(key=lambda x: x[1], reverse=True)

        visible_other_total = sum(d for _, d, _ in pid_deltas)
        visible_total_cpu_ms = proc_cpu_ms + visible_other_total
        visible_total_eff = (
            (visible_total_cpu_ms * 1_000_000.0) / wall_delta_ms
            if wall_delta_ms > 0 else 0.0
        )

        # Probe thread CPU (delta from start, not cumulative absolute)
        try:
            now_tt = time.thread_time_ns()
            if self._probe_thread_cpu_start_ns is None:
                self._probe_thread_cpu_start_ns = now_tt
                probe_delta_ms = 0.0
            else:
                probe_delta_ms = (now_tt - self._probe_thread_cpu_start_ns) / 1_000_000.0
                self._probe_thread_cpu_total_ns = now_tt - self._probe_thread_cpu_start_ns
        except Exception:
            probe_delta_ms = None

        # Find new TIDs and PIDs in this interval
        new_tids_in_window = []
        new_pids_in_window = []
        for key in set(curr_tid_map) - set(prev_tid_map):
            tid = key.split(":")[0]
            comm = curr_tid_map[key].get("comm", "") if curr_tid_map.get(key) else ""
            new_tids_in_window.append(f"{tid}:{comm}")
        for key in set(curr_pid_map) - set(prev_pid_map):
            pid = key.split(":")[0]
            current_pid = curr_pid_map.get(key)
            comm = current_pid.get("comm", "") if current_pid else ""
            new_pids_in_window.append(f"{pid}:{comm}")

        # Top TIDs formatted as tid:comm:cpu_ms
        top_tids_fmt = ",".join(f"{tid}:{comm}:{cpu:.3f}" for tid, cpu, comm in tid_deltas[:5])
        # Top PIDs formatted as pid:comm:cpu_ms
        top_pids_fmt = ",".join(f"{pid}:{comm}:{cpu:.3f}" for pid, cpu, comm in pid_deltas[:5])

        return {
            "wall_delta_ms": round(wall_delta_ms, 3),
            "proc_cpu_ms": round(proc_cpu_ms, 3),
            "proc_eff": round(proc_eff, 3),
            "top_tids": top_tids_fmt,
            "top_pids": top_pids_fmt,
            "visible_other_cpu_ms": round(visible_other_total, 3),
            "visible_total_cpu_ms": round(visible_total_cpu_ms, 3),
            "visible_total_eff": round(visible_total_eff, 3),
            "probe_thread_cpu_ms": round(probe_delta_ms, 3) if probe_delta_ms is not None else None,
            "new_tids": ",".join(new_tids_in_window[:5]) or "none",
            "new_pids": ",".join(new_pids_in_window[:5]) or "none",
        }

    def _emit_cpu_window(self, deltas: dict[str, Any], phase: str, start_wall_ns: int, end_wall_ns: int) -> None:
        wcpu = deltas.get("probe_thread_cpu_ms")
        wcpu_str = f"probe_thread_cpu_ms={wcpu:.3f}" if wcpu is not None else "probe_thread_cpu_ms=none"
        parts: list[str] = [
            f"window={self._interval_count}",
            f"phase={phase}",
            f"start_wall_unix_ns={start_wall_ns}",
            f"end_wall_unix_ns={end_wall_ns}",
            f"main_process_cpu_ms={deltas.get('proc_cpu_ms', 0):.3f}",
            f"main_process_effective_cores={deltas.get('proc_eff', 0):.3f}",
            f"visible_other_process_cpu_ms={deltas.get('visible_other_cpu_ms', 0):.3f}",
            f"visible_total_cpu_ms={deltas.get('visible_total_cpu_ms', 0):.3f}",
            f"visible_total_effective_cores={deltas.get('visible_total_eff', 0):.3f}",
            wcpu_str,
            f"top_tids={deltas.get('top_tids', 'none')}",
            f"top_pids={deltas.get('top_pids', 'none')}",
            f"new_tids={deltas.get('new_tids', 'none')}",
            f"new_pids={deltas.get('new_pids', 'none')}",
        ]
        print(f"[v2.restore_cpu_window] {' '.join(parts)}", flush=True)

    def _run(self) -> None:
        self._previous_sample = self._sample()
        self._last_log_mono_ns = self._previous_sample.mono_ns
        self._last_log_wall_ns = self._previous_sample.wall_ns
        interval_samples = [self._previous_sample]
        self._total_samples += 1

        while not self._stop.wait(self._SAMPLE_INTERVAL_S):
            now_mono = time.monotonic_ns()
            elapsed_since_entry = (now_mono - self._entry_mono_ns) / 1_000_000_000.0
            if elapsed_since_entry >= self._WATCH_DURATION_S:
                self._emit_final_summary()
                break

            prev = self._previous_sample
            if prev is None:
                continue
            cur = self._sample()
            self._previous_sample = cur
            interval_samples.append(cur)
            self._total_samples += 1
            self._total_intervals += 1

            # Detect create/exit
            created, exited = self._detect_create_exit(prev, cur)

            # Emit precise create/exit logs
            for ev in created:
                etype = ev.get("type", "?")
                if etype == "thread":
                    tid = ev.get("tid", "?")
                    comm = ev.get("comm", "")
                    ts_start = ev.get("starttime", 0)
                    first_seen = cur.wall_ns
                    # Actual ppid from proc stat (parent is main process)
                    thread_ppid = self._pid
                    # Python thread name from threading.enumerate()
                    python_name = _python_thread_name_for_native_tid(int(tid)) if tid != "?" else "?"
                    # Check if this TID was present in snapshot capture
                    captured_in_snapshot = 1 if str(tid) in self._capture_native_tids else 0
                    print(
                        f"[v2.thread_seen] event=created "
                        f"tid={tid} "
                        f"ppid={thread_ppid} "
                        f"starttime_ticks={ts_start} "
                        f"comm={comm or '?'} "
                        f"python_name={python_name} "
                        f"captured_in_snapshot={captured_in_snapshot} "
                        f"first_seen_wall_unix_ns={first_seen}",
                        flush=True,
                    )
                    self._all_seen_created_tids[str(tid)] = {
                        "first_seen": first_seen,
                        "comm": comm,
                        "starttime": ts_start,
                        "ppid": thread_ppid,
                        "python_name": python_name,
                        "captured_in_snapshot": captured_in_snapshot,
                    }
                elif etype == "process":
                    pid = ev.get("pid", "?")
                    ppid_val = ev.get("ppid", "?")
                    st_val = ev.get("starttime", 0)
                    comm_val = ev.get("comm", "")
                    cmdline_val = ev.get("cmdline", "")
                    first_seen = cur.wall_ns
                    print(
                        f"[v2.process_seen] event=created "
                        f"pid={pid} "
                        f"ppid={ppid_val} "
                        f"starttime_ticks={st_val} "
                        f"comm={comm_val or '?'} "
                        f"cmdline={cmdline_val or '?'} "
                        f"first_seen_wall_unix_ns={first_seen}",
                        flush=True,
                    )
                    self._all_seen_created_pids[str(pid)] = {
                        "first_seen": first_seen,
                        "comm": comm_val,
                        "cmdline": cmdline_val,
                        "starttime": st_val,
                        "ppid": ppid_val,
                    }

            for ev in exited:
                etype = ev.get("type", "?")
                if etype == "thread":
                    tid = str(ev.get("tid", "?"))
                    created_info = self._all_seen_created_tids.get(tid, {})
                    first_seen = created_info.get("first_seen", prev.wall_ns)
                    lifetime_ms = (cur.wall_ns - first_seen) / 1_000_000.0
                    # Total CPU from tracked identity
                    total_cpu_ms = 0.0
                    peak_eff = 0.0
                    for key, val in self._cpu_by_tid_identity.items():
                        if key.split(":")[0] == tid:
                            total_cpu_ms = val
                    for key, val in self._peak_cores_by_tid.items():
                        if key.split(":")[0] == tid:
                            peak_eff = val
                    print(
                        f"[v2.thread_seen] event=exited "
                        f"tid={tid} "
                        f"lifetime_ms={lifetime_ms:.3f} "
                        f"total_cpu_ms={total_cpu_ms:.3f} "
                        f"peak_effective_cores={peak_eff:.3f}",
                        flush=True,
                    )
                    self._all_seen_exited_tids[tid] = {
                        "lifetime_ms": lifetime_ms,
                        "total_cpu_ms": total_cpu_ms,
                        "peak_eff": peak_eff,
                    }
                elif etype == "process":
                    pid = str(ev.get("pid", "?"))
                    created_info = self._all_seen_created_pids.get(pid, {})
                    first_seen = created_info.get("first_seen", prev.wall_ns)
                    lifetime_ms = (cur.wall_ns - first_seen) / 1_000_000.0
                    total_cpu_ms = 0.0
                    peak_eff = 0.0
                    for key, val in self._cpu_by_pid_identity.items():
                        if key.split(":")[0] == pid:
                            total_cpu_ms = val
                    for key, val in self._peak_cores_by_pid.items():
                        if key.split(":")[0] == pid:
                            peak_eff = val
                    print(
                        f"[v2.process_seen] event=exited "
                        f"pid={pid} "
                        f"lifetime_ms={lifetime_ms:.3f} "
                        f"total_cpu_ms={total_cpu_ms:.3f} "
                        f"peak_effective_cores={peak_eff:.3f}",
                        flush=True,
                    )
                    self._all_seen_exited_pids[pid] = {
                        "lifetime_ms": lifetime_ms,
                        "total_cpu_ms": total_cpu_ms,
                        "peak_eff": peak_eff,
                    }

            # Log every 250ms
            if now_mono - self._last_log_mono_ns >= self._LOG_INTERVAL_S * 1_000_000_000:
                deltas = self._compute_interval_cpu_deltas(interval_samples[0], interval_samples[-1])
                if deltas:
                    self._emit_cpu_window(deltas, self.phase, interval_samples[0].wall_ns, interval_samples[-1].wall_ns)
                self._last_log_mono_ns = cur.mono_ns
                self._last_log_wall_ns = cur.wall_ns
                interval_samples = [cur]
                self._interval_count += 1

        else:
            # completed without break (stop event)
            if interval_samples and len(interval_samples) >= 2:
                deltas = self._compute_interval_cpu_deltas(interval_samples[0], interval_samples[-1])
                if deltas:
                    self._emit_cpu_window(deltas, self.phase, interval_samples[0].wall_ns, interval_samples[-1].wall_ns)

    def _emit_final_summary(self) -> None:
        duration_ms = max(1, (time.monotonic_ns() - self._entry_mono_ns) / 1_000_000.0)
        errors: list[str] = []

        # ── Separate PID categories ──────────────────────────────────────
        # Identify child PIDs (PPID == our PID) and other PIDs
        # Uses pid:starttime identity keys from the watcher tracking
        child_pid_keys: set[str] = set()
        other_pid_keys: set[str] = set()
        for key in self._cpu_by_pid_identity:
            pid_str = key.split(":")[0]
            # Check if this PID has PPID == our PID by looking at create records
            # or by checking the process relationship
            # Use _all_seen_created_pids ppid field when available
            created_info = self._all_seen_created_pids.get(pid_str, {})
            ppid = created_info.get("ppid")
            if ppid is not None and ppid == self._pid:
                child_pid_keys.add(key)
            elif pid_str == str(self._pid):
                pass  # skip self
            else:
                other_pid_keys.add(key)

        # ── Aggregate totals ─────────────────────────────────────────────
        main_total_cpu_ms = 0.0
        child_total_cpu_ms = 0.0
        other_total_cpu_ms = 0.0
        main_peak_eff = 0.0
        child_peak_eff = 0.0
        other_peak_eff = 0.0

        for key, val in self._cpu_by_pid_identity.items():
            if key in child_pid_keys:
                child_total_cpu_ms += val
            elif key in other_pid_keys:
                other_total_cpu_ms += val
        for key, val in self._peak_cores_by_pid.items():
            if key in child_pid_keys and val > child_peak_eff:
                child_peak_eff = val
            elif key in other_pid_keys and val > other_peak_eff:
                other_peak_eff = val

        for key, val in self._cpu_by_tid_identity.items():
            main_total_cpu_ms += val
        for key, val in self._peak_cores_by_tid.items():
            if val > main_peak_eff:
                main_peak_eff = val

        visible_other_total_cpu_ms = child_total_cpu_ms + other_total_cpu_ms
        visible_total_cpu_ms = main_total_cpu_ms + visible_other_total_cpu_ms
        visible_peak_eff = max(child_peak_eff, other_peak_eff)
        visible_total_peak_eff = max(main_peak_eff, visible_peak_eff)

        # Probe thread CPU
        probe_cpu_ms = self._probe_thread_cpu_total_ns / 1_000_000.0 if self._probe_thread_cpu_total_ns else 0.0
        probe_eff = probe_cpu_ms / duration_ms if duration_ms > 0 else 0.0

        # ── Top identities ───────────────────────────────────────────────
        sorted_tids = sorted(self._cpu_by_tid_identity.items(), key=lambda x: x[1], reverse=True)
        sorted_child_pids = sorted(
            ((k, v) for k, v in self._cpu_by_pid_identity.items() if k in child_pid_keys),
            key=lambda x: x[1], reverse=True,
        )
        sorted_other_pids = sorted(
            ((k, v) for k, v in self._cpu_by_pid_identity.items() if k in other_pid_keys),
            key=lambda x: x[1], reverse=True,
        )

        # Lookup comm for a given key (tid identity or pid identity) - capture fingerprint or created records
        def _tid_comm(tid_str: str) -> str:
            """Look up comm for a native TID string."""
            rec = self._all_seen_created_tids.get(tid_str, {})
            comm = rec.get("comm", "")
            if comm:
                return str(comm)
            # Try capture fingerprint
            cap_fp = _V2_SNAPSHOT_CAPTURE_FINGERPRINT.get("_fp_object")
            if cap_fp is not None:
                for tr in getattr(cap_fp, "proc_task_records", []):
                    if str(tr.get("tid", "")) == tid_str:
                        comm = tr.get("comm", "")
                        if comm:
                            return str(comm)
            return "?"

        def _pid_comm(pid_str: str) -> str:
            """Look up comm for a PID string."""
            rec = self._all_seen_created_pids.get(pid_str, {})
            comm = rec.get("comm", "")
            if comm:
                return str(comm)
            return "?"

        top_native = ",".join(
            f"{k.split(':')[0]}:{_tid_comm(k.split(':')[0])}:{v:.3f}" for k, v in sorted_tids[:5]
        ) or "none"
        top_child = ",".join(
            f"{k.split(':')[0]}:{_pid_comm(k.split(':')[0])}:{v:.3f}" for k, v in sorted_child_pids[:5]
        ) or "none"
        top_other = ",".join(
            f"{k.split(':')[0]}:{_pid_comm(k.split(':')[0])}:{v:.3f}" for k, v in sorted_other_pids[:5]
        ) or "none"

        # ── Coordinator worker identities from fingerprints ──────────────
        cap_fp = _V2_SNAPSHOT_CAPTURE_FINGERPRINT.get("_fp_object")
        rst_fp = _V2_RESTORE_FINGERPRINT.get("_fp_object")
        coord_worker_native_ids: set[str] = set()
        coord_worker_names: list[str] = []
        # Prefer restore fingerprint's bridge_snapshot pool_threads (most current)
        if rst_fp is not None:
            bridge_snap = getattr(rst_fp, "bridge_snapshot", None) or {}
            pool_threads = bridge_snap.get("pool_threads", [])
            if isinstance(pool_threads, (list, tuple)) and pool_threads:
                for pt in pool_threads:
                    nid = pt.get("native_id")
                    if nid is not None:
                        coord_worker_native_ids.add(str(nid))
                        pt_name = pt.get("name", "?") or "?"
                        coord_worker_names.append(f"{nid}:{pt_name}")
        # Fall back to capture fingerprint's coordinator_state pool_threads
        if not coord_worker_native_ids and cap_fp is not None:
            cs = getattr(cap_fp, "coordinator_state", None) or {}
            pool_threads = cs.get("pool_threads", [])
            if isinstance(pool_threads, (list, tuple)):
                for pt in pool_threads:
                    nid = pt.get("native_id")
                    if nid is not None:
                        coord_worker_native_ids.add(str(nid))
                        pt_name = pt.get("name", "?") or "?"
                        coord_worker_names.append(f"{nid}:{pt_name}")
        # Also include any known coordinator TIDs from thread name prefix "comfymodal-restore"
        # that are present in the capture fingerprint's proc_task_records
        if cap_fp is not None:
            for tr in getattr(cap_fp, "proc_task_records", []):
                tid = str(tr.get("tid", ""))
                comm = tr.get("comm", "") or ""
                if "comfymodal" in comm or "restore" in comm:
                    if tid and tid not in coord_worker_native_ids and tid.isdigit():
                        coord_worker_native_ids.add(tid)
                        coord_worker_names.append(f"{tid}:{comm}")

        # Coord worker CPU from watcher tracked TID identities that match coordinator worker IDs
        coord_worker_tids_list = sorted(
            list(coord_worker_native_ids & set(k.split(":")[0] for k in self._cpu_by_tid_identity)),
        )[:16]
        coord_worker_tids_str = ",".join(coord_worker_tids_list) or "none"
        coord_worker_total_cpu = sum(
            v for k, v in self._cpu_by_tid_identity.items()
            if k.split(":")[0] in coord_worker_native_ids
        )
        coord_worker_peak = max(
            (v for k, v in self._peak_cores_by_tid.items()
             if k.split(":")[0] in coord_worker_native_ids),
            default=0.0,
        )
        # Captured native TIDs (from capture fingerprint task records) that are NOT coordinator workers
        captured_native_all: set[str] = set()
        if cap_fp is not None:
            for tr in getattr(cap_fp, "proc_task_records", []):
                t = tr.get("tid")
                if t is not None:
                    captured_native_all.add(str(t))
        captured_native_non_coord = captured_native_all - coord_worker_native_ids

        # Preserved: captured native TIDs that still appear in watcher tracking
        watcher_tid_idents = set(k.split(":")[0] for k in self._cpu_by_tid_identity)
        preserved_tids = captured_native_all & watcher_tid_idents
        preserved_count = len(preserved_tids)
        preserved_tids_str = ",".join(sorted(preserved_tids)[:32]) or "none"

        # Non-coordinator captured native CPU
        captured_native_non_coord_total_cpu = sum(
            v for k, v in self._cpu_by_tid_identity.items()
            if k.split(":")[0] in captured_native_non_coord
        )
        captured_native_non_coord_peak = max(
            (v for k, v in self._peak_cores_by_tid.items()
             if k.split(":")[0] in captured_native_non_coord),
            default=0.0,
        )

        # New thread names as list
        new_thread_names_list = []
        for tid_key in sorted(self._all_seen_created_tids.keys()):
            d = self._all_seen_created_tids.get(tid_key, {})
            comm = d.get("comm", "?") or "?"
            new_thread_names_list.append(f"{tid_key}:{comm}")
        new_thread_names_fmt = ",".join(new_thread_names_list[:32]) or "none"

        # Native/child seen/created/exited counts
        native_tids_seen = len(self._seen_tid_identities)
        native_tids_created_after_restore = len(self._all_seen_created_tids)
        native_tids_exited = len(self._all_seen_exited_tids)
        visible_pids_seen = len(self._seen_pid_identities)
        child_pids_created = sum(
            1 for item in self._all_seen_created_pids.values()
            if item.get("ppid") == self._pid
        )
        child_pids_exited = sum(
            1 for pid, item in self._all_seen_exited_pids.items()
            if self._all_seen_created_pids.get(pid, {}).get("ppid") == self._pid
        )

        # ── Evidence-based classification ────────────────────────────────
        # Use visible_total_peak_eff as the measured denominator.
        # Categories contribute against visible_total_peak_eff, not main_process.
        classification = "outside_pid_namespace_or_dashboard_mismatch"
        reasons: list[str] = []

        # Calculate contributions as fractions of visible_total_peak_eff
        # (using accumulated CPU ms for proportion)
        visible_denom = max(visible_total_cpu_ms, 0.001)

        coord_frac = coord_worker_total_cpu / visible_denom
        captured_nc_frac = captured_native_non_coord_total_cpu / visible_denom
        new_tid_frac = sum(
            v for k, v in self._cpu_by_tid_identity.items()
            if k.split(":")[0] not in coord_worker_native_ids
            and k.split(":")[0] not in captured_native_non_coord
        ) / visible_denom
        child_frac = child_total_cpu_ms / visible_denom
        other_frac = other_total_cpu_ms / visible_denom

        if visible_total_peak_eff >= 4.0:
            # High CPU scenario — check for dominant category (>=60%)
            if coord_frac >= 0.6:
                classification = "coordinator_worker_cpu"
                reasons.append(f"coord_frac={coord_frac:.3f} peak={visible_total_peak_eff:.2f}")
            elif captured_nc_frac >= 0.60:
                classification = "captured_native_threads"
                reasons.append(f"captured_nc_frac={captured_nc_frac:.3f} peak={visible_total_peak_eff:.2f}")
            elif new_tid_frac >= 0.60:
                classification = "new_native_threads_after_restore"
                reasons.append(f"new_tid_frac={new_tid_frac:.3f} peak={visible_total_peak_eff:.2f}")
            elif child_frac >= 0.60:
                classification = "visible_child_processes"
                reasons.append(f"child_frac={child_frac:.3f} peak={visible_total_peak_eff:.2f}")
            else:
                # Multiple categories materially contribute — mixed
                classification = "mixed_container_visible_cpu"
                reasons.append(
                    f"coord={coord_frac:.3f} captured_nc={captured_nc_frac:.3f} "
                    f"new_tid={new_tid_frac:.3f} child={child_frac:.3f} other={other_frac:.3f} "
                    f"peak={visible_total_peak_eff:.2f}"
                )
        else:
            # Low CPU (<4 cores peak)
            if native_tids_created_after_restore > 0 or child_pids_created > 0 or other_pid_keys:
                # Observable explanation exists
                if coord_frac >= 0.6:
                    classification = "coordinator_worker_cpu"
                elif captured_nc_frac >= 0.60:
                    classification = "captured_native_threads"
                elif new_tid_frac >= 0.60:
                    classification = "new_native_threads_after_restore"
                elif child_frac >= 0.5 or child_pids_created > 0:
                    classification = "visible_child_processes"
                else:
                    classification = "container_visible_cpu_not_high"
                reasons.append(
                    f"peak={visible_total_peak_eff:.2f} "
                    f"coord={coord_frac:.3f} captured_nc={captured_nc_frac:.3f} "
                    f"new_tid={new_tid_frac:.3f} child={child_frac:.3f} other={other_frac:.3f}"
                )
            else:
                classification = "outside_pid_namespace_or_dashboard_mismatch"
                reasons.append(f"peak={visible_total_peak_eff:.2f} no_observable_explanation")

        # If nothing happened, probe_failed
        if native_tids_seen == 0 and visible_pids_seen == 0 and duration_ms > 5000:
            classification = "probe_failed"
            reasons = [f"no_tids_or_pids_in_{duration_ms:.0f}ms"]

        # Snapshot/restore torch thread counts from capture/restore fingerprints
        snap_torch_nt = cap_fp.torch_state.get("num_threads", "unknown") if cap_fp else "unknown"
        snap_torch_ni = cap_fp.torch_state.get("num_interop_threads", "unknown") if cap_fp else "unknown"
        rst_fp = _V2_RESTORE_FINGERPRINT.get("_fp_object")
        rst_torch_nt = rst_fp.torch_state.get("num_threads", "unknown") if rst_fp else "unknown"
        rst_torch_ni = rst_fp.torch_state.get("num_interop_threads", "unknown") if rst_fp else "unknown"

        summary_status = "ok"
        if self._records_truncated:
            errors.append("records_truncated")

        # Restore fingerprint values — hash match as true/false/unknown
        restore_cpu_flags = (rst_fp.cpu.cpu_flags_hash or "unknown") if rst_fp else "unknown"
        snap_cpu_flags = (cap_fp.cpu.cpu_flags_hash or "absent") if cap_fp else "absent"
        if cap_fp and rst_fp:
            if cap_fp.cpu.cpu_flags_hash and rst_fp.cpu.cpu_flags_hash:
                flags_match = "true" if cap_fp.cpu.cpu_flags_hash == rst_fp.cpu.cpu_flags_hash else "false"
            elif not cap_fp.cpu.cpu_flags_hash and not rst_fp.cpu.cpu_flags_hash:
                flags_match = "true"  # both absent = match
            else:
                flags_match = "unknown"  # one absent, one present
        else:
            flags_match = "unknown"

        print(
            f"[v2.restore_worker_probe_summary] "
            f"duration_ms={duration_ms:.3f} "
            f"sample_interval_ms={int(self._SAMPLE_INTERVAL_S * 1000)} "
            f"sample_count={self._total_samples} "
            f"probe_thread_cpu_ms={probe_cpu_ms:.3f} "
            f"probe_thread_effective_cores={probe_eff:.3f} "
            f"main_process_total_cpu_ms={main_total_cpu_ms:.3f} "
            f"main_process_peak_effective_cores={main_peak_eff:.3f} "
            f"visible_other_process_total_cpu_ms={visible_other_total_cpu_ms:.3f} "
            f"visible_other_process_peak_effective_cores={visible_peak_eff:.3f} "
            f"visible_total_cpu_ms={visible_total_cpu_ms:.3f} "
            f"visible_total_peak_effective_cores={visible_total_peak_eff:.3f} "
            f"native_tids_seen={native_tids_seen} "
            f"native_tids_created_after_restore={native_tids_created_after_restore} "
            f"native_tids_exited={native_tids_exited} "
            f"visible_pids_seen={visible_pids_seen} "
            f"child_pids_created={child_pids_created} "
            f"child_pids_exited={child_pids_exited} "
            f"top_native_threads={top_native} "
            f"top_child_processes={top_child} "
            f"top_other_processes={top_other} "
            f"coordinator_worker_tids={coord_worker_tids_str} "
            f"coordinator_worker_names={','.join(coord_worker_names[:8]) or 'none'} "
            f"coordinator_worker_total_cpu_ms={coord_worker_total_cpu:.3f} "
            f"coordinator_worker_peak_effective_cores={coord_worker_peak:.3f} "
            f"captured_native_non_coord_total_cpu_ms={captured_native_non_coord_total_cpu:.3f} "
            f"captured_native_non_coord_peak_effective_cores={captured_native_non_coord_peak:.3f} "
            f"captured_native_tids_preserved={preserved_tids_str} "
            f"captured_native_count={preserved_count} "
            f"new_native_thread_names={new_thread_names_fmt} "
            f"snapshot_cpu_flags_hash={snap_cpu_flags} "
            f"restore_cpu_flags_hash={restore_cpu_flags} "
            f"cpu_flags_hash_match={flags_match} "
            f"snapshot_torch_num_threads={snap_torch_nt} "
            f"restore_torch_num_threads={rst_torch_nt} "
            f"snapshot_torch_num_interop_threads={snap_torch_ni} "
            f"restore_torch_num_interop_threads={rst_torch_ni} "
            f"records_truncated={self._records_truncated} "
            f"status={summary_status}"
            + (f" errors={','.join(errors)}" if errors else ""),
            flush=True,
        )

        print(
            f"[v2.restore_worker_classification] "
            f"classification={classification}"
            + (f" reasons={' '.join(reasons)}" if reasons else ""),
            flush=True,
        )


# ── Public starter / phase setter / finisher ──────────────────────────


def start_restore_worker_probe() -> _RestoreCpuWatcher | None:
    """Start the restore CPU watcher daemon thread.

    Returns the watcher instance or None on failure.
    Must be called after claim_restore_entry() on the first restore.
    The watcher is a one-shot 10s daemon that does not block restore.
    """
    global _RESTORE_WATCHER_INSTANCE
    try:
        watcher = _RestoreCpuWatcher(
            _RESTORE_MONO_NS or time.monotonic_ns(),
            _RESTORE_WALL_NS or time.time_ns(),
        )
        watcher.set_phase("restore_entry")
        watcher.start()
        _RESTORE_WATCHER_INSTANCE = watcher
        return watcher
    except Exception:
        return None


def set_restore_fingerprint(fp: RuntimeFingerprint) -> None:
    """Store the restore fingerprint at module level for watcher access."""
    global _V2_RESTORE_FINGERPRINT
    _V2_RESTORE_FINGERPRINT.clear()
    _V2_RESTORE_FINGERPRINT["_fp_object"] = fp
    _V2_RESTORE_FINGERPRINT["stage"] = "restore"


def set_restore_worker_probe_phase(phase: str) -> None:
    """Set the current phase for the watcher (thread-safe)."""
    global _RESTORE_WATCHER_INSTANCE
    w = _RESTORE_WATCHER_INSTANCE
    if w is not None:
        w.set_phase(phase)


def finish_restore_worker_probe() -> None:
    """Signal the watcher to stop (non-blocking).
    Normal restore must NOT call this.  It is an explicit API for
    external completion; the watcher naturally ends after 10s.
    """
    global _RESTORE_WATCHER_INSTANCE
    w = _RESTORE_WATCHER_INSTANCE
    if w is not None:
        w.stop()
        _RESTORE_WATCHER_INSTANCE = None
