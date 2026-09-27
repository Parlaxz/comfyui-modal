"""Measurement-only Modal Volume queue-depth (QD) shootout probe (Batch C9).

Purpose: determine whether the ~3-4 GB/s full-file result observed by C6
(single full-file os.preadv == 4.07 GB/s; native mmap page-in == 3.6-8 GB/s)
is a true Modal Volume bandwidth ceiling or merely the throughput of ONE
outstanding sequential reader.

The probe measures aggregate throughput with multiple outstanding independent
positional reads of the SAME safetensors file (disjoint byte ranges, no
duplicate overlapping reads), plus native baselines and, when the packages
are present in the image, the external compiled loaders surveyed by C10:

  - Run:ai Model Streamer 0.16.1  (RUNAI_STREAMER_CONCURRENCY env)
  - fastsafetensors 0.3.3         (max_copy_block_size <= 1 GiB, max_threads)

THIS MODULE MEASURES ONLY.  It never loads a live model, never mutates
production loader state, and runs only when explicitly invoked through the
standalone Modal function ``run_unet_qd_probe`` (modal_app.py) or directly
via ``run_unet_qd_probe_battery``.  Every sub-measurement is individually
try/except'd; the result dict is JSON-safe and bounded.

Offline contract (Windows dev box): the module imports with zero side
effects; every Linux-only capability (os.preadv / /proc / resource /
pin_memory) degrades to a named ``skipped``/``error`` entry when absent.
The real measurement runs on the Linux Modal container against the exact
ZImage file (z_image_turbo_bf16.safetensors, 12,309,817,472 data bytes).
"""

from __future__ import annotations

import gc as _gc
import hashlib as _hashlib
import json as _json
import os as _os
import platform as _platform
import struct as _struct
import sys as _sys
import threading as _threading
import time as _time

# ── Constants (all measurements are bounded by these) ─────────────────────
_SYS_CALL = 32 * 1024 * 1024  # validated short-read-free syscall regime (C6)
_HASH_SEG = 256 * 1024        # sample-hash head/tail segment per region
_STRIDE_VERIFY = 512 * 1024 * 1024  # strided verification interval
_SCREEN_WINDOW = 2 * 1024 * 1024 * 1024  # 2 GiB per screen config
_SCREEN_BLOCKS = (32, 64, 128, 256)      # MiB
_SCREEN_QDS = (1, 2, 4, 8)
_FULLFILE_DEFAULT_BLOCKS = {1: 32, 2: 256, 4: 256, 8: 128, 16: 128}  # MiB
_WARM_REPEAT = 256 * 1024 * 1024  # per-config warm-repeat size (256 MiB)
_WINDOWS = 6                       # 6 x 2 GiB rotating screen windows
_VERIFY_KEYS = 16                  # loader shape/dtype spot-check count
_RUNAI_MEMORY_LIMIT = "14000000000"  # bytes (~14 GiB host staging cap; file is 11.5 GiB)
_EXTERNAL_CPU_CORES_MAX = 16
_PINNED_COUNTER_LOCK = _threading.Lock()
_PINNED_LIVE_BYTES = [0]

_MP_MODULE = None


def _lazy_mp():
    """Return the model_preload module (cached) or None."""
    global _MP_MODULE
    if _MP_MODULE is None:
        try:
            import importlib as _il
            _MP_MODULE = _il.import_module("comfymodal_runtime.model_preload")
        except Exception:
            _MP_MODULE = False
    return _MP_MODULE or None


def _lazy_usp():
    """Return the unet_salvage_probe module (cached) or None."""
    try:
        import importlib as _il
        return _il.import_module("comfymodal_runtime.unet_salvage_probe")
    except Exception:
        return None


def _json_safe(value):
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


# ── A. Pure helpers (offline-testable) ────────────────────────────────────


def static_segments(total, qd):
    """Partition [0, total) into *qd* disjoint contiguous segments with no
    gaps and no overlap.  Returns [(start, end), ...] in file order; the sum
    of (end-start) equals *total* exactly.  Raises ValueError for invalid
    inputs."""
    total = int(total)
    qd = int(qd)
    if total < 0 or qd <= 0:
        raise ValueError(f"invalid total={total} qd={qd}")
    if total == 0:
        return []
    seg = (total + qd - 1) // qd
    out = []
    for i in range(qd):
        s = i * seg
        e = min(s + seg, total)
        if e > s:
            out.append((s, e))
    return out


def dynamic_blocks(total, block):
    """Block-granular work items covering [0, total) exactly: [(start, len),
    ...] with len <= block; the final item is clamped.  No gaps/overlap."""
    total = int(total)
    block = int(block)
    if total < 0 or block <= 0:
        raise ValueError(f"invalid total={total} block={block}")
    out = []
    off = 0
    while off < total:
        ln = min(block, total - off)
        out.append((off, ln))
        off += ln
    return out


def partition_coverage(ranges, total):
    """Validate that *ranges* exactly cover [0, total): sorted starts at 0,
    contiguous, final end == total, no overlap.  Returns (ok, reason)."""
    if not ranges:
        return (total == 0), "empty"
    rs = sorted((int(s), int(e)) for s, e in ranges)
    expect = 0
    for s, e in rs:
        if s != expect:
            return False, f"gap_or_overlap at {s} (expected {expect})"
        if e < s:
            return False, f"inverted range {s}..{e}"
        expect = e
    if expect != int(total):
        return False, f"end {expect} != total {total}"
    return True, "ok"


def rotate_window(config_index, window_len, total):
    """Rotate the screen read window so consecutive configs read different
    file regions (cache-fair).  Returns (start, length) clamped to total."""
    n = _WINDOWS
    seg = window_len
    w = config_index % n
    start = w * seg
    if start >= total:
        start = total - seg
    return (max(0, start), min(seg, total - start))


def sample_regions(total, stride=None):
    """Deterministic strided verification regions [(start, length), ...] over
    [0, total): head, tail, and one head+tail sample per *stride* window.
    Bounded: ceil(total/stride)*2 + 2 regions of _HASH_SEG bytes each."""
    stride = int(stride or _STRIDE_VERIFY)
    total = int(total)
    regions = []
    if total <= 0:
        return regions
    seg = _HASH_SEG
    regions.append((0, min(seg, total)))
    if total > seg:
        regions.append((total - seg, seg))
    r = 0
    while r + stride < total:
        head = (r, min(seg, stride))
        tail_start = min(r + stride - seg, total - seg)
        tail = (tail_start, seg)
        regions.append(head)
        if tail[0] != head[0]:
            regions.append(tail)
        r += stride
    return regions


def _tensor_raw_sample(t, seg=_HASH_SEG):
    """Deterministic bounded byte sample of a torch tensor: first + last
    *seg* bytes of its flattened uint8 view.  CUDA tensors are sliced on
    device and only the slices are copied to CPU (bounded H2D).  Never
    raises; returns b'' on failure."""
    try:
        import torch as _t
        c = t.detach().contiguous().reshape(-1).view(_t.uint8)
        if c.device.type != "cpu":
            c = c.cpu()
        n = c.numel()
        if n <= 0:
            return b""
        if n <= 2 * seg:
            return c.numpy().tobytes()
        head = c[:seg].numpy().tobytes()
        tail = c[-seg:].numpy().tobytes()
        return head + tail
    except Exception:
        return b""


def sample_hash_of_tensors(tensors, seg=_HASH_SEG):
    """sha256 over per-key bounded byte samples in sorted key order.
    Deterministic and bounded (~2*seg per tensor).  Returns hex digest or
    '' on failure."""
    try:
        h = _hashlib.sha256()
        for k in sorted(tensors):
            h.update(str(k).encode("utf-8"))
            h.update(_tensor_raw_sample(tensors[k], seg=seg))
        return h.hexdigest()
    except Exception:
        return ""


def key_set_ok(keys, header):
    """Exact sorted key-set equality between *keys* and the header's tensor
    keys (excluding __metadata__)."""
    try:
        expect = sorted(k for k in (header or {}) if k != "__metadata__")
        return sorted(str(k) for k in (keys or [])) == expect
    except Exception:
        return False


