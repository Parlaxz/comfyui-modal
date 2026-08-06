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


def backing_diag_any_enabled() -> bool:
    return backing_verify_enabled() or anon_snapshot_enabled() or synth_h2d_probe_enabled()


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
    import time
    import torch
    record: dict[str, Any] = {
        "enabled": True,
        "bytes": int(bytes_),
        "dtype": "float32",
        "contiguous": True,
        "touched": True,
    }
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
        try:
            del _gpu_tensor
            torch.cuda.empty_cache()
        except Exception:
            pass
        del _cpu_tensor
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
    return record
