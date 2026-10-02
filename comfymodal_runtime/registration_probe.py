from __future__ import annotations

import ctypes
import mmap
import os
import time
from multiprocessing import shared_memory
from typing import Any


def _driver() -> dict[str, Any]:
    lib = ctypes.CDLL("libcuda.so.1")
    ci = ctypes.c_int
    cp = ctypes.c_void_p
    cu64 = ctypes.c_uint64
    lib.cuInit.argtypes = [ctypes.c_uint]
    lib.cuInit.restype = ci
    lib.cuDeviceGet.argtypes = [ctypes.POINTER(ci), ci]
    lib.cuDeviceGet.restype = ci
    lib.cuCtxCreate_v2.argtypes = [ctypes.POINTER(cp), ctypes.c_uint, ci]
    lib.cuCtxCreate_v2.restype = ci
    lib.cuCtxDestroy_v2.argtypes = [cp]
    lib.cuCtxDestroy_v2.restype = ci
    lib.cuMemHostRegister_v2.argtypes = [cp, ctypes.c_size_t, ctypes.c_uint]
    lib.cuMemHostRegister_v2.restype = ci
    lib.cuMemHostUnregister.argtypes = [cp]
    lib.cuMemHostUnregister.restype = ci
    return {"lib": lib, "ci": ci, "cp": cp, "device": None}


def _check(rc: int, name: str) -> None:
    if int(rc) != 0:
        raise RuntimeError(f"{name}_failed:{int(rc)}")


def _primary_context(device_index: int) -> dict[str, Any]:
    rt = _driver()
    lib = rt["lib"]
    device = rt["ci"]()
    _check(lib.cuInit(0), "cuInit")
    _check(lib.cuDeviceGet(ctypes.byref(device), rt["ci"](int(device_index))), "cuDeviceGet")
    lib.cuDevicePrimaryCtxRetain.argtypes = [ctypes.POINTER(rt["cp"]), rt["ci"]]
    lib.cuDevicePrimaryCtxRetain.restype = rt["ci"]
    lib.cuCtxSetCurrent.argtypes = [rt["cp"]]
    lib.cuCtxSetCurrent.restype = rt["ci"]
    context = rt["cp"]()
    _check(lib.cuDevicePrimaryCtxRetain(ctypes.byref(context), device), "cuDevicePrimaryCtxRetain")
    _check(lib.cuCtxSetCurrent(context), "cuCtxSetCurrent")
    return {"device": int(device.value), "context": hex(int(context.value or 0))}


def _fresh_driver_context(device_index: int) -> dict[str, Any]:
    rt = _driver()
    lib = rt["lib"]
    device = rt["ci"]()
    _check(lib.cuInit(0), "cuInit")
    _check(lib.cuDeviceGet(ctypes.byref(device), rt["ci"](int(device_index))), "cuDeviceGet")
    context = rt["cp"]()
    _check(lib.cuCtxCreate_v2(ctypes.byref(context), 0, device), "cuCtxCreate")
    return {"runtime": rt, "device": int(device.value), "context": hex(int(context.value or 0)), "handle": context}


def _mapping(kind: str, size: int) -> tuple[Any, int, dict[str, Any]]:
    if kind == "posix_shm":
        owner = shared_memory.SharedMemory(create=True, size=size)
        return owner, int(ctypes.addressof(ctypes.c_char.from_buffer(owner.buf))), {"type": kind, "name": owner.name}
    flags = mmap.MAP_SHARED if kind == "anonymous_shared" else mmap.MAP_PRIVATE
    flags |= getattr(mmap, "MAP_ANONYMOUS", 0x20)
    owner = mmap.mmap(-1, size, flags=flags, prot=mmap.PROT_READ | mmap.PROT_WRITE)
    return owner, int(ctypes.addressof(ctypes.c_char.from_buffer(owner))), {"type": kind}


def _raw_array(size: int) -> tuple[Any, int, dict[str, Any]]:
    import multiprocessing as mp

    owner = mp.RawArray(ctypes.c_char, size)
    return owner, int(ctypes.addressof(owner)), {"type": "historical_m2_anonymous_shared_rawarray"}


def _register_current(owner: Any, address: int, size: int, device_index: int) -> dict[str, Any]:
    import torch

    _primary = _primary_context(device_index)
    cudart = torch.cuda.cudart()
    register = getattr(cudart, "cudaHostRegister")
    unregister = getattr(cudart, "cudaHostUnregister")
    before = time.monotonic_ns()
    rc = int(register(address, size, 0))
    after = time.monotonic_ns()
    if rc != 0:
        raise RuntimeError(f"cudaHostRegister_failed:{rc}")
    unregister(address)
    return {
        "api": "torch.cuda.cudart().cudaHostRegister",
        "flags": 0,
        "register_ms": (after - before) / 1e6,
        "context": _primary,
        "torch_version": str(torch.__version__),
        "torch_cuda_version": str(torch.version.cuda),
        "device_name": str(torch.cuda.get_device_name(device_index)),
    }


def _register_historical(owner: Any, address: int, size: int, device_index: int) -> dict[str, Any]:
    import ctypes as ct

    fresh = _fresh_driver_context(device_index)
    lib = fresh["runtime"]["lib"]
    before = time.monotonic_ns()
    _check(lib.cuMemHostRegister_v2(ct.c_void_p(address), ct.c_size_t(size), ct.c_uint(0)), "cuMemHostRegister")
    after = time.monotonic_ns()
    _check(lib.cuMemHostUnregister(ct.c_void_p(address)), "cuMemHostUnregister")
    _check(lib.cuCtxDestroy_v2(fresh["handle"]), "cuCtxDestroy")
    return {
        "api": "cuMemHostRegister_v2",
        "flags": 0,
        "register_ms": (after - before) / 1e6,
        "context": {"type": "fresh_raw_driver_context", "device": fresh["device"], "context": fresh["context"]},
    }


def run_registration_probe(*, mapping_kind: str, size_mib: int = 320, device_index: int = 0) -> dict[str, Any]:
    allowed = {"posix_shm", "anonymous_shared", "anonymous_private", "historical_m2"}
    if mapping_kind not in allowed:
        raise ValueError(f"mapping_kind_invalid:{mapping_kind}")
    size = int(size_mib) * 1024 * 1024
    started = time.monotonic_ns()
    owner = None
    try:
        owner, address, mapping = (
            _raw_array(size) if mapping_kind == "historical_m2" else _mapping(mapping_kind, size)
        )
        if mapping_kind == "historical_m2":
            registration = _register_historical(owner, address, size, device_index)
        else:
            registration = _register_current(owner, address, size, device_index)
        registration.update({
            "status": "ok",
            "mapping": mapping,
            "size_bytes": size,
            "pointer": address,
            "alignment": {"mod_4k": address % 4096, "mod_64k": address % 65536, "mod_2m": address % (2 * 1024 * 1024)},
            "wall_total_ms": (time.monotonic_ns() - started) / 1e6,
            "pid": os.getpid(),
        })
        return registration
    finally:
        if isinstance(owner, shared_memory.SharedMemory):
            owner.close()
            owner.unlink()
        elif hasattr(owner, "close"):
            owner.close()
