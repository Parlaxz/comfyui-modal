"""E16 source-I/O measurements shared by the local tests and Modal endpoint."""

from __future__ import annotations

import gc
import hashlib
import mmap
import os
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, cast

MIB = 1024 * 1024
CURRENT_RANGE = "CURRENT_RANGE"
SOURCE_ORDER = "SEQUENTIAL_SOURCE_ORDER"
MMAP = "MMAP"
TMP_STAGE = "TMP_STAGE"
BLOCK_BYTES = 256 * MIB
RANGE_BYTES = 32 * MIB
PINNED_PROBE_BYTES = 256 * MIB
PINNED_FILL_BYTES = 512 * MIB

_HEADER_BYTES = 8
_DTYPE_ITEMSIZE = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "I16": 2,
    "I32": 4,
    "I64": 8,
    "F16": 2,
    "BF16": 2,
    "F32": 4,
    "F64": 8,
}


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _cpu_ms() -> float:
    return time.process_time() * 1000.0


def _median(values: list[int]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _gbps(byte_count: int, wall_ms: float | None) -> float | None:
    if wall_ms is None or wall_ms <= 0:
        return None
    return round(byte_count / 1e9 / (wall_ms / 1000.0), 3)


def _read_exact(handle: Any, count: int) -> bytes:
    value = handle.read(count)
    if len(value) != count:
        raise ValueError("unexpected EOF")
    return value


def parse_safetensors_header(path: str | Path) -> dict[str, Any]:
    """Parse metadata without hashing or reading tensor payload bytes."""
    path = Path(path)
    size_bytes = path.stat().st_size
    with path.open("rb") as handle:
        header_len = int.from_bytes(_read_exact(handle, _HEADER_BYTES), "little")
        if header_len > (1 << 31) or _HEADER_BYTES + header_len > size_bytes:
            raise ValueError(f"invalid safetensors header length for {path}")
        header = __import__("json").loads(
            _read_exact(handle, header_len).decode("utf-8")
        )
    if not isinstance(header, dict):
        raise ValueError(f"safetensors header is not an object: {path}")
    data_start = _HEADER_BYTES + header_len
    data_bytes = size_bytes - data_start
    tensors: list[dict[str, Any]] = []
    payload_bytes = 0
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"malformed tensor entry: {name}")
        dtype = str(entry.get("dtype", ""))
        shape = entry.get("shape")
        offsets = entry.get("data_offsets")
        if not isinstance(shape, list) or not isinstance(offsets, list) or len(offsets) != 2:
            raise ValueError(f"malformed tensor metadata: {name}")
        try:
            shape = tuple(int(value) for value in shape)
            begin, end = int(offsets[0]), int(offsets[1])
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"malformed tensor metadata: {name}") from exc
        if any(value < 0 for value in shape) or begin < 0 or end < begin or end > data_bytes:
            raise ValueError(f"out-of-bounds tensor metadata: {name}")
        tensor_bytes = end - begin
        payload_bytes += tensor_bytes
        tensors.append({
            "name": str(name),
            "dtype": dtype,
            "shape": list(shape),
            "numel": _numel(shape),
            "rel_begin": begin,
            "rel_end": end,
            "begin": data_start + begin,
            "end": data_start + end,
            "bytes": tensor_bytes,
        })
    tensors.sort(key=lambda item: (item["begin"], item["end"], item["name"]))
    for previous, current in zip(tensors, tensors[1:]):
        if current["begin"] < previous["end"]:
            raise ValueError(f"overlapping tensor metadata: {path}")
    return {
        "path": str(path),
        "filename": path.name,
        "size_bytes": size_bytes,
        "header_bytes": data_start,
        "data_start": data_start,
        "data_bytes": data_bytes,
        "tensors": tensors,
        "tensor_count": len(tensors),
        "tensor_bytes": payload_bytes,
        "gap_bytes": data_bytes - payload_bytes,
    }


