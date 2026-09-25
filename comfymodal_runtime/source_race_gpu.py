"""Minimal additive shareable-host-staging + H2D support for the frozen mmap source harness.

This module is intentionally small and is *only* used when the caller opts in.
When it is not used, ``run_mmap_lifecycle_probe`` follows its original private
destination path byte-for-byte.

Modes:
  * staging: four QD4 reader processes write the 64 MiB blocks they already read
    into a POSIX shared-memory region (``/dev/shm`` backed, fork-inherited)
    instead of process-private bytearrays.  A consumer in the CUDA-owning parent
    process advances each lane's ``consumed`` counter so a reader can reuse a
    slot.  No CUDA.
  * registered: the same, with the staging region pinned via ``cuMemHostRegister``
    (the driver-API equivalent of ``cudaHostRegister``).  No bytes copied.
  * h2d: the same pinned staging plus one GPU destination buffer, one
    non-blocking stream, and one ``cuMemcpyHtoDAsync`` per produced block with a
    fresh completion event per transfer.  A staging slot is released only after
    its transfer's event has completed.

Staging layout: ``qd`` lanes; each lane owns ``slots`` slots of ``read_bytes``.
A lane's slot ``k`` is the block with per-lane publish sequence ``k % slots``.
A reader may only write sequence ``s`` when ``s - consumed < slots``; it
publishes ``s + 1`` only after the native memcpy has fully returned.

CUDA is initialized by the caller in the parent **after** the reader fork but
**before** the readers are released (the harness ``on_ready`` hook), so no CUDA
context is inherited by a reader child and no setup cost lands on the source
critical path.  The context is popped from the main thread so the H2D consumer
thread makes it current itself.  All control counters use ``lock=False`` shared
primitives (one writer, one reader per lane) so a fork can never inherit a
locked primitive.  Readers never execute CUDA.
"""

from __future__ import annotations

import collections
import ctypes
import hashlib
import threading
import time
from typing import Any

_DRIVER: dict[str, Any] = {"lib": None}
_CUDA_SUCCESS = 0


def _load_driver() -> Any:
    """Load libcuda.so.1 and declare only the driver entry points we use."""
    if _DRIVER["lib"] is not None:
        return _DRIVER["lib"]
    last: Exception | None = None
    lib = None
    for name in ("libcuda.so.1", "libcuda.so"):
        try:
            lib = ctypes.CDLL(name)
            break
        except OSError as exc:  # noqa: PERF203
            last = exc
    if lib is None:
        raise RuntimeError(f"libcuda unavailable: {last}")

    def sym(*names: str) -> Any:
        for candidate in names:
            fn = getattr(lib, candidate, None)
            if fn is not None:
                return fn
        raise AttributeError(f"none of {names} present in libcuda")

    ci, cp, cv, cs, cu64 = (
        ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_uint64)
    cf = ctypes.c_float
    protos = {
        "cuInit": ([cv], ci),
        "cuDeviceGet": ([ctypes.POINTER(ci), ci], ci),
        "cuDeviceGetName": ([ctypes.c_char_p, ci, ci], ci),
        "cuCtxCreate_v2": ([ctypes.POINTER(cp), cv, ci], ci),
        "cuCtxDestroy_v2": ([cp], ci),
        "cuCtxPopCurrent_v2": ([ctypes.POINTER(cp)], ci),
        "cuCtxSetCurrent": ([cp], ci),
        "cuMemHostRegister_v2": ([cp, cs, cv], ci),
        "cuMemHostUnregister": ([cp], ci),
        "cuMemAlloc_v2": ([ctypes.POINTER(cu64), cs], ci),
        "cuMemFree_v2": ([cu64], ci),
        "cuStreamCreate": ([ctypes.POINTER(cp), cv], ci),
        "cuStreamDestroy_v2": ([cp], ci),
        "cuStreamSynchronize": ([cp], ci),
        "cuEventCreate": ([ctypes.POINTER(cp), cv], ci),
        "cuEventDestroy_v2": ([cp], ci),
        "cuEventRecord": ([cp, cp], ci),
        "cuEventQuery": ([cp], ci),
        "cuEventSynchronize": ([cp], ci),
        "cuEventElapsedTime": ([ctypes.POINTER(cf), cp, cp], ci),
        "cuMemcpyHtoDAsync_v2": ([cu64, cp, cs, cp], ci),
        "cuMemcpyDtoH_v2": ([cp, cu64, cs], ci),
    }
    aliases = {
        "cuCtxCreate_v2": ("cuCtxCreate_v2", "cuCtxCreate"),
        "cuCtxDestroy_v2": ("cuCtxDestroy_v2", "cuCtxDestroy"),
        "cuCtxPopCurrent_v2": ("cuCtxPopCurrent_v2", "cuCtxPopCurrent"),
        "cuMemHostRegister_v2": ("cuMemHostRegister_v2", "cuMemHostRegister"),
        "cuMemAlloc_v2": ("cuMemAlloc_v2", "cuMemAlloc"),
        "cuMemFree_v2": ("cuMemFree_v2", "cuMemFree"),
        "cuStreamDestroy_v2": ("cuStreamDestroy_v2", "cuStreamDestroy"),
        "cuEventDestroy_v2": ("cuEventDestroy_v2", "cuEventDestroy"),
        "cuMemcpyHtoDAsync_v2": ("cuMemcpyHtoDAsync_v2", "cuMemcpyHtoDAsync"),
        "cuMemcpyDtoH_v2": ("cuMemcpyDtoH_v2", "cuMemcpyDtoH"),
    }
    resolved: dict[str, Any] = {}
    for key, (argtypes, restype) in protos.items():
        fn = sym(*aliases.get(key, (key,)))
        fn.argtypes = argtypes
        fn.restype = restype
        resolved[key] = fn
    _DRIVER["lib"] = resolved
    return resolved


