#!/usr/bin/env python3
"""Source-only safetensors source-I/O benchmark (e14).

Local, standard-library-only harness (plus optional torch/numpy for the
pinned subtest).  Reads the exact safetensors tensor extent byte sequence
with several strategies and compares hashes.  No Modal imports, no network,
no model construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

CURRENT_RANGE = "CURRENT_RANGE"
SEQUENTIAL = "SEQUENTIAL"
TMP_STAGE = "TMP_STAGE"
MMAP = "MMAP"
PREAD = "PREAD"

ALL_ARMS = [CURRENT_RANGE, SEQUENTIAL, TMP_STAGE, MMAP, PREAD]

COPY_BUFSIZE = 8 * 1024 * 1024
_HEADER_BYTES = 8
_IDENTITY_CHUNK = 1 << 20

CACHE_NOTE = (
    "cache_label is a requested process-level label, never a claim of a "
    "disk-cold measurement. Windows cannot drop the page cache, unprivileged "
    "POSIX users cannot drop caches, and fresh Modal containers may still hit "
    "provider-side or distributed-FS caching. Do not infer remote cold-start "
    "or network-FS behavior from these local numbers."
)


def _mib(value: int) -> int:
    return value * 1024 * 1024


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _cpu_ms() -> float:
    return time.process_time() * 1000.0


def _median(values: list) -> Optional[float]:
    if not values:
        return None
    return round(statistics.median(values), 3)


def _gbps_decimal(byte_count: int, milliseconds: Optional[float]) -> Optional[float]:
    if milliseconds is None or milliseconds <= 0:
        return None
    return round(byte_count / 1e9 / (milliseconds / 1000.0), 3)


def _fmt(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{ndigits}f}"
    return str(value)


def _faults() -> tuple:
    try:
        import resource
    except Exception:
        return None, None
    getrusage = getattr(resource, "getrusage", None)
    usage_self = getattr(resource, "RUSAGE_SELF", None)
    if getrusage is None or usage_self is None:
        return None, None
    usage = getrusage(usage_self)
    return getattr(usage, "ru_majflt", None), getattr(usage, "ru_minflt", None)


def _fault_delta(before, after):
    if before is None or after is None:
        return None
    return max(0, after - before)


def _attempt_drop_caches(drop_caches: bool) -> dict:
    if not drop_caches:
        return {"attempted": False, "supported": False, "error": None}
    if os.name == "nt":
        return {
            "attempted": True,
            "supported": False,
            "error": "drop_caches is not supported on Windows; no-op",
        }
    drop_path = "/proc/sys/vm/drop_caches"
    if not os.path.isfile(drop_path):
        return {
            "attempted": True,
            "supported": False,
            "error": "missing /proc/sys/vm/drop_caches",
        }
    try:
        geteuid = getattr(os, "geteuid", None)
        if geteuid is not None and geteuid() != 0:
            return {
                "attempted": True,
                "supported": False,
                "error": "requires root (euid != 0)",
            }
        try:
            subprocess.run(["sync"], check=True, timeout=5)
        except Exception as exc:
            return {
                "attempted": True,
                "supported": False,
                "error": f"sync failed: {exc}",
            }
        with open(drop_path, "w", encoding="ascii") as handle:
            handle.write("1")
    except Exception as exc:
        return {"attempted": True, "supported": False, "error": str(exc)}
    return {"attempted": True, "supported": True, "error": None}


def _collect_files(paths) -> list:
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    found.append((child, False))
        elif path.is_file():
            found.append((path, True))
        else:
            raise ValueError(f"path does not exist: {raw}")
    found.sort(key=lambda pair: str(pair[0]))
    out = []
    seen = set()
    for path, explicit in found:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append((path, explicit))
    return out


def _read_exact(handle, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("unexpected EOF while reading safetensors header")
    return data


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_IDENTITY_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_shard(path: Path) -> dict:
    size_bytes = os.path.getsize(path)
    with open(path, "rb") as handle:
        header_len = int.from_bytes(_read_exact(handle, _HEADER_BYTES), "little", signed=False)
        if header_len > (1 << 31) or _HEADER_BYTES + header_len > size_bytes:
            raise ValueError(
                f"invalid safetensors header length {header_len} for {path}"
            )
        raw_header = _read_exact(handle, header_len)
    try:
        header = json.loads(raw_header.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"not a safetensors JSON header in {path}: {exc}")
    if not isinstance(header, dict):
        raise ValueError(f"safetensors header is not a JSON object in {path}")
    data_bytes = size_bytes - _HEADER_BYTES - header_len
    relative = []
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"malformed tensor entry {name!r} in {path}")
        offsets = entry.get("data_offsets")
        if not (isinstance(offsets, list) and len(offsets) == 2):
            raise ValueError(f"missing data_offsets for {name!r} in {path}")
        begin, end = offsets
        if not (isinstance(begin, int) and isinstance(end, int)):
            raise ValueError(f"non-integer data_offsets for {name!r} in {path}")
        if begin < 0 or end <= begin or end > data_bytes:
            raise ValueError(
                f"out-of-range data_offsets [{begin}, {end}] for {name!r} in "
                f"{path} (data_bytes={data_bytes})"
            )
        relative.append((begin, end, name))
    relative.sort(key=lambda item: (item[0], item[1]))
    for index in range(1, len(relative)):
        prev_begin, prev_end, _ = relative[index - 1]
        cur_begin, cur_end, _ = relative[index]
        if cur_begin < prev_end and not (cur_begin == prev_begin and cur_end == prev_end):
            raise ValueError(
                f"overlapping extents in {path}: [{prev_begin}, {prev_end}) vs "
                f"[{cur_begin}, {cur_end})"
            )
    payload_bytes = sum(end - begin for begin, end, _ in relative)
    abs_extents = [
        (_HEADER_BYTES + header_len + begin, _HEADER_BYTES + header_len + end, name)
        for begin, end, name in relative
    ]
    return {
        "path": str(path),
        "size_bytes": size_bytes,
        "header_len": header_len,
        "data_bytes": data_bytes,
        "extents": abs_extents,
        "payload_bytes": payload_bytes,
        "sha256": _file_sha256(path),
    }


def _payload_sha256(shards: list) -> str:
    digest = hashlib.sha256()
    for shard in shards:
        with open(shard["path"], "rb") as handle:
            for begin, end, _name in shard["extents"]:
                handle.seek(begin)
                remaining = end - begin
                while remaining:
                    chunk = handle.read(min(remaining, _IDENTITY_CHUNK))
                    if not chunk:
                        raise ValueError(f"short read while hashing payload of {shard['path']}")
                    digest.update(chunk)
                    remaining -= len(chunk)
    return digest.hexdigest()


def load_manifest(paths) -> dict:
    """Build a deterministic safetensors manifest from files/directories.

    Extents are absolute byte ranges (8 + header_len + relative offset),
    sorted in physical file order.  Records full size and SHA256 identity
    before any timing happens.
    """
    shards = []
    for path, explicit in _collect_files(paths):
        try:
            shards.append(_parse_shard(path))
        except ValueError as exc:
            if explicit:
                raise
            continue
    if not shards:
        raise ValueError("no valid safetensors files found under the given paths")
    return {
        "shards": shards,
        "files": [shard["path"] for shard in shards],
        "total_size_bytes": sum(shard["size_bytes"] for shard in shards),
        "payload_bytes": sum(shard["payload_bytes"] for shard in shards),
        "expected_payload_sha256": _payload_sha256(shards),
    }


def _iter_extents(manifest):
    for shard in manifest["shards"]:
        for begin, end, _name in shard["extents"]:
            yield shard["path"], begin, end - begin


def _contiguous_regions_of(shard):
    """Yield (begin, end) contiguous tensor-data regions for one shard.

    Extents are merged only when the next absolute begin equals the current
    end (physically adjacent, no gap).  A gap always starts a new region, so
    the concatenated payload byte order is preserved exactly.
    """
    regions = []
    for begin, end, _name in shard["extents"]:
        if regions and begin == regions[-1][1]:
            regions[-1] = (regions[-1][0], end)
        else:
            regions.append((begin, end))
    for begin, end in regions:
        yield begin, end


def _iter_contiguous_regions(manifest):
    """Yield contiguous tensor-data regions per shard.

    Extents are merged into a single region only when the next absolute begin
    equals the current end (i.e. the extents are physically adjacent with no
    gap).  A gap (next begin > current end) always starts a new region, so the
    concatenated payload byte order is preserved exactly.  Each yielded item is
    (path, begin, length) where length is the merged region length.
    """
    for shard in manifest["shards"]:
        for begin, end in _contiguous_regions_of(shard):
            yield shard["path"], begin, end - begin


def _thread_count() -> int:
    """Cheap estimate of the process's active thread count.

    Prefers torch.get_num_threads() when torch is already imported, else
    os.cpu_count(); falls back to 1.  Never forces a torch import.
    """
    if "torch" in sys.modules:
        try:
            import torch
            get_num_threads = getattr(torch, "get_num_threads", None)
            if get_num_threads is not None:
                count = int(get_num_threads())
                if count > 0:
                    return count
        except Exception:
            pass
    try:
        count = os.cpu_count()
        if count:
            return int(count)
    except Exception:
        pass
    return 1


def _safe_basename(path: str) -> str:
    """Basename usable as a staged-file name on the current platform."""
    base = os.path.basename(path) or "shard"
    if os.name == "nt":
        base = base.translate({ord(char): "_" for char in '<>:"/\\|?*'})
        base = base.rstrip(" .") or "shard"
    return base


def _arm_result(arm: str, manifest: dict, cache_label: str, status: str = "ok", **kwargs) -> dict:
    result = {
        "arm": arm,
        "status": status,
        "reason": None,
        "bytes": manifest["payload_bytes"],
        "payload_bytes": manifest["payload_bytes"],
        "source_bytes_read": None,
        "wall_ms": None,
        "process_cpu_ms": None,
        "effective_GBps": None,
        "read_call_count": None,
        "min_read_bytes": None,
        "median_read_bytes": None,
        "max_read_bytes": None,
        "thread_count": _thread_count(),
        "cache_label": cache_label,
        "major_fault_delta": None,
        "minor_fault_delta": None,
        "digest": None,
        "digest_match": None,
        "error": None,
    }
    result.update(kwargs)
    return result


def _unsupported(manifest: dict, arm: str, cache_label: str, reason: str) -> dict:
    return _arm_result(arm, manifest, cache_label, status="unsupported", reason=reason)


def run_current_range(manifest: dict, range_bytes: int, cache_label: str) -> dict:
    """os.pread exact extents in range_bytes chunks, retrying short reads.

    Falls back to a binary file handle with seek/read in the same range-chunk
    geometry when os.pread is unavailable (e.g. Windows), so the arm remains
    runnable instead of reporting unsupported.
    """
    pread = getattr(os, "pread", None)
    backend = "os.pread" if pread is not None else "seek/read"
    digest = hashlib.sha256()
    read_sizes = []
    source_bytes = 0
    calls = 0
    maj0, min0 = _faults()
    t0, c0 = _now_ms(), _cpu_ms()
    try:
        for path, begin, length in _iter_extents(manifest):
            pos = begin
            remaining = length
            if pread is not None:
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                try:
                    while remaining:
                        chunk = pread(fd, min(range_bytes, remaining), pos)
                        if not chunk:
                            raise IOError(f"unexpected EOF reading {path} at {pos}")
                        digest.update(chunk)
                        source_bytes += len(chunk)
                        calls += 1
                        read_sizes.append(len(chunk))
                        pos += len(chunk)
                        remaining -= len(chunk)
                finally:
                    os.close(fd)
            else:
                with open(path, "rb") as handle:
                    while remaining:
                        handle.seek(pos)
                        chunk = handle.read(min(range_bytes, remaining))
                        if not chunk:
                            raise IOError(f"unexpected EOF reading {path} at {pos}")
                        digest.update(chunk)
                        source_bytes += len(chunk)
                        calls += 1
                        read_sizes.append(len(chunk))
                        pos += len(chunk)
                        remaining -= len(chunk)
    except Exception as exc:
        return _arm_result(
            CURRENT_RANGE, manifest, cache_label, status="error", error=str(exc),
            digest=digest.hexdigest(), digest_match=False,
            source_bytes_read=source_bytes, read_call_count=calls,
            wall_ms=_now_ms() - t0, process_cpu_ms=_cpu_ms() - c0,
            io_backend=backend,
        )
    wall, cpu = _now_ms() - t0, _cpu_ms() - c0
    maj1, min1 = _faults()
    dg = digest.hexdigest()
    return _arm_result(
        CURRENT_RANGE, manifest, cache_label,
        source_bytes_read=source_bytes, wall_ms=wall, process_cpu_ms=cpu,
        effective_GBps=_gbps_decimal(manifest["payload_bytes"], wall),
        read_call_count=calls,
        min_read_bytes=min(read_sizes) if read_sizes else None,
        median_read_bytes=_median(read_sizes),
        max_read_bytes=max(read_sizes) if read_sizes else None,
        major_fault_delta=_fault_delta(maj0, maj1),
        minor_fault_delta=_fault_delta(min0, min1),
        digest=dg, digest_match=dg == manifest["expected_payload_sha256"],
        io_backend=backend,
    )


def run_sequential(manifest: dict, block_bytes: int, cache_label: str) -> dict:
    """Buffered file reads over exact tensor regions in block_bytes chunks.

    Never reads header, gaps, or trailing bytes.
    """
    digest = hashlib.sha256()
    read_sizes = []
    source_bytes = 0
    calls = 0
    maj0, min0 = _faults()
    t0, c0 = _now_ms(), _cpu_ms()
    try:
        for path, begin, length in _iter_contiguous_regions(manifest):
            with open(path, "rb") as handle:
                pos = begin
                remaining = length
                handle.seek(pos)
                while remaining:
                    chunk = handle.read(min(block_bytes, remaining))
                    if not chunk:
                        raise IOError(f"unexpected EOF reading {path} at {pos}")
                    digest.update(chunk)
                    source_bytes += len(chunk)
                    calls += 1
                    read_sizes.append(len(chunk))
                    pos += len(chunk)
                    remaining -= len(chunk)
    except Exception as exc:
        return _arm_result(
            SEQUENTIAL, manifest, cache_label, status="error", error=str(exc),
            digest=digest.hexdigest(), digest_match=False,
            source_bytes_read=source_bytes, read_call_count=calls,
            wall_ms=_now_ms() - t0, process_cpu_ms=_cpu_ms() - c0,
        )
    wall, cpu = _now_ms() - t0, _cpu_ms() - c0
    maj1, min1 = _faults()
    dg = digest.hexdigest()
    return _arm_result(
        SEQUENTIAL, manifest, cache_label,
        source_bytes_read=source_bytes, wall_ms=wall, process_cpu_ms=cpu,
        effective_GBps=_gbps_decimal(manifest["payload_bytes"], wall),
        read_call_count=calls,
        min_read_bytes=min(read_sizes) if read_sizes else None,
        median_read_bytes=_median(read_sizes),
        max_read_bytes=max(read_sizes) if read_sizes else None,
        major_fault_delta=_fault_delta(maj0, maj1),
        minor_fault_delta=_fault_delta(min0, min1),
        digest=dg, digest_match=dg == manifest["expected_payload_sha256"],
    )


def run_mmap(manifest: dict, block_bytes: int, cache_label: str) -> dict:
    """Sequentially hash exact extents through a read-only mmap."""
    digest = hashlib.sha256()
    read_sizes = []
    source_bytes = 0
    calls = 0
    maj0, min0 = _faults()
    t0, c0 = _now_ms(), _cpu_ms()
    try:
        for shard in manifest["shards"]:
            fd = os.open(shard["path"], os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                mapping = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
            finally:
                os.close(fd)
            try:
                for begin, end in _contiguous_regions_of(shard):
                    pos = begin
                    remaining = end - begin
                    while remaining:
                        count = min(block_bytes, remaining)
                        chunk = mapping[pos:pos + count]
                        if len(chunk) != count:
                            raise IOError(
                                f"short mmap read at {pos} of {shard['path']}: "
                                f"expected {count} bytes, got {len(chunk)}"
                            )
                        digest.update(chunk)
                        source_bytes += len(chunk)
                        calls += 1
                        read_sizes.append(len(chunk))
                        pos += count
                        remaining -= count
            finally:
                mapping.close()
    except Exception as exc:
        return _arm_result(
            MMAP, manifest, cache_label, status="error", error=str(exc),
            digest=digest.hexdigest(), digest_match=False,
            source_bytes_read=source_bytes, read_call_count=calls,
            wall_ms=_now_ms() - t0, process_cpu_ms=_cpu_ms() - c0,
        )
    wall, cpu = _now_ms() - t0, _cpu_ms() - c0
    maj1, min1 = _faults()
    dg = digest.hexdigest()
    return _arm_result(
        MMAP, manifest, cache_label,
        source_bytes_read=source_bytes, wall_ms=wall, process_cpu_ms=cpu,
        effective_GBps=_gbps_decimal(manifest["payload_bytes"], wall),
        read_call_count=calls,
        min_read_bytes=min(read_sizes) if read_sizes else None,
        median_read_bytes=_median(read_sizes),
        max_read_bytes=max(read_sizes) if read_sizes else None,
        major_fault_delta=_fault_delta(maj0, maj1),
        minor_fault_delta=_fault_delta(min0, min1),
        digest=dg, digest_match=dg == manifest["expected_payload_sha256"],
    )


def run_tmp_stage(
    manifest: dict,
    block_bytes: int,
    cache_label: str,
    keep_temp: bool = False,
    temp_dir: Optional[str] = None,
) -> dict:
    """Copy full source files to a temp dir, then reread exact extents there.

    temp_dir, when given, is the parent directory used for the staging dir
    (tempfile.mkdtemp dir=...).  Staged destinations get an index prefix so
    multiple files sharing a basename cannot collide; the copy/reread loops
    share the same mapping.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="src_io_e14_", dir=temp_dir))
    try:
        digest = hashlib.sha256()
        copy_sizes = []
        copied_bytes = 0
        copy_calls = 0
        staged = {}
        for index, shard in enumerate(manifest["shards"]):
            staged[shard["path"]] = tmp_dir / f"{index:05d}_{_safe_basename(shard['path'])}"
        t0, c0 = _now_ms(), _cpu_ms()
        for shard in manifest["shards"]:
            dst = staged[shard["path"]]
            with open(shard["path"], "rb") as src, open(dst, "wb") as out:
                while True:
                    chunk = src.read(COPY_BUFSIZE)
                    if not chunk:
                        break
                    out.write(chunk)
                    copied_bytes += len(chunk)
                    copy_calls += 1
                    copy_sizes.append(len(chunk))
        copy_wall, copy_cpu = _now_ms() - t0, _cpu_ms() - c0
        reread_sizes = []
        reread_bytes = 0
        reread_calls = 0
        t1, c1 = _now_ms(), _cpu_ms()
        for shard in manifest["shards"]:
            dst = staged[shard["path"]]
            with open(dst, "rb") as handle:
                for begin, end in _contiguous_regions_of(shard):
                    pos = begin
                    remaining = end - begin
                    handle.seek(pos)
                    while remaining:
                        chunk = handle.read(min(block_bytes, remaining))
                        if not chunk:
                            raise IOError(f"unexpected EOF rereading {dst} at {pos}")
                        digest.update(chunk)
                        reread_bytes += len(chunk)
                        reread_calls += 1
                        reread_sizes.append(len(chunk))
                        pos += len(chunk)
                        remaining -= len(chunk)
        reread_wall, reread_cpu = _now_ms() - t1, _cpu_ms() - c1
        combined_wall = copy_wall + reread_wall
        combined_cpu = copy_cpu + reread_cpu
        all_sizes = copy_sizes + reread_sizes
        dg = digest.hexdigest()
        return _arm_result(
            TMP_STAGE, manifest, cache_label,
            source_bytes_read=copied_bytes,
            wall_ms=combined_wall, process_cpu_ms=combined_cpu,
            effective_GBps=_gbps_decimal(copied_bytes + reread_bytes, combined_wall),
            read_call_count=copy_calls + reread_calls,
            min_read_bytes=min(all_sizes) if all_sizes else None,
            median_read_bytes=_median(all_sizes),
            max_read_bytes=max(all_sizes) if all_sizes else None,
            digest=dg, digest_match=dg == manifest["expected_payload_sha256"],
            temp_copy_ms=copy_wall, temp_copy_cpu_ms=copy_cpu,
            temp_reread_ms=reread_wall, temp_reread_cpu_ms=reread_cpu,
            combined_ms=combined_wall, local_reread_bytes=reread_bytes,
            temp_copy_GBps=_gbps_decimal(copied_bytes, copy_wall),
            temp_reread_GBps=_gbps_decimal(reread_bytes, reread_wall),
            temp_dir=str(tmp_dir) if keep_temp else None,
        )
    except Exception as exc:
        return _arm_result(TMP_STAGE, manifest, cache_label, status="error", error=str(exc))
    finally:
        if not keep_temp:
            shutil.rmtree(tmp_dir, ignore_errors=True)


