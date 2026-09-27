"""Measurement-only mechanism probe for the V2 CUDA-loader salvage experiment.

The production pinned-ring UNET loader (V1, ``COMFYMODAL_V2_UNET_PINNED_RING``,
``_ring_*`` in ``model_preload.py``) is correct but slow.  The salvage
hypothesis (V2) eliminates three measured host costs:

  (a) the ~2.3 s ``get_model`` construction regression by constructing the
      ZImage model under ``torch.device("meta")`` and materializing directly
      on CUDA via ``Module.to_empty``;
  (b) CPU staging entirely, via either (i) ``cudaHostRegister`` on the
      existing safetensors mmap ranges followed by async non-blocking DMA
      mmap -> GPU, or (ii) ``os.preadv`` reading file bytes DIRECTLY into
      preallocated pinned buffers then async DMA (single pass, no
      mmap -> pinned memcpy).

THIS MODULE MEASURES ONLY.  It never loads a live model, never mutates
production loader state, and runs only when explicitly invoked through the
standalone Modal function ``run_unet_mechanism_probe`` (modal_app.py) or
directly via ``run_unet_mechanism_probes``.  Every sub-probe is individually
try/except'd; the result dict is JSON-safe and bounded.

Offline contract (Windows dev box): the module imports with zero side
effects (no torch init at import) and every OS/Linux-only capability
(``os.preadv`` / ``os.posix_fadvise`` / ``os.statvfs`` / ``resource`` /
GDS / ``cudaHostRegister``) degrades to a named ``skipped``/``error`` entry
when absent.  The real measurement runs on the Linux Modal container.
"""

from __future__ import annotations

import gc as _gc
import glob as _glob
import hashlib as _hashlib
import json as _json
import os as _os
import platform as _platform
import struct as _struct
import subprocess as _subprocess
import sys as _sys
import time as _time

# ── Constants (all measurements are bounded by these) ─────────────────────
_PAGE = 4096
# Windows mmap offset/length must be a multiple of the allocation granularity
# (64 KiB), which is itself a multiple of the page size, so aligning to this
# value is safe for both mmap and cudaHostRegister page alignment.
_MMAP_ALIGN = (64 * 1024) if _os.name == "nt" else _PAGE

_TOUCH_WAVE_TARGET = 64 * 1024 * 1024
_TOUCH_64MB = 64 * 1024 * 1024
_TOUCH_256MB = 256 * 1024 * 1024
_TOUCH_1500MB = 1536 * 1024 * 1024  # 1.5 GiB
_PREADV_64MB = 64 * 1024 * 1024
_PREADV_128MB = 128 * 1024 * 1024
_PREADV_256MB = 256 * 1024 * 1024
_REG_256MB = 256 * 1024 * 1024
_REG_1500MB = 1536 * 1024 * 1024  # 1.5 GiB
_BULK_CHUNKS = 64
_BULK_CHUNK_BYTES = 24 * 1024 * 1024  # 64 x 24 MiB == 1.5 GiB dests
_HASH_SEG = 256 * 1024  # hash only the first/last 256 KiB of a region
_GDS_GLOB_LIMIT = 8
_CUDA_ERROR_NOT_SUPPORTED = 801
_MAX_POISON_PATHS = 40
_PINNED_MAX_CONCURRENT = 1

_MP_MODULE = None


def _lazy_mp():
    """Return the model_preload module (cached) or None.  Attribute access is
    deferred to call time so test monkeypatches of module-level helpers are
    observed."""
    global _MP_MODULE
    if _MP_MODULE is None:
        try:
            import importlib as _il
            _MP_MODULE = _il.import_module("comfymodal_runtime.model_preload")
        except Exception:
            _MP_MODULE = False
    return _MP_MODULE or None


# ── A. Pure helpers (offline-testable, no CUDA/file IO) ───────────────────