def _check(rc: int, what: str) -> None:
    if rc != _CUDA_SUCCESS:
        raise RuntimeError(f"cuda_{what}_failed:rc={rc}")


_CUDA_ERROR_NOT_READY = 600


def _wait_event(lib: Any, event: Any, timeout_s: float) -> bool:
    """Bounded completion wait; never blocks past timeout_s."""
    deadline = time.monotonic() + timeout_s
    while True:
        rc = lib["cuEventQuery"](event)
        if rc == _CUDA_SUCCESS:
            return True
        if rc != _CUDA_ERROR_NOT_READY:
            return False
        if time.monotonic() > deadline:
            return False
        time.sleep(0.0005)


def _cuda_context() -> dict[str, Any]:
    """cuInit + device 0 + a fresh context on the calling thread."""
    lib = _load_driver()
    _check(lib["cuInit"](0), "cuInit")
    dev = ctypes.c_int()
    _check(lib["cuDeviceGet"](ctypes.byref(dev), 0), "cuDeviceGet")
    name = ctypes.create_string_buffer(128)
    lib["cuDeviceGetName"](name, 128, dev)
    ctx = ctypes.c_void_p()
    _check(lib["cuCtxCreate_v2"](ctypes.byref(ctx), 0, dev), "cuCtxCreate")
    return {
        "lib": lib,
        "ctx": ctx,
        "device_name": name.value.decode("utf-8", "replace").split("\x00")[0],
    }


def setup_cuda(staging: dict[str, Any], mode: str, gpu_bytes: int = 0) -> dict[str, Any]:
    """Post-fork, pre-source CUDA setup, called from the harness ``on_ready`` hook.

    Pins the shared staging via cuMemHostRegister and, for ``h2d``, allocates the
    single GPU destination and the single non-blocking stream.  The context is
    popped from the calling thread so the H2D consumer can make it current.
    """
    rt = _cuda_context()
    lib = rt["lib"]
    setup_t0 = time.perf_counter()
    t0 = time.perf_counter()
    _check(lib["cuMemHostRegister_v2"](
        ctypes.c_void_p(int(staging["seg_base"])),
        ctypes.c_size_t(int(staging["bytes"])),
        ctypes.c_uint(0)), "cuMemHostRegister")
    register_ms = (time.perf_counter() - t0) * 1000.0

    info: dict[str, Any] = {
        "device_name": rt["device_name"],
        "registered": True,
        "register_ms": register_ms,
        "register_bytes": int(staging["bytes"]),
    }
    cuda: dict[str, Any] = {"lib": lib, "ctx": rt["ctx"], "device_name": rt["device_name"]}
    if mode == "h2d":
        alloc_t0 = time.perf_counter()
        dptr = ctypes.c_uint64(0)
        _check(lib["cuMemAlloc_v2"](ctypes.byref(dptr), ctypes.c_size_t(int(gpu_bytes))), "cuMemAlloc")
        alloc_ms = (time.perf_counter() - alloc_t0) * 1000.0
        stream = ctypes.c_void_p()
        _check(lib["cuStreamCreate"](ctypes.byref(stream), ctypes.c_uint(1)), "cuStreamCreate")
        cuda.update({"dptr": int(dptr.value), "stream": stream, "gpu_bytes": int(gpu_bytes)})
        info.update({"gpu_bytes": int(gpu_bytes), "gpu_alloc": True, "gpu_alloc_ms": alloc_ms,
                     "stream_created": True})
    info["setup_ms"] = (time.perf_counter() - setup_t0) * 1000.0
    staging["_cuda"] = cuda
    popped = ctypes.c_void_p()
    lib["cuCtxPopCurrent_v2"](ctypes.byref(popped))
    return info


