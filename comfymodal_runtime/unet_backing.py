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


def rehome_after_restore_enabled() -> bool:
    """True when ``COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE`` is on.

    Post-restore rehoming: after the Modal snapshot restore, clone every
    UNET parameter/buffer storage into fresh anonymous CPU RAM immediately
    before the request-scoped GPU activation so the H2D transfer reads
    ordinary anonymous pages instead of the Modal-restored pages (which
    DMA at ~2 GB/s vs ~9-27 GB/s for fresh memory).  Default off.
    """
    return _flag("COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE")


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
    bytes.  Uses the libc ``mincore`` syscall via ctypes.  Holds strong
    storage references for the whole scan so a concurrent ``.data``
    replacement can never free a storage while its address range is being
    classified.  Never raises.
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
        _held: list[Any] = [unet, _module]
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
            _held.append(_st)
            _held.append(_tensor)
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

    **Strong storage references:** every storage object backing the raw
    pointer reads is held alive in ``_held`` for the whole traversal.  A
    concurrent mutation that replaces ``.data`` (e.g. a GPU move) can only
    free the OLD storage when no strong reference remains; holding the
    storage objects prevents the freed-memory read (use-after-free) that
    would otherwise segfault the container mid-traversal.
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
        _held: list[Any] = [unet, _module]  # strong refs for the whole walk
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
            _held.append(_st)
            _held.append(_tensor)
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


# ── Post-restore rehoming (Experiment 2/3) ───────────────────────────────
# The retained UNET after a Modal memory-snapshot restore lives on the
# restored heap pages, which DMA at ~2 GB/s while freshly allocated
# anonymous pages in the same container reach 9-27 GB/s.  Rehoming clones
# every parameter/buffer storage into fresh anonymous CPU RAM immediately
# before the GPU activation so the real H2D reads ordinary pages.

_PAGE_SIZE_CACHE: int = 0


def _page_size_cached() -> int:
    global _PAGE_SIZE_CACHE
    if not _PAGE_SIZE_CACHE:
        _PAGE_SIZE_CACHE = _page_size()
    return _PAGE_SIZE_CACHE


def _iter_unet_tensors(unet: Any):
    """Yield ``(name, tensor, storage, addr, nbytes)`` for every UNET
    parameter/buffer storage (dedup by storage identity).  Never raises."""
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
        if not _addr or _nbytes <= 0 or id(_st) in _seen:
            continue
        _seen.add(id(_st))
        yield _name, _tensor, _st, _addr, _nbytes


def measure_model_synced_h2d(
    unet: Any, *, label: str = "", keep_gpu: bool = False,
) -> tuple[dict[str, Any], tuple[list[Any], list[str]] | None]:
    """Synchronized H2D of the model's ACTUAL CPU storages (read-only).

    Copies every storage to the GPU with the same per-storage
    ``to(cuda, non_blocking=True)`` + final-sync loop shape as the real
    ComfyUI UNET load, keeping the GPU tensors until the sync, then frees
    them.  The CPU model is NEVER mutated (no ``.data`` replacement), so
    the measurement can run before and/or after a rehome clone without
    altering the model.  Records wall/process CPU, bytes, GB/s, faults.
    With *keep_gpu* True the GPU tensors are NOT freed and are returned as
    the second element (the caller owns the reference; used by the rehoming
    experiment to byte-compare the clone against the transferred original).
    Never raises.
    """
    import torch
    _tensors: list[tuple[str, Any]] = []
    for _name, _tensor, _st, _addr, _nbytes in _iter_unet_tensors(unet):
        _tensors.append((_name, _tensor))
    return measure_tensors_synced_h2d(
        _tensors, label=label, keep_gpu=keep_gpu,
    )


