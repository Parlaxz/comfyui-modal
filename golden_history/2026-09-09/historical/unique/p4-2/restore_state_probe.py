"""Shared retained-state measurement helper for the 2x2 restore matrix.

Used by BOTH CPU-snapshot and GPU-snapshot shadow arms, immediately before
the ``snap=True`` enter returns (final pre-capture) and at restore time.

This module deliberately does NOT measure "snapshot file size": Modal does
not expose the serialized checkpoint byte count through the 1.4.3 SDK, so
we report composition counters instead (process memory + tensor storage +
CUDA state) and record ``serialized_snapshot_size_status`` as "unavailable"
for the Modal byte count.

All functions are bounded, JSON-safe and never raise.
"""

from __future__ import annotations

import hashlib
import gc
import json
import os
import platform
import subprocess
import sys
import sysconfig
import threading
import time
import weakref
from collections import Counter
from typing import Any, Mapping, cast

_MIB = 1024.0 * 1024.0
RUNTIME_MEMORY_FORENSICS_GATE_KEY = "COMFYMODAL_V2_RUNTIME_MEMORY_FORENSICS"
_TRUTHY = {"1", "true", "yes", "on"}
_MAX_FORENSICS_MAPPINGS = 256
_MAX_FORENSICS_BYTES = 8 << 20
_MAX_LARGEST_MAPPINGS = 32
_MAX_MODULE_NAMES = 256


def _read_text(path: str, max_bytes: int = 1 << 20) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_bytes)
    except Exception:  # noqa: BLE001
        return None


def _proc_self_file(name: str) -> str | None:
    return _read_text(f"/proc/self/{name}")


