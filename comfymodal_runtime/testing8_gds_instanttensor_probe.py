"""TESTING8-only native GDS and InstantTensor probes.

This module is lazy-loaded by a diagnostic Modal method. It does not participate
in model loading or Golden execution.
"""

from __future__ import annotations

import contextlib
import ctypes.util
import hashlib
import importlib
import importlib.metadata
import inspect
import io
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Any, Iterator, cast


CLIP_PATH = "/root/models/text_encoders/qwen_3_4b.safetensors"
UNET_PATH = "/root/models/diffusion_models/z_image_turbo_bf16.safetensors"
GDS_BYTES = 64 * 1024 * 1024
INSTANT_CHUNK = 64 * 1024 * 1024
INSTANT_DEPTH = 4
INSTANT_BUFFER = INSTANT_CHUNK * INSTANT_DEPTH


def _run(command: list[str], *, timeout: float = 20.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
        return {
            "argv": command,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "argv": command,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def _which(name: str) -> str | None:
    return shutil.which(name)


def _read_text(path: str, limit: int = 20000) -> str | None:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return None


def _path_info(path: str) -> dict[str, Any]:
    out: dict[str, Any] = {"path": path, "exists": os.path.exists(path)}
    try:
        st = os.stat(path)
        out.update({
            "mode": stat.filemode(st.st_mode),
            "size": st.st_size,
            "is_regular": stat.S_ISREG(st.st_mode),
        })
    except OSError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _model_header(path: str) -> dict[str, Any]:
    with open(path, "rb") as handle:
        header_len = int.from_bytes(handle.read(8), "little")
        header = json.loads(handle.read(header_len))
    tensors = {
        name: value for name, value in header.items()
        if isinstance(value, dict) and "data_offsets" in value
    }
    total = sum(int(value["data_offsets"][1]) - int(value["data_offsets"][0])
                for value in tensors.values())
    return {"tensor_names": sorted(tensors), "tensor_count": len(tensors), "tensor_bytes": total}


def _collect_capability(path: str) -> dict[str, Any]:
    env = {
        key: value for key, value in os.environ.items()
        if any(token in key.upper() for token in ("MODAL", "CUDA", "NVIDIA", "PROVIDER", "REGION"))
        and not any(token in key.upper() for token in ("TOKEN", "SECRET", "IDENTITY", "AUTH", "PASSWORD"))
    }
    cufile_paths: list[str] = []
    for root in ("/usr/local/cuda", "/usr/local/cuda-13.0", "/usr/local/cuda-12.8"):
        candidate = os.path.join(root, "lib64", "libcufile.so")
        if os.path.exists(candidate):
            cufile_paths.append(candidate)
    found = ctypes.util.find_library("cufile")
    if found and found not in cufile_paths:
        cufile_paths.append(found)
    header_paths = [
        candidate for candidate in (
            "/usr/local/cuda/include/cufile.h",
            "/usr/local/cuda-13.0/include/cufile.h",
            "/usr/local/cuda-12.8/include/cufile.h",
        ) if os.path.exists(candidate)
    ]
    commands = {
        "uname": _run(["uname", "-a"]),
        "proc_version": _run(["cat", "/proc/version"]),
        "cgroup": _run(["cat", "/proc/1/cgroup"]),
        "gpu": _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]),
        "cuda_runtime": _run(["nvcc", "--version"]),
        "gdscheck": _run(["gdscheck", "-p"]) if _which("gdscheck") else None,
        "mount": _run(["findmnt", "-T", path, "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"]),
        "statfs": _run(["stat", "-f", "-c", "%T %S %B", path]),
        "cufile_ldconfig": _run(["sh", "-lc", "ldconfig -p 2>/dev/null | grep -i libcufile || true"]),
    }
    return {
        "provider_region_env": env,
        "model": _path_info(path),
        "filesystem": {
            "mount_command": commands["mount"],
            "statfs_command": commands["statfs"],
        },
        "gpu": commands["gpu"],
        "kernel_gvisor": {
            "uname": commands["uname"],
            "proc_version": commands["proc_version"],
            "cgroup": commands["cgroup"],
        },
        "cuda_runtime": commands["cuda_runtime"],
        "libcufile": {
            "ctypes_find": found,
            "paths": cufile_paths,
            "ldconfig": commands["cufile_ldconfig"],
        },
        "cufile_header": {"paths": header_paths},
        "cufile_config": {
            "path": "/etc/cufile.json",
            "readable": os.access("/etc/cufile.json", os.R_OK),
            "content": _read_text("/etc/cufile.json"),
        },
        "gdscheck": commands["gdscheck"],
        "nvidia_fs": {
            "proc": _path_info("/proc/driver/nvidia-fs"),
            "module": _run(["sh", "-lc", "lsmod 2>/dev/null | grep -i nvidia_fs || true"]),
        },
        "devices": {
            path: _path_info(path)
            for path in ("/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm", "/dev/nvidia-fs", "/dev/cufile")
        },
    }