def build_staging(qd: int, slots: int, read_bytes: int) -> dict[str, Any]:
    """Allocate one POSIX shared-memory staging region for ``qd`` reader lanes."""
    import multiprocessing as mp

    qd = int(qd)
    slots = int(slots)
    read_bytes = int(read_bytes)
    if qd < 1 or slots < 1 or read_bytes < 1:
        raise ValueError("qd, slots and read_bytes must be positive")
    lane_bytes = slots * read_bytes
    total = qd * lane_bytes
    buf = mp.RawArray(ctypes.c_char, total)
    return {
        "enabled": True,
        "seg_base": int(ctypes.addressof(buf)),
        "slots": slots,
        "lane_bytes": lane_bytes,
        "read_bytes": read_bytes,
        "bytes": total,
        "published": [mp.Value("q", 0, lock=False) for _ in range(qd)],
        "consumed": [mp.Value("q", 0, lock=False) for _ in range(qd)],
        "slot_off": [mp.Array("q", slots, lock=False) for _ in range(qd)],
        "slot_len": [mp.Array("q", slots, lock=False) for _ in range(qd)],
        "alive": mp.Value("i", 1, lock=False),
        "_buf": buf,
    }


def start_consumer(
    staging: dict[str, Any],
    qd: int,
    read_bytes: int,
    mode: str,
    verify: bool = False,
    file_path: str = "",
) -> tuple[threading.Thread, dict[str, Any]]:
    """Start the parent-side consumer for the requested mode."""
    if mode in ("shared", "registered"):
        return _start_release_thread(staging, int(qd))
    if mode == "h2d":
        return _start_h2d_thread(staging, int(qd), bool(verify), str(file_path))
    raise ValueError(f"unsupported staging consumer mode: {mode}")


def _start_release_thread(staging: dict[str, Any], qd: int) -> tuple[threading.Thread, dict[str, Any]]:
    """Release each lane's consumed counter so a reader can reuse a slot."""
    state: dict[str, Any] = {"released": 0, "max_lag": 0, "wall_ms": None}

    def _run() -> None:
        started = time.perf_counter()
        while True:
            progressed = False
            for lane in range(qd):
                pub = int(staging["published"][lane].value)
                con = int(staging["consumed"][lane].value)
                if pub > con:
                    staging["consumed"][lane].value = pub
                    state["released"] += pub - con
                    progressed = True
            lag = 0
            for lane in range(qd):
                lane_lag = int(staging["published"][lane].value) - int(staging["consumed"][lane].value)
                if lane_lag > lag:
                    lag = lane_lag
            if lag > state["max_lag"]:
                state["max_lag"] = lag
            if not progressed and int(staging["alive"].value) == 0:
                break
            time.sleep(0.0002)
        state["wall_ms"] = (time.perf_counter() - started) * 1000.0

    thread = threading.Thread(target=_run, name="staging-release", daemon=True)
    thread.start()
    return thread, state


