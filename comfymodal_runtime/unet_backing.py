"""UNET snapshot-backing diagnostics (default off).

Question being answered: do slow 12.31 GB CPU->GPU UNET transfers come from
safetensors/Volume-backed (mmap) pages or from the general Modal host
memory/PCIe path?

Three diagnostic capabilities, every one default-OFF:

- ``COMFYMODAL_V2_UNET_BACKING_VERIFY=1`` — read-only: classify every UNET
  parameter/buffer storage address against ``/proc/self/maps`` into
  volume-file backed / anonymous / unknown.  Run immediately before snapshot
  capture (proves what the snapshot pages are backed by) and at transfer time
  (proves what the real transfer reads from).
- ``COMFYMODAL_V2_ANON_UNET_SNAPSHOT=1`` — Arm B: clone every UNET parameter
  and buffer into freshly allocated anonymous CPU memory (preserving dtype,
  shape, strides/layout and parameter objects), release the old storages and
  run GC immediately before snapshot capture, then re-verify the backing.
- ``COMFYMODAL_V2_SYNTH_H2D_PROBE=1`` — per-run: immediately before the real
  UNET transfer, synchronously copy a touched 2 GB anonymous contiguous CPU
  tensor to the GPU, measure duration + GB/s, then free the GPU tensor before
  the UNET loads.  Also records the per-run UNET backing classification.

Nothing here ever raises; every helper is best-effort and try/except-wrapped.
"""
from __future__ import annotations

import gc
import os
from pathlib import Path
from typing import Any

_SYNTH_H2D_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def backing_verify_enabled() -> bool:
    return _flag("COMFYMODAL_V2_UNET_BACKING_VERIFY")


def anon_snapshot_enabled() -> bool:
    return _flag("COMFYMODAL_V2_ANON_UNET_SNAPSHOT")


def synth_h2d_probe_enabled() -> bool:
    return _flag("COMFYMODAL_V2_SYNTH_H2D_PROBE")


def page_path_probe_enabled() -> bool:
    return _flag("COMFYMODAL_V2_PAGE_PATH_PROBE")


def backing_diag_any_enabled() -> bool:
    return (
        backing_verify_enabled()
        or anon_snapshot_enabled()
        or synth_h2d_probe_enabled()
        or page_path_probe_enabled()
    )


def _read_proc_maps() -> list[str]:
    try:
        return Path("/proc/self/maps").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except Exception:
        return []


def _maps_backing(addr: int, maps_lines: list[str]) -> str:
    """Classify one address against cached ``/proc/self/maps`` lines.

    The map line format is fixed-width: ``start-end perms offset dev inode
    [pathname]``.  A missing pathname (or ``[anon]``-style token) is an
    anonymous mapping; an inode number in the 5th column is NOT a pathname,
    so lines without a pathname must never be classified as file-backed.
    Returns ``anonymous``, ``file:<pathname>`` or ``unknown``.
    """
    for _line in maps_lines:
        _toks = _line.split()
        if len(_toks) < 5:
            continue
        _start_s, _, _end_s = _toks[0].partition("-")
        try:
            _start = int(_start_s, 16)
            _end = int(_end_s, 16)
        except ValueError:
            continue
        if _start <= addr < _end:
            _path = " ".join(_toks[5:]) if len(_toks) > 5 else ""
            if not _path or _path.startswith("["):
                return "anonymous"
            return f"file:{_path}"
    return "unknown"


def _maps_line_for(addr: int, maps_lines: list[str]) -> str:
    """Return the raw maps line covering *addr* (or empty)."""
    for _line in maps_lines:
        _toks = _line.split()
        if len(_toks) < 5:
            continue
        try:
            _start = int(_toks[0].split("-")[0], 16)
            _end = int(_toks[0].split("-")[1], 16)
        except (ValueError, IndexError):
            continue
        if _start <= addr < _end:
            return _line
    return ""