_GDS_HELPER = r'''
#define _GNU_SOURCE
#include <cuda.h>
#include <cufile.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/types.h>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <iostream>
#include <chrono>

static void err_json(const char* name, CUfileError_t e) {
  std::cout << "\"" << name << "_err\":{\"err\":"
            << static_cast<int>(e.err) << ",\"cu_err\":"
            << static_cast<int>(e.cu_err) << "},";
}

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const char* path = argv[1];
  const size_t bytes = 64ULL * 1024ULL * 1024ULL;
  int fd = -1;
  CUfileHandle_t fh{};
  CUdeviceptr device = 0;
  CUcontext context = nullptr;
  bool driver_open = false, handle_registered = false, buffer_registered = false;
  CUfileError_t e{};
  std::cout << "{";
  e = cuFileDriverOpen();
  err_json("driver_open", e);
  std::cout << "\"driver_open_ok\":" << (e.err == CU_FILE_SUCCESS ? "true" : "false") << ",";
  if (e.err != CU_FILE_SUCCESS) { std::cout << "\"native_success\":false}"; return 0; }
  driver_open = true;
  CUresult cr = cuInit(0);
  std::cout << "\"cu_init\":" << static_cast<int>(cr) << ",";
  CUdevice dev{};
  cr = cuDeviceGet(&dev, 0);
  std::cout << "\"cu_device_get\":" << static_cast<int>(cr) << ",";
  cr = cuCtxCreate(&context, nullptr, 0, dev);
  std::cout << "\"cu_ctx_create\":" << static_cast<int>(cr) << ",";
  if (cr != CUDA_SUCCESS) { std::cout << "\"native_success\":false}"; cuFileDriverClose(); return 0; }
  fd = open(path, O_RDONLY | O_DIRECT);
  std::cout << "\"open_errno\":" << (fd < 0 ? errno : 0) << ",";
  if (fd < 0) { std::cout << "\"native_success\":false}"; cuCtxDestroy(context); cuFileDriverClose(); return 0; }
  CUfileDescr_t desc{};
  desc.type = CU_FILE_HANDLE_TYPE_OPAQUE_FD;
  desc.handle.fd = fd;
  e = cuFileHandleRegister(&fh, &desc);
  err_json("handle_register", e);
  std::cout << "\"handle_register_ok\":" << (e.err == CU_FILE_SUCCESS ? "true" : "false") << ",";
  if (e.err != CU_FILE_SUCCESS) { close(fd); cuCtxDestroy(context); cuFileDriverClose(); std::cout << "\"native_success\":false}"; return 0; }
  handle_registered = true;
  cr = cuMemAlloc(&device, bytes);
  std::cout << "\"cu_mem_alloc\":" << static_cast<int>(cr) << ",";
  if (cr != CUDA_SUCCESS) { cuFileHandleDeregister(fh); close(fd); cuCtxDestroy(context); cuFileDriverClose(); std::cout << "\"native_success\":false}"; return 0; }
  e = cuFileBufRegister(reinterpret_cast<void*>(device), bytes, 0);
  err_json("buffer_register", e);
  std::cout << "\"buffer_register_ok\":" << (e.err == CU_FILE_SUCCESS ? "true" : "false") << ",";
  buffer_registered = e.err == CU_FILE_SUCCESS;
  cr = cuCtxSynchronize();
  auto t0 = std::chrono::steady_clock::now();
  ssize_t got = cuFileRead(fh, reinterpret_cast<void*>(device), bytes, 0, 0);
  cr = cuCtxSynchronize();
  auto t1 = std::chrono::steady_clock::now();
  double wall_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
  std::cout << "\"cu_file_read_return\":" << static_cast<long long>(got) << ",";
  std::cout << "\"cu_file_read_errno\":" << (got < 0 ? errno : 0) << ",";
  std::cout << "\"cuda_sync_after_read\":" << static_cast<int>(cr) << ",";
  std::cout << "\"transfer_wall_ms\":" << wall_ms << ",";
  bool correct = false;
  if (got == static_cast<ssize_t>(bytes)) {
    void* expected = nullptr;
    void* actual = nullptr;
    if (posix_memalign(&expected, 4096, bytes) == 0 && posix_memalign(&actual, 4096, bytes) == 0) {
      int vf = open(path, O_RDONLY);
      ssize_t read_back = vf >= 0 ? pread(vf, expected, bytes, 0) : -1;
      if (vf >= 0) close(vf);
      CUresult copy_cr = cuMemcpyDtoH(actual, device, bytes);
      if (read_back == static_cast<ssize_t>(bytes) && copy_cr == CUDA_SUCCESS)
        correct = std::memcmp(expected, actual, bytes) == 0;
      std::free(expected); std::free(actual);
    }
  }
  std::cout << "\"correctness\":" << (correct ? "true" : "false") << ",";
  std::cout << "\"native_success\":" << (got == static_cast<ssize_t>(bytes) && correct ? "true" : "false") << "}";
  if (buffer_registered) cuFileBufDeregister(reinterpret_cast<void*>(device));
  if (handle_registered) cuFileHandleDeregister(fh);
  if (device) cuMemFree(device);
  close(fd);
  if (context) cuCtxDestroy(context);
  if (driver_open) cuFileDriverClose();
  return 0;
}
'''