def measure_tensors_synced_h2d(
    tensors: list[tuple[str, Any]], *, label: str = "", keep_gpu: bool = False,
) -> tuple[dict[str, Any], tuple[list[Any], list[str]] | None]:
    """Synchronized H2D of the ACTUAL storages of the given tensor refs.

    Same loop/measurement semantics as ``measure_model_synced_h2d`` but
    operates on an explicit ``(name, tensor)`` list — so the rehoming
    experiment can measure the ORIGINAL restored storages from references
    captured BEFORE an in-place rehome clone, even when the clone runs
    first.  The (name, gpu_tensor) pairing is preserved 1:1 so callers can
    byte-compare by name.  Never raises.
    """
    record: dict[str, Any] = {
        "label": label,
        "method": "model_storages_synced_h2d",
        "copy_style": "per_storage_non_blocking_final_sync",
        "storages": 0,
        "bytes": 0,
    }
    import time
    import torch
    _gpu_tensors: list[Any] = []
    _gpu_names: list[str] = []
    _held: list[Any] = [t for _, t in tensors]
    # ── H2D decomposition (measurement-only; never alters loop mechanics) ──
    # CUDA-event interval realizes the async copies (start event after the
    # pre-sync, end event before the existing final synchronize).  Every new
    # field is guarded; on any failure the field stays absent and the
    # function's "Never raises" contract holds.
    _ev_start = None
    _ev_end = None
    _loop_wall_start = None
    _loop_wall_end = None
    try:
        _ev_start = torch.cuda.Event(enable_timing=True)
        _ev_end = torch.cuda.Event(enable_timing=True)
    except Exception:
        _ev_start = _ev_end = None
    try:
        torch.cuda.synchronize()
        if _ev_start is not None:
            try:
                _ev_start.record()
            except Exception:
                _ev_start = None
        _start_wall = time.perf_counter()
        _start_cpu = _proc_self_stat_cpu_ms()
        _before = _rusage_faults()
        _loop_wall_start = time.perf_counter()
        for _name, _tensor in tensors:
            try:
                _gpu = _tensor.to(device="cuda", non_blocking=True)
            except Exception:
                continue
            _gpu_tensors.append(_gpu)
            _gpu_names.append(_name)
            _st = _tensor.untyped_storage() if hasattr(_tensor, "untyped_storage") else _tensor.storage()
            _held.append(_st)
            record["storages"] += 1
            _nbytes = int(_st.nbytes())
            record["bytes"] += _nbytes
            if _nbytes > record.get("largest_copy_bytes", 0):
                record["largest_copy_bytes"] = _nbytes
        _loop_wall_end = time.perf_counter()
        if _ev_end is not None:
            try:
                _ev_end.record()
            except Exception:
                _ev_end = None
        torch.cuda.synchronize()
        _wall_s = max(time.perf_counter() - _start_wall, 1e-9)
        _cpu_ms = _proc_self_stat_cpu_ms()
        record["wall_ms"] = round(_wall_s * 1000.0, 3)
        record["gb_per_s"] = round(
            (record["bytes"] / 1_000_000_000.0) / _wall_s, 3
        )
        # ── H2D decomposition fields (additive; guarded individually) ──
        if _loop_wall_start is not None and _loop_wall_end is not None:
            try:
                record["enqueue_host_ms"] = round(
                    (_loop_wall_end - _loop_wall_start) * 1000.0, 3
                )
            except Exception:
                pass
        if _ev_start is not None and _ev_end is not None:
            try:
                record["cuda_elapsed_ms"] = round(
                    float(_ev_start.elapsed_time(_ev_end)), 3
                )
            except Exception:
                pass
        # sync_wait_host_ms = total wall − loop body wall (pure subtraction;
        # host-side estimate covering the final synchronize + event-elapsed
        # read, consistent with the existing wall_ms window).
        _e_host = record.get("enqueue_host_ms")
        _w_total = record.get("wall_ms")
        if _e_host is not None and _w_total is not None:
            try:
                record["sync_wait_host_ms"] = round(max(_w_total - _e_host, 0.0), 3)
            except Exception:
                pass
        try:
            record["stream_id"] = str(torch.cuda.current_stream())
        except Exception:
            pass
        record["sync_method"] = "torch.cuda.synchronize (full device)"
        # ── H2D classification (guarded; additive key only) ──
        # classify_h2d reads the h2d_* key family; this measurement clone
        # stores the same values unprefixed, so provide BOTH spellings.
        # Absent when the telemetry module / function is unavailable; never
        # raises (the "Never raises" contract holds with the module absent).
        try:
            from comfymodal_runtime import host_hardware_telemetry as _hht_c
            _cls_view = dict(record)
            _cls_view["h2d_cuda_elapsed_ms"] = record.get("cuda_elapsed_ms")
            _cls_view["h2d_enqueue_host_ms"] = record.get("enqueue_host_ms")
            _cls_view["h2d_sync_wait_host_ms"] = record.get("sync_wait_host_ms")
            record["h2d_classification"] = _hht_c.classify_h2d(_cls_view)
        except Exception:
            pass
        record["process_cpu_ms"] = (
            round(_cpu_ms - _start_cpu, 3)
            if _cpu_ms is not None and _start_cpu is not None else None
        )
        _after = _rusage_faults()
        if _before and _after:
            record["major_faults"] = max(0, _after[0] - _before[0])
            record["minor_faults"] = max(0, _after[1] - _before[1])
        record["rss_mib"] = _proc_self_rss_mib()
        if keep_gpu:
            return record, (_gpu_tensors, _gpu_names)
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
        if keep_gpu:
            return record, None
    finally:
        if not keep_gpu:
            try:
                del _gpu_tensors
                torch.cuda.empty_cache()
            except Exception:
                pass
            _malloc_trim()
    return record, None