_PREAD_API_NAMES = ("pread", "read_range")


def _find_safetensors_pread():
    """Return (name, callable) for an explicitly public safetensors pread API.

    Only an exact, public attribute on the top-level public ``safetensors``
    module is considered.  We never scan arbitrary callable names inside
    imported submodules, and we never guess signature permutations beyond the
    single documented (path, offset, length) call.  If no such public API
    exists, return None (callers report UNSUPPORTED).
    """
    try:
        import safetensors
    except Exception:
        return None
    for name in _PREAD_API_NAMES:
        value = getattr(safetensors, name, None)
        if callable(value):
            return f"safetensors.{name}", value
    return None


def _call_pread(fn, path: str, offset: int, length: int) -> Optional[bytes]:
    """Call the documented (path, offset, length) pread signature exactly once."""
    try:
        result = fn(path, offset, length)
    except TypeError:
        return None
    return result if isinstance(result, bytes) else None


def run_pread(manifest: dict, range_bytes: int, cache_label: str) -> dict:
    """UNSUPPORTED unless a clearly public installed safetensors pread API exists."""
    probe = _find_safetensors_pread()
    if probe is None:
        return _unsupported(
            manifest,
            PREAD,
            cache_label,
            "no public installed safetensors pread API is callable; refusing to "
            "fake it with safe_open/get_tensor or monkeypatching",
        )
    name, fn = probe
    digest = hashlib.sha256()
    read_sizes = []
    source_bytes = 0
    calls = 0
    maj0, min0 = _faults()
    t0, c0 = _now_ms(), _cpu_ms()
    try:
        for path, begin, length in _iter_extents(manifest):
            pos = begin
            remaining = length
            while remaining:
                chunk = _call_pread(fn, path, pos, min(range_bytes, remaining))
                if chunk is None:
                    return _unsupported(
                        manifest, PREAD, cache_label,
                        f"{name} is callable but rejected our (path, offset, length) "
                        "signature; refusing to guess further",
                    )
                if not chunk:
                    raise IOError(f"unexpected EOF from {name} reading {path} at {pos}")
                digest.update(chunk)
                source_bytes += len(chunk)
                calls += 1
                read_sizes.append(len(chunk))
                pos += len(chunk)
                remaining -= len(chunk)
    except Exception as exc:
        return _arm_result(
            PREAD, manifest, cache_label, status="error", error=str(exc),
            digest=digest.hexdigest(), digest_match=False,
            source_bytes_read=source_bytes, read_call_count=calls,
            wall_ms=_now_ms() - t0, process_cpu_ms=_cpu_ms() - c0,
        )
    wall, cpu = _now_ms() - t0, _cpu_ms() - c0
    maj1, min1 = _faults()
    dg = digest.hexdigest()
    return _arm_result(
        PREAD, manifest, cache_label,
        source_bytes_read=source_bytes, wall_ms=wall, process_cpu_ms=cpu,
        effective_GBps=_gbps_decimal(manifest["payload_bytes"], wall),
        read_call_count=calls,
        min_read_bytes=min(read_sizes) if read_sizes else None,
        median_read_bytes=_median(read_sizes),
        max_read_bytes=max(read_sizes) if read_sizes else None,
        major_fault_delta=_fault_delta(maj0, maj1),
        minor_fault_delta=_fault_delta(min0, min1),
        digest=dg, digest_match=dg == manifest["expected_payload_sha256"],
        pread_api=name,
    )