def tensor_bytes_from_header(header):
    """Sum of header data_offsets deltas (== safetensors data section)."""
    try:
        total = 0
        for k, info in (header or {}).items():
            if k == "__metadata__":
                continue
            offs = info.get("data_offsets") or [0, 0]
            total += int(offs[1]) - int(offs[0])
        return total
    except Exception:
        return 0


_TORCH_DTYPE_TO_ST = {
    "float32": "F32", "float16": "F16", "bfloat16": "BF16", "float64": "F64",
    "int8": "I8", "int16": "I16", "int32": "I32", "int64": "I64",
    "uint8": "U8", "uint16": "U16", "uint32": "U32", "uint64": "U64",
    "bool": "BOOL",
}


def spot_check_tensors(tensors, header, count=_VERIFY_KEYS):
    """Shape/dtype spot check on a bounded spread of keys.  Returns
    {ok: bool, checked: int, mismatches: [...]}."""
    keys = [k for k in (header or {}) if k != "__metadata__"]
    if not keys:
        return {"ok": False, "checked": 0, "mismatches": ["no_header_keys"]}
    step = max(1, len(keys) // count)
    picked = keys[::step][:count]
    mismatches = []
    for k in picked:
        info = (header or {}).get(k) or {}
        t = tensors.get(k)
        if t is None:
            mismatches.append(f"{k}:missing")
            continue
        try:
            exp_shape = [int(_s) for _s in info.get("shape") or []]
            exp_dtype = str(info.get("dtype", ""))
            got_shape = list(t.shape)
            got_dtype = _TORCH_DTYPE_TO_ST.get(str(t.dtype).replace("torch.", ""),
                                               str(t.dtype))
            if got_shape != exp_shape:
                mismatches.append(f"{k}:shape {got_shape} != {exp_shape}")
            if got_dtype != exp_dtype:
                mismatches.append(f"{k}:dtype {got_dtype} != {exp_dtype}")
        except Exception as exc:  # noqa: BLE001
            mismatches.append(f"{k}:{type(exc).__name__}:{str(exc)[:80]}")
    return {
        "ok": not mismatches,
        "checked": len(picked),
        "mismatches": mismatches[:8],
    }


# ── B. Resource sampling (degrade to {} off-Linux) ────────────────────────


def snapshot_rusage():
    try:
        import resource as _resource
        r = _resource.getrusage(_resource.RUSAGE_SELF)
        return {
            "rss_peak_bytes": int(r.ru_maxrss) * 1024,
            "minflt": int(r.ru_minflt),
            "majflt": int(r.ru_majflt),
            "utime": float(r.ru_utime),
            "stime": float(r.ru_stime),
        }
    except Exception:
        return {}


def _proc_self_status():
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _ctxt_switches():
    """(voluntary, involuntary) context-switch counters from /proc/self/
    status; (None, None) when unavailable."""
    try:
        txt = _proc_self_status()
        v = nv = None
        for line in txt.splitlines():
            if line.startswith("voluntary_ctxt_switches:"):
                v = int(line.split(":", 1)[1].strip())
            elif line.startswith("nonvoluntary_ctxt_switches:"):
                nv = int(line.split(":", 1)[1].strip())
        return (v, nv)
    except Exception:
        return (None, None)


def _vm_rss_bytes():
    try:
        txt = _proc_self_status()
        for line in txt.splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split(":", 1)[1].strip().split()[0]) * 1024
        return None
    except Exception:
        return None


def _thread_cpu_ms():
    """Sum of utime+stime (clock ticks) over all threads under /proc/self/
    task, converted to ms; None when unavailable."""
    try:
        tids = _os.listdir("/proc/self/task")
        total = 0
        for tid in tids:
            try:
                with open(f"/proc/self/task/{tid}/stat", "r", encoding="utf-8") as f:
                    parts = f.read().rsplit(")", 1)[-1].split()
                # parts[11] utime, parts[12] stime (after comm rsplit)
                total += int(parts[11]) + int(parts[12])
            except Exception:
                continue
        return round(total * (1000.0 / _clk_tck()), 2)
    except Exception:
        return None


def _clk_tck():
    try:
        return float(_os.sysconf(_os.sysconf_names["SC_CLK_TCK"]))
    except Exception:
        return 100.0


def _rusage_delta(a, b, key):
    """Delta of a rusage counter.  Integer counters (minflt/majflt) return
    int deltas; float seconds (utime/stime) return float seconds."""
    try:
        if a and b and a.get(key) is not None and b.get(key) is not None:
            va, vb = a[key], b[key]
            if isinstance(va, int) and isinstance(vb, int):
                return int(vb) - int(va)
            return float(vb) - float(va)
    except Exception:
        pass
    return None


def _cpu_ms_from_rusage(a, b):
    """Process CPU ms from utime+stime float-second deltas (or None)."""
    _u = _rusage_delta(a, b, "utime")
    _s = _rusage_delta(a, b, "stime")
    if _u is None and _s is None:
        return None
    total_s = (float(_u or 0.0)) + (float(_s or 0.0))
    return round(total_s * 1000.0, 2)


def _ctx_delta(a, b):
    try:
        if a and b and a[0] is not None and b[0] is not None:
            return (int(b[0]) - int(a[0]), int(b[1]) - int(a[1]))
    except Exception:
        pass
    return None


def pinned_alloc(nbytes):
    """Bounded pinned allocation with plain fallback; tracks live pinned
    bytes globally for the peak-pinned metric."""
    nbytes = int(nbytes)
    if nbytes <= 0:
        raise ValueError("pinned_alloc size must be positive")
    try:
        import torch as _t
        buf = _t.empty(nbytes, dtype=_t.uint8, pin_memory=True)
    except Exception:
        import torch as _t
        buf = _t.empty(nbytes, dtype=_t.uint8)
    _PINNED_COUNTER_LOCK.acquire()
    try:
        _PINNED_LIVE_BYTES[0] += buf.nbytes
        peak = _PINNED_LIVE_BYTES[0]
    finally:
        _PINNED_COUNTER_LOCK.release()
    return buf, peak


def pinned_free(buf):
    try:
        if buf is not None:
            with _PINNED_COUNTER_LOCK:
                _PINNED_LIVE_BYTES[0] = max(0, _PINNED_LIVE_BYTES[0] - int(buf.nbytes))
    except Exception:
        pass
    try:
        del buf
    except Exception:
        pass


def _preadv_fill(fd, mv, file_off):
    """Fill *mv* fully from *file_off* via 32 MiB-positioned os.preadv calls
    with short-read retry.  Returns total bytes read (== len(mv)).  Raises
    IOError on zero-read (EOF before fill)."""
    total = 0
    while total < len(mv):
        n = int(_os.preadv(fd, [mv[total:]], int(file_off) + total))
        if n <= 0:
            raise IOError(
                f"short_read got={n} at file_off={int(file_off) + total} "
                f"remaining={len(mv) - total}"
            )
        total += n
    return total


# ── C. Raw QD config runner ───────────────────────────────────────────────