def _rusage_faults() -> tuple[int, int] | None:
    try:
        import resource as _r
        _ru = _r.getrusage(_r.RUSAGE_SELF)
        return (int(_ru.ru_majflt), int(_ru.ru_minflt))
    except Exception:
        return None


def clone_unet_to_fresh_ram_after_restore(unet: Any) -> dict[str, Any]:
    """Clone every UNET parameter/buffer storage into fresh anonymous RAM.

    Storage-faithful clone: for each UNIQUE storage (data_ptr, nbytes) one
    fresh anonymous storage is allocated and every parameter/buffer that
    references it is rebound (via ``.data`` / ``_buffers``) to an
    ``as_strided`` view of the SAME fresh storage — preserving dtype,
    shape, strides, storage offset, and tied/shared-storage relationships
    exactly.  Parameter objects keep their identity; module identity is
    unchanged (in-place rehome, never a rebuild).

    Records wall/process CPU, cloned storages/bytes, mincore residency of
    the fresh storage, backing classification, rusage faults and RSS.
    Never raises.
    """
    result: dict[str, Any] = {
        "method": "storage_faithful_fresh_ram_rehome",
        "cloned_storages": 0,
        "bytes": 0,
        "tensors_rebound": 0,
        "unsupported": 0,
    }
    import gc
    import time
    import torch
    _module = _resolve_unet_module(unet)
    _start_wall = time.perf_counter()
    _start_cpu = _proc_self_stat_cpu_ms()
    _before = _rusage_faults()
    try:
        _fresh_by_key: dict[tuple[int, int], Any] = {}

        def _alloc_fresh(key: tuple[int, int]) -> Any:
            _fresh = _fresh_by_key.get(key)
            if _fresh is None:
                _addr, _nbytes = key
                _fresh = torch.empty(
                    max(1, _nbytes), dtype=torch.uint8, device="cpu"
                )
                _fresh_by_key[key] = _fresh
            return _fresh

        _plans: list[tuple[Any, str, Any, Any, int]] = []  # (owner, kind, orig, fresh_typed, offset)

        def _plan_owner(owner: Any, name: str, tensor: Any) -> None:
            _plan = _plan_tensor_rebind(tensor, _alloc_fresh)
            if _plan is None:
                result["unsupported"] += 1
                return
            _fresh_typed, _offset = _plan
            _plans.append((owner, name, tensor, _fresh_typed, _offset))

        for _mod in _module.modules():
            for _key, _param in list(getattr(_mod, "_parameters", {}).items()):
                if _param is None:
                    continue
                _plan_owner(_mod, _key, _param)
            for _key, _buf in list(getattr(_mod, "_buffers", {}).items()):
                if _buf is None:
                    continue
                _plan_owner(_mod, _key, _buf)

        # ── Storage copy: parallel ctypes.memmove (fast path) ──────────
        # torch ``copy_`` on the restored pages measured 0.8-2 GB/s (the
        # copy kernel's own path), while a plain memcpy of the same pages
        # runs at 30-60 GB/s (proven by the native traversal in E1).  Each
        # unique source storage is copied into its fresh anonymous storage
        # with memmove; storages >4 MB are split into 8 chunks moved by a
        # bounded thread pool.  Strong refs to source storages and target
        # fresh tensors are held for the whole phase.
        import ctypes
        _copy_plan: list[tuple[int, int, int, Any, Any]] = []  # (src_ptr, dst_ptr, nbytes, src_st, dst_t)
        _seen_copy: set[tuple[int, int]] = set()
        for _owner, _name, _orig, _fresh_typed, _offset in _plans:
            try:
                _src_st = (
                    _orig.untyped_storage()
                    if hasattr(_orig, "untyped_storage") else _orig.storage()
                )
                _src_ptr = int(_src_st.data_ptr())
                _nbytes = int(_src_st.nbytes())
                _dst_t = _fresh_typed
                _dst_st = _dst_t.untyped_storage() if hasattr(_dst_t, "untyped_storage") else _dst_t.storage()
                _dst_ptr = int(_dst_st.data_ptr())
            except Exception:
                result["unsupported"] += 1
                continue
            _key = (_src_ptr, _nbytes)
            if _key in _seen_copy:
                continue
            _seen_copy.add(_key)
            _copy_plan.append((_src_ptr, _dst_ptr, _nbytes, _src_st, _dst_t))

        _MEMCPY_CHUNK = 8 * 1024 * 1024  # 8 MiB per memmove call
        _MEMCPY_WORKERS = 8
        _work: list[tuple[int, int, int]] = []
        for _src_ptr, _dst_ptr, _nbytes, _src_st, _dst_t in _copy_plan:
            if _nbytes <= _MEMCPY_CHUNK:
                _work.append((_src_ptr, _dst_ptr, _nbytes))
            else:
                _chunks = max(1, min(32, (_nbytes + _MEMCPY_CHUNK - 1) // _MEMCPY_CHUNK))
                _step = (_nbytes + _chunks - 1) // _chunks
                for _c in range(_chunks):
                    _off = _c * _step
                    _len = min(_step, _nbytes - _off)
                    if _len > 0:
                        _work.append((_src_ptr + _off, _dst_ptr + _off, _len))
        if _work:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=_MEMCPY_WORKERS, thread_name_prefix="v2-rehome-memcpy",
            ) as _pool:
                list(_pool.map(
                    lambda _args: ctypes.memmove(_args[1], _args[0], _args[2]), _work,
                ))
        result["memcpy_calls"] = len(_work)

        # ── Rebind views (no data copy) ────────────────────────────────
        _rebound = 0
        for _owner, _name, _orig, _fresh_typed, _offset in _plans:
            try:
                _view = torch.as_strided(
                    _fresh_typed, size=_orig.shape, stride=_orig.stride(),
                    storage_offset=_offset,
                )
                if isinstance(_orig, torch.nn.Parameter):
                    _orig.data = _view
                else:
                    _owner._buffers[_name] = _view
                _rebound += 1
            except Exception:
                result["unsupported"] += 1
        result["tensors_rebound"] = _rebound
        _cpu_ms = _proc_self_stat_cpu_ms()
        _wall_s = max(time.perf_counter() - _start_wall, 1e-9)
        result["wall_ms"] = round(_wall_s * 1000.0, 3)
        result["process_cpu_ms"] = (
            round(_cpu_ms - _start_cpu, 3)
            if _cpu_ms is not None and _start_cpu is not None else None
        )
        result["cloned_storages"] = len(_fresh_by_key)
        result["bytes"] = sum(_fresh.numel() for _fresh in _fresh_by_key.values())
        result["storage_keys"] = sorted(
            (str(k[0]), int(k[1])) for k in _fresh_by_key
        )[:8]
        _after = _rusage_faults()
        if _before and _after:
            result["major_faults"] = max(0, _after[0] - _before[0])
            result["minor_faults"] = max(0, _after[1] - _before[1])
        gc.collect()
        result["residency"] = mincore_unet_residency(unet)
        result["backing"] = capture_unet_backing_evidence(
            unet, label="after_rehome_clone",
        )
        result["rss_mib"] = _proc_self_rss_mib()
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:200]
    return result


