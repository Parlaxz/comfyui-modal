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
import hashlib
import json
import os
import platform
import sys
import threading
import time
import types
from typing import Any
import uuid

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
_MAX_CENSUS_DEPTH = 2
_MAX_CENSUS_NODES = 128
_MAX_CENSUS_CHILDREN = 32
_MAX_CENSUS_TYPES = 32
_MAX_CENSUS_TENSOR_RECORDS = 32
_MAX_CENSUS_FAIL_CLOSED_REASONS = 8

_LATEST_BY_STAGE: dict[str, dict[str, Any]] = {}
_CAPTURE_GENERATION: dict[str, str] = {}


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
    path_bytes: dict[str, int] = {}
    mapped_bytes = 0
    anonymous_bytes = 0
    file_backed_bytes = 0
    total_count = 0
    for line in raw.splitlines():
        if " " not in line:
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        pathname = fields[-1] if len(fields) >= 6 else ""
        total_count += 1
        mapping_bytes = 0
        try:
            start, end = fields[0].split("-", 1)
            mapping_bytes = max(0, int(end, 16) - int(start, 16))
        except Exception:
            pass
        mapped_bytes += mapping_bytes
        if not pathname or pathname.startswith("["):
            anonymous += 1
            anonymous_bytes += mapping_bytes
        else:
            file_backed += 1
            file_backed_bytes += mapping_bytes
        if pathname:
            key = pathname[:160]
            path_counts[key] = path_counts.get(key, 0) + 1
            path_bytes[key] = path_bytes.get(key, 0) + mapping_bytes
    top_paths = sorted(path_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_MAX_MAPPING_PATHS]
    top_paths_by_bytes = sorted(path_bytes.items(), key=lambda kv: (-kv[1], kv[0]))[:_MAX_MAPPING_PATHS]
    return {
        "available": True,
        "total_mappings": total_count,
        "anonymous_mappings": anonymous,
        "file_backed_mappings": file_backed,
        "other_mappings": other,
        "mapped_bytes": mapped_bytes,
        "anonymous_bytes": anonymous_bytes,
        "file_backed_bytes": file_backed_bytes,
        "top_paths_by_count": [{"path": p, "count": c} for p, c in top_paths],
        "top_paths_by_bytes": [{"path": p, "bytes": b} for p, b in top_paths_by_bytes],
    }