def _proc_self_file_bounded(name: str, max_bytes: int) -> tuple[str | None, bool]:
    """Read a proc file with one sentinel byte so truncation is observable."""
    try:
        with open(f"/proc/self/{name}", "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read(max(0, int(max_bytes)) + 1)
        truncated = len(raw) > max(0, int(max_bytes))
        return raw[:max(0, int(max_bytes))], truncated
    except Exception:  # noqa: BLE001
        return None, False


def runtime_memory_forensics_enabled() -> bool:
    """Return whether the bounded full-smaps diagnostic is explicitly enabled."""
    try:
        return os.environ.get(RUNTIME_MEMORY_FORENSICS_GATE_KEY, "").strip().lower() in _TRUTHY
    except Exception:  # noqa: BLE001
        return False


def _mib_bytes(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(float(value) * _MIB)
    return None


def _parse_kb_lines(raw: str | None) -> dict[str, int]:
    out: dict[str, int] = {}
    if not raw:
        return out
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        try:
            out[key.strip().lower()] = int(value.strip().split()[0])
        except Exception:  # noqa: BLE001
            continue
    return _normalize_process_memory_schema(out)


def _parse_bounded_smaps(
    raw: str | None,
    *,
    max_mappings: int = _MAX_FORENSICS_MAPPINGS,
    max_bytes: int = _MAX_FORENSICS_BYTES,
    source_truncated: bool = False,
) -> dict[str, Any]:
    """Parse resident composition from a bounded, opt-in ``smaps`` read."""
    result: dict[str, Any] = {
        "available": False,
        "partial": False,
        "partial_reasons": [],
        "bytes_read": 0,
        "mapping_count": 0,
        "native_library_resident_bytes": None,
        "native_library_resident_status": "unavailable",
        "cuda_runtime_host_mapped_bytes": None,
        "cuda_runtime_host_mapped_status": "unavailable",
        "file_backed_resident_bytes": None,
        "file_backed_resident_status": "unavailable",
        "custom_node_resident_bytes": None,
        "custom_node_resident_status": "unavailable",
        "thread_stack_resident_bytes": None,
        "thread_stack_resident_status": "unavailable",
        "largest_mappings": [],
    }
    if not raw:
        return result
    result["available"] = True
    result["bytes_read"] = min(len(raw.encode("utf-8", "replace")), max_bytes)
    if source_truncated:
        result["partial"] = True
        result["partial_reasons"].append("byte_limit")
    mappings: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    consumed = 0
    for line in raw.splitlines():
        consumed += len(line) + 1
        if consumed > max_bytes:
            result["partial"] = True
            if "byte_limit" not in result["partial_reasons"]:
                result["partial_reasons"].append("byte_limit")
            break
        fields = line.split()
        if len(fields) >= 5 and "-" in fields[0] and len(fields[0].split("-", 1)[0]) >= 4:
            if current is not None:
                mappings.append(current)
            if len(mappings) >= max_mappings:
                result["partial"] = True
                result["partial_reasons"].append("mapping_limit")
                break
            current = {"path": "", "rss_kb": 0, "pss_kb": 0}
            if len(fields) >= 6:
                current["path"] = " ".join(fields[5:])[:160]
            continue
        if current is None or ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() not in ("rss", "pss"):
            continue
        try:
            current[f"{key.strip().lower()}_kb"] = int(value.strip().split()[0])
        except Exception:  # noqa: BLE001
            pass
    if current is not None and len(mappings) < max_mappings:
        mappings.append(current)

    native = 0
    cuda_native = 0
    file_backed = 0
    custom = 0
    stacks = 0
    native_known = cuda_native_known = file_backed_known = custom_known = stack_known = False
    for mapping in mappings:
        path = str(mapping.get("path", ""))
        resident = int(mapping.get("rss_kb", 0) or 0) * 1024
        lowered = path.lower()
        if path and not path.startswith("["):
            file_backed += resident
            file_backed_known = True
        if (".so" in lowered or ".dylib" in lowered or ".dll" in lowered
                or "libcuda" in lowered or "libcudart" in lowered):
            native += resident
            native_known = True
            if "cuda" in lowered or "cudart" in lowered:
                cuda_native += resident
                cuda_native_known = True
        if "custom_nodes/" in lowered or "custom-node" in lowered:
            custom += resident
            custom_known = True
        if path.startswith("[stack"):
            stacks += resident
            stack_known = True
    largest = sorted(
        mappings,
        key=lambda item: (-int(item.get("rss_kb", 0) or 0), str(item.get("path", ""))),
    )[:_MAX_LARGEST_MAPPINGS]
    _category_status = "partial" if result["partial"] else "bounded_smaps"
    result.update({
        "mapping_count": len(mappings),
        "native_library_resident_bytes": native if native_known else None,
        "native_library_resident_status": _category_status if native_known else ("partial" if result["partial"] else "unavailable"),
        "cuda_runtime_host_mapped_bytes": cuda_native if cuda_native_known else None,
        "cuda_runtime_host_mapped_status": _category_status if cuda_native_known else ("partial" if result["partial"] else "unavailable"),
        "file_backed_resident_bytes": file_backed if file_backed_known else None,
        "file_backed_resident_status": _category_status if file_backed_known else ("partial" if result["partial"] else "unavailable"),
        "custom_node_resident_bytes": custom if custom_known else None,
        "custom_node_resident_status": _category_status if custom_known else ("partial" if result["partial"] else "unavailable"),
        "thread_stack_resident_bytes": stacks if stack_known else None,
        "thread_stack_resident_status": _category_status if stack_known else ("partial" if result["partial"] else "unavailable"),
        "largest_mappings": [
            {
                "path": str(item.get("path", ""))[:160],
                "resident_bytes": int(item.get("rss_kb", 0) or 0) * 1024,
                "pss_bytes": int(item.get("pss_kb", 0) or 0) * 1024,
            }
            for item in largest
        ],
    })
    return result


def _python_heap_indicators() -> dict[str, Any]:
    out: dict[str, Any] = {
        "available": True,
        "allocated_blocks": None,
        "gc_counts": [],
        "tracemalloc_tracing": False,
        "tracemalloc_current_bytes": None,
        "tracemalloc_peak_bytes": None,
        "tracemalloc_status": "not_started",
    }
    try:
        get_blocks = getattr(sys, "getallocatedblocks", None)
        if callable(get_blocks):
            out["allocated_blocks"] = int(cast(Any, get_blocks)())
    except Exception:  # noqa: BLE001
        pass
    try:
        out["gc_counts"] = [int(value) for value in gc.get_count()]
    except Exception:  # noqa: BLE001
        pass
    # Looking in sys.modules is intentional: measurement must never start
    # tracemalloc merely to obtain a number.
    try:
        trace = sys.modules.get("tracemalloc")
        if trace is not None and bool(trace.is_tracing()):
            out["tracemalloc_tracing"] = True
            out["tracemalloc_status"] = "already_running"
            out["tracemalloc_current_bytes"] = int(trace.get_traced_memory()[0])
            out["tracemalloc_peak_bytes"] = int(trace.get_traced_memory()[1])
    except Exception:  # noqa: BLE001
        out["tracemalloc_status"] = "unavailable"
    return out


def _allocator_indicators() -> dict[str, Any]:
    out: dict[str, Any] = {
        "implementation": platform.python_implementation(),
        "pymalloc_enabled": None,
        "pythonmalloc_env": os.environ.get("PYTHONMALLOC", "") if hasattr(os, "environ") else "",
        "arena_count": None,
        "arena_bytes": None,
        "arena_status": "unavailable_without_allocator_introspection",
    }
    try:
        config = sysconfig.get_config_var("WITH_PYMALLOC")
        out["pymalloc_enabled"] = bool(config) if config is not None else None
    except Exception:  # noqa: BLE001
        pass
    return out


def _resource_indicators() -> dict[str, Any]:
    """Read optional process high-water accounting without changing state."""
    out: dict[str, Any] = {"available": False, "max_rss_bytes": None, "status": "unavailable"}
    try:
        import resource

        getrusage = getattr(resource, "getrusage", None)
        self_resource = getattr(resource, "RUSAGE_SELF", None)
        if not callable(getrusage) or self_resource is None:
            return out
        usage = getrusage(self_resource)
        value = float(getattr(usage, "ru_maxrss"))
        # Linux reports KiB; macOS reports bytes.
        out["max_rss_bytes"] = int(value * 1024 if platform.system() == "Linux" else value)
        out["available"] = True
        out["status"] = "ok"
    except Exception:  # noqa: BLE001
        pass
    return out


def _thread_pool_counts() -> dict[str, int]:
    counts = {"thread_pool_executors": 0, "process_pool_executors": 0}
    try:
        for module in list(sys.modules.values())[:4000]:
            namespace = getattr(module, "__dict__", {})
            for value in list(namespace.values())[:256]:
                name = type(value).__name__
                if name == "ThreadPoolExecutor":
                    counts["thread_pool_executors"] += 1
                elif name == "ProcessPoolExecutor":
                    counts["process_pool_executors"] += 1
    except Exception:  # noqa: BLE001
        pass
    return counts


def _module_indicators() -> dict[str, Any]:
    try:
        names = list(sys.modules.keys())
    except Exception:  # noqa: BLE001
        return {"available": False, "count": None, "custom_node_count": None, "custom_node_names": []}
    custom: list[str] = []
    for name in names:
        if name.startswith("custom_nodes.") or ".custom_nodes." in name:
            custom.append(name)
            continue
        try:
            module_file = str(getattr(sys.modules.get(name), "__file__", ""))
        except Exception:  # noqa: BLE001
            module_file = ""
        if "custom_nodes" in module_file.lower():
            custom.append(name)
    custom.sort()
    return {
        "available": True,
        "count": len(names),
        "sampled": _MAX_MODULE_NAMES,
        "custom_node_count": len(custom),
        "custom_node_names": custom[:_MAX_MODULE_NAMES],
        "custom_node_resident_bytes": None,
        "custom_node_resident_status": "requires_bounded_smaps",
    }


def _cuda_host_indicators() -> dict[str, Any]:
    """Observe already-loaded CUDA state without probing or initializing it."""
    out: dict[str, Any] = {
        "torch_loaded": False,
        "cuda_module_loaded": False,
        "cuda_context_initialized": None,
        "cuda_runtime_host_mapped_bytes": None,
        "cuda_host_allocated_bytes": None,
        "cuda_host_allocation_status": "unavailable_without_cuda_allocator_probe",
    }
    try:
        torch = sys.modules.get("torch")
        out["torch_loaded"] = torch is not None
        cuda = getattr(torch, "cuda", None) if torch is not None else None
        out["cuda_module_loaded"] = cuda is not None
        is_initialized = getattr(cuda, "is_initialized", None)
        if callable(is_initialized):
            # is_initialized() is a local state check; unlike is_available(),
            # it does not ask the driver to initialize or synchronize.
            out["cuda_context_initialized"] = bool(is_initialized())
    except Exception:  # noqa: BLE001
        pass
    return out


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str, separators=(",", ":")))
    except Exception:  # noqa: BLE001
        return None