def page_align_range(start, end, page_size=4096):
    """Floor-align *start* and ceil-align *end* to *page_size*.

    ``page_align_range(0, 100, 4096) -> (0, 4096)``.  Raises ValueError for a
    non-positive page size or an inverted range."""
    start = int(start)
    end = int(end)
    page_size = int(page_size)
    if page_size <= 0:
        raise ValueError(f"page_size must be positive: {page_size}")
    if end < start:
        raise ValueError(f"end ({end}) < start ({start})")
    aligned_start = (start // page_size) * page_size
    aligned_end = ((end + page_size - 1) // page_size) * page_size
    return aligned_start, aligned_end


def _header_keys(header):
    return [k for k in (header or {}) if k != "__metadata__"]


def build_wave_ranges(header, keys=None, wave_target_bytes=64 * 1024 * 1024,
                      max_wave_bytes=128 * 1024 * 1024):
    """Partition the header's tensors (in header order) into contiguous byte
    waves.  Returns a list of wave dicts or None when any single tensor
    exceeds *max_wave_bytes* (unsupported).

    Each wave::

      {keys, rel_byte_start, rel_byte_end, tensor_bytes,
       tensors: [{key, dtype, shape, rel_off, rel_end, nbytes}, ...]}

    Tensors of a wave are byte-contiguous in the file (a tensor whose
    ``rel_off`` does not equal the running wave end opens a new wave), so
    ``rel_byte_end - rel_byte_start == sum(nbytes)`` per wave."""
    wave_target_bytes = int(wave_target_bytes)
    max_wave_bytes = int(max_wave_bytes)
    if not header:
        return []
    _keys = [k for k in (list(keys) if keys is not None else _header_keys(header))]
    waves = []
    cur = None
    for k in _keys:
        info = (header or {}).get(k)
        if info is None:
            continue
        try:
            offs = info.get("data_offsets")
            if not offs:
                continue
            rel_off = int(offs[0])
            rel_end = int(offs[1])
        except Exception:
            continue
        nbytes = rel_end - rel_off
        if nbytes <= 0:
            continue
        if nbytes > max_wave_bytes:
            return None
        tinfo = {
            "key": str(k),
            "dtype": str(info.get("dtype", "")),
            "shape": [int(_s) for _s in (info.get("shape") or [])],
            "rel_off": rel_off,
            "rel_end": rel_end,
            "nbytes": nbytes,
        }
        if cur is None:
            cur = {
                "keys": [str(k)],
                "rel_byte_start": rel_off,
                "rel_byte_end": rel_end,
                "tensor_bytes": nbytes,
                "tensors": [tinfo],
            }
        elif rel_off != cur["rel_byte_end"]:
            # File bytes are not contiguous here -> close this wave so every
            # wave remains internally contiguous.
            waves.append(cur)
            cur = {
                "keys": [str(k)],
                "rel_byte_start": rel_off,
                "rel_byte_end": rel_end,
                "tensor_bytes": nbytes,
                "tensors": [tinfo],
            }
        elif cur["tensor_bytes"] + nbytes > wave_target_bytes:
            waves.append(cur)
            cur = {
                "keys": [str(k)],
                "rel_byte_start": rel_off,
                "rel_byte_end": rel_end,
                "tensor_bytes": nbytes,
                "tensors": [tinfo],
            }
        else:
            cur["keys"].append(str(k))
            cur["rel_byte_end"] = rel_end
            cur["tensor_bytes"] += nbytes
            cur["tensors"].append(tinfo)
    if cur is not None:
        waves.append(cur)
    return waves


def slice_tensor_from_buffer(buf, dtype, shape, offset, nbytes):
    """Return ``buf[offset:offset+nbytes].view(dtype=dtype).reshape(shape)``.

    *buf* may be a torch tensor or any buffer-protocol object (bytearray,
    mmap, numpy array); non-tensors are wrapped with ``torch.frombuffer``.
    Works for mixed bf16/f16/f32 dtypes."""
    import torch as _t
    if not isinstance(buf, _t.Tensor):
        buf = _t.frombuffer(buf, dtype=_t.uint8)
    offset = int(offset)
    nbytes = int(nbytes)
    return buf[offset:offset + nbytes].view(dtype=dtype).reshape([int(_s) for _s in shape])


def reconcile_header_bytes(header):
    """Reconcile the header's data offsets against the safetensors layout.

    Returns ``(total_data_bytes, per_key_nbytes)`` when every tensor range is
    non-negative and the sorted ranges exactly cover ``[0, total)`` with no
    gaps or overlaps (the packed layout the format guarantees); None on any
    inconsistency (overlap, gap, negative, or inverted range)."""
    if not header:
        return (0, {})
    ranges = []
    per_key = {}
    for k, info in (header or {}).items():
        if k == "__metadata__":
            continue
        try:
            offs = info.get("data_offsets")
            if not offs:
                return None
            s = int(offs[0])
            e = int(offs[1])
        except Exception:
            return None
        if s < 0 or e < s:
            return None
        ranges.append((s, e))
        per_key[str(k)] = e - s
    if not ranges:
        return (0, {})
    ranges.sort(key=lambda r: r[0])
    expect = 0
    for s, e in ranges:
        if s != expect:
            return None
        expect = e
    return (expect, per_key)


def collect_meta_tensors(obj, path=""):
    """Walk *obj* and return ``[(path, dtype, shape, numel), ...]`` for every
    torch tensor whose device type is ``"meta"``.

    Traverses nn.Module params/buffers/submodules, dicts, lists/tuples, and
    plain object attribute trees (bounded depth <= 6, cycle-safe by id).
    Real (non-meta) tensors are ignored."""
    import torch as _t
    out = []
    seen = set()

    def visit(o, p, depth):
        if depth > 6:
            return
        oid = id(o)
        if oid in seen:
            return
        if isinstance(o, _t.nn.Module):
            seen.add(oid)
            for name, param in o._parameters.items():
                if param is None:
                    continue
                if param.device.type == "meta":
                    out.append((f"{p}.{name}" if p else str(name),
                                str(param.dtype), list(param.shape), int(param.numel())))
            for name, buf in o._buffers.items():
                if buf is None:
                    continue
                if buf.device.type == "meta":
                    out.append((f"{p}.{name}" if p else str(name),
                                str(buf.dtype), list(buf.shape), int(buf.numel())))
            for name, mod in o._modules.items():
                if mod is not None:
                    visit(mod, f"{p}.{name}" if p else str(name), depth + 1)
            # Plain instance attributes (e.g. BaseModel.model_sampling) hold
            # non-module objects that can still carry poisoned meta tensors.
            try:
                _plain = dict(vars(o))
            except Exception:
                _plain = {}
            for _name, _v in _plain.items():
                if _name in ("_parameters", "_buffers", "_modules",
                             "_non_persistent_buffers_set"):
                    continue
                if _name in o._parameters or _name in o._buffers or _name in o._modules:
                    continue
                if _v is None or callable(_v):
                    continue
                if isinstance(_v, (_t.nn.Module, _t.Tensor)):
                    continue  # handled above
                visit(_v, f"{p}.{_name}" if p else str(_name), depth + 1)
            return
        if isinstance(o, dict):
            seen.add(oid)
            for k, v in o.items():
                visit(v, f"{p}.{k}" if p else str(k), depth + 1)
            return
        if isinstance(o, (list, tuple)):
            seen.add(oid)
            for i, v in enumerate(o):
                visit(v, f"{p}[{i}]", depth + 1)
            return
        if isinstance(o, _t.Tensor):
            if o.device.type == "meta":
                out.append((p, str(o.dtype), list(o.shape), int(o.numel())))
            return
        if o is None or isinstance(o, (str, bytes, int, float, bool)):
            return
        # Plain object attribute tree.
        seen.add(oid)
        for name in dir(o):
            if name.startswith("_"):
                continue
            try:
                v = getattr(o, name)
            except Exception:
                continue
            if callable(v):
                continue
            visit(v, f"{p}.{name}" if p else str(name), depth + 1)

    visit(obj, path, 0)
    return out


def is_pinned(buf):
    """True when *buf* reports itself pinned; never raises."""
    try:
        return bool(buf.is_pinned())
    except Exception:
        return False


def snapshot_rusage():
    """Process resource snapshot ``{rss_bytes, minflt, majflt, utime, stime}``
    via the ``resource`` module (Linux); ``{}`` on Windows/ImportError.
    Never raises.  ``ru_maxrss`` is a high-water mark so deltas are monotonic."""
    try:
        import resource as _resource
        r = _resource.getrusage(_resource.RUSAGE_SELF)
        return {
            "rss_bytes": int(r.ru_maxrss) * 1024,
            "minflt": int(r.ru_minflt),
            "majflt": int(r.ru_majflt),
            "utime": float(r.ru_utime),
            "stime": float(r.ru_stime),
        }
    except Exception:
        return {}


def _rusage_delta(a, b, key):
    try:
        if a and b and a.get(key) is not None and b.get(key) is not None:
            return int(b[key]) - int(a[key])
    except Exception:
        pass
    return None


def _json_safe(value):
    """JSON-safety wrapper.  Prefers model_preload._c6_json_safe (handles
    torch.dtype/device/tensors/numpy scalars); falls back to a minimal
    recursive str()-based conversion when model_preload is unavailable."""
    _mp = _lazy_mp()
    if _mp is not None:
        try:
            return _mp._c6_json_safe(value)
        except Exception:
            pass
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


# ── Generic measurement wrapper ───────────────────────────────────────────


def _measure(fn):
    """Run *fn* (returns an extra-fields dict or None) inside a wall + rusage
    bracket.  Returns ``{status, wall_ms, rss_delta_bytes, minflt_delta}``
    merged with the fn's extra fields (or an error string on exception)."""
    _r0 = snapshot_rusage()
    _t0 = _time.perf_counter()
    try:
        _extra = fn()
        _status = "ok"
        _err = ""
    except Exception as exc:  # noqa: BLE001
        _extra = None
        _status = "error"
        _err = f"{type(exc).__name__}: {str(exc)[:200]}"
    _wall = round((_time.perf_counter() - _t0) * 1000, 4)
    _r1 = snapshot_rusage()
    _entry = {
        "status": _status,
        "wall_ms": _wall,
        "rss_delta_bytes": _rusage_delta(_r0, _r1, "rss_bytes"),
        "minflt_delta": _rusage_delta(_r0, _r1, "minflt"),
    }
    if _err:
        _entry["error"] = _err
    if _extra:
        _entry.update(_extra)
    return _entry


def _empty_cache(torch_module):
    try:
        torch_module.cuda.empty_cache()
    except Exception:
        pass


def _model_summary(model):
    """Bounded param/device/dtype summary of a constructed model."""
    try:
        _params = list(model.parameters())
    except Exception:
        _params = []
    _devices = sorted({str(p.device) for p in _params})
    _dtype_counts = {}
    for p in _params:
        _dtype_counts[str(p.dtype)] = _dtype_counts.get(str(p.dtype), 0) + 1
    return {
        "param_count": len(_params),
        "device_summary": _devices,
        "dtype_counts": _dtype_counts,
    }


# ── Section 1: env ────────────────────────────────────────────────────────


def _probe_env():
    import torch as _t
    out = {
        "status": "ok",
        "os": _os.name,
        "platform": _sys.platform,
        "python": _platform.python_version(),
        "torch_version": "",
        "cuda_available": False,
        "cuda_device_name": None,
        "cudart_attrs": [],
    }
    try:
        out["torch_version"] = str(_t.__version__)
    except Exception:
        pass
    try:
        out["cuda_available"] = bool(_t.cuda.is_available())
    except Exception:
        pass
    if out["cuda_available"]:
        try:
            out["cuda_device_name"] = str(_t.cuda.get_device_name(0))
        except Exception:
            out["cuda_device_name"] = None
    try:
        _cudart = _t.cuda.cudart()
        out["cudart_attrs"] = [
            a for a in ("cudaHostRegister", "cudaHostUnregister", "cudaDeviceGetAttribute")
            if callable(getattr(_cudart, a, None))
        ]
    except Exception:
        pass
    return out


# ── Section 2: gds (cheap capability check only) ──────────────────────────


def _probe_gds():
    out = {
        "status": "ok",
        "libcufile_found": False,
        "libcufile_paths": [],
        "nvidia_fs_proc_exists": False,
        "driver_version": "",
        "verdict": "unknown",
        "reason": "",
    }
    try:
        _paths = []
        try:
            import ctypes.util as _ctypes_util
            _lib = _ctypes_util.find_library("cufile")
            if _lib:
                _paths.append(str(_lib))
        except Exception:
            pass
        try:
            _found = _glob.glob("/usr/local/cuda*/**/libcufile*", recursive=True)
            _paths.extend(str(_p) for _p in _found[:_GDS_GLOB_LIMIT])
        except Exception:
            pass
        _paths = list(dict.fromkeys(_paths))
        out["libcufile_found"] = bool(_paths)
        out["libcufile_paths"] = _paths
        try:
            out["nvidia_fs_proc_exists"] = bool(_os.path.exists("/proc/driver/nvidia-fs"))
        except Exception:
            pass
        try:
            _r = _subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10,
            )
            _lines = [ln.strip() for ln in (_r.stdout or "").splitlines() if ln.strip()]
            out["driver_version"] = _lines[0] if _lines else ""
        except Exception:
            out["driver_version"] = ""
        if out["libcufile_found"] and out["nvidia_fs_proc_exists"]:
            out["verdict"] = "supported"
            out["reason"] = "libcufile+nvidia-fs present (IOMMU not checked)"
        elif out["libcufile_found"] or out["nvidia_fs_proc_exists"]:
            out["verdict"] = "not_supported"
            out["reason"] = "partial install (libcufile or nvidia-fs missing)"
        else:
            out["verdict"] = "not_supported"
            out["reason"] = "no libcufile, no nvidia-fs"
    except Exception as exc:  # noqa: BLE001
        out["status"] = "error"
        out["verdict"] = "unknown"
        out["reason"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out


# ── Section 3: file ───────────────────────────────────────────────────────


def _probe_file(model_path, header):
    out = {
        "status": "error",
        "path": str(model_path),
        "size_bytes": -1,
        "fd_open_ok": False,
        "statvfs_report": {},
        "header_parse_ok": False,
        "header_bytes": -1,
        "data_start_offset": -1,
        "tensor_count": 0,
        "total_data_bytes": 0,
    }
    try:
        out["size_bytes"] = int(_os.path.getsize(model_path))
    except Exception:
        pass
    _fd = None
    try:
        _fd = _os.open(model_path, _os.O_RDONLY)
        out["fd_open_ok"] = True
    except Exception:
        pass
    if _fd is not None:
        try:
            _os.close(_fd)
        except Exception:
            pass
    _st = {}
    try:
        _v = _os.statvfs(model_path)
        _st = {
            k: str(getattr(_v, k))
            for k in ("f_bsize", "f_frsize", "f_blocks", "f_bfree", "f_bavail",
                      "f_files", "f_ffree", "f_favail", "f_flag", "f_namemax")
            if hasattr(_v, k)
        }
    except Exception:
        _st = {"placeholder": "statvfs_unavailable_on_this_os"}
    out["statvfs_report"] = _st
    try:
        with open(model_path, "rb") as _f:
            _head_len = _struct.unpack("<Q", _f.read(8))[0]
        out["header_bytes"] = int(_head_len)
        out["data_start_offset"] = 8 + int(_head_len)
    except Exception:
        pass
    if header is None:
        return out
    out["header_parse_ok"] = True
    out["tensor_count"] = len(_header_keys(header))
    _rec = reconcile_header_bytes(header)
    if _rec is not None:
        out["total_data_bytes"] = int(_rec[0])
    out["status"] = "ok" if out["header_parse_ok"] else "error"
    return out


# ── Section 4: construction (the 2.34 s get_model battery) ────────────────


def _probe_construction(model_path):
    import torch as _t
    _mp = _lazy_mp()
    out = {}
    _err_base = {
        "status": "error",
        "wall_ms": 0.0,
        "rss_delta_bytes": None,
        "minflt_delta": None,
        "error": "config_derivation_failed",
    }
    if _mp is None:
        out["config_derivation"] = {"status": "error", "error": "model_preload_unavailable"}
        for _name in ("c1_plain", "c1_warm", "c2_meta", "c3_meta_fix", "c4_to_empty"):
            out[_name] = dict(_err_base)
        return out, None
    try:
        _derived = _mp._ring_derive_config(model_path)
    except Exception as exc:  # noqa: BLE001
        _derived = None
        _err_base["error"] = f"config_derivation: {type(exc).__name__}: {str(exc)[:120]}"
    if _derived is None:
        out["config_derivation"] = {"status": "error", "error": _err_base["error"]}
        for _name in ("c1_plain", "c1_warm", "c2_meta", "c3_meta_fix", "c4_to_empty"):
            out[_name] = dict(_err_base)
        return out, None
    _config, _meta_sd, _header, _n_layers, _prefix = _derived
    out["config_derivation"] = {
        "status": "ok",
        "config_class": type(_config).__name__,
        "n_layers": int(_n_layers or 0),
        "eff_prefix": str(_prefix or ""),
        "sd_tensor_count": int(len(_meta_sd or {})),
    }
    _holder = {}

    def _c1_run():
        with _t.no_grad():
            _m = _config.get_model(_meta_sd, "")
        _extra = _model_summary(_m)
        del _m
        _gc.collect()
        _empty_cache(_t)
        return _extra

    out["c1_plain"] = _measure(_c1_run)

    def _c1w_run():
        with _t.no_grad():
            _m = _config.get_model(_meta_sd, "")
        _extra = _model_summary(_m)
        del _m
        _gc.collect()
        _empty_cache(_t)
        return _extra

    out["c1_warm"] = _measure(_c1w_run)

    def _c2_run():
        with _t.no_grad(), _t.device("meta"):
            _m = _config.get_model(_meta_sd, "")
        _holder["c2"] = _m
        _params = list(_m.parameters())
        _all_meta = bool(_params) and all(_p.device.type == "meta" for _p in _params)
        _mc = collect_meta_tensors(_m)
        _meta_bytes = int(sum(_n for (_p, _d, _s, _n) in _mc))
        return {
            "param_count": len(_params),
            "all_params_meta": bool(_all_meta),
            "meta_tensor_count": len(_mc),
            "meta_tensor_bytes": _meta_bytes,
            "poisoned_paths": [_p for (_p, _d, _s, _n) in _mc][:_MAX_POISON_PATHS],
            "device_summary": sorted({_p.device.type for _p in _params}) if _params else [],
        }

    out["c2_meta"] = _measure(_c2_run)
    _c2_model = _holder.get("c2")
    _c2_poisoned = bool(out["c2_meta"].get("meta_tensor_count"))
    if _c2_model is not None and _c2_poisoned:

        def _c3_run():
            # comfy/model_base.py line 76 imports `comfy.model_sampling` and
            # line 97 defines the module-level factory
            # `def model_sampling(model_config, model_type)`; BaseModel.__init__
            # (line 173) assigns `self.model_sampling = model_sampling(...)`.
            # Recreate it OUTSIDE the meta context using the same helper.
            _ms_fn = _mp._c6_comfy_fn("comfy.model_base", "model_sampling")
            if not callable(_ms_fn):
                raise RuntimeError("comfy.model_base.model_sampling unavailable")
            _ms = _ms_fn(_c2_model.model_config, _c2_model.model_type)
            _c2_model.model_sampling = _ms
            _mc = collect_meta_tensors(_ms)
            return {
                "sampling_meta_tensor_count": len(_mc),
                "sampling_meta_tensor_bytes": int(sum(_n for (_p, _d, _s, _n) in _mc)),
                "remaining_poisoned_paths": [_p for (_p, _d, _s, _n) in _mc][:_MAX_POISON_PATHS],
            }

        out["c3_meta_fix"] = _measure(_c3_run)
    else:
        out["c3_meta_fix"] = {
            "status": "skipped",
            "wall_ms": 0.0,
            "reason": "c2_meta_no_poisoned_tensors" if _c2_model is not None
            else "c2_meta_model_unavailable",
        }
    del _c2_model
    _gc.collect()
    _empty_cache(_t)

    def _c4_run():
        with _t.no_grad(), _t.device("meta"):
            _m = _config.get_model(_meta_sd, "")
        _m.to_empty(device=_t.device("cuda"))
        _params = list(_m.parameters())
        _extra = {
            "param_count": len(_params),
            "device_summary": sorted({str(_p.device) for _p in _params}) if _params else [],
            "dtype_summary": sorted({str(_p.dtype) for _p in _params}) if _params else [],
        }
        del _m
        _gc.collect()
        _empty_cache(_t)
        return _extra

    out["c4_to_empty"] = _measure(_c4_run)
    return out, (_config, _meta_sd, _header, _n_layers, _prefix)


def _probe_c5(derived):
    """Real-device get_model AFTER the io touch section warmed page cache
    (placement-vs-memory-pressure signal).  Runs last by design; the ordering
    (construction_a -> io -> c5) is documented in the orchestrator."""
    import torch as _t
    if derived is None:
        return {
            "status": "error",
            "wall_ms": 0.0,
            "rss_delta_bytes": None,
            "minflt_delta": None,
            "error": "config_derivation_failed",
        }
    _config, _meta_sd, _header, _n_layers, _prefix = derived

    def _run():
        with _t.no_grad():
            _m = _config.get_model(_meta_sd, "")
        _extra = _model_summary(_m)
        del _m
        _gc.collect()
        _empty_cache(_t)
        return _extra

    return _measure(_run)


# ── Section 5: io ─────────────────────────────────────────────────────────


def _touch_keys_for_target(waves, target, max_keys=32):
    """Accumulate keys (in file order from the head, i.e. wave 0) whose
    combined bytes reach *target*, bounded to *max_keys* keys."""
    keys = []
    acc = 0
    for w in waves or []:
        for t in w.get("tensors", []):
            keys.append(t["key"])
            acc += int(t["nbytes"])
            if acc >= int(target) or len(keys) >= int(max_keys):
                return keys, acc
    return keys, acc


def _safe_open_exit(f):
    """Close a safetensors ``safe_open`` handle.  Not every safetensors
    version exposes ``.close()``; the context-manager protocol is the
    portable close.  Never raises."""
    if f is None:
        return
    _exit = getattr(f, "__exit__", None)
    if callable(_exit):
        try:
            _exit(None, None, None)
        except Exception:
            pass


def _tensor_nbytes(header, key):
    try:
        offs = (header or {}).get(key, {}).get("data_offsets") or [0, 0]
        return int(offs[1]) - int(offs[0])
    except Exception:
        return 0


def _probe_i_touch(model_path, ctx):
    """Page-cache residency probe: safetensors mmap get_tensor for key sets
    covering ~64 MiB / ~256 MiB / ~1.5 GiB; first-touch wall, second-touch
    wall (same key), effective GB/s each."""
    try:
        import safetensors as _st
    except Exception:
        return {"status": "skipped", "reason": "unavailable: safetensors"}
    header = ctx.get("header")
    if not header:
        return {"status": "skipped", "reason": "header_unavailable"}
    try:
        waves = build_wave_ranges(header, wave_target_bytes=_TOUCH_WAVE_TARGET)
    except Exception:
        waves = []
    out = {
        "status": "ok",
        "wave_count": len(waves),
        "largest_wave_bytes": int(max((w["tensor_bytes"] for w in waves), default=0)),
    }
    if not waves:
        return {**out, "status": "error", "error": "no_waves"}
    try:
        _f = _st.safe_open(model_path, framework="pt", device="cpu")
    except Exception as exc:  # noqa: BLE001
        return {**out, "status": "error", "error": f"open: {type(exc).__name__}: {str(exc)[:120]}"}
    try:
        for _label, _target in (
            ("touch_64MiB", _TOUCH_64MB),
            ("touch_256MiB", _TOUCH_256MB),
            ("touch_1.5GiB", _TOUCH_1500MB),
        ):
            try:
                _keys, _acc = _touch_keys_for_target(waves, _target, max_keys=32)
                if not _keys:
                    out[_label] = {"status": "error", "error": "no_keys_for_target"}
                    continue
                _t0 = _time.perf_counter()
                _bytes = 0
                for _k in _keys:
                    _tt = _f.get_tensor(_k)
                    _bytes += int(_tt.numel()) * int(_tt.element_size())
                    del _tt
                _wall1 = (_time.perf_counter() - _t0) * 1000
                _big = max(_keys, key=lambda _k: _tensor_nbytes(header, _k))
                _t0 = _time.perf_counter()
                _tt = _f.get_tensor(_big)
                _wall2 = (_time.perf_counter() - _t0) * 1000
                del _tt
                _big_nbytes = _tensor_nbytes(header, _big)
                out[_label] = {
                    "status": "ok",
                    "bytes": int(_bytes),
                    "key_count": len(_keys),
                    "first_touch_wall_ms": round(_wall1, 4),
                    "first_touch_gbps": round(_bytes / (_wall1 * 1e6) if _wall1 > 0 else 0.0, 4),
                    "second_touch_key": _big,
                    "second_touch_key_bytes": int(_big_nbytes),
                    "second_touch_wall_ms": round(_wall2, 4),
                    "second_touch_gbps": round(
                        _big_nbytes / (_wall2 * 1e6) if _wall2 > 0 else 0.0, 4),
                }
            except Exception as exc:  # noqa: BLE001
                out[_label] = {"status": "error",
                               "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    finally:
        _safe_open_exit(_f)
    return out


def _probe_i_fadvise(model_path, ctx):
    """os.posix_fadvise WILLNEED/SEQUENTIAL wall + post-advise 256 MiB
    first-touch (effect signal)."""
    _fadv = getattr(_os, "posix_fadvise", None)
    if not callable(_fadv):
        return {"status": "skipped", "reason": "unavailable: os.posix_fadvise"}
    out = {
        "status": "ok",
        "constants": {
            "POSIX_FADV_WILLNEED": int(getattr(_os, "POSIX_FADV_WILLNEED", 3)),
            "POSIX_FADV_SEQUENTIAL": int(getattr(_os, "POSIX_FADV_SEQUENTIAL", 2)),
        },
    }
    _fd = None
    try:
        _fd = _os.open(model_path, _os.O_RDONLY)
        _t0 = _time.perf_counter()
        _fadv(_fd, 0, 0, getattr(_os, "POSIX_FADV_WILLNEED", 3))
        out["willneed_wall_ms"] = round((_time.perf_counter() - _t0) * 1000, 4)
        out["willneed_ok"] = True
        _t0 = _time.perf_counter()
        _fadv(_fd, 0, 0, getattr(_os, "POSIX_FADV_SEQUENTIAL", 2))
        out["sequential_wall_ms"] = round((_time.perf_counter() - _t0) * 1000, 4)
        out["sequential_ok"] = True
    except Exception as exc:  # noqa: BLE001
        out["status"] = "error"
        out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    finally:
        if _fd is not None:
            try:
                _os.close(_fd)
            except Exception:
                pass
    try:
        _touch = _probe_single_touch(model_path, ctx, _TOUCH_256MB)
        out["post_advise_first_touch_wall_ms"] = _touch["first_touch_wall_ms"]
        out["post_advise_first_touch_gbps"] = _touch["first_touch_gbps"]
        out["post_advise_bytes"] = _touch["bytes"]
    except Exception as exc:  # noqa: BLE001
        out["post_advise_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out


def _probe_single_touch(model_path, ctx, target):
    """One bounded first-touch measurement (used by i_fadvise)."""
    import safetensors as _st
    header = ctx.get("header")
    if not header:
        raise RuntimeError("header_unavailable")
    waves = build_wave_ranges(header, wave_target_bytes=_TOUCH_WAVE_TARGET)
    keys, _acc = _touch_keys_for_target(waves, target, max_keys=32)
    if not keys:
        raise RuntimeError("no_keys_for_target")
    with _st.safe_open(model_path, framework="pt", device="cpu") as _f:
        _t0 = _time.perf_counter()
        _bytes = 0
        for _k in keys:
            _tt = _f.get_tensor(_k)
            _bytes += int(_tt.numel()) * int(_tt.element_size())
            del _tt
        _wall = (_time.perf_counter() - _t0) * 1000
    return {
        "bytes": int(_bytes),
        "first_touch_wall_ms": round(_wall, 4),
        "first_touch_gbps": round(_bytes / (_wall * 1e6) if _wall > 0 else 0.0, 4),
        "key_count": len(keys),
    }


def _tensor_raw_bytes(t):
    """Raw bytes of a torch tensor (bf16 has no numpy mapping -> uint8 view)."""
    import torch as _t
    _c = t.contiguous()
    if _c.dtype == _t.bfloat16:
        return _c.view(_t.uint8).numpy().tobytes()
    return _c.numpy().tobytes()


def _reference_bytes_for_range(so, header, lo, hi):
    """Safetensors data == the concatenation of tensor bytes in offset order;
    reconstruct the reference bytes for file-data range [lo, hi) from
    ``get_tensor`` output (header order is validated as file order by
    reconcile_header_bytes)."""
    _items = []
    for _k, _info in (header or {}).items():
        if _k == "__metadata__":
            continue
        _offs = _info.get("data_offsets")
        if not _offs:
            continue
        _s, _e = int(_offs[0]), int(_offs[1])
        if _e <= lo:
            continue
        if _s >= hi:
            break
        _items.append((_s, _e, _k))
    _items.sort(key=lambda x: x[0])
    _parts = []
    for _s, _e, _k in _items:
        _t = so.get_tensor(_k)
        try:
            _raw = _tensor_raw_bytes(_t)
        finally:
            del _t
        _a = max(_s, lo) - _s
        _b = min(_e, hi) - _s
        if _b > _a:
            _parts.append(_raw[_a:_b])
    return b"".join(_parts)


def _region_hash_match(so, header, rel_start, region_bytes, buf):
    """Hash the first + last 256 KiB of a preadv'd region and compare against
    the safetensors reference bytes for the same file-data ranges.  None when
    verification is impossible (not an assertion failure)."""
    try:
        if so is None or region_bytes <= 0:
            return None
        _seg = min(_HASH_SEG, int(region_bytes))

        def _h(b):
            return _hashlib.sha256(bytes(b)).hexdigest()

        _head = _h(buf[:_seg])
        _tail = _h(buf[int(region_bytes) - _seg:])
        _ref_head = _reference_bytes_for_range(so, header, rel_start, rel_start + _seg)
        _ref_tail = _reference_bytes_for_range(
            so, header, rel_start + int(region_bytes) - _seg, rel_start + int(region_bytes))
        return bool(_head == _h(_ref_head) and _tail == _h(_ref_tail))
    except Exception:
        return None


def _preadv_size_runs(fd, so, header, data_start, total_data, size):
    """Three consecutive *size*-byte preadv ranges at data offsets
    0 / size / 2*size (clamped to the file), then one warm repeat of range 0.
    Allocates at most ONE pinned buffer at a time (freed between ranges)."""
    import torch as _t
    _preadv = getattr(_os, "preadv", None)
    out_ranges = []
    _warm = None
    for i in range(3):
        rel_start = int(i) * int(size)
        if rel_start >= int(total_data):
            out_ranges.append({
                "range": int(i), "status": "ok", "bytes_returned": 0,
                "wall_ms": 0.0, "gbps": 0.0, "hash_match": None,
                "reason": "beyond_eof",
            })
            continue
        nbytes = min(int(size), int(total_data) - rel_start)
        pinned = _t.empty(nbytes, dtype=_t.uint8, pin_memory=True)
        npv = None
        mv = None
        try:
            npv = pinned.numpy()
            mv = memoryview(npv)
            _t0 = _time.perf_counter()
            got = int(_preadv(fd, [mv], int(data_start) + rel_start))
            _wall = (_time.perf_counter() - _t0) * 1000
            _hm = None
            if i == 0:
                _hm = _region_hash_match(so, header, rel_start, got, mv[:got])
            out_ranges.append({
                "range": int(i),
                "bytes_returned": got,
                "wall_ms": round(_wall, 4),
                "gbps": round(got / (_wall * 1e6) if _wall > 0 else 0.0, 4),
                "hash_match": _hm,
            })
        finally:
            try:
                del pinned
            except Exception:
                pass
            try:
                del npv, mv
            except Exception:
                pass
    # Warm repeat of range 0 (cache-hit signal).
    if out_ranges and out_ranges[0].get("bytes_returned", 0) > 0:
        try:
            _n0 = int(out_ranges[0]["bytes_returned"])
            pinned2 = _t.empty(_n0, dtype=_t.uint8, pin_memory=True)
            try:
                _mv2 = memoryview(pinned2.numpy())
                _t0 = _time.perf_counter()
                _n2 = int(_preadv(fd, [_mv2], int(data_start)))
                _wall2 = (_time.perf_counter() - _t0) * 1000
                _warm = {
                    "wall_ms": round(_wall2, 4),
                    "gbps": round(_n2 / (_wall2 * 1e6) if _wall2 > 0 else 0.0, 4),
                    "bytes_returned": _n2,
                }
            finally:
                try:
                    del pinned2
                except Exception:
                    pass
        except Exception:
            _warm = None
    return {
        "ranges": out_ranges,
        "warm_repeat_wall_ms": _warm["wall_ms"] if _warm else None,
        "warm_repeat_gbps": _warm["gbps"] if _warm else None,
    }


def _probe_i_preadv(model_path, ctx):
    """Direct file -> pinned-buffer reads via os.preadv (single pass, no
    mmap -> pinned memcpy).  Bounded pinned budget: one 256 MiB max buffer,
    sequential, freed between ranges."""
    _preadv = getattr(_os, "preadv", None)
    if not callable(_preadv):
        return {"status": "skipped", "reason": "unavailable: os.preadv"}
    header = ctx.get("header")
    data_start = int(ctx.get("data_start_offset") or -1)
    total_data = int(ctx.get("total_data_bytes") or 0)
    if not header or data_start <= 0:
        return {"status": "skipped", "reason": "header_unavailable"}
    try:
        import safetensors as _st
        _so = _st.safe_open(model_path, framework="pt", device="cpu")
    except Exception:
        return {"status": "skipped", "reason": "unavailable: safetensors"}
    out = {"status": "ok"}
    _fd = None
    try:
        _fd = _os.open(model_path, _os.O_RDONLY)
    except Exception as exc:  # noqa: BLE001
        try:
            _so.close()
        except Exception:
            pass
        return {"status": "error", "error": f"open: {type(exc).__name__}: {str(exc)[:120]}"}
    try:
        for _label, _size in (
            ("preadv_64MiB", _PREADV_64MB),
            ("preadv_128MiB", _PREADV_128MB),
            ("preadv_256MiB", _PREADV_256MB),
        ):
            try:
                _res = _preadv_size_runs(_fd, _so, header, data_start, total_data, _size)
                out[_label] = {"status": "ok", "ranges": _res["ranges"],
                               "warm_repeat_wall_ms": _res["warm_repeat_wall_ms"],
                               "warm_repeat_gbps": _res["warm_repeat_gbps"]}
            except Exception as exc:  # noqa: BLE001
                out[_label] = {"status": "error",
                               "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    finally:
        _safe_open_exit(_so)
        if _fd is not None:
            try:
                _os.close(_fd)
            except Exception:
                pass
    return out


def _query_cuda_attr(fn, attr_id, device=0):
    """cudaDeviceGetAttribute via ctypes c_int byref; None when fn missing."""
    if not callable(fn):
        return None
    import ctypes as _ctypes
    try:
        _val = _ctypes.c_int(0)
        _rc = fn(_ctypes.byref(_val), int(attr_id), int(device))
        return {"rc": int(_rc), "value": int(_val.value)}
    except Exception as exc:  # noqa: BLE001
        return {"rc": -1, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}


def _cudart_error_str(cudart, rc):
    try:
        _f = getattr(cudart, "cudaGetErrorString", None)
        if callable(_f):
            _s = _f(rc)
            if isinstance(_s, (tuple, list)) and _s:
                _s = _s[0]
            if _s:
                return str(_s)
    except Exception:
        pass
    return f"cuda_rc={rc}"


def _is_unsupported(rc):
    try:
        return int(rc) == _CUDA_ERROR_NOT_SUPPORTED
    except Exception:
        return False


def _close_reg(res):
    try:
        del res["src_all"]
    except Exception:
        pass
    try:
        res["mm"].close()
    except Exception:
        pass
    try:
        _os.close(res["fd"])
    except Exception:
        pass


def _open_registered_range(model_path, data_start, data_rel_start, size,
                           cudart, register, flags):
    """Open the file, mmap a page/alignment-aligned window around the target
    data range, and cudaHostRegister the aligned range.  Returns a resource
    dict on success or ``{"error", "rc"}`` on failure (resources closed)."""
    import torch as _t
    import mmap as _mmap
    try:
        _fsize = int(_os.path.getsize(model_path))
    except Exception:
        _fsize = 0
    _target_start = int(data_start) + int(data_rel_start)
    _target_end = min(_target_start + int(size), _fsize)
    if _target_end <= _target_start:
        return {"error": "region_beyond_eof", "rc": -1}
    _a_start, _a_end = page_align_range(_target_start, _target_end, page_size=_PAGE)
    # Platform allocation-granularity fix for the mmap offset/length.
    if _a_start % _MMAP_ALIGN != 0:
        _a_start = (_a_start // _MMAP_ALIGN) * _MMAP_ALIGN
    if _a_end % _MMAP_ALIGN != 0:
        _a_end = ((_a_end + _MMAP_ALIGN - 1) // _MMAP_ALIGN) * _MMAP_ALIGN
    _a_end = min(_a_end, _fsize)
    _mlen = _a_end - _a_start
    if _mlen <= 0:
        return {"error": "aligned_range_empty", "rc": -1}
    _fd = None
    _mm = None
    try:
        _fd = _os.open(model_path, _os.O_RDONLY)
        _mm = _mmap.mmap(_fd, _mlen, access=_mmap.ACCESS_READ, offset=_a_start)
        _src_all = _t.frombuffer(_mm, dtype=_t.uint8)
        _ptr = int(_src_all.data_ptr())
        try:
            _rc = register(_ptr, _mlen, int(flags))
        except Exception as exc:  # noqa: BLE001
            _close_reg({"src_all": _src_all, "mm": _mm, "fd": _fd})
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "rc": -1}
        if int(_rc) != 0:
            _close_reg({"src_all": _src_all, "mm": _mm, "fd": _fd})
            return {"error": _cudart_error_str(cudart, _rc), "rc": int(_rc)}
        return {
            "ok": True,
            "fd": _fd,
            "mm": _mm,
            "src_all": _src_all,
            "ptr": _ptr,
            "mlen": _mlen,
            "src_offset_in_mmap": int(data_start) + int(data_rel_start) - _a_start,
            "region_bytes": _target_end - _target_start,
        }
    except Exception as exc:  # noqa: BLE001
        if _mm is not None:
            try:
                _mm.close()
            except Exception:
                pass
        if _fd is not None:
            try:
                _os.close(_fd)
            except Exception:
                pass
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "rc": -1}


def _reg_h2d_battery(cudart, register, unregister, model_path, data_start,
                     size, flags):
    """Register an aligned range, issue one async H2D copy, unregister.
    Host-issue wall (perf_counter around the copy call) + CUDA-event device
    elapsed.  Resources freed in finally."""
    import torch as _t
    _reg = _open_registered_range(model_path, data_start, 0, size,
                                  cudart, register, flags)
    if "error" in _reg:
        return {
            "status": "unsupported" if _is_unsupported(_reg.get("rc")) else "error",
            "error": _reg["error"],
            "rc": _reg.get("rc"),
            "flags": int(flags),
        }
    out = {
        "status": "ok",
        "flags": int(flags),
        "registered_bytes": int(_reg["mlen"]),
        "region_bytes": int(_reg["region_bytes"]),
    }
    try:
        _off = int(_reg["src_offset_in_mmap"])
        _nb = int(_reg["region_bytes"])
        _src = _reg["src_all"][_off:_off + _nb]
        _dest = _t.empty(_nb, dtype=_t.uint8, device="cuda")
        try:
            _t.cuda.synchronize()
            _ev0 = _t.cuda.Event(enable_timing=True)
            _ev1 = _t.cuda.Event(enable_timing=True)
            _ev0.record()
            _t0 = _time.perf_counter()
            _dest.copy_(_src, non_blocking=True)
            out["h2d_host_issue_wall_ms"] = round((_time.perf_counter() - _t0) * 1000, 4)
            _ev1.record()
            _t.cuda.synchronize()
            _dev = float(_ev0.elapsed_time(_ev1))
            out["h2d_device_ms"] = round(_dev, 4)
            out["h2d_gbps"] = round(_nb / (_dev * 1e6) if _dev > 0 else 0.0, 4)
        finally:
            del _dest
            _empty_cache(_t)
        try:
            _t0 = _time.perf_counter()
            _rc = unregister(_reg["ptr"])
            out["unregister_wall_ms"] = round((_time.perf_counter() - _t0) * 1000, 4)
            out["unregister_rc"] = int(_rc)
        except Exception as exc:  # noqa: BLE001
            out["unregister_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    finally:
        _close_reg(_reg)
    return out


def _reg_bulk_battery(cudart, register, unregister, model_path, data_start,
                      size, flags):
    """Register ~1.5 GiB, issue 64 async ~24 MiB copies into preallocated
    cuda dests (1.5 GiB GPU budget), single sync, unregister."""
    import torch as _t
    _reg = _open_registered_range(model_path, data_start, 0, size,
                                  cudart, register, flags)
    if "error" in _reg:
        return {
            "status": "unsupported" if _is_unsupported(_reg.get("rc")) else "error",
            "error": _reg["error"],
            "rc": _reg.get("rc"),
            "flags": int(flags),
        }
    out = {
        "status": "ok",
        "flags": int(flags),
        "registered_bytes": int(_reg["mlen"]),
        "region_bytes": int(_reg["region_bytes"]),
    }
    _bulk = {"status": "skipped", "reason": "region_too_small"}
    try:
        _avail = int(_reg["region_bytes"])
        _chunk = _BULK_CHUNK_BYTES
        if _avail >= _chunk:
            _dests = []
            try:
                for _ in range(_BULK_CHUNKS):
                    _dests.append(_t.empty(_chunk, dtype=_t.uint8, device="cuda"))
                _t.cuda.synchronize()
                _ev0 = _t.cuda.Event(enable_timing=True)
                _ev1 = _t.cuda.Event(enable_timing=True)
                _per_copy = []
                _base = int(_reg["src_offset_in_mmap"])
                _n_slots = max(1, _avail // _chunk)
                _ev0.record()
                _t0 = _time.perf_counter()
                for _i in range(_BULK_CHUNKS):
                    _slot = _i % _n_slots
                    _src = _reg["src_all"][_base + _slot * _chunk:
                                           _base + (_slot + 1) * _chunk]
                    _tt = _time.perf_counter()
                    _dests[_i].copy_(_src, non_blocking=True)
                    _per_copy.append(round((_time.perf_counter() - _tt) * 1000, 4))
                _issue = (_time.perf_counter() - _t0) * 1000
                _ev1.record()
                _t.cuda.synchronize()
                _dev = float(_ev0.elapsed_time(_ev1))
                _total = _BULK_CHUNKS * _chunk
                _bulk = {
                    "status": "ok",
                    "chunks": _BULK_CHUNKS,
                    "chunk_bytes": int(_chunk),
                    "host_issue_wall_ms": round(_issue, 4),
                    "per_copy_us": [round(_u * 1000, 2) for _u in _per_copy],
                    "device_total_ms": round(_dev, 4),
                    "total_gbps": round(_total / (_dev * 1e6) if _dev > 0 else 0.0, 4),
                }
            finally:
                del _dests
                _empty_cache(_t)
        out["bulk_issue"] = _bulk
        try:
            _rc = unregister(_reg["ptr"])
            out["unregister_rc"] = int(_rc)
        except Exception as exc:  # noqa: BLE001
            out["unregister_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    finally:
        _close_reg(_reg)
    return out


def _probe_i_reg(model_path, ctx):
    """cudaHostRegister battery over mmap'd file ranges.  Skips cleanly when
    CUDA or the cudart fns are unavailable; records unsupported and stops the
    rest of i_reg on cudaErrorNotSupported."""
    import torch as _t
    header = ctx.get("header")
    data_start = int(ctx.get("data_start_offset") or -1)
    if not header or data_start <= 0:
        return {"status": "skipped", "reason": "header_unavailable"}
    if not _t.cuda.is_available():
        return {"status": "skipped", "reason": "unavailable: cuda"}
    try:
        _cudart = _t.cuda.cudart()
    except Exception as exc:  # noqa: BLE001
        return {"status": "skipped",
                "reason": f"unavailable: cudart ({type(exc).__name__})"}
    _register = getattr(_cudart, "cudaHostRegister", None)
    _unregister = getattr(_cudart, "cudaHostUnregister", None)
    if not callable(_register) or not callable(_unregister):
        return {"status": "skipped",
                "reason": "unavailable: cudaHostRegister/cudaHostUnregister"}
    out = {"status": "ok"}
    _getattr_fn = getattr(_cudart, "cudaDeviceGetAttribute", None)
    out["attrs"] = {
        "cudaDevAttrHostRegisterSupported": _query_cuda_attr(_getattr_fn, 99),
        "cudaDevAttrHostRegisterReadOnlySupported": _query_cuda_attr(_getattr_fn, 113),
    }
    _ro_supported = bool((out["attrs"]["cudaDevAttrHostRegisterReadOnlySupported"] or {}).get("value"))
    out["reg_256MiB"] = _reg_h2d_battery(
        _cudart, _register, _unregister, model_path, data_start, _REG_256MB, 0)
    if out["reg_256MiB"].get("status") == "unsupported":
        out["status"] = "unsupported"
        return out
    if _ro_supported:
        out["reg_256MiB_readonly"] = _reg_h2d_battery(
            _cudart, _register, _unregister, model_path, data_start, _REG_256MB, 4)
        if out["reg_256MiB_readonly"].get("status") == "unsupported":
            out["reg_256MiB_readonly"]["note"] = "readonly unsupported; continuing with default"
    else:
        out["reg_256MiB_readonly"] = {
            "status": "skipped",
            "reason": "cudaDevAttrHostRegisterReadOnlySupported=0",
        }
    _flags = 4 if _ro_supported else 0
    out["reg_1.5GiB"] = _reg_bulk_battery(
        _cudart, _register, _unregister, model_path, data_start, _REG_1500MB, _flags)
    if out["reg_1.5GiB"].get("status") == "unsupported":
        out["status"] = "unsupported"
        return out
    return out


def _probe_io(model_path, ctx):
    out = {}
    for _name, _fn in (
        ("i_touch", _probe_i_touch),
        ("i_fadvise", _probe_i_fadvise),
        ("i_preadv", _probe_i_preadv),
        ("i_reg", _probe_i_reg),
    ):
        try:
            out[_name] = _fn(model_path, ctx)
        except Exception as exc:  # noqa: BLE001
            out[_name] = {"status": "error",
                          "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return out


# ── Section 6: summary ────────────────────────────────────────────────────


def _cuda_register_available():
    try:
        import torch as _t
        if not _t.cuda.is_available():
            return False
        _c = _t.cuda.cudart()
        return (callable(getattr(_c, "cudaHostRegister", None))
                and callable(getattr(_c, "cudaHostUnregister", None)))
    except Exception:
        return False


def _max_preadv_gbps(preadv):
    _best = 0.0
    for _label, _entry in (preadv or {}).items():
        if not isinstance(_entry, dict):
            continue
        for _r in _entry.get("ranges", []) or []:
            try:
                _best = max(_best, float(_r.get("gbps") or 0.0))
            except Exception:
                pass
        try:
            _best = max(_best, float(_entry.get("warm_repeat_gbps") or 0.0))
        except Exception:
            pass
    return round(_best, 4)


def _max_reg_gbps(reg):
    _best = 0.0
    for _key in ("reg_256MiB", "reg_256MiB_readonly"):
        _e = (reg or {}).get(_key) or {}
        try:
            _best = max(_best, float(_e.get("h2d_gbps") or 0.0))
        except Exception:
            pass
    _bulk = ((reg or {}).get("reg_1.5GiB") or {}).get("bulk_issue") or {}
    try:
        _best = max(_best, float(_bulk.get("total_gbps") or 0.0))
    except Exception:
        pass
    return round(_best, 4)


def _page_cache_evidence(i_touch):
    for _label, _entry in (i_touch or {}).items():
        if not isinstance(_entry, dict):
            continue
        _f = _entry.get("first_touch_wall_ms")
        _s = _entry.get("second_touch_wall_ms")
        try:
            if _f and _s and float(_f) > 2.0 * float(_s) and float(_f) > 1.0:
                return True
        except Exception:
            continue
    return False


def _build_summary(result):
    _sections = result.get("sections") or {}
    _constr = _sections.get("construction") or {}
    _io = _sections.get("io") or {}
    _c2 = _constr.get("c2_meta") or {}

    def _section_status(_name):
        _sec = _sections.get(_name) or {}
        if isinstance(_sec, dict):
            return _sec.get("status", "unknown")
        return "unknown"

    _io_status = "error"
    if isinstance(_io, dict):
        _statuses = [_e.get("status", "unknown") for _e in _io.values() if isinstance(_e, dict)]
        if _statuses:
            if "error" in _statuses:
                _io_status = "error"
            elif "ok" in _statuses:
                _io_status = "ok"
            elif "skipped" in _statuses:
                _io_status = "skipped"
    _constr_status = "error"
    if isinstance(_constr, dict):
        _c = [_constr.get(k) for k in ("c1_plain", "c2_meta")]
        _statuses = [_e.get("status", "unknown") for _e in _c if isinstance(_e, dict)]
        if "ok" in _statuses:
            _constr_status = "ok"
        elif _statuses and "error" in _statuses:
            _constr_status = "error"
    return {
        "total_wall_ms": round(float(result.get("_wall_ms") or 0.0), 4),
        "per_section_status": {
            "env": _section_status("env"),
            "gds": _section_status("gds"),
            "file": _section_status("file"),
            "construction": _constr_status,
            "io": _io_status,
        },
        "preadv_available": callable(getattr(_os, "preadv", None)),
        "cuda_host_register_available": _cuda_register_available(),
        "meta_construction_ok": bool(
            _c2.get("status") == "ok" and _c2.get("all_params_meta")),
        "sampling_poisoned": bool(_c2.get("meta_tensor_count")),
        "best_preadv_gbps": _max_preadv_gbps(_io.get("i_preadv")),
        "best_registered_h2d_gbps": _max_reg_gbps(_io.get("i_reg")),
        "page_cache_evidence": _page_cache_evidence(_io.get("i_touch")),
    }


def _emit_event(emit, trace, summary):
    _payload = _json_safe(summary)
    if emit is not None and callable(emit):
        try:
            emit("unet_salvage_mechanism_probe", _payload)
            return
        except Exception:
            pass
    if trace is not None:
        _e = getattr(trace, "emit", None)
        if callable(_e):
            try:
                _e("unet_salvage_mechanism_probe", phase="restore", metadata=_payload)
            except Exception:
                pass


# ── B. Orchestrator ───────────────────────────────────────────────────────


def run_unet_mechanism_probes(model_path, trace=None, emit=None):
    """Run the full measurement-only mechanism battery against *model_path*.

    Returns a JSON-safe dict with sections env / gds / file / construction /
    io / summary.  Every sub-probe is individually try/except'd; the function
    never raises.  Ordering note: the construction battery runs first
    (c1_plain, c1_warm, c2_meta, c3_meta_fix, c4_to_empty), then the io
    section warms the page cache (i_touch touches up to ~1.5 GiB of the file
    — the real ZImage weight footprint is ~2 GiB, so the "2 GiB touch" in the
    experiment description is approximated by the bounded i_touch targets),
    then c5_postread re-measures real-device get_model under the warmed page
    cache.  Temp budgets: GPU <= 1.5 GiB, pinned <= 256 MiB sequential,
    registered <= 1.5 GiB.
    """
    _t0 = _time.monotonic()
    _result = {"probe": "unet_salvage_mechanism", "model_path": str(model_path), "status": "ok"}
    _sections = {}
    _ctx = {"path": str(model_path)}

    _mp = _lazy_mp()
    _header = None
    if _mp is not None:
        try:
            _header = _mp._c6_parse_safetensors_header(model_path)
        except Exception:
            _header = None

    for _name, _fn in (
        ("env", lambda: _probe_env()),
        ("gds", lambda: _probe_gds()),
    ):
        try:
            _sections[_name] = _fn()
        except Exception as exc:  # noqa: BLE001
            _sections[_name] = {"status": "error",
                                "error": f"{type(exc).__name__}: {str(exc)[:120]}"}

    try:
        _file_sec = _probe_file(model_path, _header)
    except Exception as exc:  # noqa: BLE001
        _file_sec = {"status": "error",
                     "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    _sections["file"] = _file_sec
    _ctx.update({
        "header": _header,
        "header_bytes": _file_sec.get("header_bytes"),
        "data_start_offset": _file_sec.get("data_start_offset"),
        "total_data_bytes": _file_sec.get("total_data_bytes"),
        "size_bytes": _file_sec.get("size_bytes"),
    })

    _constr_a, _derived = _probe_construction(model_path)
    _sections["construction"] = _constr_a

    _sections["io"] = _probe_io(model_path, _ctx)

    try:
        _sections["construction"]["c5_postread"] = _probe_c5(_derived)
    except Exception as exc:  # noqa: BLE001
        _sections["construction"]["c5_postread"] = {
            "status": "error",
            "wall_ms": 0.0,
            "rss_delta_bytes": None,
            "minflt_delta": None,
            "error": f"{type(exc).__name__}: {str(exc)[:120]}",
        }

    _result["sections"] = _sections
    _result["_wall_ms"] = round((_time.monotonic() - _t0) * 1000, 4)
    try:
        _sections["summary"] = _build_summary(_result)
    except Exception as exc:  # noqa: BLE001
        _sections["summary"] = {
            "status": "error",
            "error": f"{type(exc).__name__}: {str(exc)[:120]}",
            "total_wall_ms": _result.get("_wall_ms"),
        }
    _result.pop("_wall_ms", None)

    _summary = _sections.get("summary") or {}
    _compact = {
        "secs": _summary.get("per_section_status"),
        "preadv": _summary.get("preadv_available"),
        "reg": _summary.get("cuda_host_register_available"),
        "meta_ok": _summary.get("meta_construction_ok"),
        "poisoned": _summary.get("sampling_poisoned"),
        "preadv_gbps": _summary.get("best_preadv_gbps"),
        "reg_gbps": _summary.get("best_registered_h2d_gbps"),
        "pcache": _summary.get("page_cache_evidence"),
        "wall_ms": _summary.get("total_wall_ms"),
    }
    try:
        print("[v2.salvage_probe] summary=" + _json.dumps(
            _json_safe(_compact), separators=(",", ":"), sort_keys=True), flush=True)
    except Exception:
        pass

    _emit_event(emit, trace, _summary)

    return _json_safe(_result)
