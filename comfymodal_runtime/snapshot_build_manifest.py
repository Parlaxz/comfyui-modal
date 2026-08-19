"""Snapshot-build-only manifest (default OFF).

Records, immediately before Modal's snapshot capture and again at the
first restored Python line, the process state that Modal serializes into
the memory snapshot: RSS / max RSS / VmSize, ``/proc/self/smaps_rollup``,
mapping totals (anonymous vs file-backed, grouped by mapped path),
imported module names, native and Python thread counts + names, child
processes, open file descriptors summarized by target, Torch intra/inter-op
thread settings, retained CLIP/UNET/VAE identities and storage bytes,
registered global executors/futures, a bounded Python GC object-count
summary, and Modal class/image/resource identity.

Purpose: the pre-Python scheduling stage (submission → Python resume) is
Modal-side but is influenced by what *our* code captures into the snapshot.
This module lets a controlled run prove (or falsify) snapshot-composition
hypotheses with the same data captured at both boundaries.

Gate: ``COMFYMODAL_V2_SNAPSHOT_MANIFEST`` (default off).  Never enable this
during measured latency runs — the capture itself costs tens of
milliseconds and allocates.  Everything here is bounded, JSON-safe and
never raises.

R2a additions: ``status`` also records ``RssAnon``/``RssFile`` (kB) and the
manifest carries a ``cgroup`` entry reading ``memory.current`` (cgroup v2,
v1 ``usage_in_bytes`` fallback), so the snapshot boundary can be measured
from the cgroup accounting side as well.
"""

from __future__ import annotations

import gc
import json
import os
import platform
import sys
import threading
import time
from typing import Any

_GATE_KEY = "COMFYMODAL_V2_SNAPSHOT_MANIFEST"
_TRUTHY = {"1", "true", "yes", "on"}
_MAX_MODULES = 4000
_MAX_MAPPING_PATHS = 60
_MAX_FD_TARGETS = 40
_MAX_THREAD_NAMES = 64
_MAX_CHILDREN = 32
_MAX_EXECUTORS = 32
_MAX_GC_TYPES = 24
_MAX_STORAGE_RANGES = 64

_LATEST_BY_STAGE: dict[str, dict[str, Any]] = {}


def manifest_enabled() -> bool:
    return os.environ.get(_GATE_KEY, "").strip().lower() in _TRUTHY


def _read_proc(path: str, max_bytes: int = 1 << 20) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_bytes)
    except Exception:
        return None


def _capture_status() -> dict[str, Any]:
    out: dict[str, Any] = {}
    raw = _read_proc("/proc/self/status")
    if not raw:
        return out
    _anon_keys = {"RssAnon": "rss_anon", "RssFile": "rss_file"}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in ("VmRSS", "VmHWM", "VmSize", "VmData", "VmStk", "Threads"):
            try:
                out[key.lower()] = int(value.strip().split()[0])
            except Exception:
                out[key.lower()] = value.strip()
        elif key in _anon_keys:
            try:
                out[_anon_keys[key]] = int(value.strip().split()[0])
            except Exception:
                out[_anon_keys[key]] = value.strip()
    return out


def _capture_cgroup() -> dict[str, Any]:
    """cgroup memory.current (v2) with v1 usage_in_bytes fallback.

    Returns ``{"available": bool, "memory_current_bytes": int | None}``;
    ``None`` bytes when unreadable.  Never raises."""
    for path in (
        "/sys/fs/cgroup/memory.current",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes",
    ):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read(4096)
            if not raw:
                continue
            return {"available": True, "memory_current_bytes": int(raw.strip().split()[0])}
        except Exception:
            continue
    return {"available": False, "memory_current_bytes": None}


def _capture_smaps_rollup() -> dict[str, int] | None:
    raw = _read_proc("/proc/self/smaps_rollup")
    if not raw:
        return None
    out: dict[str, int] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        try:
            out[key.strip().lower()] = int(value.strip().split()[0])
        except Exception:
            continue
    return out


def _capture_mappings() -> dict[str, Any]:
    """Mapping totals grouped anonymous/file-backed and by mapped path."""
    raw = _read_proc("/proc/self/maps")
    if not raw:
        return {"available": False}
    anonymous = 0
    file_backed = 0
    other = 0
    path_counts: dict[str, int] = {}
    total_count = 0
    for line in raw.splitlines():
        if " " not in line:
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        pathname = fields[-1] if len(fields) >= 6 else ""
        total_count += 1
        if not pathname or pathname.startswith("["):
            anonymous += 1
        else:
            file_backed += 1
        if pathname:
            key = pathname[:160]
            path_counts[key] = path_counts.get(key, 0) + 1
    top_paths = sorted(path_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_MAX_MAPPING_PATHS]
    return {
        "available": True,
        "total_mappings": total_count,
        "anonymous_mappings": anonymous,
        "file_backed_mappings": file_backed,
        "other_mappings": other,
        "top_paths_by_count": [{"path": p, "count": c} for p, c in top_paths],
    }


