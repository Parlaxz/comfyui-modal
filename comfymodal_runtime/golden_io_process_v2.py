"""Golden I/O Process V2 — one shared host backing for the storage read.

Faithful two-process I/O extraction: the parent owns CUDA, H2D, and model
construction; a CUDA-sterile child only receives/writes bytes in one
process-shared host mapping.  The intended production path registers that
SAME mapping with CUDA (``cudaHostRegister``) so the parent H2Ds directly from
the bytes the child produced, with **no** shared-RAM -> second pinned-buffer
copy.

This module currently implements only the FIRST GATE:

    a focused, cheap remote probe that decides whether a *writable anonymous
    shared mapping* can be registered by the CUDA-owning parent and H2D'd at
    pinned-memory-class bandwidth on this Modal target.

The child is launched as a separate Python interpreter running a standard
library-only program (no torch, no CUDA).  It writes a deterministic pattern
into the shared mapping and reports its own byte hash; the parent independently
hashes the same mapping, registers it, H2Ds it, and verifies the GPU observed
exact bytes.  Pinned (``cudaHostAlloc``-class) and pageable controls are
measured with the identical copy loop for comparison.

Default OFF: ``COMFYMODAL_GOLDEN_IO_PROCESS_V2=0``.  The probe method is invoked
explicitly and does not depend on the switch.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import mmap
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Any, Mapping, Optional, Sequence

IO_PROCESS_V2_ENV = "COMFYMODAL_GOLDEN_IO_PROCESS_V2"
IO_PROCESS_V2_BACKING_ENV = "COMFYMODAL_GOLDEN_IO_PROCESS_V2_BACKING"
IO_PROCESS_V2_SOURCE_GEOMETRY_ENV = "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY"
_TRUTHY = {"1", "true", "yes", "on"}
_BACKING_TYPES = ("posix", "sysv")
_SOURCE_GEOMETRIES = {
    "qd4_32": (4, 32 * 1024 * 1024),
    "qd2_128": (2, 128 * 1024 * 1024),
    # Appended last so the existing ``allowed=qd4_32,qd2_128`` substring in the
    # selector error stays intact for the control contract.
    "qd4_64": (4, 64 * 1024 * 1024),
}


def normalize_backing_type(value: Any = None) -> str:
    selected = os.environ.get(IO_PROCESS_V2_BACKING_ENV) if value is None else value
    selected = "posix" if selected is None or not str(selected).strip() else str(selected).strip().lower()
    if selected not in _BACKING_TYPES:
        raise ValueError(
            f"{IO_PROCESS_V2_BACKING_ENV}_invalid:{selected};allowed={','.join(_BACKING_TYPES)}"
        )
    return selected


def normalize_source_geometry(value: Any = None) -> str:
    selected = os.environ.get(IO_PROCESS_V2_SOURCE_GEOMETRY_ENV) if value is None else value
    selected = "qd4_32" if selected is None or not str(selected).strip() else str(selected).strip().lower()
    if selected not in _SOURCE_GEOMETRIES:
        raise ValueError(
            f"{IO_PROCESS_V2_SOURCE_GEOMETRY_ENV}_invalid:{selected};allowed={','.join(_SOURCE_GEOMETRIES)}"
        )
    return selected

# Deterministic fill pattern.  The child program embeds the IDENTICAL formula
# (see ``_CHILD_SOURCE``); keep the two in sync.
_PATTERN_BLOCK_BYTES = 64 * 1024

_CUDA_HOST_REGISTER_DEFAULT = 0
_CUDA_HOST_REGISTER_MAPPED = 0x02
# cudaErrorOperatingSystem (304) and friends that mean "not supported here".
_UNSUPPORTED_RCS = {304, 801}

_DEFAULT_SIZE_MIB = 256
_MAX_SIZE_MIB = 24000
# Verification sample for large backings (full-payload hashing is not required
# to prove the mechanism; the 256 MiB gate already proved whole-buffer exactness).
_SAMPLE_VERIFY_BYTES = 64 * 1024 * 1024


def io_process_v2_enabled() -> bool:
    """Return True only when the V2 full-backing switch is ON (default OFF)."""
    return str(os.environ.get(IO_PROCESS_V2_ENV) or "").strip().lower() in _TRUTHY


# ── deterministic pattern ─────────────────────────────────────────────────────


def _pattern_block() -> bytes:
    return bytes(((i * 131 + 7) ^ (i >> 5)) & 0xFF for i in range(_PATTERN_BLOCK_BYTES))


def _expected_pattern(size: int) -> bytes:
    block = _pattern_block()
    blen = len(block)
    if size <= 0:
        return b""
    return block * (size // blen) + block[: size % blen]


def _expected_sha256(size: int) -> str:
    return hashlib.sha256(_expected_pattern(size)).hexdigest()


def _sha256_region(view: Any) -> str:
    h = hashlib.sha256()
    h.update(memoryview(view).cast("B"))
    return h.hexdigest()


# ── environment introspection (stdlib only) ───────────────────────────────────


def _cgroup_memory_limit_bytes() -> Optional[int]:
    for path in (
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ):
        try:
            raw = open(path, "r").read().strip()
        except OSError:
            continue
        if raw and raw not in {"max", "-1"}:
            try:
                return int(raw)
            except ValueError:
                continue
    return None


def _proc_status_kb(pid: int, key: str) -> Optional[int]:
    try:
        with open(f"/proc/{pid}/status", "r") as fh:
            for line in fh:
                if line.startswith(key + ":"):
                    return int(line.split()[1])
    except Exception:
        pass
    return None


def _shm_address(shm: "shared_memory.SharedMemory") -> int:
    return int(ctypes.addressof(ctypes.c_char.from_buffer(shm.buf)))


def _shm_fs_info() -> dict:
    for path in ("/dev/shm", "/run/shm", "/tmp"):
        try:
            st = os.statvfs(path)
        except OSError:
            continue
        return {
            "path": path,
            "total_bytes": int(st.f_blocks) * int(st.f_frsize),
            "free_bytes": int(st.f_bavail) * int(st.f_frsize),
        }
    return {}


# ── cudart helpers (mirror the proven salvage-probe invocation) ───────────────


def _cudart_error_str(cudart: Any, rc: int) -> str:
    try:
        fn = getattr(cudart, "cudaGetErrorString", None)
        if callable(fn):
            value = fn(rc)
            if isinstance(value, (tuple, list)) and value:
                value = value[0]
            if value:
                return str(value)
    except Exception:
        pass
    return f"cuda_rc={rc}"


def _query_cuda_attr(fn: Any, attr_id: int, device: int = 0) -> Optional[dict]:
    if not callable(fn):
        return None
    try:
        value = ctypes.c_int(0)
        rc = fn(ctypes.byref(value), int(attr_id), int(device))
        return {"rc": int(rc), "value": int(value.value)}
    except Exception as exc:  # noqa: BLE001
        return {"rc": -1, "error": f"{type(exc).__name__}: {exc}"[:120]}


# ── CUDA-sterile child (standard library only; separate interpreter) ──────────

_CHILD_SOURCE = r"""
import ctypes
import hashlib
import json
import os
import sys
from multiprocessing import shared_memory

name = sys.argv[1]
size = int(sys.argv[2])
nonce = sys.argv[3].encode("utf-8")
hash_bytes = int(sys.argv[4]) if len(sys.argv) > 4 else size
hash_bytes = max(0, min(hash_bytes, size))

shm = shared_memory.SharedMemory(name=name)
buf = shm.buf

# Same-backing identity proof: the parent wrote this nonce before we attached.
seen = bytes(memoryview(buf)[: len(nonce)])

block = bytes(((i * 131 + 7) ^ (i >> 5)) & 0xFF for i in range(65536))
blen = len(block)
pos = 0
while pos < size:
    end = min(pos + blen, size)
    buf[pos:end] = block[: end - pos]
    pos = end

digest = hashlib.sha256(memoryview(buf)[:hash_bytes]).hexdigest()
addr = int(ctypes.addressof(ctypes.c_char.from_buffer(buf)))
vmrss = None
try:
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS:"):
            vmrss = int(line.split()[1])
            break
except Exception:
    pass
try:
    shm.close()
except Exception:
    pass

print(json.dumps({
    "op": "filled",
    "pid": os.getpid(),
    "ppid": os.getppid(),
    "size": size,
    "sha256": digest,
    "hash_bytes": hash_bytes,
    "addr": addr,
    "nonce_echo": seen.decode("utf-8", errors="replace"),
    "nonce_match": bool(seen == nonce),
    "torch_imported": bool("torch" in sys.modules),
    "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    "vmrss_kb": vmrss,
}))
""".strip()


def _run_child_fill(
    shm_name: str,
    size: int,
    nonce: str,
    hash_bytes: Optional[int] = None,
    timeout_s: float = 900.0,
) -> dict:
    """Run the CUDA-sterile child program; return its parsed report."""
    proc = subprocess.run(
        [
            sys.executable, "-c", _CHILD_SOURCE,
            shm_name, str(int(size)), nonce,
            str(int(size if hash_bytes is None else hash_bytes)),
        ],
        capture_output=True,
        text=True,
        timeout=float(timeout_s),
    )
    report: dict = {
        "returncode": int(proc.returncode),
        "stderr_tail": (proc.stderr or "")[-600:],
    }
    parsed: Optional[dict] = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get("op") == "filled":
            parsed = candidate
    if parsed is not None:
        report.update(parsed)
    else:
        report["error"] = "child_report_missing"
    return report


# ── H2D measurement (identical loop for every source class) ───────────────────


def _require_torch() -> Any:
    import torch  # local import: the child never reaches this module's CUDA path

    return torch


def _h2d_reps(torch: Any, src: Any, size: int, reps: int = 3) -> tuple[Any, list[dict]]:
    dest = torch.empty(size, dtype=torch.uint8, device="cuda")
    dest.copy_(src, non_blocking=True)
    torch.cuda.synchronize()
    samples: list[dict] = []
    for _ in range(max(1, int(reps))):
        torch.cuda.synchronize()
        start_ev = torch.cuda.Event(enable_timing=True)
        end_ev = torch.cuda.Event(enable_timing=True)
        start_ev.record()
        t0 = time.perf_counter()
        dest.copy_(src, non_blocking=True)
        issue_ms = (time.perf_counter() - t0) * 1000.0
        end_ev.record()
        torch.cuda.synchronize()
        device_ms = float(start_ev.elapsed_time(end_ev))
        samples.append({
            "issue_ms": round(issue_ms, 4),
            "device_ms": round(device_ms, 4),
            "gbps": round(size / (device_ms * 1e6) if device_ms > 0 else 0.0, 4),
        })
    return dest, samples


def _median_gbps(samples: list[dict]) -> Optional[float]:
    values = sorted(float(s["gbps"]) for s in samples if s.get("gbps") is not None)
    if not values:
        return None
    return round(values[len(values) // 2], 4)


def _readback_sha256(torch: Any, device_tensor: Any, sample: int) -> str:
    host = torch.empty(int(sample), dtype=torch.uint8, pin_memory=True)
    host.copy_(device_tensor[: int(sample)], non_blocking=True)
    torch.cuda.synchronize()
    return _sha256_region(memoryview(host.numpy()))


# ── probe ─────────────────────────────────────────────────────────────────────


def run_primitive_probe(
    *,
    request_id: str = "",
    size_mib: int = _DEFAULT_SIZE_MIB,
    device_index: int = 0,
    include_controls: bool = True,
    verify_full: bool = True,
) -> dict:
    """Prove/disprove shared registered memory on this Modal target.

    ``include_controls`` allocates parallel pinned/pageable host buffers and is
    only safe at small sizes.  ``verify_full`` hashes/reads back the whole
    backing; leave it False for full-model-size backings (a bounded sample is
    verified instead).  Never raises: every failure is captured in the record.
    """
    size_mib = max(1, min(int(size_mib or _DEFAULT_SIZE_MIB), _MAX_SIZE_MIB))
    size = size_mib * 1024 * 1024
    sample = size if verify_full else min(size, _SAMPLE_VERIFY_BYTES)
    torch = _require_torch()

    result: dict[str, Any] = {
        "status": "ok",
        "mode": "golden_io_process_v2_primitive",
        "request_id": str(request_id or ""),
        "size_mib": size_mib,
        "size_bytes": size,
        "verify_full": bool(verify_full),
        "include_controls": bool(include_controls),
        "verify_sample_bytes": int(sample),
        "self_pid": os.getpid(),
        "python": sys.version.split()[0],
        "torch_version": str(getattr(torch, "__version__", "")),
        "cuda_available": bool(torch.cuda.is_available()),
        "env": {
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "MODAL_REGION": os.environ.get("MODAL_REGION"),
            "MODAL_CLOUD_PROVIDER": os.environ.get("MODAL_CLOUD_PROVIDER"),
            "MODAL_IMAGE_ID": os.environ.get("MODAL_IMAGE_ID"),
        },
        "cgroup_memory_limit_bytes": _cgroup_memory_limit_bytes(),
        "parent_rss_kb_before": _proc_status_kb(os.getpid(), "VmRSS"),
    }
    if not result["cuda_available"]:
        result["status"] = "error"
        result["error"] = "cuda_unavailable"
        return result
    result["cuda_device_name"] = str(torch.cuda.get_device_name(device_index))

    cudart = torch.cuda.cudart()
    register = getattr(cudart, "cudaHostRegister", None)
    unregister = getattr(cudart, "cudaHostUnregister", None)
    result["cudart_available"] = {
        "cudaHostRegister": callable(register),
        "cudaHostUnregister": callable(unregister),
        "cudaDeviceGetAttribute": callable(getattr(cudart, "cudaDeviceGetAttribute", None)),
    }
    getattr_fn = getattr(cudart, "cudaDeviceGetAttribute", None)
    result["device_attrs"] = {
        "cudaDevAttrHostRegisterSupported(99)": _query_cuda_attr(getattr_fn, 99, device_index),
        "cudaDevAttrHostRegisterReadOnlySupported(113)": _query_cuda_attr(getattr_fn, 113, device_index),
    }

    shm = None
    child_report: dict = {}
    registered_flags: Optional[int] = None
    try:
        shm = shared_memory.SharedMemory(create=True, size=size)
        result["mapping"] = {
            "shm_name": shm.name,
            "parent_addr": _shm_address(shm),
            "size_bytes": size,
        }
        result["shm_fs"] = _shm_fs_info()

        # Same-backing identity proof: parent writes a nonce the child echoes.
        nonce = hashlib.sha256(os.urandom(16)).hexdigest()
        shm.buf[: len(nonce)] = nonce.encode("utf-8")

        child_report = _run_child_fill(shm.name, size, nonce, hash_bytes=sample)
        result["child"] = child_report

        pattern_view = memoryview(shm.buf)[:sample]
        parent_sha = _sha256_region(pattern_view)
        expected_sha = _expected_sha256(sample)
        result["correctness"] = {
            "expected_sha256": expected_sha,
            "child_sha256": child_report.get("sha256"),
            "parent_sha256": parent_sha,
            "child_wrote_exact": child_report.get("sha256") == expected_sha,
            "parent_observed_child_bytes": parent_sha == child_report.get("sha256"),
            "same_backing_nonce_match": bool(child_report.get("nonce_match")),
            "child_torch_imported": bool(child_report.get("torch_imported")),
        }

        # Register the SAME mapping the child wrote.
        if callable(register) and callable(unregister):
            ptr = int(result["mapping"]["parent_addr"])
            attempts = []
            for flags, label in (
                (_CUDA_HOST_REGISTER_DEFAULT, "default"),
                (_CUDA_HOST_REGISTER_MAPPED, "mapped"),
            ):
                t0 = time.perf_counter()
                try:
                    rc = int(register(ptr, size, int(flags)))
                    err = None if rc == 0 else _cudart_error_str(cudart, rc)
                except Exception as exc:  # noqa: BLE001
                    rc = -1
                    err = f"{type(exc).__name__}: {exc}"[:200]
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                attempts.append({
                    "flags": int(flags),
                    "label": label,
                    "rc": rc,
                    "error": err,
                    "unsupported": rc in _UNSUPPORTED_RCS if rc >= 0 else False,
                    "register_ms": round(elapsed_ms, 4),
                })
                if rc == 0:
                    registered_flags = int(flags)
                    break
            result["registration"] = {
                "attempts": attempts,
                "registered": registered_flags is not None,
                "registered_flags": registered_flags,
            }
        else:
            result["registration"] = {
                "registered": False,
                "error": "cudaHostRegister/cudaHostUnregister unavailable",
            }

        shm_tensor = torch.frombuffer(shm.buf, dtype=torch.uint8)

        # H2D from the shared mapping, registered or not (contrast is the point).
        shm_dest, shm_samples = _h2d_reps(torch, shm_tensor, size)
        result["h2d_from_shared_mapping"] = {
            "registered": registered_flags is not None,
            "samples": shm_samples,
            "median_gbps": _median_gbps(shm_samples),
            "gpu_readback_sha256": _readback_sha256(torch, shm_dest, sample),
        }
        del shm_dest

        if include_controls:
            # Control: pinned host tensor (cudaHostAlloc-class), same copy loop.
            pattern_bytes = _expected_pattern(size)
            pattern_tensor = torch.frombuffer(bytearray(pattern_bytes), dtype=torch.uint8)
            pinned_src = torch.empty(size, dtype=torch.uint8, pin_memory=True)
            pinned_src.copy_(pattern_tensor)
            pageable_src = torch.empty(size, dtype=torch.uint8)
            pageable_src.copy_(pattern_tensor)

            pinned_dest, pinned_samples = _h2d_reps(torch, pinned_src, size)
            result["h2d_from_pinned_control"] = {
                "samples": pinned_samples,
                "median_gbps": _median_gbps(pinned_samples),
                "gpu_readback_sha256": _readback_sha256(torch, pinned_dest, size),
            }
            del pinned_dest

            pageable_dest, pageable_samples = _h2d_reps(torch, pageable_src, size)
            result["h2d_from_pageable_control"] = {
                "samples": pageable_samples,
                "median_gbps": _median_gbps(pageable_samples),
                "gpu_readback_sha256": _readback_sha256(torch, pageable_dest, size),
            }
            del pageable_dest
        else:
            result["h2d_from_pinned_control"] = None
            result["h2d_from_pageable_control"] = None

        # Unregister and free GPU scratch.
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        if registered_flags is not None and callable(unregister):
            t0 = time.perf_counter()
            try:
                urc = int(unregister(int(result["mapping"]["parent_addr"])))
                result["registration"]["unregister_rc"] = urc
            except Exception as exc:  # noqa: BLE001
                result["registration"]["unregister_error"] = f"{type(exc).__name__}: {exc}"[:200]
            result["registration"]["unregister_ms"] = round((time.perf_counter() - t0) * 1000.0, 4)

        result["expected_sha256"] = expected_sha
        result["parent_rss_kb_after"] = _proc_status_kb(os.getpid(), "VmRSS")
        result["memory"] = {
            "backing_bytes": size,
            "parent_rss_kb_before": result.get("parent_rss_kb_before"),
            "parent_rss_kb_after": result.get("parent_rss_kb_after"),
            "child_vmrss_kb": child_report.get("vmrss_kb"),
            "projected_rss_kb_if_backing_is_sole_large_alloc": (
                (result.get("parent_rss_kb_before") or 0) + size // 1024
            ),
        }

        # ── verdict ──────────────────────────────────────────────────────
        reg = result["registration"]
        correctness = result["correctness"]
        reg_gbps = result["h2d_from_shared_mapping"]["median_gbps"]
        pinned_gbps = (result.get("h2d_from_pinned_control") or {}).get("median_gbps")
        shared_readback_ok = (
            result["h2d_from_shared_mapping"]["gpu_readback_sha256"] == expected_sha
        )
        result["verdict"] = {
            "mapping_written_by_child_and_observed": bool(
                correctness["child_wrote_exact"] and correctness["parent_observed_child_bytes"]
            ),
            "same_backing_identity": bool(correctness["same_backing_nonce_match"]),
            "child_cuda_sterile": not bool(correctness["child_torch_imported"]),
            "host_register_succeeded": bool(reg.get("registered")),
            "gpu_observed_exact_bytes": bool(shared_readback_ok),
            "shared_h2d_median_gbps": reg_gbps,
            "pinned_control_median_gbps": pinned_gbps,
            "pinned_class_bandwidth": bool(
                reg_gbps is not None
                and pinned_gbps is not None
                and pinned_gbps > 0
                and reg_gbps >= 0.75 * pinned_gbps
            )
            if (reg.get("registered") and pinned_gbps is not None)
            else None,
        }
    except BaseException as exc:  # noqa: BLE001 - never raise
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:400]
    finally:
        if shm is not None:
            try:
                shm.buf.release()
            except Exception:
                pass
            try:
                shm.close()
            except Exception:
                pass
            try:
                shm.unlink()
            except Exception:
                pass
    return result


# ══════════════════════════════════════════════════════════════════════════════
# V2 loader runtime: one reusable registered backing + persistent CUDA-sterile
# child.  The child performs the complete QD source read for each model into the
# SAME backing; the parent H2Ds directly from that backing (no shared->pinned
# copy).  Control IPC is one coarse READ_MODEL command per model.
# ══════════════════════════════════════════════════════════════════════════════

# Sized for the largest Golden payload (UNET ~12.31 GB) plus margin.  One
# backing is created, registered, and reused for CLIP -> UNET -> VAE.
GOLDEN_IO_V2_BACKING_BYTES = 13_000_000_000
V2_DEFAULT_QD = 4
V2_DEFAULT_CHUNK_BYTES = 32 * 1024 * 1024

# Persistent child.  Standard library only (never imports torch / never touches
# CUDA).  It owns the file descriptor, the QD source workers, exact byte
# coverage, and the writes into the shared backing; it replies DONE or ERROR.
_LOADER_CHILD_SOURCE = r"""
import ctypes
import json
import os
import sys
import threading
import time

backing_type = str(sys.argv[1])
identifier = str(sys.argv[2])
size = int(sys.argv[3])
nonce = str(sys.argv[4]).encode("utf-8")
shm = None
sysv_addr = None
sysv_libc = None
if backing_type == "posix":
    from multiprocessing import shared_memory
    shm = shared_memory.SharedMemory(name=identifier)
    buf = shm.buf
elif backing_type == "sysv":
    sysv_libc = ctypes.CDLL(None, use_errno=True)
    sysv_libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
    sysv_libc.shmat.restype = ctypes.c_void_p
    sysv_libc.shmdt.argtypes = [ctypes.c_void_p]
    sysv_libc.shmdt.restype = ctypes.c_int
    sysv_addr = sysv_libc.shmat(int(identifier), None, 0)
    failed = ctypes.c_void_p(-1).value
    if sysv_addr in (None, failed):
        raise OSError(ctypes.get_errno(), "shmat")
    buf = (ctypes.c_ubyte * size).from_address(int(sysv_addr))
else:
    raise RuntimeError("unsupported_backing_type")

seen_nonce = bytes(memoryview(buf)[: len(nonce)])


def reply(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _pread(fd, view, offset):
    # Positioned reads straight into the shared backing.  POSIX only; the
    # child only runs on the Linux Modal runtime.
    if hasattr(os, "preadv"):
        return os.preadv(fd, [view], offset)
    if hasattr(os, "pread"):
        data = os.pread(fd, len(view), offset)
        view[:len(data)] = data
        return len(data)
    raise RuntimeError("positioned_read_unsupported")


def _fill(cmd):
    path = str(cmd["path"])
    data_start = int(cmd["data_start"])
    payload = int(cmd["payload_bytes"])
    qd = max(1, int(cmd.get("qd", 4)))
    chunk = max(1, int(cmd.get("chunk_bytes", 32 * 1024 * 1024)))
    lock = threading.Lock()
    active = [0]
    qd_max = [0]
    total = [0]
    read_calls = [0]
    short_read_retries = [0]
    read_records = []
    errs = []
    # Contiguous regions, one per source worker (the child owns QD concurrency).
    parts = []
    base = 0
    for index in range(qd):
        length = payload // qd + (1 if index < payload % qd else 0)
        if length > 0:
            parts.append((base, length))
        base += length

    def worker(dest0, length):
        # One descriptor per source worker: no cross-thread shared cursor.
        fd = os.open(path, os.O_RDONLY)
        dest = dest0
        remaining = length
        offset = data_start + dest0
        try:
            while remaining > 0:
                take = min(chunk, remaining)
                with lock:
                    active[0] += 1
                    if active[0] > qd_max[0]:
                        qd_max[0] = active[0]
                try:
                    view = memoryview(buf)[dest:dest + take]
                    got = _pread(fd, view, offset)
                    if got <= 0:
                        raise RuntimeError("short_read")
                    with lock:
                        total[0] += got
                        read_calls[0] += 1
                        if got < take:
                            short_read_retries[0] += 1
                        read_records.append({
                            "destination_offset": int(dest),
                            "source_offset": int(offset),
                            "requested_bytes": int(take),
                            "returned_bytes": int(got),
                        })
                    dest += got
                    offset += got
                    remaining -= got
                finally:
                    with lock:
                        active[0] -= 1
        except BaseException as exc:  # noqa: BLE001
            errs.append(f"{type(exc).__name__}:{exc}")
        finally:
            try:
                os.close(fd)
            except Exception:
                pass

    t0 = time.monotonic_ns()
    threads = [threading.Thread(target=worker, args=part, daemon=True) for part in parts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    t1 = time.monotonic_ns()
    wall_ms = (t1 - t0) / 1e6
    ok = (int(total[0]) == payload) and not errs
    expected_ranges = []
    for dest0, length in parts:
        cursor = int(dest0)
        remaining = int(length)
        while remaining:
            take = min(chunk, remaining)
            expected_ranges.append((cursor, cursor + take))
            cursor += take
            remaining -= take
    actual_ranges = sorted(
        (int(record["destination_offset"]),
         int(record["destination_offset"]) + int(record["returned_bytes"]))
        for record in read_records
    )
    coverage_ok = actual_ranges == sorted(expected_ranges)
    reply({
        "op": "done" if ok and coverage_ok else "error",
        "role": str(cmd.get("role") or ""),
        "backing_type": backing_type,
        "shmid": int(identifier) if backing_type == "sysv" else None,
        "capacity_bytes": size,
        "source_geometry": str(cmd.get("source_geometry") or f"qd{qd}_{chunk // (1024 * 1024)}mib"),
        "source_qd": qd,
        "source_block_bytes": chunk,
        "child_attach_success": True,
        "same_backing_nonce_match": bool(seen_nonce == nonce),
        "cuda_initialized": False,
        "cuda_tasks": 0,
        "gpu_alloc_bytes": 0,
        "path": path,
        "bytes": int(total[0]),
        "payload_bytes": payload,
        "read_calls": int(read_calls[0]),
        "short_read_retries": int(short_read_retries[0]),
        "read_records": read_records,
        "coverage": {
            "ok": bool(coverage_ok),
            "expected_bytes": int(payload),
            "covered_bytes": int(sum(end - start for start, end in actual_ranges)),
            "expected_ranges": [[start, end] for start, end in expected_ranges],
            "actual_ranges": [[start, end] for start, end in actual_ranges],
        },
        "wall_ms": round(wall_ms, 4),
        "gbps": round(payload / (wall_ms * 1e6), 4) if wall_ms > 0 else 0.0,
        "qd_max": int(qd_max[0]),
        "regions": len(parts),
        "child_start_ns": t0,
        "child_end_ns": t1,
        "error": errs[0] if errs else None,
    })


reply({
    "op": "ready",
    "pid": os.getpid(),
    "addr": int(ctypes.addressof(ctypes.c_char.from_buffer(buf))),
    "backing_type": backing_type,
    "shmid": int(identifier) if backing_type == "sysv" else None,
    "capacity_bytes": size,
    "source_geometry": "unselected_until_read_model",
    "child_attach_success": True,
    "same_backing_nonce_match": bool(seen_nonce == nonce),
    "cuda_initialized": False,
    "cuda_tasks": 0,
    "gpu_alloc_bytes": 0,
    "torch_imported": bool("torch" in sys.modules),
    "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
})

for line in iter(sys.stdin.readline, ""):
    line = line.strip()
    if not line:
        continue
    try:
        cmd = json.loads(line)
    except ValueError:
        reply({"op": "error", "error": "bad_json"})
        continue
    op = str(cmd.get("op") or "")
    if op == "ping":
        reply({"op": "pong", "pid": os.getpid()})
    elif op == "read_model":
        _fill(cmd)
    elif op == "exit":
        break
    else:
        reply({"op": "error", "error": f"bad_op:{op}"})

try:
    if shm is not None:
        shm.close()
    elif sysv_libc is not None and sysv_addr is not None:
        sysv_libc.shmdt(ctypes.c_void_p(sysv_addr))
except Exception:
    pass
"""


class SharedBackingRuntime:
    """Parent-owned, CUDA-registered shared backing reused across all models."""

    def __init__(self, size_bytes: int, *, device_index: int = 0) -> None:
        self.size_bytes = int(size_bytes)
        self.device_index = int(device_index)
        self.backing_type = normalize_backing_type()
        self.source_geometry = normalize_source_geometry()
        self.created = False
        self.registered = False
        self.backing_create_ms: Optional[float] = None
        self.prefault_ms: Optional[float] = None
        self.prefault_method: Optional[str] = None
        self.register_ms: Optional[float] = None
        self.prefault_plus_register_ms: Optional[float] = None
        self.unregister_ms: Optional[float] = None
        self.child_pid: Optional[int] = None
        self.child_addr: Optional[int] = None
        self.child_torch_imported: Optional[bool] = None
        self.child_cuda_visible_devices: Optional[str] = None
        self.child_cuda_initialized = False
        self.child_cuda_tasks = 0
        self.child_gpu_alloc_bytes = 0
        self._shm = None
        self._buffer = None
        self._sysv_libc = None
        self._sysv_addr: Optional[int] = None
        self._sysv_shmid: Optional[int] = None
        self._nonce = ""
        self._proc = None
        self._tensor = None
        self.events: dict[str, dict] = {}
        self.cleanup_status: dict[str, Any] = {}

    def _create_backing(self) -> None:
        if self.backing_type == "posix":
            self._shm = shared_memory.SharedMemory(create=True, size=self.size_bytes)
            self._buffer = self._shm.buf
            return
        libc = ctypes.CDLL(None, use_errno=True)
        libc.shmget.argtypes = [ctypes.c_int, ctypes.c_size_t, ctypes.c_int]
        libc.shmget.restype = ctypes.c_int
        libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        libc.shmat.restype = ctypes.c_void_p
        libc.shmdt.argtypes = [ctypes.c_void_p]
        libc.shmdt.restype = ctypes.c_int
        libc.shmctl.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        libc.shmctl.restype = ctypes.c_int
        shmid = int(libc.shmget(0, self.size_bytes, 0o1000 | 0o600))
        if shmid < 0:
            raise OSError(ctypes.get_errno(), "shmget")
        addr = libc.shmat(shmid, None, 0)
        if addr in (None, ctypes.c_void_p(-1).value):
            libc.shmctl(shmid, 0, None)
            raise OSError(ctypes.get_errno(), "shmat")
        self._sysv_libc = libc
        self._sysv_addr = int(addr)
        self._sysv_shmid = shmid
        self._buffer = (ctypes.c_ubyte * self.size_bytes).from_address(int(addr))

    def _backing_identifier(self) -> str:
        if self.backing_type == "posix":
            assert self._shm is not None
            return str(self._shm.name)
        assert self._sysv_shmid is not None
        return str(self._sysv_shmid)

    def _backing_address(self) -> int:
        assert self._buffer is not None
        return int(ctypes.addressof(ctypes.c_ubyte.from_buffer(self._buffer)))

    def ensure(self) -> "SharedBackingRuntime":
        if self.created:
            return self
        torch = _require_torch()
        t0 = time.perf_counter()
        self._create_backing()
        self.backing_create_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        self._nonce = hashlib.sha256(os.urandom(16)).hexdigest()
        self._buffer[: len(self._nonce)] = self._nonce.encode("utf-8")
        cudart = torch.cuda.cudart()
        register = getattr(cudart, "cudaHostRegister", None)
        if not callable(register):
            raise RuntimeError("cudaHostRegister_unavailable")
        ptr = self._backing_address()
        # Explicit prefault was measured and rejected (2026-09-12): the kernel
        # MADV_POPULATE_WRITE path was unavailable, and a memset prefault of the
        # 13 GB mapping cost 16.4 s (0.79 GB/s) versus cudaHostRegister's own
        # population at ~4.7 GB/s (2.7 s).  Prefault is therefore NOT applied;
        # registration alone remains the population step.  The split timing
        # fields are retained so the one-time setup cost stays explicit.
        self.prefault_ms = 0.0
        self.prefault_method = "not_applied"
        t0 = time.perf_counter()
        rc = int(register(ptr, self.size_bytes, _CUDA_HOST_REGISTER_DEFAULT))
        self.register_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        self.prefault_plus_register_ms = round(
            (self.prefault_ms or 0.0) + (self.register_ms or 0.0), 4
        )
        print(
            "[v2.golden_io_process_v2] "
            f"event=setup_timings backing_create_ms={self.backing_create_ms} "
            f"prefault_method={self.prefault_method} prefault_ms={self.prefault_ms} "
            f"cudaHostRegister_ms={self.register_ms} "
            f"prefault_plus_register_ms={self.prefault_plus_register_ms}",
            flush=True,
        )
        if rc != 0:
            raise RuntimeError(f"cudaHostRegister_failed:{rc}:{_cudart_error_str(cudart, rc)}")
        self.registered = True
        child_env = os.environ.copy()
        child_env["CUDA_VISIBLE_DEVICES"] = ""
        self._proc = subprocess.Popen(
            [
                sys.executable, "-c", _LOADER_CHILD_SOURCE,
                self.backing_type, self._backing_identifier(),
                str(self.size_bytes), self._nonce,
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=child_env,
        )
        ready = self._recv(timeout_s=180.0)
        if not isinstance(ready, dict) or ready.get("op") != "ready":
            raise RuntimeError(f"child_ready_failed:{str(ready)[:200]}")
        self.child_pid = int(ready.get("pid") or 0) or None
        self.child_addr = ready.get("addr")
        self.child_torch_imported = bool(ready.get("torch_imported"))
        self.child_cuda_visible_devices = ready.get("cuda_visible_devices")
        self.child_cuda_initialized = bool(ready.get("cuda_initialized"))
        self.child_cuda_tasks = int(ready.get("cuda_tasks") or 0)
        self.child_gpu_alloc_bytes = int(ready.get("gpu_alloc_bytes") or 0)
        if ready.get("backing_type") != self.backing_type or not ready.get("child_attach_success"):
            raise RuntimeError("child_backing_attach_proof_failed")
        if not ready.get("same_backing_nonce_match"):
            raise RuntimeError("child_same_backing_nonce_failed")
        self._tensor = torch.frombuffer(self._buffer, dtype=torch.uint8)
        self.created = True
        return self

    @property
    def tensor(self) -> Any:
        return self._tensor

    def _send(self, obj: dict) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _recv(self, *, timeout_s: float) -> dict:
        assert self._proc is not None and self._proc.stdout is not None
        import select
        ready, _, _ = select.select([self._proc.stdout], [], [], float(timeout_s))
        if not ready:
            raise RuntimeError(f"child_ipc_timeout:{timeout_s}")
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("child_ipc_eof")
        return json.loads(line)

    def read_model(
        self,
        path: str,
        *,
        data_start: int,
        payload_bytes: int,
        role: str,
        qd: int = V2_DEFAULT_QD,
        chunk_bytes: int = V2_DEFAULT_CHUNK_BYTES,
    ) -> dict:
        self.ensure()
        command = {
            "op": "read_model",
            "role": str(role),
            "path": os.path.abspath(path),
            "data_start": int(data_start),
            "payload_bytes": int(payload_bytes),
            "qd": int(_SOURCE_GEOMETRIES[self.source_geometry][0]),
            "chunk_bytes": int(_SOURCE_GEOMETRIES[self.source_geometry][1]),
            "source_geometry": self.source_geometry,
        }
        t0 = time.perf_counter_ns()
        self._send(command)
        reply = self._recv(timeout_s=900.0)
        t1 = time.perf_counter_ns()
        reply["parent_send_ns"] = t0
        reply["parent_recv_ns"] = t1
        reply["parent_roundtrip_ms"] = round((t1 - t0) / 1e6, 4)
        if reply.get("op") != "done":
            raise RuntimeError(f"child_read_failed:{str(reply.get('error'))[:300]}")
        if int(reply.get("bytes") or -1) != int(payload_bytes):
            raise RuntimeError(f"child_coverage_mismatch:{reply.get('bytes')}!={payload_bytes}")
        reply["backing_type"] = self.backing_type
        reply["shmid"] = self._sysv_shmid
        reply["capacity_bytes"] = self.size_bytes
        reply["source_geometry"] = self.source_geometry
        reply["source_qd"] = int(_SOURCE_GEOMETRIES[self.source_geometry][0])
        reply["source_block_bytes"] = int(_SOURCE_GEOMETRIES[self.source_geometry][1])
        reply["parent_attach_success"] = True
        reply["same_backing_nonce_match"] = bool(reply.get("same_backing_nonce_match"))
        self.events[str(role)] = dict(reply)
        return reply

    def close(self) -> dict:
        out: dict = {"pid": self.child_pid}
        torch = None
        try:
            torch = _require_torch()
        except Exception:
            pass
        if self._proc is not None:
            try:
                self._send({"op": "exit"})
            except Exception as exc:  # noqa: BLE001
                out["exit_error"] = f"{type(exc).__name__}: {exc}"[:160]
            try:
                self._proc.wait(timeout=10.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        if self.registered and torch is not None and self._buffer is not None:
            cudart = torch.cuda.cudart()
            unregister = getattr(cudart, "cudaHostUnregister", None)
            if callable(unregister):
                t0 = time.perf_counter()
                try:
                    out["unregister_rc"] = int(unregister(self._backing_address()))
                except Exception as exc:  # noqa: BLE001
                    out["unregister_error"] = f"{type(exc).__name__}: {exc}"[:160]
                self.unregister_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        if self.backing_type == "posix" and self._shm is not None:
            try:
                self._shm.buf.release()
            except Exception:
                pass
            try:
                self._shm.close()
            except Exception as exc:
                out["close_error"] = f"{type(exc).__name__}: {exc}"[:160]
            try:
                self._shm.unlink()
                out["cleanup_status"] = "unlinked"
            except Exception as exc:
                out["cleanup_status"] = f"unlink_error:{type(exc).__name__}:{exc}"[:160]
        elif self.backing_type == "sysv" and self._sysv_libc is not None:
            if self._sysv_addr is not None:
                try:
                    out["parent_detach_rc"] = int(
                        self._sysv_libc.shmdt(ctypes.c_void_p(self._sysv_addr))
                    )
                except Exception as exc:
                    out["parent_detach_error"] = f"{type(exc).__name__}: {exc}"[:160]
            if self._sysv_shmid is not None:
                try:
                    out["ipc_rmid_rc"] = int(
                        self._sysv_libc.shmctl(self._sysv_shmid, 0, None)
                    )
                    out["cleanup_status"] = "ipc_rmid"
                except Exception as exc:
                    out["cleanup_status"] = f"ipc_rmid_error:{type(exc).__name__}:{exc}"[:160]
        self._buffer = None
        self.created = False
        self.cleanup_status = dict(out)
        return out

    def evidence(self) -> dict:
        return {
            "active": True,
            "backing_type": self.backing_type,
            "backing_bytes": self.size_bytes,
            "capacity_bytes": self.size_bytes,
            "shmid": self._sysv_shmid,
            "parent_attach_success": bool(self._buffer is not None),
            "child_attach_success": bool(self.child_pid),
            "same_backing_nonce_proof": (
                all(bool(event.get("same_backing_nonce_match")) for event in self.events.values())
                if self.events else None
            ),
            "cleanup_status": dict(self.cleanup_status),
            "registered": self.registered,
            "backing_create_ms": self.backing_create_ms,
            "prefault_ms": self.prefault_ms,
            "prefault_method": self.prefault_method,
            "register_ms_one_time": self.register_ms,
            "prefault_plus_register_ms": self.prefault_plus_register_ms,
            "one_time_setup_ms": round(
                (self.backing_create_ms or 0.0)
                + (self.prefault_plus_register_ms or 0.0),
                4,
            ),
            "unregister_ms": self.unregister_ms,
            "child_pid": self.child_pid,
            "child_addr": self.child_addr,
            "child_torch_imported": self.child_torch_imported,
            "child_cuda_visible_devices": self.child_cuda_visible_devices,
            "child_cuda_initialized": bool(self.child_cuda_initialized),
            "child_cuda_tasks": int(self.child_cuda_tasks),
            "child_gpu_alloc_bytes": int(self.child_gpu_alloc_bytes),
            "parent_physical_source_reads": 0,
            "models": {role: dict(ev) for role, ev in self.events.items()},
        }


# ══════════════════════════════════════════════════════════════════════════════
# V2 C0: bounded shared-pinned streaming arena (opt-in, fail-closed).
#
# One parent-created POSIX mapping of exactly 512 MiB is registered once by the
# CUDA-owning parent and split into four stable 128 MiB slots (A0/A1 -> worker 0,
# B0/B1 -> worker 1).  A CUDA-sterile standard-library child performs positioned
# reads (os.preadv) directly into the exact leased slot; the parent H2Ds straight
# from that registered slot with no shared->pinned copy and no model-sized
# backing.  The existing parent TransportDispatcher remains the sole owner of
# H2D submission, host events, reaping, and slot return.
# ══════════════════════════════════════════════════════════════════════════════

IO_PROCESS_V2_STREAMING_ENV = "COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING"
# C0-only, deploy-baked selector for the child's persistent positioned-FD
# cache.  Default OFF reproduces the exact per-fill open/preadv/close
# lifecycle; ON opens one descriptor per normalized (path, producer_id) key.
IO_PROCESS_V2_PERSISTENT_FDS_ENV = "COMFYMODAL_GOLDEN_IO_PROCESS_V2_PERSISTENT_FDS"
# C0-only, deploy-baked diagnostic selector for the private source/destination
# split.  Default OFF reproduces the exact direct file -> leased SHM slot path
# with no private buffers; ON stages each fill in one reusable private
# per-worker buffer and then copies into the leased SHM slot, exposing split
# source-read vs private->SHM timings.  Evidence-only, never promoted.
IO_PROCESS_V2_C0_PRIVATE_SPLIT_IO_ENV = "COMFYMODAL_GOLDEN_C0_PRIVATE_SPLIT_IO"
# C0-only, deploy-baked forensic selector: when ON, the CUDA-sterile child
# starts a VizTracer around its worker/writer/positioned-read seam and writes a
# deterministic child trace the parent can bundle.  OFF (default) reproduces
# the exact uninstrumented child; this is trace configuration only and never
# changes C0 geometry, the FD lifecycle, or IPC semantics.
GOLDEN_C0_CHILD_VIZTRACER_ENV = "COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER"
# Parent-owned path handed to the child at spawn (dedicated env var, not a
# deploy input).  Both sides share this single deterministic location so the
# parent copies the exact file, never a newest-file heuristic.
_C0_CHILD_VIZTRACER_PATH = "/tmp/comfymodal_c0_child_viztracer.json"

# Distinct C0 direct Volume V1 treatment selector (deploy-baked, default OFF).
# ON replaces only the CUDA-sterile child's byte producer with a VolumeGetFile2
# ranged read streamed as concurrent 8 MiB blocks into the leased SHM slot.
# There is deliberately no preadv fallback when ON.
IO_PROCESS_V2_C0_SOURCE_VOLUME_V1_ENV = "COMFYMODAL_GOLDEN_C0_SOURCE_VOLUME_V1"
# Parent-resolved V1 Volume identity handed to the child at spawn.  The object
# id is resolved once in the parent under the container's existing Modal auth
# and is recorded as evidence only; it is never a hardcoded authority.
C0_SOURCE_VOLUME_ID_ENV = "COMFYMODAL_C0_SOURCE_VOLUME_ID"
C0_SOURCE_VOLUME_NAME_ENV = "COMFYMODAL_C0_SOURCE_VOLUME_NAME"
C0_SOURCE_VOLUME_MOUNT_ENV = "COMFYMODAL_C0_SOURCE_VOLUME_MOUNT"
# Optional cross-check only: unset means "no expectation recorded".
C0_SOURCE_VOLUME_EXPECTED_ID_ENV = "COMFYMODAL_C0_SOURCE_VOLUME_EXPECTED_ID"
# The child loads the stdlib transport module by explicit path (never a package
# import that could pull torch into the CUDA-sterile process).
C0_RUNTIME_DIR_ENV = "COMFYMODAL_C0_RUNTIME_DIR"
# Bounded per-fill block-GET concurrency for the direct Volume treatment.
C0_VOLUME_BLOCK_CONCURRENCY = 8
_DEFAULT_MODELS_MOUNT = "/root/models"

# Diagnostic-only clustered preadv-sickness selector (deploy-baked, default OFF).
# Distinct from the Volume, VizTracer, and private-split diagnostics: it adds an
# outstanding-read registry, an independent 500ms watchdog, a passive snapshot
# captured before any active probe, and a bounded active probe matrix.  OFF
# leaves QD, source geometry, SHM arena, H2D, tensor adoption, fallback,
# settings, and production read behavior byte-for-byte unchanged.
IO_PROCESS_V2_C0_PREADV_SICKNESS_DIAG_ENV = "COMFYMODAL_GOLDEN_C0_PREADV_SICKNESS_DIAG"
# Parent-provided inputs handed to the child at spawn (never deploy inputs):
# the pre-registered control manifest plus config/profile hashes and a
# per-invocation identifier used for invocation-bound filenames/IDs.
C0_PREADV_SICKNESS_CONTROLS_ENV = "COMFYMODAL_C0_PREADV_SICKNESS_CONTROLS"
C0_PREADV_SICKNESS_PROFILE_HASH_ENV = "COMFYMODAL_C0_PREADV_SICKNESS_PROFILE_HASH"
C0_PREADV_SICKNESS_CONFIG_HASH_ENV = "COMFYMODAL_C0_PREADV_SICKNESS_CONFIG_HASH"
C0_PREADV_SICKNESS_INVOCATION_ID_ENV = "COMFYMODAL_C0_PREADV_SICKNESS_INVOCATION_ID"
C0_PREADV_SICKNESS_TRIPWIRE_NS = 500_000_000
C0_PREADV_SICKNESS_CONTROLS_BASENAME = "c0_preadv_controls.json"
# The 15 required hypothesis families, in stable report order.  The child emits
# exactly this set; the parent surfaces it verbatim (never synthesized).
C0_PREADV_SICKNESS_HYPOTHESIS_FAMILIES = (
    "same_file_fast_offset_slow",
    "pathological_offset_specific",
    "size_ladder_scaling",
    "fresh_fd_slow",
    "persistent_fd_slow",
    "different_model_file_slow",
    "metadata_syscall_slow",
    "private_anonymous_destination_slow",
    "separate_diagnostic_shm_destination_slow",
    "memory_only_copy_slow",
    "local_file_control_slow",
    "helper_thread_starved",
    "cgroup_cpu_pressure",
    "cgroup_memory_pressure",
    "cgroup_io_pressure_convoy",
)
C0_PREADV_SICKNESS_HYPOTHESIS_STATUSES = (
    "consistent",
    "inconsistent",
    "not_discriminated",
    "not_tested",
)

C0_ARENA_BYTES = 512 * 1024 * 1024

# Deploy-baked selector -> C0 geometry.  The arena is always exactly 512 MiB;
# only the slot split and the child source-worker pool change.  Only ``qd4_64``
# selects the wider treatment arm.  Every other selector -- the explicit
# control ``qd2_128`` and the default ``qd4_32`` -- preserves the control
# geometry exactly, so there is no cross-arm fallback and existing control
# contracts are unchanged.
_C0_TREATMENT_SOURCE_GEOMETRY = "qd4_64"
_C0_TREATMENT_GEOMETRY = {
    "slot_bytes": 64 * 1024 * 1024,
    "slot_count": 8,
    "source_workers": 4,
    "slot_owners": (0, 0, 1, 1, 2, 2, 3, 3),
    "capacity_class": "c0-qd4-64m",
}
_C0_CONTROL_GEOMETRY = {
    "slot_bytes": 128 * 1024 * 1024,
    "slot_count": 4,
    "source_workers": 2,
    "slot_owners": (0, 0, 1, 1),
    "capacity_class": "c0-qd2-128m",
}
# Occupancy histogram covers the largest admissible source pool (QD4).
_C0_QD_DISTRIBUTION_MAX = 4


def resolve_c0_geometry(value: Any = None) -> dict:
    """Resolve the selected C0 arena/slot/worker geometry in one place.

    ``value`` (or the deploy-baked environment when omitted) selects exactly one
    geometry.  ``qd4_64`` maps to the treatment tuple; anything else maps to the
    control tuple.  There is deliberately no cross-arm fallback, no partial
    inheritance, and no dependency on the parent H2D QD.
    """
    selected = normalize_source_geometry(value)
    geometry = (
        _C0_TREATMENT_GEOMETRY
        if selected == _C0_TREATMENT_SOURCE_GEOMETRY
        else _C0_CONTROL_GEOMETRY
    )
    resolved = dict(geometry)
    resolved["arena_bytes"] = int(C0_ARENA_BYTES)
    resolved["source_geometry"] = selected
    return resolved


# Resolved once at import from the deploy-baked environment so the public
# constants Golden Serial imports always describe the selected arm.
_ACTIVE_C0_GEOMETRY = resolve_c0_geometry()
C0_SLOT_BYTES = int(_ACTIVE_C0_GEOMETRY["slot_bytes"])
C0_SLOT_COUNT = int(_ACTIVE_C0_GEOMETRY["slot_count"])
C0_SOURCE_WORKERS = int(_ACTIVE_C0_GEOMETRY["source_workers"])
# Slots are pinned to the static source workers only as evidence: the
# dispatcher's StagingPool hands free slots to whichever producer leases next.
C0_SLOT_OWNERS = tuple(int(owner) for owner in _ACTIVE_C0_GEOMETRY["slot_owners"])
C0_CAPACITY_CLASS = str(_ACTIVE_C0_GEOMETRY["capacity_class"])
C0_SOURCE_GEOMETRY = str(_ACTIVE_C0_GEOMETRY["source_geometry"])
# At most one fill can be outstanding per producer, and only the selected
# number of producers exist; the explicit bound keeps the IPC queue finite.
C0_INFLIGHT_LIMIT = C0_SLOT_COUNT
C0_VALID_ROLES = ("model", "clip", "unet", "vae")


def io_process_v2_streaming_enabled() -> bool:
    """True only when the C0 streaming-arena switch is ON (default OFF)."""
    return str(os.environ.get(IO_PROCESS_V2_STREAMING_ENV) or "").strip().lower() in _TRUTHY


IO_PROCESS_V2_SOURCE_ENGINE_ENV = "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE"
_SOURCE_ENGINES = ("preadv", "mmap_fresh")


def resolve_c0_source_engine(value: Any = None) -> str:
    """Resolve the C0 child byte-producer engine (``preadv`` default)."""
    selected = os.environ.get(IO_PROCESS_V2_SOURCE_ENGINE_ENV) if value is None else value
    selected = str(selected if selected is not None else "preadv").strip().lower()
    if selected not in _SOURCE_ENGINES:
        raise ValueError(
            f"invalid C0 source engine {selected!r}; expected one of {_SOURCE_ENGINES}"
        )
    return selected


def c0_mmap_engine_enabled() -> bool:
    """True only when the frozen mmap source engine is selected."""
    return resolve_c0_source_engine() == "mmap_fresh"


IO_PROCESS_V2_C0_HOST_REGISTER_ENV = "COMFYMODAL_GOLDEN_C0_HOST_REGISTER"


def c0_host_register_enabled() -> bool:
    """True only when the C0 POSIX-SHM arena is registered with ``cudaHostRegister``.

    Deploy-baked: read once at arena creation (and mirrored by the parent for
    evidence).  Default ON is the existing production behavior -- the parent
    H2Ds directly from the registered shared mapping with no shared->pinned
    copy.  OFF leaves the byte-identical POSIX-SHM arena (same mapping, slots,
    geometry, source engine, and H2D dispatcher) unregistered.  This isolates
    registration from every other destination/page-state difference.
    """
    raw = str(os.environ.get(IO_PROCESS_V2_C0_HOST_REGISTER_ENV, "1")).strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"invalid C0 host-register selector {raw!r}; expected a boolean token"
    )


def io_process_v2_persistent_fds_enabled() -> bool:
    """True only when the C0 child persistent-FD cache is ON (default OFF).

    Deploy-baked: read once at child launch (and mirrored by the parent for
    evidence).  OFF is the exact per-fill ``os.open -> preadv -> os.close``
    control; ON reuses one positioned descriptor per (path, producer).
    """
    return str(os.environ.get(IO_PROCESS_V2_PERSISTENT_FDS_ENV) or "").strip().lower() in _TRUTHY


def c0_private_split_io_enabled() -> bool:
    """True only when the diagnostic C0 private split staging is ON (default OFF).

    Deploy-baked: read once at child launch (and mirrored by the parent for
    evidence). OFF is the exact direct source -> leased SHM slot child path. ON
    adds one reusable private buffer per source worker (thread or mmap reader
    process) and an explicit copy into the leased slot. Evidence-only; never
    changes geometry or H2D.
    """
    return str(os.environ.get(IO_PROCESS_V2_C0_PRIVATE_SPLIT_IO_ENV) or "").strip().lower() in _TRUTHY


def child_viztracer_enabled() -> bool:
    """True only when the C0 child forensic VizTracer capture is ON (default OFF)."""
    return str(os.environ.get(GOLDEN_C0_CHILD_VIZTRACER_ENV) or "").strip().lower() in _TRUTHY


def child_viztracer_output_path() -> str:
    """Deterministic child trace path shared by the parent and the child."""
    return _C0_CHILD_VIZTRACER_PATH


def c0_source_volume_v1_enabled() -> bool:
    """True only when the distinct C0 direct Volume V1 treatment is ON.

    Deploy-baked: read once at child launch (and mirrored by the parent for
    evidence).  OFF is the exact C0 preadv control.  ON has no preadv fallback.
    """
    return str(os.environ.get(IO_PROCESS_V2_C0_SOURCE_VOLUME_V1_ENV) or "").strip().lower() in _TRUTHY


def c0_source_volume_name() -> str:
    """The same-name V1 models Volume whose object id the parent resolves."""
    return (
        str(os.environ.get("COMFYMODAL_MODELS_VOLUME") or "comfyui-models").strip()
        or "comfyui-models"
    )


def c0_source_volume_mount() -> str:
    """Container-local mount prefix for the models Volume."""
    return (
        str(os.environ.get(C0_SOURCE_VOLUME_MOUNT_ENV) or _DEFAULT_MODELS_MOUNT).strip()
        or _DEFAULT_MODELS_MOUNT
    )


def c0_preadv_sickness_diag_enabled() -> bool:
    """True only when the clustered preadv-sickness diagnostic is ON (default OFF).

    Deploy-baked: read once at child launch (and mirrored by the parent for
    evidence).  OFF is the exact C0 preadv persistent-FD control; ON adds the
    registry/watchdog/probe diagnostics and never changes geometry, the FD
    lifecycle, H2D, adoption, or validation.
    """
    return (
        str(os.environ.get(IO_PROCESS_V2_C0_PREADV_SICKNESS_DIAG_ENV) or "")
        .strip().lower() in _TRUTHY
    )


def c0_preadv_controls_manifest_path() -> str:
    """Deterministic checked-in control-offset manifest path."""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        C0_PREADV_SICKNESS_CONTROLS_BASENAME,
    )


def load_c0_preadv_controls() -> dict:
    """Load the pre-registered CLIP/UNET control manifest (never raises)."""
    path = c0_preadv_controls_manifest_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        return {
            "schema": "comfymodal.c0.preadv.controls",
            "load_error": f"{type(exc).__name__}:{exc}"[:160],
            "files": {},
        }
    if not isinstance(manifest, dict):
        return {
            "schema": "comfymodal.c0.preadv.controls",
            "load_error": "not_a_mapping",
            "files": {},
        }
    return manifest


def c0_preadv_sickness_config_hashes() -> dict:
    """Canonical selector/config hash plus the profile identity and hash.

    The hash is derived from the launch-time selector values only, so it is the
    same value the child computes at spawn and independent of wall-clock or any
    request payload.
    """
    profile = str(os.environ.get("COMFYMODAL_V2_ENV_PROFILE") or "inherit")
    canonical = {
        "selector": True,
        "persistent_fds": io_process_v2_persistent_fds_enabled(),
        "private_split_io": c0_private_split_io_enabled(),
        "source_volume_v1": c0_source_volume_v1_enabled(),
        "child_viztracer": child_viztracer_enabled(),
        "source_geometry": C0_SOURCE_GEOMETRY,
        "slot_bytes": int(C0_SLOT_BYTES),
        "slot_count": int(C0_SLOT_COUNT),
        "source_workers": int(C0_SOURCE_WORKERS),
        "tripwire_ns": int(C0_PREADV_SICKNESS_TRIPWIRE_NS),
        "profile": profile,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "profile": profile,
        "profile_hash": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
        "config_hash": hashlib.sha256(blob).hexdigest(),
        "canonical": canonical,
    }


def c0_preadv_sickness_invocation_id() -> str:
    """Invocation-bound identifier; never a newest-file/timestamp heuristic."""
    digest = hashlib.sha256(
        (str(os.getpid()) + ":" + str(time.time_ns())).encode("utf-8")
    ).hexdigest()
    return digest[:24]


def _default_c0_source_volume_resolver(volume_name: str) -> dict:
    """Resolve the V1 Volume object id once, under the container's Modal auth.

    Uses only the public Modal client handle; the internal ``_client``/stub
    transport is the child's business.  Kept as a module-level hook so pure
    tests can inject a resolver without Modal or network access.
    """
    import modal

    volume = modal.Volume.from_name(str(volume_name), create_if_missing=False)
    volume.hydrate()
    return {
        "volume_id": str(volume.object_id or ""),
        "volume_name": str(volume_name),
    }


# Injectable resolver hook: production uses the Modal client above; tests
# replace this with a pure fake.  Never hardcode a stale object id anywhere.
_c0_source_volume_resolver = _default_c0_source_volume_resolver


def resolve_c0_source_volume_metadata(volume_name: Optional[str] = None) -> dict:
    """Resolve the same-name V1 Volume identity for the child launch.

    Fails closed (raises) when the object id cannot be resolved so an ON
    selector can never silently degrade to the preadv control.  The optional
    expected id is recorded as evidence only and never gates the launch.
    """
    name = c0_source_volume_name() if volume_name is None else str(volume_name)
    resolved = _c0_source_volume_resolver(name)
    if not isinstance(resolved, dict):
        raise RuntimeError("c0_source_volume_resolver_invalid")
    volume_id = str(resolved.get("volume_id") or "").strip()
    if not volume_id:
        raise RuntimeError(f"c0_source_volume_id_unresolved:{name}")
    expected = (
        str(os.environ.get(C0_SOURCE_VOLUME_EXPECTED_ID_ENV) or "").strip() or None
    )
    return {
        "volume_name": name,
        "volume_id": volume_id,
        "mount": c0_source_volume_mount(),
        "volume_type": "V1",
        "expected_object_id": expected,
        "object_id_matches_expected": (volume_id == expected) if expected else None,
    }


def child_viztracer_artifact() -> dict:
    """Return the child trace path and terminal status for parent finalization.

    When the flag is OFF this is an explicit ``disabled`` record.  When ON the
    child writes its terminal status beside the trace file; a missing status
    file is reported as ``missing`` rather than assumed complete.  Never raises.
    """
    enabled = child_viztracer_enabled()
    path = child_viztracer_output_path()
    artifact: dict = {
        "enabled": bool(enabled),
        "path": path,
        "status": "disabled" if not enabled else "missing",
        "trace_present": False,
    }
    if not enabled:
        return artifact
    try:
        with open(path + ".status.json", "r", encoding="utf-8") as handle:
            status = json.load(handle)
        if isinstance(status, dict):
            artifact.update({str(k): v for k, v in status.items()})
    except Exception:
        pass
    artifact["trace_present"] = bool(os.path.isfile(path))
    try:
        runtime = get_arena_runtime()
        ready = getattr(runtime, "child_viztracer", None) if runtime is not None else None
        if isinstance(ready, dict):
            artifact["ready_status"] = str(ready.get("status") or "")
    except Exception:
        pass
    return artifact


def _read_runtime_text(path: str, limit: int = 240) -> Optional[str]:
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read(int(limit)).strip()
    except Exception:
        return None


def platform_runtime_markers() -> dict:
    """Best-effort parent/child platform/runtime markers for C0 evidence.

    Captures the kernel release/version, ``/proc/version``, an explicit
    gVisor/runsc marker when the platform exposes one, and the transparent
    hugepage shmem policy when readable.  The C0 mapping is the same-container
    reproduction: these markers exist so a missing upstream gVisor fix can be
    seen in evidence, and they never gate behavior.  Never raises; missing
    values stay ``None``.
    """
    markers: dict = {
        "platform_release": None,
        "platform_version": None,
        "proc_version": None,
        "gvisor_marker": None,
        "shmem_enabled": None,
        "shmem_enabled_path": "/sys/kernel/mm/transparent_hugepage/shmem_enabled",
    }
    try:
        markers["platform_release"] = str(platform.release())
        markers["platform_version"] = str(platform.version())
    except Exception:
        pass
    proc_version = _read_runtime_text("/proc/version")
    markers["proc_version"] = proc_version
    haystack = (proc_version or "").lower()
    for needle in ("gvisor", "runsc"):
        if needle in haystack:
            markers["gvisor_marker"] = needle
            break
    markers["shmem_enabled"] = _read_runtime_text(markers["shmem_enabled_path"])
    return markers


# ══════════════════════════════════════════════════════════════════════════════
# C0 bounded preadv diagnostics (passive evidence only)
# ══════════════════════════════════════════════════════════════════════════════
# Everything below is passive, fail-open, and never branched on by the fill
# path.  The parent samples the CUDA-sterile child's task/cgroup/PSI state only
# while a fill is actually outstanding, and the child captures a bounded
# post-hoc self snapshot only for reads that ran longer than the threshold.
# Neither path reads/copies payload bytes, changes geometry, the FD lifecycle,
# H2D, restore, or the sampler.

C0_LIVE_SAMPLER_ENV = "COMFYMODAL_GOLDEN_C0_LIVE_SAMPLER"
# Default ON: the parent sampler is the preferred evidence source.  An explicit
# falsy value disables it, leaving the child post-hoc fallback as the only
# origin.  The child fallback is always available so evidence survives even when
# the parent cannot open the child's procfs.
_C0_LIVE_SAMPLER_DEFAULT_ENABLED = True
_C0_LIVE_SAMPLER_POLL_S = 0.025
_C0_LIVE_SAMPLER_THRESHOLD_NS = 100_000_000
_C0_LIVE_SAMPLER_CAP = 32
_C0_CHILD_FALLBACK_CAP = 32
_C0_CHILD_FALLBACK_THRESHOLD_NS = 100_000_000

_MOUNTINFO_UNESCAPE = {"040": " ", "011": "\t", "012": "\n", "134": "\\"}


def c0_live_sampler_enabled() -> bool:
    """True when the parent C0 live sampler is armed (default ON)."""
    raw = os.environ.get(C0_LIVE_SAMPLER_ENV)
    if raw is None or not str(raw).strip():
        return bool(_C0_LIVE_SAMPLER_DEFAULT_ENABLED)
    return str(raw).strip().lower() in _TRUTHY


def _unescape_mountinfo_field(value: Any) -> str:
    """Decode the octal escapes mountinfo(5) uses for space/tab/newline/backslash."""
    text = str(value or "")
    if "\\" not in text:
        return text
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == "\\" and index + 4 <= length and text[index + 1:index + 4].isdigit():
            token = text[index + 1:index + 4]
            out.append(_MOUNTINFO_UNESCAPE.get(token, text[index:index + 4]))
            index += 4
        else:
            out.append(text[index])
            index += 1
    return "".join(out)


def parse_mountinfo_line(line: str) -> Optional[dict]:
    """Parse one ``/proc/self/mountinfo`` line; None when malformed.

    Fields: mount id, parent id, major:minor, root, mount point, per-mount
    options, optional fields, fstype, source, super options.  Pure parsing; the
    octal escapes are decoded.  Never raises.
    """
    if not isinstance(line, str) or " - " not in line:
        return None
    left, right = line.split(" - ", 1)
    lparts = left.split()
    rparts = right.split()
    if len(lparts) < 6 or len(rparts) < 2:
        return None
    try:
        mount_id = int(lparts[0])
        parent_id = int(lparts[1])
    except (TypeError, ValueError):
        return None
    return {
        "mount_id": mount_id,
        "parent_id": parent_id,
        "major_minor": str(lparts[2]),
        "root": _unescape_mountinfo_field(lparts[3]),
        "mount_point": _unescape_mountinfo_field(lparts[4]),
        "mount_options": _unescape_mountinfo_field(lparts[5]),
        "optional_fields": [_unescape_mountinfo_field(f) for f in lparts[6:]],
        "fstype": str(rparts[0]),
        "source": _unescape_mountinfo_field(rparts[1]),
        "super_options": _unescape_mountinfo_field(" ".join(rparts[2:])),
    }


def _best_mount_for_path(mounts: Sequence[dict], path: str) -> Optional[dict]:
    """Longest-prefix mountinfo match for a path; None when nothing matches."""
    best: Optional[dict] = None
    for entry in mounts:
        mount_point = str(entry.get("mount_point") or "")
        if not mount_point:
            continue
        if mount_point == "/":
            matched = True
        else:
            prefix = mount_point.rstrip("/")
            matched = path == mount_point or path.startswith(prefix + "/")
        if matched:
            if best is None or len(mount_point) > len(str(best.get("mount_point") or "")):
                best = entry
    return best


def _statfs_numeric_type(path: str) -> dict:
    """Numeric filesystem type for a path (statfs f_type; statvfs fallback)."""
    out: dict = {
        "path": str(path),
        "status": "unavailable",
        "f_type": None,
        "f_bsize": None,
        "f_blocks": None,
        "f_bavail": None,
        "error": None,
    }
    statfs = getattr(os, "statfs", None)
    if callable(statfs):
        try:
            st = statfs(str(path))
            f_type = getattr(st, "f_type", None)
            out.update({
                "status": "available",
                "f_type": int(f_type) if f_type is not None else None,
                "f_bsize": int(getattr(st, "f_bsize", 0) or 0) or None,
                "f_blocks": int(getattr(st, "f_blocks", 0) or 0) or None,
                "f_bavail": int(getattr(st, "f_bavail", 0) or 0) or None,
            })
            return out
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"statfs:{type(exc).__name__}"[:120]
    statvfs = getattr(os, "statvfs", None)
    if callable(statvfs):
        try:
            st = statvfs(str(path))
            out.update({
                "status": "statvfs_only",
                "f_bsize": int(getattr(st, "f_frsize", 0) or 0) or None,
                "f_blocks": int(getattr(st, "f_blocks", 0) or 0) or None,
                "f_bavail": int(getattr(st, "f_bavail", 0) or 0) or None,
            })
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"statvfs:{type(exc).__name__}"[:120]
    return out


def read_mount_identity(
    paths: Sequence[str],
    *,
    mountinfo_path: str = "/proc/self/mountinfo",
) -> dict:
    """One-time, filtered mount identity for the given paths; never raises.

    Filters mountinfo to the exact paths (longest-prefix match), decodes the
    octal escapes, and records statfs/statvfs numeric types.  A fuse-like
    fstype is reported only when mountinfo actually says so; FUSE is never
    assumed.  Missing/unreadable mountinfo is an explicit ``supported=False``
    with an error, never a fabricated entry.
    """
    result: dict = {
        "supported": False,
        "mountinfo_path": str(mountinfo_path),
        "error": None,
        "entries": [],
        "paths": {},
        "statfs": {},
        "fstypes": [],
        "has_fuse_fstype": False,
    }
    entries: list[dict] = []
    text: Optional[str] = None
    try:
        with open(str(mountinfo_path), "r", errors="replace") as handle:
            text = handle.read()
        result["supported"] = True
    except Exception as exc:  # noqa: BLE001
        result["supported"] = False
        result["error"] = f"{type(exc).__name__}:{exc}"[:160]
    if text:
        for line in text.splitlines():
            parsed = parse_mountinfo_line(line)
            if parsed is not None:
                entries.append(parsed)
    result["entries"] = entries
    fstypes = sorted({str(e.get("fstype")) for e in entries if e.get("fstype")})
    result["fstypes"] = fstypes
    result["has_fuse_fstype"] = any("fuse" in fstype.lower() for fstype in fstypes)
    for raw_path in paths:
        raw = str(raw_path)
        try:
            normalized = os.path.abspath(raw)
        except Exception:  # noqa: BLE001
            normalized = raw
        # Prefer the raw mountinfo-style path; the abspath is a fallback for
        # hosts (Windows) where abspath would rewrite a Unix-style path.
        mount = _best_mount_for_path(entries, raw)
        if mount is None and normalized != raw:
            mount = _best_mount_for_path(entries, normalized)
        result["paths"][raw] = {
            "path": normalized,
            "mount": mount,
        }
        result["statfs"][raw] = _statfs_numeric_type(raw)
    return result


def _page_size() -> int:
    try:
        value = int(os.sysconf("SC_PAGE_SIZE"))
        if value > 0:
            return value
    except Exception:  # noqa: BLE001
        pass
    return 4096


def mincore_residency(address: int, length: int, *, page_size: Optional[int] = None) -> dict:
    """Passive page-residency of one host range via libc ``mincore``; no reads.

    Returns explicit supported/status/error.  Non-posix or any syscall failure
    leaves counts ``None`` rather than a fabricated zero.  The range is aligned
    to the page size before sampling, so ``total_pages`` is the aligned count.
    """
    result: dict = {
        "status": "unsupported",
        "supported": False,
        "address": int(address),
        "length": int(length),
        "page_size": None,
        "total_pages": None,
        "resident_pages": None,
        "resident_percent": None,
        "error": None,
    }
    if os.name != "posix":
        result["error"] = "non_posix"
        return result
    page = int(page_size) if page_size else _page_size()
    result["page_size"] = page
    start = int(address) & ~(page - 1)
    end = int(address) + int(length)
    end_aligned = (end + page - 1) & ~(page - 1)
    n_pages = (end_aligned - start) // page
    if n_pages <= 0:
        result.update({
            "status": "empty",
            "supported": True,
            "total_pages": 0,
            "resident_pages": 0,
            "resident_percent": 0.0,
        })
        return result
    try:
        try:
            libc = ctypes.CDLL(None, use_errno=True)
        except Exception:  # noqa: BLE001
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
        fn = libc.mincore
        fn.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        fn.restype = ctypes.c_int
        vec = (ctypes.c_ubyte * n_pages)()
        rc = fn(ctypes.c_void_p(start), ctypes.c_size_t(end_aligned - start), vec)
        if rc != 0:
            result.update({
                "status": "error",
                "supported": True,
                "error": f"mincore_errno:{ctypes.get_errno()}",
            })
            return result
        resident = sum(1 for value in vec if value & 0x01)
        result.update({
            "status": "ok",
            "supported": True,
            "total_pages": n_pages,
            "resident_pages": resident,
            "resident_percent": round(resident / n_pages * 100.0, 2),
        })
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}:{exc}"[:160]
    return result


def _source_cachestat(fd: int) -> dict:
    """Optional cachestat; explicit unsupported when the platform lacks it."""
    cachestat = getattr(os, "cachestat", None)
    if not callable(cachestat):
        return {"status": "unsupported", "error": "os.cachestat_unavailable"}
    try:
        st = cachestat(int(fd))
        fields = {}
        for name in dir(st):
            if name.startswith("_"):
                continue
            try:
                value = getattr(st, name)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                fields[name] = value
        return {"status": "available", "fields": fields}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:160]}


def probe_source_cache(
    path: str,
    *,
    ranges: Optional[Sequence[tuple[int, int]]] = None,
    max_bytes: int = 16 * 1024 * 1024,
) -> dict:
    """One-time page-cache residency probe for a source file; no reads/touches.

    Opens a separate ``O_RDONLY`` probe descriptor, ``fstat``s it, memory-maps
    only the requested (page-aligned) file range(s), samples ``mincore`` without
    reading or advising, then unmaps and closes.  Cachestat is reported only
    when the platform genuinely exposes it.  Never raises; virtualized or
    unsupported hosts report explicit status instead of inferred cache state.
    """
    out: dict = {
        "path": str(path),
        "status": "unsupported",
        "supported": False,
        "file_size": None,
        "ranges": [],
        "cachestat": {"status": "disabled", "error": None},
        "error": None,
    }
    if os.name != "posix":
        out["error"] = "non_posix"
        return out
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except Exception as exc:  # noqa: BLE001
        out.update({"status": "error", "error": f"open:{type(exc).__name__}:{exc}"[:160]})
        return out
    try:
        try:
            size = int(os.fstat(fd).st_size)
        except Exception as exc:  # noqa: BLE001
            out.update({"status": "error", "error": f"fstat:{type(exc).__name__}"[:160]})
            return out
        out["file_size"] = size
        requested = list(ranges) if ranges else [(0, min(size, int(max_bytes)))]
        align = int(getattr(mmap, "ALLOCATIONGRANULARITY", _page_size()) or _page_size())
        if align <= 0:
            align = _page_size()
        regions: list[tuple[int, int]] = []
        for offset, length in requested:
            try:
                offset = max(0, int(offset))
                length = max(0, int(length))
            except (TypeError, ValueError):
                continue
            if length <= 0 or offset >= size:
                continue
            length = min(length, size - offset)
            aligned_offset = offset - (offset % align)
            aligned_length = length + (offset - aligned_offset)
            regions.append((aligned_offset, aligned_length))
        if not regions:
            regions = [(0, min(size, int(max_bytes)))]
        for offset, length in regions:
            entry: dict = {"offset": offset, "length": length, "status": "unavailable"}
            if length <= 0:
                entry["status"] = "empty"
                out["ranges"].append(entry)
                continue
            try:
                mapping = mmap.mmap(fd, length, offset=offset, access=mmap.ACCESS_COPY)
            except Exception as exc:  # noqa: BLE001
                entry.update({"status": "mmap_error", "error": f"{type(exc).__name__}:{exc}"[:120]})
                out["ranges"].append(entry)
                continue
            try:
                address = ctypes.addressof(ctypes.c_char.from_buffer(mapping))
                residency = mincore_residency(address, length)
                residency.update({"offset": offset, "length": length})
                out["ranges"].append(residency)
            finally:
                try:
                    mapping.close()
                except Exception:  # noqa: BLE001
                    pass
        out["supported"] = True
        if any(entry.get("status") == "ok" for entry in out["ranges"]):
            out["status"] = "ok"
        else:
            out["status"] = "unavailable"
            out["error"] = "no_ok_range"
        out["cachestat"] = _source_cachestat(fd)
    finally:
        try:
            os.close(fd)
        except Exception:  # noqa: BLE001
            pass
    return out


def _read_thp_state() -> dict:
    """THP shmem/enabled/defrag files if readable; fail-open, no fabrication."""
    paths = {
        "shmem_enabled": "/sys/kernel/mm/transparent_hugepage/shmem_enabled",
        "enabled": "/sys/kernel/mm/transparent_hugepage/enabled",
        "defrag": "/sys/kernel/mm/transparent_hugepage/defrag",
    }
    out: dict = {}
    for key, path in paths.items():
        value = _read_runtime_text(path, 256)
        out[key] = {
            "path": path,
            "available": value is not None,
            "value": value,
        }
    return out


def _read_proc_task_stat(pid: int, tid: Optional[int] = None) -> dict:
    """Parse ``/proc/<pid>/task/<tid>/stat`` (or main-thread stat); fail-open."""
    path = (
        f"/proc/{int(pid)}/task/{int(tid)}/stat"
        if tid is not None else f"/proc/{int(pid)}/stat"
    )
    text = _read_runtime_text(path, 4096)
    if text is None:
        return {"available": False, "path": path, "error": "stat_unreadable"}
    try:
        rparen = text.rfind(")")
        rest = text[rparen + 1:].split()
    except Exception:  # noqa: BLE001
        return {"available": False, "path": path, "error": "stat_parse"}
    if len(rest) < 13:
        return {"available": False, "path": path, "error": "stat_short"}

    def _int_at(index: int) -> Optional[int]:
        if index >= len(rest):
            return None
        token = rest[index].lstrip("-")
        return int(rest[index]) if token.isdigit() else None

    return {
        "available": True,
        "path": path,
        "state": rest[0],
        "minflt": _int_at(7),
        "majflt": _int_at(9),
        "utime": _int_at(11),
        "stime": _int_at(12),
        "processor": _int_at(36),
        "policy": _int_at(38),
        "delayacct_blkio_ticks": _int_at(39),
    }


def _read_proc_status_subset(pid: int, tid: Optional[int] = None) -> dict:
    """Read the scheduling/switch/affinity subset of a task status; fail-open."""
    path = (
        f"/proc/{int(pid)}/task/{int(tid)}/status"
        if tid is not None else f"/proc/{int(pid)}/status"
    )
    text = _read_runtime_text(path, 32768)
    if text is None:
        return {"available": False, "path": path, "error": "status_unreadable"}
    wanted = {
        "State", "Cpus_allowed_list", "Mems_allowed_list",
        "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches",
        "Threads", "Seccomp", "VmRSS", "VmSwap",
    }
    out: dict = {"available": True, "path": path}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key in wanted:
            out[key] = value.strip()
    return out


def _read_proc_io(pid: int, tid: Optional[int] = None) -> dict:
    """Parse a process or task ``io`` file into integer counters; fail-open."""
    path = (
        f"/proc/{int(pid)}/task/{int(tid)}/io"
        if tid is not None else f"/proc/{int(pid)}/io"
    )
    text = _read_runtime_text(path, 4096)
    if text is None:
        return {"available": False, "path": path, "error": "io_unreadable"}
    out: dict = {"available": True, "path": path}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        token = value.strip()
        if key and token.lstrip("-").isdigit():
            out[key] = int(token)
    return out


def _read_keyval_file(path: str, limit: int = 16384) -> dict:
    """Read a small ``key value``/``key: value`` file; fail-open."""
    text = _read_runtime_text(path, limit)
    if text is None:
        return {"available": False, "path": str(path), "error": "unreadable"}
    values: dict = {"available": True, "path": str(path)}
    for line in text.splitlines():
        key, _, value = line.partition(" ")
        if not key:
            continue
        token = value.strip()
        if token.lstrip("-").isdigit():
            values[key] = int(token)
        elif token:
            values[key] = token
    return values


def _read_cgroup_raw(base: Optional[str]) -> dict:
    """Snapshot the v2 cgroup cpu/memory/io/PSI files under ``base``; fail-open."""
    out: dict = {
        "base": base,
        "status": "unavailable",
        "cpu_stat": None,
        "memory_stat": None,
        "memory_events": None,
        "memory_current": None,
        "io_stat_snippet": None,
        "error": None,
    }
    if not base:
        out["error"] = "cgroup_base_unavailable"
        return out
    try:
        if not os.path.isdir(str(base)):
            out["error"] = "cgroup_base_missing"
            return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}"[:120]
        return out
    available = False
    for key, filename in (
        ("cpu_stat", "cpu.stat"),
        ("memory_stat", "memory.stat"),
        ("memory_events", "memory.events"),
    ):
        parsed = _read_keyval_file(os.path.join(str(base), filename), 8192)
        out[key] = parsed
        available = available or bool(parsed.get("available"))
    memory_current = _read_runtime_text(os.path.join(str(base), "memory.current"), 1024)
    if memory_current is not None:
        out["memory_current"] = memory_current.strip()
        available = True
    io_snippet = _read_runtime_text(os.path.join(str(base), "io.stat"), 2048)
    if io_snippet is not None:
        out["io_stat_snippet"] = " | ".join(
            line.strip() for line in io_snippet.splitlines()[:4] if line.strip()
        )[:600]
        available = True
    out["status"] = "available" if available else "unavailable"
    if not available:
        out["error"] = "cgroup_files_missing"
    return out


def _read_pressure_snapshot() -> dict:
    """Read ``/proc/pressure/*`` without the synthetic-detection sleep; fail-open.

    The host-telemetry ``read_psi`` intentionally sleeps 200 ms to detect a
    synthetic file; the live sampler must never pay that per poll, so this is a
    dedicated cheap reader.  Absent sources stay unavailable, never zero.
    """
    out: dict = {"status": "unavailable", "sources": {}, "error": None}
    base = "/proc/pressure"
    try:
        if not os.path.isdir(base):
            out["error"] = "pressure_tree_absent"
            return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}"[:120]
        return out
    any_available = False
    for source in ("cpu", "memory", "io"):
        text = _read_runtime_text(f"{base}/{source}", 512)
        if text is None:
            out["sources"][source] = {"available": False}
            continue
        any_available = True
        parsed: dict = {"available": True}
        for line in text.splitlines():
            parts = line.split()
            if not parts or parts[0] not in ("some", "full"):
                continue
            fields: dict = {}
            for token in parts[1:]:
                key, _, value = token.partition("=")
                if key in ("avg10", "avg60", "avg300"):
                    try:
                        fields[key] = float(value)
                    except ValueError:
                        pass
                elif key == "total":
                    try:
                        fields[key] = int(value)
                    except ValueError:
                        pass
            parsed[parts[0]] = fields
        out["sources"][source] = parsed
    out["status"] = "available" if any_available else "unavailable"
    return out


def _runtime_cgroup_base() -> Optional[str]:
    """Resolve the cgroup directory once for per-sample file reads; fail-open."""
    try:
        from .host_hardware_telemetry import read_cgroup_fields

        info = read_cgroup_fields()
        mount_point = info.get("cgroup_mount_point")
        rel_path = info.get("cgroup_rel_path")
        if mount_point and rel_path is not None:
            rel = str(rel_path)
            if rel in ("", "/"):
                return str(mount_point)
            return os.path.join(str(mount_point), rel.lstrip("/"))
        return str(mount_point) if mount_point else None
    except Exception:  # noqa: BLE001
        return None


def collect_runtime_identity() -> dict:
    """One-time runtime/cgroup/PSI identity snapshot; never raises.

    Uses the existing host-telemetry helpers where safe (cgroup discovery and
    the PSI reader) plus small stdlib fail-open reads.  The guest kernel
    identity is reported as observed; it is never assumed equal to the host.
    """
    out: dict = {
        "platform_release": None,
        "platform_version": None,
        "platform_machine": None,
        "uname": None,
        "python": sys.version.split()[0],
        "proc_version": None,
        "cpu_count": None,
        "effective_cpu_count": None,
        "cpu_affinity": None,
        "seccomp": None,
        "cgroup": None,
        "psi": None,
        "error": None,
    }
    try:
        out["platform_release"] = str(platform.release())
        out["platform_version"] = str(platform.version())
        out["platform_machine"] = str(platform.machine())
        uname = platform.uname()
        out["uname"] = {
            "system": str(uname.system),
            "node": str(uname.node),
            "release": str(uname.release),
            "version": str(uname.version),
            "machine": str(uname.machine),
            "processor": str(uname.processor),
        }
    except Exception:  # noqa: BLE001
        pass
    out["proc_version"] = _read_runtime_text("/proc/version", 512)
    try:
        out["cpu_count"] = os.cpu_count()
    except Exception:  # noqa: BLE001
        pass
    try:
        affinity = os.sched_getaffinity(0)
        out["effective_cpu_count"] = len(affinity)
        out["cpu_affinity"] = sorted(int(cpu) for cpu in affinity)
    except Exception:  # noqa: BLE001
        pass
    try:
        status = _read_proc_status_subset(os.getpid())
        if status.get("available"):
            out["seccomp"] = status.get("Seccomp")
            out["self_status"] = {
                key: status.get(key)
                for key in ("State", "Cpus_allowed_list", "Mems_allowed_list", "Threads")
            }
    except Exception:  # noqa: BLE001
        pass
    try:
        from .host_hardware_telemetry import read_cgroup_fields, read_psi

        out["cgroup"] = read_cgroup_fields()
        out["psi"] = read_psi()
    except Exception as exc:  # noqa: BLE001
        out["cgroup"] = {"cgroup_source": "unavailable"}
        out["psi"] = {"psi_status": "unavailable"}
        out["error"] = f"host_hardware:{type(exc).__name__}"[:120]
    return out


def _child_fallback_records(diagnostics: Any) -> int:
    """Count child post-hoc fallback captures across a diagnostic list."""
    count = 0
    if not isinstance(diagnostics, list):
        return 0
    for record in diagnostics:
        if isinstance(record, dict) and isinstance(record.get("child_fallback"), dict):
            count += 1
    return count


def c0_selected() -> bool:
    """Resolve the C0 selector, failing closed when it is armed without V2.

    C0 has no cross-arm fallback: requesting it without the base V2 switch is a
    configuration error, not a silent downgrade to Treatment B.  The
    persistent-FD cache is a C0-child treatment with no meaning outside the C0
    streaming arena, so arming it without C0 is rejected instead of silently
    inert.
    """
    selected = io_process_v2_streaming_enabled()
    if io_process_v2_persistent_fds_enabled() and not selected:
        raise RuntimeError("golden_io_v2_persistent_fds_requires_c0_streaming")
    if c0_private_split_io_enabled() and not selected:
        raise RuntimeError("golden_io_v2_c0_private_split_io_requires_c0_streaming")
    if c0_source_volume_v1_enabled() and not selected:
        raise RuntimeError("golden_io_v2_c0_source_volume_v1_requires_c0_streaming")
    if c0_preadv_sickness_diag_enabled() and not selected:
        raise RuntimeError("golden_io_v2_c0_preadv_sickness_diag_requires_c0_streaming")
    if selected and not io_process_v2_enabled():
        raise RuntimeError("golden_io_v2_c0_requires_v2")
    return selected


def c0_transport_dimensions() -> dict:
    """Resolve the selected C0 parent transport geometry in one place.

    C0 owns exactly ``C0_SOURCE_WORKERS`` child fill workers.  The static
    dispatcher plans one disjoint contiguous source region per *producer*, so
    the parent ``producer_workers`` MUST equal the child pool size; inheriting
    a wider parent H2D QD (or the ``TransportConfig`` default of 4) would plan
    more regions than the child pool has workers.

    ``C0_SLOT_OWNERS`` stays evidence only: the dispatcher's StagingPool hands
    free slots to whichever producer leases next, so the correspondence is
    recorded, not enforced.  The returned tuple is the deploy-baked selection
    (control ``qd2_128`` -> 2 workers / 4 slots / 128 MiB, treatment
    ``qd4_64`` -> 4 workers / 8 slots / 64 MiB) with no cross-arm fallback.
    """
    return {
        "queue_depth": C0_SOURCE_WORKERS,
        "block_bytes": C0_SLOT_BYTES,
        "staging_slots": C0_SLOT_COUNT,
        "producer_workers": C0_SOURCE_WORKERS,
    }


class C0ProtocolError(RuntimeError):
    """Fail-closed error for any invalid C0 child-fill request or reply."""


@dataclass(frozen=True)
class C0FillRequest:
    """One lease-aware child-fill command.

    Every field is part of the identity contract: a reply is only accepted when
    it echoes the exact request, slot, generation, and arena epoch.  The parent
    never copies the payload; the child writes the bytes directly into the
    leased shared slot named by ``slot_index``.
    """

    request_id: int
    arena_epoch: int
    role: str
    source: str
    slot_index: int
    slot_generation: int
    source_offset: int
    destination_offset: int
    length: int
    # Producer identity is not part of the fill identity contract; it selects
    # the child's persistent (path, producer) FD-cache key.  Default 0 keeps the
    # pre-existing single-producer call shape valid.
    producer_id: int = 0
    # Passive correlation metadata, also outside the identity contract.  The
    # child echoes them onto every per-read syscall diagnostic; the parent uses
    # them only to correlate a physical read with its submission.  Defaults keep
    # every pre-existing call shape valid.
    record_id: str | int | None = None
    fill_index: int | None = None

    def as_message(self) -> dict:
        return {
            "op": "fill",
            "request_id": int(self.request_id),
            "arena_epoch": int(self.arena_epoch),
            "role": str(self.role),
            "path": str(self.source),
            "slot_index": int(self.slot_index),
            "slot_generation": int(self.slot_generation),
            "source_offset": int(self.source_offset),
            "destination_offset": int(self.destination_offset),
            "length": int(self.length),
            "producer_id": int(self.producer_id),
            "record_id": self.record_id,
            "fill_index": self.fill_index,
        }


def _require_plain_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise C0ProtocolError(f"c0_invalid_{name}:{value!r}")
    return int(value)


def _is_plain_int(value: Any) -> bool:
    """True only for a real ``int`` (never a bool); child evidence gate."""
    return isinstance(value, int) and not isinstance(value, bool)


def _nearest_rank_percentile(values: Sequence[int], fraction: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(int(value) for value in values)
    index = int(round(fraction * (len(ordered) - 1)))
    return int(ordered[max(0, min(index, len(ordered) - 1))])


def _read_duration_summary(durations_ns: Sequence[int]) -> dict:
    """Aggregate per-fill child positioned-read durations (count, p50, p90, max).

    The aggregate is derived from child replies; the raw per-fill samples are
    retained so terminal evidence can prove the summary.  All units are ms.
    """
    values = [int(value) for value in durations_ns]
    if not values:
        return {
            "count": 0,
            "p50_ms": None,
            "p90_ms": None,
            "max_ms": None,
            "total_ms": 0.0,
            "samples_ms": [],
        }
    p50 = _nearest_rank_percentile(values, 0.50)
    p90 = _nearest_rank_percentile(values, 0.90)
    return {
        "count": len(values),
        "p50_ms": round(p50 / 1e6, 4) if p50 is not None else None,
        "p90_ms": round(p90 / 1e6, 4) if p90 is not None else None,
        "max_ms": round(max(values) / 1e6, 4),
        "total_ms": round(sum(values) / 1e6, 4),
        "samples_ms": [round(value / 1e6, 4) for value in values],
    }


def validate_fill_request(request: C0FillRequest) -> None:
    """Validate a fill request against the fixed C0 arena bounds.

    Runs in the parent before send and is mirrored by the child.  Out-of-range
    slot/length/destination values are rejected before they can reach the
    registered mapping.
    """
    if not isinstance(request, C0FillRequest):
        raise C0ProtocolError("c0_fill_request_not_typed")
    if request.role not in C0_VALID_ROLES:
        raise C0ProtocolError(f"c0_invalid_role:{request.role!r}")
    if not isinstance(request.source, str) or not request.source:
        raise C0ProtocolError("c0_invalid_source_identity")
    _require_plain_int(request.request_id, "request_id", minimum=1)
    _require_plain_int(request.arena_epoch, "arena_epoch", minimum=0)
    producer_id = _require_plain_int(request.producer_id, "producer_id")
    if producer_id >= C0_SOURCE_WORKERS:
        raise C0ProtocolError(f"c0_producer_id_out_of_range:{producer_id}")
    # Optional correlation metadata.  Validated only when present so every
    # pre-existing call shape (both fields default None) stays valid.
    if request.record_id is not None and not isinstance(request.record_id, (str, int)):
        raise C0ProtocolError(f"c0_invalid_record_id:{request.record_id!r}")
    if request.fill_index is not None:
        _require_plain_int(request.fill_index, "fill_index")
    slot_index = _require_plain_int(request.slot_index, "slot_index")
    if slot_index >= C0_SLOT_COUNT:
        raise C0ProtocolError(f"c0_slot_out_of_range:{slot_index}")
    _require_plain_int(request.slot_generation, "slot_generation", minimum=1)
    _require_plain_int(request.source_offset, "source_offset")
    destination_offset = _require_plain_int(request.destination_offset, "destination_offset")
    length = _require_plain_int(request.length, "length", minimum=1)
    if length > C0_SLOT_BYTES:
        raise C0ProtocolError(f"c0_length_exceeds_slot:{length}>{C0_SLOT_BYTES}")
    if destination_offset + length > C0_SLOT_BYTES:
        raise C0ProtocolError("c0_destination_exceeds_slot")


def validate_fill_reply(request: C0FillRequest, reply: Any) -> int:
    """Accept exactly one fully-echoed READY reply; return its byte count.

    Anything else (error, short read, stale generation, another request's
    identity) fails closed rather than publishing a READY slot.
    """
    if not isinstance(reply, dict):
        raise C0ProtocolError("c0_reply_not_a_mapping")
    if reply.get("op") != "ready":
        raise C0ProtocolError(f"c0_reply_not_ready:{str(reply.get('op'))[:40]}")
    for field, expected in (
        ("request_id", request.request_id),
        ("arena_epoch", request.arena_epoch),
        ("slot_index", request.slot_index),
        ("slot_generation", request.slot_generation),
        ("source_offset", request.source_offset),
        ("destination_offset", request.destination_offset),
    ):
        actual = reply.get(field)
        if actual != expected:
            raise C0ProtocolError(f"c0_reply_identity_mismatch:{field}:{actual!r}!={expected!r}")
    returned = reply.get("returned_bytes", reply.get("length"))
    if not isinstance(returned, int) or isinstance(returned, bool) or returned != request.length:
        raise C0ProtocolError(f"c0_reply_short:{returned!r}!={request.length}")
    return int(returned)


def c0_source_h2d_overlap_markers(
    *,
    first_source_read_start_mono_ns: Optional[int],
    last_source_read_end_mono_ns: Optional[int],
    first_h2d_submit_mono_ns: Optional[int],
) -> dict:
    """Assemble the passive C0 child-source / parent-H2D overlap markers.

    These four values exist only as evidence.  They are never consumed by a
    branch, gate, retry, or fallback decision; the ordering flag merely records
    whether the child's last validated fill completed at or before the parent's
    first H2D submit.  A missing instant stays ``None`` and yields ``False``
    rather than a fabricated timestamp.
    """
    ordered = bool(
        last_source_read_end_mono_ns is not None
        and first_h2d_submit_mono_ns is not None
        and int(last_source_read_end_mono_ns) <= int(first_h2d_submit_mono_ns)
    )
    return {
        "c0_first_source_read_start_mono_ns": (
            int(first_source_read_start_mono_ns)
            if first_source_read_start_mono_ns is not None else None
        ),
        "c0_last_source_read_end_mono_ns": (
            int(last_source_read_end_mono_ns)
            if last_source_read_end_mono_ns is not None else None
        ),
        "c0_first_h2d_submit_mono_ns": (
            int(first_h2d_submit_mono_ns)
            if first_h2d_submit_mono_ns is not None else None
        ),
        "c0_child_source_end_le_parent_h2d_begin": ordered,
    }


def reconcile_destination_coverage(
    intervals: list[tuple[int, int]], total_bytes: int
) -> dict:
    """Prove destination intervals exactly tile ``[0, total_bytes)``.

    A short read advances the destination cursor by the bytes actually
    returned, so the recorded intervals must still be non-overlapping and
    gapless.  This is the pure reconciliation used by the C0 contract tests.
    """
    total = _require_plain_int(total_bytes, "total_bytes")
    normalized: list[tuple[int, int]] = []
    for start, end in intervals:
        start = _require_plain_int(start, "interval_start")
        end = _require_plain_int(end, "interval_end")
        if end < start:
            raise C0ProtocolError("c0_interval_negative")
        if end > start:
            normalized.append((start, end))
    normalized.sort()
    cursor = 0
    covered = 0
    for start, end in normalized:
        if start < cursor:
            return {
                "ok": False,
                "reason": "overlap",
                "expected_bytes": total,
                "covered_bytes": covered,
                "at": start,
            }
        if start > cursor:
            return {
                "ok": False,
                "reason": "gap",
                "expected_bytes": total,
                "covered_bytes": covered,
                "at": cursor,
            }
        covered += end - start
        cursor = end
    if cursor != total:
        return {
            "ok": False,
            "reason": "short" if cursor < total else "overrun",
            "expected_bytes": total,
            "covered_bytes": covered,
            "at": cursor,
        }
    return {
        "ok": True,
        "reason": "ok",
        "expected_bytes": total,
        "covered_bytes": covered,
        "at": cursor,
    }


def reconcile_source_coverage(
    expected_ranges: Sequence[tuple[int, int]],
    actual_ranges: Sequence[tuple[int, int]],
) -> dict:
    """Compare returned source byte ranges with the safetensors ranges.

    This intentionally does not reduce the proof to a byte total.  A duplicate
    read and a gap can have the same total as a correct read, so each returned
    interval must be inside the expected parent ranges and the sorted returned
    intervals must tile those ranges exactly.
    """
    def _normalize(values: Sequence[tuple[int, int]], label: str) -> list[tuple[int, int]]:
        result = []
        for row in values:
            if not isinstance(row, (tuple, list)) or len(row) != 2:
                raise C0ProtocolError(f"c0_{label}_range_shape")
            start = _require_plain_int(row[0], f"{label}_start")
            end = _require_plain_int(row[1], f"{label}_end")
            if end < start:
                raise C0ProtocolError(f"c0_{label}_range_negative")
            if end > start:
                result.append((start, end))
        return sorted(result)

    expected = _normalize(expected_ranges, "expected")
    actual = _normalize(actual_ranges, "actual")
    expected_bytes = sum(end - start for start, end in expected)
    actual_bytes = sum(end - start for start, end in actual)
    duplicates = 0
    gaps = 0
    out_of_parent = 0
    # The file header precedes the first data range; it is not a gap.
    cursor = expected[0][0] if expected else 0
    for start, end in actual:
        parent = next((item for item in expected if item[0] <= start and end <= item[1]), None)
        if parent is None:
            out_of_parent += 1
        if start < cursor:
            duplicates += 1
        elif start > cursor:
            gaps += 1
        cursor = max(cursor, end)
    def _merged(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        merged: list[tuple[int, int]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged
    # Split reads are legitimate: several contiguous actual intervals may tile
    # one expected parent range. Exactness is union coverage, not read count.
    exact = (
        not out_of_parent
        and duplicates == 0
        and gaps == 0
        and _merged(actual) == _merged(expected)
        and bool(expected)
    )
    if expected:
        # Detect gaps between expected safetensors data ranges as well as at the
        # edges; actual reads may not bridge an absent parent range.
        expected_cursor = expected[0][0]
        for start, end in expected:
            if start > expected_cursor:
                gaps += 1
            expected_cursor = max(expected_cursor, end)
    return {
        "ok": bool(exact),
        "reason": "ok" if exact else (
            "out_of_parent" if out_of_parent else
            "duplicate" if duplicates else "gap" if gaps else "range_mismatch"
        ),
        "expected_ranges": [[start, end] for start, end in expected],
        "actual_ranges": [[start, end] for start, end in actual],
        "expected_bytes": expected_bytes,
        "returned_bytes": actual_bytes,
        "duplicate_count": duplicates,
        "gap_count": gaps,
        "out_of_parent_count": out_of_parent,
    }


def source_touch_copy_throughput(
    records: Sequence[Mapping[str, Any]],
) -> dict:
    """Compute explicitly labelled busy and union-window source-touch rates."""
    intervals: list[tuple[int, int]] = []
    bytes_total = 0
    durations = []
    pipe_excess: list[int] = []
    invalid: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            invalid.append(f"record_{index}:not_mapping")
            continue
        start = record.get("copy_start_ns")
        end = record.get("copy_end_ns")
        returned = record.get("returned_bytes")
        op_ns = record.get("mmap_op_ns", record.get("read_duration_ns"))
        pipe_ns = record.get("mmap_pipe_rtt_ns")
        if not all(_is_plain_int(value) for value in (start, end, returned, op_ns)):
            invalid.append(f"record_{index}:missing_boundary")
            continue
        if start < 0 or end < start or op_ns < 0 or returned <= 0:
            invalid.append(f"record_{index}:non_monotonic")
            continue
        if pipe_ns is not None:
            if not _is_plain_int(pipe_ns) or pipe_ns < op_ns:
                invalid.append(f"record_{index}:negative_pipe_excess")
            else:
                pipe_excess.append(pipe_ns - op_ns)
        intervals.append((start, end))
        durations.append(end - start)
        bytes_total += returned
    union_ns = 0
    previous_end = None
    for start, end in sorted(intervals):
        if previous_end is None:
            union_ns += end - start
        elif start >= previous_end:
            union_ns += end - start
        elif end > previous_end:
            union_ns += end - previous_end
        previous_end = max(previous_end or end, end)
    busy_ns = sum(durations)
    gib = float(2 ** 30)
    return {
        "valid": not invalid,
        "returned_bytes": bytes_total,
        "source_touch_copy_busy_ns": busy_ns,
        "source_touch_copy_union_window_ns": union_ns,
        "source_touch_copy_busy_gib_s": (
            bytes_total / busy_ns * 1e9 / gib if busy_ns else None
        ),
        "source_touch_copy_union_window_gib_s": (
            bytes_total / union_ns * 1e9 / gib if union_ns else None
        ),
        "pipe_excess_ns": pipe_excess,
        "invalid_records": invalid,
        "label": "source-touch-copy end-to-end rate; not raw disk, page-in-only, or source-only speed",
    }


class C0ReplyRegistry:
    """Classify child replies as exactly-once by request identity.

    The reader thread owns this registry.  Unknown ids, duplicates, and replies
    after a fail-closed runtime error all raise ``C0ProtocolError``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[int, dict] = {}

    @property
    def outstanding(self) -> int:
        with self._lock:
            return len(self._pending)

    def register(self, request_id: int) -> dict:
        waiter: dict = {"event": threading.Event(), "reply": None, "error": None}
        with self._lock:
            self._pending[request_id] = waiter
        return waiter

    def resolve(self, reply: dict) -> None:
        if not isinstance(reply, dict):
            raise C0ProtocolError("c0_reply_not_a_mapping")
        request_id = reply.get("request_id")
        if not isinstance(request_id, int) or isinstance(request_id, bool):
            raise C0ProtocolError(f"c0_reply_missing_request_id:{request_id!r}")
        with self._lock:
            waiter = self._pending.pop(request_id, None)
        if waiter is None:
            raise C0ProtocolError(f"c0_unknown_or_duplicate_reply:{request_id}")
        # Retain the full reply even on the error path: a child error reply
        # still carries its own descriptor deltas (including close-on-error),
        # and the parent aggregates them before failing the fill closed.
        waiter["reply"] = reply
        if reply.get("op") not in ("ready", "pong"):
            waiter["error"] = str(reply.get("error") or reply.get("op") or "c0_child_error")
        waiter["event"].set()

    def discard(self, request_id: int) -> None:
        """Drop a waiter that timed out; a late reply then fails as unknown."""
        with self._lock:
            self._pending.pop(request_id, None)

    def fail_all(self, message: str) -> list[int]:
        with self._lock:
            waiters = list(self._pending.items())
            self._pending.clear()
        for request_id, waiter in waiters:
            waiter["error"] = message
            waiter["event"].set()
        return [request_id for request_id, _ in waiters]


class C0LiveSampler:
    """Passive parent-side sampler for one outstanding C0 child fill.

    Owned by :class:`SharedArenaRing`, runs on its own dedicated thread (never
    the fill executor, never inside the child ``_pread_into_probed``).  It polls
    only while a fill is outstanding, samples only calls already older than the
    slow threshold, caps retained records, and counts dropped/missed samples.
    Every record preserves per-field availability/error; a missing procfs or
    cgroup value stays ``None`` rather than a fabricated zero.  Evidence only:
    nothing here branches, gates, retries, or changes the read path.
    """

    def __init__(
        self,
        ring: "SharedArenaRing",
        *,
        enabled: Optional[bool] = None,
        poll_s: float = _C0_LIVE_SAMPLER_POLL_S,
        threshold_ns: int = _C0_LIVE_SAMPLER_THRESHOLD_NS,
        cap: int = _C0_LIVE_SAMPLER_CAP,
    ) -> None:
        self._ring = ring
        self.enabled = c0_live_sampler_enabled() if enabled is None else bool(enabled)
        self.poll_s = max(0.005, float(poll_s))
        self.threshold_ns = max(0, int(threshold_ns))
        self.cap = max(1, int(cap))
        self._records: list[dict] = []
        self._dropped = 0
        self._missed = 0
        self._sample_count = 0
        self._errors: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started_mono_ns: Optional[int] = None
        self._cgroup_base: Optional[str] = None
        self._cgroup_resolved = False

    # ── lifecycle ─────────────────────────────────────────────────────────
    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._started_mono_ns = time.monotonic_ns()
        self._thread = threading.Thread(
            target=self._loop, name="c0-live-sampler", daemon=True
        )
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(2.0, self.poll_s * 4.0))
        return self.snapshot()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except BaseException as exc:  # noqa: BLE001 - diagnostics never raise
                self._note_error(f"{type(exc).__name__}:{exc}")
            self._stop.wait(self.poll_s)

    def _note_error(self, message: str) -> None:
        with self._lock:
            self._errors.append(str(message)[:200])
            del self._errors[:-8]

    # ── sampling ──────────────────────────────────────────────────────────
    def _poll_once(self) -> None:
        if not self.enabled:
            return
        # Cheap gate: never touch the ring lock or procfs when no fill is out.
        if not self._ring.has_outstanding_fills():
            return
        now = time.monotonic_ns()
        try:
            inflight = self._ring.inflight_requests()
        except Exception as exc:  # noqa: BLE001
            self._note_error(f"inflight:{type(exc).__name__}")
            return
        active = [
            request for request in inflight
            if now - int(request.get("started_mono_ns") or now) >= self.threshold_ns
        ]
        if not active:
            return
        snapshot = self._sample_child_snapshot()
        if not snapshot.get("available"):
            with self._lock:
                self._missed += 1
        for request in active:
            self._append_record(self._build_record(request, snapshot, now))

    def _append_record(self, record: dict) -> None:
        with self._lock:
            self._sample_count += 1
            if len(self._records) < self.cap:
                self._records.append(record)
            else:
                self._dropped += 1

    def _build_record(self, request: dict, snapshot: dict, now: int) -> dict:
        started = int(request.get("started_mono_ns") or now)
        return {
            "origin": "parent",
            "sampled_mono_ns": int(now),
            "wall_ns": int(time.time() * 1_000_000_000),
            "elapsed_ms": round((now - started) / 1e6, 3),
            "request_id": request.get("request_id"),
            "role": request.get("role"),
            "slot_index": request.get("slot_index"),
            "producer_id": request.get("producer_id"),
            "record_id": request.get("record_id"),
            "fill_index": request.get("fill_index"),
            "source": request.get("source"),
            "child_pid": snapshot.get("pid"),
            # Correlated from the reply's diagnostic state once it arrives; the
            # live sample cannot know the child worker TID/preadv start yet.
            "worker_native_tid": None,
            "preadv_start_ns": None,
            "snapshot_available": bool(snapshot.get("available")),
            "snapshot_error": snapshot.get("error"),
            "snapshot_origin": snapshot.get("origin"),
            "worker_tid_source": snapshot.get("worker_tid_source"),
            "sampled_threads": snapshot.get("threads"),
            "child_status": snapshot.get("status"),
            "proc_io": snapshot.get("proc_io"),
            "cgroup": snapshot.get("cgroup"),
            "psi": snapshot.get("psi"),
        }

    def _sample_child_snapshot(self) -> dict:
        pid = getattr(self._ring, "child_pid", None)
        out: dict = {
            "origin": "parent",
            "available": False,
            "pid": pid,
            "error": None,
            "worker_tid_source": None,
            "status": None,
            "proc_io": None,
            "cgroup": None,
            "psi": None,
            "threads": None,
        }
        if not pid:
            out["error"] = "child_pid_unavailable"
            return out
        if os.name != "posix":
            out["error"] = "procfs_unsupported"
            return out
        status = _read_proc_status_subset(int(pid))
        out["status"] = status
        if not status.get("available"):
            out["error"] = status.get("error") or "status_unavailable"
            return out
        out["available"] = True
        out["proc_io"] = _read_proc_io(int(pid))
        out["cgroup"] = _read_cgroup_raw(self._resolve_cgroup_base())
        out["psi"] = _read_pressure_snapshot()
        tids, tid_source = self._worker_tids()
        out["worker_tid_source"] = tid_source
        out["threads"] = [self._sample_thread(int(pid), tid) for tid in tids]
        return out

    def _worker_tids(self) -> tuple[list[int], str]:
        """Worker native TIDs from launch-time readiness; main thread fallback."""
        tids: list[int] = []
        ready = getattr(self._ring, "child_ready_evidence", None) or {}
        for info in ready.get("worker_threads") or []:
            if not isinstance(info, dict):
                continue
            native_id = info.get("native_id")
            if isinstance(native_id, int) and not isinstance(native_id, bool):
                tids.append(int(native_id))
        if tids:
            return tids, "worker_ready_evidence"
        pid = getattr(self._ring, "child_pid", None)
        return ([int(pid)] if pid else []), "main_thread_fallback"

    def _sample_thread(self, pid: int, tid: int) -> dict:
        base = f"/proc/{pid}/task/{tid}"
        stack = _read_runtime_text(f"{base}/stack", 512)
        return {
            "tid": int(tid),
            "stat": _read_proc_task_stat(pid, tid),
            "status": _read_proc_status_subset(pid, tid),
            "wchan": _read_runtime_text(f"{base}/wchan", 256),
            "syscall": _read_runtime_text(f"{base}/syscall", 256),
            "schedstat": _read_runtime_text(f"{base}/schedstat", 256),
            "io": _read_proc_io(pid, tid),
            "stack": (stack or "")[:512] if stack is not None else None,
        }

    def _resolve_cgroup_base(self) -> Optional[str]:
        if not self._cgroup_resolved:
            self._cgroup_base = _runtime_cgroup_base()
            self._cgroup_resolved = True
        return self._cgroup_base

    def enrich_from_reply(self, request_id: int, reply: Any) -> None:
        """Attach the reply's worker TID / preadv start to a matching live record."""
        source = dict(reply) if isinstance(reply, dict) else {}
        diagnostics = source.get("preadv_diagnostics")
        if not isinstance(diagnostics, list):
            return
        worker_tid = None
        preadv_start = None
        for record in diagnostics:
            if not isinstance(record, dict):
                continue
            if worker_tid is None and _is_plain_int(record.get("worker_native_tid")):
                worker_tid = int(record["worker_native_tid"])
            if preadv_start is None and _is_plain_int(record.get("preadv_start_ns")):
                preadv_start = int(record["preadv_start_ns"])
            if worker_tid is not None and preadv_start is not None:
                break
        if worker_tid is None and preadv_start is None:
            return
        with self._lock:
            for record in self._records:
                if record.get("request_id") != request_id:
                    continue
                if record.get("worker_native_tid") is None:
                    record["worker_native_tid"] = worker_tid
                if record.get("preadv_start_ns") is None:
                    record["preadv_start_ns"] = preadv_start

    # ── evidence ──────────────────────────────────────────────────────────
    def snapshot(self, *, child_fallback_count: int = 0) -> dict:
        with self._lock:
            records = [dict(record) for record in self._records]
            errors = list(self._errors)
            record_count = len(records)
            dropped = self._dropped
            missed = self._missed
            sample_count = self._sample_count
        return {
            "enabled": bool(self.enabled),
            "origin": "parent",
            "threshold_ms": round(self.threshold_ns / 1e6, 3),
            "poll_interval_ms": round(self.poll_s * 1000.0, 3),
            "cap": self.cap,
            "sample_count": int(sample_count),
            "record_count": int(record_count),
            "dropped": int(dropped),
            "missed": int(missed),
            "origins": {
                "parent": int(record_count),
                "child-fallback": int(child_fallback_count),
            },
            "errors": errors,
            "records": records,
        }

    def role_telemetry(self, role: str, diagnostics: Any) -> dict:
        """Per-role sampler evidence plus that role's child fallback count."""
        with self._lock:
            records = [
                dict(record)
                for record in self._records
                if str(record.get("role")) == str(role)
            ]
            base = {
                "enabled": bool(self.enabled),
                "threshold_ms": round(self.threshold_ns / 1e6, 3),
                "poll_interval_ms": round(self.poll_s * 1000.0, 3),
                "cap": self.cap,
                "sample_count": int(self._sample_count),
                "dropped": int(self._dropped),
                "missed": int(self._missed),
            }
        base["record_count"] = len(records)
        base["records"] = records
        base["origins"] = {
            "parent": len(records),
            "child-fallback": _child_fallback_records(diagnostics),
        }
        return base


# Diagnostic-only bound for the rejected child startup reply.  The parent
# raises ``c0_child_ready_failed:<reply>``; a truncated ``repr`` drops the
# trailing ``volume_v1.setup_error`` that the Volume V1 treatment needs in
# attempt artifacts.  Compact JSON under this generous bound keeps the
# structured failure context.  Never branched on.
_C0_CHILD_READY_FAILURE_LIMIT = 4000


def _format_child_ready_failure(ready: Any) -> str:
    """Serialize a rejected child startup reply as bounded compact JSON.

    When the child failed during Volume V1 transport setup, the real cause lives
    in the nested ``volume_v1.setup_error`` which the outer 240-char attempt
    error bound would otherwise truncate away.  Emit it as a leading marker so
    the cause survives that bound; all other failure shapes are unchanged.
    """
    try:
        text = json.dumps(ready, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(ready)
    prefix = ""
    if isinstance(ready, dict) and ready.get("op") == "startup_failed":
        volume_v1 = ready.get("volume_v1")
        if isinstance(volume_v1, dict):
            setup_error = volume_v1.get("setup_error")
            if isinstance(setup_error, str) and setup_error:
                prefix = f"c0_volume_transport_setup_failed:{setup_error}|"
    return (prefix + text)[:_C0_CHILD_READY_FAILURE_LIMIT]


class SharedArenaRing:
    """Parent-owned 512 MiB POSIX arena + persistent CUDA-sterile filler child.

    The mapping is created once, registered once by the CUDA-owning parent, and
    reused for every C0 model stage.  No model-sized backing exists: the four
    128 MiB slots are the only payload storage.
    """

    def __init__(
        self,
        *,
        size_bytes: int = C0_ARENA_BYTES,
        slot_count: int = C0_SLOT_COUNT,
        slot_bytes: int = C0_SLOT_BYTES,
        device_index: int = 0,
    ) -> None:
        if int(size_bytes) != int(slot_count) * int(slot_bytes):
            raise ValueError("c0_arena_geometry_mismatch")
        self.size_bytes = int(size_bytes)
        self.slot_count = int(slot_count)
        self.slot_bytes = int(slot_bytes)
        self.device_index = int(device_index)
        self.created = False
        self.registered = False
        self.epoch = 0
        self.backing_create_ms: Optional[float] = None
        self.backing_create_start_ns: Optional[int] = None
        self.backing_create_end_ns: Optional[int] = None
        self.register_ms: Optional[float] = None
        self.register_start_ns: Optional[int] = None
        self.register_end_ns: Optional[int] = None
        self.unregister_ms: Optional[float] = None
        self.child_pid: Optional[int] = None
        self.child_start_ns: Optional[int] = None
        self.child_ready_ns: Optional[int] = None
        self.child_torch_imported: Optional[bool] = None
        self.child_cuda_initialized = False
        # Launch-time source-worker readiness proof.  Retained from the child's
        # ready_child report so evidence/teardown can show both configured
        # workers were actually started and barrier-ready before any fill.
        self.child_ready_evidence: Optional[dict] = None
        # Forensic child-only VizTracer selector + launch-time ready status.
        # OFF leaves the child exactly uninstrumented; ON never changes geometry,
        # the FD lifecycle, or IPC semantics.
        self.child_viztracer_enabled = child_viztracer_enabled()
        self.child_viztracer_path: Optional[str] = None
        self.child_viztracer: Optional[dict] = None
        self._shm = None
        self._tensor = None
        self._arena_address: Optional[int] = None
        self._slot_tensors: tuple[Any, ...] = ()
        self._proc = None
        self._stdin = None
        self._stdout = None
        self._closing = threading.Event()
        self._dead: Optional[str] = None
        self._registry = C0ReplyRegistry()
        self._requests: list[dict] = []
        self._req_cond = threading.Condition()
        self._next_request_id = 0
        self._inflight = 0
        self._writer_thread: Optional[threading.Thread] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._close_lock = threading.RLock()
        self._closed = False
        self._already_unlinked = False
        self.cleanup_status: dict[str, Any] = {}
        self.cleanup_unresolved = False
        self.events: dict[str, dict] = {}
        # Passive evidence counters.
        self.fills_submitted = 0
        self.fills_ready = 0
        self.fills_failed = 0
        self.short_read_failures = 0
        self.max_concurrent_fills = 0
        self.concurrent_fill_events = 0
        self.backpressure_block_count = 0
        self.backpressure_block_ns = 0
        self.physical_read_bytes = 0
        self.physical_read_syscalls = 0
        self.slot_fills = [0] * self.slot_count
        self.slot_reuses = 0
        self._registered_fill_total = 0
        # Launch-time treatment snapshot.  The child reads the same selector
        # once at spawn; the parent must report the value it launched with, not
        # whatever the environment says at evidence time.
        self.persistent_fds = io_process_v2_persistent_fds_enabled()
        # Deploy-baked cudaHostRegister selector for the C0 POSIX-SHM arena.
        # Read once here (before the mapping exists) and mirrored into evidence
        # so the arm is provable from the arena record, not the live env.
        self.host_register_enabled = c0_host_register_enabled()
        # Diagnostic-only private source/destination split snapshot.  The child
        # reads the same selector once at spawn; the parent reports what it
        # launched with.  OFF is the exact direct file -> leased SHM path.
        self.private_split_io = c0_private_split_io_enabled()
        # Distinct C0 direct Volume V1 treatment snapshot.  The child reads the
        # same selector once at spawn; the parent resolves the same-name V1
        # Volume object id under the container's existing Modal auth and passes
        # it at launch.  ON has no preadv fallback.
        self.source_volume_v1 = c0_source_volume_v1_enabled()
        self.source_volume_metadata: Optional[dict] = None
        self.child_volume_evidence: Optional[dict] = None
        # Parent platform/runtime markers for split-IO evidence; the child
        # reports its own in ready_child.  Evidence only, never branched on.
        self.runtime_markers: dict = platform_runtime_markers()
        self.child_runtime_markers: Optional[dict] = None
        # Diagnostic clustered preadv-sickness snapshot.  The child reads the
        # selector once at spawn; the parent reports the pre-registered control
        # manifest and the launch-time hashes without reading model bytes.
        self.preadv_sickness_diag = c0_preadv_sickness_diag_enabled()
        self.preadv_sickness_manifest: Optional[dict] = (
            load_c0_preadv_controls() if self.preadv_sickness_diag else None
        )
        self.preadv_sickness_hashes: Optional[dict] = (
            c0_preadv_sickness_config_hashes() if self.preadv_sickness_diag else None
        )
        self.preadv_sickness_invocation_id: Optional[str] = None
        self.child_preadv_sickness: Optional[dict] = None
        self.child_preadv_sickness_terminal: Optional[dict] = None
        # Passive C0 child descriptor-lifecycle telemetry.  Aggregated from the
        # per-fill child evidence; keyed by the full (path, producer) identity.
        self.fd_open_count = 0
        self.fd_reuse_count = 0
        self.fd_close_count = 0
        self.fd_open_wall_ms = 0.0
        self.fd_close_wall_ms = 0.0
        self.total_fill_wall_ns = 0
        self._fd_keys: set[tuple[str, int]] = set()
        self.child_fd_telemetry: Optional[dict] = None
        # Retained per-role stage readers.  The reader is the authoritative
        # per-(path, producer) descriptor evidence source; the ring holds it so
        # arena evidence can surface each role's telemetry at teardown without
        # any golden_serial.py participation.
        self._stage_readers: dict[str, Any] = {}
        # Passive C0 source/H2D overlap stamps: earliest fill-submit and latest
        # fill-ready monotonic instants per role.  Stored only; never branched on.
        self.fill_submit_mono_ns: dict[str, int] = {}
        self.fill_ready_mono_ns: dict[str, int] = {}
        # Passive parent lease-inflight occupancy.  Sampled at every inflight
        # transition from the ring's own outstanding-fill counter -- the real
        # parent lease state, never a synthetic geometry claim.  Bucket i counts
        # how often i fills were simultaneously outstanding; index is clamped to
        # QD4 while ``max_source_inflight`` keeps the true peak.
        self.max_source_inflight = 0
        self.source_inflight_samples = 0
        self.source_inflight_occupancy = [0] * (_C0_QD_DISTRIBUTION_MAX + 1)
        # ── bounded passive preadv diagnostics (evidence only) ─────────────
        # In-flight request correlation for the parent live sampler.  Keyed by
        # request id and maintained under ``_req_cond`` by ``fill`` only; the
        # sampler reads it, never mutates it.
        self._inflight_requests: dict[int, dict] = {}
        self._live_sampler: Optional[C0LiveSampler] = None
        # One-time mount identity: captured once per unique source path and once
        # for /dev/shm, before that path's first fill.  No per-read probing.
        self._mount_identity: Optional[dict] = None
        self._mount_identity_paths: set[str] = set()
        # One-time source page-cache residency keyed by unique model path.
        self._source_cache: dict[str, dict] = {}
        # Passive SHM residency: baseline right after allocation, then exactly
        # once per slot after its first validated fill.  Never per later fill.
        self._shm_residency_baseline: Optional[list] = None
        self._slot_residency_after: dict[int, dict] = {}
        # One-time runtime/cgroup/PSI identity snapshot.
        self._runtime_identity: Optional[dict] = None

    def _record_source_inflight(self, inflight: int) -> None:
        """Count one observed parent lease-inflight level (QD0..QD4)."""
        value = max(0, int(inflight))
        if value > self.max_source_inflight:
            self.max_source_inflight = value
        self.source_inflight_samples += 1
        self.source_inflight_occupancy[min(value, _C0_QD_DISTRIBUTION_MAX)] += 1

    # ── lifecycle ─────────────────────────────────────────────────────────
    def ensure(self) -> "SharedArenaRing":
        if self.created:
            return self
        # Distinct C0 direct Volume V1 treatment: resolve the same-name V1
        # Volume identity once, before the mapping exists, so a failed
        # resolution fails the launch closed without leaking a segment.
        if self.source_volume_v1:
            self.source_volume_metadata = dict(resolve_c0_source_volume_metadata())
        torch = _require_torch()
        cudart = torch.cuda.cudart()
        register = getattr(cudart, "cudaHostRegister", None)
        if self.host_register_enabled and not callable(register):
            raise RuntimeError("cudaHostRegister_unavailable")
        self.backing_create_start_ns = time.monotonic_ns()
        t0 = time.perf_counter()
        self._shm = shared_memory.SharedMemory(create=True, size=self.size_bytes)
        self.backing_create_end_ns = time.monotonic_ns()
        self.backing_create_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        self._tensor = torch.frombuffer(self._shm.buf, dtype=torch.uint8)
        self._arena_address = _shm_address(self._shm)
        self._slot_tensors = tuple(
            self._tensor[index * self.slot_bytes : (index + 1) * self.slot_bytes]
            for index in range(self.slot_count)
        )
        # cudaHostRegister the SAME POSIX-SHM mapping the child writes, unless
        # the deploy-baked selector turned registration OFF.  OFF leaves the
        # mapping, slots, geometry, source engine, and H2D dispatcher byte
        # identical; only the registration is skipped.
        if self.host_register_enabled:
            self.register_start_ns = time.monotonic_ns()
            t0 = time.perf_counter()
            rc = int(register(self._arena_address, self.size_bytes, _CUDA_HOST_REGISTER_DEFAULT))
            self.register_end_ns = time.monotonic_ns()
            self.register_ms = round((time.perf_counter() - t0) * 1000.0, 4)
            if rc != 0:
                self._release_mapping_after_failed_setup()
                raise RuntimeError(f"cudaHostRegister_failed:{rc}:{_cudart_error_str(cudart, rc)}")
            self.registered = True
        child_env = os.environ.copy()
        child_env["CUDA_VISIBLE_DEVICES"] = ""
        # The CUDA-sterile child loads the stdlib transport module by explicit
        # path; never via a package import that could pull torch.
        child_env[C0_RUNTIME_DIR_ENV] = os.path.dirname(os.path.abspath(__file__))
        # Distinct C0 direct Volume V1: hand the child the resolved same-name V1
        # Volume identity.  The object id is parent-resolved evidence, never a
        # hardcoded authority, and the child re-uses it verbatim.
        if self.source_volume_v1 and isinstance(self.source_volume_metadata, dict):
            child_env[C0_SOURCE_VOLUME_ID_ENV] = str(
                self.source_volume_metadata.get("volume_id") or ""
            )
            child_env[C0_SOURCE_VOLUME_NAME_ENV] = str(
                self.source_volume_metadata.get("volume_name") or ""
            )
            child_env[C0_SOURCE_VOLUME_MOUNT_ENV] = str(
                self.source_volume_metadata.get("mount") or c0_source_volume_mount()
            )
        # Hand the child the one deterministic forensic trace path.  This is a
        # parent-only spawn input; the deploy flag decides whether it is used.
        if self.child_viztracer_enabled:
            self.child_viztracer_path = child_viztracer_output_path()
            child_env["COMFYMODAL_C0_CHILD_VIZTRACER_PATH"] = self.child_viztracer_path
        # Diagnostic clustered preadv-sickness: hand the child the pre-registered
        # control manifest plus launch-time hashes and a per-invocation id.  The
        # manifest holds offsets only; no model bytes are read or changed.
        if self.preadv_sickness_diag:
            if self.preadv_sickness_invocation_id is None:
                self.preadv_sickness_invocation_id = c0_preadv_sickness_invocation_id()
            hashes = self.preadv_sickness_hashes or {}
            child_env[IO_PROCESS_V2_C0_PREADV_SICKNESS_DIAG_ENV] = "1"
            child_env[C0_PREADV_SICKNESS_CONTROLS_ENV] = json.dumps(
                self.preadv_sickness_manifest or {}, separators=(",", ":"), default=str
            )
            child_env[C0_PREADV_SICKNESS_PROFILE_HASH_ENV] = str(
                hashes.get("profile_hash") or ""
            )
            child_env[C0_PREADV_SICKNESS_CONFIG_HASH_ENV] = str(
                hashes.get("config_hash") or ""
            )
            child_env[C0_PREADV_SICKNESS_INVOCATION_ID_ENV] = str(
                self.preadv_sickness_invocation_id or ""
            )
        self.child_start_ns = time.monotonic_ns()
        self._proc = subprocess.Popen(
            [
                sys.executable, "-c", _C0_CHILD_SOURCE,
                str(self._shm.name), str(self.size_bytes),
                str(self.slot_count), str(self.slot_bytes), str(C0_SOURCE_WORKERS),
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=child_env,
        )
        self._stdin = self._proc.stdin
        self._stdout = self._proc.stdout
        ready = self._read_child_ready(timeout_s=180.0)
        self.child_ready_ns = time.monotonic_ns()
        if not isinstance(ready, dict) or ready.get("op") != "ready_child":
            self._cleanup_failed_setup()
            raise RuntimeError(
                f"c0_child_ready_failed:{_format_child_ready_failure(ready)}"
            )
        self.child_pid = int(ready.get("pid") or 0) or None
        self.child_torch_imported = bool(ready.get("torch_imported"))
        self.child_cuda_initialized = bool(ready.get("cuda_initialized"))
        _ready_child_viztracer = ready.get("child_viztracer")
        self.child_viztracer = (
            dict(_ready_child_viztracer)
            if isinstance(_ready_child_viztracer, dict)
            else None
        )
        # Child-side platform/runtime markers reported in ready_child.  Evidence
        # only; a missing/None block never fails the launch.
        _ready_runtime_markers = ready.get("runtime_markers")
        self.child_runtime_markers = (
            dict(_ready_runtime_markers)
            if isinstance(_ready_runtime_markers, dict)
            else None
        )
        # Distinct C0 direct Volume V1 child launch evidence (transport/session
        # provenance reported by the child).  Evidence only; the ready_child
        # contract above already fails the launch closed on setup failure.
        _ready_volume = ready.get("volume_v1")
        self.child_volume_evidence = (
            dict(_ready_volume) if isinstance(_ready_volume, dict) else None
        )
        # Diagnostic clustered preadv-sickness child launch evidence.  Evidence
        # only; a missing/disabled block never fails the launch.
        _ready_sickness = ready.get("preadv_sickness_diag")
        self.child_preadv_sickness = (
            dict(_ready_sickness) if isinstance(_ready_sickness, dict) else None
        )
        # The child was handed the exact pre-registered control manifest.  If it
        # could not load it, record the discrepancy instead of assuming parity.
        if self.preadv_sickness_diag and isinstance(self.child_preadv_sickness, dict):
            self.child_preadv_sickness["parent_manifest_roles"] = sorted(
                (self.preadv_sickness_manifest or {}).get("files", {}).keys()
                if isinstance(self.preadv_sickness_manifest, dict)
                else []
            )
        if self.child_torch_imported:
            self._cleanup_failed_setup()
            raise RuntimeError("c0_child_not_cuda_sterile")
        if self.child_cuda_initialized:
            self._cleanup_failed_setup()
            raise RuntimeError("c0_child_cuda_initialized")
        # Source-worker readiness proof.  The child emits ready_child only after
        # every configured source worker has started and reached the startup
        # barrier, so the parent verifies that proof before accepting any fill.
        # A short/absent proof fails closed: a lazily-started worker pool would
        # otherwise let the second fill block behind the first worker's preadv.
        _ready_workers = ready.get("workers_configured")
        _ready_worker_count = ready.get("workers_ready")
        _startup_barrier = ready.get("startup_barrier")
        try:
            _ready_workers_int = int(_ready_workers)
            _ready_worker_count_int = int(_ready_worker_count)
        except (TypeError, ValueError):
            self._cleanup_failed_setup()
            raise RuntimeError(
                f"c0_child_worker_readiness_missing:{_ready_workers!r}:{_ready_worker_count!r}"
            )
        _barrier_threads = (
            _startup_barrier.get("threads") if isinstance(_startup_barrier, dict) else None
        )
        self.child_ready_evidence = {
            "workers_configured": _ready_workers_int,
            "workers_ready": _ready_worker_count_int,
            "startup_wall_ms": ready.get("startup_wall_ms"),
            "startup_barrier": (
                dict(_startup_barrier) if isinstance(_startup_barrier, dict) else None
            ),
            "worker_threads": (
                list(_barrier_threads) if isinstance(_barrier_threads, list) else None
            ),
            # Diagnostic split evidence: the child allocated one private staging
            # buffer per worker before the barrier, and its own runtime markers.
            "private_split_io": bool(ready.get("private_split_io")),
            "source_engine": ready.get("source_engine"),
            "mmap_source": (
                dict(ready.get("mmap_source"))
                if isinstance(ready.get("mmap_source"), dict)
                else None
            ),
            "private_buffer_bytes_per_worker": ready.get("private_buffer_bytes_per_worker"),
            "runtime_markers": (
                dict(_ready_runtime_markers)
                if isinstance(_ready_runtime_markers, dict)
                else None
            ),
            # One-time child-side mount identity reported in ready_child.
            "mount_identity": (
                dict(ready.get("mount_identity"))
                if isinstance(ready.get("mount_identity"), dict)
                else None
            ),
        }
        if (
            _ready_workers_int != C0_SOURCE_WORKERS
            or _ready_worker_count_int != _ready_workers_int
        ):
            self._cleanup_failed_setup()
            raise RuntimeError(
                "c0_child_worker_readiness_failed:"
                f"configured={_ready_workers_int}:ready={_ready_worker_count_int}:"
                f"expected={C0_SOURCE_WORKERS}"
            )
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="c0-ipc-writer", daemon=True
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="c0-ipc-reader", daemon=True
        )
        self._writer_thread.start()
        self._reader_thread.start()
        self.epoch += 1
        self.created = True
        # ── one-time passive diagnostics (never gates the launch) ──────────
        # SHM residency baseline right after allocation; runtime/cgroup/PSI
        # identity and /dev/shm mount identity captured once; then the parent
        # live sampler is started on its own thread.  Any diagnostic failure is
        # absorbed here so it can never fail the arena launch.
        try:
            self._shm_residency_baseline = self._sample_slot_residency()
            self._runtime_identity = collect_runtime_identity()
            self._capture_mount_identity(["/dev/shm"])
            self._live_sampler = C0LiveSampler(self)
            self._live_sampler.start()
        except BaseException as exc:  # noqa: BLE001 - diagnostics are passive
            self.runtime_markers = dict(self.runtime_markers or {})
            self.runtime_markers["diagnostics_setup_error"] = (
                f"{type(exc).__name__}:{exc}"[:160]
            )
        print(
            "[v2.golden_io_process_v2.c0] "
            f"event=arena_ready bytes={self.size_bytes} slots={self.slot_count} "
            f"slot_bytes={self.slot_bytes} epoch={self.epoch} "
            f"host_register_enabled={int(bool(self.host_register_enabled))} "
            f"registered={int(bool(self.registered))} "
            f"register_ms={self.register_ms} child_pid={self.child_pid} "
            f"child_torch_imported={self.child_torch_imported} "
            f"workers_configured={(_ready_workers_int)} "
            f"workers_ready={(_ready_worker_count_int)} "
            f"worker_startup_ms={ready.get('startup_wall_ms')}",
            flush=True,
        )
        return self

    def _release_mapping_after_failed_setup(self) -> dict:
        out: dict[str, Any] = {}
        if self._shm is not None:
            try:
                self._shm.buf.release()
            except Exception:
                pass
            try:
                self._shm.close()
            except Exception as exc:  # noqa: BLE001
                out["close_error"] = f"{type(exc).__name__}: {exc}"[:160]
            try:
                self._shm.unlink()
            except Exception as exc:  # noqa: BLE001
                out["unlink_error"] = f"{type(exc).__name__}: {exc}"[:160]
        self._shm = None
        self._tensor = None
        self._slot_tensors = ()
        self.created = False
        return out

    def _cleanup_failed_setup(self) -> None:
        try:
            if self._proc is not None:
                self._proc.kill()
        except Exception:
            pass
        if self.registered:
            try:
                self._unregister()
            except Exception:
                # Registration failure handling is best-effort; the mapping is
                # still torn down so a failed setup does not leak a segment.
                pass
        self._release_mapping_after_failed_setup()

    def _read_child_ready(self, *, timeout_s: float) -> Any:
        import select

        assert self._stdout is not None
        ready, _, _ = select.select([self._stdout], [], [], float(timeout_s))
        if not ready:
            return None
        line = self._stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except ValueError:
            return None

    # ── IPC owners (one per direction) ────────────────────────────────────
    def _writer_loop(self) -> None:
        while True:
            with self._req_cond:
                while not self._requests and not self._closing.is_set():
                    self._req_cond.wait()
                if not self._requests:
                    return
                message = self._requests.pop(0)
            try:
                assert self._stdin is not None
                self._stdin.write(json.dumps(message) + "\n")
                self._stdin.flush()
            except BaseException as exc:  # noqa: BLE001
                self._fail_runtime(f"c0_ipc_write_failed:{type(exc).__name__}:{exc}"[:200])
                return

    def _reader_loop(self) -> None:
        while not self._closing.is_set():
            stdout = self._stdout
            if stdout is None:
                return
            try:
                line = stdout.readline()
            except BaseException as exc:  # noqa: BLE001
                self._fail_runtime(f"c0_ipc_read_failed:{type(exc).__name__}:{exc}"[:200])
                return
            if not line:
                self._fail_runtime("c0_child_ipc_eof")
                return
            line = line.strip()
            if not line:
                continue
            try:
                reply = json.loads(line)
            except ValueError:
                self._fail_runtime("c0_child_reply_bad_json")
                return
            if isinstance(reply, dict) and reply.get("op") == "fatal":
                self._fail_runtime(f"c0_child_fatal:{str(reply.get('error'))[:200]}")
                return
            try:
                self._registry.resolve(reply)
            except C0ProtocolError as exc:
                self._fail_runtime(str(exc))
                return

    def _fail_runtime(self, message: str) -> None:
        with self._req_cond:
            if self._dead is None:
                self._dead = str(message)[:240]
            self._inflight = 0
            self._req_cond.notify_all()
        self._registry.fail_all(self._dead)

    # ── fill seam ─────────────────────────────────────────────────────────
    def fill(self, request: C0FillRequest, *, timeout_s: float = 900.0) -> dict:
        validate_fill_request(request)
        if self._dead is not None:
            raise C0ProtocolError(f"c0_runtime_dead:{self._dead}")
        if self._closing.is_set():
            raise C0ProtocolError("c0_runtime_closing")
        if self._stdin is None or self._stdout is None:
            raise C0ProtocolError("c0_runtime_not_started")
        # Passive one-time probes run outside the fill lock (file I/O only) and
        # can never fail the fill; a diagnostic error is absorbed, not raised.
        try:
            self._capture_fill_diagnostics(request)
        except BaseException:  # noqa: BLE001
            pass
        waiter = self._registry.register(request.request_id)
        event = waiter["event"]
        enqueued = False
        started = time.monotonic_ns()
        try:
            with self._req_cond:
                while self._inflight >= C0_INFLIGHT_LIMIT and self._dead is None and not self._closing.is_set():
                    self.backpressure_block_count += 1
                    self._req_cond.wait(0.05)
                if self._dead is not None:
                    raise C0ProtocolError(f"c0_runtime_dead:{self._dead}")
                if self._closing.is_set():
                    raise C0ProtocolError("c0_runtime_closing")
                concurrent = self._inflight
                self._inflight += 1
                enqueued = True
                self._record_source_inflight(self._inflight)
                self._registered_fill_total += 1
                if concurrent > 0:
                    self.concurrent_fill_events += 1
                if self._inflight > self.max_concurrent_fills:
                    self.max_concurrent_fills = self._inflight
                # Passive stamp: the instant the parent hands the fill off.
                submit_ns = time.monotonic_ns()
                previous_submit = self.fill_submit_mono_ns.get(request.role)
                if previous_submit is None or submit_ns < previous_submit:
                    self.fill_submit_mono_ns[request.role] = submit_ns
                self._register_inflight(request, started_mono_ns=started)
                self._requests.append(request.as_message())
                self._req_cond.notify_all()
            self.backpressure_block_ns += time.monotonic_ns() - started
            self.fills_submitted += 1
            self.slot_fills[request.slot_index] += 1
            if not event.wait(float(timeout_s)):
                self._registry.discard(request.request_id)
                raise C0ProtocolError(f"c0_fill_timeout:{request.request_id}")
            error = waiter.get("error")
            if error:
                self.fills_failed += 1
                self.short_read_failures += 1
                # Absorb the error reply's descriptor deltas before failing
                # closed so a physical open/close-on-error cannot disappear
                # from aggregate telemetry.
                self._absorb_fd_evidence(request, waiter.get("reply"))
                # Retain any per-read syscall diagnostics the failing reply
                # carried; the filler still fails closed exactly as before.
                self._absorb_preadv_diagnostics(request, waiter.get("reply"))
                raise C0ProtocolError(str(error))
            reply = waiter.get("reply")
            validate_fill_reply(request, reply)
            # Passive stamp: the instant the validated fill became READY.
            ready_ns = time.monotonic_ns()
            previous_ready = self.fill_ready_mono_ns.get(request.role)
            if previous_ready is None or ready_ns > previous_ready:
                self.fill_ready_mono_ns[request.role] = ready_ns
            self.fills_ready += 1
            self.physical_read_bytes += request.length
            self.physical_read_syscalls += int((reply or {}).get("read_syscalls") or 0)
            self._absorb_fd_evidence(request, reply)
            self.total_fill_wall_ns += max(0, time.monotonic_ns() - started)
            # Passive: correlate this fill's live samples with the child's
            # per-read diagnostics and sample this slot's residency exactly once.
            try:
                self._after_fill_ready(request, reply)
            except BaseException:  # noqa: BLE001 - diagnostics are passive
                pass
            return reply
        finally:
            if not enqueued:
                self._registry.discard(request.request_id)
            with self._req_cond:
                self._unregister_inflight(request.request_id)
                if enqueued:
                    self._inflight = max(0, self._inflight - 1)
                    self._record_source_inflight(self._inflight)
                self._req_cond.notify_all()

    # ── stage seams ───────────────────────────────────────────────────────
    def _absorb_fd_evidence(self, request: C0FillRequest, reply: Any) -> None:
        """Fold one child fill reply's descriptor deltas into aggregate evidence.

        The CUDA-sterile child owns the physical descriptor lifecycle; these are
        its own per-fill deltas, keyed here by the full (path, producer)
        identity.  Missing fields default to zero so non-C0 reply shapes cannot
        fabricate descriptor activity.
        """
        source = dict(reply) if isinstance(reply, dict) else {}
        self.fd_open_count += max(0, int(source.get("fd_open_count") or 0))
        self.fd_reuse_count += max(0, int(source.get("fd_reuse_count") or 0))
        self.fd_close_count += max(0, int(source.get("fd_close_count") or 0))
        self.fd_open_wall_ms += max(0.0, float(source.get("fd_open_wall_ms") or 0.0))
        self.fd_close_wall_ms += max(0.0, float(source.get("fd_close_wall_ms") or 0.0))
        # Descriptor identity is normalized exactly as the child key is, so the
        # parent and child reconcile under the same (path, producer_id) key.
        path = source.get("fd_key_path")
        if not path:
            path = os.path.normpath(str(request.source))
        self._fd_keys.add((str(path), int(request.producer_id)))

    def _absorb_preadv_diagnostics(self, request: C0FillRequest, reply: Any) -> None:
        """Hand an error reply's per-read diagnostics to its role's reader.

        The ready path folds them through ``C0StageReader._record_fill_telemetry``;
        a child error/short-read raises inside ``fill`` before the reader sees the
        reply, so retain the list here.  No-op when the role has no stage reader
        (for example a bare ``fill`` unit test); never invents a record.
        """
        reader = self._stage_readers.get(str(request.role))
        if reader is not None:
            reader._absorb_preadv_diagnostics(reply)
            # Distinct C0 direct Volume V1 treatment: retain a failed extent's
            # block diagnostics exactly like the ready path does.
            reader._absorb_volume_telemetry(reply)
            # Diagnostic clustered preadv-sickness block survives a failed fill.
            reader._absorb_sickness_diagnostics(reply)

    def slot_base_address(self, slot_index: int) -> int:
        if not isinstance(slot_index, int) or isinstance(slot_index, bool):
            raise C0ProtocolError("c0_slot_index_not_int")
        if not 0 <= slot_index < self.slot_count:
            raise C0ProtocolError(f"c0_slot_out_of_range:{slot_index}")
        assert self._arena_address is not None
        return int(self._arena_address) + slot_index * self.slot_bytes

    def new_stage_pool(self, capacity_class: str = C0_CAPACITY_CLASS) -> Any:
        from .golden_qd_transport import StagingPool

        if not self._slot_tensors:
            raise C0ProtocolError("c0_arena_not_ready")
        return StagingPool(
            self.slot_count,
            self.slot_bytes,
            capacity_class,
            buffers=self._slot_tensors,
            backing_buffer=self._tensor,
        )

    def stage_reader(self, *, role: str, pool: Any, source: str) -> "C0StageReader":
        reader = C0StageReader(self, role=role, pool=pool, source=source)
        # Retain the reader so its child-reported per-(path, producer)
        # descriptor lifecycle survives into arena teardown evidence.
        self._stage_readers[str(role)] = reader
        return reader

    # ── bounded passive preadv diagnostics ────────────────────────────────
    def has_outstanding_fills(self) -> bool:
        """Cheap gate for the sampler: only poll while a fill is outstanding."""
        return bool(self._inflight_requests) or self._inflight > 0

    def inflight_requests(self) -> list[dict]:
        """Snapshot the parent's outstanding fill correlation, for the sampler."""
        with self._req_cond:
            return [dict(request) for request in self._inflight_requests.values()]

    def _capture_mount_identity(self, paths: Sequence[str]) -> None:
        """Capture one-time mount identity for any not-yet-seen path."""
        new_paths = [path for path in paths if str(path) not in self._mount_identity_paths]
        if not new_paths:
            return
        captured = read_mount_identity(new_paths)
        if self._mount_identity is None:
            self._mount_identity = captured
        else:
            merged = self._mount_identity
            merged["paths"].update(captured.get("paths", {}))
            merged["statfs"].update(captured.get("statfs", {}))
            for entry in captured.get("entries", []):
                if entry not in merged["entries"]:
                    merged["entries"].append(entry)
            merged["fstypes"] = sorted(set(merged.get("fstypes", [])) | set(captured.get("fstypes", [])))
            merged["has_fuse_fstype"] = bool(merged.get("has_fuse_fstype")) or bool(captured.get("has_fuse_fstype"))
            if not merged.get("supported") and captured.get("supported"):
                merged["supported"] = True
                merged["error"] = None
        for path in new_paths:
            self._mount_identity_paths.add(str(path))

    def _capture_source_cache(self, request: C0FillRequest) -> None:
        """One-time source page-cache probe for a path's first fill."""
        path = str(request.source)
        if path in self._source_cache:
            return
        self._source_cache[path] = probe_source_cache(
            path,
            ranges=[(int(request.source_offset), int(request.length))],
        )

    def _sample_slot_residency(self) -> list:
        """Baseline mincore residency for every C0 arena slot (no touching)."""
        samples: list = []
        for slot_index in range(self.slot_count):
            try:
                sample = mincore_residency(
                    self.slot_base_address(slot_index), self.slot_bytes
                )
            except Exception as exc:  # noqa: BLE001
                sample = {
                    "supported": False,
                    "status": "error",
                    "error": f"{type(exc).__name__}:{exc}"[:160],
                }
            sample["slot_index"] = int(slot_index)
            sample["address"] = self._slot_address_or_none(slot_index)
            sample["length"] = int(self.slot_bytes)
            samples.append(sample)
        return samples

    def _slot_address_or_none(self, slot_index: int) -> Optional[int]:
        try:
            return int(self.slot_base_address(slot_index))
        except Exception:  # noqa: BLE001
            return None

    def _record_slot_residency(self, slot_index: int) -> None:
        """Sample a slot's residency exactly once, after its first valid fill."""
        if slot_index in self._slot_residency_after:
            return
        if self._shm is None or self._arena_address is None:
            return
        try:
            sample = mincore_residency(
                self.slot_base_address(slot_index), self.slot_bytes
            )
        except Exception as exc:  # noqa: BLE001
            sample = {
                "supported": False,
                "status": "error",
                "error": f"{type(exc).__name__}:{exc}"[:160],
            }
        sample["slot_index"] = int(slot_index)
        sample["address"] = self._slot_address_or_none(slot_index)
        sample["length"] = int(self.slot_bytes)
        self._slot_residency_after[int(slot_index)] = sample

    def _capture_fill_diagnostics(self, request: C0FillRequest) -> None:
        """Passive one-time probes before a fill (no lock held; file I/O here)."""
        self._capture_mount_identity([request.source])
        self._capture_source_cache(request)
        if self._live_sampler is None:
            self._live_sampler = C0LiveSampler(self)
            self._live_sampler.start()

    def _register_inflight(self, request: C0FillRequest, *, started_mono_ns: int) -> None:
        """Record sampler correlation for one outstanding fill (lock held)."""
        self._inflight_requests[int(request.request_id)] = {
            "request_id": int(request.request_id),
            "role": str(request.role),
            "slot_index": int(request.slot_index),
            "producer_id": int(request.producer_id),
            "record_id": request.record_id,
            "fill_index": request.fill_index,
            "source": str(request.source),
            "length": int(request.length),
            "started_mono_ns": int(started_mono_ns),
        }

    def _unregister_inflight(self, request_id: int) -> None:
        self._inflight_requests.pop(int(request_id), None)

    def _after_fill_ready(self, request: C0FillRequest, reply: Any) -> None:
        """Passive one-time slot residency + sampler correlation after READY."""
        self._record_slot_residency(int(request.slot_index))
        if self._live_sampler is not None:
            self._live_sampler.enrich_from_reply(int(request.request_id), reply)

    def _stop_live_sampler(self) -> Optional[dict]:
        sampler = self._live_sampler
        if sampler is None:
            return None
        try:
            return sampler.stop()
        except Exception:  # noqa: BLE001
            return None

    def sampler_role_telemetry(self, role: str, diagnostics: Any) -> dict:
        sampler = self._live_sampler
        if sampler is None:
            return {
                "enabled": False,
                "threshold_ms": round(_C0_LIVE_SAMPLER_THRESHOLD_NS / 1e6, 3),
                "poll_interval_ms": round(_C0_LIVE_SAMPLER_POLL_S * 1000.0, 3),
                "cap": _C0_LIVE_SAMPLER_CAP,
                "sample_count": 0,
                "dropped": 0,
                "missed": 0,
                "record_count": 0,
                "records": [],
                "origins": {
                    "parent": 0,
                    "child-fallback": _child_fallback_records(diagnostics),
                },
            }
        return sampler.role_telemetry(role, diagnostics)

    def sampler_evidence(self) -> dict:
        sampler = self._live_sampler
        if sampler is None:
            return {
                "enabled": False,
                "origin": "parent",
                "threshold_ms": round(_C0_LIVE_SAMPLER_THRESHOLD_NS / 1e6, 3),
                "poll_interval_ms": round(_C0_LIVE_SAMPLER_POLL_S * 1000.0, 3),
                "cap": _C0_LIVE_SAMPLER_CAP,
                "sample_count": 0,
                "record_count": 0,
                "dropped": 0,
                "missed": 0,
                "origins": {"parent": 0, "child-fallback": self._child_fallback_total()},
                "records": [],
            }
        child_fallback = self._child_fallback_total()
        return sampler.snapshot(child_fallback_count=child_fallback)

    def _child_fallback_total(self) -> int:
        total = 0
        for reader in self._stage_readers.values():
            total += _child_fallback_records(getattr(reader, "_preadv_diagnostics", []))
        return total

    def _preadv_sickness_evidence(self) -> dict:
        """Parent-side view of the clustered preadv-sickness diagnostic.

        The child owns the registry/watchdog/probes; the parent retains what it
        was told and never synthesizes a block.  The parent sampler is labelled
        explicitly as parent-side timing and is never substituted for the
        child's passive snapshot.
        """
        if not self.preadv_sickness_diag:
            return {"enabled": False}
        return {
            "enabled": True,
            "selector": True,
            "tripwire_ms": round(C0_PREADV_SICKNESS_TRIPWIRE_NS / 1e6, 3),
            "config_hash": (self.preadv_sickness_hashes or {}).get("config_hash"),
            "profile_hash": (self.preadv_sickness_hashes or {}).get("profile_hash"),
            "profile": (self.preadv_sickness_hashes or {}).get("profile"),
            "invocation_id": self.preadv_sickness_invocation_id,
            "control_manifest_path": c0_preadv_controls_manifest_path(),
            "control_manifest": self.preadv_sickness_manifest,
            "child_launch": (
                dict(self.child_preadv_sickness)
                if self.child_preadv_sickness else None
            ),
            "child_terminal": (
                dict(self.child_preadv_sickness_terminal)
                if self.child_preadv_sickness_terminal else None
            ),
            "hypothesis_families": list(C0_PREADV_SICKNESS_HYPOTHESIS_FAMILIES),
            "hypothesis_statuses": list(C0_PREADV_SICKNESS_HYPOTHESIS_STATUSES),
            "parent_side_timing": {
                "origin": "parent",
                "source": "C0LiveSampler",
                "note": "parent-side timing only; not the child passive snapshot",
            },
        }

    def _residency_evidence(self) -> dict:
        latest = None
        if self._slot_residency_after:
            latest_index = max(self._slot_residency_after)
            latest = dict(self._slot_residency_after[latest_index])
            latest["slot_index"] = latest_index
        return {
            "baseline": self._shm_residency_baseline,
            "after_first_fill": [
                dict(self._slot_residency_after[key])
                for key in sorted(self._slot_residency_after)
            ],
            "latest_slot_residency": latest,
            "thp": _read_thp_state(),
        }

    def _persistence_evidence(self) -> dict:
        return {
            "arena_epoch": int(self.epoch),
            "arena_epoch_stable": self.epoch >= 1,
            "slot_fills": list(self.slot_fills),
            "slot_reuse_count": max(0, self._registered_fill_total - self.slot_count),
            "latest_slot_residency": (
                dict(self._slot_residency_after[max(self._slot_residency_after)])
                if self._slot_residency_after else None
            ),
            "teardown_deferred": bool(self.cleanup_unresolved),
        }

    # ── close ─────────────────────────────────────────────────────────────
    def close(self) -> dict:
        with self._close_lock:
            if self._closed:
                return dict(self.cleanup_status)
            close_t0 = time.perf_counter()
            out: dict[str, Any] = {"pid": self.child_pid, "arena_epoch": self.epoch}
            self._closing.set()
            with self._req_cond:
                self._req_cond.notify_all()
            # Stop/join the passive sampler before the child is stopped so a
            # sample can never race a dead child pid.  Captured into teardown
            # evidence; a None sampler is an explicit disabled/never-started.
            sampler_snapshot = self._stop_live_sampler()
            out["live_sampler"] = sampler_snapshot
            outstanding = self._registry.outstanding
            out["outstanding_fills"] = outstanding
            if outstanding or self._dead is not None or self._inflight:
                # An unresolved fill may still be writing the registered
                # mapping.  Retain ownership rather than unregister/unlink under
                # a live writer; the resource is intentionally left reachable.
                # However the child process itself must still be stopped/reaped
                # with bounded waits, otherwise the Modal invocation stays alive
                # until the 3600s container timeout even after outputs/SHA.
                if outstanding:
                    self._registry.fail_all("c0_close_with_outstanding_fills")
                self.cleanup_unresolved = True
                out["cleanup_status"] = "cleanup_unresolved"
                out["cleanup_unresolved"] = True
                out["dead"] = self._dead
                teardown_order: list[str] = []
                for name, action in (
                    ("child_stop", self._stop_child),
                    ("writer_join", self._join_writer),
                ):
                    step_t0 = time.perf_counter()
                    try:
                        action()
                    except BaseException as exc:  # noqa: BLE001
                        out.setdefault("errors", []).append(
                            f"{name}:{type(exc).__name__}:{exc}"[:200]
                        )
                    out[f"{name}_ms"] = round((time.perf_counter() - step_t0) * 1000.0, 4)
                    teardown_order.append(name)
                out["teardown_order"] = teardown_order
                out["fd_reconciliation"] = self._fd_reconciliation(
                    incomplete_reason="cleanup_unresolved_child_stopped_mapping_retained"
                )
                out["child_viztracer"] = (
                    dict(self.child_viztracer) if self.child_viztracer else None
                )
                out["child_ready_evidence"] = (
                    dict(self.child_ready_evidence) if self.child_ready_evidence else None
                )
                out["runtime_markers"] = dict(self.runtime_markers)
                out["preadv_sickness_diag"] = self._preadv_sickness_evidence()
                out["child_runtime_markers"] = (
                    dict(self.child_runtime_markers) if self.child_runtime_markers else None
                )
                out["close_total_ms"] = round((time.perf_counter() - close_t0) * 1000.0, 4)
                self._closed = True
                self.cleanup_status = dict(out)
                return out

            errors: list[str] = []
            # Reverse creation order, child first: the reader thread is blocked
            # in ``readline`` on a live child, so sending ``exit`` and waiting
            # for termination must happen before the join.  Only then does the
            # child's stdout reach EOF and unblock the reader; joining first
            # would burn the full join timeout on a child nobody asked to exit.
            teardown_order: list[str] = []
            for name, action in (
                ("child_stop", self._stop_child),
                ("writer_join", self._join_writer),
            ):
                step_t0 = time.perf_counter()
                try:
                    action()
                except BaseException as exc:  # noqa: BLE001
                    errors.append(f"{name}:{type(exc).__name__}:{exc}"[:200])
                out[f"{name}_ms"] = round((time.perf_counter() - step_t0) * 1000.0, 4)
                teardown_order.append(name)
            try:
                self._unregister()
            except BaseException as exc:  # noqa: BLE001
                errors.append(f"unregister:{type(exc).__name__}:{exc}"[:200])
            teardown_order.append("unregister")
            if not errors:
                try:
                    out["release_status"] = self._release_mapping()
                except BaseException as exc:  # noqa: BLE001
                    errors.append(f"release:{type(exc).__name__}:{exc}"[:200])
                teardown_order.append("release_mapping")
            if errors:
                self.cleanup_unresolved = True
                out["cleanup_status"] = "cleanup_unresolved"
                out["errors"] = errors
            else:
                out["cleanup_status"] = "released"
            out["teardown_order"] = teardown_order
            out["close_total_ms"] = round((time.perf_counter() - close_t0) * 1000.0, 4)
            out["cleanup_unresolved"] = self.cleanup_unresolved
            out["unregister_ms"] = self.unregister_ms
            out["child_fd_telemetry"] = (
                dict(self.child_fd_telemetry) if self.child_fd_telemetry else None
            )
            out["child_viztracer"] = (
                dict(self.child_viztracer) if self.child_viztracer else None
            )
            out["child_ready_evidence"] = (
                dict(self.child_ready_evidence) if self.child_ready_evidence else None
            )
            out["runtime_markers"] = dict(self.runtime_markers)
            out["preadv_sickness_diag"] = self._preadv_sickness_evidence()
            out["child_runtime_markers"] = (
                dict(self.child_runtime_markers) if self.child_runtime_markers else None
            )
            # Terminal parent-vs-child descriptor reconciliation.  Computed
            # after ``_stop_child`` captured the child's final snapshot; a
            # killed child that emitted none leaves this unknown, never a match.
            out["fd_reconciliation"] = self._fd_reconciliation()
            self._closed = True
            self.cleanup_status = dict(out)
            return out

    def _join_writer(self) -> None:
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=2.0)
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2.0)
        # ``_stop_child`` has already stopped the child, so its stdout is at EOF
        # and the reader either consumed it or exited on the EOF error.  Close
        # the streams only now; closing before the join would race a live
        # blocking ``readline``.
        self._close_ipc_streams()

    def _close_ipc_streams(self) -> None:
        streams = [self._stdin, self._stdout]
        try:
            if self._proc is not None and getattr(self._proc, "stderr", None) is not None:
                streams.append(self._proc.stderr)
        except Exception:
            pass
        for stream in streams:
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

    def _stop_child(self) -> None:
        try:
            if self._stdin is not None:
                self._stdin.write('{"op":"exit"}\n')
                self._stdin.flush()
        except Exception:
            pass
        if self._proc is not None:
            try:
                self._proc.wait(timeout=10.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                try:
                    self._proc.wait(timeout=5.0)
                except Exception:
                    pass
        # The child reports its final descriptor aggregate on stderr just before
        # exit.  Read it only after the process is gone so the read cannot block
        # on a live writer.  The capture itself is bounded (see below).
        self._capture_child_fd_telemetry()

    def _capture_child_fd_telemetry(self) -> None:
        """Parse the child's final ``fd_stats_child`` line, if it emitted one.

        Bounded: never blocks on a live writer and never buffers an unbounded
        terminal payload.  The child truncation fix keeps the terminal block
        small, but an older/stuck child may still emit megabytes; cap the drain
        so teardown cannot stall here.
        """
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
            if proc.poll() is None:
                return
        except Exception:
            return
        try:
            import select as _select

            text_parts: list[str] = []
            total = 0
            limit = 512 * 1024
            stream = proc.stderr
            while total < limit:
                try:
                    ready, _, _ = _select.select([stream], [], [], 2.0)
                except Exception:
                    break
                if not ready:
                    break
                try:
                    chunk = stream.read(min(65536, limit - total))
                except Exception:
                    break
                if not chunk:
                    break
                text_parts.append(chunk)
                total += len(chunk)
                # Child stderr is line-delimited JSON; one full drain pass is
                # enough once the process is reaped.  Avoid spinning: if the
                # stream would block, the select above already gates us.
                if len(chunk) < 65536:
                    # Try one more non-blocking check for EOF, then stop.
                    try:
                        ready2, _, _ = _select.select([stream], [], [], 0.2)
                    except Exception:
                        break
                    if not ready2:
                        # Either EOF or no more data without blocking; stop.
                        # For a closed pipe readline/read returns "" and select
                        # may still report readable, so attempt one final read.
                        try:
                            tail = stream.read(min(65536, limit - total))
                        except Exception:
                            tail = ""
                        if tail:
                            text_parts.append(tail)
                        break
            text = "".join(text_parts)
        except Exception:
            return
        except Exception:
            return
        if not text:
            return
        parsed: Optional[dict] = None
        viz_status: Optional[dict] = None
        sickness_terminal: Optional[dict] = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                candidate = json.loads(line)
            except ValueError:
                continue
            if isinstance(candidate, dict) and candidate.get("op") == "fd_stats_child":
                parsed = candidate
            elif isinstance(candidate, dict) and candidate.get("op") == "child_viztracer_status":
                viz_status = candidate
            elif (
                isinstance(candidate, dict)
                and candidate.get("op") == "preadv_sickness_child_terminal"
            ):
                sickness_terminal = candidate
        if parsed is not None:
            self.child_fd_telemetry = parsed
        if viz_status is not None:
            self.child_viztracer = viz_status
        if sickness_terminal is not None:
            self.child_preadv_sickness_terminal = sickness_terminal

    def _fd_reconciliation(self, *, incomplete_reason: Optional[str] = None) -> dict:
        """Reconcile parent-aggregated per-fill deltas vs the child's snapshot.

        The parent aggregates only what the child reports per fill.  The child's
        terminal snapshot additionally counts the descriptors it closes at child
        shutdown; those are separated by ``fd_shutdown_close_count`` so the two
        views reconcile exactly instead of hiding or double-counting shutdown
        closes.  A missing child snapshot is reported as unknown, never a match.
        """
        parent = {
            "fill_count": int(self.fills_ready),
            "source_bytes": int(self.physical_read_bytes),
            "fd_open_count": int(self.fd_open_count),
            "fd_reuse_count": int(self.fd_reuse_count),
            "fd_close_count": int(self.fd_close_count),
            "fd_open_wall_ms": round(self.fd_open_wall_ms, 4),
            "fd_close_wall_ms": round(self.fd_close_wall_ms, 4),
            "unique_fd_keys": len(self._fd_keys),
            "persistent_fds": bool(self.persistent_fds),
        }
        snapshot = self.child_fd_telemetry
        if not isinstance(snapshot, dict):
            return {
                "parent": parent,
                "child": None,
                "match": False,
                "status": "unknown",
                "reason": incomplete_reason or "child_fd_snapshot_missing",
            }
        shutdown_close = max(0, int(snapshot.get("fd_shutdown_close_count") or 0))
        child = {
            "fill_count": int(snapshot.get("fill_count") or 0),
            "source_bytes": int(snapshot.get("source_bytes") or 0),
            "fd_open_count": int(snapshot.get("fd_open_count") or 0),
            "fd_reuse_count": int(snapshot.get("fd_reuse_count") or 0),
            "fd_close_count": int(snapshot.get("fd_close_count") or 0),
            "fd_shutdown_close_count": shutdown_close,
            "fd_open_wall_ms": round(float(snapshot.get("fd_open_wall_ms") or 0.0), 4),
            "fd_close_wall_ms": round(float(snapshot.get("fd_close_wall_ms") or 0.0), 4),
            "unique_fd_keys": int(snapshot.get("unique_fd_keys") or 0),
            "persistent_fds": bool(snapshot.get("persistent_fds")),
        }
        reasons: list[str] = []
        if parent["fd_open_count"] != child["fd_open_count"]:
            reasons.append(f"fd_open_count:{parent['fd_open_count']}!={child['fd_open_count']}")
        if parent["fd_reuse_count"] != child["fd_reuse_count"]:
            reasons.append(f"fd_reuse_count:{parent['fd_reuse_count']}!={child['fd_reuse_count']}")
        expected_close = parent["fd_close_count"] + child["fd_shutdown_close_count"]
        if expected_close != child["fd_close_count"]:
            reasons.append(f"fd_close_count:{expected_close}!={child['fd_close_count']}")
        if parent["fill_count"] != child["fill_count"]:
            reasons.append(f"fill_count:{parent['fill_count']}!={child['fill_count']}")
        if parent["source_bytes"] != child["source_bytes"]:
            reasons.append(f"source_bytes:{parent['source_bytes']}!={child['source_bytes']}")
        if parent["persistent_fds"] != child["persistent_fds"]:
            reasons.append(f"persistent_fds:{parent['persistent_fds']}!={child['persistent_fds']}")
        match = not reasons
        return {
            "parent": parent,
            "child": child,
            "match": bool(match),
            "status": "complete" if match else "mismatch",
            "reason": "ok" if match else ";".join(reasons)[:240],
            "wall_ms_delta": {
                "open": round(parent["fd_open_wall_ms"] - child["fd_open_wall_ms"], 4),
                "close": round(parent["fd_close_wall_ms"] - child["fd_close_wall_ms"], 4),
            },
        }

    def _unregister(self) -> None:
        if not self.registered:
            return
        torch = _require_torch()
        cudart = torch.cuda.cudart()
        unregister = getattr(cudart, "cudaHostUnregister", None)
        if not callable(unregister):
            raise RuntimeError("cudaHostUnregister_unavailable")
        assert self._arena_address is not None
        t0 = time.perf_counter()
        rc = int(unregister(self._arena_address))
        self.unregister_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        if rc != 0:
            raise RuntimeError(f"cudaHostUnregister_failed:{rc}")
        self.registered = False

    def _release_mapping(self) -> str:
        """Destroy the parent-owned mapping exactly once.

        Detaches the handle before touching it so a repeated release is a
        no-op (idempotent teardown).  ``unlink`` reports the terminal mapping
        state: a POSIX segment that is already gone is released, not failed.
        """
        shm = self._shm
        if shm is None:
            return "already_released"
        self._shm = None
        self._tensor = None
        self._slot_tensors = ()
        self.created = False
        try:
            shm.buf.release()
        except Exception:
            pass
        shm.close()
        try:
            shm.unlink()
            status = "unlinked"
        except FileNotFoundError:
            # The name is already destroyed (for example an out-of-process
            # resource tracker unlinked it at child exit).  Release is complete.
            self._already_unlinked = True
            status = "already_unlinked"
        return status

    # ── evidence ──────────────────────────────────────────────────────────
    def evidence(self) -> dict:
        models = {role: dict(ev) for role, ev in self.events.items()}
        # The retained stage readers own the per-(path, producer) child
        # descriptor evidence.  Surface each role's telemetry under its model
        # entry so arena_evidence() (and the golden_parallel arena_before_close
        # teardown event) carries it without any golden_serial.py change.
        for role, reader in self._stage_readers.items():
            entry = models.get(f"{role}_load")
            if entry is None:
                entry = {}
                models[f"{role}_load"] = entry
            entry["fd_telemetry"] = reader.fd_telemetry()
        return {
            "active": True,
            "mode": "golden_io_process_v2_c0_streaming_arena",
            "arena_bytes": self.size_bytes,
            "slot_count": self.slot_count,
            "slot_bytes": self.slot_bytes,
            "arena_epoch": self.epoch,
            "backing_type": "posix",
            "registered": bool(self.registered),
            # Launch-time cudaHostRegister arm selector snapshot.  ``registered``
            # above proves what actually happened; this proves which arm the
            # deploy baked even if registration failed before evidence.
            "host_register_enabled": bool(self.host_register_enabled),
            "already_unlinked": bool(self._already_unlinked),
            "backing_create_ms": self.backing_create_ms,
            "backing_create_start_ns": self.backing_create_start_ns,
            "backing_create_end_ns": self.backing_create_end_ns,
            "register_ms_one_time": self.register_ms,
            "register_start_ns": self.register_start_ns,
            "register_end_ns": self.register_end_ns,
            "unregister_ms": self.unregister_ms,
            "child_pid": self.child_pid,
            "child_start_ns": self.child_start_ns,
            "child_ready_ns": self.child_ready_ns,
            "child_torch_imported": self.child_torch_imported,
            "child_cuda_initialized": bool(self.child_cuda_initialized),
            "child_cuda_sterile": not bool(self.child_torch_imported),
            # Launch-time treatment snapshot, not a live environment read.
            "persistent_fds": bool(self.persistent_fds),
            # Distinct C0 direct Volume V1 treatment snapshot.  The metadata is
            # the parent-resolved same-name V1 Volume identity (evidence only;
            # object_id_matches_expected is a cross-check, never an authority).
            "source_volume_v1": bool(self.source_volume_v1),
            "source_volume": (
                dict(self.source_volume_metadata)
                if self.source_volume_metadata else None
            ),
            "child_volume_evidence": (
                dict(self.child_volume_evidence)
                if self.child_volume_evidence else None
            ),
            # Diagnostic-only private split-IO snapshot and runtime markers.
            # The child's own markers are carried in ready_child evidence.
            "private_split_io": bool(self.private_split_io),
            "runtime_markers": dict(self.runtime_markers),
            "child_runtime_markers": (
                dict(self.child_runtime_markers) if self.child_runtime_markers else None
            ),
            # Forensic child-only VizTracer launch status.  None when OFF or
            # before launch; explicit unavailable/start_error status when the
            # flag is ON so a missing child trace is visible, never silent.
            "child_viztracer_enabled": bool(self.child_viztracer_enabled),
            "child_viztracer": (
                dict(self.child_viztracer) if self.child_viztracer else None
            ),
            # Diagnostic clustered preadv-sickness snapshot.  OFF is an explicit
            # disabled block; ON carries the launch selector, hashes, the
            # pre-registered control manifest, and the child terminal snapshot.
            "preadv_sickness_diag": self._preadv_sickness_evidence(),
            # Launch-time source-worker readiness proof retained from the
            # child's ready_child report: both configured workers were started
            # and barrier-ready before the parent accepted any fill.
            "child_ready_evidence": (
                dict(self.child_ready_evidence) if self.child_ready_evidence else None
            ),
            "child_workers_configured": (
                self.child_ready_evidence.get("workers_configured")
                if self.child_ready_evidence else None
            ),
            "child_workers_ready": (
                self.child_ready_evidence.get("workers_ready")
                if self.child_ready_evidence else None
            ),
            "child_worker_startup_wall_ms": (
                self.child_ready_evidence.get("startup_wall_ms")
                if self.child_ready_evidence else None
            ),
            "source_geometry": C0_SOURCE_GEOMETRY,
            "source_engine": (
                self.child_ready_evidence.get("source_engine")
                if self.child_ready_evidence else None
            ),
            "source_engine_fallback": {
                "selected": (
                    self.child_ready_evidence.get("source_engine")
                    if self.child_ready_evidence else None
                ),
                "fallback": False,
                "reason": "no_cross_engine_fallback",
            },
            "capacity_class": C0_CAPACITY_CLASS,
            "source_workers": C0_SOURCE_WORKERS,
            "source_qd": C0_SOURCE_WORKERS,
            "slot_owners": list(C0_SLOT_OWNERS),
            "slot_fills": list(self.slot_fills),
            "slot_reuse_count": max(0, self._registered_fill_total - self.slot_count),
            "fills_submitted": self.fills_submitted,
            "fills_ready": self.fills_ready,
            "fills_failed": self.fills_failed,
            "short_read_failures": self.short_read_failures,
            "correctness_ok": bool(
                self.fills_submitted > 0
                and self.fills_submitted == self.fills_ready
                and self.fills_failed == 0
            ),
            "max_concurrent_fills": self.max_concurrent_fills,
            "concurrent_fill_events": self.concurrent_fill_events,
            "overlap_events": self.concurrent_fill_events,
            # Parent lease-inflight occupancy (the ring's own outstanding-fill
            # counter).  Bucket i counts observations with i simultaneous
            # leases; clamped at QD4 while ``max_source_inflight`` keeps the
            # true peak.  Passive evidence only.
            "max_source_inflight": int(self.max_source_inflight),
            "source_inflight_samples": int(self.source_inflight_samples),
            "source_inflight_occupancy_qd0_qd4": list(self.source_inflight_occupancy),
            "backpressure_block_count": self.backpressure_block_count,
            "backpressure_block_ms": round(self.backpressure_block_ns / 1e6, 4),
            "physical_read_bytes": self.physical_read_bytes,
            "physical_read_syscalls": self.physical_read_syscalls,
            "fill_count": self.fills_ready,
            "source_bytes": self.physical_read_bytes,
            "source_fill_wall_ms": round(self.total_fill_wall_ns / 1e6, 4),
            "fd_open_count": int(self.fd_open_count),
            "fd_reuse_count": int(self.fd_reuse_count),
            "fd_close_count": int(self.fd_close_count),
            "fd_open_wall_ms": round(self.fd_open_wall_ms, 4),
            "fd_close_wall_ms": round(self.fd_close_wall_ms, 4),
            "unique_fd_keys": len(self._fd_keys),
            "fd_keys": [
                {"path": path, "producer_id": producer_id}
                for path, producer_id in sorted(self._fd_keys)
            ],
            "child_fd_telemetry": (
                dict(self.child_fd_telemetry) if self.child_fd_telemetry else None
            ),
            "parent_physical_source_reads": 0,
            "shared_to_pinned_bytes": 0,
            "full_payload_host_memcpy": False,
            "fallback_count": 0,
            "cleanup_status": dict(self.cleanup_status),
            "cleanup_unresolved": bool(self.cleanup_unresolved),
            # ── bounded passive preadv diagnostics (evidence only) ─────────
            # Parent live sampler (or its explicit disabled shape), one-time
            # mount identity, SHM/source page residency, runtime/cgroup/PSI
            # identity, and arena persistence stability.  Every block carries
            # its own availability/errors; missing values are never zeroed.
            "live_sampler": self.sampler_evidence(),
            "mount_identity": (
                dict(self._mount_identity) if self._mount_identity is not None else {
                    "supported": False,
                    "error": "not_captured",
                    "paths": {},
                    "statfs": {},
                    "entries": [],
                }
            ),
            "shm_residency": self._residency_evidence(),
            "source_cache": {
                "paths": {path: dict(probe) for path, probe in self._source_cache.items()},
                "unique_paths": len(self._source_cache),
            },
            "runtime_identity": (
                dict(self._runtime_identity) if self._runtime_identity is not None else {
                    "captured": False,
                    "error": "not_captured",
                }
            ),
            "persistence": self._persistence_evidence(),
            "models": models,
        }


def _lease_target_address(target: Any) -> int:
    """Return the writable host address of a lease read target.

    C0 arena slots are CPU ``torch.uint8`` views over the registered POSIX
    mapping.  ``ctypes`` cannot consume torch's own buffer export, so tensor
    targets are converted through the canonical writable-byte view used by the
    Golden readers; that view rejects non-CPU, non-uint8, non-contiguous, and
    read-only storage.  Plain buffer objects (bytearray/memoryview pools) are
    validated as writable through ``ctypes``.  Anything else fails closed.
    """
    if callable(getattr(target, "data_ptr", None)):
        from .golden_serial import _writable_bytes_view

        view = _writable_bytes_view(target)
        return int(ctypes.addressof(ctypes.c_char.from_buffer(view)))
    return int(ctypes.addressof(ctypes.c_char.from_buffer(target)))


class C0StageReader:
    """Lease-aware child-fill seam for one C0 model stage.

    The child performs the physical read into the registered shared slot; the
    parent returns the byte count with no shared->pinned copy.  Every request
    carries arena epoch, slot index, slot generation, request id, role/source
    identity, source offset, destination offset, and length.
    """

    handles_actual_source_telemetry = False
    actual_source_telemetry = None
    child_owned_physical_reads = True

    def __init__(self, ring: SharedArenaRing, *, role: str, pool: Any, source: str) -> None:
        if role not in C0_VALID_ROLES:
            raise C0ProtocolError(f"c0_invalid_role:{role!r}")
        self._ring = ring
        self._role = role
        self._pool = pool
        self._source = os.path.abspath(str(source))
        self.open_count = 0
        self.fill_wall_ns = 0
        self.fills = 0
        self.source_bytes = 0
        # Child-reported descriptor-lifecycle telemetry, keyed by producer.  The
        # path is fixed for this stage reader, so (path, producer) is recovered
        # from the reader's source plus the producer id.
        self.fd_open_count = 0
        self.fd_reuse_count = 0
        self.fd_close_count = 0
        self.fd_open_wall_ms = 0.0
        self.fd_close_wall_ms = 0.0
        self._fd_by_producer: dict[int, dict] = {}
        # Passive per-role overlap instants (evidence only; never branched on).
        self.first_source_read_start_mono_ns: Optional[int] = None
        self.last_source_read_end_mono_ns: Optional[int] = None
        # Child-reported positioned-read interval: the child and parent
        # monotonic clocks are comparable on the target, so these are stored
        # verbatim from replies and never invented.
        self.first_child_read_start_mono_ns: Optional[int] = None
        self.last_child_read_end_mono_ns: Optional[int] = None
        self._child_read_durations_ns: list[int] = []
        # Passive per-read mmap-engine phase split (empty for the preadv path).
        self._mmap_map_ns: list[int] = []
        self._mmap_memcpy_ns: list[int] = []
        self._mmap_memcpy_warm_ns: list[int] = []
        self._mmap_memcpy_shm_warm_ns: list[int] = []
        self._mmap_frozen_copy_ns: list[int] = []
        self._mmap_frozen_unmap_ns: list[int] = []
        self._mmap_munmap_ns: list[int] = []
        self._mmap_gate_wait_ns: list[int] = []
        self._mmap_pipe_rtt_ns: list[int] = []
        self._source_touch_copy_ns: list[int] = []
        self._mmap_read_records: list[dict] = []
        self._mmap_minflt: list[int] = []
        self._mmap_majflt: list[int] = []
        self._mmap_reader_pids: set[int] = set()
        # FIRST_FILL vs REUSED_SLOT split.  The parent classifies every fill
        # from its own slot-fill counter: the first touch of a slot
        # materializes destination pages on the write path, later fills reuse
        # them.  The production arena is never prefaulted/warmed, so this split
        # is the only honest way to separate a first-touch penalty from
        # steady-state copies.  Stored only; never branched on.
        self._fill_first_count = 0
        self._fill_reuse_count = 0
        self._mmap_memcpy_first_ns: list[int] = []
        self._mmap_memcpy_reuse_ns: list[int] = []
        self._mmap_map_first_ns: list[int] = []
        self._mmap_map_reuse_ns: list[int] = []
        self._mmap_munmap_first_ns: list[int] = []
        self._mmap_munmap_reuse_ns: list[int] = []
        self._mmap_op_total_first_ns: list[int] = []
        self._mmap_op_total_reuse_ns: list[int] = []
        self._mmap_pipe_rtt_first_ns: list[int] = []
        self._mmap_pipe_rtt_reuse_ns: list[int] = []
        # Diagnostic private split-IO role telemetry.  The child reports the
        # split fields; the parent aggregates them per role and never invents
        # a timing or a worker identity.
        self.private_split_io = bool(ring.private_split_io)
        self.private_buffer_bytes = 0
        self._source_read_durations_ns: list[int] = []
        self._private_to_shm_durations_ns: list[int] = []
        self._worker_identities: set[int] = set()
        self._worker_indices: set[int] = set()
        # Passive per-read syscall diagnostics copied verbatim from child
        # replies.  The parent never synthesizes a record: absent replies leave
        # this empty and ``fd_telemetry`` reports an empty list.
        self._preadv_diagnostics: list[dict] = []
        # Distinct C0 direct Volume V1 telemetry copied verbatim from child
        # replies: one summary per logical extent plus the flattened per-block
        # diagnostics.  Empty (never fabricated) when the treatment is OFF.
        self.source_volume_v1 = bool(getattr(ring, "source_volume_v1", False))
        self._volume_transfers: list[dict] = []
        self._volume_block_diagnostics: list[dict] = []
        # Diagnostic clustered preadv-sickness blocks copied verbatim from child
        # replies (ready and error).  Empty when the selector is OFF; the parent
        # never synthesizes a block or a hypothesis.
        self.preadv_sickness_diag = bool(getattr(ring, "preadv_sickness_diag", False))
        self._sickness_diagnostics: list[dict] = []

    @property
    def pool(self) -> Any:
        return self._pool

    def _next_request_id(self) -> int:
        with self._ring._req_cond:
            self._ring._next_request_id += 1
            return self._ring._next_request_id

    def readinto_lease(self, lease: Any, target: Any, offset: int, producer_id: Optional[int] = None) -> int:
        from .golden_qd_transport import StageLease

        if not isinstance(lease, StageLease):
            raise C0ProtocolError("c0_requires_typed_lease")
        if lease._pool is not self._pool:
            raise C0ProtocolError("c0_lease_belongs_to_other_pool")
        length = len(target)
        if length <= 0:
            return 0
        slot_index = int(lease.slot_index)
        declared = lease.declared_range
        if declared is None:
            raise C0ProtocolError("c0_lease_declared_range_missing")
        # The declared lease range is the authoritative source identity; the
        # physical read cursor must land exactly on it before any bytes move,
        # and the requested extent must not overrun the declared interval.
        if int(offset) != int(declared.source_offset):
            raise C0ProtocolError(
                f"c0_lease_source_offset_mismatch:{int(offset)}!={int(declared.source_offset)}"
            )
        if length > int(declared.length):
            raise C0ProtocolError(
                f"c0_lease_length_exceeds_declared_range:{length}>{int(declared.length)}"
            )
        base = self._ring.slot_base_address(slot_index)
        try:
            address = _lease_target_address(target)
        except (TypeError, ValueError, BufferError) as exc:
            raise C0ProtocolError("c0_target_not_writable_shared_slot") from exc
        if address < base or address + length > base + self._ring.slot_bytes:
            raise C0ProtocolError("c0_target_outside_leased_slot")
        # ``destination_offset`` is the physical write position *within the
        # leased slot* -- the child writes there directly.  The absolute model
        # destination stays owned by the dispatcher's ReadyRecord.
        destination_in_slot = address - base
        if producer_id is None:
            producer_id = 0
        elif (
            not isinstance(producer_id, int)
            or isinstance(producer_id, bool)
            or producer_id < 0
        ):
            raise C0ProtocolError(f"c0_invalid_producer_id:{producer_id!r}")
        request = C0FillRequest(
            request_id=self._next_request_id(),
            arena_epoch=self._ring.epoch,
            role=self._role,
            source=self._source,
            slot_index=slot_index,
            slot_generation=int(lease.generation),
            source_offset=int(offset),
            destination_offset=destination_in_slot,
            length=length,
            producer_id=int(producer_id),
            # Passive correlation metadata only: the declared record id plus
            # this reader's submission ordinal, stamped before ``fill`` so the
            # child can correlate each physical read with its submission.
            record_id=declared.record_id,
            fill_index=int(self.fills),
        )
        validate_fill_request(request)
        started = time.monotonic_ns()
        # FIRST_FILL vs REUSED_SLOT classification, taken from the ring's own
        # slot-fill counter before this fill increments it.  Only one fill can
        # be outstanding per leased slot, so this read is exact for the slot.
        first_fill = int(self._ring.slot_fills[slot_index]) == 0
        reply = self._ring.fill(request)
        self.fill_wall_ns += time.monotonic_ns() - started
        self.fills += 1
        self.source_bytes += length
        self._record_fill_telemetry(
            producer_id=int(producer_id),
            length=length,
            reply=reply,
            first_fill=bool(first_fill),
        )
        # Passive: mirror the ring's per-role stamps into this stage reader.
        submit_ns = self._ring.fill_submit_mono_ns.get(self._role)
        if submit_ns is not None and (
            self.first_source_read_start_mono_ns is None
            or submit_ns < self.first_source_read_start_mono_ns
        ):
            self.first_source_read_start_mono_ns = submit_ns
        ready_ns = self._ring.fill_ready_mono_ns.get(self._role)
        if ready_ns is not None and (
            self.last_source_read_end_mono_ns is None
            or ready_ns > self.last_source_read_end_mono_ns
        ):
            self.last_source_read_end_mono_ns = ready_ns
        # The child wrote directly into the registered slot; the validated
        # reply is the only proof that lets the dispatcher publish READY.
        return length

    def _record_fill_telemetry(
        self, *, producer_id: int, length: int, reply: Any, first_fill: bool
    ) -> None:
        """Fold one child fill's descriptor deltas into this stage reader."""
        source = dict(reply) if isinstance(reply, dict) else {}
        if first_fill:
            self._fill_first_count += 1
        else:
            self._fill_reuse_count += 1
        opened = max(0, int(source.get("fd_open_count") or 0))
        reused = max(0, int(source.get("fd_reuse_count") or 0))
        closed = max(0, int(source.get("fd_close_count") or 0))
        open_wall = max(0.0, float(source.get("fd_open_wall_ms") or 0.0))
        close_wall = max(0.0, float(source.get("fd_close_wall_ms") or 0.0))
        self.fd_open_count += opened
        self.fd_reuse_count += reused
        self.fd_close_count += closed
        self.fd_open_wall_ms += open_wall
        self.fd_close_wall_ms += close_wall
        entry = self._fd_by_producer.get(producer_id)
        if entry is None:
            entry = {
                "path": self._source,
                "producer_id": int(producer_id),
                "fill_count": 0,
                "source_bytes": 0,
                "fd_open_count": 0,
                "fd_reuse_count": 0,
                "fd_close_count": 0,
                "fd_open_wall_ms": 0.0,
                "fd_close_wall_ms": 0.0,
            }
            self._fd_by_producer[producer_id] = entry
        entry["fill_count"] += 1
        entry["source_bytes"] += int(length)
        entry["fd_open_count"] += opened
        entry["fd_reuse_count"] += reused
        entry["fd_close_count"] += closed
        entry["fd_open_wall_ms"] = round(entry["fd_open_wall_ms"] + open_wall, 4)
        entry["fd_close_wall_ms"] = round(entry["fd_close_wall_ms"] + close_wall, 4)
        # Child positioned-read interval and duration, taken verbatim from the
        # reply so the per-role aggregate is provable from raw child evidence.
        start_ns = source.get("child_read_start_ns")
        end_ns = source.get("child_read_end_ns")
        duration_ns = source.get("read_duration_ns")
        if _is_plain_int(start_ns) and (
            self.first_child_read_start_mono_ns is None
            or int(start_ns) < self.first_child_read_start_mono_ns
        ):
            self.first_child_read_start_mono_ns = int(start_ns)
        if _is_plain_int(end_ns) and (
            self.last_child_read_end_mono_ns is None
            or int(end_ns) > self.last_child_read_end_mono_ns
        ):
            self.last_child_read_end_mono_ns = int(end_ns)
        if _is_plain_int(duration_ns):
            self._child_read_durations_ns.append(int(duration_ns))
        # Passive per-read mmap-engine phase split, copied verbatim from the
        # reply when the child ran the mmap engine; absent for the preadv path.
        for _attr, _key in (
            ("_mmap_map_ns", "mmap_map_ns"),
            ("_mmap_memcpy_ns", "mmap_memcpy_ns"),
            ("_mmap_memcpy_warm_ns", "mmap_memcpy_warm_ns"),
            ("_mmap_memcpy_shm_warm_ns", "mmap_memcpy_shm_warm_ns"),
            ("_mmap_frozen_copy_ns", "mmap_frozen_copy_ns"),
            ("_mmap_frozen_unmap_ns", "mmap_frozen_unmap_ns"),
            ("_mmap_munmap_ns", "mmap_munmap_ns"),
            ("_mmap_gate_wait_ns", "mmap_launch_gap_wait_ns"),
            ("_mmap_pipe_rtt_ns", "mmap_pipe_rtt_ns"),
            ("_mmap_minflt", "mmap_minflt"),
            ("_mmap_majflt", "mmap_majflt"),
        ):
            _value = source.get(_key)
            if _is_plain_int(_value):
                getattr(self, _attr).append(int(_value))
        if str(source.get("source_engine") or "") == "mmap_fresh":
            copy_start = source.get("copy_start_ns")
            copy_end = source.get("copy_end_ns")
            returned = source.get("returned_bytes")
            if all(_is_plain_int(value) for value in (copy_start, copy_end, returned)):
                self._mmap_read_records.append({
                    "copy_start_ns": int(copy_start),
                    "copy_end_ns": int(copy_end),
                    "returned_bytes": int(returned),
                    "source_offset": source.get("source_offset"),
                    "source_range": source.get("source_range"),
                    "mmap_map_ns": source.get("mmap_map_ns"),
                    "source_touch_copy_ns": source.get(
                        "source_touch_copy_ns", source.get("mmap_memcpy_ns")
                    ),
                    "mmap_munmap_ns": source.get("mmap_munmap_ns"),
                    "mmap_op_ns": source.get("mmap_op_ns", source.get("read_duration_ns")),
                    "mmap_pipe_rtt_ns": source.get("mmap_pipe_rtt_ns"),
                    "pipe_excess_ns": (
                        int(source["mmap_pipe_rtt_ns"])
                        - int(source.get("mmap_op_ns", source.get("read_duration_ns")))
                        if _is_plain_int(source.get("mmap_pipe_rtt_ns"))
                        and _is_plain_int(source.get("mmap_op_ns", source.get("read_duration_ns")))
                        else None
                    ),
                })
                copy_ns = source.get("source_touch_copy_ns", source.get("mmap_memcpy_ns"))
                if _is_plain_int(copy_ns):
                    self._source_touch_copy_ns.append(int(copy_ns))
        # FIRST_FILL vs REUSED_SLOT split of the mmap source-touch memcpy, the
        # whole source op, map, munmap and pipe round-trip. On the direct path
        # the memcpy destination is SHM; on private-split it is private staging
        # and private_to_shm_duration_ns reports the second copy separately.
        for _key, _first_attr, _reuse_attr in (
            ("mmap_memcpy_ns", "_mmap_memcpy_first_ns", "_mmap_memcpy_reuse_ns"),
            ("mmap_map_ns", "_mmap_map_first_ns", "_mmap_map_reuse_ns"),
            ("mmap_munmap_ns", "_mmap_munmap_first_ns", "_mmap_munmap_reuse_ns"),
            ("mmap_pipe_rtt_ns", "_mmap_pipe_rtt_first_ns", "_mmap_pipe_rtt_reuse_ns"),
            ("read_duration_ns", "_mmap_op_total_first_ns", "_mmap_op_total_reuse_ns"),
        ):
            _value = source.get(_key)
            if _is_plain_int(_value):
                _target = _first_attr if first_fill else _reuse_attr
                getattr(self, _target).append(int(_value))
        _reader_pid = source.get("reader_pid")
        if _is_plain_int(_reader_pid):
            self._mmap_reader_pids.add(int(_reader_pid))
        # Diagnostic private split-IO fields.  Only present when the child ran
        # the split path; the parent records the split source-read and
        # private->SHM copy durations and this worker's identity verbatim.
        if bool(source.get("split_io")):
            self.private_split_io = True
            source_read_ns = source.get("source_read_duration_ns")
            if _is_plain_int(source_read_ns):
                self._source_read_durations_ns.append(int(source_read_ns))
            copy_ns = source.get("private_to_shm_duration_ns")
            if _is_plain_int(copy_ns):
                self._private_to_shm_durations_ns.append(int(copy_ns))
            buffer_bytes = source.get("private_buffer_bytes")
            if _is_plain_int(buffer_bytes):
                self.private_buffer_bytes = max(
                    self.private_buffer_bytes, int(buffer_bytes)
                )
            worker_ident = source.get("worker_ident")
            if _is_plain_int(worker_ident):
                self._worker_identities.add(int(worker_ident))
            worker_index = source.get("worker_index")
            if _is_plain_int(worker_index):
                self._worker_indices.add(int(worker_index))
        # Passive per-read syscall diagnostics.  Copy only dict records the
        # child actually reported; never synthesize a key or a value here.
        self._absorb_preadv_diagnostics(reply)
        # Distinct C0 direct Volume V1 telemetry, copied verbatim from the reply
        # when the treatment produced it; a no-op for the preadv control.
        self._absorb_volume_telemetry(reply)
        # Diagnostic clustered preadv-sickness block, copied verbatim when the
        # selector produced one; a no-op otherwise.
        self._absorb_sickness_diagnostics(reply)

    def _absorb_sickness_diagnostics(self, reply: Any) -> None:
        """Copy a child reply's preadv-sickness block verbatim, or nothing.

        Used by the ready path and the ring's error path so a failed fill's
        diagnostic survives.  The parent never invents a block.
        """
        source = dict(reply) if isinstance(reply, dict) else {}
        block = source.get("preadv_sickness_diag")
        if isinstance(block, dict):
            self._sickness_diagnostics.append(dict(block))

    def _sickness_telemetry(self) -> dict:
        """Aggregate this stage's preadv-sickness evidence (never fabricated)."""
        blocks = [dict(block) for block in self._sickness_diagnostics]
        fired = [block for block in blocks if bool(block.get("tripwire", {}).get("fired"))]
        hypotheses: dict = {}
        # Per-family status history, recorded only when fired blocks disagree.
        # Raw blocks remain authoritative; this summary preserves a later
        # conflicting status instead of silently dropping it to the first block.
        conflicts: dict = {}
        for block in fired:
            for family, entry in (block.get("hypotheses") or {}).items():
                previous = hypotheses.get(family)
                if isinstance(previous, dict):
                    previous_status = previous.get("status")
                    current_status = (
                        entry.get("status") if isinstance(entry, dict) else None
                    )
                    if previous_status != current_status:
                        history = conflicts.setdefault(family, [previous_status])
                        if current_status not in history:
                            history.append(current_status)
                # Latest block wins.
                hypotheses[family] = entry
        return {
            "enabled": bool(self.preadv_sickness_diag),
            "block_count": len(blocks),
            "fired_count": len(fired),
            "blocks": blocks,
            "hypothesis_families": list(C0_PREADV_SICKNESS_HYPOTHESIS_FAMILIES),
            "latest_hypotheses": hypotheses,
            "hypothesis_conflicts": conflicts,
            # Explicitly labelled parent-side timing reference; the child passive
            # snapshot is never substituted by or with this.
            "parent_side_timing": {
                "origin": "parent",
                "source": "C0LiveSampler",
                "note": "parent-side timing only; not the child passive snapshot",
            },
        }

    def _absorb_volume_telemetry(self, reply: Any) -> None:
        """Copy a child reply's direct-Volume telemetry verbatim, or nothing.

        Used by the ready path and the ring's error path so a failed extent's
        block diagnostics survive.  The parent never invents a transfer, block
        record, digest, or timing.
        """
        source = dict(reply) if isinstance(reply, dict) else {}
        transfer = source.get("volume_transfer")
        if isinstance(transfer, dict):
            self._volume_transfers.append(dict(transfer))
        diagnostics = source.get("volume_block_diagnostics")
        if isinstance(diagnostics, list):
            for record in diagnostics:
                if isinstance(record, dict):
                    self._volume_block_diagnostics.append(dict(record))

    def _volume_telemetry(self) -> dict:
        """Aggregate this stage's direct-Volume V1 evidence (never fabricated)."""
        transfers = [dict(item) for item in self._volume_transfers]
        total_phase_ms = sum(
            float(item.get("volume_phase_wall_ms") or 0.0) for item in transfers
        )
        completed_bytes = sum(
            int(item.get("completed_bytes") or 0) for item in transfers
        )
        return {
            "source_volume_v1": bool(self.source_volume_v1),
            "extent_count": len(transfers),
            "block_count": sum(int(item.get("block_count") or 0) for item in transfers),
            "requested_bytes": sum(
                int(item.get("requested_bytes") or 0) for item in transfers
            ),
            "completed_bytes": completed_bytes,
            "volume_metadata_rpc_wall_ms": sum(
                float(item.get("volume_metadata_rpc_wall_ms") or 0.0)
                for item in transfers
            ),
            "volume_phase_wall_ms": total_phase_ms,
            "aggregate_bps": (
                completed_bytes / (total_phase_ms / 1000.0)
                if total_phase_ms > 0 else None
            ),
            "concurrency": max(
                (int(item.get("concurrency") or 0) for item in transfers), default=0
            ),
            "concurrency_high_water": max(
                (int(item.get("concurrency_high_water") or 0) for item in transfers),
                default=0,
            ),
            "retry_count": sum(
                int(item.get("retry_count") or 0) for item in transfers
            ),
            "failure_count": sum(
                int(item.get("failure_count") or 0) for item in transfers
            ),
            "fallback_count": sum(
                int(item.get("fallback_count") or 0) for item in transfers
            ),
            "extents": transfers,
        }

    def _absorb_preadv_diagnostics(self, reply: Any) -> None:
        """Copy a child reply's per-read diagnostics verbatim, or nothing.

        Used by the ready path (``_record_fill_telemetry``) and by the ring's
        error path, so a short-read/failed fill's per-read evidence is retained
        rather than silently dropped.  Records are shallow-copied and malformed
        entries ignored; the parent never invents a record.
        """
        source = dict(reply) if isinstance(reply, dict) else {}
        diagnostics = source.get("preadv_diagnostics")
        if not isinstance(diagnostics, list):
            return
        for record in diagnostics:
            if isinstance(record, dict):
                self._preadv_diagnostics.append(dict(record))

    def fd_telemetry(self) -> dict:
        """Authoritative per-role/path descriptor evidence for this stage.

        ``keys`` is keyed by full source path and producer id.  Every value is
        child-reported; the parent aggregates, it does not invent descriptor
        activity.
        """
        return {
            "role": self._role,
            "path": self._source,
            "persistent_fds": bool(self._ring.persistent_fds),
            "fill_count": int(self.fills),
            "source_bytes": int(self.source_bytes),
            "source_fill_wall_ms": round(self.fill_wall_ns / 1e6, 4),
            "fd_open_count": int(self.fd_open_count),
            "fd_reuse_count": int(self.fd_reuse_count),
            "fd_close_count": int(self.fd_close_count),
            "fd_open_wall_ms": round(self.fd_open_wall_ms, 4),
            "fd_close_wall_ms": round(self.fd_close_wall_ms, 4),
            "unique_fd_keys": len(self._fd_by_producer),
            "keys": [
                dict(self._fd_by_producer[key])
                for key in sorted(self._fd_by_producer)
            ],
            # Passive per-role timing evidence.  The two parent markers are the
            # earliest fill-submit / latest fill-ready instants; the two child
            # markers are the child's own first read-start / last read-end.
            # Stored only; never consumed by a branch, gate, retry, or fallback.
            "first_source_read_start_mono_ns": (
                int(self.first_source_read_start_mono_ns)
                if self.first_source_read_start_mono_ns is not None else None
            ),
            "last_source_read_end_mono_ns": (
                int(self.last_source_read_end_mono_ns)
                if self.last_source_read_end_mono_ns is not None else None
            ),
            "first_fill_submit_mono_ns": self._ring.fill_submit_mono_ns.get(self._role),
            "last_fill_ready_mono_ns": self._ring.fill_ready_mono_ns.get(self._role),
            "first_child_read_start_mono_ns": self.first_child_read_start_mono_ns,
            "last_child_read_end_mono_ns": self.last_child_read_end_mono_ns,
            "child_read_duration_ms": _read_duration_summary(
                self._child_read_durations_ns
            ),
            # Passive mmap-engine per-read phase split (empty for preadv).  This
            # attributes the source cost to map / memcpy / unmap / gate wait /
            # pipe round-trip and page faults, so no second experiment is needed
            # to prove where source time goes.
            "mmap_read_phases": {
                "available": bool(self._mmap_map_ns),
                "map_ms": _read_duration_summary(self._mmap_map_ns),
                "memcpy_ms": _read_duration_summary(self._mmap_memcpy_ns),
                "memcpy_warm_ms": _read_duration_summary(
                    self._mmap_memcpy_warm_ns
                ),
                "memcpy_shm_warm_ms": _read_duration_summary(
                    self._mmap_memcpy_shm_warm_ns
                ),
                "frozen_parity_copy_ms": _read_duration_summary(
                    self._mmap_frozen_copy_ns
                ),
                "frozen_parity_unmap_ms": _read_duration_summary(
                    self._mmap_frozen_unmap_ns
                ),
                "munmap_ms": _read_duration_summary(self._mmap_munmap_ns),
                "gate_wait_ms": _read_duration_summary(self._mmap_gate_wait_ns),
                "pipe_rtt_ms": _read_duration_summary(self._mmap_pipe_rtt_ns),
                "minflt_total": (
                    sum(self._mmap_minflt) if self._mmap_minflt else None
                ),
                "majflt_total": (
                    sum(self._mmap_majflt) if self._mmap_majflt else None
                ),
                "reader_pids": sorted(self._mmap_reader_pids),
                "source_touch_copy_ms": _read_duration_summary(self._source_touch_copy_ns),
                "source_touch_copy_records": [dict(record) for record in self._mmap_read_records],
                "mmap_read_records": [dict(record) for record in self._mmap_read_records],
                "source_touch_copy_throughput": source_touch_copy_throughput(
                    self._mmap_read_records
                ),
            },
            # FIRST_FILL vs REUSED_SLOT split.  Each sub-distribution carries
            # the raw per-read samples, so any percentile/threshold can be
            # reconstructed from this evidence.  Empty for the preadv control.
            "first_fill_split": {
                "first_fill_count": int(self._fill_first_count),
                "reused_slot_count": int(self._fill_reuse_count),
                "memcpy_first_fill_ms": _read_duration_summary(
                    self._mmap_memcpy_first_ns
                ),
                "memcpy_reused_slot_ms": _read_duration_summary(
                    self._mmap_memcpy_reuse_ns
                ),
                "map_first_fill_ms": _read_duration_summary(
                    self._mmap_map_first_ns
                ),
                "map_reused_slot_ms": _read_duration_summary(
                    self._mmap_map_reuse_ns
                ),
                "munmap_first_fill_ms": _read_duration_summary(
                    self._mmap_munmap_first_ns
                ),
                "munmap_reused_slot_ms": _read_duration_summary(
                    self._mmap_munmap_reuse_ns
                ),
                "op_total_first_fill_ms": _read_duration_summary(
                    self._mmap_op_total_first_ns
                ),
                "op_total_reused_slot_ms": _read_duration_summary(
                    self._mmap_op_total_reuse_ns
                ),
                "pipe_rtt_first_fill_ms": _read_duration_summary(
                    self._mmap_pipe_rtt_first_ns
                ),
                "pipe_rtt_reused_slot_ms": _read_duration_summary(
                    self._mmap_pipe_rtt_reuse_ns
                ),
            },
            # Diagnostic private split-IO role telemetry.  ``source_read`` is
            # file -> private buffer; ``private_to_shm`` is private buffer ->
            # leased SHM slot.  OFF reports an empty/zero split block.
            "split_io": bool(self.private_split_io),
            "private_buffer_bytes": int(self.private_buffer_bytes),
            "worker_identities": sorted(self._worker_identities),
            "worker_indices": sorted(self._worker_indices),
            "source_read_duration_ms": _read_duration_summary(
                self._source_read_durations_ns
            ),
            "private_to_shm_duration_ms": _read_duration_summary(
                self._private_to_shm_durations_ns
            ),
            # Passive per-read positioned-syscall diagnostics, copied verbatim
            # from child replies.  Empty (never fabricated) when the child
            # reported none.
            "preadv_diagnostics": [dict(record) for record in self._preadv_diagnostics],
            # Distinct C0 direct Volume V1 evidence: the aggregate summary plus
            # the flattened, verbatim per-block diagnostics alongside the preadv
            # list above.  OFF reports an explicit disabled/empty block.
            "volume_telemetry": self._volume_telemetry(),
            "volume_block_diagnostics": [
                dict(record) for record in self._volume_block_diagnostics
            ],
            # Diagnostic clustered preadv-sickness evidence, copied verbatim
            # from child replies.  OFF reports an explicit disabled block.
            "preadv_sickness_diag": self._sickness_telemetry(),
            # Passive bounded live-sampler evidence for this role plus the
            # child post-hoc fallback captures carried by its diagnostics.
            "sampler": self._ring.sampler_role_telemetry(
                self._role, self._preadv_diagnostics
            ),
        }

    def readinto(self, target: Any, offset: int, producer_id: Optional[int] = None) -> int:
        # C0 must never accept a non-lease fill: without the lease there is no
        # authoritative slot/generation identity to place the bytes.
        raise C0ProtocolError("c0_requires_readinto_lease")

    def close(self) -> None:
        return None


_C0_CHILD_SOURCE = r"""
import asyncio
import ctypes
import importlib.util
import json
import os
import queue
import resource
import select
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import shared_memory

shm_name = str(sys.argv[1])
arena_bytes = int(sys.argv[2])
slot_count = int(sys.argv[3])
slot_bytes = int(sys.argv[4])
workers = int(sys.argv[5]) if len(sys.argv) > 5 else 2

# Deploy-baked source-engine selector, read once at child launch.  ``preadv``
# (default) is the exact positioned-read control.  ``mmap_fresh`` replaces ONLY
# the byte producer with the frozen mmap engine: each source worker is an
# independent READER PROCESS (never a thread), started eagerly, holding a
# persistent per-(path, producer) descriptor, and performing a fresh
# PROT_READ|MAP_PRIVATE exact-window mapping per read copied with native
# libc.memcpy and unmapped synchronously.  A 4 ms global launch-spacing floor is
# shared by every reader.  There is deliberately no cross-arm fallback.
source_engine = (
    str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE") or "preadv")
    .strip().lower()
)
mmap_engine = source_engine == "mmap_fresh"
# Diagnostic-only (default OFF): an extra warm copy per read, used once to split
# source page-in from destination-copy cost.  Never enabled for production.
mmap_copy_diag = (
    str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_MMAP_COPY_DIAG") or "")
    .strip().lower() in ("1", "true", "yes", "on")
)
# Diagnostics cost extra full copies per read, so they run only for the first
# few fills of each reader process (one reader == one process == one budget).
_mmap_diag_budget = 3
MMAP_LAUNCH_GAP_NS = 4_000_000
_PROT_READ = 1
_MAP_PRIVATE = 2
_PAGE = 4096
_mmap_libc = None
_mmap_buf_addr = 0
_mmap_reader_fds = {}
_mmap_readers = []
if mmap_engine:
    _mmap_libc = ctypes.CDLL(None, use_errno=True)
    _mmap_libc.mmap.restype = ctypes.c_void_p
    _mmap_libc.mmap.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_long,
    ]
    _mmap_libc.munmap.restype = ctypes.c_int
    _mmap_libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    _mmap_libc.memcpy.restype = ctypes.c_void_p
    _mmap_libc.memcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    _PAGE = int(os.sysconf("SC_PAGE_SIZE"))

# Deploy-baked selector, read once at child launch.  OFF reproduces the exact
# per-fill open/preadv/close lifecycle; ON keeps a lazy positioned-FD cache
# keyed by normalized (path, producer_id).
persistent_fds = (
    str(os.environ.get("COMFYMODAL_GOLDEN_IO_PROCESS_V2_PERSISTENT_FDS") or "")
    .strip().lower() in ("1", "true", "yes", "on")
)

# Deploy-baked diagnostic selector, read once at child launch.  OFF reproduces
# the exact direct file -> leased SHM slot write.  ON stages each fill in one
# reusable private per-worker buffer and then copies into the leased slot.
private_split_io = (
    str(os.environ.get("COMFYMODAL_GOLDEN_C0_PRIVATE_SPLIT_IO") or "")
    .strip().lower() in ("1", "true", "yes", "on")
)

# Deploy-baked distinct treatment selector, read once at launch.  ON replaces
# only the byte producer: a direct Volume V1 VolumeGetFile2 ranged read streamed
# as concurrent 8 MiB blocks into the leased SHM slot (or private split buffer).
# There is deliberately no preadv fallback when ON.
source_volume_v1 = (
    str(os.environ.get("COMFYMODAL_GOLDEN_C0_SOURCE_VOLUME_V1") or "")
    .strip().lower() in ("1", "true", "yes", "on")
)
volume_id = str(os.environ.get("COMFYMODAL_C0_SOURCE_VOLUME_ID") or "").strip()
volume_name = str(os.environ.get("COMFYMODAL_C0_SOURCE_VOLUME_NAME") or "").strip()
volume_mount = (
    str(os.environ.get("COMFYMODAL_C0_SOURCE_VOLUME_MOUNT") or "/root/models").strip()
    or "/root/models"
)
volume_block_concurrency = 8
c0_volume = None
_volume_stub = None
_volume_session = None
_volume_session_source = None
_volume_setup_error = None
_volume_loop_holder = {}
_volume_ready = threading.Event()

# Deploy-baked forensic child-only VizTracer selector, read once at launch.
# OFF leaves this child exactly uninstrumented.  ON traces function-level
# source worker / writer / positioned-read boundaries.  viztracer is imported
# lazily and only here; the C0 child must remain CUDA-sterile (no torch import).
child_viztracer_enabled = (
    str(os.environ.get("COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER") or "")
    .strip().lower() in ("1", "true", "yes", "on")
)
child_viztracer_path = str(
    os.environ.get("COMFYMODAL_C0_CHILD_VIZTRACER_PATH")
    or "/tmp/comfymodal_c0_child_viztracer.json"
)
child_viztracer_status_path = child_viztracer_path + ".status.json"
_child_tracer = None
_child_viztracer_status = {
    "op": "child_viztracer_status",
    "enabled": bool(child_viztracer_enabled),
    "status": "disabled" if not child_viztracer_enabled else "pending",
    "path": child_viztracer_path,
    "pid": os.getpid(),
}

# ── diagnostic clustered preadv sickness (selector ON only) ──────────────────
# Distinct default-OFF diagnostic profile.  OFF leaves every production read,
# descriptor, slot, and reply byte-for-byte unchanged.  ON adds an outstanding
# read registry, an independent watchdog, a passive snapshot, and a bounded
# active probe matrix.  stdlib only: no signals, no torch/CUDA, no new process.
preadv_sickness_diag = (
    str(os.environ.get("COMFYMODAL_GOLDEN_C0_PREADV_SICKNESS_DIAG") or "")
    .strip().lower() in ("1", "true", "yes", "on")
)
sickness_profile_hash = str(
    os.environ.get("COMFYMODAL_C0_PREADV_SICKNESS_PROFILE_HASH") or ""
)
sickness_config_hash = str(
    os.environ.get("COMFYMODAL_C0_PREADV_SICKNESS_CONFIG_HASH") or ""
)
sickness_invocation_id = str(
    os.environ.get("COMFYMODAL_C0_PREADV_SICKNESS_INVOCATION_ID") or ""
)
SICKNESS_SCHEMA = "comfymodal.c0.preadv_sickness"
SICKNESS_VERSION = 1
SICKNESS_TRIPWIRE_NS = 500000000
SICKNESS_SIZE_LADDER = (65536, 1048576, 16777216)
SICKNESS_MAX_PROBES_PER_REQUEST = 48
SICKNESS_MAX_PROBES_TOTAL = 256
SICKNESS_HEARTBEAT_INTERVAL_S = 0.02
SICKNESS_HEARTBEAT_HISTORY = 256
SICKNESS_WATCHDOG_POLL_S = 0.01
# Bounded join for the independent tripwire handler at teardown.  The handler
# runs on a daemon thread, so a stuck probe matrix can never delay child exit
# or a production worker's completion.
SICKNESS_DIAG_JOIN_S = 5.0
SICKNESS_LOCAL_CONTROL_PATH = "/tmp/comfymodal_c0_sickness_local_%d.bin" % os.getpid()
sickness_control_manifest = None
if preadv_sickness_diag:
    try:
        _manifest_raw = str(
            os.environ.get("COMFYMODAL_C0_PREADV_SICKNESS_CONTROLS") or ""
        )
        if _manifest_raw:
            sickness_control_manifest = json.loads(_manifest_raw)
    except Exception:
        sickness_control_manifest = None
_sickness_lock = threading.Lock()
_sickness_outstanding = {}
_sickness_sequence = 0
_sickness_fired = {}
_sickness_events = []
_sickness_completed_reads = []
_sickness_production_durations_ns = []
_sickness_probe_total = 0
_sickness_reply_blocks = {}
_sickness_reply_events = {}
# Independent tripwire handler.  The watchdog only detects, marks fired, and
# enqueues; a single daemon worker runs the passive+active matrix so a slow
# matrix can never delay detection of the next outstanding read.
_sickness_trip_queue = queue.Queue()
_sickness_diag_thread = None
_sickness_errors = []
_sickness_stop = threading.Event()
_sickness_heartbeat_stop = threading.Event()
_sickness_heartbeat = {
    "thread": "c0-sickness-heartbeat",
    "started_mono_ns": None,
    "count": 0,
    "history": [],
    "interval_s": SICKNESS_HEARTBEAT_INTERVAL_S,
    "max_gap_ms": None,
    "last_mono_ns": None,
}
_sickness_local_control_ready = False

shm = shared_memory.SharedMemory(name=shm_name)
buf = shm.buf
# The parent owns this POSIX segment.  multiprocessing registers every
# attachment with a process-local resource tracker; left registered, this
# child's tracker would unlink the parent's segment when the child exits and
# the parent's later release would fail closed.  Detach our registration so
# only the creating parent destroys the mapping.
try:
    from multiprocessing import resource_tracker
    resource_tracker.unregister(shm.name, "shared_memory")
except Exception:
    pass
out_q = queue.Queue(maxsize=max(16, slot_count * 8))


def _emit(obj):
    try:
        out_q.put(obj)
    except Exception:
        pass


def _read_runtime_text(path, limit=240):
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read(int(limit)).strip()
    except Exception:
        return None


def _runtime_markers():
    # Cheap child-side platform/runtime markers for split-IO evidence.  Never
    # raises; missing values stay None.  The existing 512 MiB C0 mapping is the
    # same-container reproduction, so these markers (not a separate service)
    # are how a missing upstream gVisor fix becomes visible in evidence.
    markers = {
        "platform_release": None,
        "platform_version": None,
        "proc_version": None,
        "gvisor_marker": None,
        "shmem_enabled": None,
        "shmem_enabled_path": "/sys/kernel/mm/transparent_hugepage/shmem_enabled",
    }
    try:
        import platform as _platform
        markers["platform_release"] = str(_platform.release())
        markers["platform_version"] = str(_platform.version())
    except Exception:
        pass
    proc_version = _read_runtime_text("/proc/version")
    markers["proc_version"] = proc_version
    haystack = (proc_version or "").lower()
    for needle in ("gvisor", "runsc"):
        if needle in haystack:
            markers["gvisor_marker"] = needle
            break
    markers["shmem_enabled"] = _read_runtime_text(markers["shmem_enabled_path"])
    return markers


def _child_mount_identity(paths):
    # One-time child-side view of the same mountinfo the parent filters.  Raw
    # fields only (no escape decoding); the parent's decoder is authoritative.
    # Never raises; unreadable mountinfo is an explicit unsupported record.
    out = {"supported": False, "error": None, "paths": {}, "entries": []}
    try:
        with open("/proc/self/mountinfo", "r", errors="replace") as handle:
            text = handle.read()
    except Exception as exc:
        out["error"] = ("%s:%s" % (type(exc).__name__, exc))[:160]
        return out
    entries = []
    for line in text.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        lparts = left.split()
        rparts = right.split()
        if len(lparts) < 6 or len(rparts) < 2:
            continue
        entries.append({
            "mount_id": lparts[0],
            "parent_id": lparts[1],
            "major_minor": lparts[2],
            "root": lparts[3],
            "mount_point": lparts[4],
            "mount_options": lparts[5],
            "optional_fields": lparts[6:],
            "fstype": rparts[0],
            "source": rparts[1],
            "super_options": rparts[2:],
        })
    out["supported"] = True
    out["entries"] = entries
    for path in paths:
        matches = [
            entry for entry in entries
            if entry["mount_point"] == path
            or str(path).startswith(entry["mount_point"].rstrip("/") + "/")
        ]
        out["paths"][str(path)] = (
            max(matches, key=lambda entry: len(entry["mount_point"]))
            if matches else None
        )
    return out


def _tracer_enable_thread():
    # VizTracer start() traces the control/main thread; every thread that owns
    # source-read or reply-write work must opt in explicitly so worker and
    # writer boundaries are captured.
    tracer = _child_tracer
    if tracer is None:
        return
    try:
        hook = getattr(tracer, "enable_thread_tracing", None)
        if callable(hook):
            hook()
    except Exception:
        pass


def _write_child_viztracer_status():
    if not child_viztracer_enabled:
        return
    try:
        with open(child_viztracer_status_path, "w") as handle:
            json.dump(_child_viztracer_status, handle, sort_keys=True)
    except Exception:
        pass


def _start_child_viztracer():
    global _child_tracer
    if not child_viztracer_enabled:
        return
    # Start from a clean deterministic path so a stale prior artifact can never
    # be mistaken for this child's capture.
    for stale in (child_viztracer_path, child_viztracer_status_path):
        try:
            if os.path.exists(stale):
                os.remove(stale)
        except Exception:
            pass
    try:
        entries = int(os.environ.get("COMFYMODAL_V2_FULL_TRACE_ENTRIES") or 8000000)
    except Exception:
        entries = 8000000
    if entries <= 0:
        entries = 8000000
    try:
        # Lazy, child-only import: never torch/CUDA.  No include-file filter is
        # applied so full-function tracing covers this child's own source seam.
        from viztracer import VizTracer
        tracer = VizTracer(
            tracer_entries=entries,
            max_stack_depth=64,
            output_file=child_viztracer_path,
            ignore_c_function=False,
            log_gc=True,
            log_async=True,
            file_info=True,
            register_global=True,
            trace_self=False,
            minimize_memory=True,
            log_func_args=False,
            log_func_retval=False,
            log_print=False,
            pid_suffix=False,
        )
        tracer.start()
        _child_tracer = tracer
        _child_viztracer_status.update({
            "status": "started",
            "tracer_entries": int(entries),
            "max_stack_depth": 64,
            "viztracer_version": str(
                getattr(VizTracer, "__version__", None)
                or getattr(VizTracer, "VERSION", None)
                or "unknown"
            ),
        })
    except ImportError as exc:
        _child_viztracer_status.update({
            "status": "unavailable",
            "error": ("%s:%s" % (type(exc).__name__, exc))[:240],
        })
    except Exception as exc:
        _child_viztracer_status.update({
            "status": "start_error",
            "error": ("%s:%s" % (type(exc).__name__, exc))[:240],
        })
    _write_child_viztracer_status()


def _stop_child_viztracer():
    global _child_tracer
    tracer = _child_tracer
    if tracer is None:
        # Flag ON but no live tracer: persist and emit the explicit failure
        # status so the parent sees missing capture, never silence.
        _write_child_viztracer_status()
        try:
            sys.stderr.write(json.dumps(_child_viztracer_status, sort_keys=True) + "\n")
            sys.stderr.flush()
        except Exception:
            pass
        return
    try:
        try:
            tracer.stop()
        finally:
            tracer.save(child_viztracer_path)
        _child_viztracer_status["status"] = "saved"
    except Exception as exc:
        _child_viztracer_status.update({
            "status": "save_error",
            "error": ("%s:%s" % (type(exc).__name__, exc))[:240],
        })
    finally:
        _child_tracer = None
    try:
        import hashlib as _hashlib
        _child_viztracer_status["trace_bytes"] = int(os.path.getsize(child_viztracer_path))
        _digest = _hashlib.sha256()
        with open(child_viztracer_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                _digest.update(chunk)
        _child_viztracer_status["trace_sha256"] = _digest.hexdigest()
    except Exception as exc:
        if _child_viztracer_status.get("status") == "saved":
            _child_viztracer_status["status"] = "save_error"
            _child_viztracer_status["error"] = ("%s:%s" % (type(exc).__name__, exc))[:240]
    _write_child_viztracer_status()
    try:
        sys.stderr.write(json.dumps(_child_viztracer_status, sort_keys=True) + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _writer():
    # Sole owner of stdout: read workers never touch the control IPC.
    _tracer_enable_thread()
    while True:
        item = out_q.get()
        if item is None:
            return
        try:
            sys.stdout.write(json.dumps(item) + "\n")
            sys.stdout.flush()
        except Exception:
            return


def _pread_into(fd, view, offset):
    if hasattr(os, "preadv"):
        return int(os.preadv(fd, [view], offset))
    if hasattr(os, "pread"):
        data = os.pread(fd, len(view), offset)
        view[: len(data)] = data
        return len(data)
    raise RuntimeError("positioned_read_unsupported")


def _volume_load_transport_module():
    # Load the transport module by explicit path: never a package import that
    # could pull torch into the CUDA-sterile child.  Absent runtime dir / module
    # is a fail-closed setup error, never a silent preadv fallback.
    runtime_dir = str(os.environ.get("COMFYMODAL_C0_RUNTIME_DIR") or "")
    if not runtime_dir:
        raise RuntimeError("c0_runtime_dir_missing")
    module_path = os.path.join(runtime_dir, "c0_volume_transport_v1.py")
    spec = importlib.util.spec_from_file_location(
        "comfymodal_c0_volume_v1", module_path
    )
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass decoration can resolve the module via
    # sys.modules[cls.__module__]; module_from_spec alone leaves it absent and
    # dataclass processing raises AttributeError on NoneType.__dict__.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Only unwind our own registration; a pre-existing entry (should not
        # happen for a unique name) is left untouched.
        if sys.modules.get(spec.name) is module:
            del sys.modules[spec.name]
        raise
    return module


async def _volume_setup_async():
    global _volume_stub, _volume_session, _volume_session_source
    from modal.volume import _Volume
    volume = _Volume.from_id(volume_id)
    await volume.hydrate()
    _volume_stub = volume._client.stub
    session, source, _closable = await c0_volume.resolve_http_session()
    _volume_session = session
    _volume_session_source = source


def _volume_loop_main():
    global _volume_setup_error
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _volume_loop_holder["loop"] = loop
    try:
        loop.run_until_complete(_volume_setup_async())
    except BaseException as exc:
        _volume_setup_error = ("%s:%s" % (type(exc).__name__, exc))[:240]
        _volume_ready.set()
        try:
            loop.close()
        except Exception:
            pass
        return
    _volume_ready.set()
    try:
        loop.run_forever()
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass


def _start_volume_transport():
    if not source_volume_v1:
        return
    if c0_volume is None:
        raise RuntimeError("c0_volume_module_unavailable")
    if not volume_id:
        raise RuntimeError("c0_source_volume_id_missing")
    _volume_ready.clear()
    thread = threading.Thread(
        target=_volume_loop_main, name="c0-volume-loop", daemon=True
    )
    thread.start()
    if not _volume_ready.wait(timeout=180.0):
        raise RuntimeError("c0_volume_transport_setup_timeout")
    if _volume_setup_error is not None:
        raise RuntimeError("c0_volume_transport_setup_failed:" + _volume_setup_error)


def _volume_evidence():
    return {
        "enabled": bool(source_volume_v1),
        "volume_name": volume_name,
        "volume_id": volume_id,
        "mount": volume_mount,
        "transport_ready": bool(
            _volume_stub is not None and _volume_session is not None
        ),
        "session_source": _volume_session_source,
        "setup_error": _volume_setup_error,
        "block_concurrency": int(volume_block_concurrency),
        "cuda_initialized": False,
        "torch_imported": bool("torch" in sys.modules),
    }


def _volume_fill_blocking(req, read_target, offset, length):
    loop = _volume_loop_holder.get("loop")
    if loop is None:
        raise RuntimeError("c0_volume_loop_not_running")
    relative = c0_volume.volume_relative_path(str(req["path"]), volume_mount)
    future = asyncio.run_coroutine_threadsafe(
        c0_volume.fetch_volume_range(
            stub=_volume_stub,
            session=_volume_session,
            volume_id=volume_id,
            path=relative,
            start=int(offset),
            length=int(length),
            target=read_target,
            concurrency=int(volume_block_concurrency),
        ),
        loop,
    )
    try:
        return future.result(timeout=900.0)
    except BaseException:
        # Timeout or transport failure: cancel the pending extent so it cannot
        # keep writing the leased slot after this fill has failed closed.
        future.cancel()
        raise


def _read_schedstat(native_tid):
    # /proc/self/task/<tid>/schedstat is [run_ns, wait_ns, timeslices] on Linux.
    # Missing procfs (non-Linux, restricted container) or an unknown tid is
    # None; probing must never abort the fill.
    try:
        with open("/proc/self/task/%s/schedstat" % int(native_tid), "r") as handle:
            return [int(part) for part in handle.read().split()]
    except Exception:
        return None


def _syscall_probe(native_tid):
    # Cheap passive observation captured outside the measured preadv interval.
    # Every field is independently fail-open: a missing clock, rusage source,
    # or procfs entry stays None instead of raising into the fill path.
    #
    # ``rusage`` is recorded ONLY from a successful per-thread RUSAGE_THREAD
    # call.  There is deliberately no RUSAGE_SELF fallback: process-wide
    # counters must never be relabelled as thread-bounded.  When the scope is
    # unavailable the value is None and ``rusage_scope`` stays None, so the
    # evidence is explicit rather than silently process-wide.
    probe = {
        "wall_ns": None,
        "thread_cpu_ns": None,
        "rusage": None,
        "rusage_scope": None,
        "schedstat": None,
    }
    try:
        probe["wall_ns"] = int(time.monotonic_ns())
    except Exception:
        pass
    try:
        probe["thread_cpu_ns"] = int(time.thread_time_ns())
    except Exception:
        pass
    try:
        # Deferred so a platform without ``resource`` (or without the
        # per-thread scope) degrades to None rather than breaking the child
        # import surface.
        import resource as _resource
        rusage_thread = getattr(_resource, "RUSAGE_THREAD", None)
        if rusage_thread is not None:
            usage = _resource.getrusage(rusage_thread)
            probe["rusage"] = {
                "ru_minflt": int(usage.ru_minflt),
                "ru_majflt": int(usage.ru_majflt),
                "ru_nvcsw": int(usage.ru_nvcsw),
                "ru_nivcsw": int(usage.ru_nivcsw),
            }
            probe["rusage_scope"] = "thread"
    except Exception:
        probe["rusage"] = None
        probe["rusage_scope"] = None
    probe["schedstat"] = _read_schedstat(native_tid)
    return probe


def _probe_delta(before, after):
    # Element-wise delta for two rusage dicts or two schedstat lists.  Either
    # observation missing yields None, never a fabricated value.
    if before is None or after is None:
        return None
    try:
        if isinstance(before, dict) and isinstance(after, dict):
            return {
                key: int(after.get(key, 0)) - int(before.get(key, 0))
                for key in sorted(set(before) | set(after))
            }
        if isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
            count = min(len(before), len(after))
            return [int(after[index]) - int(before[index]) for index in range(count)]
    except Exception:
        return None
    return None


# ── bounded child post-hoc fallback for slow reads (stdlib only) ─────────────
# Only used when a single positioned read actually ran longer than the slow
# threshold.  It captures this child's own task/proc state *after* the measured
# syscall interval, so it cannot perturb the read timing.  Bounded and counted;
# every read is fail-open and missing files stay None, never zero.
_child_fallback_records = []
_child_fallback_dropped = 0
_child_fallback_cap = 32
_child_fallback_threshold_ns = 100000000


def _read_child_text(path, limit=16384):
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read(int(limit))
    except Exception:
        return None


def _read_child_keyvals(path, limit=16384):
    text = _read_child_text(path, limit)
    if text is None:
        return {"available": False, "path": path, "error": "unreadable"}
    out = {"available": True, "path": path}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        token = value.strip()
        if key and token.lstrip("-").isdigit():
            out[key] = int(token)
        elif key and token:
            out[key] = token
    return out


def _child_task_stat_fields(native_tid):
    text = None
    if native_tid is not None:
        text = _read_child_text("/proc/self/task/%s/stat" % int(native_tid), 4096)
    if text is None:
        text = _read_child_text("/proc/self/stat", 4096)
    if text is None:
        return {"available": False, "error": "stat_unreadable"}
    try:
        rparen = text.rfind(")")
        rest = text[rparen + 1:].split()
    except Exception:
        return {"available": False, "error": "stat_parse"}

    def _at(index):
        if index >= len(rest):
            return None
        token = rest[index].lstrip("-")
        return int(rest[index]) if token.isdigit() else None

    return {
        "available": True,
        "state": rest[0] if len(rest) > 0 else None,
        "minflt": _at(7),
        "majflt": _at(9),
        "utime": _at(11),
        "stime": _at(12),
        "processor": _at(36),
        "policy": _at(38),
        "delayacct_blkio_ticks": _at(39),
    }


def _child_self_snapshot(native_tid):
    snapshot = {
        "origin": "child-fallback",
        "wall_ns": None,
        "worker_native_tid": native_tid,
    }
    try:
        snapshot["wall_ns"] = int(time.monotonic_ns())
    except Exception:
        pass
    snapshot["task_stat"] = _child_task_stat_fields(native_tid)
    snapshot["status"] = _read_child_keyvals("/proc/self/status", 32768)
    base = "/proc/self/task/%s" % int(native_tid) if native_tid is not None else "/proc/self"
    snapshot["wchan"] = _read_child_text(base + "/wchan", 256)
    snapshot["syscall"] = _read_child_text(base + "/syscall", 256)
    snapshot["schedstat"] = _read_child_text(base + "/schedstat", 256)
    snapshot["io"] = _read_child_keyvals(base + "/io", 4096)
    stack = _read_child_text(base + "/stack", 1024)
    snapshot["stack"] = (stack or "")[:1024] if stack is not None else None
    snapshot["cgroup"] = _read_child_text("/proc/self/cgroup", 1024)
    return snapshot


# ── diagnostic clustered preadv sickness helpers (selector ON only) ──────────
def _sickness_mono_ns():
    try:
        return int(time.monotonic_ns())
    except Exception:
        return None


def _sickness_wall_ns():
    try:
        return int(time.time_ns())
    except Exception:
        return None


def _sickness_fd_identity(fd):
    try:
        st = os.fstat(int(fd))
        return {
            "available": True,
            "st_dev": int(st.st_dev),
            "st_ino": int(st.st_ino),
            "st_mode": int(st.st_mode),
            "st_size": int(st.st_size),
            "st_nlink": int(st.st_nlink),
            "st_mtime_ns": int(st.st_mtime_ns),
        }
    except Exception as exc:
        return {"available": False, "error": ("%s:%s" % (type(exc).__name__, exc))[:160]}


def _sickness_view_address(view):
    try:
        import ctypes as _ctypes
        return int(_ctypes.addressof(_ctypes.c_char.from_buffer(view)))
    except Exception:
        return None


def _sickness_build_record(context, fd, view, offset):
    try:
        length = int(len(view))
    except Exception:
        length = None
    return {
        "sequence": 0,
        "role": context.get("role"),
        "path": context.get("path"),
        "worker_name": context.get("worker_name"),
        "worker_index": context.get("worker_index"),
        "worker_ident": context.get("worker_ident"),
        "worker_native_tid": context.get("worker_native_tid"),
        "fd_number": int(fd) if fd is not None else None,
        "fd_identity": (
            _sickness_fd_identity(fd)
            if fd is not None
            else {"available": False, "error": "fd_none"}
        ),
        "offset": int(offset),
        "length": length,
        "iovec_geometry": {"count": 1, "lengths": [length]},
        "destination_address": _sickness_view_address(view),
        "slot_index": context.get("slot_index"),
        "destination_offset": context.get("destination_offset"),
        "enter_mono_ns": _sickness_mono_ns(),
        "enter_wall_ns": _sickness_wall_ns(),
        "request_id": context.get("request_id"),
        "record_id": context.get("record_id"),
        "fill_index": context.get("fill_index"),
        "age_ms": 0.0,
    }


def _sickness_register_record(record):
    global _sickness_sequence
    if not preadv_sickness_diag:
        return None
    with _sickness_lock:
        _sickness_sequence += 1
        record["sequence"] = int(_sickness_sequence)
        _sickness_outstanding[int(_sickness_sequence)] = record
    return int(record["sequence"])


def _sickness_unregister_record(sequence):
    if sequence is None:
        return None
    with _sickness_lock:
        return _sickness_outstanding.pop(int(sequence), None)


def _sickness_outstanding_snapshot(now_mono_ns=None):
    with _sickness_lock:
        records = [dict(record) for record in _sickness_outstanding.values()]
    now = _sickness_mono_ns() if now_mono_ns is None else int(now_mono_ns)
    for record in records:
        enter = record.get("enter_mono_ns")
        if now is not None and enter is not None:
            age_ns = max(0, now - int(enter))
            record["age_ns"] = int(age_ns)
            record["age_ms"] = round(age_ns / 1e6, 3)
        else:
            record["age_ns"] = None
            record["age_ms"] = None
    return records


def _sickness_due_records(now_mono_ns, threshold_ns):
    due = []
    for record in _sickness_outstanding_snapshot(now_mono_ns):
        age_ns = record.get("age_ns")
        if age_ns is not None and int(age_ns) >= int(threshold_ns):
            due.append(record)
    return due


def _sickness_request_key(record):
    request_id = record.get("request_id")
    if request_id is not None:
        return "req:%s" % request_id
    return "seq:%s" % record.get("sequence")


def _sickness_mark_fired(key):
    with _sickness_lock:
        if key in _sickness_fired:
            return False
        _sickness_fired[key] = True
    return True


def _sickness_trigger_outstanding(sequence):
    if sequence is None:
        return False
    with _sickness_lock:
        return int(sequence) in _sickness_outstanding


def _sickness_begin_read(context, fd, view, offset):
    try:
        if not preadv_sickness_diag:
            return None
        record = _sickness_build_record(context, fd, view, offset)
        return _sickness_register_record(record)
    except BaseException:
        return None


def _sickness_end_read(sequence, returned, error):
    try:
        record = _sickness_unregister_record(sequence)
    except BaseException:
        return
    if record is None:
        return
    end_ns = _sickness_mono_ns()
    enter_ns = record.get("enter_mono_ns")
    duration_ns = (
        max(0, int(end_ns) - int(enter_ns))
        if end_ns is not None and enter_ns is not None
        else None
    )
    record["exit_mono_ns"] = end_ns
    record["duration_ms"] = (
        round(duration_ns / 1e6, 6) if duration_ns is not None else None
    )
    record["returned_bytes"] = int(returned) if returned is not None else None
    if error:
        record["error"] = str(error)[:200]
    try:
        if duration_ns is not None:
            _sickness_production_durations_ns.append(int(duration_ns))
            del _sickness_production_durations_ns[:-256]
        _sickness_completed_reads.append({
            "sequence": record.get("sequence"),
            "role": record.get("role"),
            "path": record.get("path"),
            "offset": record.get("offset"),
            "length": record.get("length"),
            "worker_native_tid": record.get("worker_native_tid"),
            "duration_ms": record.get("duration_ms"),
            "enter_mono_ns": enter_ns,
            "exit_mono_ns": end_ns,
            "returned_bytes": record.get("returned_bytes"),
            "error": record.get("error"),
        })
        del _sickness_completed_reads[:-256]
    except Exception:
        pass


def _sickness_duration_summary(durations_ns=None):
    values = [
        int(value)
        for value in (
            _sickness_production_durations_ns if durations_ns is None else durations_ns
        )
    ]
    if not values:
        return {"count": 0, "p50_ms": None, "p90_ms": None, "max_ms": None}
    ordered = sorted(values)

    def _pct(fraction):
        index = int(round(fraction * (len(ordered) - 1)))
        return round(ordered[max(0, min(index, len(ordered) - 1))] / 1e6, 4)

    return {
        "count": len(ordered),
        "p50_ms": _pct(0.5),
        "p90_ms": _pct(0.9),
        "max_ms": _pct(1.0),
    }


def _sickness_heartbeat_loop():
    _sickness_heartbeat["thread_alive"] = True
    _sickness_heartbeat["started_mono_ns"] = _sickness_mono_ns()
    last = None
    while not _sickness_heartbeat_stop.is_set():
        now = _sickness_mono_ns()
        if now is not None:
            gap = None if last is None else max(0, now - int(last))
            _sickness_heartbeat["count"] = int(_sickness_heartbeat.get("count") or 0) + 1
            _sickness_heartbeat["last_mono_ns"] = now
            if gap is not None and (
                _sickness_heartbeat.get("max_gap_ms") is None
                or gap / 1e6 > float(_sickness_heartbeat["max_gap_ms"])
            ):
                _sickness_heartbeat["max_gap_ms"] = round(gap / 1e6, 3)
            _sickness_heartbeat["history"].append({
                "mono_ns": now,
                "wall_ns": _sickness_wall_ns(),
                "gap_ms": round(gap / 1e6, 3) if gap is not None else None,
            })
            del _sickness_heartbeat["history"][:-SICKNESS_HEARTBEAT_HISTORY]
            last = now
        _sickness_heartbeat_stop.wait(SICKNESS_HEARTBEAT_INTERVAL_S)
    _sickness_heartbeat["thread_alive"] = False


def _start_sickness_heartbeat():
    if not preadv_sickness_diag:
        return
    thread = threading.Thread(
        target=_sickness_heartbeat_loop, name="c0-sickness-heartbeat", daemon=True
    )
    thread.start()


def _sickness_heartbeat_snapshot():
    return {
        "thread": _sickness_heartbeat.get("thread"),
        "thread_alive": bool(_sickness_heartbeat.get("thread_alive")),
        "started_mono_ns": _sickness_heartbeat.get("started_mono_ns"),
        "count": int(_sickness_heartbeat.get("count") or 0),
        "interval_s": _sickness_heartbeat.get("interval_s"),
        "max_gap_ms": _sickness_heartbeat.get("max_gap_ms"),
        "last_mono_ns": _sickness_heartbeat.get("last_mono_ns"),
        "history": [dict(item) for item in _sickness_heartbeat.get("history", [])],
    }


def _sickness_cgroup_snapshot():
    out = {
        "paths": {},
        "availability": {},
        "cpu": None,
        "memory": None,
        "io": None,
        "pressure": {},
    }
    for label, candidates in (
        ("cpu", ("/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/cpu/cpu.stat")),
        ("memory", (
            "/sys/fs/cgroup/memory.current",
            "/sys/fs/cgroup/memory/memory.usage_in_bytes",
        )),
        ("io", (
            "/sys/fs/cgroup/io.stat",
            "/sys/fs/cgroup/blkio/blkio.throttle.io_service_bytes",
        )),
    ):
        data = {"available": False, "error": "not_probed"}
        used_path = None
        for path in candidates:
            data = _read_child_keyvals(path)
            used_path = path
            if data.get("available"):
                break
        out["paths"][label] = used_path
        out["availability"][label] = bool(data.get("available"))
        out[label] = data
    for label, candidates in (
        ("cpu", ("/sys/fs/cgroup/cpu.pressure", "/sys/fs/cgroup/cpu/cpu.pressure")),
        ("memory", (
            "/sys/fs/cgroup/memory.pressure",
            "/sys/fs/cgroup/memory/memory.pressure",
        )),
        ("io", ("/sys/fs/cgroup/io.pressure", "/sys/fs/cgroup/io.pressure")),
    ):
        text = None
        used_path = None
        for path in candidates:
            text = _read_child_text(path)
            used_path = path
            if text is not None:
                break
        out["pressure"][label] = {
            "path": used_path,
            "available": text is not None,
            "raw": text,
        }
    return out


def _sickness_passive_snapshot(trigger):
    now_mono = _sickness_mono_ns()
    now_wall = _sickness_wall_ns()
    pid = os.getpid()
    tid = trigger.get("worker_native_tid")
    base = "/proc/%s" % pid
    task_base = "%s/task/%s" % (base, int(tid)) if tid is not None else base
    cgroup = _sickness_cgroup_snapshot()
    proc_status = _read_child_keyvals(base + "/status", 32768)
    proc_io = _read_child_keyvals(base + "/io", 8192)
    unavailable = []
    if tid is None:
        unavailable.append("worker_native_tid")
    worker_wchan = _read_child_text(task_base + "/wchan", 256)
    if worker_wchan is None:
        unavailable.append("worker_wchan")
    if not proc_status.get("available"):
        unavailable.append("proc_status")
    if not proc_io.get("available"):
        unavailable.append("proc_io")
    return {
        "schema": "comfymodal.c0.preadv_sickness.passive",
        "version": SICKNESS_VERSION,
        "mono_ns": now_mono,
        "wall_ns": now_wall,
        "pid": pid,
        "trigger": {
            "sequence": trigger.get("sequence"),
            "role": trigger.get("role"),
            "path": trigger.get("path"),
            "offset": trigger.get("offset"),
            "length": trigger.get("length"),
            "worker_native_tid": tid,
            "request_id": trigger.get("request_id"),
            "record_id": trigger.get("record_id"),
            "fill_index": trigger.get("fill_index"),
            "fd_identity": trigger.get("fd_identity"),
            "destination_address": trigger.get("destination_address"),
            "age_ms": trigger.get("age_ms"),
        },
        "outstanding_reads": _sickness_outstanding_snapshot(now_mono),
        "outstanding_count": len(_sickness_outstanding_snapshot(now_mono)),
        "worker": {
            "tid": tid,
            "blocked_state": _read_child_text(task_base + "/status", 4096),
            "wchan": worker_wchan,
            "syscall": _read_child_text(task_base + "/syscall", 256),
            "schedstat": _read_child_text(task_base + "/schedstat", 256),
            "stat": _child_task_stat_fields(tid),
            "io": _read_child_keyvals(task_base + "/io", 4096),
            "stack": _read_child_text(task_base + "/stack", 1024),
        },
        "proc": {
            "status": proc_status,
            "stat": _child_task_stat_fields(None),
            "io": proc_io,
            "statm": _read_child_text(base + "/statm", 512),
        },
        "cgroup": cgroup,
        "fd": trigger.get("fd_identity"),
        "path": trigger.get("path"),
        "stage": {
            "role": trigger.get("role"),
            "slot_index": trigger.get("slot_index"),
            "destination_offset": trigger.get("destination_offset"),
            "request_id": trigger.get("request_id"),
            "record_id": trigger.get("record_id"),
            "fill_index": trigger.get("fill_index"),
        },
        "helper_heartbeat": _sickness_heartbeat_snapshot(),
        "prior_production_durations": _sickness_duration_summary(),
        "unavailable": unavailable,
        "availability": {
            "proc_status": bool(proc_status.get("available")),
            "proc_io": bool(proc_io.get("available")),
            "worker_task": tid is not None,
            "cgroup": cgroup.get("availability"),
        },
    }


def _sickness_annotate_probe(record, before, after):
    record["original_outstanding_before"] = bool(before)
    record["original_outstanding_after"] = bool(after)
    record["original_completed_during_probe"] = bool(before and not after)
    record["state_changed"] = bool(before != after)
    record["confounded"] = bool(before and not after)
    if record["confounded"]:
        record["state"] = "STATE_CHANGED/CONFOUNDED"
    return record


def _sickness_probe_base(spec):
    return {
        "label": spec.get("label"),
        "kind": spec.get("kind"),
        "path": spec.get("path"),
        "offset": spec.get("offset"),
        "length": spec.get("length"),
        "destination": spec.get("destination"),
        "fd_source": spec.get("fd_source"),
        "syscall": spec.get("syscall"),
        "production_shm_target": False,
        "manifest_metadata": spec.get("manifest_metadata"),
        "started_mono_ns": None,
        "ended_mono_ns": None,
        "started_wall_ns": None,
        "ended_wall_ns": None,
        "wall_ms": None,
        "bytes": None,
        "error": None,
        "status": "not_tested",
        "original_outstanding_before": None,
        "original_outstanding_after": None,
        "original_completed_during_probe": None,
        "state_changed": False,
        "confounded": False,
    }


def _sickness_probe_read(spec, trigger_sequence, control_fd):
    record = _sickness_probe_base(spec)
    before = _sickness_trigger_outstanding(trigger_sequence)
    t0 = _sickness_mono_ns()
    w0 = _sickness_wall_ns()
    try:
        path = str(spec.get("path") or "")
        if not path or not os.path.exists(path):
            record["error"] = "path_unavailable"
            record["status"] = "not_tested"
        else:
            length = max(1, int(spec.get("length") or 1))
            offset = max(0, int(spec.get("offset") or 0))
            dest = bytearray(length)
            if spec.get("fd_source") == "persistent":
                if control_fd is None:
                    record["error"] = "persistent_control_fd_unavailable"
                    record["status"] = "not_tested"
                else:
                    n = _pread_into(control_fd, memoryview(dest)[:length], offset)
                    record["bytes"] = int(n)
                    record["status"] = "ok"
            else:
                fd = os.open(path, os.O_RDONLY)
                try:
                    n = _pread_into(fd, memoryview(dest)[:length], offset)
                    record["bytes"] = int(n)
                    record["status"] = "ok"
                finally:
                    try:
                        os.close(fd)
                    except Exception:
                        pass
    except BaseException as exc:
        record["status"] = "error"
        record["error"] = ("%s:%s" % (type(exc).__name__, exc))[:200]
    finally:
        t1 = _sickness_mono_ns()
        w1 = _sickness_wall_ns()
        record["started_mono_ns"] = t0
        record["ended_mono_ns"] = t1
        record["started_wall_ns"] = w0
        record["ended_wall_ns"] = w1
        record["wall_ms"] = (
            round(max(0, t1 - t0) / 1e6, 6)
            if t0 is not None and t1 is not None
            else None
        )
        _sickness_annotate_probe(
            record, before, _sickness_trigger_outstanding(trigger_sequence)
        )
    return record


def _sickness_probe_stat_meta(spec, trigger_sequence):
    record = _sickness_probe_base(spec)
    before = _sickness_trigger_outstanding(trigger_sequence)
    t0 = _sickness_mono_ns()
    w0 = _sickness_wall_ns()
    try:
        path = str(spec.get("path") or "")
        if not path or not os.path.exists(path):
            record["error"] = "path_unavailable"
            record["status"] = "not_tested"
        else:
            stat_t0 = _sickness_mono_ns()
            st = os.stat(path)
            stat_t1 = _sickness_mono_ns()
            fd = os.open(path, os.O_RDONLY)
            open_t1 = _sickness_mono_ns()
            fst = os.fstat(fd)
            fstat_t1 = _sickness_mono_ns()
            os.close(fd)
            record["metadata"] = {
                "stat_size": int(st.st_size),
                "fstat_ino": int(fst.st_ino),
                "stat_ms": round((stat_t1 - stat_t0) / 1e6, 6),
                "open_ms": round((open_t1 - stat_t1) / 1e6, 6),
                "fstat_ms": round((fstat_t1 - open_t1) / 1e6, 6),
            }
            record["status"] = "ok"
    except BaseException as exc:
        record["status"] = "error"
        record["error"] = ("%s:%s" % (type(exc).__name__, exc))[:200]
    finally:
        t1 = _sickness_mono_ns()
        w1 = _sickness_wall_ns()
        record["started_mono_ns"] = t0
        record["ended_mono_ns"] = t1
        record["started_wall_ns"] = w0
        record["ended_wall_ns"] = w1
        record["wall_ms"] = (
            round(max(0, t1 - t0) / 1e6, 6)
            if t0 is not None and t1 is not None
            else None
        )
        _sickness_annotate_probe(
            record, before, _sickness_trigger_outstanding(trigger_sequence)
        )
    return record


def _sickness_probe_memcpy(spec, trigger_sequence):
    record = _sickness_probe_base(spec)
    before = _sickness_trigger_outstanding(trigger_sequence)
    t0 = _sickness_mono_ns()
    w0 = _sickness_wall_ns()
    try:
        length = max(1, int(spec.get("length") or 1))
        source = bytearray(length)
        destination = bytearray(length)
        destination[:] = source
        record["bytes"] = length
        record["status"] = "ok"
    except BaseException as exc:
        record["status"] = "error"
        record["error"] = ("%s:%s" % (type(exc).__name__, exc))[:200]
    finally:
        t1 = _sickness_mono_ns()
        w1 = _sickness_wall_ns()
        record["started_mono_ns"] = t0
        record["ended_mono_ns"] = t1
        record["started_wall_ns"] = w0
        record["ended_wall_ns"] = w1
        record["wall_ms"] = (
            round(max(0, t1 - t0) / 1e6, 6)
            if t0 is not None and t1 is not None
            else None
        )
        _sickness_annotate_probe(
            record, before, _sickness_trigger_outstanding(trigger_sequence)
        )
    return record


def _sickness_probe_local(spec, trigger_sequence):
    record = _sickness_probe_base(spec)
    before = _sickness_trigger_outstanding(trigger_sequence)
    t0 = _sickness_mono_ns()
    w0 = _sickness_wall_ns()
    try:
        length = max(1, int(spec.get("length") or 1))
        path = SICKNESS_LOCAL_CONTROL_PATH
        fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_RDWR, 0o600)
        try:
            payload = b"c0-preadv-sickness-local-control"
            written = 0
            while written < length:
                chunk = payload[: min(len(payload), length - written)]
                if not chunk:
                    break
                written += os.write(fd, chunk)
            n = _pread_into(fd, memoryview(bytearray(length)), 0)
            record["bytes"] = int(n)
            record["local_path"] = path
            record["status"] = "ok"
        finally:
            try:
                os.close(fd)
            except Exception:
                pass
    except BaseException as exc:
        record["status"] = "error"
        record["error"] = ("%s:%s" % (type(exc).__name__, exc))[:200]
    finally:
        t1 = _sickness_mono_ns()
        w1 = _sickness_wall_ns()
        record["started_mono_ns"] = t0
        record["ended_mono_ns"] = t1
        record["started_wall_ns"] = w0
        record["ended_wall_ns"] = w1
        record["wall_ms"] = (
            round(max(0, t1 - t0) / 1e6, 6)
            if t0 is not None and t1 is not None
            else None
        )
        _sickness_annotate_probe(
            record, before, _sickness_trigger_outstanding(trigger_sequence)
        )
    return record


def _sickness_manifest_fast_offset(manifest, role):
    files = (manifest or {}).get("files") or {}
    entry = files.get(role) or {}
    for control in entry.get("offsets") or []:
        if control.get("kind") == "historical_fast":
            return control
    return None


def _sickness_manifest_tail_offset(manifest, role):
    files = (manifest or {}).get("files") or {}
    entry = files.get(role) or {}
    for control in entry.get("offsets") or []:
        if control.get("kind") == "tail":
            return control
    return None


def _sickness_probe_plan(role, path, file_size, manifest):
    probe_bytes = 65536
    fast = _sickness_manifest_fast_offset(manifest, role)
    tail = _sickness_manifest_tail_offset(manifest, role)
    fast_offset = int(fast.get("offset")) if isinstance(fast, dict) else 0
    tail_offset = (
        int(tail.get("offset"))
        if isinstance(tail, dict)
        else max(0, int(file_size or 0) - probe_bytes)
    )
    plan = []

    def _add(label, kind, **kwargs):
        plan.append({
            "label": label,
            "kind": kind,
            "path": kwargs.get("path", path),
            "offset": int(kwargs.get("offset", fast_offset) or 0),
            "length": int(kwargs.get("length", probe_bytes) or probe_bytes),
            "fd_source": kwargs.get("fd_source"),
            "destination": kwargs.get("destination", "private_anonymous_bytearray"),
            "production_shm_target": False,
            "syscall": "os.preadv" if hasattr(os, "preadv") else "os.pread",
            "reason": kwargs.get("reason"),
            "manifest_metadata": kwargs.get("manifest_metadata"),
        })

    _add(
        "same_file_historically_fast_offset",
        "pread",
        offset=fast_offset,
        length=probe_bytes,
        fd_source="fresh",
        manifest_metadata=(fast or {}).get("historical"),
    )
    _add(
        "pathological_offset_small_request",
        "pread",
        offset=tail_offset,
        length=probe_bytes,
        fd_source="fresh",
        manifest_metadata=(tail or {}).get("historical"),
    )
    for size, suffix in zip(SICKNESS_SIZE_LADDER, ("64k", "1m", "16m")):
        _add(
            "size_ladder_%s" % suffix,
            "pread",
            offset=fast_offset,
            length=int(size),
            fd_source="fresh",
        )
    _add("fresh_fd", "pread", offset=fast_offset, length=probe_bytes, fd_source="fresh")
    _add(
        "persistent_fd",
        "pread",
        offset=fast_offset,
        length=probe_bytes,
        fd_source="persistent",
    )
    files = (manifest or {}).get("files") or {}
    other_role = None
    for candidate in sorted(files):
        if candidate != role:
            other_role = candidate
            break
    other_entry = files.get(other_role) if other_role else None
    other_path = (
        str((other_entry or {}).get("path") or "") if isinstance(other_entry, dict) else ""
    )
    other_fast = _sickness_manifest_fast_offset(manifest, other_role) if other_role else None
    if other_path and os.path.exists(other_path):
        _add(
            "different_model_file",
            "pread",
            path=other_path,
            offset=int((other_fast or {}).get("offset") or 0),
            length=probe_bytes,
            fd_source="fresh",
            manifest_metadata=(other_fast or {}).get("historical"),
        )
    else:
        _add("different_model_file", "none", reason="different_model_file_unavailable")
    _add("stat_open_fstat_metadata", "stat", offset=fast_offset)
    _add(
        "private_anonymous_destination",
        "pread",
        offset=fast_offset,
        length=probe_bytes,
        fd_source="fresh",
        destination="private_anonymous_bytearray",
    )
    _add(
        "separate_diagnostic_shm_destination",
        "none",
        reason="separate_shm_not_provisioned_by_parent",
    )
    _add("memory_only_memcpy_control", "memcpy", length=probe_bytes)
    _add("local_file_control", "local", length=probe_bytes)
    _add("helper_heartbeat_scheduler_liveness", "heartbeat")
    _add("convoy_qd_collapse_timeline", "timeline")
    return plan


def _sickness_run_probe_matrix(trigger, trigger_sequence, role, path, file_size):
    global _sickness_probe_total
    plan = _sickness_probe_plan(role, path, file_size, sickness_control_manifest)
    records = []
    control_fd = None
    if path and os.path.exists(path):
        try:
            control_fd = os.open(path, os.O_RDONLY)
        except Exception:
            control_fd = None
    try:
        for spec in plan:
            if (
                _sickness_probe_total >= SICKNESS_MAX_PROBES_TOTAL
                or len(records) >= SICKNESS_MAX_PROBES_PER_REQUEST
            ):
                record = _sickness_probe_base(spec)
                record["status"] = "not_tested"
                record["error"] = "budget_exhausted"
                records.append(record)
                continue
            kind = spec.get("kind")
            if kind == "pread":
                record = _sickness_probe_read(spec, trigger_sequence, control_fd)
            elif kind == "stat":
                record = _sickness_probe_stat_meta(spec, trigger_sequence)
            elif kind == "memcpy":
                record = _sickness_probe_memcpy(spec, trigger_sequence)
            elif kind == "local":
                record = _sickness_probe_local(spec, trigger_sequence)
            elif kind == "heartbeat":
                record = _sickness_probe_base(spec)
                before = _sickness_trigger_outstanding(trigger_sequence)
                record["heartbeat"] = _sickness_heartbeat_snapshot()
                record["status"] = "ok"
                _sickness_annotate_probe(
                    record, before, _sickness_trigger_outstanding(trigger_sequence)
                )
            elif kind == "timeline":
                # Convoy / QD-collapse timeline: a private outstanding-read
                # snapshot, never a production SHM write.
                record = _sickness_probe_base(spec)
                before = _sickness_trigger_outstanding(trigger_sequence)
                record["outstanding_snapshot"] = _sickness_outstanding_snapshot()
                record["status"] = "ok"
                _sickness_annotate_probe(
                    record, before, _sickness_trigger_outstanding(trigger_sequence)
                )
            else:
                record = _sickness_probe_base(spec)
                record["status"] = "not_tested"
                record["error"] = spec.get("reason") or "probe_unavailable"
            _sickness_probe_total += 1
            records.append(record)
    finally:
        if control_fd is not None:
            try:
                os.close(control_fd)
            except Exception:
                pass
    return records


def _sickness_probe_by_label(probes):
    return {
        str(probe.get("label")): probe
        for probe in probes
        if isinstance(probe, dict)
    }


def _sickness_probe_slow(probes, label, slow_ms=100.0):
    probe = probes.get(label)
    if not probe or probe.get("status") != "ok" or probe.get("wall_ms") is None:
        return None
    return float(probe["wall_ms"]) >= float(slow_ms)


def _sickness_hypotheses(probes, passive):
    by = _sickness_probe_by_label(probes)

    def _tri(label, slow_ms=100.0):
        probe = by.get(label)
        if probe is None:
            return "not_tested"
        # A probe that could not run (or errored) is explicitly not_tested;
        # a probe that ran but carries no usable timing is not_discriminated.
        if probe.get("status") in ("not_tested", "error"):
            return "not_tested"
        result = _sickness_probe_slow(by, label, slow_ms)
        if result is None:
            return "not_discriminated"
        return "consistent" if result else "inconsistent"

    heartbeat = (passive or {}).get("helper_heartbeat") or {}
    cgroup = (passive or {}).get("cgroup") or {}
    pressure = cgroup.get("pressure") or {}

    def _pressure_status(key):
        entry = pressure.get(key) or {}
        if not entry.get("available"):
            return "not_tested"
        for line in str(entry.get("raw") or "").splitlines():
            if "avg10=" in line:
                try:
                    value = float(line.split("avg10=", 1)[1].split()[0])
                except Exception:
                    continue
                return "consistent" if value > 0.0 else "inconsistent"
        return "not_discriminated"

    heartbeat_status = "not_tested"
    if "thread_alive" in heartbeat:
        gap = heartbeat.get("max_gap_ms")
        if gap is None:
            heartbeat_status = "not_discriminated"
        else:
            heartbeat_status = "consistent" if float(gap) >= 100.0 else "inconsistent"

    family_probe = {
        "same_file_fast_offset_slow": "same_file_historically_fast_offset",
        "pathological_offset_specific": "pathological_offset_small_request",
        "size_ladder_scaling": "size_ladder_16m",
        "fresh_fd_slow": "fresh_fd",
        "persistent_fd_slow": "persistent_fd",
        "different_model_file_slow": "different_model_file",
        "metadata_syscall_slow": "stat_open_fstat_metadata",
        "private_anonymous_destination_slow": "private_anonymous_destination",
        "separate_diagnostic_shm_destination_slow": "separate_diagnostic_shm_destination",
        "memory_only_copy_slow": "memory_only_memcpy_control",
        "local_file_control_slow": "local_file_control",
        "helper_thread_starved": "helper_heartbeat_scheduler_liveness",
    }
    statuses = {
        "same_file_fast_offset_slow": _tri(family_probe["same_file_fast_offset_slow"]),
        "pathological_offset_specific": _tri(
            family_probe["pathological_offset_specific"]
        ),
        "size_ladder_scaling": _tri(family_probe["size_ladder_scaling"]),
        "fresh_fd_slow": _tri(family_probe["fresh_fd_slow"]),
        "persistent_fd_slow": _tri(family_probe["persistent_fd_slow"]),
        "different_model_file_slow": _tri(family_probe["different_model_file_slow"]),
        "metadata_syscall_slow": _tri(family_probe["metadata_syscall_slow"]),
        "private_anonymous_destination_slow": _tri(
            family_probe["private_anonymous_destination_slow"]
        ),
        "separate_diagnostic_shm_destination_slow": _tri(
            family_probe["separate_diagnostic_shm_destination_slow"]
        ),
        "memory_only_copy_slow": _tri(family_probe["memory_only_copy_slow"]),
        "local_file_control_slow": _tri(family_probe["local_file_control_slow"]),
        "helper_thread_starved": heartbeat_status,
        "cgroup_cpu_pressure": _pressure_status("cpu"),
        "cgroup_memory_pressure": _pressure_status("memory"),
        "cgroup_io_pressure_convoy": _pressure_status("io"),
    }
    allowed = {"consistent", "inconsistent", "not_discriminated", "not_tested"}
    out = {}
    for family in sorted(statuses):
        status = statuses[family]
        if status not in allowed:
            status = "not_discriminated"
        label = family_probe.get(family)
        probe = by.get(label) if label else None
        out[family] = {
            "status": status,
            "evidence": {
                "probe": label or "passive.cgroup.pressure",
                "probe_status": (probe or {}).get("status"),
                "probe_wall_ms": (probe or {}).get("wall_ms"),
            },
            "reason": (
                None
                if status != "not_tested"
                else ((probe or {}).get("error") or "probe_not_tested")
            ),
        }
    return out


def _sickness_build_timeline(trip_event, passive, probes):
    timeline = [dict(trip_event)]
    if passive is not None:
        timeline.append({
            "phase": "passive_snapshot",
            "mono_ns": passive.get("mono_ns"),
            "wall_ns": passive.get("wall_ns"),
            "outstanding_count": passive.get("outstanding_count"),
        })
    for probe in probes:
        timeline.append({
            "phase": "active_probe",
            "label": probe.get("label"),
            "status": probe.get("status"),
            "started_mono_ns": probe.get("started_mono_ns"),
            "ended_mono_ns": probe.get("ended_mono_ns"),
            "wall_ms": probe.get("wall_ms"),
            "state_changed": probe.get("state_changed"),
        })
    return timeline


def _sickness_reply_block_snapshot(block):
    # Copy a published diagnostic block through JSON so a production reply
    # never shares mutable state with the independent tripwire handler thread.
    try:
        return json.loads(json.dumps(block, default=str))
    except BaseException:
        return None


def _sickness_publish_reply_block(key, block):
    # Replace the whole published dict at each phase boundary.  A reader that
    # already grabbed the previous reference can never observe a concurrent
    # mutation.
    snapshot = _sickness_reply_block_snapshot(block)
    if snapshot is None:
        return
    with _sickness_lock:
        _sickness_reply_blocks[key] = snapshot


def _sickness_handle_tripwire(key, trigger, sequence):
    mono_start = _sickness_mono_ns()
    wall_start = _sickness_wall_ns()
    event = {
        "phase": "tripwire",
        "key": key,
        "mono_ns": mono_start,
        "wall_ns": wall_start,
        "threshold_ms": round(SICKNESS_TRIPWIRE_NS / 1e6, 3),
        "trigger_sequence": trigger.get("sequence"),
        "trigger_age_ms": trigger.get("age_ms"),
        "role": trigger.get("role"),
        "path": trigger.get("path"),
        "offset": trigger.get("offset"),
        "length": trigger.get("length"),
        "worker_native_tid": trigger.get("worker_native_tid"),
    }
    block = {
        "schema": SICKNESS_SCHEMA,
        "version": SICKNESS_VERSION,
        "selector": True,
        "config_hash": sickness_config_hash,
        "profile_hash": sickness_profile_hash,
        "invocation_id": sickness_invocation_id,
        "request_id": trigger.get("request_id"),
        "status": "collecting",
        "tripwire": {
            "threshold_ms": round(SICKNESS_TRIPWIRE_NS / 1e6, 3),
            "fired": True,
            "first_fired_mono_ns": mono_start,
            "first_fired_wall_ns": wall_start,
            "key": key,
        },
        "snapshot_order": [],
        "passive": None,
        "active_probes": [],
        "hypotheses": {},
        "timeline": [],
        "helper_heartbeat": {},
        "production_reads": [],
        "control_manifest": sickness_control_manifest,
        "budget": {},
    }
    # Publish the firing block immediately so a production reply that lands
    # before the passive snapshot still carries bounded firing evidence.
    _sickness_publish_reply_block(key, block)
    try:
        # Passive snapshot MUST be captured before any active probe runs.
        block["passive"] = _sickness_passive_snapshot(trigger)
        block["snapshot_order"].append("passive")
        block["helper_heartbeat"] = _sickness_heartbeat_snapshot()
        # Publish the raw passive snapshot before any active probe runs.  A
        # production reply is never made to wait for the probe matrix; the
        # terminal path preserves the complete block.
        _sickness_publish_reply_block(key, block)
        path = str(trigger.get("path") or "")
        file_size = None
        try:
            if path and os.path.exists(path):
                file_size = int(os.stat(path).st_size)
        except Exception:
            file_size = None
        probes = _sickness_run_probe_matrix(
            trigger, sequence, trigger.get("role"), path, file_size
        )
        block["snapshot_order"].append("active_probes")
        block["active_probes"] = probes
        block["hypotheses"] = _sickness_hypotheses(probes, block.get("passive"))
        block["timeline"] = _sickness_build_timeline(
            event, block.get("passive"), probes
        )
        block["production_reads"] = [
            dict(item) for item in _sickness_completed_reads[-64:]
        ]
        block["budget"] = {
            "max_probes_per_request": SICKNESS_MAX_PROBES_PER_REQUEST,
            "max_probes_total": SICKNESS_MAX_PROBES_TOTAL,
            "probes_in_block": len(probes),
            "probes_total": _sickness_probe_total,
        }
        block["status"] = "complete"
    except BaseException as exc:
        block["status"] = "error"
        block["error"] = ("%s:%s" % (type(exc).__name__, exc))[:240]
    finally:
        # The complete (or errored) block is published for the child terminal
        # evidence even when the production reply already carried the
        # incomplete snapshot.
        _sickness_publish_reply_block(key, block)
        _sickness_events.append({
            "key": key,
            "mono_ns": mono_start,
            "wall_ns": wall_start,
            "status": block.get("status"),
        })
        del _sickness_events[:-64]
        reply_event = _sickness_reply_events.get(key)
        if reply_event is not None:
            reply_event.set()


def _sickness_queue_tripwire(key, record):
    # Non-blocking handoff.  The watchdog polling loop must never run the probe
    # matrix inline.
    _sickness_trip_queue.put((key, record, record.get("sequence")))


def _sickness_watchdog_scan():
    # One detection pass: mark first-only and enqueue.  Never runs the matrix.
    now = _sickness_mono_ns()
    if now is None:
        return 0
    detected = 0
    for record in _sickness_due_records(now, SICKNESS_TRIPWIRE_NS):
        key = _sickness_request_key(record)
        if not _sickness_mark_fired(key):
            continue
        _sickness_reply_events.setdefault(key, threading.Event())
        _sickness_queue_tripwire(key, record)
        detected += 1
    return detected


def _sickness_diag_worker():
    # Single independent handler.  Detection (watchdog) is decoupled from
    # handling so a slow probe matrix cannot delay the next tripwire.
    while True:
        item = _sickness_trip_queue.get()
        try:
            if item is None:
                return
            key, record, sequence = item
            _sickness_handle_tripwire(key, record, sequence)
        except BaseException as exc:
            _sickness_errors.append(("%s:%s" % (type(exc).__name__, exc))[:160])
            del _sickness_errors[:-8]
        finally:
            try:
                _sickness_trip_queue.task_done()
            except BaseException:
                pass


def _sickness_watchdog_loop():
    while not _sickness_stop.is_set():
        try:
            _sickness_watchdog_scan()
        except BaseException as exc:
            _sickness_errors.append(("%s:%s" % (type(exc).__name__, exc))[:160])
            del _sickness_errors[:-8]
        _sickness_stop.wait(SICKNESS_WATCHDOG_POLL_S)


def _sickness_request_block(req, got):
    # Never waits.  A production child reply must not block on the bounded
    # probe matrix: a fired request returns the latest published block (raw
    # passive data collected so far, explicitly marked incomplete while the
    # handler is still collecting).  The complete block is retained in the
    # child terminal evidence regardless of which reply landed first.
    try:
        if not preadv_sickness_diag:
            return None
        request_id = req.get("request_id")
        key = "req:%s" % request_id
        with _sickness_lock:
            block = _sickness_reply_blocks.get(key)
            fired = key in _sickness_fired
        if isinstance(block, dict):
            snapshot = _sickness_reply_block_snapshot(block)
            if snapshot is None:
                snapshot = dict(block)
            if str(snapshot.get("status")) == "collecting":
                snapshot["status"] = "incomplete"
            return snapshot
        # Fired but the handler has not published yet, or not fired at all.
        # This is a clearly marked bounded block, never a 60s wait.
        return {
            "schema": SICKNESS_SCHEMA,
            "version": SICKNESS_VERSION,
            "selector": True,
            "config_hash": sickness_config_hash,
            "profile_hash": sickness_profile_hash,
            "invocation_id": sickness_invocation_id,
            "request_id": request_id,
            "status": "incomplete" if fired else "not_fired",
            "tripwire": {
                "threshold_ms": round(SICKNESS_TRIPWIRE_NS / 1e6, 3),
                "fired": bool(fired),
            },
            "snapshot_order": [],
            "passive": None,
            "active_probes": [],
            "hypotheses": _sickness_hypotheses([], None),
            "timeline": [],
            "helper_heartbeat": _sickness_heartbeat_snapshot(),
            "production_reads": [
                dict(item) for item in _sickness_completed_reads[-64:]
            ],
            "control_manifest": sickness_control_manifest,
            "budget": {
                "max_probes_per_request": SICKNESS_MAX_PROBES_PER_REQUEST,
                "max_probes_total": SICKNESS_MAX_PROBES_TOTAL,
                "probes_total": _sickness_probe_total,
            },
        }
    except BaseException as exc:
        return {
            "schema": SICKNESS_SCHEMA,
            "version": SICKNESS_VERSION,
            "selector": True,
            "status": "error",
            "error": ("%s:%s" % (type(exc).__name__, exc))[:200],
        }


def _sickness_attach_reply(payload, req, got):
    # OFF leaves the production reply schema exactly as the control path
    # emitted it: the diagnostic key is omitted, never added as None/disabled.
    if not preadv_sickness_diag:
        return payload
    try:
        payload["preadv_sickness_diag"] = _sickness_request_block(req, got)
    except BaseException:
        pass
    return payload


def _sickness_launch_evidence():
    if not preadv_sickness_diag:
        return {"enabled": False}
    controls = sickness_control_manifest or {}
    return {
        "enabled": True,
        "schema": SICKNESS_SCHEMA,
        "version": SICKNESS_VERSION,
        "tripwire_ms": round(SICKNESS_TRIPWIRE_NS / 1e6, 3),
        "config_hash": sickness_config_hash,
        "profile_hash": sickness_profile_hash,
        "invocation_id": sickness_invocation_id,
        "control_manifest_loaded": bool(controls),
        "control_manifest_roles": sorted((controls.get("files") or {}).keys()),
        "control_manifest": controls,
        "size_ladder": list(SICKNESS_SIZE_LADDER),
        "max_probes_per_request": SICKNESS_MAX_PROBES_PER_REQUEST,
        "max_probes_total": SICKNESS_MAX_PROBES_TOTAL,
        "heartbeat_interval_s": SICKNESS_HEARTBEAT_INTERVAL_S,
        "cuda_initialized": False,
        "torch_imported": bool("torch" in sys.modules),
    }


def _sickness_ready_child_fields():
    # OFF omits the diagnostic key entirely so ready_child keeps the exact
    # control schema; ON attaches the explicit launch evidence.
    if not preadv_sickness_diag:
        return {}
    return {"preadv_sickness_diag": _sickness_launch_evidence()}


def _pread_into_probed(fd, view, offset, context, records):
    # Wrap exactly one physical positioned read.  The before/after probes sit
    # outside the measured interval; ``preadv_start_ns``/``preadv_end_ns``
    # bracket only the actual ``_pread_into`` syscall.  One record is appended
    # in ``finally`` even when the syscall raises, so a failed read is still
    # evidenced.  Diagnostics are passive: the wrapper never branches, gates,
    # retries, or changes the returned byte count.
    native_tid = context.get("worker_native_tid")
    record = {
        "role": context.get("role"),
        "worker_name": context.get("worker_name"),
        "worker_index": context.get("worker_index"),
        "worker_ident": context.get("worker_ident"),
        "worker_native_tid": native_tid,
        "fd_key_path": context.get("fd_key_path"),
        "fd_key_producer": context.get("fd_key_producer"),
        "fd_number": context.get("fd_number"),
        "path": context.get("path"),
        "syscall": (
            "os.preadv" if hasattr(os, "preadv")
            else ("os.pread" if hasattr(os, "pread") else "unsupported")
        ),
        "offset": int(offset),
        "requested_bytes": int(len(view)),
        "record_id": context.get("record_id"),
        "fill_index": context.get("fill_index"),
    }
    # Diagnostic outstanding-read registry (selector ON only).  A globals lookup
    # keeps the pure AST-extracted helper working when the diagnostic subsystem
    # is absent.  Never branches, gates, retries, or changes the byte count.
    _sickness_begin = globals().get("_sickness_begin_read")
    _sickness_sequence = None
    if _sickness_begin is not None:
        try:
            _sickness_sequence = _sickness_begin(context, fd, view, offset)
        except BaseException:
            _sickness_sequence = None
    before = _syscall_probe(native_tid)
    record["preadv_start_ns"] = before.get("wall_ns")
    record["thread_cpu_before_ns"] = before.get("thread_cpu_ns")
    record["rusage_before"] = before.get("rusage")
    record["schedstat_before"] = before.get("schedstat")
    returned = None
    syscall_error = None
    try:
        returned = _pread_into(fd, view, offset)
    except BaseException as exc:
        syscall_error = ("%s:%s" % (type(exc).__name__, exc))[:200]
        raise
    finally:
        # Timestamp immediately after the syscall, then probe rusage/schedstat
        # outside the measured interval.
        record["preadv_end_ns"] = int(time.monotonic_ns())
        after = _syscall_probe(native_tid)
        record["thread_cpu_after_ns"] = after.get("thread_cpu_ns")
        record["rusage_after"] = after.get("rusage")
        # One explicit scope label for this record's rusage before/after/delta.
        # Both probes must agree it is thread scope; otherwise None, so a
        # process-wide counter can never be read as thread-bounded.
        record["rusage_scope"] = (
            "thread"
            if before.get("rusage_scope") == "thread"
            and after.get("rusage_scope") == "thread"
            else None
        )
        record["schedstat_after"] = after.get("schedstat")
        start_ns = record.get("preadv_start_ns")
        end_ns = record.get("preadv_end_ns")
        wall_ns = (
            max(0, int(end_ns) - int(start_ns))
            if start_ns is not None and end_ns is not None else None
        )
        record["preadv_wall_ms"] = (
            round(wall_ns / 1e6, 6) if wall_ns is not None else None
        )
        cpu_before = record.get("thread_cpu_before_ns")
        cpu_after = record.get("thread_cpu_after_ns")
        cpu_delta_ns = (
            max(0, int(cpu_after) - int(cpu_before))
            if cpu_before is not None and cpu_after is not None else None
        )
        record["thread_cpu_delta_ms"] = (
            round(cpu_delta_ns / 1e6, 6) if cpu_delta_ns is not None else None
        )
        record["off_cpu_estimate_ms"] = (
            round(max(0, wall_ns - cpu_delta_ns) / 1e6, 6)
            if wall_ns is not None and cpu_delta_ns is not None else None
        )
        record["rusage_delta"] = _probe_delta(
            record.get("rusage_before"), record.get("rusage_after")
        )
        record["schedstat_delta"] = _probe_delta(
            record.get("schedstat_before"), record.get("schedstat_after")
        )
        record["returned_bytes"] = int(returned) if returned is not None else None
        if syscall_error is not None:
            record["error"] = syscall_error
        # Bounded child post-hoc fallback: only for a read that actually ran
        # longer than the slow threshold, and only after the measured interval.
        # The parent prefers its own live sampler when it can reach this child's
        # procfs; this guarantees evidence survives when it cannot.
        if wall_ns is not None and wall_ns >= _child_fallback_threshold_ns:
            global _child_fallback_dropped
            try:
                if len(_child_fallback_records) < _child_fallback_cap:
                    fallback = _child_self_snapshot(native_tid)
                    _child_fallback_records.append(fallback)
                    record["child_fallback"] = fallback
                else:
                    _child_fallback_dropped += 1
                    record["child_fallback_dropped"] = True
            except Exception:
                pass
        _sickness_end = globals().get("_sickness_end_read")
        if _sickness_end is not None:
            try:
                _sickness_end(_sickness_sequence, returned, syscall_error)
            except BaseException:
                pass
        records.append(record)
    return returned


# ── child-owned descriptor lifecycle (persistent-FD treatment only) ───────────
# OFF: every fill opens and closes exactly one descriptor (control).  ON: one
# descriptor per normalized (path, producer_id), reused for every positioned
# preadv, closed on fill error or at child shutdown.  All counters are the
# child's own; the parent only aggregates what it is told.
_fd_lock = threading.RLock()
_fd_cache = {}
_fd_stats = {}
_fd_open_count = 0
_fd_reuse_count = 0
_fd_close_count = 0
_fd_shutdown_close_count = 0
_fd_open_wall_ns = 0
_fd_close_wall_ns = 0
_fd_finalized = False


def _fd_key(path, producer_id):
    return (os.path.normpath(str(path)), int(producer_id))


def _fd_stat_row(key):
    row = _fd_stats.get(key)
    if row is None:
        row = {
            "path": key[0],
            "producer_id": key[1],
            "fill_count": 0,
            "source_bytes": 0,
            "fd_open_count": 0,
            "fd_reuse_count": 0,
            "fd_close_count": 0,
            "fd_open_wall_ms": 0.0,
            "fd_close_wall_ms": 0.0,
        }
        _fd_stats[key] = row
    return row


def _close_fd(key, fd):
    # Close one descriptor and account for it; returns (closed, wall_ns).
    global _fd_close_count, _fd_close_wall_ns
    t0 = time.monotonic_ns()
    try:
        os.close(fd)
    except Exception:
        return False, 0
    close_wall_ns = max(0, time.monotonic_ns() - t0)
    with _fd_lock:
        _fd_close_count += 1
        _fd_close_wall_ns += close_wall_ns
        row = _fd_stat_row(key)
        row["fd_close_count"] += 1
        row["fd_close_wall_ms"] = round(row["fd_close_wall_ms"] + close_wall_ns / 1e6, 4)
    return True, close_wall_ns


def _acquire_fd(path, producer_id):
    # Return (key, fd, opened_here, open_wall_ns, reused,
    #         open_delta, reuse_delta, close_delta, close_wall_ns).
    # The deltas describe exactly the descriptor lifecycle this call performed.
    # A descriptor that loses the lazy-open race still physically opened and is
    # immediately closed, so both syscalls are counted and reported here rather
    # than vanishing from telemetry.
    global _fd_open_count, _fd_reuse_count, _fd_open_wall_ns
    key = _fd_key(path, producer_id)
    if not persistent_fds:
        t0 = time.monotonic_ns()
        fd = os.open(path, os.O_RDONLY)
        open_wall_ns = max(0, time.monotonic_ns() - t0)
        with _fd_lock:
            _fd_open_count += 1
            _fd_open_wall_ns += open_wall_ns
            row = _fd_stat_row(key)
            row["fd_open_count"] += 1
            row["fd_open_wall_ms"] = round(row["fd_open_wall_ms"] + open_wall_ns / 1e6, 4)
        return key, fd, True, open_wall_ns, False, 1, 0, 0, 0
    with _fd_lock:
        fd = _fd_cache.get(key)
        if fd is not None:
            _fd_reuse_count += 1
            row = _fd_stat_row(key)
            row["fd_reuse_count"] += 1
            return key, fd, False, 0, True, 0, 1, 0, 0
    # Open outside the lock so one slow open cannot stall the other producer.
    t0 = time.monotonic_ns()
    fd = os.open(path, os.O_RDONLY)
    open_wall_ns = max(0, time.monotonic_ns() - t0)
    with _fd_lock:
        existing = _fd_cache.get(key)
        if existing is not None:
            # Lost the open race; keep the cached winner and discard ours.
            # Account for this descriptor's physical open and immediate close
            # before counting the reuse of the winner.
            _fd_open_count += 1
            _fd_open_wall_ns += open_wall_ns
            row = _fd_stat_row(key)
            row["fd_open_count"] += 1
            row["fd_open_wall_ms"] = round(row["fd_open_wall_ms"] + open_wall_ns / 1e6, 4)
            _fd_reuse_count += 1
            row["fd_reuse_count"] += 1
            closed, close_wall_ns = _close_fd(key, fd)
            return (
                key, existing, False, open_wall_ns, True,
                1, 1, 1 if closed else 0, close_wall_ns,
            )
        _fd_cache[key] = fd
        _fd_open_count += 1
        _fd_open_wall_ns += open_wall_ns
        row = _fd_stat_row(key)
        row["fd_open_count"] += 1
        row["fd_open_wall_ms"] = round(row["fd_open_wall_ms"] + open_wall_ns / 1e6, 4)
        return key, fd, True, open_wall_ns, False, 1, 0, 0, 0


def _finish_fd(key, fd, opened_here, ok):
    # Return (closed, close_wall_ns) under the selected lifecycle.
    if not persistent_fds:
        return _close_fd(key, fd)
    if ok:
        return False, 0
    # Close-on-error: drop the key so a failed descriptor is never reused.
    with _fd_lock:
        if _fd_cache.get(key) == fd:
            _fd_cache.pop(key, None)
            return _close_fd(key, fd)
    if opened_here:
        return _close_fd(key, fd)
    return False, 0


def _record_fill_amount(key, source_bytes):
    with _fd_lock:
        row = _fd_stat_row(key)
        row["fill_count"] += 1
        row["source_bytes"] += max(0, int(source_bytes))


def _close_all_fds():
    # Deterministic shutdown closes.  Tracked separately from per-fill closes
    # so the parent can reconcile its own per-fill deltas against the child's
    # terminal total instead of guessing about hidden shutdown closes.
    global _fd_shutdown_close_count
    with _fd_lock:
        for key, fd in tuple(_fd_cache.items()):
            closed, _ = _close_fd(key, fd)
            if closed:
                _fd_shutdown_close_count += 1
        _fd_cache.clear()


def _fd_snapshot():
    with _fd_lock:
        rows = [dict(_fd_stats[key]) for key in sorted(_fd_stats)]
        return {
            "op": "fd_stats_child",
            "persistent_fds": bool(persistent_fds),
            "fill_count": int(sum(row["fill_count"] for row in rows)),
            "source_bytes": int(sum(row["source_bytes"] for row in rows)),
            "fd_open_count": int(_fd_open_count),
            "fd_reuse_count": int(_fd_reuse_count),
            "fd_close_count": int(_fd_close_count),
            "fd_shutdown_close_count": int(_fd_shutdown_close_count),
            "fd_open_wall_ms": round(_fd_open_wall_ns / 1e6, 4),
            "fd_close_wall_ms": round(_fd_close_wall_ns / 1e6, 4),
            "unique_fd_keys": len(rows),
            "keys": rows,
        }


def _finalize_fds():
    # Deterministic child shutdown: close every cached descriptor exactly once.
    global _fd_finalized
    if _fd_finalized:
        return
    _fd_finalized = True
    _close_all_fds()
    try:
        sys.stderr.write(json.dumps(_fd_snapshot()) + "\n")
        sys.stderr.flush()
    except Exception:
        pass


# ── diagnostic private source/destination split staging (flag ON only) ───────
# Exactly one reusable anonymous private buffer per existing source worker
# thread.  It is allocated during the required startup barrier and stored in a
# thread-local, so the same pool thread reuses its buffer for every fill.  No
# process, slot, or FD lifecycle is added, and OFF never allocates.
_worker_local = threading.local()


def _worker_private_buffer():
    if not private_split_io:
        return None
    buffer = getattr(_worker_local, "private_buffer", None)
    if buffer is None or len(buffer) < int(slot_bytes):
        buffer = bytearray(int(slot_bytes))
        _worker_local.private_buffer = buffer
    return buffer


# ── frozen fresh-window mmap source engine (mmap_fresh only) ─────────────────
# Each source worker is an independent READER PROCESS.  A reader owns its own
# persistent per-(path, producer) descriptor and does one fresh exact-window
# PROT_READ|MAP_PRIVATE mapping per read, copied with native libc.memcpy into
# the leased SHM slot and unmapped synchronously.  Readers publish their result
# back over a private pipe; they never touch the control IPC or stdout.

def _mmap_send_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _mmap_recv_all(fd, count):
    chunks = []
    remaining = int(count)
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _mmap_buffer_address():
    return int(ctypes.addressof(ctypes.c_char.from_buffer(memoryview(buf))))


_mmap_private_buf = None
_mmap_private_buf_addr = 0
_mmap_private_buf_len = 0


def _mmap_private_copy_target(length):
    # One reusable PRIVATE anonymous buffer per reader process. The bounded
    # copy diagnostic uses it as a warm destination; private-split mode uses it
    # as the real source staging destination before the explicit SHM copy.
    global _mmap_private_buf, _mmap_private_buf_addr, _mmap_private_buf_len
    need = int(length)
    if need <= 0:
        return 0, 0
    if _mmap_private_buf is None or _mmap_private_buf_len < need:
        _mmap_private_buf = bytearray(need)
        _mmap_private_buf_addr = int(
            ctypes.addressof(ctypes.c_char.from_buffer(_mmap_private_buf))
        )
        _mmap_private_buf_len = need
    return _mmap_private_buf_addr, _mmap_private_buf_len


def _mmap_fault_counters():
    # (minor, major) page-fault totals for this process, or (None, None).
    # Linux-only, best-effort: used purely to attribute per-read source cost.
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        return int(ru.ru_minflt), int(ru.ru_majflt)
    except BaseException:
        return None, None


def _mmap_reader_fill(req):
    base = {
        "request_id": req.get("request_id"),
        "arena_epoch": req.get("arena_epoch"),
        "role": req.get("role"),
        "slot_index": req.get("slot_index"),
        "slot_generation": req.get("slot_generation"),
        "source_offset": req.get("source_offset"),
        "destination_offset": req.get("destination_offset"),
    }
    producer_id = int(req.get("producer_id") or 0)
    path = str(req.get("path"))
    fd_key_path = os.path.normpath(path)
    fd_key_producer = int(producer_id)
    fd_open_delta = 0
    fd_reuse_delta = 0
    fd = _mmap_reader_fds.get((fd_key_path, fd_key_producer))
    try:
        if fd is None:
            fd = os.open(path, os.O_RDONLY)
            _mmap_reader_fds[(fd_key_path, fd_key_producer)] = fd
            fd_open_delta = 1
        else:
            fd_reuse_delta = 1
        slot = int(req["slot_index"])
        length = int(req["length"])
        destination = int(req["destination_offset"])
        offset = int(req["source_offset"])
        if slot < 0 or slot >= slot_count:
            raise ValueError("slot_out_of_range")
        if length <= 0 or length > slot_bytes:
            raise ValueError("length_out_of_range")
        if destination < 0 or destination + length > slot_bytes:
            raise ValueError("destination_out_of_range")
        if offset < 0:
            raise ValueError("source_offset_negative")
        dest_addr = _mmap_buf_addr + slot * slot_bytes + destination
        source_dest_addr = dest_addr
        private_addr = 0
        private_len = 0
        if private_split_io:
            private_addr, private_len = _mmap_private_copy_target(length)
            if not private_addr or private_len < length:
                raise RuntimeError("mmap_private_buffer_unavailable")
            source_dest_addr = private_addr
        window_start = (offset // _PAGE) * _PAGE
        delta = offset - window_start
        window_len = ((delta + length + _PAGE - 1) // _PAGE) * _PAGE
        read_start_ns = time.monotonic_ns()
        map_end_ns = read_start_ns
        copy_end_ns = read_start_ns
        private_to_shm_start_ns = None
        private_to_shm_end_ns = None
        unmap_end_ns = read_start_ns
        win = int(_mmap_libc.mmap(
            None, window_len, _PROT_READ, _MAP_PRIVATE, fd, window_start
        ))
        if win in (0, -1) or win == 0xFFFFFFFFFFFFFFFF:
            raise OSError("mmap_failed errno=%d" % int(ctypes.get_errno()))
        map_end_ns = time.monotonic_ns()
        faults_before = _mmap_fault_counters()
        warm_ns = None
        shm_warm_ns = None
        frozen_copy_ns = None
        frozen_unmap_ns = None
        try:
            _mmap_libc.memcpy(source_dest_addr, win + delta, length)
            copy_end_ns = time.monotonic_ns()
            if private_split_io:
                private_to_shm_start_ns = copy_end_ns
                _mmap_libc.memcpy(dest_addr, private_addr, length)
                private_to_shm_end_ns = time.monotonic_ns()
            # Diagnostics only (default OFF): repeat the SAME (now resident)
            # window copy into a private anonymous buffer.  Pure-copy time vs the
            # production copy time splits source page-in from destination-copy
            # cost.  Never enabled by default: it doubles the copied bytes.
            global _mmap_diag_budget
            if mmap_copy_diag and not private_split_io and _mmap_diag_budget > 0:
                _mmap_diag_budget -= 1
                try:
                    priv_addr, _plen = _mmap_private_copy_target(length)
                    if priv_addr:
                        # (1) warmed source -> PRIVATE anon destination
                        w0 = time.monotonic_ns()
                        _mmap_libc.memcpy(priv_addr, win + delta, length)
                        warm_ns = int(max(0, time.monotonic_ns() - w0))
                        # (2) warmed PRIVATE source -> the registered SHM slot
                        # destination.  Isolates the destination write path with
                        # a fully warm source, so a slow SHM write is visible
                        # independently of source page-in.
                        s0 = time.monotonic_ns()
                        _mmap_libc.memcpy(dest_addr, priv_addr, length)
                        shm_warm_ns = int(max(0, time.monotonic_ns() - s0))
                        # (3) frozen-parity op: a fresh window of the SAME file
                        # range copied into the PRIVATE buffer (exactly arm C's
                        # shape), so its munmap can be compared with the
                        # production munmap in the same process and run.
                        fpw = int(_mmap_libc.mmap(
                            None, window_len, _PROT_READ, _MAP_PRIVATE,
                            fd, window_start,
                        ))
                        if fpw not in (0, -1) and fpw != 0xFFFFFFFFFFFFFFFF:
                            f0 = time.monotonic_ns()
                            _mmap_libc.memcpy(priv_addr, fpw + delta, length)
                            f1 = time.monotonic_ns()
                            _mmap_libc.munmap(fpw, window_len)
                            f2 = time.monotonic_ns()
                            frozen_copy_ns = int(max(0, f1 - f0))
                            frozen_unmap_ns = int(max(0, f2 - f1))
                except BaseException:
                    warm_ns = None
                    shm_warm_ns = None
                    frozen_copy_ns = None
                    frozen_unmap_ns = None
        finally:
            if copy_end_ns == read_start_ns:
                copy_end_ns = time.monotonic_ns()
            # Synchronous unmap: the fresh window never outlives the read.
            _mmap_libc.munmap(win, window_len)
            unmap_end_ns = time.monotonic_ns()
        faults_after = _mmap_fault_counters()
        read_end_ns = unmap_end_ns
        minflt = None
        majflt = None
        if faults_before[0] is not None and faults_after[0] is not None:
            minflt = int(faults_after[0] - faults_before[0])
            majflt = int(faults_after[1] - faults_before[1])
        result = dict(base)
        result.update({
            "op": "ready",
            "returned_bytes": int(length),
            "read_syscalls": 1,
            "preadv_diagnostics": [],
            "child_read_start_ns": int(read_start_ns),
            "child_read_end_ns": int(read_end_ns),
            "read_duration_ns": int(max(0, read_end_ns - read_start_ns)),
            "short": False,
            "cuda_initialized": False,
            "gpu_alloc_bytes": 0,
            "torch_imported": False,
            "producer_id": int(producer_id),
            "fd_key_path": fd_key_path,
            "fd_key_producer": fd_key_producer,
            "fd_open_count": int(fd_open_delta),
            "fd_reuse_count": int(fd_reuse_delta),
            "fd_close_count": 0,
            "fd_open_wall_ms": 0.0,
            "fd_close_wall_ms": 0.0,
            "source_engine": "mmap_fresh",
            "reader_pid": os.getpid(),
            "reader_index": int(req.get("_reader_index") or 0),
            "mmap_window_bytes": int(window_len),
            "mmap_launch_gap_wait_ns": int(req.get("_launch_gap_wait_ns") or 0),
            # Per-read phase split so source cost is attributable without a
            # second experiment: map, memcpy, unmap, plus page-fault deltas.
             "mmap_map_ns": int(max(0, map_end_ns - read_start_ns)),
             # ``source_touch_copy`` is the production mmap memcpy from the
             # mapped source window into the leased arena slot.  Keep the old
             # key as a compatibility alias; it was frequently misread as a
             # raw-disk or page-in-only measurement.
             "copy_start_ns": int(map_end_ns),
             "copy_end_ns": int(copy_end_ns),
             "source_touch_copy_ns": int(max(0, copy_end_ns - map_end_ns)),
             "mmap_memcpy_ns": int(max(0, copy_end_ns - map_end_ns)),
             "mmap_munmap_ns": int(max(
                 0,
                 unmap_end_ns - (
                     private_to_shm_end_ns
                     if private_to_shm_end_ns is not None else copy_end_ns
                 ),
             )),
             "mmap_op_start_ns": int(read_start_ns),
             "mmap_op_end_ns": int(read_end_ns),
             "mmap_op_ns": int(max(0, read_end_ns - read_start_ns)),
             "source_range": [int(offset), int(offset + length)],
             "source_end_offset": int(offset + length),
            "mmap_minflt": minflt,
            "mmap_majflt": majflt,
            "mmap_memcpy_warm_ns": warm_ns,
            "mmap_memcpy_shm_warm_ns": shm_warm_ns,
            "mmap_frozen_copy_ns": frozen_copy_ns,
            "mmap_frozen_unmap_ns": frozen_unmap_ns,
        })
        if private_split_io:
            result.update({
                "split_io": True,
                "private_buffer_bytes": int(private_len),
                "source_read_duration_ns": int(max(0, copy_end_ns - read_start_ns)),
                "private_to_shm_duration_ns": int(max(
                    0, private_to_shm_end_ns - private_to_shm_start_ns
                )),
                "worker_index": int(req.get("_reader_index") or 0),
                "worker_ident": os.getpid(),
                "worker_native_id": None,
            })
        return result
    except BaseException as exc:
        err = dict(base)
        err.update({
            "op": "error",
            "error": ("%s:%s" % (type(exc).__name__, exc))[:200],
            "producer_id": int(producer_id),
            "preadv_diagnostics": [],
            "fd_key_path": fd_key_path,
            "fd_key_producer": fd_key_producer,
            "fd_open_count": int(fd_open_delta),
            "fd_reuse_count": int(fd_reuse_delta),
            "fd_close_count": 0,
            "fd_open_wall_ms": 0.0,
            "fd_close_wall_ms": 0.0,
            "source_engine": "mmap_fresh",
            "reader_pid": os.getpid(),
        })
        return err


def _mmap_reader_main(index, cmd_r, res_w):
    # Runs in the reader PROCESS: standard library only, no torch, no CUDA, no
    # stdout.  A crash here is contained to the reader and surfaces to the
    # parent as an EOF on that reader's reply pipe.
    # Allocate and zero the process-private staging buffer before the first
    # request enters its measured source interval. Each reader process owns one
    # reusable buffer; later fills do not allocate or first-touch it.
    if private_split_io:
        _mmap_private_copy_target(slot_bytes)
    while True:
        header = _mmap_recv_all(cmd_r, 4)
        if header is None:
            break
        (size,) = struct.unpack("<I", header)
        payload = _mmap_recv_all(cmd_r, size)
        if payload is None:
            break
        try:
            req = json.loads(payload.decode("utf-8"))
        except ValueError:
            break
        req["_reader_index"] = int(index)
        result = _mmap_reader_fill(req)
        blob = json.dumps(result, default=str).encode("utf-8")
        try:
            _mmap_send_all(res_w, struct.pack("<I", len(blob)) + blob)
        except Exception:
            break
    try:
        os._exit(0)
    except Exception:
        pass


_mmap_gate_lock = threading.Lock()
_mmap_last_launch_ns = [0]


def _mmap_launch_gate():
    # One global launch-spacing floor across every reader process.  Sleep the
    # remaining fraction with the lock RELEASED (frozen-engine semantics), so
    # readers never serialize behind another reader's wait; the floor spaces
    # CLAIMS, not reads.
    entered = time.monotonic_ns()
    while True:
        with _mmap_gate_lock:
            now = time.monotonic_ns()
            elapsed = now - _mmap_last_launch_ns[0]
            if elapsed >= MMAP_LAUNCH_GAP_NS:
                _mmap_last_launch_ns[0] = now
                return max(0, int(now - entered))
            remaining = MMAP_LAUNCH_GAP_NS - elapsed
        time.sleep(remaining / 1e9)


def _mmap_spawn_readers():
    global _mmap_buf_addr
    _mmap_buf_addr = _mmap_buffer_address()
    for index in range(max(1, int(workers))):
        cmd_r, cmd_w = os.pipe()
        res_r, res_w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(cmd_w)
                os.close(res_r)
            except Exception:
                pass
            _mmap_reader_main(index, cmd_r, res_w)
            os._exit(0)
        os.close(cmd_r)
        os.close(res_w)
        _mmap_readers.append({
            "index": int(index),
            "pid": int(pid),
            "cmd_w": cmd_w,
            "res_r": res_r,
            "lock": threading.Lock(),
        })
    return len(_mmap_readers)


def _mmap_shutdown_readers():
    for reader in _mmap_readers:
        try:
            os.close(reader["cmd_w"])
        except Exception:
            pass
        try:
            os.close(reader["res_r"])
        except Exception:
            pass
    for reader in _mmap_readers:
        try:
            os.waitpid(reader["pid"], 0)
        except Exception:
            pass
    _mmap_readers.clear()


MMAP_READER_IO_TIMEOUT_S = 120.0


def _mmap_reader_round_trip(reader, blob):
    # Bounded, liveness-checked pipe round-trip.  A dead reader fails fast and a
    # stalled reader fails closed on a deadline, so one sick source read can
    # never hang the whole request; the parent sees an explicit fill error.
    with reader["lock"]:
        reaped = 0
        try:
            reaped, _status = os.waitpid(reader["pid"], os.WNOHANG)
        except ChildProcessError:
            reaped = reader["pid"]
        if reaped == reader["pid"]:
            raise RuntimeError("mmap_reader_dead:%d" % int(reader["index"]))
        _mmap_send_all(reader["cmd_w"], struct.pack("<I", len(blob)) + blob)
        deadline = time.monotonic() + MMAP_READER_IO_TIMEOUT_S

        def _read_exact(count):
            chunks = []
            remaining = int(count)
            while remaining > 0:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise RuntimeError(
                        "mmap_reader_timeout:%d" % int(reader["index"])
                    )
                ready, _w, _x = select.select([reader["res_r"]], [], [], budget)
                if not ready:
                    raise RuntimeError(
                        "mmap_reader_timeout:%d" % int(reader["index"])
                    )
                chunk = os.read(reader["res_r"], remaining)
                if not chunk:
                    return None
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)

        header = _read_exact(4)
        if header is None:
            raise RuntimeError("mmap_reader_eof")
        (size,) = struct.unpack("<I", header)
        payload = _read_exact(size)
    if payload is None:
        raise RuntimeError("mmap_reader_eof")
    return payload


def _do_fill_mmap(req):
    base = {
        "request_id": req.get("request_id"),
        "arena_epoch": req.get("arena_epoch"),
        "role": req.get("role"),
        "slot_index": req.get("slot_index"),
        "slot_generation": req.get("slot_generation"),
        "source_offset": req.get("source_offset"),
        "destination_offset": req.get("destination_offset"),
    }
    try:
        if not _mmap_readers:
            raise RuntimeError("mmap_readers_not_started")
        producer_id = int(req.get("producer_id") or 0)
        reader = _mmap_readers[producer_id % len(_mmap_readers)]
        wait_ns = _mmap_launch_gate()
        outgoing = dict(req)
        outgoing["_launch_gap_wait_ns"] = int(wait_ns)
        blob = json.dumps(outgoing, default=str).encode("utf-8")
        rtt_start_ns = time.monotonic_ns()
        payload = _mmap_reader_round_trip(reader, blob)
        rtt_ns = int(max(0, time.monotonic_ns() - rtt_start_ns))
        result = json.loads(payload.decode("utf-8"))
        result["mmap_pipe_rtt_ns"] = rtt_ns
        _emit(result)
    except BaseException as exc:
        err = dict(base)
        err.update({
            "op": "error",
            "error": ("%s:%s" % (type(exc).__name__, exc))[:200],
            "source_engine": "mmap_fresh",
            "producer_id": int(req.get("producer_id") or 0),
            "preadv_diagnostics": [],
            "fd_open_count": 0,
            "fd_reuse_count": 0,
            "fd_close_count": 0,
            "fd_open_wall_ms": 0.0,
            "fd_close_wall_ms": 0.0,
        })
        _emit(err)


def _do_fill(req):
    if mmap_engine:
        _do_fill_mmap(req)
        return
    _tracer_enable_thread()
    rid = req.get("request_id")
    base = {
        "request_id": rid,
        "arena_epoch": req.get("arena_epoch"),
        "role": req.get("role"),
        "slot_index": req.get("slot_index"),
        "slot_generation": req.get("slot_generation"),
        "source_offset": req.get("source_offset"),
        "destination_offset": req.get("destination_offset"),
    }
    # Safe descriptor-delta defaults.  Both the ready and the error reply carry
    # the same delta shape; when acquisition never happened the deltas stay
    # zero, and when a later step fails after acquisition they carry the real
    # per-fill open/reuse/close deltas so the parent never loses them.
    producer_id = int(req.get("producer_id") or 0)
    fd_key = None
    fd_open_delta = 0
    fd_reuse_delta = 0
    fd_close_delta = 0
    fd_open_wall_ns = 0
    fd_close_wall_ns = 0
    # Child positioned-read interval.  Recorded around the pread loop only (not
    # the descriptor open/close) so the parent's per-fill duration aggregate is
    # derived from this child evidence.  Parent and child monotonic clocks are
    # comparable on the target.
    read_start_ns = None
    read_end_ns = None
    # Diagnostic split staging state (flag ON only): the per-worker private
    # buffer plus this worker's identity, and the separate source-read vs
    # private->SHM copy intervals.  OFF leaves these None/zero and the exact
    # direct file -> leased SHM path below is used unchanged.
    private_buffer = None
    worker_thread = threading.current_thread()
    worker_name = str(worker_thread.name)
    worker_index = getattr(_worker_local, "worker_index", None)
    worker_ident = int(threading.get_ident())
    worker_native_id = getattr(worker_thread, "native_id", None)
    if worker_native_id is None:
        try:
            worker_native_id = int(threading.get_native_id())
        except Exception:
            worker_native_id = None
    # Passive per-read syscall diagnostics for this fill.  Populated by the
    # measured preadv wrapper; empty until the read loop actually runs.
    preadv_diagnostics = []
    source_read_end_ns = None
    private_copy_start_ns = None
    private_copy_end_ns = None
    # Distinct C0 direct Volume V1 treatment state (initialized before the
    # guarded body so the error reply can always carry it).
    volume_transfer = None
    volume_block_diagnostics = []
    if private_split_io:
        private_buffer = _worker_private_buffer()
    try:
        slot = int(req["slot_index"])
        length = int(req["length"])
        destination = int(req["destination_offset"])
        offset = int(req["source_offset"])
        if slot < 0 or slot >= slot_count:
            raise ValueError("slot_out_of_range")
        if length <= 0 or length > slot_bytes:
            raise ValueError("length_out_of_range")
        if destination < 0 or destination + length > slot_bytes:
            raise ValueError("destination_out_of_range")
        if offset < 0:
            raise ValueError("source_offset_negative")
        path = str(req["path"])
        fd_key = _fd_key(path, producer_id)
        target = memoryview(buf)[slot * slot_bytes + destination: slot * slot_bytes + destination + length]
        got = 0
        syscalls = 0
        # OFF: the positioned read writes straight into the leased SHM slot.
        # ON: the positioned read writes into this worker's reusable private
        # buffer, then a separate timed copy moves the bytes into the leased
        # slot; the parent/H2D/adoption path sees the same slot bytes.
        read_target = target
        if private_split_io:
            read_target = memoryview(private_buffer)[:length]
        read_start_ns = time.monotonic_ns()
        if source_volume_v1:
            # Distinct treatment: the direct Volume V1 transport replaces only
            # the byte producer.  No descriptor is opened and no positioned read
            # is issued; there is deliberately no preadv fallback.
            try:
                summary = _volume_fill_blocking(req, read_target, offset, length)
            except BaseException as exc:
                summary = {
                    "ok": False,
                    "error": "volume_transport:%s:%s" % (type(exc).__name__, exc),
                    "completed_bytes": 0,
                    "volume_block_diagnostics": [],
                }
            volume_block_diagnostics = [
                dict(record)
                for record in (summary.get("volume_block_diagnostics") or [])
                if isinstance(record, dict)
            ]
            volume_transfer = {
                key: value
                for key, value in summary.items()
                if key != "volume_block_diagnostics"
            }
            got = int(summary.get("completed_bytes") or 0) if summary.get("ok") else 0
            source_read_end_ns = time.monotonic_ns()
            if private_split_io:
                private_copy_start_ns = time.monotonic_ns()
                if got > 0:
                    target[:got] = read_target[:got]
                private_copy_end_ns = time.monotonic_ns()
                read_end_ns = private_copy_end_ns
            else:
                read_end_ns = source_read_end_ns
            # Keep the child terminal descriptor snapshot reconcilable with the
            # parent's successful-fill aggregate even though no descriptor was
            # opened: one validated volume fill counts as one successful source
            # fill (open/reuse/close deltas stay zero on both sides).
            if got == length:
                _record_fill_amount(fd_key, got)
        else:
            (
                fd_key, fd, opened_here, open_wall_ns, reused,
                fd_open_delta, fd_reuse_delta, fd_close_delta, fd_close_wall_ns,
            ) = _acquire_fd(path, producer_id)
            fd_open_wall_ns = open_wall_ns
            # Passive correlation context threaded onto every per-syscall diagnostic.
            read_diag_context = {
                "role": req.get("role"),
                "worker_name": worker_name,
                "worker_index": worker_index,
                "worker_ident": worker_ident,
                "worker_native_tid": worker_native_id,
                "path": path,
                "fd_key_path": fd_key[0] if fd_key else None,
                "fd_key_producer": fd_key[1] if fd_key else None,
                "fd_number": int(fd),
                "record_id": req.get("record_id"),
                "fill_index": req.get("fill_index"),
                "request_id": req.get("request_id"),
                "slot_index": req.get("slot_index"),
                "destination_offset": req.get("destination_offset"),
            }
            try:
                while got < length:
                    n = _pread_into_probed(
                        fd, read_target[got:], offset + got,
                        read_diag_context, preadv_diagnostics,
                    )
                    syscalls += 1
                    if n <= 0:
                        break
                    got += n
                source_read_end_ns = time.monotonic_ns()
                if private_split_io:
                    private_copy_start_ns = time.monotonic_ns()
                    if got > 0:
                        target[:got] = read_target[:got]
                    private_copy_end_ns = time.monotonic_ns()
                    read_end_ns = private_copy_end_ns
                else:
                    read_end_ns = source_read_end_ns
            finally:
                if read_end_ns is None:
                    read_end_ns = time.monotonic_ns()
                if source_read_end_ns is None:
                    source_read_end_ns = read_end_ns
                if private_split_io and private_copy_end_ns is None:
                    private_copy_start_ns = read_end_ns
                    private_copy_end_ns = read_end_ns
                ok = got == length
                closed, finish_close_wall_ns = _finish_fd(fd_key, fd, opened_here, ok)
                fd_close_delta += 1 if closed else 0
                fd_close_wall_ns += finish_close_wall_ns
                _record_fill_amount(fd_key, got)
        result = dict(base)
        result.update({
            "op": "ready" if got == length else "error",
            "returned_bytes": got,
            "read_syscalls": syscalls,
            "preadv_diagnostics": preadv_diagnostics,
            "child_read_start_ns": int(read_start_ns),
            "child_read_end_ns": int(read_end_ns),
            "read_duration_ns": int(max(0, read_end_ns - read_start_ns)),
            "short": got < length,
            "cuda_initialized": False,
            "gpu_alloc_bytes": 0,
            "torch_imported": bool("torch" in sys.modules),
            "producer_id": producer_id,
            "fd_key_path": fd_key[0],
            "fd_key_producer": fd_key[1],
            "fd_open_count": int(fd_open_delta),
            "fd_reuse_count": int(fd_reuse_delta),
            "fd_close_count": int(fd_close_delta),
            "fd_open_wall_ms": round(fd_open_wall_ns / 1e6, 4),
            "fd_close_wall_ms": round(fd_close_wall_ns / 1e6, 4),
        })
        if private_split_io:
            result.update({
                "split_io": True,
                "private_buffer_bytes": (
                    int(len(private_buffer)) if private_buffer is not None else 0
                ),
                "source_read_duration_ns": int(max(0, source_read_end_ns - read_start_ns)),
                "private_to_shm_duration_ns": int(
                    max(0, private_copy_end_ns - private_copy_start_ns)
                ),
                "worker_index": worker_index,
                "worker_ident": worker_ident,
                "worker_native_id": worker_native_id,
            })
        if source_volume_v1:
            result.update({
                "volume_source": "direct_volume_v1",
                "volume_transfer": volume_transfer,
                "volume_block_diagnostics": volume_block_diagnostics,
            })
        if got != length:
            result["error"] = (
                "volume_short:%d:%d" % (got, length)
                if source_volume_v1 else "short_read:%d:%d" % (got, length)
            )
        _sickness_attach_reply(result, req, got)
        _emit(result)
    except BaseException as exc:
        err = dict(base)
        err.update({
            "op": "error",
            "error": ("%s:%s" % (type(exc).__name__, exc))[:200],
            "producer_id": int(producer_id),
            "preadv_diagnostics": preadv_diagnostics,
            "fd_key_path": (
                fd_key[0] if fd_key else os.path.normpath(str(req.get("path") or ""))
            ),
            "fd_key_producer": fd_key[1] if fd_key else int(producer_id),
            "fd_open_count": int(fd_open_delta),
            "fd_reuse_count": int(fd_reuse_delta),
            "fd_close_count": int(fd_close_delta),
            "fd_open_wall_ms": round(fd_open_wall_ns / 1e6, 4),
            "fd_close_wall_ms": round(fd_close_wall_ns / 1e6, 4),
            "child_read_start_ns": int(read_start_ns) if read_start_ns is not None else None,
            "child_read_end_ns": int(read_end_ns) if read_end_ns is not None else None,
            "read_duration_ns": (
                int(max(0, read_end_ns - read_start_ns))
                if read_start_ns is not None and read_end_ns is not None else None
            ),
        })
        if private_split_io:
            err.update({
                "split_io": True,
                "private_buffer_bytes": (
                    int(len(private_buffer)) if private_buffer is not None else 0
                ),
                "source_read_duration_ns": (
                    int(max(0, source_read_end_ns - read_start_ns))
                    if read_start_ns is not None and source_read_end_ns is not None
                    else None
                ),
                "private_to_shm_duration_ns": (
                    int(max(0, private_copy_end_ns - private_copy_start_ns))
                    if private_copy_start_ns is not None and private_copy_end_ns is not None
                    else None
                ),
                "worker_index": worker_index,
                "worker_ident": worker_ident,
                "worker_native_id": worker_native_id,
            })
        if source_volume_v1:
            err.update({
                "volume_source": "direct_volume_v1",
                "volume_transfer": volume_transfer,
                "volume_block_diagnostics": volume_block_diagnostics,
            })
        # Diagnostics survive a failed fill exactly as they do on READY.  OFF
        # omits the key entirely so the error reply keeps the control schema.
        _sickness_attach_reply(err, req, got)
        _emit(err)


# Distinct C0 direct Volume V1 treatment: load the stdlib transport module and
# start the child's dedicated transport loop before the worker pool.  A missing
# client/module/auth fails the child launch closed; there is deliberately no
# preadv fallback when the selector is ON.
if source_volume_v1:
    try:
        c0_volume = _volume_load_transport_module()
        _start_volume_transport()
    except BaseException as exc:
        _volume_setup_error = ("%s:%s" % (type(exc).__name__, exc))[:240]

# Forensic child tracer starts before the worker pool and writer thread so
# both thread-entry enable hooks see a live tracer.  OFF is a no-op and the
# pool/writer startup below is identical to the uninstrumented child.
# Frozen mmap source engine: fork every reader process BEFORE any control thread
# starts, so the fork is taken from a single-threaded process.  Readers are
# eager (started here, not on first fill) and hold their own persistent
# descriptors.  OFF starts nothing and this block is a no-op.
_mmap_ready_evidence = {
    "enabled": bool(mmap_engine),
    "source_engine": source_engine,
    "launch_gap_ns": int(MMAP_LAUNCH_GAP_NS) if mmap_engine else None,
    "readers": [],
    "readers_started": 0,
}
if mmap_engine:
    _mmap_spawn_readers()
    _mmap_ready_evidence["readers"] = [
        {"index": r["index"], "pid": r["pid"]} for r in _mmap_readers
    ]
    _mmap_ready_evidence["readers_started"] = len(_mmap_readers)

_start_child_viztracer()
_writer_thread = threading.Thread(target=_writer, daemon=True)
_writer_thread.start()
# Diagnostic watchdog + heartbeat start before the worker pool so a slow first
# production read is already observable.  OFF starts no thread.
if preadv_sickness_diag:
    _start_sickness_heartbeat()
    _sickness_watchdog_thread = threading.Thread(
        target=_sickness_watchdog_loop, name="c0-sickness-watchdog", daemon=True
    )
    _sickness_watchdog_thread.start()
    # Independent, single tripwire handler.  Decoupled from the polling loop so
    # a slow probe matrix cannot delay detection of the next outstanding read.
    _sickness_diag_thread = threading.Thread(
        target=_sickness_diag_worker, name="c0-sickness-diag", daemon=True
    )
    _sickness_diag_thread.start()
_pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="c0-read")

# ── startup barrier: every configured source worker real before ready ────────
# ``ThreadPoolExecutor`` grows threads lazily on submit, so without this warm-up
# the first fill could start worker 0 while the second fill blocks in
# Thread.start/Event.wait behind it.  Submit exactly ``workers`` startup tasks:
# each is a real pool thread, opts into the tracer via the same thread hook the
# fill path uses, records its identity, then rendezvouses on a bounded barrier.
# ``ready_child`` is emitted only after every configured worker has arrived.
# These are the same pool threads that later run ``_do_fill``; no new process or
# persistent-worker architecture is introduced.
_startup_timeout_s = 30.0
_startup_barrier = threading.Barrier(workers)
_startup_lock = threading.Lock()
_startup_threads = {}


def _startup_probe(index):
    _tracer_enable_thread()
    thread = threading.current_thread()
    # Stamp this worker's identity into its thread-local so every later
    # ``_do_fill`` on the same pool thread can report which worker produced the
    # bytes.  When the diagnostic split is ON, allocate exactly one reusable
    # private buffer here -- before the readiness barrier -- so both configured
    # workers are buffer-complete before the child emits ready_child.
    _worker_local.worker_index = int(index)
    _worker_local.worker_ident = int(threading.get_ident())
    _worker_local.worker_native_id = getattr(thread, "native_id", None)
    private_buffer_bytes = 0
    if private_split_io and not mmap_engine:
        private_buffer_bytes = int(len(_worker_private_buffer()))
    info = {
        "index": int(index),
        "name": str(thread.name),
        "ident": int(threading.get_ident()),
        "native_id": getattr(thread, "native_id", None),
        "private_buffer_bytes": private_buffer_bytes,
    }
    with _startup_lock:
        _startup_threads[int(index)] = info
    _startup_barrier.wait(timeout=_startup_timeout_s)
    return info


_startup_t0 = time.perf_counter_ns()
_startup_deadline = time.monotonic() + _startup_timeout_s
_startup_futures = [_pool.submit(_startup_probe, index) for index in range(workers)]
_startup_error = None
_startup_ready = 0
for future in _startup_futures:
    try:
        future.result(timeout=max(0.0, _startup_deadline - time.monotonic()))
        _startup_ready += 1
    except BaseException as exc:
        if _startup_error is None:
            _startup_error = (
                "%s:%s" % (type(exc).__name__, str(exc) or "startup_barrier_unmet")
            )[:200]
_startup_wall_ms = round((time.perf_counter_ns() - _startup_t0) / 1e6, 4)
_startup_evidence = {
    "configured": int(workers),
    "started": len(_startup_threads),
    "ready": int(_startup_ready),
    "wall_ms": _startup_wall_ms,
    "threads": [_startup_threads[index] for index in sorted(_startup_threads)],
}
if (
    _startup_error is not None
    or _startup_ready != workers
    or _volume_setup_error is not None
):
    _emit({
        "op": "startup_failed",
        "pid": os.getpid(),
        "workers_configured": int(workers),
        "workers_ready": int(_startup_ready),
        "startup_wall_ms": _startup_wall_ms,
        "startup_barrier": _startup_evidence,
        "private_split_io": bool(private_split_io),
        "source_volume_v1": bool(source_volume_v1),
        "volume_v1": _volume_evidence(),
        "error": _startup_error
        or _volume_setup_error
        or ("startup_workers_incomplete:%d/%d" % (_startup_ready, workers)),
    })
else:
    _emit({
        "op": "ready_child",
        "pid": os.getpid(),
        "arena_bytes": arena_bytes,
        "slot_count": slot_count,
        "slot_bytes": slot_bytes,
        "workers": workers,
        "workers_configured": int(workers),
        "workers_ready": int(_startup_ready),
        "startup_wall_ms": _startup_wall_ms,
        "startup_barrier": _startup_evidence,
        "source_engine": source_engine,
        "mmap_source": _mmap_ready_evidence,
        "cuda_initialized": False,
        "gpu_alloc_bytes": 0,
        "torch_imported": bool("torch" in sys.modules),
        "child_viztracer": dict(_child_viztracer_status),
        # Diagnostic split evidence: one private buffer per ready worker, plus
        # cheap child runtime markers.  OFF reports 0/None and changes nothing.
        "private_split_io": bool(private_split_io),
        "private_buffer_bytes_per_worker": int(slot_bytes) if private_split_io else 0,
        "private_buffer_owner": (
            "mmap_reader_process" if private_split_io and mmap_engine
            else "source_worker_thread" if private_split_io else None
        ),
        # Distinct C0 direct Volume V1 launch evidence.  OFF is an explicit
        # disabled block; ON reports the resolved transport/session provenance.
        "source_volume_v1": bool(source_volume_v1),
        "volume_v1": _volume_evidence(),
        "runtime_markers": _runtime_markers(),
        # One-time child-side mount identity for /dev/shm (parent-/dev/shm
        # filtered view is captured independently by the parent).
        "mount_identity": _child_mount_identity(["/dev/shm"]),
        # Diagnostic clustered preadv-sickness launch evidence.  OFF omits the
        # key entirely (exact control schema); ON reports the selector, hashes,
        # and the pre-registered control manifest without touching model bytes.
        **_sickness_ready_child_fields(),
    })
try:
    for line in iter(sys.stdin.readline, ""):
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            _emit({"op": "fatal", "error": "bad_json"})
            continue
        op = str(req.get("op") or "")
        if op == "fill":
            _pool.submit(_do_fill, req)
        elif op == "ping":
            _emit({"op": "pong", "request_id": req.get("request_id"), "pid": os.getpid()})
        elif op == "exit":
            break
        else:
            _emit({"op": "error", "request_id": req.get("request_id"), "error": "bad_op:%s" % op})
finally:
    # Drain every in-flight fill before touching the cached descriptors: a
    # fill thread may still be mid-preadv on an ON-path fd.  Only after the
    # pool is quiescent do we close cached descriptors and emit the terminal
    # descriptor snapshot.  ``_finalize_fds`` is idempotent, so the clean
    # ``exit`` path and an unexpected stdin EOF cannot double-finalize.
    # Bounded: a fill thread stuck in a sick preadv must never pin child exit
    # (which previously kept the Modal invocation alive until the 3600s
    # timeout).  Cancel pending work, wait briefly, then proceed; the parent
    # reaps with kill as a final backstop.
    try:
        try:
            _pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            _pool.shutdown(wait=False)
    except Exception:
        pass
    try:
        import threading as _shutdown_th
        _pool_done = _shutdown_th.Event()
        def _await_pool_quiescent():
            try:
                _pool.shutdown(wait=True)
            except Exception:
                pass
            finally:
                _pool_done.set()
        _shutdown_th.Thread(target=_await_pool_quiescent, daemon=True).start()
        _pool_done.wait(timeout=15.0)
    except Exception:
        pass
    _finalize_fds()
    # Stop the forked reader processes (no-op when the mmap engine is OFF).
    try:
        _mmap_shutdown_readers()
    except Exception:
        pass
    # Drain first, then stop/save the child tracer: no worker may still be
    # mid-preadv when the tracer tears down.  CUDA-sterile and descriptor
    # cleanup semantics above are unchanged.
    _stop_child_viztracer()
    # Stop the diagnostic watchdog/heartbeat after the pool is quiescent and
    # emit the terminal diagnostic snapshot on stderr for the parent.
    _sickness_stop.set()
    _sickness_heartbeat_stop.set()
    if preadv_sickness_diag:
        # Bound the join: the handler is a daemon, so a stuck probe must never
        # delay child exit or any production worker's completion.
        try:
            _sickness_trip_queue.put_nowait(None)
        except Exception:
            pass
        if _sickness_diag_thread is not None:
            _sickness_diag_thread.join(timeout=SICKNESS_DIAG_JOIN_S)
        try:
            with _sickness_lock:
                _all_blocks = [
                    json.loads(json.dumps(block, default=str))
                    for block in _sickness_reply_blocks.values()
                ]
            # Bound the terminal payload: a full per-read history (16k+
            # production reads) previously exceeded the 64KB stderr pipe and
            # blocked child exit while the parent was in proc.wait().  Keep
            # summaries, tripwire status, hashes, and the last few blocks;
            # truncate giant arrays explicitly.
            def _truncate_block(block):
                if not isinstance(block, dict):
                    return block
                out = dict(block)
                for key in ("production_reads", "timeline", "active_probes"):
                    val = out.get(key)
                    if isinstance(val, list) and len(val) > 20:
                        out[key] = {
                            "truncated": True,
                            "total": len(val),
                            "last_20": val[-20:],
                        }
                manifest = out.get("control_manifest")
                if isinstance(manifest, dict):
                    files = manifest.get("files")
                    if isinstance(files, dict):
                        out["control_manifest"] = {
                            "roles": sorted(files.keys()),
                            "truncated": True,
                        }
                return out
            if len(_all_blocks) > 8:
                reply_blocks = [_truncate_block(b) for b in _all_blocks[-8:]]
                blocks_truncated = {
                    "truncated": True,
                    "total": len(_all_blocks),
                    "kept": 8,
                }
            else:
                reply_blocks = [_truncate_block(b) for b in _all_blocks]
                blocks_truncated = {"truncated": False, "total": len(_all_blocks)}
            sys.stderr.write(json.dumps({
                "op": "preadv_sickness_child_terminal",
                "schema": SICKNESS_SCHEMA,
                "version": SICKNESS_VERSION,
                "invocation_id": sickness_invocation_id,
                "tripwire_events": list(_sickness_events)[-64:],
                "reply_blocks": reply_blocks,
                "reply_blocks_truncation": blocks_truncated,
                "probes_total": int(_sickness_probe_total),
                "errors": list(_sickness_errors)[-8:],
                "heartbeat": _sickness_heartbeat_snapshot(),
            }, default=str)[:256 * 1024] + "\n")
            sys.stderr.flush()
        except Exception:
            pass
    try:
        out_q.put_nowait(None)
    except Exception:
        pass
    try:
        buf.release()
    except Exception:
        pass
    try:
        shm.close()
    except Exception:
        pass
"""


_C0_RUNTIME: Optional[SharedArenaRing] = None


def arena_runtime_enabled() -> bool:
    return c0_selected()


def ensure_arena_runtime() -> SharedArenaRing:
    """Create/register the single 512 MiB C0 arena + sterile child (idempotent)."""
    global _C0_RUNTIME
    if _C0_RUNTIME is not None and _C0_RUNTIME.created:
        return _C0_RUNTIME
    runtime = SharedArenaRing()
    runtime.ensure()
    _C0_RUNTIME = runtime
    return runtime


def get_arena_runtime() -> Optional[SharedArenaRing]:
    return _C0_RUNTIME


def close_arena_runtime() -> dict:
    global _C0_RUNTIME
    if _C0_RUNTIME is None:
        return {"active": False}
    out = _C0_RUNTIME.close()
    if out.get("cleanup_unresolved"):
        # Unresolved ownership is retained: keep the reference alive rather
        # than letting GC drop the registered mapping.
        return out
    _C0_RUNTIME = None
    return out


def arena_evidence() -> dict:
    if _C0_RUNTIME is None:
        return {"active": False}
    return _C0_RUNTIME.evidence()


_RUNTIME: Optional[SharedBackingRuntime] = None


def loader_enabled() -> bool:
    """True when the V2 two-process loader is enabled (default OFF)."""
    return io_process_v2_enabled()


def ensure_runtime(size_bytes: Optional[int] = None) -> SharedBackingRuntime:
    """Create/register the single reuseable backing + child once (idempotent)."""
    global _RUNTIME
    if _RUNTIME is not None and _RUNTIME.created:
        return _RUNTIME
    runtime = SharedBackingRuntime(int(size_bytes or GOLDEN_IO_V2_BACKING_BYTES))
    runtime.ensure()
    _RUNTIME = runtime
    print(
        "[v2.golden_io_process_v2] "
        f"event=backing_ready bytes={runtime.size_bytes} register_ms={runtime.register_ms} "
        f"child_pid={runtime.child_pid} child_torch_imported={runtime.child_torch_imported}",
        flush=True,
    )
    return runtime


def get_runtime() -> Optional[SharedBackingRuntime]:
    return _RUNTIME


def runtime_evidence() -> dict:
    c0 = arena_evidence()
    if c0.get("active"):
        return c0
    if _RUNTIME is None:
        return {"active": False}
    return _RUNTIME.evidence()


def close_runtime() -> dict:
    global _RUNTIME, _C0_RUNTIME
    out: dict = {}
    if _C0_RUNTIME is not None:
        c0_out = _C0_RUNTIME.close()
        out["c0"] = c0_out
        if not c0_out.get("cleanup_unresolved"):
            _C0_RUNTIME = None
    if _RUNTIME is not None:
        out["backing"] = _RUNTIME.close()
        _RUNTIME = None
    return out or {"active": False}


__all__ = [
    "IO_PROCESS_V2_ENV",
    "IO_PROCESS_V2_BACKING_ENV",
    "IO_PROCESS_V2_SOURCE_GEOMETRY_ENV",
    "IO_PROCESS_V2_STREAMING_ENV",
    "IO_PROCESS_V2_PERSISTENT_FDS_ENV",
    "IO_PROCESS_V2_SOURCE_ENGINE_ENV",
    "resolve_c0_source_engine",
    "c0_mmap_engine_enabled",
    "IO_PROCESS_V2_C0_PRIVATE_SPLIT_IO_ENV",
    "IO_PROCESS_V2_C0_SOURCE_VOLUME_V1_ENV",
    "IO_PROCESS_V2_C0_PREADV_SICKNESS_DIAG_ENV",
    "C0_PREADV_SICKNESS_CONTROLS_ENV",
    "C0_PREADV_SICKNESS_PROFILE_HASH_ENV",
    "C0_PREADV_SICKNESS_CONFIG_HASH_ENV",
    "C0_PREADV_SICKNESS_INVOCATION_ID_ENV",
    "C0_PREADV_SICKNESS_TRIPWIRE_NS",
    "C0_PREADV_SICKNESS_HYPOTHESIS_FAMILIES",
    "C0_PREADV_SICKNESS_HYPOTHESIS_STATUSES",
    "c0_preadv_sickness_diag_enabled",
    "c0_preadv_controls_manifest_path",
    "load_c0_preadv_controls",
    "c0_preadv_sickness_config_hashes",
    "c0_preadv_sickness_invocation_id",
    "C0_SOURCE_VOLUME_ID_ENV",
    "C0_SOURCE_VOLUME_NAME_ENV",
    "C0_SOURCE_VOLUME_MOUNT_ENV",
    "C0_VOLUME_BLOCK_CONCURRENCY",
    "c0_private_split_io_enabled",
    "c0_source_volume_v1_enabled",
    "c0_source_volume_name",
    "c0_source_volume_mount",
    "resolve_c0_source_volume_metadata",
    "platform_runtime_markers",
    "GOLDEN_C0_CHILD_VIZTRACER_ENV",
    "child_viztracer_artifact",
    "child_viztracer_enabled",
    "child_viztracer_output_path",
    "C0_ARENA_BYTES",
    "C0_SLOT_BYTES",
    "C0_SLOT_COUNT",
    "C0_SOURCE_WORKERS",
    "C0_SLOT_OWNERS",
    "C0_CAPACITY_CLASS",
    "C0_SOURCE_GEOMETRY",
    "C0_INFLIGHT_LIMIT",
    "resolve_c0_geometry",
    "C0FillRequest",
    "C0ProtocolError",
    "C0ReplyRegistry",
    "C0StageReader",
    "C0LiveSampler",
    "SharedArenaRing",
    "C0_LIVE_SAMPLER_ENV",
    "c0_live_sampler_enabled",
    "parse_mountinfo_line",
    "read_mount_identity",
    "mincore_residency",
    "probe_source_cache",
    "collect_runtime_identity",
    "arena_evidence",
    "arena_runtime_enabled",
    "c0_selected",
    "c0_transport_dimensions",
    "close_arena_runtime",
    "ensure_arena_runtime",
    "get_arena_runtime",
    "io_process_v2_streaming_enabled",
    "io_process_v2_persistent_fds_enabled",
    "reconcile_destination_coverage",
    "reconcile_source_coverage",
    "source_touch_copy_throughput",
    "validate_fill_reply",
    "validate_fill_request",
    "GOLDEN_IO_V2_BACKING_BYTES",
    "SharedBackingRuntime",
    "close_runtime",
    "ensure_runtime",
    "get_runtime",
    "io_process_v2_enabled",
    "normalize_backing_type",
    "normalize_source_geometry",
    "loader_enabled",
    "run_primitive_probe",
    "runtime_evidence",
]