def _clamp_range_to_mapping(addr: int, nbytes: int, maps_lines: list[str]) -> tuple[int, int] | None:
    """Clamp [addr, addr+nbytes) to the covering /proc/self/maps mapping.

    Returns ``(start, end)`` page-rounded INSIDE the covering mapping, or
    ``None`` when no mapping covers *addr* (never traverse unmapped memory —
    an overrun would segfault the container).  Reads are restricted to the
    mapping so the probe can never touch pages outside the storage's own
    mapping.
    """
    _page = _page_size()
    for _line in maps_lines:
        _toks = _line.split()
        if len(_toks) < 5:
            continue
        try:
            _m_start = int(_toks[0].split("-")[0], 16)
            _m_end = int(_toks[0].split("-")[1], 16)
        except (ValueError, IndexError):
            continue
        if _m_start <= addr < _m_end:
            _start = max((addr // _page) * _page, _m_start)
            _end = min(((addr + nbytes + _page - 1) // _page) * _page, _m_end)
            if _end > _start:
                return (_start, _end)
            return None
    return None


def _resolve_unet_module(unet: Any) -> Any:
    """Return the ``torch.nn.Module`` owning the UNET parameters.

    The CPU-snapshot UNET may be a plain module or wrapped (ComfyUI
    ModelPatcher exposes the underlying model via ``.model``).
    """
    import torch
    if isinstance(unet, torch.nn.Module):
        return unet
    _model = getattr(unet, "model", None)
    if isinstance(_model, torch.nn.Module):
        return _model
    return unet


def capture_unet_backing_evidence(unet: Any, *, label: str = "") -> dict[str, Any]:
    """Classify every UNET parameter/buffer storage address against maps.

    Read-only.  Returns counts per backing class, total bytes, tensor count
    and up to 12 sample entries (name, address, bytes, backing).  Never
    raises.
    """
    evidence: dict[str, Any] = {"label": label, "counts": {}, "tensors": 0, "bytes": 0}
    _maps = _read_proc_maps()
    if not _maps:
        evidence["error"] = "proc_maps_unreadable"
        return evidence
    try:
        _module = _resolve_unet_module(unet)
        _items: list[tuple[str, Any]] = []
        try:
            _items += [(n, t) for n, t in _module.named_parameters(
                recurse=True, remove_duplicate=False)]
        except Exception:
            pass
        try:
            _items += [(n, t) for n, t in _module.named_buffers(
                recurse=True, remove_duplicate=False)]
        except Exception:
            pass
        _seen_ids: set[int] = set()
        _counts: dict[str, int] = {"anonymous": 0, "volume": 0, "unknown": 0}
        _samples: list[dict[str, Any]] = []
        _bytes = 0
        _tensors = 0
        for _name, _tensor in _items:
            try:
                if hasattr(_tensor, "untyped_storage"):
                    _st = _tensor.untyped_storage()
                else:
                    _st = _tensor.storage()
                _addr = int(_st.data_ptr())
                _nbytes = int(_st.nbytes())
            except Exception:
                continue
            if not _addr or id(_st) in _seen_ids:
                continue
            _seen_ids.add(id(_st))
            _tensors += 1
            _bytes += _nbytes
            _backing = _maps_backing(_addr, _maps)
            if _backing == "anonymous":
                _counts["anonymous"] += 1
            elif _backing.startswith("file:"):
                _counts["volume"] += 1
            else:
                _counts["unknown"] += 1
            if len(_samples) < 12:
                _samples.append({
                    "name": _name, "addr": hex(_addr),
                    "bytes": _nbytes, "backing": _backing,
                    "maps_line": _maps_line_for(_addr, _maps),
                })
        evidence["counts"] = _counts
        evidence["tensors"] = _tensors
        evidence["bytes"] = _bytes
        evidence["samples"] = _samples
        if _counts["volume"] and not _counts["anonymous"]:
            evidence["predominant"] = "volume"
        elif _counts["anonymous"] and not _counts["volume"]:
            evidence["predominant"] = "anonymous"
        else:
            evidence["predominant"] = "mixed"
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = str(exc)[:200]
    return evidence


def clone_unet_to_anonymous_ram(unet: Any) -> dict[str, Any]:
    """Clone every UNET parameter/buffer into fresh anonymous CPU memory.

    Preserves dtype, shape, strides/layout (``torch.preserve_format``),
    parameter objects (``.data`` replaced in place) and model identity.
    Old storages are released and GC runs before returning.  Returns a
    verification summary (cloned count, bytes, post-clone backing counts).
    Never raises.
    """
    import torch
    result: dict[str, Any] = {"cloned": 0, "bytes": 0, "error": ""}
    try:
        _module = _resolve_unet_module(unet)
        _done_ids: set[int] = set()
        for _mod in _module.modules():
            for _key, _param in list(getattr(_mod, "_parameters", {}).items()):
                if _param is None or id(_param) in _done_ids:
                    continue
                _done_ids.add(id(_param))
                try:
                    _new = torch.empty_like(_param, memory_format=torch.preserve_format)
                    _new.copy_(_param)
                    _param.data = _new
                    result["cloned"] += 1
                    result["bytes"] += int(_new.numel()) * int(_new.element_size())
                except Exception:
                    pass
            for _key, _buf in list(getattr(_mod, "_buffers", {}).items()):
                if _buf is None or id(_buf) in _done_ids:
                    continue
                _done_ids.add(id(_buf))
                try:
                    _new = torch.empty_like(_buf, memory_format=torch.preserve_format)
                    _new.copy_(_buf)
                    _mod._buffers[_key] = _new
                    result["cloned"] += 1
                    result["bytes"] += int(_new.numel()) * int(_new.element_size())
                except Exception:
                    pass
        gc.collect()
        _post = capture_unet_backing_evidence(unet, label="after_clone")
        result["post_clone"] = _post
        result["counts"] = _post.get("counts", {})
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:200]
    return result


def run_synth_h2d_probe(
    *, bytes_: int = _SYNTH_H2D_BYTES, sample_count: int | None = None,
) -> dict[str, Any] | None:
    """Diagnostic-only synchronized H2D copy of a touched anonymous tensor.

    Allocates ``bytes_`` (2 GiB default) of fresh anonymous contiguous CPU
    memory, touches every page, then synchronously copies to the GPU,
    measuring wall duration and effective GB/s.  Frees the GPU tensor before
    returning.  Returns ``None`` when disabled; never raises.
    """
    if not synth_h2d_probe_enabled():
        return None
    return run_contiguous_h2d_probe(bytes_=bytes_, sample_count=sample_count)


def run_contiguous_h2d_probe(
    *, bytes_: int, sample_count: int | None = None,
) -> dict[str, Any]:
    """Ungated synchronized H2D copy of a touched anonymous contiguous tensor.

    Same mechanics as ``run_synth_h2d_probe`` but without the gate check, so
    page-path diagnostics can size it exactly (e.g. 12.31 GB) regardless of
    the legacy 2 GiB gate.  Allocates, measures and frees its GPU tensor
    independently; never raises.
    """
    import time
    import torch
    record: dict[str, Any] = {
        "enabled": True,
        "bytes": int(bytes_),
        "dtype": "float32",
        "contiguous": True,
        "touched": True,
    }
    _cpu_tensor = None
    _gpu_tensor = None
    try:
        _n = max(1, int(bytes_) // 4)
        if sample_count is not None and sample_count > 0:
            _n = min(_n, sample_count)
        _cpu_tensor = torch.empty(_n, dtype=torch.float32, device="cpu")
        _cpu_tensor.fill_(1.0)  # touch every page so the copy measures DMA path
        torch.cuda.synchronize()
        _start = time.perf_counter()
        _gpu_tensor = _cpu_tensor.to(device="cuda", non_blocking=False)
        torch.cuda.synchronize()
        _dur_s = max(time.perf_counter() - _start, 1e-9)
        _copied = int(_cpu_tensor.numel()) * 4
        record["wall_ms"] = round(_dur_s * 1000.0, 3)
        record["gb_per_s"] = round((_copied / 1_000_000_000.0) / _dur_s, 3)
        record["copied_bytes"] = _copied
        record["process_cpu_ms"] = _proc_self_stat_cpu_ms()
        record["rss_mib"] = _proc_self_rss_mib()
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
    finally:
        # ALWAYS release the CPU and GPU tensors (even on error) so a failed
        # probe cannot leak 12.31 GB of CPU memory and OOM the container.
        try:
            del _gpu_tensor
            torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            del _cpu_tensor
        except Exception:
            pass
        _malloc_trim()
    return record


def _proc_self_rss_mib() -> float | None:
    try:
        for _line in Path("/proc/self/status").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if _line.startswith("VmRSS:"):
                return round(float(_line.split()[1]) / 1024.0, 1)
    except Exception:
        pass
    return None


def _malloc_trim() -> None:
    """glibc malloc_trim(0): return freed large blocks to the OS."""
    try:
        import ctypes
        _libc = ctypes.CDLL(None, use_errno=True)
        _libc.malloc_trim(0)
    except Exception:
        pass


def _proc_self_stat_cpu_ms() -> float | None:
    """Process CPU (utime+stime) from /proc/self/stat, in ms.  None on failure."""
    try:
        _raw = Path("/proc/self/stat").read_text(
            encoding="utf-8", errors="replace"
        )
        _rest = _raw[_raw.rfind(")") + 1:].split()
        # After the comm field: state(0) ppid(1) ... utime(11) stime(12) in
        # the post-")" numbering (fields 14/15 of the full stat).
        _utime = float(_rest[11])
        _stime = float(_rest[12])
        _hz = 100.0
        return round((_utime + _stime) / _hz * 1000.0, 3)
    except Exception:
        return None


def unet_storage_sizes(unet: Any) -> list[int]:
    """Byte sizes of every unique UNET parameter/buffer storage (dedup by id)."""
    sizes: list[int] = []
    try:
        _module = _resolve_unet_module(unet)
        _seen: set[int] = set()
        for _name, _tensor in list(_module.named_parameters(recurse=True, remove_duplicate=False)) + list(
            _module.named_buffers(recurse=True, remove_duplicate=False)
        ):
            try:
                if hasattr(_tensor, "untyped_storage"):
                    _st = _tensor.untyped_storage()
                else:
                    _st = _tensor.storage()
                _addr = int(_st.data_ptr())
                _nbytes = int(_st.nbytes())
            except Exception:
                continue
            if not _addr or id(_st) in _seen:
                continue
            _seen.add(id(_st))
            if _nbytes > 0:
                sizes.append(_nbytes)
    except Exception:
        pass
    return sizes


def mincore_unet_residency(unet: Any) -> dict[str, Any]:
    """mincore page residency of every UNET storage (before touching).

    Per-storage page-aligned range, aggregated resident/total pages and
    bytes.  Uses the libc ``mincore`` syscall via ctypes.  Never raises.
    """
    record: dict[str, Any] = {
        "method": "mincore",
        "storages": 0,
        "total_pages": 0,
        "resident_pages": 0,
        "total_bytes": 0,
        "resident_bytes": 0,
    }
    try:
        import ctypes
        _page = _page_size()
        _libc = ctypes.CDLL(None, use_errno=True)
        _mincore = _libc.mincore
        _maps = _read_proc_maps()
        _module = _resolve_unet_module(unet)
        _seen: set[int] = set()
        _storages = 0
        _total = 0
        _resident = 0
        _total_bytes = 0
        _resident_bytes = 0
        for _name, _tensor in list(_module.named_parameters(recurse=True, remove_duplicate=False)) + list(
            _module.named_buffers(recurse=True, remove_duplicate=False)
        ):
            try:
                if hasattr(_tensor, "untyped_storage"):
                    _st = _tensor.untyped_storage()
                else:
                    _st = _tensor.storage()
                _addr = int(_st.data_ptr())
                _nbytes = int(_st.nbytes())
            except Exception:
                continue
            if not _addr or id(_st) in _seen:
                continue
            _seen.add(id(_st))
            _rng = _clamp_range_to_mapping(_addr, _nbytes, _maps)
            if _rng is None:
                continue
            _start, _end = _rng
            _npages = (_end - _start) // _page
            if _npages <= 0:
                continue
            _vec = (ctypes.c_ubyte * _npages)()
            if _mincore(ctypes.c_void_p(_start), ctypes.c_size_t(_npages * _page), _vec) != 0:
                continue
            _resident += sum(1 for _b in _vec if _b & 0x1)
            _total += _npages
            _total_bytes += _nbytes
            _storages += 1
        record["storages"] = _storages
        record["total_pages"] = _total
        record["resident_pages"] = _resident
        record["total_bytes"] = _total_bytes
        record["resident_bytes"] = int(_resident * _page)
        if _total:
            record["resident_fraction"] = round(_resident / _total, 4)
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
    return record


def traverse_unet_pages(unet: Any) -> dict[str, Any]:
    """Native one-byte-per-page traversal of every UNET storage.

    Reads exactly one byte from every OS page of every storage using a
    vectorized NumPy strided view over the raw storage bytes (no Python
    per-page loop).  Records wall/process CPU, covered pages/bytes and
    effective traversal bandwidth.  Never raises.
    """
    record: dict[str, Any] = {
        "method": "numpy_strided_read_1B_per_page",
    }
    try:
        import ctypes
        import time
        import numpy as np
        _page = _page_size()
        _maps = _read_proc_maps()
        _module = _resolve_unet_module(unet)
        _seen: set[int] = set()
        _start_wall = time.perf_counter()
        _start_cpu = _proc_self_stat_cpu_ms()
        _covered_bytes = 0
        _covered_pages = 0
        _read_sum = 0
        for _name, _tensor in list(_module.named_parameters(recurse=True, remove_duplicate=False)) + list(
            _module.named_buffers(recurse=True, remove_duplicate=False)
        ):
            try:
                if hasattr(_tensor, "untyped_storage"):
                    _st = _tensor.untyped_storage()
                else:
                    _st = _tensor.storage()
                _addr = int(_st.data_ptr())
                _nbytes = int(_st.nbytes())
            except Exception:
                continue
            if not _addr or id(_st) in _seen:
                continue
            _seen.add(id(_st))
            _start = (_addr // _page) * _page
            _end = ((_addr + _nbytes + _page - 1) // _page) * _page
            _len = _end - _start
            if _len <= 0:
                continue
            _buf = (ctypes.c_char * _len).from_address(_start)
            _arr = np.frombuffer(memoryview(_buf), dtype=np.uint8)
            _sel = _arr[::_page]
            _read_sum += int(_sel.sum(dtype=np.uint64))
            _covered_pages += _sel.size
            _covered_bytes += _len
        _wall_s = max(time.perf_counter() - _start_wall, 1e-9)
        _cpu_ms = _proc_self_stat_cpu_ms()
        record["wall_ms"] = round(_wall_s * 1000.0, 3)
        record["process_cpu_ms"] = (
            round(_cpu_ms - _start_cpu, 3)
            if _cpu_ms is not None and _start_cpu is not None else None
        )
        record["covered_pages"] = _covered_pages
        record["covered_bytes"] = _covered_bytes
        record["page_size"] = _page
        record["read_sum"] = int(_read_sum)
        record["effective_gb_per_s"] = round(
            (_covered_bytes / 1_000_000_000.0) / _wall_s, 3
        )
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
    return record


def run_multi_storage_h2d_probe(storage_sizes: list[int]) -> dict[str, Any]:
    """Synchronized H2D of fresh anonymous storages matching the UNET sizes.

    Allocates one fresh anonymous CPU tensor per size, touches every page,
    then copies each to the GPU with the same per-storage loop shape as the
    real UNET load (per-tensor ``.to(cuda, non_blocking=True)`` + final
    sync), measuring wall/process CPU and effective GB/s.  The per-storage
    loop is preserved, but tensors are processed in bounded waves (64 per
    wave) so the CPU memory footprint of the probe never exceeds one wave
    (~1.8 GB) on top of the restored UNET — a single-pass 454-tensor
    allocation could push the container over its memory cap and get OOM-
    killed.  GPU tensors are kept until the final sync (per-storage copies
    stay in flight), then everything is freed.  Never raises.
    """
    import time
    import torch
    record: dict[str, Any] = {
        "enabled": True,
        "storages": 0,
        "bytes": 0,
        "dtype": "float32",
        "touched": True,
        "copy_style": "per_storage_non_blocking_final_sync",
        "wave_size": 32,
    }
    _gpu_tensors: list[Any] = []
    _wave: list[Any] = []
    _total_bytes = 0
    _storage_count = 0
    try:
        torch.cuda.synchronize()
        _start = time.perf_counter()
        _start_cpu = _proc_self_stat_cpu_ms()
        for _size in storage_sizes:
            if _size <= 0:
                continue
            _n = max(1, int(_size) // 4)
            _t = torch.empty(_n, dtype=torch.float32, device="cpu")
            _t.fill_(1.0)  # touch every page
            _wave.append(_t)
            _total_bytes += int(_t.numel()) * 4
            _storage_count += 1
            if len(_wave) >= 32:
                for _wt in _wave:
                    _gpu_tensors.append(_wt.to(device="cuda", non_blocking=True))
                del _wave
                _wave = []
        for _wt in _wave:
            _gpu_tensors.append(_wt.to(device="cuda", non_blocking=True))
        del _wave
        _wave = []
        torch.cuda.synchronize()
        _wall_s = max(time.perf_counter() - _start, 1e-9)
        _cpu_ms = _proc_self_stat_cpu_ms()
        record["storages"] = _storage_count
        record["bytes"] = _total_bytes
        record["wall_ms"] = round(_wall_s * 1000.0, 3)
        record["gb_per_s"] = round(
            (_total_bytes / 1_000_000_000.0) / _wall_s, 3
        )
        record["process_cpu_ms"] = (
            round(_cpu_ms - _start_cpu, 3)
            if _cpu_ms is not None and _start_cpu is not None else None
        )
        record["rss_mib"] = _proc_self_rss_mib()
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
    finally:
        try:
            del _gpu_tensors
            torch.cuda.empty_cache()
        except Exception:
            pass
        del _wave
        _malloc_trim()
    return record


def _page_size() -> int:
    try:
        import ctypes
        return int(ctypes.CDLL(None, use_errno=True).getpagesize())
    except Exception:
        return 4096