def _capture_mapping_composition(
    smaps_rollup: dict[str, int] | None,
    mappings: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compose bounded process-memory evidence without inspecting tensors.

    ``smaps_rollup`` is the kernel's resident composition; ``maps`` contributes
    virtual mapping composition.  Neither source is assumed to be the Modal
    serialized snapshot size, and unavailable sources remain unavailable.
    """
    smaps = smaps_rollup if isinstance(smaps_rollup, dict) else {}
    maps = mappings if isinstance(mappings, dict) else {}
    return {
        "available": bool(smaps or maps.get("available")),
        "smaps_available": bool(smaps),
        "mappings_available": bool(maps.get("available")),
        "smaps_rss_kb": smaps.get("rss"),
        "smaps_pss_kb": smaps.get("pss"),
        "smaps_anonymous_kb": smaps.get("anonymous"),
        "smaps_private_dirty_kb": smaps.get("private_dirty"),
        "mapping_virtual_bytes": maps.get("mapped_bytes"),
        "mapping_anonymous_bytes": maps.get("anonymous_bytes"),
        "mapping_file_backed_bytes": maps.get("file_backed_bytes"),
        "note": "resident/mapping composition is not serialized snapshot size",
    }


def _safe_instance_namespace(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return an ordinary instance dictionary without invoking custom code.

    The normal instance ``__dict__`` is a built-in getset descriptor.  A
    class-level property or other descriptor with that name is not trusted:
    even ``object.__getattribute__`` would invoke it.  Looking up the class
    dictionaries through ``type.__getattribute__`` inspects descriptors without
    invoking the descriptor itself.
    """
    try:
        value_type = type(value)
        for base in type.__getattribute__(value_type, "__mro__"):
            class_dict = type.__getattribute__(base, "__dict__")
            if "__dict__" not in class_dict:
                continue
            descriptor = class_dict["__dict__"]
            if type(descriptor) not in {
                types.GetSetDescriptorType,
                types.MemberDescriptorType,
            }:
                return None, "custom_dict_descriptor"
            namespace = object.__getattribute__(value, "__dict__")
            if type(namespace) is not dict:
                return None, "unsafe_instance_dict"
            return namespace, None
        return None, None
    except Exception:
        return None, "instance_dict_unavailable"


def _capture_selected_root_census(
    surfaces: dict[str, list[Any]] | None,
) -> dict[str, Any]:
    """Census only the explicitly supplied proof roots, to a small fixed bound.

    This is intentionally not a heap walk: it does not use ``gc`` referents,
    invokes no arbitrary properties, and records only type/count primitives.
    """
    if type(surfaces) is not dict:
        return {"available": False, "reason": "no_selected_roots"}
    selected: list[tuple[str, Any]] = []
    selected_root_truncated = False
    for kind in ("roots", "registries", "coordinators"):
        try:
            # ``surfaces`` is exact ``dict`` above, so its ordinary ``get``
            # cannot dispatch to caller-defined code.
            values = surfaces.get(kind)
        except Exception:
            continue
        # These are caller-owned top-level containers.  Never call an
        # overridden iterator (or any other subclass hook) while collecting
        # the bounded roots.
        if type(values) is list:
            values_length = len(values)
            values_iter = list.__iter__(values)
        elif type(values) is tuple:
            values_length = len(values)
            values_iter = tuple.__iter__(values)
        else:
            continue
        if values_length > _MAX_CENSUS_CHILDREN:
            selected_root_truncated = True
        try:
            for _ in range(_MAX_CENSUS_CHILDREN):
                try:
                    value = next(values_iter)
                except StopIteration:
                    break
                except Exception:
                    break
                if value is not None:
                    selected.append((kind, value))
        except Exception:
            continue
    if not selected:
        return {"available": False, "reason": "no_selected_roots"}

    queue: list[tuple[str, Any, int, str]] = []
    root_indexes: dict[str, int] = {}
    for kind, value in selected:
        index = root_indexes.get(kind, 0)
        root_indexes[kind] = index + 1
        queue.append((kind, value, 0, f"{kind}[{index}]"))
    seen: set[int] = set()
    type_counts: dict[str, int] = {}
    root_counts: dict[str, int] = {}
    tensor_like = 0
    model_patcher_like = 0
    tensor_records: list[dict[str, Any]] = []
    tensor_storage_ids: set[int] = set()
    tensor_storage_bytes = 0
    containers = 0
    truncated = False
    fail_closed_reasons: dict[str, int] = {}

    def record_fail_closed(reason: str) -> None:
        if reason in fail_closed_reasons:
            fail_closed_reasons[reason] += 1
        elif len(fail_closed_reasons) < _MAX_CENSUS_FAIL_CLOSED_REASONS:
            fail_closed_reasons[reason] = 1

    while queue and len(seen) < _MAX_CENSUS_NODES:
        kind, value, depth, path = queue.pop(0)
        try:
            value_id = id(value)
            if value_id in seen:
                continue
            seen.add(value_id)
            value_type = type(value)
            type_name = str(
                type.__getattribute__(value_type, "__name__")
            )[:96]
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            root_counts[kind] = root_counts.get(kind, 0) + 1
            try:
                module_name = str(
                    type.__getattribute__(value_type, "__dict__").get(
                        "__module__", ""
                    )
                )
            except Exception:
                module_name = ""
            if isinstance(value, (dict, list, tuple, set, frozenset)) and type(value) not in {
                dict, list, tuple, set, frozenset
            }:
                return {"available": False, "reason": "unsafe_selected_container"}
            if type_name in {"Tensor", "Parameter"} or (
                module_name.startswith("torch") and "tensor" in type_name.lower()
            ):
                tensor_like += 1
                if len(tensor_records) < _MAX_CENSUS_TENSOR_RECORDS:
                    record: dict[str, Any] = {
                        "path": path,
                        "type": type_name,
                        "module": module_name[:96],
                    }
                    # Metadata is read only for real torch tensors already
                    # present in sys.modules.  No import, storage copy, or
                    # tensor conversion is performed during the census.
                    torch_module = sys.modules.get("torch")
                    tensor_type = getattr(torch_module, "Tensor", None)
                    parameter_type = getattr(
                        getattr(torch_module, "nn", None), "Parameter", None
                    )
                    if type(value) in {tensor_type, parameter_type}:
                        try:
                            storage = value.untyped_storage()
                            storage_id = int(storage.data_ptr())
                            storage_bytes = int(storage.nbytes())
                            record.update({
                                "device": str(value.device),
                                "dtype": str(value.dtype),
                                "shape": list(value.shape),
                                "numel": int(value.numel()),
                                "storage_bytes": storage_bytes,
                            })
                            if storage_id not in tensor_storage_ids:
                                tensor_storage_ids.add(storage_id)
                                tensor_storage_bytes += storage_bytes
                        except Exception:
                            record["metadata"] = "unavailable"
                    tensor_records.append(record)
            if (
                "modelpatcher" in type_name.lower()
                or "model_patcher" in type_name.lower()
            ):
                model_patcher_like += 1
            if depth >= _MAX_CENSUS_DEPTH:
                continue
            children: Any = None
            if type(value) is dict:
                children = dict.values(value)
                containers += 1
            elif type(value) is list:
                children = list.__iter__(value)
                containers += 1
            elif type(value) is tuple:
                children = tuple.__iter__(value)
                containers += 1
            elif type(value) is set:
                children = set.__iter__(value)
                containers += 1
            elif type(value) is frozenset:
                children = frozenset.__iter__(value)
                containers += 1
            else:
                namespace, namespace_reason = _safe_instance_namespace(value)
                if namespace_reason:
                    record_fail_closed(namespace_reason)
                if type(namespace) is dict:
                    children = namespace.values()
                    containers += 1
            if children is not None:
                for child_index, child in enumerate(children):
                    if child_index >= _MAX_CENSUS_CHILDREN:
                        truncated = True
                        break
                    if child is not None:
                        queue.append((kind, child, depth + 1, f"{path}[{child_index}]"))
        except Exception:
            continue
    if queue:
        truncated = True
    top_types = sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:_MAX_CENSUS_TYPES]
    return {
        "available": True,
        "selected_root_count": len(selected),
        "visited_count": len(seen),
        "depth_limit": _MAX_CENSUS_DEPTH,
        "node_limit": _MAX_CENSUS_NODES,
        "child_limit": _MAX_CENSUS_CHILDREN,
        "truncated": truncated,
        "selected_root_truncated": selected_root_truncated,
        "containers": containers,
        "tensor_like_count": tensor_like,
        "model_patcher_like_count": model_patcher_like,
        "tensor_records": tensor_records,
        "tensor_storage_bytes": tensor_storage_bytes,
        "root_counts": root_counts,
        "top_types": [{"type": name, "count": count} for name, count in top_types],
        "fail_closed_reasons": fail_closed_reasons,
    }