# ── Process memory ────────────────────────────────────────────────────────


def _probe_process_memory_impl(
    *,
    include_smaps: bool | None = None,
    max_smaps_mappings: int = _MAX_FORENSICS_MAPPINGS,
    max_smaps_bytes: int = _MAX_FORENSICS_BYTES,
) -> dict[str, Any]:
    """Process memory: smaps_rollup, status VmRSS/VmHWM, cgroup current/peak.

    All byte counters are normalized to MiB (2 decimals).  Fields that are
    unavailable on the platform are reported as ``None``.
    """
    out: dict[str, Any] = {
        "capture_wall_unix_ns": time.time_ns(),
        "rss_mib": None, "pss_mib": None, "anonymous_mib": None,
        "private_clean_mib": None, "private_dirty_mib": None,
        "shared_clean_mib": None, "shared_dirty_mib": None,
        "rss_file_mib": None, "uss_mib": None, "private_mib": None,
        "swap_mib": None,
        "status_vmrss_mib": None, "status_vmhwm_mib": None,
        "status_vmsize_mib": None, "status_vmdata_mib": None, "status_vmstk_mib": None,
        "cgroup_current_mib": None, "cgroup_peak_mib": None,
        "native_library_resident_bytes": None,
        "native_library_resident_status": "unavailable",
        "mapped_native_library_bytes": None,
        "cuda_runtime_host_mapped_bytes": None,
        "cuda_runtime_host_mapped_status": "unavailable",
        "file_backed_resident_bytes": None,
        "custom_node_resident_bytes": None,
        "custom_node_resident_status": "unavailable",
        "thread_stack_resident_bytes": None,
        "thread_stack_resident_status": "unavailable",
        "thread_stack_total_bytes": None,
        "uss_status": "unavailable",
        "rss_status": "unavailable",
        "pss_status": "unavailable",
        "anonymous_status": "unavailable",
        "shared_status": "unavailable",
        "private_clean_status": "unavailable",
        "private_dirty_status": "unavailable",
        "private_status": "unavailable",
        "file_backed_resident_status": "unavailable",
        # Per-field provenance is kept separately from the legacy status
        # labels.  This prevents a partial smaps attribution from looking like
        # a complete replacement of a status:RssFile/approximate fallback.
        "field_sources": {},
        "field_statuses": {},
        "smaps": {
            "available": False,
            "status": "disabled",
            "native_library_resident_status": "disabled",
            "cuda_runtime_host_mapped_status": "disabled",
            "file_backed_resident_status": "disabled",
            "custom_node_resident_status": "disabled",
            "thread_stack_resident_status": "disabled",
            "largest_mappings": [],
        },
        "source": "unavailable",
    }
    rollup_kb: dict[str, int] = {}
    raw = _proc_self_file("smaps_rollup")
    if raw:
        kb = _parse_kb_lines(raw)
        rollup_kb = kb
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
                    if _out_key in {"anonymous_mib", "private_clean_mib", "private_dirty_mib",
                                    "shared_clean_mib", "shared_dirty_mib"}:
                        status_name = {
                            "anonymous_mib": "anonymous_status",
                            "private_clean_mib": "private_clean_status",
                            "private_dirty_mib": "private_dirty_status",
                            "shared_clean_mib": "shared_status",
                            "shared_dirty_mib": "shared_status",
                        }[_out_key]
                        out[status_name] = "smaps_rollup"
            out["source"] = "smaps_rollup"
            out["rss_status"] = "smaps_rollup" if "rss" in kb else "unavailable"
            out["pss_status"] = "smaps_rollup" if "pss" in kb else "unavailable"
    # Source precedence for file-backed residency is explicit: complete smaps
    # wins, status:RssFile is the fallback, and the rss-anonymous approximation
    # is last.  A partial smaps sample remains visible in ``smaps`` but does
    # not replace a complete fallback.  Keep MiB and byte forms synchronized.
    _file_backed_source = "unavailable"
    status_kb: dict[str, int] = {}
    status_raw = _proc_self_file("status")
    if status_raw:
        status_kb = _parse_kb_lines(status_raw)
        for source_key, out_key in (
            ("vmrss", "status_vmrss_mib"), ("vmhwm", "status_vmhwm_mib"),
            ("vmsize", "status_vmsize_mib"), ("vmdata", "status_vmdata_mib"),
            ("vmstk", "status_vmstk_mib"),
        ):
            if source_key in status_kb:
                out[out_key] = round(status_kb[source_key] / 1024.0, 2)
        if "rssfile" in status_kb:
            out["rss_file_mib"] = round(status_kb["rssfile"] / 1024.0, 2)
            out["file_backed_resident_status"] = "status_rssfile"
            _file_backed_source = "status_rssfile"
        for source_key, out_key in (("rssanon", "anonymous_mib"),):
            if source_key in status_kb and out[out_key] is None:
                out[out_key] = round(status_kb[source_key] / 1024.0, 2)
        for line in status_raw.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            if key.strip() in ("VmRSS", "VmHWM"):
                # Parsed above; retain the historical fields and labels.
                pass
    private_clean = out.get("private_clean_mib")
    private_dirty = out.get("private_dirty_mib")
    if isinstance(private_clean, (int, float)) and isinstance(private_dirty, (int, float)):
        out["uss_mib"] = round(float(private_clean) + float(private_dirty), 2)
        out["private_mib"] = out["uss_mib"]
        out["uss_status"] = "approximate_private_clean_plus_dirty"
        out["private_status"] = out["uss_status"]
    if out.get("rss_file_mib") is None:
        rss = out.get("rss_mib")
        anonymous = out.get("anonymous_mib")
        if isinstance(rss, (int, float)) and isinstance(anonymous, (int, float)):
            out["rss_file_mib"] = round(max(0.0, float(rss) - float(anonymous)), 2)
            out["file_backed_resident_status"] = "approximate_rss_minus_anonymous"
            _file_backed_source = "approximate_rss_minus_anonymous"
    if include_smaps is None:
        include_smaps = runtime_memory_forensics_enabled()
    if include_smaps:
        try:
            full_smaps, _smaps_source_truncated = _proc_self_file_bounded(
                "smaps", max(4096, min(int(max_smaps_bytes), _MAX_FORENSICS_BYTES))
            )
            smaps = _parse_bounded_smaps(
                full_smaps,
                max_mappings=max(1, min(int(max_smaps_mappings), _MAX_FORENSICS_MAPPINGS)),
                max_bytes=max(4096, min(int(max_smaps_bytes), _MAX_FORENSICS_BYTES)),
                source_truncated=_smaps_source_truncated,
            )
            smaps["status"] = (
                "partial" if smaps.get("partial")
                else "captured" if smaps.get("available") else "unavailable"
            )
            out["smaps"] = smaps
            out["native_library_resident_bytes"] = smaps.get("native_library_resident_bytes")
            out["native_library_resident_status"] = smaps.get("native_library_resident_status", "unavailable")
            out["mapped_native_library_bytes"] = smaps.get("native_library_resident_bytes")
            out["cuda_runtime_host_mapped_bytes"] = smaps.get("cuda_runtime_host_mapped_bytes")
            out["cuda_runtime_host_mapped_status"] = smaps.get("cuda_runtime_host_mapped_status", "unavailable")
            if out.get("file_backed_resident_bytes") is None and (
                not smaps.get("partial") or out.get("rss_file_mib") is None
            ):
                out["file_backed_resident_bytes"] = smaps.get("file_backed_resident_bytes")
                out["file_backed_resident_status"] = smaps.get("file_backed_resident_status", "unavailable")
            out["custom_node_resident_bytes"] = smaps.get("custom_node_resident_bytes")
            out["custom_node_resident_status"] = smaps.get("custom_node_resident_status", "unavailable")
            out["thread_stack_resident_bytes"] = smaps.get("thread_stack_resident_bytes")
            out["thread_stack_resident_status"] = smaps.get("thread_stack_resident_status", "unavailable")
            out["thread_stack_total_bytes"] = smaps.get("thread_stack_resident_bytes")
            out["largest_bounded_smaps_mappings"] = smaps.get("largest_mappings", [])
            _smaps_file_backed = smaps.get("file_backed_resident_bytes")
            # A bounded partial read is not authoritative for the whole
            # address space.  Retain an already available status:RssFile or
            # rss-anonymous approximation; use the partial value only when no
            # fallback exists at all.
            if isinstance(_smaps_file_backed, int) and (
                not smaps.get("partial")
                or (
                    out.get("file_backed_resident_bytes") is None
                    and out.get("rss_file_mib") is None
                )
            ):
                out["file_backed_resident_bytes"] = _smaps_file_backed
                out["rss_file_mib"] = round(_smaps_file_backed / _MIB, 2)
                out["file_backed_resident_status"] = smaps.get(
                    "file_backed_resident_status", "unavailable"
                )
                _file_backed_source = "smaps"
        except Exception:  # noqa: BLE001
            out["smaps"] = {
                "available": False,
                "status": "unavailable",
                "largest_mappings": [],
                "native_library_resident_status": "unavailable",
                "cuda_runtime_host_mapped_status": "unavailable",
                "file_backed_resident_status": "unavailable",
                "custom_node_resident_status": "unavailable",
                "thread_stack_resident_status": "unavailable",
            }
            out.update({
                "native_library_resident_bytes": None,
                "native_library_resident_status": "unavailable",
                "mapped_native_library_bytes": None,
                "cuda_runtime_host_mapped_bytes": None,
                "cuda_runtime_host_mapped_status": "unavailable",
                "custom_node_resident_bytes": None,
                "custom_node_resident_status": "unavailable",
                "thread_stack_resident_bytes": None,
                "thread_stack_resident_status": "unavailable",
                "thread_stack_total_bytes": None,
                "largest_bounded_smaps_mappings": [],
            })
    else:
        out.update({
            "native_library_resident_bytes": None,
            "native_library_resident_status": "disabled",
            "mapped_native_library_bytes": None,
            "cuda_runtime_host_mapped_bytes": None,
            "cuda_runtime_host_mapped_status": "disabled",
            "custom_node_resident_bytes": None,
            "custom_node_resident_status": "disabled",
            "thread_stack_resident_bytes": None,
            "thread_stack_resident_status": "disabled",
            "thread_stack_total_bytes": None,
            "largest_bounded_smaps_mappings": [],
        })
    for mib_key in (
        "rss_mib", "pss_mib", "anonymous_mib", "private_clean_mib",
        "private_dirty_mib", "shared_clean_mib", "shared_dirty_mib",
        "rss_file_mib", "uss_mib", "private_mib",
    ):
        out[mib_key.replace("_mib", "_bytes")] = _mib_bytes(out.get(mib_key))
    for source_key, output_key in (
        ("rss", "rss_bytes"), ("pss", "pss_bytes"),
        ("anonymous", "anonymous_bytes"), ("private_clean", "private_clean_bytes"),
        ("private_dirty", "private_dirty_bytes"), ("shared_clean", "shared_clean_bytes"),
        ("shared_dirty", "shared_dirty_bytes"), ("swap", "swap_bytes"),
    ):
        if source_key in rollup_kb:
            out[output_key] = rollup_kb[source_key] * 1024
    if _file_backed_source == "smaps":
        # Preserve the exact smaps total; do not replace it with status:RssFile.
        out["rss_file_bytes"] = out.get("file_backed_resident_bytes")
    elif "rssfile" in status_kb:
        out["rss_file_bytes"] = status_kb["rssfile"] * 1024
        out["file_backed_resident_bytes"] = out["rss_file_bytes"]
        out["file_backed_resident_status"] = "status_rssfile"
    if "private_clean" in rollup_kb and "private_dirty" in rollup_kb:
        out["uss_bytes"] = (rollup_kb["private_clean"] + rollup_kb["private_dirty"]) * 1024
        out["private_bytes"] = out["uss_bytes"]
    if out.get("file_backed_resident_bytes") is None:
        out["file_backed_resident_bytes"] = _mib_bytes(out.get("rss_file_mib"))
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
    _field_pairs = {
        "rss_mib": ("rss_status", "smaps_rollup"),
        "pss_mib": ("pss_status", "smaps_rollup"),
        "anonymous_mib": ("anonymous_status", "smaps_rollup"),
        "private_clean_mib": ("private_clean_status", "smaps_rollup"),
        "private_dirty_mib": ("private_dirty_status", "smaps_rollup"),
        "shared_clean_mib": ("shared_status", "smaps_rollup"),
        "shared_dirty_mib": ("shared_status", "smaps_rollup"),
        "rss_file_mib": ("file_backed_resident_status", "unavailable"),
        "file_backed_resident_bytes": ("file_backed_resident_status", "unavailable"),
        "uss_mib": ("uss_status", "unavailable"),
        "private_mib": ("private_status", "unavailable"),
        "native_library_resident_bytes": ("native_library_resident_status", "unavailable"),
        "cuda_runtime_host_mapped_bytes": ("cuda_runtime_host_mapped_status", "unavailable"),
        "custom_node_resident_bytes": ("custom_node_resident_status", "unavailable"),
        "thread_stack_resident_bytes": ("thread_stack_resident_status", "unavailable"),
    }
    for field_name, (status_key, default_source) in _field_pairs.items():
        value = out.get(field_name)
        status = str(out.get(status_key) or "unavailable")
        if value is None:
            source = "unavailable"
        elif field_name in {"native_library_resident_bytes", "cuda_runtime_host_mapped_bytes",
                            "custom_node_resident_bytes", "thread_stack_resident_bytes"}:
            source = "smaps" if status in {"bounded_smaps", "partial"} else status
        elif field_name in {"rss_file_mib", "file_backed_resident_bytes"}:
            source = {
                "status_rssfile": "status_rssfile",
                "approximate_rss_minus_anonymous": "approximate_rss_minus_anonymous",
                "bounded_smaps": "smaps",
                "partial": "smaps_partial",
            }.get(status, default_source)
        else:
            source = default_source if status in {"smaps_rollup", "approximate_private_clean_plus_dirty"} else status
        out["field_sources"][field_name] = source
        out["field_statuses"][field_name] = status
        out[f"{field_name.removesuffix('_mib')}_source"] = source
    # Byte aliases are derived from the MiB values (or the exact rollup/status
    # byte counters), so publish the same provenance for both representations.
    for byte_name, mib_name in (
        ("rss_bytes", "rss_mib"), ("pss_bytes", "pss_mib"),
        ("anonymous_bytes", "anonymous_mib"),
        ("private_clean_bytes", "private_clean_mib"),
        ("private_dirty_bytes", "private_dirty_mib"),
        ("shared_clean_bytes", "shared_clean_mib"),
        ("shared_dirty_bytes", "shared_dirty_mib"),
        ("swap_bytes", "swap_mib"), ("rss_file_bytes", "rss_file_mib"),
        ("uss_bytes", "uss_mib"), ("private_bytes", "private_mib"),
    ):
        if byte_name in out:
            out["field_sources"][byte_name] = out["field_sources"].get(mib_name, "unavailable")
            out["field_statuses"][byte_name] = out["field_statuses"].get(mib_name, "unavailable")
            out[f"{byte_name.removesuffix('_bytes')}_source"] = out["field_sources"][byte_name]
    return _normalize_process_memory_schema(out)