def _numel(shape: Iterable[int]) -> int:
    result = 1
    for value in shape:
        result *= int(value)
    return result


def contiguous_regions(manifest: Mapping[str, Any]) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    for tensor in manifest["tensors"]:
        begin, end = int(tensor["begin"]), int(tensor["end"])
        if regions and begin == regions[-1][1]:
            regions[-1] = (regions[-1][0], end)
        else:
            regions.append((begin, end))
    return regions


def manifest_for_path(path: str | Path, role: str) -> dict[str, Any]:
    manifest = parse_safetensors_header(path)
    manifest["role"] = role
    manifest["folder"] = "text_encoders" if role == "CLIP" else "diffusion_models"
    return manifest


def _plan_payload(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(plan.get("restore_plan"), Mapping):
        return plan["restore_plan"]
    return plan


def model_requests_from_plan(plan: Mapping[str, Any]) -> list[dict[str, str]]:
    payload = _plan_payload(plan)
    model_spec = payload.get("model_spec")
    if not isinstance(model_spec, Mapping):
        raise ValueError("model plan has no model_spec")
    loaders = model_spec.get("loaders")
    if not isinstance(loaders, Mapping):
        raise ValueError("model plan has no loaders")
    requests: list[dict[str, str]] = []
    for role, key, field, folder in (
        ("CLIP", "clip", "clip_name", "text_encoders"),
        ("UNET", "unet", "unet_name", "diffusion_models"),
    ):
        values = loaders.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"model plan loader list is invalid: {key}")
        for loader in values:
            if not isinstance(loader, Mapping) or not isinstance(loader.get(field), str):
                raise ValueError(f"model plan loader entry is invalid: {key}")
            filename = str(loader[field])
            if filename:
                requests.append({"role": role, "filename": filename, "folder": folder})
    if not any(item["role"] == "CLIP" for item in requests):
        raise ValueError("model plan resolved no CLIP loader")
    if not any(item["role"] == "UNET" for item in requests):
        raise ValueError("model plan resolved no UNET loader")
    return requests


def _readinto_hash(handle: Any, count: int, digest: Any, read_sizes: list[int]) -> int:
    buffer = bytearray(min(count, BLOCK_BYTES))
    total = 0
    while total < count:
        wanted = min(len(buffer), count - total)
        view = memoryview(buffer)[:wanted]
        read = handle.readinto(view)
        if not read:
            raise IOError("short read")
        digest.update(view[:read])
        read_sizes.append(read)
        total += read
    return total


def _result(arm: str, manifest: Mapping[str, Any], *, status: str = "ok", **fields: Any) -> dict[str, Any]:
    result = {
        "arm": arm,
        "status": status,
        "bytes": int(manifest["tensor_bytes"]),
        "tensor_data_bytes": int(manifest["tensor_bytes"]),
        "data_region_bytes": int(manifest["data_bytes"]),
        "source_bytes_read": None,
        "wall_ms": None,
        "process_cpu_ms": None,
        "effective_GBps": None,
        "read_call_count": None,
        "min_read_bytes": None,
        "median_read_bytes": None,
        "max_read_bytes": None,
        "digest": None,
        "digest_match": None,
        "source_to_pinned_copy_bytes": 0,
        "cache_reset_before": None,
        "error": None,
    }
    result.update(fields)
    return result


def _finish(
    result: dict[str, Any],
    digest: Any,
    expected_digest: str | None,
    read_sizes: list[int],
    source_bytes: int,
    wall_ms: float,
    cpu_ms: float,
) -> dict[str, Any]:
    result.update({
        "source_bytes_read": source_bytes,
        "wall_ms": round(wall_ms, 3),
        "process_cpu_ms": round(cpu_ms, 3),
        "effective_GBps": _gbps(result["bytes"], wall_ms),
        "read_call_count": len(read_sizes),
        "min_read_bytes": min(read_sizes) if read_sizes else None,
        "median_read_bytes": _median(read_sizes),
        "max_read_bytes": max(read_sizes) if read_sizes else None,
        "digest": digest.hexdigest(),
    })
    if expected_digest is not None:
        result["digest_match"] = result["digest"] == expected_digest
    return result


