"""Minimal additive shareable-host-staging support for the frozen mmap source harness.

This module is intentionally small and is *only* used when the caller opts in.
When it is not used, ``run_mmap_lifecycle_probe`` follows its original private
destination path byte-for-byte.

Slices:
  * staging: four QD4 reader processes write the 64 MiB blocks they already read
    into a POSIX shared-memory region (``/dev/shm`` backed, fork-inherited)
    instead of process-private bytearrays.  A release consumer in the CUDA-owning
    parent process advances each lane's ``consumed`` counter so a reader can
    reuse a slot.  No CUDA is involved.
  * registered: the same, with the staging region pinned via ``cuMemHostRegister``
    (the driver-API equivalent of ``cudaHostRegister``).  No bytes are copied to
    the GPU.
  * h2d (later slice): each published block is ``cuMemcpyHtoDAsync``'d to one GPU
    buffer on one stream, with a fresh completion event per transfer.

Staging layout: ``qd`` lanes; each lane owns ``slots`` slots of ``read_bytes``.
A lane's slot ``k`` is the block with per-lane publish sequence ``k % slots``.
A reader may only write sequence ``s`` when ``s - consumed < slots``; it
publishes ``s + 1`` only after the native memcpy has fully returned.

CUDA is initialized by the caller in the parent **after** the reader fork but
**before** the readers are released (the harness ``on_ready`` hook), so no CUDA
context is ever inherited by a reader child and no registration cost lands on
the source critical path.  The created context is popped from the current thread
so the later H2D consumer can make it current itself.  All control counters use
``lock=False`` shared primitives (one writer, one reader per lane) so a fork can
never inherit a locked primitive.
"""

from __future__ import annotations

import ctypes
import threading
import time
from typing import Any

_DRIVER: dict[str, Any] = {"lib": None}


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

    ci, cp, cv, cs = ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t
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
    }
    aliases = {
        "cuCtxCreate_v2": ("cuCtxCreate_v2", "cuCtxCreate"),
        "cuCtxDestroy_v2": ("cuCtxDestroy_v2", "cuCtxDestroy"),
        "cuCtxPopCurrent_v2": ("cuCtxPopCurrent_v2", "cuCtxPopCurrent"),
        "cuMemHostRegister_v2": ("cuMemHostRegister_v2", "cuMemHostRegister"),
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
    if rc != 0:
        raise RuntimeError(f"cuda_{what}_failed:rc={rc}")


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


def register_staging_now(staging: dict[str, Any]) -> dict[str, Any]:
    """Pin the shared staging region with cuMemHostRegister (cudaHostRegister).

    Called from the harness ``on_ready`` hook: after the reader fork and before
    the readers are released.  The CUDA context is popped from the calling thread
    so a later consumer thread can make it current itself.
    """
    rt = _cuda_context()
    lib = rt["lib"]
    t0 = time.perf_counter()
    rc = lib["cuMemHostRegister_v2"](
        ctypes.c_void_p(int(staging["seg_base"])),
        ctypes.c_size_t(int(staging["bytes"])),
        ctypes.c_uint(0),
    )
    register_ms = (time.perf_counter() - t0) * 1000.0
    _check(rc, "cuMemHostRegister")
    popped = ctypes.c_void_p()
    lib["cuCtxPopCurrent_v2"](ctypes.byref(popped))
    staging["_cuda"] = {"lib": lib, "ctx": rt["ctx"], "device_name": rt["device_name"]}
    return {
        "device_name": rt["device_name"],
        "registered": True,
        "register_ms": register_ms,
        "bytes": int(staging["bytes"]),
    }


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
) -> tuple[threading.Thread, dict[str, Any]]:
    """Start the parent-side slot-release consumer (shared and registered modes).

    ``registered`` registration itself is performed by ``register_staging_now``
    from the harness ``on_ready`` hook, not here.  ``h2d`` is added by the later
    slice and reuses the same seam.
    """
    if mode in ("shared", "registered"):
        return _start_release_thread(staging, int(qd))
    raise ValueError(f"unsupported staging consumer mode: {mode}")


def _start_release_thread(
    staging: dict[str, Any],
    qd: int,
) -> tuple[threading.Thread, dict[str, Any]]:
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