def _run_worker_static(fd, data_start, seg_start, seg_end, block, out,
                       worker_idx):
    """One worker: sequential 32 MiB-syscall preadv over its own contiguous
    segment [seg_start, seg_end), in *block*-sized buffer iterations.
    Records per-block timings and byte totals into *out*."""
    import time as _t
    seg_len = seg_end - seg_start
    buf, peak = pinned_alloc(min(block, seg_len))
    t_start = _t.perf_counter()
    total = 0
    blocks = []
    first_wall = None
    off = seg_start
    try:
        while off < seg_end:
            chunk_len = min(block, seg_end - off)
            if buf.nbytes < chunk_len:
                pinned_free(buf)
                buf, peak = pinned_alloc(chunk_len)
            mv = memoryview(buf.numpy())[:chunk_len]
            b0 = _t.perf_counter()
            got = _preadv_fill(fd, mv, data_start + off)
            bw = (_t.perf_counter() - b0) * 1000.0
            if first_wall is None:
                first_wall = bw
            blocks.append({
                "off": int(off),
                "len": int(got),
                "wall_ms": round(bw, 4),
                "gbps": round(got / (bw * 1e6) if bw > 0 else 0.0, 4),
            })
            total += got
            off += chunk_len
    finally:
        pinned_free(buf)
    wall = (_t.perf_counter() - t_start) * 1000.0
    out[worker_idx] = {
        "worker": int(worker_idx),
        "segment_start": int(seg_start),
        "segment_end": int(seg_end),
        "bytes_returned": int(total),
        "wall_ms": round(wall, 4),
        "gbps": round(total / (wall * 1e6) if wall > 0 else 0.0, 4),
        "block_count": len(blocks),
        "first_block_wall_ms": round(first_wall or 0.0, 4),
        "block_timings_ms": [round(b["wall_ms"], 4) for b in blocks],
        "block_gbps": [round(b["gbps"], 4) for b in blocks],
    }


def _run_worker_dynamic(fd, data_start, items, lock, block, out, worker_idx):
    """Worker pulls (rel_start, len) items from a shared block queue."""
    import time as _t
    t_start = _t.perf_counter()
    total = 0
    blocks = []
    first_wall = None
    buf = None
    try:
        while True:
            lock.acquire()
            try:
                item = items.pop() if items else None
            finally:
                lock.release()
            if item is None:
                break
            rel_start, ln = item
            if buf is None or buf.nbytes < ln:
                pinned_free(buf)
                buf, _ = pinned_alloc(ln)
            mv = memoryview(buf.numpy())[:ln]
            b0 = _t.perf_counter()
            got = _preadv_fill(fd, mv, data_start + rel_start)
            bw = (_t.perf_counter() - b0) * 1000.0
            if first_wall is None:
                first_wall = bw
            blocks.append({
                "off": int(rel_start),
                "len": int(got),
                "wall_ms": round(bw, 4),
            })
            total += got
    finally:
        pinned_free(buf)
    wall = (_t.perf_counter() - t_start) * 1000.0
    out[worker_idx] = {
        "worker": int(worker_idx),
        "schedule": "dynamic",
        "bytes_returned": int(total),
        "wall_ms": round(wall, 4),
        "gbps": round(total / (wall * 1e6) if wall > 0 else 0.0, 4),
        "block_count": len(blocks),
        "first_block_wall_ms": round(first_wall or 0.0, 4),
    }


def _safe_open_exit(f):
    """Portable safetensors safe_open close (not every version exposes
    ``.close()``; the context-manager protocol is the portable close)."""
    if f is None:
        return
    _exit = getattr(f, "__exit__", None)
    if callable(_exit):
        try:
            _exit(None, None, None)
        except Exception:
            pass