def _empty_process_memory(*, status: str = "unavailable", error: str = "") -> dict[str, Any]:
    """Return the stable JSON-safe process probe schema on total failure."""
    result: dict[str, Any] = {
        "capture_wall_unix_ns": time.time_ns(),
        "rss_mib": None, "pss_mib": None, "anonymous_mib": None,
        "private_clean_mib": None, "private_dirty_mib": None,
        "shared_clean_mib": None, "shared_dirty_mib": None,
        "rss_file_mib": None, "uss_mib": None, "private_mib": None,
        "swap_mib": None,
        "status_vmrss_mib": None, "status_vmhwm_mib": None,
        "status_vmsize_mib": None, "status_vmdata_mib": None, "status_vmstk_mib": None,
        "cgroup_current_mib": None, "cgroup_peak_mib": None,
        "native_library_resident_bytes": None,
        "native_library_resident_status": status,
        "mapped_native_library_bytes": None,
        "cuda_runtime_host_mapped_bytes": None,
        "cuda_runtime_host_mapped_status": status,
        "file_backed_resident_bytes": None,
        "custom_node_resident_bytes": None,
        "custom_node_resident_status": status,
        "thread_stack_resident_bytes": None,
        "thread_stack_resident_status": status,
        "thread_stack_total_bytes": None,
        "uss_status": status, "rss_status": status, "pss_status": status,
        "anonymous_status": status, "shared_status": status,
        "private_clean_status": status, "private_dirty_status": status,
        "private_status": status, "file_backed_resident_status": status,
        "field_sources": {}, "field_statuses": {},
        "smaps": {
            "available": False, "partial": False, "status": status,
            "partial_reasons": [], "bytes_read": 0, "mapping_count": 0,
            "native_library_resident_bytes": None,
            "native_library_resident_status": status,
            "cuda_runtime_host_mapped_bytes": None,
            "cuda_runtime_host_mapped_status": status,
            "file_backed_resident_bytes": None,
            "file_backed_resident_status": status,
            "custom_node_resident_bytes": None,
            "custom_node_resident_status": status,
            "thread_stack_resident_bytes": None,
            "thread_stack_resident_status": status,
            "largest_mappings": [],
        },
        "source": "unavailable",
        "status": status,
    }
    if error:
        result["error"] = str(error)[:240]
    return _normalize_process_memory_schema(result, status=status)