def _plan_tensor_rebind(
    tensor: Any,
    alloc_fresh: Any,
) -> tuple[Any, int] | None:
    """Plan one tensor's rebind onto a fresh storage.

    Returns ``(fresh_typed_view, storage_offset_in_elements)`` or None for
    unsupported tensors (non-CPU / meta / sparse / quantized / empty /
    misaligned).  The fresh typed view covers the WHOLE fresh storage so
    ``torch.as_strided`` can address any offset; the copy target region is
    computed from the ORIGINAL tensor's storage offset.
    """
    try:
        import torch
        _dev = getattr(tensor, "device", None)
        _dev_type = getattr(_dev, "type", None)
        _dev_str = str(_dev_type() if callable(_dev_type) else (_dev_type or "")).lower()
        if _dev_str not in ("cpu", ""):
            return None
        if getattr(tensor, "is_meta", False):
            return None
        for _attr in ("is_sparse", "is_quantized", "is_mkldnn", "is_nested"):
            try:
                if getattr(tensor, _attr, False):
                    return None
            except Exception:
                return None
        if int(tensor.numel()) == 0:
            return None
        if hasattr(tensor, "untyped_storage"):
            _st = tensor.untyped_storage()
        else:
            _st = tensor.storage()
        _addr = int(_st.data_ptr())
        _nbytes = int(_st.nbytes())
        if not _addr or _nbytes <= 0:
            return None
        _itemsize = int(tensor.element_size())
        if _nbytes % _itemsize != 0:
            return None
        _fresh = alloc_fresh((_addr, _nbytes))
        _fresh_typed = _fresh.view(tensor.dtype)
        return _fresh_typed, int(tensor.storage_offset())
    except Exception:  # noqa: BLE001
        return None