def _strict_gds(path: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "phase": "native_gds",
        "model_path": path,
        "compat_mode_disabled": False,
        "status": "inconclusive",
    }
    result["capability"] = _collect_capability(path)
    with tempfile.TemporaryDirectory(prefix="testing8-gds-") as temp:
        config_path = os.path.join(temp, "cufile.json")
        config = {
            "logging": {"level": "INFO"},
            "properties": {"allow_compat_mode": False, "force_compat_mode": False},
        }
        pathlib.Path(config_path).write_text(json.dumps(config), encoding="utf-8")
        result["strict_config"] = {
            "path": config_path,
            "content": config,
            "env": {
                "CUFILE_ENV_PATH_JSON": config_path,
                "CUFILE_FORCE_COMPAT_MODE": "false",
            },
        }
        env = os.environ.copy()
        env.update({
            "CUFILE_ENV_PATH_JSON": config_path,
            "CUFILE_FORCE_COMPAT_MODE": "false",
        })
        compiler = _which("g++") or _which("clang++")
        header_paths = (result["capability"].get("cufile_header") or {}).get("paths") or []
        lib_paths = (result["capability"].get("libcufile") or {}).get("paths") or []
        result["compile"] = {"compiler": compiler, "header_paths": header_paths, "library_paths": lib_paths}
        if compiler and header_paths and lib_paths:
            source = os.path.join(temp, "gds_probe.cc")
            binary = os.path.join(temp, "gds_probe")
            pathlib.Path(source).write_text(_GDS_HELPER, encoding="utf-8")
            include = os.path.dirname(header_paths[0])
            libdir = os.path.dirname(lib_paths[0]) if "/" in lib_paths[0] else "/usr/local/cuda/lib64"
            compile_result = _run([
                compiler, source, "-std=c++17", "-O2", "-I", include,
                "-L", libdir, "-Wl,-rpath," + libdir, "-lcufile", "-lcuda",
                "-o", binary,
            ], timeout=60)
            result["compile"]["result"] = compile_result
            if compile_result.get("returncode") == 0:
                proc = subprocess.run([binary, path], capture_output=True, text=True,
                                      env=env, timeout=120, check=False)
                result["helper"] = {
                    "returncode": proc.returncode,
                    "stdout": proc.stdout[-20000:],
                    "stderr": proc.stderr[-20000:],
                }
                try:
                    helper_json = json.loads(proc.stdout)
                    result["helper"]["parsed"] = helper_json
                    result["compat_mode_disabled"] = True
                    result["status"] = "yes" if helper_json.get("native_success") else "no"
                except Exception as exc:  # noqa: BLE001
                    result["helper"]["parse_error"] = f"{type(exc).__name__}: {exc}"
        else:
            result["compile"]["skip_reason"] = "missing compiler, cufile.h, or libcufile"
    return result


def _package_source(package: Any) -> tuple[str, list[str]]:
    root = pathlib.Path(getattr(package, "__file__", "")).resolve().parent
    files: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".pyi", ".cpp", ".h", ".cc"}:
            files.append(str(path))
    return str(root), files