_PROCESS_MEMORY_MIB_FIELDS: tuple[str, ...] = (
    "rss_mib", "pss_mib", "anonymous_mib", "private_clean_mib",
    "private_dirty_mib", "shared_clean_mib", "shared_dirty_mib",
    "swap_mib", "rss_file_mib", "uss_mib", "private_mib",
)
_PROCESS_MEMORY_BYTE_FIELDS: tuple[str, ...] = (
    "rss_bytes", "pss_bytes", "anonymous_bytes", "private_clean_bytes",
    "private_dirty_bytes", "shared_clean_bytes", "shared_dirty_bytes",
    "swap_bytes", "rss_file_bytes", "uss_bytes", "private_bytes",
)
_PROCESS_MEMORY_PROVENANCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("rss_mib", "rss_status", "rss_source"),
    ("pss_mib", "pss_status", "pss_source"),
    ("anonymous_mib", "anonymous_status", "anonymous_source"),
    ("private_clean_mib", "private_clean_status", "private_clean_source"),
    ("private_dirty_mib", "private_dirty_status", "private_dirty_source"),
    ("shared_clean_mib", "shared_status", "shared_clean_source"),
    ("shared_dirty_mib", "shared_status", "shared_dirty_source"),
    ("swap_mib", "swap_status", "swap_source"),
    ("rss_file_mib", "file_backed_resident_status", "rss_file_source"),
    ("uss_mib", "uss_status", "uss_source"),
    ("private_mib", "private_status", "private_source"),
    ("file_backed_resident_bytes", "file_backed_resident_status", "file_backed_resident_source"),
    ("native_library_resident_bytes", "native_library_resident_status", "native_library_resident_source"),
    ("mapped_native_library_bytes", "native_library_resident_status", "mapped_native_library_source"),
    ("cuda_runtime_host_mapped_bytes", "cuda_runtime_host_mapped_status", "cuda_runtime_host_mapped_source"),
    ("custom_node_resident_bytes", "custom_node_resident_status", "custom_node_resident_source"),
    ("thread_stack_resident_bytes", "thread_stack_resident_status", "thread_stack_resident_source"),
    ("thread_stack_total_bytes", "thread_stack_resident_status", "thread_stack_total_source"),
)