def _capture_generation_evidence(
    stage: str,
    *,
    memory_composition: dict[str, Any],
    root_census: dict[str, Any],
) -> dict[str, Any]:
    """Create or carry a bounded snapshot-capture nonce/fingerprint."""
    global _CAPTURE_GENERATION
    stage = str(stage)
    if stage == "before_capture":
        nonce = uuid.uuid4().hex
        payload = {"memory_composition": memory_composition, "root_census": root_census}
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        _CAPTURE_GENERATION = {"nonce": nonce, "fingerprint": fingerprint}
        continuity = "origin"
    else:
        carried = dict(_CAPTURE_GENERATION)
        if not carried:
            previous = _LATEST_BY_STAGE.get("before_capture", {})
            prior = previous.get("capture_generation") if isinstance(previous, dict) else None
            if isinstance(prior, dict):
                carried = {
                    "nonce": str(prior.get("nonce", "") or ""),
                    "fingerprint": str(prior.get("fingerprint", "") or ""),
                }
        nonce = str(carried.get("nonce", "") or "")
        fingerprint = str(carried.get("fingerprint", "") or "")
        continuity = "continued" if nonce and fingerprint else "unavailable"
    return {
        "schema": "snapshot_capture_generation_v1",
        "nonce": nonce,
        "fingerprint": fingerprint,
        "stage": stage,
        "continuity": continuity,
        "nonce_continuity": continuity,
        "fingerprint_continuity": continuity,
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


def _model_parameter_count(model: Any) -> int | str:
    """Best-effort parameter + buffer element count for one retained model."""
    total = 0
    observed = False
    for method_name in ("named_parameters", "named_buffers"):
        method = getattr(model, method_name, None)
        if not callable(method):
            continue
        try:
            for _name, tensor in method():
                if tensor is None:
                    continue
                numel = getattr(tensor, "numel", None)
                if not callable(numel):
                    return "UNOBSERVABLE"
                total += int(numel())
                observed = True
        except Exception:
            return "UNOBSERVABLE"
    return total if observed or callable(getattr(model, "named_parameters", None)) else "UNOBSERVABLE"


def _model_storage_registry(model_ctx: Any, model: Any, role: str) -> Any:
    """Find an already-built cpu_snapshot_models storage registry, if exposed."""
    for owner, attr in (
        (model_ctx, f"{role}_storage_registry"),
        (model_ctx, f"{role}_registry"),
        (model, "_comfy_modal_cpu_storage_registry"),
    ):
        try:
            registry = getattr(owner, attr, None)
        except Exception:
            registry = None
        if registry is not None:
            return registry
    try:
        registries = getattr(model_ctx, "storage_registries", None)
        if isinstance(registries, dict):
            return registries.get(role)
    except Exception:
        pass
    return None


def _registry_storage_fields(registry: Any) -> dict[str, int | None]:
    if registry is None:
        return {"unique_storage_count": None, "unique_storage_bytes": None}
    try:
        count = getattr(registry, "unique_storage_count", None)
        total = getattr(registry, "total_bytes", None)
        return {
            "unique_storage_count": int(count) if count is not None else None,
            "unique_storage_bytes": int(total) if total is not None else None,
        }
    except Exception:
        return {"unique_storage_count": None, "unique_storage_bytes": None}


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
            "meta_parameter_count": _model_parameter_count(model),
        }
        entry.update(_model_storage_bytes(model))
        entry.update(_registry_storage_fields(_model_storage_registry(model_ctx, model, role)))
        out[role] = entry
    return out