def payload_digest(manifest: Mapping[str, Any]) -> str:
    digest = hashlib.sha256()
    with open(manifest["path"], "rb") as handle:
        for tensor in manifest["tensors"]:
            handle.seek(int(tensor["begin"]))
            remaining = int(tensor["bytes"])
            while remaining:
                chunk = handle.read(min(BLOCK_BYTES, remaining))
                if not chunk:
                    raise IOError("short read while validating payload")
                digest.update(chunk)
                remaining -= len(chunk)
    return digest.hexdigest()


def run_current_range(
    manifest: Mapping[str, Any],
    *,
    expected_digest: str | None,
    range_bytes: int = RANGE_BYTES,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    read_sizes: list[int] = []
    source_bytes = 0
    t0, c0 = _now_ms(), _cpu_ms()
    pread: Any = getattr(os, "pread", None)
    backend = "os.pread" if callable(pread) else "seek/read"
    try:
        for tensor in manifest["tensors"]:
            offset = int(tensor["begin"])
            remaining = int(tensor["bytes"])
            if callable(pread):
                fd = os.open(manifest["path"], os.O_RDONLY)
                try:
                    while remaining:
                        chunk = cast(bytes, pread(fd, min(range_bytes, remaining), offset))
                        if not chunk:
                            raise IOError("short read")
                        digest.update(chunk)
                        read_sizes.append(len(chunk))
                        source_bytes += len(chunk)
                        offset += len(chunk)
                        remaining -= len(chunk)
                finally:
                    os.close(fd)
            else:
                with open(manifest["path"], "rb") as handle:
                    while remaining:
                        handle.seek(offset)
                        chunk = handle.read(min(range_bytes, remaining))
                        if not chunk:
                            raise IOError("short read")
                        digest.update(chunk)
                        read_sizes.append(len(chunk))
                        source_bytes += len(chunk)
                        offset += len(chunk)
                        remaining -= len(chunk)
    except Exception as exc:
        result = _result(CURRENT_RANGE, manifest, status="error", error=str(exc), io_backend=backend)
        return _finish(result, digest, expected_digest, read_sizes, source_bytes, _now_ms() - t0, _cpu_ms() - c0)
    result = _result(CURRENT_RANGE, manifest, io_backend=backend)
    return _finish(result, digest, expected_digest, read_sizes, source_bytes, _now_ms() - t0, _cpu_ms() - c0)


def run_source_order(
    manifest: Mapping[str, Any],
    layout: Any,
    source_order: Any,
    slabs: list[Any],
    *,
    expected_digest: str | None,
    block_bytes: int = BLOCK_BYTES,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    read_sizes: list[int] = []
    source_bytes = 0
    handles: dict[int, Any] = {}
    t0, c0 = _now_ms(), _cpu_ms()
    try:
        for index, block in enumerate(source_order.iter_blocks(layout, block_bytes)):
            handle = handles.get(int(block.file_index))
            if handle is None:
                handle = open(block.file, "rb")
                handles[int(block.file_index)] = handle
            slab = slabs[index % len(slabs)]
            source_order.read_into(handle, slab, int(block.size), int(block.file_offset))
            digest.update(memoryview(slab.numpy())[: int(block.size)])
            read_sizes.append(int(block.size))
            source_bytes += int(block.size)
    except Exception as exc:
        result = _result(SOURCE_ORDER, manifest, status="error", error=str(exc), io_backend="e11.preadv")
        return _finish(result, digest, expected_digest, read_sizes, source_bytes, _now_ms() - t0, _cpu_ms() - c0)
    finally:
        for handle in handles.values():
            handle.close()
    result = _result(SOURCE_ORDER, manifest, io_backend="e11.preadv")
    result["source_order_block_bytes"] = block_bytes
    result["density_gap_bytes"] = int(manifest["gap_bytes"])
    return _finish(result, digest, expected_digest, read_sizes, source_bytes, _now_ms() - t0, _cpu_ms() - c0)


def run_mmap(
    manifest: Mapping[str, Any],
    *,
    expected_digest: str | None,
    block_bytes: int = BLOCK_BYTES,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    read_sizes: list[int] = []
    source_bytes = 0
    t0, c0 = _now_ms(), _cpu_ms()
    mapping = None
    try:
        with open(manifest["path"], "rb") as handle:
            mapping = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        for begin, end in contiguous_regions(manifest):
            offset = begin
            remaining = end - begin
            while remaining:
                count = min(block_bytes, remaining)
                chunk = mapping[offset:offset + count]
                if len(chunk) != count:
                    raise IOError("short mmap read")
                digest.update(chunk)
                read_sizes.append(count)
                source_bytes += count
                offset += count
                remaining -= count
    except Exception as exc:
        result = _result(MMAP, manifest, status="error", error=str(exc))
        return _finish(result, digest, expected_digest, read_sizes, source_bytes, _now_ms() - t0, _cpu_ms() - c0)
    finally:
        if mapping is not None:
            mapping.close()
        gc.collect()
    result = _result(MMAP, manifest, io_backend="mmap")
    result["mmap_block_bytes"] = block_bytes
    return _finish(result, digest, expected_digest, read_sizes, source_bytes, _now_ms() - t0, _cpu_ms() - c0)


def run_tmp_stage(
    manifests: list[Mapping[str, Any]],
    *,
    expected_digest: str | None,
    block_bytes: int = BLOCK_BYTES,
    temp_root: str = "/tmp",
) -> dict[str, Any]:
    stage_dir = Path(tempfile.mkdtemp(prefix="e16_stage_", dir=temp_root))
    digest = hashlib.sha256()
    copy_bytes = 0
    reread_bytes = 0
    copy_sizes: list[int] = []
    reread_sizes: list[int] = []
    try:
        staged: list[Path] = []
        t0, c0 = _now_ms(), _cpu_ms()
        for index, manifest in enumerate(manifests):
            destination = stage_dir / f"{index:02d}_{manifest['filename']}"
            with open(manifest["path"], "rb") as source, destination.open("wb") as target:
                while True:
                    chunk = source.read(8 * MIB)
                    if not chunk:
                        break
                    target.write(chunk)
                    copy_bytes += len(chunk)
                    copy_sizes.append(len(chunk))
            staged.append(destination)
        copy_wall, copy_cpu = _now_ms() - t0, _cpu_ms() - c0
        t1, c1 = _now_ms(), _cpu_ms()
        for manifest, path in zip(manifests, staged):
            with path.open("rb") as handle:
                for begin, end in contiguous_regions(manifest):
                    handle.seek(begin)
                    remaining = end - begin
                    while remaining:
                        chunk = handle.read(min(block_bytes, remaining))
                        if not chunk:
                            raise IOError("short /tmp reread")
                        digest.update(chunk)
                        reread_bytes += len(chunk)
                        reread_sizes.append(len(chunk))
                        remaining -= len(chunk)
        reread_wall, reread_cpu = _now_ms() - t1, _cpu_ms() - c1
        result = _result(
            TMP_STAGE,
            manifests[0] if len(manifests) == 1 else {
                "tensor_bytes": sum(int(item["tensor_bytes"]) for item in manifests),
                "data_bytes": sum(int(item["data_bytes"]) for item in manifests),
            },
            source_bytes_read=copy_bytes,
            wall_ms=round(copy_wall + reread_wall, 3),
            process_cpu_ms=round(copy_cpu + reread_cpu, 3),
            temp_copy_ms=round(copy_wall, 3),
            temp_copy_cpu_ms=round(copy_cpu, 3),
            temp_reread_ms=round(reread_wall, 3),
            temp_reread_cpu_ms=round(reread_cpu, 3),
            combined_ms=round(copy_wall + reread_wall, 3),
            local_reread_bytes=reread_bytes,
            temp_copy_GBps=_gbps(copy_bytes, copy_wall),
            temp_reread_GBps=_gbps(reread_bytes, reread_wall),
            io_backend="copy_then_local_read",
        )
        result["bytes"] = reread_bytes
        result["tensor_data_bytes"] = reread_bytes
        result["effective_GBps"] = _gbps(copy_bytes + reread_bytes, copy_wall + reread_wall)
        result["read_call_count"] = len(copy_sizes) + len(reread_sizes)
        all_sizes = copy_sizes + reread_sizes
        result["min_read_bytes"] = min(all_sizes) if all_sizes else None
        result["median_read_bytes"] = _median(all_sizes)
        result["max_read_bytes"] = max(all_sizes) if all_sizes else None
        result["digest"] = digest.hexdigest()
        result["digest_match"] = expected_digest is None or result["digest"] == expected_digest
        return result
    except Exception as exc:
        return _result(TMP_STAGE, manifests[0], status="error", error=str(exc))
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def run_pinned_fill(
    manifest: Mapping[str, Any],
    torch: Any,
    *,
    block_bytes: int = BLOCK_BYTES,
    max_bytes: int = PINNED_FILL_BYTES,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unsupported",
        "bytes": 0,
        "pageable_fill_ms": None,
        "pinned_fill_ms": None,
        "pinned_fill_overhead_percent": None,
        "host_slab_is_pinned": None,
        "digest_match": None,
        "error": None,
        "read_geometry_bytes": block_bytes,
    }
    try:
        if not bool(torch.cuda.is_available()):
            result["error"] = "torch.cuda.is_available() is false"
            return result
        pinned = torch.empty(block_bytes, dtype=torch.uint8, pin_memory=True)
        result["host_slab_is_pinned"] = bool(pinned.is_pinned())
        if not result["host_slab_is_pinned"]:
            result["error"] = "allocated CPU slab is not pinned"
            return result
        regions = contiguous_regions(manifest)
        selected: list[tuple[int, int]] = []
        remaining = max_bytes
        for begin, end in regions:
            count = min(end - begin, remaining)
            if count:
                selected.append((begin, begin + count))
                remaining -= count
            if remaining <= 0:
                break
        pageable = bytearray(block_bytes)
        pageable_digest = hashlib.sha256()
        t0 = _now_ms()
        for begin, end in selected:
            with open(manifest["path"], "rb") as handle:
                offset, left = begin, end - begin
                while left:
                    count = min(block_bytes, left)
                    handle.seek(offset)
                    chunk = handle.read(count)
                    if len(chunk) != count:
                        raise IOError("short pageable fill read")
                    pageable[:count] = chunk
                    pageable_digest.update(chunk)
                    offset += count
                    left -= count
        pageable_ms = _now_ms() - t0
        pinned_digest = hashlib.sha256()
        t1 = _now_ms()
        for begin, end in selected:
            with open(manifest["path"], "rb") as handle:
                offset, left = begin, end - begin
                while left:
                    count = min(block_bytes, left)
                    handle.seek(offset)
                    chunk = handle.read(count)
                    if len(chunk) != count:
                        raise IOError("short pinned fill read")
                    source = torch.frombuffer(bytearray(chunk), dtype=torch.uint8)
                    pinned[:count].copy_(source)
                    pinned_digest.update(chunk)
                    offset += count
                    left -= count
        pinned_ms = _now_ms() - t1
        result.update({
            "status": "ok",
            "bytes": sum(end - begin for begin, end in selected),
            "pageable_fill_ms": round(pageable_ms, 3),
            "pinned_fill_ms": round(pinned_ms, 3),
            "pinned_fill_overhead_percent": round((pinned_ms / pageable_ms - 1) * 100, 3) if pageable_ms else None,
            "digest": pinned_digest.hexdigest(),
            "digest_match": pinned_digest.hexdigest() == pageable_digest.hexdigest(),
        })
        return result
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result


def inspect_tmp(path: str = "/tmp", required_bytes: int = 0) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        filesystem = "unknown"
        try:
            with open("/proc/mounts", encoding="utf-8") as handle:
                best = ""
                for line in handle:
                    fields = line.split()
                    if len(fields) >= 3 and path.startswith(fields[1]) and len(fields[1]) >= len(best):
                        best = fields[1]
                        filesystem = fields[2]
        except OSError:
            pass
        stat = getattr(os, "statvfs")(path)
        available_bytes = int(stat.f_bavail * stat.f_frsize)
        return {
            "filesystem": filesystem,
            "total_bytes": usage.total,
            "free_bytes": usage.free,
            "available_bytes": available_bytes,
            "required_bytes": required_bytes,
            "headroom_bytes": max(4 * 1024**3, required_bytes // 10),
            "capacity": "PASS" if available_bytes >= required_bytes + max(4 * 1024**3, required_bytes // 10) else "FAIL",
            "runtime_disk_usage_bytes": usage.total - usage.free,
        }
    except Exception as exc:
        return {"capacity": "UNKNOWN", "error": str(exc)}


def inspect_cache_capability(sample_path: str) -> dict[str, Any]:
    result = {
        "posix_fadvise_available": False,
        "posix_fadvise_dontneed": "unsupported",
        "mmap_release": "available",
        "drop_caches_exists": os.path.exists("/proc/sys/vm/drop_caches"),
        "drop_caches_writable": False,
        "capability": "NONE",
    }
    fadvise = getattr(os, "posix_fadvise", None)
    dontneed = getattr(os, "POSIX_FADV_DONTNEED", None)
    if callable(fadvise) and dontneed is not None:
        result["posix_fadvise_available"] = True
        try:
            fd = os.open(sample_path, os.O_RDONLY)
            try:
                fadvise(fd, 0, 0, dontneed)
            finally:
                os.close(fd)
            result["posix_fadvise_dontneed"] = "permitted"
        except Exception as exc:
            result["posix_fadvise_dontneed"] = f"error:{type(exc).__name__}"
    try:
        result["drop_caches_writable"] = os.access("/proc/sys/vm/drop_caches", os.W_OK)
    except OSError:
        pass
    if result["drop_caches_writable"]:
        result["capability"] = "STRONG"
    elif result["posix_fadvise_dontneed"] == "permitted" or result["mmap_release"] == "available":
        result["capability"] = "PARTIAL"
    return result


def reset_file_cache(paths: Iterable[str]) -> dict[str, Any]:
    fadvise = getattr(os, "posix_fadvise", None)
    dontneed = getattr(os, "POSIX_FADV_DONTNEED", None)
    outcome = {"attempted": True, "supported": False, "errors": []}
    if not callable(fadvise) or dontneed is None:
        outcome["errors"].append("posix_fadvise unavailable")
        return outcome
    outcome["supported"] = True
    for path in paths:
        try:
            fd = os.open(path, os.O_RDONLY)
            try:
                fadvise(fd, 0, 0, dontneed)
            finally:
                os.close(fd)
        except Exception as exc:
            outcome["supported"] = False
            outcome["errors"].append(f"{path}:{type(exc).__name__}")
    return outcome


def build_eligibility(manifest: Mapping[str, Any], staged_plan: Any, source_order: Any, torch: Any) -> dict[str, Any]:
    total_tensor_bytes = int(manifest["tensor_bytes"])
    reason_names = (
        "alignment", "dtype", "shape/density", "bounds", "size mismatch",
        "unsupported representation", "other exact reason",
    )
    report = {
        "total": int(manifest["tensor_count"]),
        "direct": 0,
        "fallback": int(manifest["tensor_count"]),
        "eligible_bytes": 0,
        "total_tensor_bytes": total_tensor_bytes,
        "eligible_percent_by_tensor": 0.0,
        "eligible_percent_by_bytes": 0.0,
        "fallback_reasons": {name: {"count": 0, "bytes": 0} for name in reason_names},
        "source_order_eligible": False,
        "staged_plan_fallback_reason": staged_plan.fallback_reason,
    }
    layout = getattr(staged_plan, "source_layout", None)
    specs = getattr(staged_plan, "specs", ())
    if layout is None or not specs:
        reason = "unsupported representation"
        report["fallback_reasons"][reason] = {"count": report["total"], "bytes": total_tensor_bytes}
        return report
    spec_map: dict[Any, dict[str, Any]] = {}
    item_sizes: dict[str, int] = {}
    for checkpoint in getattr(staged_plan, "checkpoints", ()): 
        spec_map[checkpoint] = {"data_start": 0, "file_size": 0, "tensors": {}, "expected_dtypes": {}}
    for file_layout in layout.files:
        spec_map[file_layout.file] = {
            "data_start": int(file_layout.data_start),
            "file_size": int(file_layout.data_start + file_layout.data_bytes),
            "tensors": {},
            "expected_dtypes": {},
        }
    for spec in specs:
        file_spec = spec_map[spec.source_checkpoint]
        itemsize = int(torch.empty((), dtype=spec.output_dtype).element_size())
        item_sizes[spec.name] = itemsize
        file_spec["tensors"][spec.name] = {
            "dtype": spec.source_dtype_name,
            "shape": list(spec.shape),
            "numel": int(spec.nbytes // int(torch.empty((), dtype=spec.output_dtype).element_size())) if spec.output_dtype == spec.source_dtype else int(torch.tensor([], dtype=spec.source_dtype).new_empty(spec.shape).numel()),
            "data_offsets": [
                int(spec.offset - spec.source_data_start),
                int(spec.offset - spec.source_data_start + (spec.source_nbytes or spec.nbytes)),
            ],
        }
        file_spec["expected_dtypes"][spec.name] = spec.source_dtype_name
    eligibility = source_order.assess_eligibility(spec_map, layout, item_sizes)
    specs_by_name = {spec.name: spec for spec in specs}
    for tensor in layout.tensors:
        if tensor.name not in specs_by_name:
            continue
        spec = specs_by_name[tensor.name]
        reason = source_order._tensor_failure(tensor, layout, spec_map, item_sizes)
        source_bytes = int(spec.source_nbytes or spec.nbytes)
        if reason is None:
            report["direct"] += 1
            report["eligible_bytes"] += source_bytes
            continue
        category = {
            "unsafe-alignment": "alignment",
            "invalid-range": "bounds",
            "dtype-mismatch": "dtype",
        }.get(reason, "other exact reason")
        if reason == "dtype-mismatch" and int(tensor.size or 0) != int(tensor.numel) * item_sizes[spec.name]:
            category = "size mismatch"
        entry = report["fallback_reasons"].setdefault(category, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += source_bytes
    report["fallback"] = report["total"] - report["direct"]
    report["eligible_percent_by_tensor"] = round(report["direct"] / report["total"] * 100, 3) if report["total"] else 0.0
    report["eligible_percent_by_bytes"] = round(report["eligible_bytes"] / total_tensor_bytes * 100, 3) if total_tensor_bytes else 0.0
    report["source_order_eligible"] = bool(eligibility.all_direct and staged_plan.source_order_eligible)
    return report


def summarize_arm(arms: Iterable[Mapping[str, Any]], arm_name: str) -> dict[str, Any] | None:
    for arm in arms:
        if arm.get("arm") == arm_name:
            return dict(arm)
    return None