def _process_memory_status_source(status: str) -> str:
    """Map a field status to its truthful source label."""
    return {
        "smaps_rollup": "smaps_rollup",
        "status_rssfile": "status_rssfile",
        "approximate_rss_minus_anonymous": "approximate_rss_minus_anonymous",
        "approximate_private_clean_plus_dirty": "approximate_private_clean_plus_dirty",
        "bounded_smaps": "smaps",
        "partial": "smaps_partial",
    }.get(status, status if status not in {"disabled", "unavailable", "error"} else "unavailable")


_KNOWN_PROCESS_SOURCES = frozenset({
    "smaps_rollup", "status_rssfile", "approximate_rss_minus_anonymous",
    "approximate_private_clean_plus_dirty", "smaps", "smaps_partial",
})


def _normalize_process_memory_schema(
    value: Mapping[str, Any],
    *,
    status: str | None = None,
) -> dict[str, Any]:
    """Fill the process probe contract without changing observed values.

    The probe has several historical MiB fields and byte aliases.  Keeping
    their union in one normalizer makes successful, partial, unavailable, and
    exception results interchangeable for downstream JSON consumers while
    retaining the source/status reported by each measurement.
    """
    result = dict(value)
    result.setdefault("capture_wall_unix_ns", time.time_ns())
    result.setdefault("error", None)
    if status is None:
        existing = str(result.get("status", "") or "")
        if existing:
            status = existing
        elif isinstance(result.get("smaps"), Mapping) and result["smaps"].get("partial"):
            status = "partial"
        elif any(result.get(name) is not None for name in _PROCESS_MEMORY_MIB_FIELDS + _PROCESS_MEMORY_BYTE_FIELDS):
            status = "captured"
        else:
            status = "unavailable"
    result["status"] = str(status)

    for field_name in _PROCESS_MEMORY_MIB_FIELDS + _PROCESS_MEMORY_BYTE_FIELDS:
        result.setdefault(field_name, None)
    for field_name in (
        "status_vmrss_mib", "status_vmhwm_mib", "status_vmsize_mib",
        "status_vmdata_mib", "status_vmstk_mib", "cgroup_current_mib",
        "cgroup_peak_mib", "native_library_resident_bytes",
        "native_library_resident_status", "mapped_native_library_bytes",
        "cuda_runtime_host_mapped_bytes", "cuda_runtime_host_mapped_status",
        "file_backed_resident_bytes", "custom_node_resident_bytes",
        "custom_node_resident_status", "thread_stack_resident_bytes",
        "thread_stack_resident_status", "thread_stack_total_bytes",
        "uss_status", "rss_status", "pss_status", "anonymous_status",
        "shared_status", "private_clean_status", "private_dirty_status",
        "private_status", "file_backed_resident_status", "source",
    ):
        if field_name.endswith("_status"):
            result.setdefault(field_name, "unavailable")
        else:
            result.setdefault(field_name, None if field_name != "source" else "unavailable")
    for mib_name, byte_name in zip(_PROCESS_MEMORY_MIB_FIELDS, _PROCESS_MEMORY_BYTE_FIELDS):
        if result.get(byte_name) is None and isinstance(result.get(mib_name), (int, float)):
            result[byte_name] = _mib_bytes(result[mib_name])
        if result.get(mib_name) is None and isinstance(result.get(byte_name), int):
            result[mib_name] = round(result[byte_name] / _MIB, 2)

    result.setdefault("largest_bounded_smaps_mappings", [])
    raw_sources = result.get("field_sources")
    raw_statuses = result.get("field_statuses")
    sources = dict(raw_sources) if isinstance(raw_sources, Mapping) else {}
    statuses = dict(raw_statuses) if isinstance(raw_statuses, Mapping) else {}
    result["field_sources"] = sources
    result["field_statuses"] = statuses

    # Byte aliases carry the same provenance as their MiB counterpart.
    provenance = list(_PROCESS_MEMORY_PROVENANCE_FIELDS)
    source_hint = str(result.get("source", "") or "")
    for mib_name, byte_name in zip(_PROCESS_MEMORY_MIB_FIELDS, _PROCESS_MEMORY_BYTE_FIELDS):
        for field_name in (mib_name, byte_name):
            base, _ = field_name.rsplit("_", 1)
            if field_name == "rss_file_bytes":
                source_name, status_name = "rss_file_source", "file_backed_resident_status"
            else:
                source_name = f"{base}_source"
                status_name = f"{base}_status"
            existing_status = str(result.get(status_name, "") or "")
            if not existing_status:
                existing_status = statuses.get(field_name) or statuses.get(mib_name) or (
                    source_hint if source_hint in _KNOWN_PROCESS_SOURCES
                    else str(status) if result.get(field_name) is not None else "unavailable"
                )
            result[status_name] = existing_status
            current_source = result.get(source_name) or sources.get(field_name) or sources.get(mib_name)
            if current_source == "unavailable" and source_hint in _KNOWN_PROCESS_SOURCES:
                current_source = source_hint
            if not current_source:
                current_source = (
                    _process_memory_status_source(existing_status)
                    if result.get(field_name) is not None else "unavailable"
                )
            result[source_name] = str(current_source)
            sources[field_name] = str(current_source)
            statuses[field_name] = existing_status

    for field_name, status_name, source_name in provenance:
        result.setdefault(field_name, None)
        existing_status = str(result.get(status_name, "") or "")
        if not existing_status:
            existing_status = statuses.get(field_name) or (
                str(status) if result.get(field_name) is not None else "unavailable"
            )
        result[status_name] = existing_status
        current_source = result.get(source_name) or sources.get(field_name)
        if not current_source:
            current_source = (
                _process_memory_status_source(existing_status)
                if result.get(field_name) is not None else "unavailable"
            )
        result[source_name] = str(current_source)
        sources[field_name] = str(current_source)
        statuses[field_name] = existing_status
        if field_name.endswith("_bytes"):
            result.setdefault(f"{field_name}_source", str(current_source))

    smaps_defaults: dict[str, Any] = {
        "available": False, "partial": False, "status": "disabled",
        "partial_reasons": [], "bytes_read": 0, "mapping_count": 0,
        "native_library_resident_bytes": None,
        "native_library_resident_status": "disabled",
        "cuda_runtime_host_mapped_bytes": None,
        "cuda_runtime_host_mapped_status": "disabled",
        "file_backed_resident_bytes": None,
        "file_backed_resident_status": "disabled",
        "custom_node_resident_bytes": None,
        "custom_node_resident_status": "disabled",
        "thread_stack_resident_bytes": None,
        "thread_stack_resident_status": "disabled",
        "largest_mappings": [],
    }
    raw_smaps = result.get("smaps")
    if isinstance(raw_smaps, Mapping):
        smaps_defaults.update(dict(raw_smaps))
    elif result["status"] not in {"captured", "partial"}:
        smaps_defaults["status"] = result["status"]
    result["smaps"] = smaps_defaults
    return result