def run_pinned_subtest(manifest: dict, block_bytes: int) -> dict:
    """Optional: pageable bytearray vs pinned CPU torch slab fills. No H2D.

    Memory-bounded: allocates one pageable bytearray and one pinned torch slab
    of at most block_bytes each, then processes the exact extents in chunks and
    reports the same total bytes.  The pinned slab is filled through a
    PyTorch-native CPU path (torch.frombuffer over a writable bytearray chunk,
    then a bounded pinned[:count].copy_(source_tensor)) that works on
    CUDA-enabled PyTorch builds; no H2D and no numpy required.
    """
    result = {
        "arm": "PINNED_SUBTEST",
        "status": "unsupported",
        "reason": None,
        "bytes": manifest["payload_bytes"],
        "payload_bytes": manifest["payload_bytes"],
        "pageable_fill_wall_ms": None,
        "pageable_fill_cpu_ms": None,
        "pinned_fill_wall_ms": None,
        "pinned_fill_cpu_ms": None,
        "overhead_ratio": None,
        "thread_count": None,
        "cuda_available": None,
        "digest": None,
        "digest_match": None,
        "error": None,
    }
    try:
        import torch
    except Exception as exc:
        result["reason"] = f"torch not importable: {exc}"
        result["cuda_available"] = False
        return result
    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception as exc:
        result["reason"] = f"torch.cuda.is_available() raised: {exc}"
        result["cuda_available"] = False
        return result
    result["cuda_available"] = cuda_available
    if not cuda_available:
        result["reason"] = (
            "pinned subtest requires a CUDA-capable device "
            "(torch.cuda.is_available() is False); refusing to run without it"
        )
        return result
    torch_empty = getattr(torch, "empty", None)
    torch_uint8 = getattr(torch, "uint8", None)
    torch_frombuffer = getattr(torch, "frombuffer", None)
    get_num_threads = getattr(torch, "get_num_threads", None)
    if torch_empty is None or torch_uint8 is None or torch_frombuffer is None:
        result["reason"] = (
            "torch does not expose empty/uint8/frombuffer; the pinned subtest "
            "requires torch.frombuffer for a PyTorch-native CPU buffer path"
        )
        return result
    if block_bytes <= 0:
        result["reason"] = "block_bytes must be positive for the pinned subtest"
        return result
    result["thread_count"] = int(get_num_threads()) if get_num_threads is not None else 1
    try:
        pageable = bytearray(block_bytes)
        pinned = torch_empty(block_bytes, dtype=torch_uint8, pin_memory=True)
    except Exception as exc:
        result["reason"] = f"cannot allocate pageable/pinned buffers: {exc}"
        return result
    try:
        pageable_view = memoryview(pageable)
        pageable_digest = hashlib.sha256()
        t0, c0 = _now_ms(), _cpu_ms()
        filled = 0
        for path, begin, length in _iter_contiguous_regions(manifest):
            with open(path, "rb") as handle:
                pos = begin
                remaining = length
                while remaining:
                    count = min(block_bytes, remaining)
                    handle.seek(pos)
                    chunk = handle.read(count)
                    if len(chunk) != count:
                        raise IOError(f"short read {path} at {pos}")
                    pageable_view[:count] = chunk
                    pageable_digest.update(chunk)
                    filled += count
                    pos += count
                    remaining -= count
        pageable_wall, pageable_cpu = _now_ms() - t0, _cpu_ms() - c0
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    try:
        pinned_digest = hashlib.sha256()
        t0, c0 = _now_ms(), _cpu_ms()
        filled = 0
        for path, begin, length in _iter_contiguous_regions(manifest):
            with open(path, "rb") as handle:
                pos = begin
                remaining = length
                while remaining:
                    count = min(block_bytes, remaining)
                    handle.seek(pos)
                    chunk = handle.read(count)
                    if len(chunk) != count:
                        raise IOError(f"short read {path} at {pos}")
                    source_tensor = torch_frombuffer(bytearray(chunk), dtype=torch_uint8)
                    pinned[:count].copy_(source_tensor)
                    pinned_digest.update(chunk)
                    filled += count
                    pos += count
                    remaining -= count
        pinned_wall, pinned_cpu = _now_ms() - t0, _cpu_ms() - c0
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    result["status"] = "ok"
    result["pageable_fill_wall_ms"] = pageable_wall
    result["pageable_fill_cpu_ms"] = pageable_cpu
    result["pinned_fill_wall_ms"] = pinned_wall
    result["pinned_fill_cpu_ms"] = pinned_cpu
    result["overhead_ratio"] = round(pinned_wall / pageable_wall, 3) if pageable_wall > 0 else None
    dg = pinned_digest.hexdigest()
    result["digest"] = dg
    result["digest_match"] = dg == manifest["expected_payload_sha256"]
    return result