def _capture_modules() -> dict[str, Any]:
    names = sorted(sys.modules.keys())[:_MAX_MODULES]
    return {
        "count": len(sys.modules),
        "sampled": _MAX_MODULES,
        "names": names,
    }


def _capture_threads() -> dict[str, Any]:
    native_count: int | None = None
    task_raw = _read_proc("/proc/self/task", max_bytes=1 << 16)
    if task_raw is not None:
        native_count = len([x for x in task_raw.splitlines() if x.strip()])
    names: list[str] = []
    try:
        for t in threading.enumerate():
            names.append(str(getattr(t, "name", ""))[:96])
    except Exception:
        pass
    return {
        "native_count": native_count,
        "python_thread_names": names[:_MAX_THREAD_NAMES],
        "python_thread_count": len(names),
    }


def _capture_children() -> dict[str, Any]:
    self_pid = os.getpid()
    children: list[int] = []
    try:
        entries = os.listdir("/proc")
    except Exception:
        entries = []
    for entry in entries:
        if not entry.isdigit():
            continue
        stat = _read_proc(f"/proc/{entry}/stat", max_bytes=4096)
        if not stat:
            continue
        try:
            # comm may contain spaces; parse ppid after the last ')'.
            rest = stat.rpartition(")")[2].strip()
            fields = rest.split()
            if len(fields) >= 2 and fields[1].isdigit() and int(fields[1]) == self_pid:
                children.append(int(entry))
        except Exception:
            continue
        if len(children) >= _MAX_CHILDREN:
            break
    return {"pid": self_pid, "children": children}


def _capture_fds() -> dict[str, Any]:
    targets: dict[str, int] = {}
    total = 0
    try:
        entries = os.listdir("/proc/self/fd")
    except Exception:
        return {"available": False}
    for entry in entries:
        if not entry.isdigit():
            continue
        total += 1
        try:
            target = os.readlink(f"/proc/self/fd/{entry}")
        except Exception:
            target = "<unresolved>"
        key = target[:160]
        targets[key] = targets.get(key, 0) + 1
    top = sorted(targets.items(), key=lambda kv: (-kv[1], kv[0]))[:_MAX_FD_TARGETS]
    return {
        "available": True,
        "total_fds": total,
        "top_targets": [{"target": t, "count": c} for t, c in top],
    }


def _capture_torch_threads() -> dict[str, Any]:
    out: dict[str, Any] = {"torch_importable": False}
    try:
        import torch
    except Exception:
        return out
    out["torch_importable"] = True
    try:
        out["torch_version"] = str(torch.__version__)
    except Exception:
        pass
    for name, fn in (
        ("intraop_threads", lambda: torch.get_num_threads()),
        ("interop_threads", lambda: torch.get_num_interop_threads()),
    ):
        try:
            out[name] = int(fn())
        except Exception:
            out[name] = None
    return out


def _model_storage_bytes(model: Any) -> dict[str, Any]:
    """Best-effort storage bytes for one model; bounded to 64 storages."""
    total = 0
    ranges = 0
    try:
        if hasattr(model, "parameters"):
            for p in model.parameters():
                if p is None:
                    continue
                try:
                    st = p.untyped_storage() if hasattr(p, "untyped_storage") else p.storage()
                except Exception:
                    continue
                try:
                    total += int(st.nbytes())
                except Exception:
                    total += int(st.size()) * max(1, p.element_size())
                ranges += 1
                if ranges >= _MAX_STORAGE_RANGES:
                    break
    except Exception:
        pass
    return {"storage_ranges": ranges, "storage_bytes": total}


def _capture_retained_models(model_ctx: Any) -> dict[str, Any]:
    """Retained CLIP/UNET/VAE identity + storage bytes from the snapshot models."""
    out: dict[str, Any] = {"present": model_ctx is not None}
    if model_ctx is None:
        return out
    try:
        key = getattr(model_ctx, "model_key", None)
        if key is not None:
            for role in ("unet_identity", "clip_identity", "vae_identity"):
                val = getattr(key, role, "") or ""
                if val:
                    out[role] = str(val)[:96]
    except Exception:
        pass
    for role, attr in (("unet", "unet"), ("clip", "clip"), ("vae", "vae")):
        model = None
        try:
            model = getattr(model_ctx, attr, None)
        except Exception:
            model = None
        if model is None:
            continue
        entry: dict[str, Any] = {
            "object_id": str(id(model)),
            "type": type(model).__name__,
        }
        entry.update(_model_storage_bytes(model))
        out[role] = entry
    return out