def probe_process_memory(
    *,
    include_smaps: bool | None = None,
    max_smaps_mappings: int = _MAX_FORENSICS_MAPPINGS,
    max_smaps_bytes: int = _MAX_FORENSICS_BYTES,
) -> dict[str, Any]:
    """Probe process memory and always return the stable failure schema."""
    try:
        return _probe_process_memory_impl(
            include_smaps=include_smaps,
            max_smaps_mappings=max_smaps_mappings,
            max_smaps_bytes=max_smaps_bytes,
        )
    except Exception as exc:  # noqa: BLE001
        return _empty_process_memory(
            status="error",
            error=f"{type(exc).__name__}: {exc}",
        )


def _empty_runtime_memory_capture(
    stage: str,
    *,
    status: str = "measurement_error",
    error: str = "",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete capture schema when any probe fails."""
    result: dict[str, Any] = {
        "schema": "golden_runtime_memory_v1",
        "stage": str(stage),
        "capture_wall_unix_ns": time.time_ns(),
        "status": status,
        "process": _empty_process_memory(status="error" if error else "unavailable", error=error),
        "python_heap": {
            "available": False, "allocated_blocks": None, "gc_counts": [],
            "tracemalloc_tracing": False, "tracemalloc_current_bytes": None,
            "tracemalloc_peak_bytes": None, "tracemalloc_status": "unavailable",
        },
        "allocator": {
            "implementation": "", "pymalloc_enabled": None,
            "pythonmalloc_env": "", "arena_count": None, "arena_bytes": None,
            "arena_status": "unavailable",
        },
        "resource": {"available": False, "max_rss_bytes": None, "status": "unavailable"},
        "cuda": {
            "torch_loaded": False, "cuda_module_loaded": False,
            "cuda_context_initialized": None, "cuda_runtime_host_mapped_bytes": None,
            "cuda_host_allocated_bytes": None,
            "cuda_host_allocation_status": "unavailable",
        },
        "threads": {
            "python_count": None, "native_count": None,
            "thread_pool_executors": 0, "process_pool_executors": 0,
        },
        "modules": {
            "available": False, "count": None, "custom_node_count": None,
            "custom_node_names": [],
        },
        "serialized_snapshot_size_bytes": None,
        "serialized_snapshot_size_status": "unavailable",
        "serialized_snapshot_size_note": "RSS/resident memory is not serialized Modal snapshot size.",
        "error": None,
        "extra": _json_safe(dict(extra)) if extra else None,
    }
    if error:
        result["error"] = str(error)[:240]
    safe = _json_safe(result)
    return safe if isinstance(safe, dict) else result


def _runtime_memory_capture_status(process: Mapping[str, Any]) -> str:
    """Classify a completed process probe without hiding partial data."""
    process_status = str(process.get("status", "") or "")
    if process_status == "partial":
        return "partial"
    if process_status in {"unavailable", "disabled"}:
        return "unavailable"
    smaps = process.get("smaps")
    if isinstance(smaps, Mapping) and smaps.get("partial"):
        return "partial"
    return "captured"


def capture_runtime_memory(
    stage: str,
    *,
    include_smaps: bool | None = None,
    max_smaps_mappings: int = _MAX_FORENSICS_MAPPINGS,
    max_smaps_bytes: int = _MAX_FORENSICS_BYTES,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture low-perturbation Golden runtime composition telemetry.

    The normal path reads one ``smaps_rollup`` plus lightweight interpreter and
    thread state.  Full ``smaps`` mapping attribution is opt-in and bounded.
    No CUDA API is used to discover availability, and tracemalloc is never
    started by measurement.  Modal's serialized snapshot byte count remains
    explicitly unavailable; resident RSS is not that byte count.
    """
    try:
        process = probe_process_memory(
            include_smaps=include_smaps,
            max_smaps_mappings=max_smaps_mappings,
            max_smaps_bytes=max_smaps_bytes,
        )
        if not isinstance(process, dict):
            raise TypeError("process_memory_probe_must_return_mapping")
        process = _normalize_process_memory_schema(process)
        if isinstance(process, dict) and process.get("status") == "error":
            return _empty_runtime_memory_capture(
                stage,
                status="measurement_error",
                error=str(process.get("error", "process_memory_probe_failed")),
                extra=extra,
            )
        modules = _module_indicators()
        smaps = process.get("smaps", {}) if isinstance(process, dict) else {}
        if isinstance(smaps, dict) and smaps.get("custom_node_resident_bytes") is not None:
            modules["custom_node_resident_bytes"] = smaps.get("custom_node_resident_bytes")
            modules["custom_node_resident_status"] = (
                "partial" if smaps.get("partial") else "bounded_smaps"
            )
        thread_count: int | None = None
        try:
            thread_count = len(threading.enumerate())
        except Exception:  # noqa: BLE001
            pass
        out: dict[str, Any] = {
            "schema": "golden_runtime_memory_v1",
            "stage": str(stage),
            "capture_wall_unix_ns": time.time_ns(),
            "status": _runtime_memory_capture_status(process),
            "error": None,
            "process": process,
            "python_heap": _python_heap_indicators(),
            "allocator": _allocator_indicators(),
            "resource": _resource_indicators(),
            "cuda": _cuda_host_indicators(),
            "threads": {
                "python_count": thread_count,
                "native_count": _parse_kb_lines(_proc_self_file("status")).get("threads"),
                **_thread_pool_counts(),
            },
            "modules": modules,
            "serialized_snapshot_size_bytes": None,
            "serialized_snapshot_size_status": "unavailable",
            "serialized_snapshot_size_note": "RSS/resident memory is not serialized Modal snapshot size.",
            "extra": _json_safe(dict(extra)) if extra else None,
        }
        cuda_native_bytes = (
            process.get("cuda_runtime_host_mapped_bytes")
            if isinstance(process, dict) else None
        )
        out["cuda"]["cuda_runtime_host_mapped_bytes"] = cuda_native_bytes
        safe = _json_safe(out)
        return safe if isinstance(safe, dict) else _empty_runtime_memory_capture(
            stage,
            status="measurement_error",
            error="json_safe_capture_failed",
            extra=extra,
        )
    except Exception as exc:  # noqa: BLE001
        return _empty_runtime_memory_capture(
            stage,
            status="measurement_error",
            error=f"{type(exc).__name__}: {exc}",
            extra=extra,
        )


# Clear names for callers that treat this as a probe rather than an emitter.
probe_runtime_memory = capture_runtime_memory
probe_memory_composition = capture_runtime_memory


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