def unet_metadata_fingerprint(unet: Any) -> dict[str, Any]:
    """Stable metadata fingerprint of every UNET param/buffer (no bytes).

    Records per-tensor dtype/shape/stride/storage-offset/storage-size plus
    an aggregate metadata hash — sufficient to prove clone identity
    (layout, dtype, ties by storage key) without hashing 12.3 GB of data.
    Never raises.
    """
    result: dict[str, Any] = {"tensors": 0, "bytes": 0, "hash": ""}
    import hashlib
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
    _h = hashlib.sha256()
    _rows: list[str] = []
    _seen_keys: set[tuple[int, int]] = set()
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
        _row = "|".join([
            _name,
            str(_tensor.dtype),
            str(list(_tensor.shape)),
            str(list(_tensor.stride())),
            str(int(_tensor.storage_offset())),
            str(int(_nbytes)),
        ])
        _rows.append(_row)
        _h.update(_row.encode("utf-8", errors="replace"))
        result["tensors"] += 1
        result["bytes"] += int(_nbytes)
        _seen_keys.add((_addr, _nbytes))
    result["storage_keys"] = len(_seen_keys)
    result["hash"] = _h.hexdigest()[:32]
    return result


def unet_byte_equality(original: Any, cloned: Any) -> dict[str, Any]:
    """Full byte equality between two UNET module states (torch.equal).

    Compares every parameter/buffer by NAME between *original* and
    *cloned*; reports compared/equal counts and the first mismatching
    name (or ``"all_equal"``).  Reads both models fully (~2 x 12.3 GB) —
    call AFTER all timing measurements.  Never raises.
    """
    result: dict[str, Any] = {"compared": 0, "equal": 0, "status": ""}
    try:
        import torch
        _a = _resolve_unet_module(original)
        _b = _resolve_unet_module(cloned)
        _a_items: dict[str, Any] = {}
        for _n, _t in _a.named_parameters(recurse=True, remove_duplicate=False):
            _a_items.setdefault(_n, _t)
        for _n, _t in _a.named_buffers(recurse=True, remove_duplicate=False):
            _a_items.setdefault(_n, _t)
        _b_items: dict[str, Any] = {}
        for _n, _t in _b.named_parameters(recurse=True, remove_duplicate=False):
            _b_items.setdefault(_n, _t)
        for _n, _t in _b.named_buffers(recurse=True, remove_duplicate=False):
            _b_items.setdefault(_n, _t)
        for _name in sorted(set(_a_items) | set(_b_items)):
            if _name not in _a_items or _name not in _b_items:
                result["status"] = f"missing:{_name}"
                return result
            try:
                if not torch.equal(_a_items[_name], _b_items[_name]):
                    result["status"] = f"mismatch:{_name}"
                    return result
            except Exception:
                result["status"] = f"compare_error:{_name}"
                return result
            result["compared"] += 1
            result["equal"] += 1
        result["status"] = "all_equal"
    except Exception as exc:  # noqa: BLE001
        result["status"] = f"error:{type(exc).__name__}"
    return result