def _steady_state_gbps(workers):
    """Median per-block GB/s across the middle 50% of blocks (all workers
    pooled, first/last 10% dropped).  None when insufficient samples."""
    vals = []
    for w in workers or []:
        for g in (w or {}).get("block_gbps") or []:
            try:
                g = float(g)
                if g > 0.0:
                    vals.append(g)
            except Exception:
                continue
    if len(vals) < 8:
        return None
    vals = sorted(vals)
    lo = max(0, int(len(vals) * 0.1))
    hi = min(len(vals), int(len(vals) * 0.9))
    mid = vals[lo:hi]
    if not mid:
        return None
    return round(sorted(mid)[len(mid) // 2], 4)


def run_qd_config(model_path, header, data_start, total, qd, block_mib,
                  window=None, schedule="static", warm_repeat=True,
                  verify=True):
    """Run one raw queue-depth config: *qd* workers read disjoint ranges of
    the file data section (window-limited when *window* is given; else the
    full file) with *block_mib* buffer iterations and 32 MiB syscalls.

    Returns a JSON-safe metrics dict.  Never raises."""
    import time as _t
    qd = int(qd)
    block = int(block_mib) * 1024 * 1024
    if window is None:
        window = (0, int(total))
    win_start, win_len = int(window[0]), int(window[1])
    out = {
        "kind": "raw_qd",
        "qd": qd,
        "worker_count": qd,
        "block_mib": int(block_mib),
        "syscall_bytes": _SYS_CALL,
        "schedule": str(schedule),
        "window_start": win_start,
        "window_len": win_len,
        "status": "error",
    }
    if not callable(getattr(_os, "preadv", None)):
        return {**out, "error": "unavailable: os.preadv"}
    fd = None
    so = None
    try:
        import safetensors as _st
        so = _st.safe_open(model_path, framework="pt", device="cpu")
    except Exception as exc:  # noqa: BLE001
        so = None
        out["safetensors_open_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    try:
        fd = _os.open(model_path, _os.O_RDONLY | getattr(_os, "O_BINARY", 0))
    except Exception as exc:  # noqa: BLE001
        return {**out, "error": f"open: {type(exc).__name__}: {str(exc)[:120]}"}
    try:
        if schedule == "dynamic":
            items = dynamic_blocks(win_len, block)
            items = [(win_start + s, ln) for s, ln in items]
            lock = _threading.Lock()
            workers_out: dict[int, dict] = {}
            threads = [
                _threading.Thread(
                    target=_run_worker_dynamic,
                    args=(fd, data_start, items, lock, block, workers_out, i),
                    daemon=True,
                )
                for i in range(qd)
            ]
            segs = []
            ok, reason = True, "dynamic_items_exact"
        else:
            segs = static_segments(win_len, qd)
            segs = [(win_start + s, win_start + e) for s, e in segs]
            ok, reason = partition_coverage(
                [(s - win_start, e - win_start) for s, e in segs], win_len)
            workers_out = {}
            threads = [
                _threading.Thread(
                    target=_run_worker_static,
                    args=(fd, data_start, s, e, block, workers_out, i),
                    daemon=True,
                )
                for i, (s, e) in enumerate(segs)
            ]
        if not ok:
            return {**out, "error": f"partition: {reason}"}
        r0 = snapshot_rusage()
        c0 = _ctxt_switches()
        tc0 = _thread_cpu_ms()
        vm0 = _vm_rss_bytes()
        t0 = _t.perf_counter()
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        wall_ms = (_t.perf_counter() - t0) * 1000.0
        r1 = snapshot_rusage()
        c1 = _ctxt_switches()
        tc1 = _thread_cpu_ms()
        vm1 = _vm_rss_bytes()
        workers = [workers_out.get(i) for i in sorted(workers_out)]
        total_bytes = int(sum((w or {}).get("bytes_returned", 0) for w in workers))
        agg_gbps = round(total_bytes / (wall_ms * 1e6) if wall_ms > 0 else 0.0, 4)
        worker_walls = [float((w or {}).get("wall_ms", 0.0)) for w in workers]
        cpu_ms = _cpu_ms_from_rusage(r0, r1)
        out.update({
            "status": "ok" if total_bytes == win_len else "byte_mismatch",
            "bytes_returned": int(total_bytes),
            "expected_bytes": int(win_len),
            "total_wall_ms": round(wall_ms, 4),
            "aggregate_gbps": agg_gbps,
            "steady_state_gbps": _steady_state_gbps(workers),
            "per_worker": workers,
            "first_range_latency_ms": round(min(
                (float((w or {}).get("first_block_wall_ms", 0.0)) for w in workers),
                default=0.0), 4),
            "tail_spread_ms": round(
                max(worker_walls, default=0.0) - min(worker_walls, default=0.0), 4),
            "process_cpu_ms": cpu_ms,
            "thread_cpu_ms": round(float(tc1 - tc0), 2)
            if tc0 is not None and tc1 is not None else None,
            "minflt_delta": _rusage_delta(r0, r1, "minflt"),
            "majflt_delta": _rusage_delta(r0, r1, "majflt"),
            "ctxt_switches_delta": _ctx_delta(c0, c1),
            "rss_delta_bytes": (vm1 - vm0) if vm0 is not None and vm1 is not None else None,
            "peak_rss_bytes": (r1 or {}).get("rss_peak_bytes"),
            "peak_pinned_bytes": _PINNED_LIVE_BYTES[0],
            "cpu_cores": int(_os.cpu_count() or 0),
            "cpu_utilization_pct": round(
                (float(cpu_ms or 0.0) / wall_ms) * 100.0, 2) if wall_ms > 0 else 0.0,
            "gbps_per_cpu_core": round(
                agg_gbps / (float(cpu_ms or 0.0) / wall_ms), 4)
            if (cpu_ms or 0.0) > 0 and wall_ms > 0 else None,
        })
        # warm repeat (cache-state signal): re-read the first warm window
        if warm_repeat and win_len > 0:
            try:
                rep_len = min(_WARM_REPEAT, win_len)
                buf = bytearray(rep_len)
                r0w = _t.perf_counter()
                got = _preadv_fill(fd, memoryview(buf), data_start + win_start)
                rep_wall = (_t.perf_counter() - r0w) * 1000.0
                out["warm_repeat"] = {
                    "bytes": int(got),
                    "wall_ms": round(rep_wall, 4),
                    "gbps": round(got / (rep_wall * 1e6) if rep_wall > 0 else 0.0, 4),
                }
            except Exception as exc:  # noqa: BLE001
                out["warm_repeat"] = {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}
        # sample-hash verification (bounded, post-hoc)
        if verify and so is not None:
            try:
                out["verify"] = verify_window_hash(
                    fd, so, header, data_start, win_start, win_len,
                    full_file=(win_start == 0 and win_len == int(total)),
                )
            except Exception as exc:  # noqa: BLE001
                out["verify"] = {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}
    finally:
        if fd is not None:
            try:
                _os.close(fd)
            except Exception:
                pass
        _safe_open_exit(so)
    return out


def verify_window_hash(fd, so, header, data_start, win_start, win_len,
                       full_file=False):
    """Hash bounded sample ranges of the just-read window and compare against
    the safetensors reference bytes.  Returns {regions: [...], all_match}.  """
    usp = _lazy_usp()
    if usp is None or so is None or win_len <= 0:
        return {"regions": [], "all_match": None,
                "reason": "reference_unavailable"}
    if full_file:
        regions = sample_regions(win_len)
    else:
        seg = _HASH_SEG
        regions = [(0, min(seg, win_len))]
        if win_len > seg:
            regions.append((win_len - seg, seg))
    results = []
    all_match = True
    for rel_start, ln in regions:
        try:
            buf = bytearray(ln)
            got = _preadv_fill(fd, memoryview(buf), data_start + win_start + rel_start)
            match = usp._region_hash_match(
                so, header, win_start + rel_start, got, buf[:got])
            if match is False:
                all_match = False
            results.append({
                "rel_start": int(win_start + rel_start),
                "bytes": int(got),
                "hash_match": match,
            })
        except Exception as exc:  # noqa: BLE001
            results.append({
                "rel_start": int(win_start + rel_start),
                "error": f"{type(exc).__name__}: {str(exc)[:80]}",
            })
            all_match = False
    return {"regions": results, "all_match": bool(all_match)}


# ── D. Baselines ──────────────────────────────────────────────────────────


def baseline_mmap_scan(model_path, header, touch_pages=True):
    """Baseline A: safetensors mmap first-touch scan (mirrors comfy's
    load_torch_file with DISABLE_MMAP=False).  get_tensor per key, then a
    page-granular first-touch pass (numpy strided read) so page-in actually
    happens inside the measured wall.  Returns metrics + the deterministic
    sample hash used as the loader validity reference."""
    import time as _t
    out = {"kind": "baseline_mmap", "status": "error"}
    r0 = snapshot_rusage()
    c0 = _ctxt_switches()
    vm0 = _vm_rss_bytes()
    t0 = _t.perf_counter()
    tensors = {}
    try:
        import safetensors as _st
        with _st.safe_open(model_path, framework="pt", device="cpu") as f:
            for k in f.keys():
                tensors[k] = f.get_tensor(k)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"open: {type(exc).__name__}: {str(exc)[:120]}"
        return out
    if touch_pages:
        try:
            import numpy as _np
            for k in list(tensors):
                raw = tensors[k].reshape(-1).view(tensors[k].dtype)
                _np.frombuffer(raw.numpy().data, dtype=_np.uint8)[::4096].sum()
        except Exception:
            pass  # touch best-effort
    wall_ms = (_t.perf_counter() - t0) * 1000.0
    r1 = snapshot_rusage()
    c1 = _ctxt_switches()
    vm1 = _vm_rss_bytes()
    total_bytes = int(sum(t.numel() * t.element_size() for t in tensors.values()))
    out.update({
        "status": "ok",
        "tensor_count": int(len(tensors)),
        "total_bytes": total_bytes,
        "total_wall_ms": round(wall_ms, 4),
        "aggregate_gbps": round(total_bytes / (wall_ms * 1e6) if wall_ms > 0 else 0.0, 4),
        "minflt_delta": _rusage_delta(r0, r1, "minflt"),
        "majflt_delta": _rusage_delta(r0, r1, "majflt"),
        "ctxt_switches_delta": _ctx_delta(c0, c1),
        "rss_delta_bytes": (vm1 - vm0) if vm0 is not None and vm1 is not None else None,
        "peak_rss_bytes": (r1 or {}).get("rss_peak_bytes"),
        "process_cpu_ms": round(
            (_rusage_delta(r0, r1, "utime") or 0) * 1000.0 / _clk_tck(), 2),
        "sample_hash": sample_hash_of_tensors(tensors),
    })
    try:
        del tensors
    except Exception:
        pass
    return out


# ── E. External loaders (C10 adapters, validity-checked) ──────────────────


def _env_set(kv):
    """Set os.environ entries, returning the previous values for restore."""
    prev = {}
    for k, v in kv.items():
        prev[k] = _os.environ.get(k)
        _os.environ[k] = str(v)
    return prev


def _env_restore(prev):
    for k, v in prev.items():
        if v is None:
            _os.environ.pop(k, None)
        else:
            _os.environ[k] = v


def _loader_timing_bracket(fn):
    """Wall + rusage bracket around a loader callable.  Returns
    (extra_fields, wall_ms, cpu_ms, rss_delta, error_or_None)."""
    import time as _t
    r0 = snapshot_rusage()
    c0 = _ctxt_switches()
    vm0 = _vm_rss_bytes()
    t0 = _t.perf_counter()
    err = None
    try:
        _extra = fn()
    except Exception as exc:  # noqa: BLE001
        _extra = None
        err = f"{type(exc).__name__}: {str(exc)[:200]}"
    wall_ms = (_t.perf_counter() - t0) * 1000.0
    r1 = snapshot_rusage()
    c1 = _ctxt_switches()
    vm1 = _vm_rss_bytes()
    cpu_ms = _cpu_ms_from_rusage(r0, r1)
    return {
        "wall_ms": round(wall_ms, 4),
        "process_cpu_ms": cpu_ms,
        "minflt_delta": _rusage_delta(r0, r1, "minflt"),
        "majflt_delta": _rusage_delta(r0, r1, "majflt"),
        "ctxt_switches_delta": _ctx_delta(c0, c1),
        "rss_delta_bytes": (vm1 - vm0) if vm0 is not None and vm1 is not None else None,
        "peak_rss_bytes": (r1 or {}).get("rss_peak_bytes"),
        "error": err,
    }, _extra


def run_external_loader(model_path, header, loader, concurrency, device,
                        block_mib=None):
    """Run one external loader config with full validity checking.  *loader*
    is "runai" or "fastsafetensors".  Returns a JSON-safe metrics dict."""
    import time as _t
    out = {
        "kind": "external",
        "loader": str(loader),
        "concurrency": int(concurrency),
        "block_mib": int(block_mib) if block_mib else None,
        "device": str(device),
        "status": "error",
    }
    try:
        tensors = None
        if loader == "runai":
            prev = _env_set({
                "RUNAI_STREAMER_CONCURRENCY": str(int(concurrency)),
                "RUNAI_STREAMER_MEMORY_LIMIT": _RUNAI_MEMORY_LIMIT,
            })
            try:
                from runai_model_streamer import SafetensorsStreamer

                def _run():
                    nonlocal tensors
                    tensors = {}
                    with SafetensorsStreamer() as streamer:
                        streamer.stream_file(
                            model_path,
                            device=device if device != "cpu" else "cpu",
                        )
                        for name, tensor in streamer.get_tensors():
                            tensors[name] = tensor.clone()
                    return {}

                timing, _extra = _loader_timing_bracket(_run)
            finally:
                _env_restore(prev)
        elif loader == "fastsafetensors":
            # Use SafeTensorsFileLoader directly: ``fastsafe_open`` does not
            # forward ``max_threads`` (0.3.3), so the thread pool would stay
            # at its default 16.  ``use_buf_register=False`` avoids the
            # cudaHostRegister path (unsupported on this platform, C6
            # rc=304); the nogds pread copier stays active.
            from fastsafetensors import SafeTensorsFileLoader

            def _run():
                nonlocal tensors
                tensors = {}
                ld = SafeTensorsFileLoader(
                    None, device=str(device), max_threads=int(concurrency),
                    nogds=True, disable_cache=True,
                )
                try:
                    ld.add_filenames({0: [model_path]})
                    bufs = ld.copy_files_to_device(
                        use_buf_register=False,
                        max_copy_block_size=(int(block_mib) if block_mib else 1024)
                        * 1024 * 1024,
                    )
                    for k in ld.get_keys():
                        tensors[k] = bufs.get_tensor(k).clone().detach()
                finally:
                    try:
                        ld.close()
                    except Exception:
                        pass
                return {}

            timing, _extra = _loader_timing_bracket(_run)
        else:
            return {**out, "error": f"unknown loader {loader!r}"}
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"setup: {type(exc).__name__}: {str(exc)[:200]}"
        return out
    if timing.get("error"):
        out.update(timing)
        out["error"] = timing.pop("error")
        return out
    out.update(timing)
    if tensors is None:
        out["error"] = "loader returned no tensors"
        return out
    total_bytes = int(sum(t.numel() * t.element_size() for t in tensors.values()))
    out.update({
        "status": "ok",
        "tensor_count": int(len(tensors)),
        "total_bytes": total_bytes,
        "aggregate_gbps": round(
            total_bytes / (timing["wall_ms"] * 1e6) if timing["wall_ms"] > 0 else 0.0, 4),
        "key_set_ok": key_set_ok(tensors.keys(), header),
        "spot_check": spot_check_tensors(tensors, header),
        "sample_hash": sample_hash_of_tensors(tensors),
        "cpu_cores": int(_os.cpu_count() or 0),
        "cpu_utilization_pct": round(
            (float(timing["process_cpu_ms"] or 0.0) / timing["wall_ms"]) * 100.0, 2)
            if timing["wall_ms"] > 0 else 0.0,
        "gbps_per_cpu_core": round(
            (total_bytes / (timing["wall_ms"] * 1e6)) /
            (float(timing["process_cpu_ms"] or 0.0) / timing["wall_ms"]), 4)
            if timing["wall_ms"] > 0 and (timing["process_cpu_ms"] or 0.0) > 0 else None,
    })
    try:
        del tensors
    except Exception:
        pass
    return out


# ── F. GPU transfer phase (storage -> pinned -> async H2D) ────────────────


def gpu_transfer_phase(model_path, header, data_start, total, qd, block_mib):
    """Best-storage-config storage→pinned→asynchronous-GPU measurement:
    preadv into per-worker pinned slots, then async non_blocking copy_ to
    CUDA dests with CUDA events; single synchronize at the end.  Returns
    metrics with H2D host-issue and CUDA-device walls."""
    import time as _t
    import torch as _torch
    out = {
        "kind": "gpu",
        "qd": int(qd),
        "block_mib": int(block_mib),
        "status": "error",
    }
    if not _torch.cuda.is_available():
        return {**out, "error": "cuda_unavailable"}
    qd = int(qd)
    block = int(block_mib) * 1024 * 1024
    fd = None
    try:
        fd = _os.open(model_path, _os.O_RDONLY | getattr(_os, "O_BINARY", 0))
        segs = static_segments(total, qd)
        segs = [(s, e) for s, e in segs]
        ok, reason = partition_coverage(segs, total)
        if not ok:
            return {**out, "error": f"partition: {reason}"}
        pinned = []
        dests = []
        workers_out = {}
        try:
            for _ in range(qd):
                pinned.append(pinned_alloc(min(block, total))[0])
                dests.append(_torch.empty(block, dtype=_torch.uint8, device="cuda"))
            _torch.cuda.synchronize()
            ev_start = _torch.cuda.Event(enable_timing=True)
            ev_end = _torch.cuda.Event(enable_timing=True)
            issue_entries = []
            t0 = _t.perf_counter()
            ev_start.record()
            for i, (s, e) in enumerate(segs):
                off = s
                while off < e:
                    ln = min(block, e - off)
                    mv = memoryview(pinned[i].numpy())[:ln]
                    _preadv_fill(fd, mv, data_start + off)
                    src = pinned[i][:ln]
                    dst = dests[i][:ln]
                    i0 = _t.perf_counter()
                    dst.copy_(src, non_blocking=True)
                    issue_entries.append(round((_t.perf_counter() - i0) * 1000.0, 4))
                    off += ln
            ev_end.record()
            _torch.cuda.synchronize()
            wall_ms = (_t.perf_counter() - t0) * 1000.0
            dev_ms = float(ev_start.elapsed_time(ev_end))
            out.update({
                "status": "ok",
                "total_bytes": int(total),
                "storage_plus_h2d_wall_ms": round(wall_ms, 4),
                "h2d_device_ms": round(dev_ms, 4),
                "h2d_host_issue_total_ms": round(sum(issue_entries), 4),
                "h2d_host_issue_max_ms": round(max(issue_entries, default=0.0), 4),
                "storage_gbps": round(
                    total / ((wall_ms - dev_ms) * 1e6) if wall_ms > dev_ms else 0.0, 4),
                "combined_gbps": round(total / (wall_ms * 1e6) if wall_ms > 0 else 0.0, 4),
                "pinned_bytes": int(qd * block),
                "gpu_temp_bytes": int(qd * block),
                "issue_count": int(len(issue_entries)),
            })
        finally:
            try:
                del dests
                _torch.cuda.empty_cache()
            except Exception:
                pass
            for b in pinned:
                pinned_free(b)
            try:
                del pinned
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        if fd is not None:
            try:
                _os.close(fd)
            except Exception:
                pass
    return out


# ── G. Orchestrator ───────────────────────────────────────────────────────


def _probe_env():
    out = {
        "status": "ok",
        "os": _os.name,
        "platform": _sys.platform,
        "python": _platform.python_version(),
        "cpu_cores": int(_os.cpu_count() or 0),
        "preadv_available": callable(getattr(_os, "preadv", None)),
        "cuda_available": False,
        "cuda_device_name": None,
    }
    try:
        import torch as _t
        out["torch_version"] = str(_t.__version__)
        out["cuda_available"] = bool(_t.cuda.is_available())
        if out["cuda_available"]:
            out["cuda_device_name"] = str(_t.cuda.get_device_name(0))
    except Exception:
        pass
    return out


def _probe_file(model_path, header):
    out = {
        "status": "error",
        "path": str(model_path),
        "size_bytes": -1,
        "header_bytes": -1,
        "data_start_offset": -1,
        "tensor_count": 0,
        "total_data_bytes": 0,
        "statvfs": {},
        "mount": "",
    }
    try:
        out["size_bytes"] = int(_os.path.getsize(model_path))
    except Exception:
        pass
    try:
        with open(model_path, "rb") as f:
            head_len = _struct.unpack("<Q", f.read(8))[0]
        out["header_bytes"] = int(head_len)
        out["data_start_offset"] = 8 + int(head_len)
    except Exception:
        pass
    if header is not None:
        out["tensor_count"] = len([k for k in header if k != "__metadata__"])
        out["total_data_bytes"] = tensor_bytes_from_header(header)
    try:
        st = _os.statvfs(model_path)
        out["statvfs"] = {
            k: int(getattr(st, k))
            for k in ("f_bsize", "f_frsize", "f_blocks", "f_bfree", "f_bavail")
            if hasattr(st, k)
        }
    except Exception:
        out["statvfs"] = {"placeholder": "statvfs_unavailable"}
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and model_path.startswith(parts[1]):
                    out["mount"] = f"{parts[0]} on {parts[1]} type {parts[2]}"
                    break
    except Exception:
        pass
    out["status"] = "ok" if out["total_data_bytes"] > 0 else "error"
    return out


def _loader_smoke_tests():
    """Cheap loader mechanism smoke tests against a small synthetic
    safetensors file written to the container's local /tmp (never the
    volume).  Each loader runs its real stream/load path; the result tells
    the structural gate whether the adapter API + env wiring are valid
    BEFORE the expensive evidence run.  Never raises."""
    import time as _t
    out = {"synthetic_file": "", "loaders": {}}
    path = "/tmp/c9qd_smoke.safetensors"
    try:
        import numpy as _np
        import torch as _torch
        import safetensors.torch as _st
        _n = 256 * 1024  # 1 MiB of f32
        _st.save_file({
            "a": _torch.from_numpy(_np.arange(_n, dtype=_np.float32)),
            "b": _torch.from_numpy(_np.full(_n, 1.5, dtype=_np.float32)),
            "c": _torch.zeros(4, dtype=_torch.bfloat16),
        }, path)
        out["synthetic_file"] = path
    except Exception as exc:  # noqa: BLE001
        out["synthetic_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return out

    # RunAI smoke
    try:
        from runai_model_streamer import SafetensorsStreamer
        prev = _env_set({
            "RUNAI_STREAMER_CONCURRENCY": "4",
            "RUNAI_STREAMER_MEMORY_LIMIT": _RUNAI_MEMORY_LIMIT,
        })
        try:
            t0 = _t.perf_counter()
            keys = []
            with SafetensorsStreamer() as streamer:
                streamer.stream_file(path, device="cpu")
                for name, _tensor in streamer.get_tensors():
                    keys.append(str(name))
                    del _tensor
            out["loaders"]["runai"] = {
                "status": "ok",
                "keys": sorted(keys),
                "wall_ms": round((_t.perf_counter() - t0) * 1000, 2),
            }
        finally:
            _env_restore(prev)
    except Exception as exc:  # noqa: BLE001
        out["loaders"]["runai"] = {
            "status": "error",
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
        }

    # fastsafetensors smoke (SafeTensorsFileLoader path, max_threads=4)
    try:
        from fastsafetensors import SafeTensorsFileLoader
        t0 = _t.perf_counter()
        ld = SafeTensorsFileLoader(None, "cpu", max_threads=4, nogds=True,
                                   disable_cache=True)
        try:
            ld.add_filenames({0: [path]})
            bufs = ld.copy_files_to_device(
                use_buf_register=False, max_copy_block_size=1 << 20)
            keys = sorted(ld.get_keys())
            for k in keys:
                _tt = bufs.get_tensor(k)
                del _tt
            out["loaders"]["fastsafetensors"] = {
                "status": "ok",
                "keys": keys,
                "wall_ms": round((_t.perf_counter() - t0) * 1000, 2),
            }
        finally:
            try:
                ld.close()
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        out["loaders"]["fastsafetensors"] = {
            "status": "error",
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
    try:
        _os.remove(path)
    except Exception:
        pass
    return out


def _loader_ownership_test():
    """Gate 1 empirical test for fastsafetensors CUDA tensor ownership
    (runs in the structural gate on the first valid container).

    Loads a small synthetic file to cuda:0 and records, for representative
    tensors: data_ptr, storage data_ptr, storage size, storage_offset,
    shape, stride, contiguous, _base, and whether multiple tensors share one
    backing allocation.  Then verifies the documented lifetime contract:
      (a) tensors remain valid while the loader/buffer is retained (read +
          hash again after gc.collect + synchronize);
      (b) tensors become invalid after FilesBufferOnDevice.close() (the
          documented contract — recorded as error/poisoned read).
    Never raises."""
    import time as _t
    import torch as _torch_ot
    out = {"status": "skipped", "reason": ""}
    if not _torch_ot.cuda.is_available():
        out["reason"] = "cuda_unavailable"
        return out
    try:
        from fastsafetensors import SafeTensorsFileLoader
    except Exception as exc:  # noqa: BLE001
        out["status"] = "skipped"
        out["reason"] = f"fastsafetensors_unavailable: {type(exc).__name__}"
        return out
    import numpy as _np
    import safetensors.torch as _st_ot
    _path = "/tmp/c9qd_ownership.safetensors"
    try:
        _n = 256 * 1024
        _st_ot.save_file({
            "a": _torch_ot.from_numpy(_np.arange(_n, dtype=_np.float32)),
            "b": _torch_ot.from_numpy(_np.full(_n, 1.5, dtype=_np.float32)),
            "c": _torch_ot.zeros(4, dtype=_torch_ot.bfloat16),
        }, _path)
    except Exception as exc:  # noqa: BLE001
        out["status"] = "error"
        out["error"] = f"synthetic_write: {type(exc).__name__}: {str(exc)[:120]}"
        return out
    try:
        _ld = SafeTensorsFileLoader(None, "cuda:0", max_threads=2, nogds=True,
                                    disable_cache=True)
        _ld.add_filenames({0: [_path]})
        _fb = _ld.copy_files_to_device(
            use_buf_register=False, max_copy_block_size=1 << 20)
        _tensors = {_k: _fb.get_tensor(_k) for _k in _ld.get_keys()}
        _torch_ot.cuda.synchronize()
        # Identity records for representative tensors.
        _identity = []
        for _k in sorted(_tensors):
            _tt = _tensors[_k]
            _stg = _tt.untyped_storage() if hasattr(_tt, "untyped_storage") else None
            _identity.append({
                "key": _k,
                "data_ptr": int(_tt.data_ptr()),
                "storage_data_ptr": int(_stg.data_ptr()) if _stg is not None else None,
                "storage_size": int(_stg.nbytes()) if _stg is not None else None,
                "storage_offset": int(_tt.storage_offset()),
                "shape": list(_tt.shape),
                "stride": list(_tt.stride()),
                "contiguous": bool(_tt.is_contiguous()),
                "base": str(getattr(_tt, "_base", None)),
            })
        _base_ptrs = sorted({int(_tt.data_ptr()) for _tt in _tensors.values()})
        out["identity"] = _identity
        out["distinct_data_ptrs"] = _base_ptrs
        out["tensors_share_allocation"] = len(_base_ptrs) < len(_tensors)
        # (a) retained-loader lifetime: gc + sync, then re-hash values.
        _hash_before = sample_hash_of_tensors(_tensors)
        _owner_ref = (_ld, _fb)
        del _ld, _fb, _tensors
        _gc.collect()
        _torch_ot.cuda.synchronize()
        _ld2, _fb2 = _owner_ref
        _t2 = {_k: _fb2.get_tensor(_k) for _k in _ld2.get_keys()}
        _torch_ot.cuda.synchronize()
        _hash_after = sample_hash_of_tensors(_t2)
        out["retained_lifetime"] = {
            "status": "ok" if _hash_after == _hash_before else "mismatch",
            "hash_before": _hash_before[:16],
            "hash_after": _hash_after[:16],
        }
        del _t2
        # (b) close() invalidates (documented contract) — record the outcome.
        try:
            _fb2.close()
            _torch_ot.cuda.synchronize()
            _bad = None
            try:
                _t3 = _fb2.get_tensor("a")
                _bad = str(_t3[:4].cpu().tolist())
                del _t3
            except Exception as _exc_c:
                _bad = f"error:{type(_exc_c).__name__}:{str(_exc_c)[:80]}"
            out["closed_lifetime"] = {
                "status": "recorded",
                "read_after_close": _bad,
            }
        except Exception as _exc_cl:
            out["closed_lifetime"] = {
                "status": "error",
                "error": f"{type(_exc_cl).__name__}: {str(_exc_cl)[:120]}",
            }
        out["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        out["status"] = "error"
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        try:
            _os.remove(_path)
        except Exception:
            pass
    return out


def _loader_imports():
    out = {}
    for name, mod in (("runai_model_streamer", "runai_model_streamer"),
                      ("fastsafetensors", "fastsafetensors")):
        try:
            m = __import__(mod)
            out[name] = {"importable": True, "version": str(getattr(m, "__version__", ""))}
        except Exception as exc:  # noqa: BLE001
            out[name] = {"importable": False,
                         "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    try:
        import safetensors
        out["safetensors_version"] = str(getattr(safetensors, "__version__", ""))
        import safetensors.torch as _st
        import inspect
        sig = inspect.signature(_st.safe_open)
        out["safe_open_backend_param"] = "backend" in sig.parameters
    except Exception as exc:  # noqa: BLE001
        out["safetensors_probe_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out


def _select_fullfile_blocks(screen):
    """Pick the full-file block size per QD from the screen results: the
    block with the best aggregate GB/s at that QD, else the default table."""
    best = {}
    for cfg in (screen or []):
        try:
            qd = int(cfg.get("qd"))
            if cfg.get("status") != "ok" or cfg.get("schedule") != "static":
                continue
            gbps = float(cfg.get("aggregate_gbps") or 0.0)
            cur = best.get(qd)
            if cur is None or gbps > cur[0]:
                best[qd] = (gbps, int(cfg.get("block_mib")))
        except Exception:
            continue
    out = {}
    for qd, default in _FULLFILE_DEFAULT_BLOCKS.items():
        if qd in best:
            out[qd] = best[qd][1]
        else:
            out[qd] = default
    return out


def run_unet_qd_probe_battery(model_path, mode="evidence", trace=None, emit=None):
    """Run the C9 queue-depth battery against *model_path*.

    mode="structural": env + file + header reconcile + one QD1 256 MiB read +
    loader import checks (cheap paid gate).
    mode="evidence": the full bounded matrix: mmap baseline, sequential
    preadv (QD1 full file), 16-config QD x block screen, full-file QD2/4/8
    (+QD16 when still scaling), warm-QD1 control, one GPU transfer phase,
    and the external loader battery (RunAI / fastsafetensors) with full
    validity checking.

    Returns a JSON-safe dict; never raises.
    """
    import time as _t
    t0 = _t.monotonic()
    result = {
        "probe": "unet_qd",
        "model_path": str(model_path),
        "mode": str(mode),
        "status": "ok",
    }
    sections = {}
    mp = _lazy_mp()
    header = None
    if mp is not None:
        try:
            header = mp._c6_parse_safetensors_header(model_path)
        except Exception:
            header = None

    sections["env"] = _probe_env()
    sections["file"] = _probe_file(model_path, header)
    sections["loader_imports"] = _loader_imports()
    sections["loader_smoke"] = _loader_smoke_tests()
    sections["loader_ownership"] = _loader_ownership_test()
    data_start = int(sections["file"].get("data_start_offset") or -1)
    total = int(sections["file"].get("total_data_bytes") or 0)
    ctx = {"header": header, "data_start": data_start, "total": total}

    if mode == "structural":
        cfg = run_qd_config(
            model_path, header, data_start, total,
            qd=1, block_mib=32, window=(0, min(256 * 1024 * 1024, total)),
            warm_repeat=True, verify=True,
        )
        sections["structural_qd1"] = cfg
        sections["summary"] = {
            "status": "ok",
            "preadv_available": bool(sections["env"].get("preadv_available")),
            "file_ok": sections["file"].get("status") == "ok",
            "structural_qd1_status": cfg.get("status"),
            "structural_qd1_gbps": cfg.get("aggregate_gbps"),
            "loader_imports": sections["loader_imports"],
            "loader_smoke": sections["loader_smoke"],
            "loader_ownership": sections["loader_ownership"],
        }
        result["sections"] = sections
        result["_wall_ms"] = round((_t.monotonic() - t0) * 1000, 4)
        return _json_safe(result)

    if mode == "external":
        # Loader-only corrective battery: env/file + the external loader
        # matrix with full validity checks.  No raw QD matrix, no baselines,
        # no GPU phase — the raw queue-depth evidence is collected by
        # mode="evidence"; this mode exists to re-run ONLY the external
        # loader phase after an adapter fix (standing rule: fix and repeat
        # the broken mechanism, bounded).
        external = []
        ref_hash = ""
        runai_ok = bool((sections["loader_imports"].get("runai_model_streamer") or {})
                        .get("importable"))
        fst_ok = bool((sections["loader_imports"].get("fastsafetensors") or {})
                      .get("importable"))
        ext_plan = []
        if runai_ok:
            ext_plan += [
                ("runai", 8, "cpu", None),
                ("runai", 16, "cpu", None),
                ("runai", 16, "cuda:0", None),
            ]
        if fst_ok:
            ext_plan += [
                ("fastsafetensors", 8, "cpu", 1024),
                ("fastsafetensors", 16, "cpu", 1024),
                ("fastsafetensors", 16, "cuda:0", 1024),
            ]
        for loader, conc, device, block_mib in ext_plan:
            res = run_external_loader(
                model_path, header, loader, conc, device, block_mib=block_mib)
            external.append(res)
        sections["external"] = external
        sections["summary"] = {
            "status": "ok",
            "total_data_bytes": int(total),
            "external": [
                {
                    "loader": e.get("loader"),
                    "concurrency": e.get("concurrency"),
                    "device": e.get("device"),
                    "status": e.get("status"),
                    "wall_ms": e.get("wall_ms"),
                    "aggregate_gbps": e.get("aggregate_gbps"),
                    "sample_hash": e.get("sample_hash"),
                    "key_set_ok": e.get("key_set_ok"),
                    "spot_check_ok": (e.get("spot_check") or {}).get("ok"),
                    "tensor_count": e.get("tensor_count"),
                    "total_bytes": e.get("total_bytes"),
                    "error": e.get("error"),
                }
                for e in external
            ],
            "loader_smoke": sections["loader_smoke"],
        }
        result["sections"] = sections
        result["_wall_ms"] = round((_t.monotonic() - t0) * 1000, 4)
        return _json_safe(result)

    if total <= 0 or data_start <= 0 or header is None:
        result["status"] = "error"
        result["error"] = "header_unavailable"
        result["sections"] = sections
        result["_wall_ms"] = round((_t.monotonic() - t0) * 1000, 4)
        return _json_safe(result)

    # ── Phase 1: native baselines ──
    sections["baseline_mmap"] = baseline_mmap_scan(model_path, header)
    sections["baseline_seq_preadv"] = run_qd_config(
        model_path, header, data_start, total,
        qd=1, block_mib=32, window=None, schedule="static",
        warm_repeat=True, verify=True,
    )
    ref_hash = (sections.get("baseline_mmap") or {}).get("sample_hash")

    # ── Phase 2: bounded QD x block screen (2 GiB windows, rotated) ──
    screen = []
    idx = 0
    for qd in _SCREEN_QDS:
        for bmib in _SCREEN_BLOCKS:
            ws, wl = rotate_window(idx, _SCREEN_WINDOW, total)
            cfg = run_qd_config(
                model_path, header, data_start, total,
                qd=qd, block_mib=bmib, window=(ws, wl), schedule="static",
                warm_repeat=True, verify=True,
            )
            cfg["_idx"] = idx
            screen.append(cfg)
            idx += 1
    # dynamic-schedule contrast at QD8/64 MiB (same window as static QD8/64)
    ws, wl = rotate_window(idx, _SCREEN_WINDOW, total)
    dyn = run_qd_config(
        model_path, header, data_start, total,
        qd=8, block_mib=64, window=(ws, wl), schedule="dynamic",
        warm_repeat=True, verify=True,
    )
    dyn["_idx"] = idx
    screen.append(dyn)
    sections["screen"] = screen

    # ── Phase 3: full-file measurement ──
    best_blocks = _select_fullfile_blocks(screen)
    qd1_gbps = float((sections.get("baseline_seq_preadv") or {}).get("aggregate_gbps") or 0.0)
    fullfile = []
    for qd in (2, 4, 8):
        fullfile.append(run_qd_config(
            model_path, header, data_start, total,
            qd=qd, block_mib=best_blocks.get(qd, _FULLFILE_DEFAULT_BLOCKS[qd]),
            window=None, schedule="static", warm_repeat=True, verify=True,
        ))
    qd8_gbps = float((fullfile[-1] or {}).get("aggregate_gbps") or 0.0)
    qd16 = None
    if qd1_gbps > 0 and qd8_gbps >= 1.2 * qd1_gbps:
        qd16 = run_qd_config(
            model_path, header, data_start, total,
            qd=16, block_mib=best_blocks.get(16, _FULLFILE_DEFAULT_BLOCKS[16]),
            window=None, schedule="static", warm_repeat=True, verify=True,
        )
        fullfile.append(qd16)
    sections["fullfile_qd16_included"] = qd16 is not None
    # warm-QD1 control: same config as the cold QD1, after the battery
    sections["fullfile_warm_qd1_control"] = run_qd_config(
        model_path, header, data_start, total,
        qd=1, block_mib=32, window=None, schedule="static",
        warm_repeat=True, verify=True,
    )
    sections["fullfile"] = fullfile

    # ── Phase 4: GPU transfer for the best screen config ──
    best_gpu = None
    for cfg in screen:
        if (cfg or {}).get("status") != "ok" or (cfg or {}).get("schedule") != "static":
            continue
        if best_gpu is None or (cfg.get("aggregate_gbps") or 0.0) > (
                best_gpu.get("aggregate_gbps") or 0.0):
            best_gpu = cfg
    gpu_qd = int((best_gpu or {}).get("qd") or 4)
    gpu_block = int((best_gpu or {}).get("block_mib") or 256)
    sections["gpu_transfer"] = gpu_transfer_phase(
        model_path, header, data_start, total, gpu_qd, gpu_block)
    sections["gpu_config"] = {"qd": gpu_qd, "block_mib": gpu_block}

    # ── Phase 5: external loaders (validity-checked) ──
    external = []
    runai_ok = bool((sections["loader_imports"].get("runai_model_streamer") or {})
                    .get("importable"))
    fst_ok = bool((sections["loader_imports"].get("fastsafetensors") or {})
                  .get("importable"))
    ext_plan = []
    if runai_ok:
        ext_plan += [
            ("runai", 8, "cpu", None),
            ("runai", 16, "cpu", None),
            ("runai", 16, "cuda:0", None),
        ]
    if fst_ok:
        ext_plan += [
            ("fastsafetensors", 8, "cpu", 1024),
            ("fastsafetensors", 16, "cpu", 1024),
            ("fastsafetensors", 16, "cuda:0", 1024),
        ]
    for loader, conc, device, block_mib in ext_plan:
        res = run_external_loader(
            model_path, header, loader, conc, device, block_mib=block_mib)
        if ref_hash and res.get("sample_hash"):
            res["sample_hash_matches_baseline"] = bool(
                res["sample_hash"] == ref_hash)
        res["_skip_reason"] = "" if res.get("status") == "ok" else res.get("error", "")
        external.append(res)
    sections["external"] = external
    if not runai_ok:
        sections["external_skips"] = {
            "runai": "import failed (image extras not installed?)"}
    if not fst_ok:
        sections.setdefault("external_skips", {})["fastsafetensors"] = (
            "import failed (image extras not installed?)")

    # ── Summary ──
    def _gbps(section, key):
        try:
            v = float((section or {}).get(key) or 0.0)
            return round(v, 4)
        except Exception:
            return 0.0

    sections["summary"] = {
        "status": "ok",
        "total_data_bytes": int(total),
        "baseline_mmap_gbps": _gbps(sections.get("baseline_mmap"), "aggregate_gbps"),
        "baseline_seq_preadv_gbps": _gbps(
            sections.get("baseline_seq_preadv"), "aggregate_gbps"),
        "baseline_mmap_wall_ms": (sections.get("baseline_mmap") or {}).get("total_wall_ms"),
        "baseline_seq_preadv_wall_ms": (
            sections.get("baseline_seq_preadv") or {}).get("total_wall_ms"),
        "fullfile_qd1_gbps": qd1_gbps,
        "fullfile_warm_qd1_gbps": _gbps(
            sections.get("fullfile_warm_qd1_control"), "aggregate_gbps"),
        "fullfile_best_qd2_gbps": _gbps(fullfile[0], "aggregate_gbps") if len(fullfile) >= 1 else 0.0,
        "fullfile_best_qd4_gbps": _gbps(fullfile[1], "aggregate_gbps") if len(fullfile) >= 2 else 0.0,
        "fullfile_best_qd8_gbps": _gbps(fullfile[2], "aggregate_gbps") if len(fullfile) >= 3 else 0.0,
        "fullfile_qd16_gbps": _gbps(qd16, "aggregate_gbps") if qd16 else 0.0,
        "qd_ratios": {
            "qd2_over_qd1": round(
                (_gbps(fullfile[0], "aggregate_gbps") / qd1_gbps), 4)
                if qd1_gbps > 0 and len(fullfile) >= 1 else None,
            "qd4_over_qd1": round(
                (_gbps(fullfile[1], "aggregate_gbps") / qd1_gbps), 4)
                if qd1_gbps > 0 and len(fullfile) >= 2 else None,
            "qd8_over_qd1": round(
                (_gbps(fullfile[2], "aggregate_gbps") / qd1_gbps), 4)
                if qd1_gbps > 0 and len(fullfile) >= 3 else None,
            "qd16_over_qd1": round(
                (_gbps(qd16, "aggregate_gbps") / qd1_gbps), 4)
                if qd16 is not None and qd1_gbps > 0 else None,
            "warm_qd1_over_cold_qd1": round(
                (_gbps(sections.get("fullfile_warm_qd1_control"), "aggregate_gbps")
                 / qd1_gbps), 4) if qd1_gbps > 0 else None,
        },
        "best_screen": {
            "qd": int((best_gpu or {}).get("qd") or 0),
            "block_mib": int((best_gpu or {}).get("block_mib") or 0),
            "gbps": _gbps(best_gpu, "aggregate_gbps"),
        },
        "best_fullfile_gbps": max(
            [qd1_gbps] + [_gbps(c, "aggregate_gbps") for c in fullfile], default=0.0),
        "external": [
            {
                "loader": e.get("loader"),
                "concurrency": e.get("concurrency"),
                "device": e.get("device"),
                "status": e.get("status"),
                "wall_ms": e.get("wall_ms"),
                "aggregate_gbps": e.get("aggregate_gbps"),
                "sample_hash_matches_baseline": e.get("sample_hash_matches_baseline"),
                "key_set_ok": e.get("key_set_ok"),
                "spot_check_ok": (e.get("spot_check") or {}).get("ok"),
                "error": e.get("error"),
            }
            for e in external
        ],
        "gpu_transfer_status": (sections.get("gpu_transfer") or {}).get("status"),
    }

    result["sections"] = sections
    result["_wall_ms"] = round((_t.monotonic() - t0) * 1000, 4)
    try:
        print("[v2.qd_probe] summary=" + _json.dumps(
            _json_safe(sections.get("summary")), separators=(",", ":"),
            sort_keys=True), flush=True)
    except Exception:
        pass
    return _json_safe(result)