def run_benchmark(
    manifest: dict,
    arms: Optional[list] = None,
    block_mib: int = 256,
    range_mib: int = 32,
    cache_label: str = "cold_unknown",
    drop_caches: bool = False,
    pinned_subtest: bool = False,
    keep_temp: bool = False,
    temp_dir: Optional[str] = None,
) -> dict:
    block_bytes = _mib(block_mib)
    range_bytes = _mib(range_mib)
    if arms is None:
        arms = list(ALL_ARMS)
    invalid = [arm for arm in arms if arm not in ALL_ARMS]
    if invalid:
        raise ValueError(f"unknown arms: {invalid}")
    if drop_caches and cache_label == "page_cache_warm":
        raise ValueError(
            "contradictory configuration: cache_label='page_cache_warm' with "
            "drop_caches=True. Dropping the page cache cannot produce a warm "
            "page-cache result; refusing to claim a disk-cold measurement."
        )
    drop_attempts = []
    arm_results = []
    for arm in arms:
        drop = _attempt_drop_caches(drop_caches)
        drop_attempts.append(drop)
        if arm == CURRENT_RANGE:
            arm_results.append(run_current_range(manifest, range_bytes, cache_label))
        elif arm == SEQUENTIAL:
            arm_results.append(run_sequential(manifest, block_bytes, cache_label))
        elif arm == TMP_STAGE:
            arm_results.append(run_tmp_stage(
                manifest, block_bytes, cache_label,
                keep_temp=keep_temp, temp_dir=temp_dir,
            ))
        elif arm == MMAP:
            arm_results.append(run_mmap(manifest, block_bytes, cache_label))
        elif arm == PREAD:
            arm_results.append(run_pread(manifest, range_bytes, cache_label))
        arm_results[-1]["cache_drop_before_arm"] = drop
    drop_attempted = any(d["attempted"] for d in drop_attempts)
    drop_supported = any(d["supported"] for d in drop_attempts)
    drop_errors = [d["error"] for d in drop_attempts if d["error"]]
    cache_meta = {
        "cache_semantics": cache_label,
        "requested": cache_label,
        "drop_attempted": drop_attempted,
        "drop_supported": drop_supported,
        "drop_error": drop_errors[0] if drop_errors else None,
        "drop_attempts": drop_attempts,
        "note": CACHE_NOTE,
    }
    return {
        "tool": "benchmark_source_io_e14",
        "platform": {
            "os": os.name,
            "python": sys.version.split()[0],
            "machine": getattr(platform, "machine", lambda: "unknown")(),
        },
        "config": {
            "arms": list(arms),
            "block_mib": block_mib,
            "range_mib": range_mib,
            "cache_label": cache_label,
            "pinned_subtest": pinned_subtest,
            "keep_temp": keep_temp,
            "temp_dir": temp_dir,
        },
        "manifest": {
            "files": manifest["files"],
            "total_size_bytes": manifest["total_size_bytes"],
            "payload_bytes": manifest["payload_bytes"],
            "expected_payload_sha256": manifest["expected_payload_sha256"],
            "shards": [
                {
                    "path": shard["path"],
                    "size_bytes": shard["size_bytes"],
                    "payload_bytes": shard["payload_bytes"],
                    "sha256": shard["sha256"],
                }
                for shard in manifest["shards"]
            ],
        },
        "cache": cache_meta,
        "arms": arm_results,
        "pinned_subtest": run_pinned_subtest(manifest, block_bytes) if pinned_subtest else None,
    }


