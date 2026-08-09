"""Shared retained-state measurement helper for the 2x2 restore matrix.

Used by BOTH CPU-snapshot and GPU-snapshot shadow arms, immediately before
the ``snap=True`` enter returns (final pre-capture) and at restore time.

This module deliberately does NOT measure "snapshot file size": Modal does
not expose the serialized checkpoint byte count through the 1.4.3 SDK, so
we report a clearly named ``retained_state_footprint`` instead (process
memory + tensor storage + CUDA state) and record ``actual_size_status`` as
"unavailable" for the Modal byte count.

All functions are bounded, JSON-safe and never raise.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import time
import weakref
from collections import Counter
from typing import Any, Mapping

_MIB = 1024.0 * 1024.0


def _read_text(path: str, max_bytes: int = 1 << 20) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_bytes)
    except Exception:  # noqa: BLE001
        return None


def _proc_self_file(name: str) -> str | None:
    return _read_text(f"/proc/self/{name}")


# ── Process memory ────────────────────────────────────────────────────────


def probe_process_memory() -> dict[str, Any]:
    """Process memory: smaps_rollup, status VmRSS/VmHWM, cgroup current/peak.

    All byte counters are normalized to MiB (2 decimals).  Fields that are
    unavailable on the platform are reported as ``None``.
    """
    out: dict[str, Any] = {
        "capture_wall_unix_ns": time.time_ns(),
        "rss_mib": None, "pss_mib": None, "anonymous_mib": None,
        "private_clean_mib": None, "private_dirty_mib": None,
        "shared_clean_mib": None, "shared_dirty_mib": None,
        "swap_mib": None,
        "status_vmrss_mib": None, "status_vmhwm_mib": None,
        "cgroup_current_mib": None, "cgroup_peak_mib": None,
        "source": "unavailable",
    }
    raw = _proc_self_file("smaps_rollup")
    if raw:
        kb: dict[str, Any] = {}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            try:
                kb[key.strip().lower()] = int(value.strip().split()[0])
            except Exception:  # noqa: BLE001
                continue
        if kb:
            for _src_key, _out_key in (
                ("rss", "rss_mib"), ("pss", "pss_mib"), ("anonymous", "anonymous_mib"),
                ("private_clean", "private_clean_mib"), ("private_dirty", "private_dirty_mib"),
                ("shared_clean", "shared_clean_mib"), ("shared_dirty", "shared_dirty_mib"),
                ("swap", "swap_mib"),
            ):
                _raw_kb = kb.get(_src_key)
                if isinstance(_raw_kb, (int, float)):
                    out[_out_key] = round(float(_raw_kb) / 1024.0, 2)
            out["source"] = "smaps_rollup"
    status_raw = _proc_self_file("status")
    if status_raw:
        for line in status_raw.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            if key.strip() in ("VmRSS", "VmHWM"):
                try:
                    _status_kb = int(value.strip().split()[0])
                    out[f"status_{key.strip().lower()}_mib"] = round(_status_kb / 1024.0, 2)
                except Exception:  # noqa: BLE001
                    pass
    for path, key in (
        ("/sys/fs/cgroup/memory.current", "cgroup_current_mib"),
        ("/sys/fs/cgroup/memory.peak", "cgroup_peak_mib"),
    ):
        raw_bytes = _read_text(path, 1 << 16)
        if not raw_bytes:
            continue
        try:
            out[key] = round(int(str(raw_bytes).strip()) / _MIB, 2)
        except Exception:  # noqa: BLE001
            pass
    if out.get("cgroup_current_mib") is None:
        for path, key in (
            ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "cgroup_current_mib"),
            ("/sys/fs/cgroup/memory/memory.max_usage_in_bytes", "cgroup_peak_mib"),
        ):
            raw_bytes = _read_text(path, 1 << 16)
            if not raw_bytes:
                continue
            try:
                out[key] = round(int(str(raw_bytes).strip()) / _MIB, 2)
            except Exception:  # noqa: BLE001
                pass
    return out


# ── Tensor storage (device-agnostic, deduplicated by underlying storage) ──


def _tensor_storage(t: Any) -> Any | None:
    try:
        if hasattr(t, "untyped_storage"):
            st = t.untyped_storage()
        else:
            st = t.storage()
        return st
    except Exception:  # noqa: BLE001
        return None


def _storage_bytes(st: Any) -> int | None:
    try:
        if hasattr(st, "nbytes"):
            nb = st.nbytes()
            if nb:
                return int(nb)
        size: Any = st.size()
        elem = getattr(st, "element_size", None)
        es: Any = elem() if callable(elem) else None
        if size and es:
            return int(size) * int(es)
        return None
    except Exception:  # noqa: BLE001
        return None

def dedupe_model_storage(module: Any) -> dict[str, Any]:
    """Deduplicated storage stats for one module, device-agnostic.

    Iterates parameters and buffers; dedupes by the underlying storage
    object identity (views sharing one storage count once).  Reports
    parameter/buffer counts and bytes (deduplicated), storage count,
    unique bytes, and the device distribution of tensors.  Never raises.
    """
    out: dict[str, Any] = {
        "module_present": module is not None,
        "parameter_count": 0,
        "buffer_count": 0,
        "unique_storage_count": 0,
        "unique_storage_bytes": 0,
        "parameter_bytes": 0,
        "buffer_bytes": 0,
        "device_distribution": {},
    }
    if module is None:
        return out
    seen_storages: dict[int, int] = {}
    devices: Counter[str] = Counter()
    params_bytes = 0
    buffers_bytes = 0
    try:
        for p in module.parameters():
            if p is None:
                continue
            out["parameter_count"] += 1
            dev = str(getattr(p, "device", ""))
            if dev:
                devices[dev] += 1
            st = _tensor_storage(p)
            if st is None:
                continue
            nb = _storage_bytes(st)
            if nb is None:
                continue
            sid = id(st)
            if sid not in seen_storages:
                seen_storages[sid] = nb
            params_bytes += nb
    except Exception:  # noqa: BLE001
        pass
    try:
        for b in module.buffers():
            if b is None:
                continue
            out["buffer_count"] += 1
            dev = str(getattr(b, "device", ""))
            if dev:
                devices[dev] += 1
            st = _tensor_storage(b)
            if st is None:
                continue
            nb = _storage_bytes(st)
            if nb is None:
                continue
            sid = id(st)
            if sid not in seen_storages:
                seen_storages[sid] = nb
            buffers_bytes += nb
    except Exception:  # noqa: BLE001
        pass
    out["unique_storage_count"] = len(seen_storages)
    out["unique_storage_bytes"] = sum(seen_storages.values())
    out["parameter_bytes"] = params_bytes
    out["buffer_bytes"] = buffers_bytes
    out["device_distribution"] = dict(devices)
    return out


def resolve_cpu_models(unet: Any, clip: Any, vae: Any) -> tuple[Any, Any, Any]:
    """Resolve the underlying modules for UNET/CLIP/VAE wrappers.

    Mirrors the shadow residency resolvers: UNET is a ModelPatcher
    (``patcher.model``), CLIP exposes ``cond_stage_model`` (fallback
    ``patcher.model``), VAE exposes ``first_stage_model``.
    """
    unet_module = getattr(unet, "model", None) or unet
    clip_module = getattr(clip, "cond_stage_model", None)
    if clip_module is None:
        _clip_patcher = getattr(clip, "patcher", None)
        clip_module = getattr(_clip_patcher, "model", None) if _clip_patcher is not None else None
    if clip_module is None:
        clip_module = clip
    vae_module = getattr(vae, "first_stage_model", None)
    if vae_module is None:
        _vae_patcher = getattr(vae, "patcher", None)
        vae_module = getattr(_vae_patcher, "model", None) if _vae_patcher is not None else None
    if vae_module is None:
        vae_module = vae
    return unet_module, clip_module, vae_module


def probe_model_storage(
    unet: Any, clip: Any, vae: Any,
    *,
    device_prefix: str | None = None,
) -> dict[str, Any]:
    """Per-model deduplicated storage + totals.

    When *device_prefix* is given (e.g. ``"cuda"``), only tensors whose
    device starts with the prefix are counted, and per-model entries carry
    the ``_cuda_`` suffix keys.  Otherwise all devices are counted with
    plain keys.
    """
    unet_mod, clip_mod, vae_mod = resolve_cpu_models(unet, clip, vae)
    models = {
        "unet": (unet, unet_mod),
        "clip": (clip, clip_mod),
        "vae": (vae, vae_mod),
    }
    suffix = f"_{device_prefix}_bytes" if device_prefix else "_bytes"
    out: dict[str, Any] = {"per_model": {}}
    total_unique = 0
    for role, (obj, module) in models.items():
        entry = dedupe_model_storage(module)
        entry["object_present"] = obj is not None
        entry["patcher_present"] = bool(obj is not None and module is not obj)
        if device_prefix:
            entry["bytes"] = sum(
                nb for sid, nb in _dev_filtered_bytes(module, device_prefix)
            )
            total = entry["bytes"]
            entry.pop("unique_storage_bytes", None)
        else:
            total = entry["unique_storage_bytes"]
        entry["device_distribution"] = _dev_filtered_distribution(module)
        total_unique += int(total or 0)
        out["per_model"][role] = entry
        out[f"{role}{suffix}"] = int(total or 0)
    out["total_unique_model_bytes"] = int(total_unique)
    return out


def _dev_filtered_bytes(module: Any, prefix: str) -> list[tuple[int, int]]:
    """List of (storage_id, bytes) for tensors on devices with *prefix*."""
    seen: dict[int, int] = {}
    try:
        for tensors in (module.parameters(), module.buffers()):
            for t in tensors:
                if t is None:
                    continue
                dev = str(getattr(t, "device", ""))
                if not dev.startswith(prefix):
                    continue
                st = _tensor_storage(t)
                if st is None:
                    continue
                nb = _storage_bytes(st)
                if nb is None:
                    continue
                seen.setdefault(id(st), nb)
    except Exception:  # noqa: BLE001
        pass
    return list(seen.items())


def _dev_filtered_distribution(module: Any) -> dict[str, int]:
    devices: Counter[str] = Counter()
    try:
        for tensors in (module.parameters(), module.buffers()):
            for t in tensors:
                if t is not None:
                    devices[str(getattr(t, "device", ""))] += 1
    except Exception:  # noqa: BLE001
        pass
    return dict(devices)


# ── CUDA state ────────────────────────────────────────────────────────────


def probe_cuda_memory() -> dict[str, Any]:
    """CUDA memory state: allocated/reserved/max + mem_get_info, in MiB.

    Never calls ``empty_cache`` and never frees anything — this measures
    the state as-is.
    """
    out: dict[str, Any] = {
        "available": False,
        "allocated_mib": None, "reserved_mib": None,
        "max_allocated_mib": None, "max_reserved_mib": None,
        "free_mib": None, "total_mib": None,
    }
    try:
        import torch
        if not torch.cuda.is_available():
            return out
        out["available"] = True
        out["allocated_mib"] = round(int(torch.cuda.memory_allocated()) / _MIB, 2)
        out["reserved_mib"] = round(int(torch.cuda.memory_reserved()) / _MIB, 2)
        try:
            out["max_allocated_mib"] = round(int(torch.cuda.max_memory_allocated()) / _MIB, 2)
        except Exception:  # noqa: BLE001
            pass
        try:
            out["max_reserved_mib"] = round(int(torch.cuda.max_memory_reserved()) / _MIB, 2)
        except Exception:  # noqa: BLE001
            pass
        try:
            free_b, total_b = torch.cuda.mem_get_info()
            out["free_mib"] = round(int(free_b) / _MIB, 2)
            out["total_mib"] = round(int(total_b) / _MIB, 2)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    return out


# ── Alive / reference proof ───────────────────────────────────────────────


def probe_alive_weakrefs(unet: Any, clip: Any, vae: Any) -> dict[str, Any]:
    """Weakref-alive flags for the three model objects (no strong refs)."""
    out: dict[str, Any] = {}
    for role, obj in (("unet", unet), ("clip", clip), ("vae", vae)):
        entry = {
            "object_present": obj is not None,
            "object_id": str(id(obj)) if obj is not None else "none",
        }
        if obj is not None:
            try:
                wr = weakref.ref(obj)
                entry["weakref_alive"] = wr() is not None
            except TypeError:
                entry["weakref_alive"] = None
                entry["weakref_error"] = "unsupported"
        else:
            entry["weakref_alive"] = False
        out[role] = entry
    return out


def probe_reference_holders(
    self_obj: Any,
    *,
    model_management: Any = None,
    bootstrap_state: Any = None,
) -> dict[str, Any]:
    """Survey the known reference holders that could keep model storages
    alive despite apparent eviction.  Returns primitives only."""
    out: dict[str, Any] = {
        "self_cpu_snapshot_models_present": False,
        "self_cpu_snapshot_models_active": False,
        "self_eviction_marker_present": False,
        "self_snapshot_eviction_retained_role": "none",
        "bridge_active_preparation": False,
        "bridge_snapshot_loader_outputs": False,
        "bootstrap_snapshot_loader_outputs": False,
        "bootstrap_snapshot_seed_present": False,
        "model_management_registered": 0,
        "model_management_entries": [],
    }
    if self_obj is not None:
        out["self_cpu_snapshot_models_present"] = bool(
            getattr(self_obj, "_cpu_snapshot_models", None) is not None
        )
        out["self_cpu_snapshot_models_active"] = bool(
            getattr(self_obj, "_cpu_snapshot_models_active", False)
        )
        out["self_eviction_marker_present"] = bool(
            getattr(self_obj, "_eviction_marker", None) is not None
        )
        out["self_snapshot_eviction_retained_role"] = str(
            getattr(self_obj, "_snapshot_eviction_retained_role", "none")
        )
        bridge = getattr(self_obj, "_preload_bridge", None)
        if bridge is not None:
            try:
                diag = bridge.diagnostic_snapshot()
            except Exception:  # noqa: BLE001
                diag = {}
            if isinstance(diag, Mapping):
                out["bridge_active_preparation"] = bool(
                    diag.get("active_preparation_exists")
                    or diag.get("current_preparation_exists")
                )
            try:
                out["bridge_snapshot_loader_outputs"] = bool(
                    getattr(bridge, "snapshot_loader_outputs", None)
                )
            except Exception:  # noqa: BLE001
                pass
    if bootstrap_state is not None:
        out["bootstrap_snapshot_loader_outputs"] = bool(
            getattr(bootstrap_state, "snapshot_loader_outputs", None)
        )
        out["bootstrap_snapshot_seed_present"] = bool(
            getattr(bootstrap_state, "snapshot_execution_seed", None) is not None
        )
    if model_management is not None:
        try:
            records = list(getattr(model_management, "current_loaded_models", []) or [])
        except Exception:  # noqa: BLE001
            records = []
        for rec in records:
            try:
                m = getattr(rec, "model", None)
                out["model_management_entries"].append({
                    "patcher_type": type(m).__name__ if m is not None else "none",
                    "object_id": str(id(m)) if m is not None else "none",
                    "device": str(
                        getattr(getattr(m, "model", None), "device", "")
                        if m is not None else ""
                    ),
                })
            except Exception:  # noqa: BLE001
                continue
        out["model_management_registered"] = len(out["model_management_entries"])
    return out


# ── Worker / pool fingerprint ─────────────────────────────────────────────


def _cpuinfo() -> dict[str, Any]:
    out: dict[str, Any] = {
        "available": False,
        "model_name": "", "vendor": "", "family": "", "model": "",
        "stepping": "", "flags_hash": "", "logical_count": 0,
        "physical_count": 0, "sockets": 0, "affinity_count": 0,
        "affinity_hash": "", "numa_nodes": 0,
    }
    raw = _read_text("/proc/cpuinfo", max_bytes=1 << 22)
    if not raw:
        return out
    out["available"] = True
    model_name = vendor = family = model = stepping = ""
    flags: list[str] = []
    physical_ids: set[str] = set()
    cores: set[str] = set()
    processor_count = 0
    cur_phys = ""
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        key = key.strip()
        if key == "model name" and not model_name:
            model_name = value
        elif key == "vendor_id" and not vendor:
            vendor = value
        elif key == "cpu family" and not family:
            family = value
        elif key == "model" and not model:
            model = value
        elif key == "stepping" and not stepping:
            stepping = value
        elif key == "flags":
            flags = value.split()
        elif key == "physical id":
            cur_phys = value
            physical_ids.add(value)
        elif key == "core id":
            cores.add(f"{cur_phys}/{value}")
        elif key == "processor":
            processor_count += 1
    out.update({
        "model_name": model_name,
        "vendor": vendor, "family": family, "model": model, "stepping": stepping,
        "flags_hash": hashlib.sha256(" ".join(sorted(flags)).encode()).hexdigest()[:16],
        "logical_count": processor_count or os.cpu_count() or 0,
        "physical_count": len(cores) or 0,
        "sockets": len(physical_ids) or 0,
    })
    try:
        _sched: Any = getattr(os, "sched_getaffinity", None)
        if callable(_sched):
            aff: Any = _sched(0)
            out["affinity_count"] = len(aff)
            out["affinity_hash"] = hashlib.sha256(
                ",".join(str(a) for a in sorted(aff)).encode()
            ).hexdigest()[:16]
    except Exception:  # noqa: BLE001
        pass
    try:
        nodes = os.listdir("/sys/devices/system/node")
        out["numa_nodes"] = len([n for n in nodes if n.startswith("node")])
    except Exception:  # noqa: BLE001
        pass
    return out


def _nvidia_smi() -> dict[str, Any]:
    out: dict[str, Any] = {"available": False}
    try:
        run = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,uuid,pci.bus_id,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
        if run.returncode != 0 or not run.stdout.strip():
            return out
        first = run.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in first.split(",")]
        if len(parts) >= 4:
            out.update({
                "available": True,
                "gpu_name": parts[0], "gpu_uuid": parts[1],
                "pci_bus_id": parts[2], "driver_version": parts[3],
            })
    except Exception:  # noqa: BLE001
        pass
    return out


def probe_worker_fingerprint(*, cuda_torch: bool = False) -> dict[str, Any]:
    """Cheap immutable worker/pool identity as exposed by the sandbox.

    *cuda_torch* enables torch.cuda-backed fields (only safe when CUDA is
    already initialized, i.e. GPU arms); driver/GPU identity always comes
    from nvidia-smi without initializing CUDA in-process.
    """
    out: dict[str, Any] = {
        "capture_wall_unix_ns": time.time_ns(),
        "requested_cloud": os.environ.get("COMFYMODAL_V2_CLOUD", ""),
        "requested_region": os.environ.get("COMFYMODAL_V2_REGION", ""),
        "modal_cloud_provider": os.environ.get("MODAL_CLOUD_PROVIDER", ""),
        "modal_region": os.environ.get("MODAL_REGION", ""),
        "modal_task_id": os.environ.get("MODAL_TASK_ID", ""),
        "modal_image_id": os.environ.get("MODAL_IMAGE_ID", ""),
        "modal_container_session_id": os.environ.get("MODAL_CONTAINER_SESSION_ID", ""),
        "hostname": platform.node(),
        "pid": os.getpid(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "cpu": _cpuinfo(),
        "gpu": _nvidia_smi(),
        "torch_version": "",
        "torch_cuda_version": "",
        "cuda_allocated_mib": None,
    }
    try:
        import torch
        out["torch_version"] = str(torch.__version__)
        out["torch_cuda_version"] = str(getattr(getattr(torch, "version", None), "cuda", "") or "")
        if cuda_torch and torch.cuda.is_available():
            out["cuda_allocated_mib"] = round(int(torch.cuda.memory_allocated()) / _MIB, 2)
    except Exception:  # noqa: BLE001
        pass
    return out


# ── Stage line emission ───────────────────────────────────────────────────


def emit_stage_line(prefix: str, stage: str, fields: Mapping[str, Any]) -> None:
    """Emit one compact stage line to stdout, e.g.::

        [cpu_snapshot_size] stage=final_pre_capture rss_mib=... ...

    Byte fields are printed raw (bytes), memory fields in MiB.
    """
    parts = [f"stage={stage}"]
    for key in sorted(fields):
        val = fields[key]
        if isinstance(val, float):
            parts.append(f"{key}={val:.2f}")
        elif isinstance(val, (int,)) and not isinstance(val, bool):
            parts.append(f"{key}={val}")
        else:
            parts.append(f"{key}={val}")
    print(f"[{prefix}] " + " ".join(parts), flush=True)