def enumerate_registered_executors() -> list[dict[str, Any]]:
    """Enumerate executor globals, retaining the live object for hygiene checks."""
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
            if obj is None:
                continue
            cls_name = type(obj).__name__
            if cls_name not in ("ThreadPoolExecutor", "ProcessPoolExecutor"):
                continue
            found.append({
                "module": mod_name[:96],
                "attr": str(attr_name)[:64],
                "type": cls_name,
                "object": obj,
            })
            if len(found) >= _MAX_EXECUTORS:
                return found
    return found


def _capture_executors() -> dict[str, Any]:
    """Registered global executors/futures: scan loaded modules' globals."""
    found = enumerate_registered_executors()
    return {
        "count": len(found),
        "executors": [
            {key: value for key, value in item.items() if key != "object"}
            for item in found
        ],
    }


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
    quiescence: dict[str, Any] | None = None,
    selected_roots: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Capture the full manifest at *stage* (e.g. ``before_capture``,
    ``first_restored_line``).  JSON-safe, bounded, never raises.

    Returns the manifest dict; also stores it under ``_LATEST_BY_STAGE``
    and prints a compact ``[v2.snapshot_manifest]`` line.  When *hygiene*
    (the ``snapshot_capture_hygiene`` event dict) is provided it is stored
    under ``manifest["capture_hygiene"]``.
    """
    # Reuse the capture-hygiene measurement functions so RSS/cgroup labels
    # cannot be mistaken for the serialized Modal snapshot size.
    try:
        from .snapshot_capture_hygiene import (
            read_cgroup_memory_current_bytes,
            read_process_status_fields,
        )
        _hygiene_status = read_process_status_fields()
        _cgroup_bytes = read_cgroup_memory_current_bytes()
    except Exception:
        _hygiene_status = {}
        _cgroup_bytes = None
    _rss_kb = _hygiene_status.get("rss_kb")
    _process_rss_bytes = int(_rss_kb) * 1024 if isinstance(_rss_kb, int) else None
    _smaps_rollup = _capture_smaps_rollup()
    _mappings = _capture_mappings()
    _mapping_composition = _capture_mapping_composition(_smaps_rollup, _mappings)
    _root_census = _capture_selected_root_census(selected_roots)
    _capture_generation = _capture_generation_evidence(
        str(stage),
        memory_composition=_mapping_composition,
        root_census=_root_census,
    )
    manifest: dict[str, Any] = {
        "stage": str(stage),
        "capture_wall_unix_ns": time.time_ns(),
        "capture_mono_ns": time.monotonic_ns(),
        "status": _capture_status(),
        "cgroup": _capture_cgroup(),
        "smaps_rollup": _smaps_rollup,
        "mappings": _mappings,
        "memory_composition": _mapping_composition,
        "mapping_composition": _mapping_composition,
        "selected_root_census": _root_census,
        "capture_generation": _capture_generation,
        "capture_generation_nonce": _capture_generation["nonce"],
        "capture_generation_fingerprint": _capture_generation["fingerprint"],
        "capture_generation_continuity": _capture_generation["continuity"],
        "modules": _capture_modules(),
        "threads": _capture_threads(),
        "children": _capture_children(),
        "fds": _capture_fds(),
        "torch_threads": _capture_torch_threads(),
        "retained_models": _capture_retained_models(model_ctx),
        "executors": _capture_executors(),
        "gc": _capture_gc(),
        "identity": _capture_modal_identity(),
        "process_rss_bytes": _process_rss_bytes,
        "process_rss_note": "Process RSS is NOT snapshot size.",
        "cgroup_memory_current_bytes": _cgroup_bytes,
        "cgroup_memory_available": _cgroup_bytes is not None,
        "cgroup_memory_note": "cgroup current is NOT serialized snapshot size.",
        "serialized_snapshot_bytes": "UNOBSERVABLE",
    }
    if extra:
        manifest["extra"] = extra
    if hygiene is not None:
        manifest["capture_hygiene"] = hygiene
    if quiescence is not None:
        manifest["quiescence"] = quiescence
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