def _print_summary(results: dict) -> None:
    manifest = results["manifest"]
    print(
        f"source io benchmark (e14): {len(manifest['files'])} file(s), "
        f"payload {manifest['payload_bytes'] / (1024 * 1024):.3f} MiB"
    )
    for arm in results["arms"]:
        if arm["status"] == "ok":
            print(
                f"  {arm['arm']:<14} ok   "
                f"{_fmt(arm['effective_GBps']):>8} GBps  "
                f"{_fmt(arm['wall_ms'], 1):>10} ms wall  "
                f"{arm['source_bytes_read']} src bytes  "
                f"digest_match={arm['digest_match']}"
            )
        else:
            detail = arm.get("reason") or arm.get("error") or ""
            print(f"  {arm['arm']:<14} {arm['status']:<11} {detail}")
    if results.get("pinned_subtest") is not None:
        sub = results["pinned_subtest"]
        if sub["status"] == "ok":
            print(
                f"  pinned subtest ok: pageable={_fmt(sub['pageable_fill_wall_ms'], 1)} ms "
                f"pinned={_fmt(sub['pinned_fill_wall_ms'], 1)} ms "
                f"overhead_ratio={_fmt(sub['overhead_ratio'])}"
            )
        else:
            detail = sub.get("reason") or sub.get("error") or ""
            print(f"  pinned subtest {sub['status']}: {detail}")
    cache = results["cache"]
    if cache["drop_attempted"]:
        print(
            f"  cache drop: attempted={cache['drop_attempted']} "
            f"supported={cache['drop_supported']} error={cache['drop_error']}"
        )
    print(f"  cache note: {cache['note']}")
    for arm in results["arms"]:
        if arm["arm"] == TMP_STAGE and arm["status"] == "ok" and arm.get("temp_dir"):
            print(f"  temp dir kept: {arm['temp_dir']}")