def _inspect_instanttensor() -> dict[str, Any]:
    out: dict[str, Any] = {"phase": "instanttensor_inspection", "status": "error"}
    try:
        package = importlib.import_module("instanttensor")
        version = importlib.metadata.version("instanttensor")
        root, files = _package_source(package)
        backend_objects: dict[str, Any] = {}
        for module_name in ("instanttensor", "instanttensor._impl"):
            try:
                module = importlib.import_module(module_name)
                backend = getattr(module, "Backend", None)
                if backend is not None:
                    backend_objects[module_name] = {
                        name: str(getattr(backend, name))
                        for name in dir(backend) if name.upper() in {"AIO", "URING", "BUFFERED_AIO", "BUFFERED_URING"}
                    }
            except Exception as exc:  # noqa: BLE001
                backend_objects[module_name] = f"{type(exc).__name__}: {exc}"
        source_hits: list[dict[str, Any]] = []
        for filename in files:
            text = _read_text(filename, 500000) or ""
            lowered = text.lower()
            if any(token in lowered for token in ("copy=false", "copy = false", "copy", "ring", "uring", "aio")):
                lines = text.splitlines()
                hits = [
                    {"line": index + 1, "text": line[:240]}
                    for index, line in enumerate(lines)
                    if any(token in line.lower() for token in (
                        "copy", "ring", "backend", "aio", "uring", "buffer", "out", "dest",
                    ))
                ][:80]
                source_hits.append({"file": filename, "hits": hits})
        safe_open = getattr(package, "safe_open", None)
        out.update({
            "status": "ok",
            "version": version,
            "package_file": getattr(package, "__file__", None),
            "source_root": root,
            "safe_open_signature": str(inspect.signature(safe_open)) if safe_open else None,
            "backend_objects": backend_objects,
            "source_hits": source_hits,
            "public_names": sorted(name for name in dir(package)
                                    if any(token in name.lower() for token in ("backend", "buffer", "dest", "out", "tensor", "open"))),
        })
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out


def _resolve_backend(package: Any, name: str) -> tuple[Any, str]:
    for module_name in ("instanttensor", "instanttensor._impl"):
        module = importlib.import_module(module_name)
        backend = getattr(module, "Backend", None)
        if backend is None:
            continue
        value = getattr(backend, name.upper(), None)
        if value is not None:
            return value, f"{module_name}.Backend.{name.upper()}"
    raise RuntimeError(f"Backend.{name.upper()} is unavailable")


def _tensor_bytes(tensor: Any) -> int:
    return int(tensor.numel()) * int(tensor.element_size())


def _full_hash(path: str, backend_name: str) -> dict[str, Any]:
    import torch
    package = importlib.import_module("instanttensor")
    backend, backend_symbol = _resolve_backend(package, backend_name)
    kwargs = {
        "framework": "pt", "device": 0, "copy": False,
        "backend": backend, "buffer_size": INSTANT_BUFFER,
        "chunk_size": INSTANT_CHUNK, "io_depth": INSTANT_DEPTH,
    }
    digest = hashlib.sha256()
    names: list[str] = []
    total = 0
    with package.safe_open(path, **kwargs) as loader:
        iterator = getattr(loader, "tensors", None)
        if not callable(iterator):
            raise RuntimeError("InstantTensor loader has no tensors() iterator")
        for name, tensor in cast(Iterator[tuple[Any, Any]], iterator()):
            names.append(str(name))
            total += _tensor_bytes(tensor)
            digest.update(tensor.detach().to(device="cpu").contiguous().view(getattr(torch, "uint8")).numpy().tobytes())
    return {"backend_symbol": backend_symbol, "tensor_count": len(names),
            "tensor_bytes": total, "sha256": digest.hexdigest()}