def _capture_executors() -> dict[str, Any]:
    """Registered global executors/futures: scan loaded modules' globals."""
    found: list[dict[str, Any]] = []
    for mod_name in list(sys.modules)[:_MAX_MODULES]:
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        try:
            names = getattr(mod, "__dict__", {})
        except Exception:
            continue
        for attr_name in list(names)[:256]:
            obj = names.get(attr_name)
            if obj is None or not isinstance(obj, object):
                continue
            cls_name = type(obj).__name__
            if cls_name in ("ThreadPoolExecutor", "ProcessPoolExecutor"):
                found.append({
                    "module": mod_name[:96],
                    "attr": str(attr_name)[:64],
                    "type": cls_name,
                })
                if len(found) >= _MAX_EXECUTORS:
                    return {"count": len(found), "executors": found}
    return {"count": len(found), "executors": found}


def _capture_gc() -> dict[str, Any]:
    try:
        gen_counts = list(gc.get_count())
    except Exception:
        gen_counts = []
    type_counts: dict[str, int] = {}
    try:
        objs = gc.get_objects()
        total = len(objs)
        for obj in objs[:_MAX_GC_TYPES * 512]:
            tname = type(obj).__name__
            type_counts[tname] = type_counts.get(tname, 0) + 1
    except Exception:
        total = None
    top = sorted(type_counts.items(), key=lambda kv: -kv[1])[:_MAX_GC_TYPES]
    return {
        "gen_counts": gen_counts,
        "total_objects": total,
        "top_types": [{"type": t, "count": c} for t, c in top],
    }


def _capture_modal_identity() -> dict[str, Any]:
    return {
        "image_id": os.environ.get("MODAL_IMAGE_ID", ""),
        "cloud": os.environ.get("MODAL_CLOUD_PROVIDER", ""),
        "region": os.environ.get("MODAL_REGION", ""),
        "app_name": os.environ.get("COMFYMODAL_V2_APP_NAME", ""),
        "class_name": os.environ.get("COMFYMODAL_V2_CLASS_NAME", ""),
        "container_session_id": os.environ.get("COMFYMODAL_CONTAINER_SESSION_ID", ""),
        "pid": os.getpid(),
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
    }


def capture_snapshot_manifest(
    stage: str,
    *,
    model_ctx: Any = None,
    extra: dict[str, Any] | None = None,
    hygiene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture the full manifest at *stage* (e.g. ``before_capture``,
    ``first_restored_line``).  JSON-safe, bounded, never raises.

    Returns the manifest dict; also stores it under ``_LATEST_BY_STAGE``
    and prints a compact ``[v2.snapshot_manifest]`` line.  When *hygiene*
    (the ``snapshot_capture_hygiene`` event dict) is provided it is stored
    under ``manifest["capture_hygiene"]``.
    """
    manifest: dict[str, Any] = {
        "stage": str(stage),
        "capture_wall_unix_ns": time.time_ns(),
        "capture_mono_ns": time.monotonic_ns(),
        "status": _capture_status(),
        "cgroup": _capture_cgroup(),
        "smaps_rollup": _capture_smaps_rollup(),
        "mappings": _capture_mappings(),
        "modules": _capture_modules(),
        "threads": _capture_threads(),
        "children": _capture_children(),
        "fds": _capture_fds(),
        "torch_threads": _capture_torch_threads(),
        "retained_models": _capture_retained_models(model_ctx),
        "executors": _capture_executors(),
        "gc": _capture_gc(),
        "identity": _capture_modal_identity(),
    }
    if extra:
        manifest["extra"] = extra
    if hygiene is not None:
        manifest["capture_hygiene"] = hygiene
    _LATEST_BY_STAGE[str(stage)] = manifest
    try:
        print(
            f"[v2.snapshot_manifest] stage={stage} "
            f"rss_kb={manifest['status'].get('vmrss')} "
            f"hwm_kb={manifest['status'].get('vmhwm')} "
            f"vmsize_kb={manifest['status'].get('vmsize')} "
            f"rss_anon_kb={manifest['status'].get('rss_anon')} "
            f"rss_file_kb={manifest['status'].get('rss_file')} "
            f"mappings={manifest['mappings'].get('total_mappings')} "
            f"anon={manifest['mappings'].get('anonymous_mappings')} "
            f"file={manifest['mappings'].get('file_backed_mappings')} "
            f"native_threads={manifest['threads'].get('native_count')} "
            f"py_threads={manifest['threads'].get('python_thread_count')} "
            f"modules={manifest['modules'].get('count')} "
            f"fds={manifest['fds'].get('total_fds')} "
            f"children={len(manifest['children'].get('children', []))} "
            f"gc_objects={manifest['gc'].get('total_objects')} "
            f"executors={manifest['executors'].get('count')} "
            f"image={manifest['identity'].get('image_id')} "
            f"cloud={manifest['identity'].get('cloud')} "
            f"region={manifest['identity'].get('region')}",
            flush=True,
        )
    except Exception:
        pass
    return manifest


def latest_manifests() -> dict[str, dict[str, Any]]:
    return dict(_LATEST_BY_STAGE)


def dump_manifest_json(manifest: dict[str, Any]) -> str:
    try:
        return json.dumps(manifest, separators=(",", ":"), sort_keys=True, default=str)
    except Exception:
        return "{}"