def render_markdown(results: dict) -> str:
    lines = []
    lines.append("# Source I/O benchmark (e14)")
    lines.append("")
    lines.append(
        "Local, source-only safetensors read benchmark. No Modal, no network, "
        "no model construction."
    )
    lines.append("")
    lines.append("## Run metadata")
    plat = results["platform"]
    config = results["config"]
    lines.append(f"- os={plat['os']} python={plat['python']} machine={plat['machine']}")
    lines.append(f"- arms: {', '.join(config['arms'])}")
    lines.append(
        f"- block_mib={config['block_mib']} range_mib={config['range_mib']} "
        f"cache_label={config['cache_label']} pinned_subtest={config['pinned_subtest']}"
    )
    lines.append("")
    lines.append("## Manifest")
    manifest = results["manifest"]
    for shard in manifest["shards"]:
        lines.append(
            f"- `{shard['path']}` size={shard['size_bytes']} "
            f"payload={shard['payload_bytes']} sha256={shard['sha256']}"
        )
    lines.append(
        f"- total size={manifest['total_size_bytes']} "
        f"payload={manifest['payload_bytes']} "
        f"expected_payload_sha256={manifest['expected_payload_sha256']}"
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| arm | status | payload_bytes | source_bytes_read | wall_ms | cpu_ms | "
        "effective_GBps | calls | min/med/max read | digest_match |"
    )
    lines.append(
        "|-----|--------|---------------|-------------------|---------|--------|"
        "---------------|-------|------------------|--------------|"
    )
    for arm in results["arms"]:
        if arm["status"] == "ok":
            read_b = f"{arm['min_read_bytes']}/{arm['median_read_bytes']}/{arm['max_read_bytes']}"
            lines.append(
                f"| {arm['arm']} | {arm['status']} | {arm['payload_bytes']} | "
                f"{arm['source_bytes_read']} | {_fmt(arm['wall_ms'], 1)} | "
                f"{_fmt(arm['process_cpu_ms'], 1)} | {_fmt(arm['effective_GBps'])} | "
                f"{arm['read_call_count']} | {read_b} | {arm['digest_match']} |"
            )
        else:
            detail = (arm.get("reason") or arm.get("error") or "").replace("|", "/")
            lines.append(f"| {arm['arm']} | {arm['status']} | - | - | - | - | - | - | - | - |")
            lines.append(f"| {arm['arm']} detail | {detail} | | | | | | | | |")
    lines.append("")
    tmp_rows = [arm for arm in results["arms"] if arm["arm"] == TMP_STAGE and arm["status"] == "ok"]
    if tmp_rows:
        lines.append("### TMP_STAGE breakdown")
        lines.append("")
        lines.append("| temp_copy_ms | temp_reread_ms | combined_ms | local_reread_bytes |")
        lines.append("|--------------|----------------|-------------|--------------------|")
        for arm in tmp_rows:
            lines.append(
                f"| {_fmt(arm['temp_copy_ms'], 1)} | {_fmt(arm['temp_reread_ms'], 1)} | "
                f"{_fmt(arm['combined_ms'], 1)} | {arm['local_reread_bytes']} |"
            )
        lines.append("")
    sub = results.get("pinned_subtest")
    if sub is not None:
        lines.append("## Pinned subtest (CPU only, no H2D)")
        lines.append("")
        if sub["status"] == "ok":
            lines.append(
                f"- pageable fill: {_fmt(sub['pageable_fill_wall_ms'], 1)} ms wall / "
                f"{_fmt(sub['pageable_fill_cpu_ms'], 1)} ms cpu"
            )
            lines.append(
                f"- pinned fill: {_fmt(sub['pinned_fill_wall_ms'], 1)} ms wall / "
                f"{_fmt(sub['pinned_fill_cpu_ms'], 1)} ms cpu"
            )
            lines.append(f"- bytes filled: {sub['bytes']}")
            lines.append(f"- overhead ratio (pinned/pageable): {_fmt(sub['overhead_ratio'])}")
            lines.append(f"- torch threads: {sub['thread_count']}")
        else:
            detail = sub.get("reason") or sub.get("error") or ""
            lines.append(f"- status: {sub['status']} ({detail})")
        lines.append("")
    cache = results["cache"]
    lines.append("## Cache semantics")
    lines.append("")
    lines.append(
        f"- requested label: {cache['requested']} "
        f"(cache_semantics={cache['cache_semantics']})"
    )
    lines.append(
        f"- drop_caches: attempted={cache['drop_attempted']} "
        f"supported={cache['drop_supported']} error={_fmt(cache['drop_error'])}"
    )
    lines.append(f"- note: {cache['note']}")
    lines.append("")
    lines.append("## Local observations vs remote conclusions")
    lines.append("")
    lines.append("**Local observations (measured here):**")
    lines.append("- wall/cpu times, read call counts, read size distributions, and page-fault deltas.")
    lines.append("- SHA256 digest and digest_match across arms for the identical concatenated extent sequence.")
    lines.append("- TMP_STAGE copy and local reread timings; pinned-subtest fill timings.")
    lines.append("")
    lines.append("**Not measured / remote conclusions (must NOT be drawn from this report):**")
    lines.append("- Nothing here ran on Modal containers, a network/distributed filesystem, or a GPU.")
    lines.append("- Cold-start, provider-side caching, and distributed-FS behavior are out of scope.")
    lines.append("- The cache label is a request label, not a guarantee (see Cache semantics).")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Source-only safetensors source-I/O benchmark (e14)."
    )
    parser.add_argument(
        "paths", nargs="+", metavar="PATH",
        help="safetensors file(s) or director(ies) to scan (repeatable)",
    )
    parser.add_argument(
        "--arm", action="append", choices=ALL_ARMS, default=None,
        help="arm to run (repeatable; default: all)",
    )
    parser.add_argument("--block-mib", type=int, default=256, help="sequential/mmap block size in MiB")
    parser.add_argument("--range-mib", type=int, default=32, help="current-range pread chunk size in MiB")
    parser.add_argument(
        "--cache-label", choices=("cold_unknown", "process_cold", "page_cache_warm"),
        default="cold_unknown", help="requested cache semantics label",
    )
    parser.add_argument("--drop-caches", action="store_true", help="attempt to drop OS page cache (opt-in; no-op unsupported on Windows)")
    parser.add_argument("--pinned-subtest", action="store_true", help="run optional pinned-CPU fill subtest")
    parser.add_argument("--json-out", metavar="FILE", help="write JSON results to FILE")
    parser.add_argument("--markdown-out", metavar="FILE", help="write markdown report to FILE")
    parser.add_argument("--keep-temp", action="store_true", help="keep TMP_STAGE temp directory")
    parser.add_argument(
        "--temp-dir", metavar="DIR", default=None,
        help="parent directory for the TMP_STAGE staging dir (default: system temp)",
    )
    args = parser.parse_args(argv)
    if args.block_mib <= 0 or args.range_mib <= 0:
        parser.error("--block-mib and --range-mib must be positive")
    try:
        manifest = load_manifest(args.paths)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        results = run_benchmark(
            manifest,
            arms=args.arm,
            block_mib=args.block_mib,
            range_mib=args.range_mib,
            cache_label=args.cache_label,
            drop_caches=args.drop_caches,
            pinned_subtest=args.pinned_subtest,
            keep_temp=args.keep_temp,
            temp_dir=args.temp_dir,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_summary(results)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)
        print(f"json written: {args.json_out}")
    if args.markdown_out:
        with open(args.markdown_out, "w", encoding="utf-8") as handle:
            handle.write(render_markdown(results))
        print(f"markdown written: {args.markdown_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