def _instanttensor_run(path: str, backend_name: str, copy_mode: bool, validate: bool) -> dict[str, Any]:
    import torch
    package = importlib.import_module("instanttensor")
    package_version = importlib.metadata.version("instanttensor")
    signature = inspect.signature(package.safe_open)
    required = {"backend", "chunk_size", "io_depth", "copy"}
    missing = sorted(required - set(signature.parameters))
    if missing:
        return {"status": "invalid", "error": f"safe_open_missing_parameters:{missing}",
                "version": package_version}
    backend, backend_symbol = _resolve_backend(package, backend_name)
    kwargs = {
        "framework": "pt", "device": 0, "copy": bool(copy_mode),
        "backend": backend, "buffer_size": INSTANT_BUFFER,
        "chunk_size": INSTANT_CHUNK, "io_depth": INSTANT_DEPTH,
    }
    for key in list(kwargs):
        if key not in signature.parameters:
            kwargs.pop(key)
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    tensors: dict[str, Any] = {}
    setup_ms = first_ms = iteration_ms = sync_ms = 0.0
    count = total = 0
    first_name = ""
    actual_backend: dict[str, str] = {}
    t_total = time.perf_counter()
    with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
        t0 = time.perf_counter()
        loader = package.safe_open(path, **kwargs)
        with loader:
            setup_ms = (time.perf_counter() - t0) * 1000.0
            iterator = getattr(loader, "tensors", None)
            if not callable(iterator):
                return {"status": "invalid", "error": "no_tensors_iterator", "version": package_version}
            for attr in ("backend", "_backend", "backend_name", "_backend_name", "io_backend"):
                if hasattr(loader, attr):
                    actual_backend[attr] = repr(getattr(loader, attr))
            t_first = time.perf_counter()
            stream = cast(Iterator[tuple[Any, Any]], iterator())
            try:
                first_name, first_tensor = next(stream)
            except StopIteration:
                return {"status": "invalid", "error": "empty_tensor_iterator", "version": package_version}
            first_ms = (time.perf_counter() - t_first) * 1000.0
            count = 1
            total = _tensor_bytes(first_tensor)
            if copy_mode:
                tensors[str(first_name)] = first_tensor
            t_iter = time.perf_counter()
            for name, tensor in stream:
                count += 1
                total += _tensor_bytes(tensor)
                if copy_mode:
                    tensors[str(name)] = tensor
            iteration_ms = (time.perf_counter() - t_iter) * 1000.0
            t_sync = time.perf_counter()
            torch.cuda.synchronize()
            sync_ms = (time.perf_counter() - t_sync) * 1000.0
    total_ms = (time.perf_counter() - t_total) * 1000.0
    expected = _model_header(path)
    result: dict[str, Any] = {
        "status": "ok",
        "model_path": path,
        "model": "clip" if path == CLIP_PATH else "unet",
        "version": package_version,
        "backend_requested": backend_name.upper(),
        "backend_symbol": backend_symbol,
        "backend_observed": actual_backend,
        "backend_proof": "observed" if actual_backend else "requested_only",
        "copy": bool(copy_mode),
        "chunk_bytes": INSTANT_CHUNK,
        "buffer_bytes": INSTANT_BUFFER,
        "depth": INSTANT_DEPTH,
        "setup_ms": round(setup_ms, 4),
        "first_tensor_ms": round(first_ms, 4),
        "iteration_ms": round(iteration_ms, 4),
        "final_cuda_sync_ms": round(sync_ms, 4),
        "wall_ms": round(total_ms, 4),
        "tensor_count": count,
        "tensor_bytes": total,
        "expected": expected,
        "exact_shape_contract": count == expected["tensor_count"] and total == expected["tensor_bytes"],
        "gbps": round(total / (total_ms * 1e6), 4) if total_ms > 0 else 0.0,
        "stdout": captured_out.getvalue()[-8000:],
        "stderr": captured_err.getvalue()[-8000:],
        "cuda_memory": {},
    }
    try:
        result["cuda_memory"] = {
            "allocated": int(torch.cuda.memory_allocated()),
            "reserved": int(torch.cuda.memory_reserved()),
        }
    except Exception:
        pass
    if copy_mode and tensors:
        first = next(iter(tensors.values()))
        result["owning_storage_probe"] = {
            "first_data_ptr": int(first.data_ptr()),
            "first_storage_ptr": int(first.untyped_storage().data_ptr()),
            "post_context_access": int(first.reshape(-1)[0].item() * 0) == 0,
        }
        del tensors
    if validate:
        try:
            validation = _full_hash(path, backend_name)
            result["full_validation"] = validation
            result["full_validation_ok"] = (
                validation["tensor_count"] == expected["tensor_count"]
                and validation["tensor_bytes"] == expected["tensor_bytes"]
            )
        except Exception as exc:  # noqa: BLE001
            result["full_validation"] = {"error": f"{type(exc).__name__}: {exc}"}
            result["full_validation_ok"] = False
    if result["backend_proof"] != "observed":
        result["status"] = "invalid"
        result["error"] = "backend_not_observed_no_silent_fallback_proof"
    return result


def run_probe(*, operation: str, model_path: str = "", backend: str = "",
              copy_mode: bool = False, validate: bool = False) -> dict[str, Any]:
    if operation == "gds":
        return _strict_gds(CLIP_PATH)
    if operation == "inspect":
        return _inspect_instanttensor()
    if operation == "instanttensor":
        path = model_path or CLIP_PATH
        if path not in {CLIP_PATH, UNET_PATH}:
            return {"status": "invalid", "error": "model_path_not_allowlisted", "model_path": path}
        if backend.upper() not in {"AIO", "URING"}:
            return {"status": "invalid", "error": "backend_not_allowlisted", "backend": backend}
        try:
            return _instanttensor_run(path, backend, bool(copy_mode), bool(validate))
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}",
                    "model_path": path, "backend": backend, "copy": bool(copy_mode)}
    return {"status": "invalid", "error": f"unknown_operation:{operation}"}