def _start_h2d_thread(
    staging: dict[str, Any],
    qd: int,
    verify: bool,
    file_path: str,
) -> tuple[threading.Thread, dict[str, Any]]:
    """DMA each published block to the GPU on one stream; fresh event per transfer."""
    seg_base = int(staging["seg_base"])
    lane_bytes = int(staging["lane_bytes"])
    read_bytes = int(staging["read_bytes"])
    slots = int(staging["slots"])

    state: dict[str, Any] = {
        "released": 0, "max_lag": 0, "wall_ms": None,
        "transfers": 0, "h2d_bytes": 0, "h2d_active_ms": 0.0, "h2d_max_ms": 0.0,
        "last_done_ns": None, "coverage_offsets": 0, "coverage_bytes": 0,
        "coverage_exact": None, "verified": False,
    }

    def _run() -> None:
        started = time.perf_counter()
        # setup_cuda() runs in the harness on_ready hook, i.e. after this thread
        # starts but before the readers are released; wait for it to install the
        # context/stream/destination.
        while "_cuda" not in staging and int(staging["alive"].value) == 1:
            time.sleep(0.0005)
        if "_cuda" not in staging:
            state["error"] = "cuda_setup_missing"
            return
        cuda = staging["_cuda"]
        lib = cuda["lib"]
        ctx = cuda["ctx"]
        dptr = int(cuda["dptr"])
        stream = cuda["stream"]
        gpu_bytes = int(cuda["gpu_bytes"])
        _check(lib["cuCtxSetCurrent"](ctx), "cuCtxSetCurrent")
        consumed = [0] * qd
        next_issue = [0] * qd
        pending: collections.deque = collections.deque()
        offsets: dict[int, int] = {}
        while True:
            issued = False
            for lane in range(qd):
                pub = int(staging["published"][lane].value)
                while next_issue[lane] < pub and (next_issue[lane] - consumed[lane]) < slots:
                    seq = next_issue[lane]
                    slot = seq % slots
                    off = int(staging["slot_off"][lane][slot])
                    ln = int(staging["slot_len"][lane][slot])
                    host = seg_base + lane * lane_bytes + slot * read_bytes
                    start_ev = ctypes.c_void_p()
                    done_ev = ctypes.c_void_p()
                    _check(lib["cuEventCreate"](ctypes.byref(start_ev), ctypes.c_uint(0)), "cuEventCreate")
                    _check(lib["cuEventCreate"](ctypes.byref(done_ev), ctypes.c_uint(0)), "cuEventCreate")
                    _check(lib["cuEventRecord"](start_ev, stream), "cuEventRecord")
                    _check(lib["cuMemcpyHtoDAsync_v2"](
                        ctypes.c_uint64(dptr + off), ctypes.c_void_p(host),
                        ctypes.c_size_t(ln), stream), "cuMemcpyHtoDAsync")
                    _check(lib["cuEventRecord"](done_ev, stream), "cuEventRecord")
                    pending.append((lane, seq, off, ln, start_ev, done_ev))
                    next_issue[lane] += 1
                    issued = True
                    state["transfers"] += 1
                    state["h2d_bytes"] += ln
                    offsets[off] = offsets.get(off, 0) + 1
            if pending:
                lane, seq, off, ln, start_ev, done_ev = pending.popleft()
                if not _wait_event(lib, done_ev, 30.0):
                    state["error"] = f"h2d_event_timeout:lane={lane}:seq={seq}"
                    break
                elapsed = ctypes.c_float(0.0)
                if lib["cuEventElapsedTime"](ctypes.byref(elapsed), start_ev, done_ev) == _CUDA_SUCCESS:
                    state["h2d_active_ms"] += float(elapsed.value)
                    state["h2d_max_ms"] = max(state["h2d_max_ms"], float(elapsed.value))
                state["last_done_ns"] = time.perf_counter_ns()
                consumed[lane] = seq + 1
                staging["consumed"][lane].value = seq + 1
                state["released"] += 1
                lib["cuEventDestroy_v2"](start_ev)
                lib["cuEventDestroy_v2"](done_ev)
                continue
            if not issued:
                if int(staging["alive"].value) == 0:
                    done = all(
                        int(staging["published"][lane].value) <= consumed[lane]
                        for lane in range(qd))
                    if done:
                        break
                time.sleep(0.0002)
        # Never leave a reader blocked on a slot, even if H2D failed.
        for lane in range(qd):
            staging["consumed"][lane].value = int(staging["published"][lane].value)
        state["wall_ms"] = (time.perf_counter() - started) * 1000.0

        state["coverage_offsets"] = len(offsets)
        dupes = [[off, count] for off, count in offsets.items() if count != 1]
        state["coverage_exact"] = (not dupes)
        if dupes:
            state["coverage_dupes"] = dupes[:16]

        if verify and file_path:
            try:
                gpu_sha = _hash_gpu(lib, dptr, gpu_bytes)
                file_sha = _hash_file(file_path)
                state["gpu_sha256"] = gpu_sha
                state["file_sha256"] = file_sha
                state["sha_match"] = (gpu_sha == file_sha)
                state["verified"] = True
            except Exception as exc:  # noqa: BLE001
                state["verify_error"] = f"{type(exc).__name__}:{str(exc)[:300]}"

        if not state.get("error"):
            lib["cuStreamSynchronize"](stream)
            lib["cuStreamDestroy_v2"](stream)
            lib["cuMemFree_v2"](ctypes.c_uint64(dptr))
            lib["cuMemHostUnregister"](ctypes.c_void_p(seg_base))

    thread = threading.Thread(target=_run, name="staging-h2d", daemon=True)
    thread.start()
    return thread, state


def _hash_file(path: str, chunk: int = 64 * 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def _hash_gpu(lib: Any, dptr: int, gpu_bytes: int, chunk: int = 64 * 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    buf = ctypes.create_string_buffer(chunk)
    off = 0
    while off < gpu_bytes:
        n = min(chunk, gpu_bytes - off)
        _check(lib["cuMemcpyDtoH_v2"](
            ctypes.addressof(buf), ctypes.c_uint64(dptr + off), ctypes.c_size_t(n)), "cuMemcpyDtoH")
        hasher.update(ctypes.string_at(ctypes.addressof(buf), n))
        off += n
    return hasher.hexdigest()
