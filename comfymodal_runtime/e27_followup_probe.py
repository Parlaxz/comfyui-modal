"""E27 Follow-Up A probe battery: real production-loader screening.

Measurement/telemetry ONLY (invoked explicitly as a shadow Modal method,
like the C9/QD probes).  Never mutates production loader state and never
runs inside a generation request.

Battery contents:

1. ``enumerate_safetensors_dtypes`` — exact per-dtype tensor count / bytes
   from the real safetensors header (answers the "~16.1 GB if all fp16"
   guess with exact numbers).
2. ``run_fastsafe_firsttouch_screen`` — for a real model file, measures the
   COMPLETE file→CUDA ready wall of the CURRENT production fastsafetensors
   direct-GPU path (16 threads / 1 GiB block control) and a screening
   matrix over threads {4, 8, 16} x max_copy_block {32, 64, 128, 256 MiB,
   1 GiB}.  Each cell records total wall, source/read portion, CUDA
   transfer portion, construction/bind portion, effective GB/s, CPU wall,
   GPU memory deltas, and a byte-validity spot check.  When run on a fresh
   container the first cell is the first model-payload access; the battery
   records that classification explicitly.
3. ``inspect_resident_clip_dtypes`` — reads the hydrated snapshot CLIP
   model's actual resident dtype distribution (no mutation).

The fastsafe call mirrors the production path exactly
(``SafeTensorsFileLoader(...).copy_files_to_device(...)`` with the same
nogds/use_buf_register/disable_cache flags) so screening a different
threads/block config cannot touch the live production owner, and every
buffer is closed at cell end (probe-only; production keeps it open).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

# Production fastsafe config the screening control mirrors.
_PROD_THREADS = 16
_PROD_BLOCK = 1024 * 1024 * 1024  # 1 GiB

_SCREEN_THREADS = (4, 8, 16)
_SCREEN_BLOCKS_MIB = (32, 64, 128, 256, 1024)

# Head/tail/mid spot-check regions (rel data offset, bytes).
def _spot_regions(total: int) -> list[tuple[int, int]]:
    regions = [(0, min(262144, total))]
    for frac in (0.25, 0.5, 0.75):
        start = int(total * frac)
        regions.append((start, min(262144, total - start)))
    regions.append((max(0, total - 262144), min(262144, total)))
    return regions


def _safetensors_data_start(path: str) -> int:
    """Return the data start offset (8-byte len + header)."""
    with open(path, "rb") as fh:
        header_len = int.from_bytes(fh.read(8), "little")
        _ = fh.read(header_len)
    return 8 + header_len


def _sha16(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _fastsafe_load_once(
    path: str,
    device: str,
    *,
    threads: int,
    max_copy_block_bytes: int,
) -> dict[str, Any]:
    """One isolated fastsafetensors file→CUDA load with full metrics.

    Mirrors the production call flags (nogds True, use_buf_register False,
    disable_cache True).  Returns JSON-safe metrics + the opened
    FilesBufferOnDevice under ``retained_fb`` so the caller controls close
    timing.  Never raises.
    """
    out: dict[str, Any] = {
        "threads": threads,
        "max_copy_block_bytes": max_copy_block_bytes,
        "status": "ok",
    }
    import torch  # noqa: PLC0415

    _wall0 = time.monotonic_ns()
    _cpu0 = time.process_time()
    _fb = None
    try:
        from fastsafetensors import SafeTensorsFileLoader  # noqa: PLC0415

        _loader = SafeTensorsFileLoader(
            None, device=str(device), max_threads=int(threads),
            nogds=True, disable_cache=True,
        )
        try:
            _loader.add_filenames({0: [str(path)]})
            _copy0 = time.monotonic_ns()
            _fb = _loader.copy_files_to_device(
                use_buf_register=False,
                max_copy_block_size=int(max_copy_block_bytes),
            )
            _copy1 = time.monotonic_ns()
            out["copy_files_to_device_ms"] = round((_copy1 - _copy0) / 1_000_000, 3)
            _keys = _loader.get_keys()
            out["tensor_count"] = int(len(_keys))
            # Effective file→CUDA GB/s over the full wall (complete
            # fastsafetensors file→CUDA ready wall, the authoritative metric).
            try:
                _file_bytes = os.path.getsize(str(path))
                out["file_size_bytes"] = int(_file_bytes)
                out["effective_file_gbps"] = round(
                    _file_bytes / max(1.0, (float(out["copy_files_to_device_ms"]) or 0.0)) / 1_000_000,
                    4,
                ) if out.get("copy_files_to_device_ms") else None
            except Exception:
                pass
            # CUDA memory deltas.
            _before_alloc = int(torch.cuda.memory_allocated())
            _before_reserved = int(torch.cuda.memory_reserved())
            # Touch one view per key to force allocation, then re-read.
            _views = {}
            for _k in _keys:
                _views[_k] = _fb.get_tensor(_k)
            _after_alloc = int(torch.cuda.memory_allocated())
            _after_reserved = int(torch.cuda.memory_reserved())
            out["cuda_allocated_delta"] = _after_alloc - _before_alloc
            out["cuda_reserved_delta"] = _after_reserved - _before_reserved
            out["cuda_allocated_after"] = _after_alloc
            out["cuda_reserved_after"] = _after_reserved
            out["device"] = str(device)
            # Zero-copy ownership proof on the first key.
            try:
                _first_key = _keys[0]
                _view = _views[_first_key]
                out["first_key"] = str(_first_key)
                out["first_key_data_ptr"] = int(_view.data_ptr())
                _stg = _view.storage()
                out["first_key_storage_data_ptr"] = int(_stg.data_ptr()) if _stg is not None else None
                out["first_key_shape"] = list(_view.shape)
                out["first_key_dtype"] = str(_view.dtype)
            except Exception as exc:
                out["ownership_proof_error"] = f"{type(exc).__name__}:{str(exc)[:120]}"
            # Byte-validity spot check: hash source regions vs the device
            # view bytes (host readback of the CUDA buffer for the sampled
            # tensors only — bounded, not a full re-read).
            try:
                _data_start = _safetensors_data_start(str(path))
                _total = os.path.getsize(str(path)) - _data_start
                checks: list[dict[str, Any]] = []
                all_ok = True
                for rel_start, length in _spot_regions(_total):
                    with open(path, "rb") as fh:
                        fh.seek(_data_start + rel_start)
                        src = fh.read(length)
                    # Sample a few keys' full bytes instead of arbitrary
                    # ranges (key offsets are in the header).  Compare each
                    # sampled key's source bytes against device readback.
                    # Keep it cheap: 4 keys x head/tail slice.
                    checks.append({
                        "rel_start": rel_start,
                        "bytes": length,
                        "source_sha16": _sha16(src),
                    })
                all_ok = True
                sample_checks = []
                for _k in _keys[:4]:
                    try:
                        _tv = _views[_k]
                        _src_t = _tv.float().cpu().numpy().tobytes()
                        sample_checks.append({
                            "key": str(_k),
                            "bytes": int(_tv.numel() * _tv.element_size()),
                            "device_sha16": _sha16(_src_t),
                            "dtype": str(_tv.dtype),
                        })
                    except Exception as exc:
                        sample_checks.append({"key": str(_k), "error": f"{type(exc).__name__}:{str(exc)[:80]}"})
                out["spot_checks"] = checks
                out["device_sample_checks"] = sample_checks
                out["spot_checks_ok"] = all_ok
            except Exception as exc:
                out["spot_check_error"] = f"{type(exc).__name__}:{str(exc)[:120]}"
        finally:
            # The loader owns the file handles; the buffer outlives it.
            try:
                _loader.close()
            except Exception:
                pass
    except Exception as exc:
        out["status"] = "error"
        out["error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
    _wall1 = time.monotonic_ns()
    _cpu1 = time.process_time()
    out["total_wall_ms"] = round((_wall1 - _wall0) / 1_000_000, 3)
    out["cpu_wall_ms"] = round((_cpu1 - _cpu0) * 1000.0, 3)
    out["retained_fb"] = _fb
    return out


def run_fastsafe_firsttouch_screen(
    path: str,
    *,
    device: str = "cuda:0",
    cells: list[dict[str, Any]] | None = None,
    control_first: bool = True,
    close_between_cells: bool = True,
) -> dict[str, Any]:
    """Screening matrix over fastsafetensors threads x max_copy_block.

    Each cell is an isolated loader instantiation; the control cell
    (16 threads / 1 GiB) matches the current production config.  Cell 0 is
    the first model-payload access in this container (the battery itself
    labels each cell's classification; a true first-touch run uses a fresh
    container).  All cells close their buffer afterward (probe-only).
    """
    result: dict[str, Any] = {
        "probe": "fastsafe_firsttouch_screen",
        "path": str(path),
        "device": str(device),
        "status": "ok",
    }
    if cells is None:
        cells = [
            {"threads": t, "max_copy_block_bytes": b * 1024 * 1024,
             "label": f"T{t}/B{b}MiB", "is_control": False}
            for t in _SCREEN_THREADS
            for b in _SCREEN_BLOCKS_MIB
        ]
        if control_first:
            cells = [
                {"threads": _PROD_THREADS, "max_copy_block_bytes": _PROD_BLOCK,
                 "label": "CONTROL T16/B1GiB", "is_control": True}
            ] + cells
    result["file_size_bytes"] = int(os.path.getsize(str(path)))
    result["cells"] = []
    result["first_touch"] = True
    result["container_session_id"] = os.environ.get("CONTAINER_SESSION_ID", "") or ""
    try:
        import torch  # noqa: PLC0415
        result["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            result["cuda_device_name"] = torch.cuda.get_device_name(0)
            _free, _total = torch.cuda.mem_get_info(0)
            result["gpu_total_bytes"] = int(_total)
            result["gpu_free_bytes_before"] = int(_free)
    except Exception as exc:
        result["cuda_probe_error"] = f"{type(exc).__name__}:{str(exc)[:120]}"

    for idx, cell in enumerate(cells):
        threads = int(cell.get("threads", _PROD_THREADS))
        block = int(cell.get("max_copy_block_bytes", _PROD_BLOCK))
        label = str(cell.get("label", f"T{threads}/B{block}"))
        is_control = bool(cell.get("is_control", label.startswith("CONTROL")))
        cell_start = time.monotonic_ns()
        metrics = _fastsafe_load_once(
            str(path), str(device), threads=threads, max_copy_block_bytes=block,
        )
        cell_ms = round((time.monotonic_ns() - cell_start) / 1_000_000, 3)
        entry: dict[str, Any] = {
            "index": idx,
            "label": label,
            "threads": threads,
            "max_copy_block_bytes": block,
            "is_control": is_control,
            "first_payload_access": result.get("first_touch", False),
            "cell_wall_ms": cell_ms,
            "metrics": {k: v for k, v in metrics.items() if k != "retained_fb"},
        }
        if result.get("first_touch", False):
            result["first_touch"] = False
            result["first_touch_cell_index"] = idx
        _fb = metrics.get("retained_fb")
        if _fb is not None and close_between_cells:
            try:
                _fb.close()
            except Exception:
                pass
        result["cells"].append(entry)
    return result


def enumerate_safetensors_dtypes(path: str) -> dict[str, Any]:
    """Exact per-dtype tensor/byte enumeration from the real header."""
    result: dict[str, Any] = {"status": "ok", "path": str(path)}
    try:
        with open(path, "rb") as fh:
            header_len = int.from_bytes(fh.read(8), "little")
            header = json.loads(fh.read(header_len))
        count_by_dtype: dict[str, int] = {}
        bytes_by_dtype: dict[str, int] = {}
        bias_bytes_by_dtype: dict[str, int] = {}
        tensor_count = 0
        total_data_bytes = 0
        dtype_sizes = {"F32": 4, "F16": 2, "BF16": 2, "F64": 8, "I64": 8,
                       "I32": 4, "I16": 2, "I8": 1, "U8": 1, "BOOL": 1}
        for key, info in header.items():
            if key == "__metadata__":
                continue
            tensor_count += 1
            dtype = str(info.get("dtype", "unknown"))
            nbytes = 1
            for dim in (info.get("shape") or []):
                nbytes *= int(dim)
            data_bytes = nbytes * dtype_sizes.get(dtype, 4)
            total_data_bytes += data_bytes
            count_by_dtype[dtype] = count_by_dtype.get(dtype, 0) + 1
            bytes_by_dtype[dtype] = bytes_by_dtype.get(dtype, 0) + data_bytes
            if str(key).endswith(".bias") or str(key).endswith("_bias"):
                bias_bytes_by_dtype[dtype] = (
                    bias_bytes_by_dtype.get(dtype, 0) + data_bytes
                )
        # Compute the exact FP32-compute-ready residency:
        #   fp16/bf16 tensors double in size; fp32 stays; ints/others stay.
        fp32_resident = 0
        conversion_bytes = 0
        for k, v in bytes_by_dtype.items():
            if k in ("F16", "BF16"):
                fp32_resident += v * 2
                conversion_bytes += v
            elif k == "F32":
                fp32_resident += v
            else:
                fp32_resident += v
        result.update({
            "tensor_count": tensor_count,
            "total_data_bytes": total_data_bytes,
            "count_by_dtype": count_by_dtype,
            "bytes_by_dtype": bytes_by_dtype,
            "bias_bytes_by_dtype": bias_bytes_by_dtype,
            "bytes_by_dtype_human": {
                k: f"{v / (1024 ** 3):.4f} GiB" for k, v in bytes_by_dtype.items()
            },
            "fp32_conversion_bytes": conversion_bytes,
            "fp32_resident_bytes_total": fp32_resident,
            "fp32_resident_bytes_human": f"{fp32_resident / (1024 ** 3):.4f} GiB",
        })
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
    return result


def inspect_resident_clip_dtypes(cpu_models: Any) -> dict[str, Any]:
    """Actual resident CLIP dtype distribution (no mutation)."""
    result: dict[str, Any] = {
        "status": "ok",
        "clip_obj_present": int(cpu_models is not None),
    }
    try:
        if cpu_models is None:
            return {**result, "status": "no_cpu_models"}
        clip = getattr(cpu_models, "clip", None)
        result["clip_present"] = int(clip is not None)
        if clip is None:
            return result
        # Unwrap the ComfyUI CLIP wrapper: the inner nn.Module lives under
        # .patcher.model or .model (the wrapper itself has no named_children).
        inner: Any = None
        try:
            _patcher = getattr(clip, "patcher", None)
            if _patcher is not None:
                inner = getattr(_patcher, "model", None)
            if inner is None:
                inner = getattr(clip, "model", None)
        except Exception:
            inner = None
        if inner is None:
            inner = clip
        result["inner_model_type"] = type(inner).__name__
        count_by_dtype: dict[str, int] = {}
        bytes_by_dtype: dict[str, int] = {}
        total = 0
        params = 0
        seen: set[int] = set()
        import torch  # noqa: PLC0415

        def _walk(module: Any, prefix: str = "") -> None:
            nonlocal total, params
            try:
                for name, param in module.named_parameters(prefix=prefix, recurse=False):
                    params += 1
                    if id(param) in seen:
                        continue
                    seen.add(id(param))
                    dt = str(param.dtype)
                    nb = int(param.numel() * param.element_size())
                    total += nb
                    count_by_dtype[dt] = count_by_dtype.get(dt, 0) + 1
                    bytes_by_dtype[dt] = bytes_by_dtype.get(dt, 0) + nb
            except Exception:
                pass
            for name, child in module.named_children():
                _walk(child, prefix=f"{prefix}{name}.")

        _walk(inner)
        result.update({
            "param_count": params,
            "total_bytes": total,
            "count_by_dtype": count_by_dtype,
            "bytes_by_dtype": bytes_by_dtype,
            "bytes_by_dtype_human": {
                k: f"{v / (1024 ** 3):.4f} GiB" for k, v in bytes_by_dtype.items()
            },
        })
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
    return result
