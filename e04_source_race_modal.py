"""Dedicated minimal Modal endpoint for the source race oracle.

No Golden harness, no ComfyUI node registry, no sampler, no model
construction.  Two GPU-pinned functions so the H100 and RTX PRO 6000 cohorts
are structurally separate and cannot be pooled.  ``single_use_containers``
gives one fresh container per call.  The image is stdlib-only plus the
``comfymodal_runtime`` source package; the oracle never imports torch/CUDA.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any

import modal


_ROOT = Path(__file__).resolve().parent
_APP_NAME = os.environ.get(
    "COMFYMODAL_SOURCE_RACE_APP_NAME", "sept-clip-source-race-oracle"
)
_MODELS_ROOT = Path("/root/models")
_VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")

# Literal ``modal_gpu`` values from GPU_CATALOG.
_H100_MODAL_GPU = "h100!"
_RTX_MODAL_GPU = "rtx-pro-6000"

_DECLARED_CPU = 12
# The oracle allocates logical_qd * race_width * read_bytes of destination
# buffers (QD2 x width16 x 128 MiB = 4 GiB) on top of the interpreter.
_DECLARED_MEMORY_MB = 16384

_image = modal.Image.debian_slim(python_version="3.11").entrypoint([])
_image = _image.apt_install("gcc", "libc6-dev", "fio")
_image = _image.add_local_file(
    str(_ROOT / "native_canary.c"), "/root/native_canary.c", copy=True
)
_image = _image.add_local_file(
    str(_ROOT / "source_touch.c"), "/root/source_touch.c", copy=True
)
_image = _image.run_commands(
    "gcc -O2 -fPIC -shared -o /opt/native_canary.so /root/native_canary.c -lpthread",
    "test -f /opt/native_canary.so",
    "gcc -O2 -fPIC -shared -o /opt/source_touch.so /root/source_touch.c",
    "test -f /opt/source_touch.so",
)
_image = _image.add_local_python_source("comfymodal_runtime", copy=True)
_image = _image.add_local_file(
    str(_ROOT / "e04_source_race_modal.py"),
    "/root/e04_source_race_modal.py",
    copy=True,
)

_models_volume = modal.Volume.from_name(_VOLUME_NAME, create_if_missing=False)
_models_mount = _models_volume.with_mount_options(read_only=True)

app = modal.App(_APP_NAME, image=_image, include_source=False)


@app.function(
    image=_image,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=900,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
)
def capability_probe(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    block_mib: int = 64,
) -> dict:
    """Phase 0: which mmap advice/residency mechanisms actually work in this runtime.

    CPU-only by construction (no `gpu=` on this function) and it stops at the source
    boundary - it never constructs a model, tensor, or CUDA object.
    """
    import ctypes as ct
    import os
    import time

    libc = ct.CDLL(None, use_errno=True)
    libc.mmap.restype = ct.c_void_p
    libc.mmap.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_int, ct.c_int,
                          ct.c_int, ct.c_longlong]
    libc.munmap.restype = ct.c_int
    libc.munmap.argtypes = [ct.c_void_p, ct.c_size_t]
    libc.madvise.restype = ct.c_int
    libc.madvise.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_int]
    libc.memcpy.restype = ct.c_void_p
    libc.memcpy.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t]

    PROT_READ, MAP_PRIVATE, MAP_POPULATE = 1, 2, 0x08000
    MADV_WILLNEED, MADV_POPULATE_READ, MADV_POPULATE_WRITE = 3, 22, 23
    PAGE = 4096

    def faults():
        try:
            with open("/proc/self/stat", "rb") as fh:
                parts = fh.read().rsplit(b")", 1)[1].split()
            return int(parts[7]), int(parts[9])
        except BaseException:  # noqa: BLE001
            return None, None

    def mincore(addr, length):
        npages = (length + PAGE - 1) // PAGE
        vec = (ct.c_ubyte * npages)()
        ct.set_errno(0)
        try:
            rc = libc.mincore(ct.c_void_p(addr), ct.c_size_t(length), ct.byref(vec))
        except BaseException as exc:  # noqa: BLE001
            return {"callable": False, "error": type(exc).__name__}
        err = ct.get_errno()
        if rc != 0:
            return {"callable": True, "rc": rc, "errno": err, "resident_pages": None}
        return {"callable": True, "rc": 0, "errno": 0, "pages": npages,
                "resident_pages": sum(1 for i in range(npages) if vec[i] & 1)}

    out: dict = {"status": "ok"}
    path = _resolve_model_path(role, model_name)
    size = os.stat(path).st_size
    block = min(int(block_mib) * 1024 * 1024, size)
    try:
        with open("/proc/sys/kernel/osrelease") as fh:
            out["kernel_release"] = fh.read().strip()
    except BaseException:  # noqa: BLE001
        out["kernel_release"] = None
    out["file"] = {"path": str(path), "size": size, "block_bytes": block}
    out["available"] = {"os.O_DIRECT": hasattr(os, "O_DIRECT"),
                        "os.preadv": hasattr(os, "preadv")}

    fd = os.open(path, os.O_RDONLY)
    ct.set_errno(0)
    base = int(libc.mmap(None, size, PROT_READ, MAP_PRIVATE, fd, 0))
    out["plain_mmap"] = {"ok": base not in (0, -1), "errno": ct.get_errno()}
    if base not in (0, -1):
        out["mincore_before_touch"] = mincore(base, block)
        f0 = faults()
        scratch = (ct.c_char * block)()
        t0 = time.perf_counter()
        libc.memcpy(ct.addressof(scratch), ct.c_void_p(base), block)
        out["first_memcpy_block_ms"] = (time.perf_counter() - t0) * 1000.0
        f1 = faults()
        out["faults_during_memcpy"] = {
            "minor": (f1[0] - f0[0]) if (f0[0] is not None and f1[0] is not None) else None,
            "major": (f1[1] - f0[1]) if (f0[1] is not None and f1[1] is not None) else None}
        out["mincore_after_touch"] = mincore(base, block)
        t0 = time.perf_counter()
        libc.memcpy(ct.addressof(scratch), ct.c_void_p(base), block)
        out["second_memcpy_block_ms"] = (time.perf_counter() - t0) * 1000.0
        for name, advice in (("madvise_WILLNEED", MADV_WILLNEED),
                             ("madvise_POPULATE_READ", MADV_POPULATE_READ),
                             ("madvise_POPULATE_WRITE", MADV_POPULATE_WRITE)):
            ct.set_errno(0)
            try:
                rc = libc.madvise(ct.c_void_p(base), ct.c_size_t(block), advice)
                out[name] = {"rc": rc, "errno": ct.get_errno(), "accepted": rc == 0}
            except BaseException as exc:  # noqa: BLE001
                out[name] = {"callable": False, "error": type(exc).__name__}
        try:
            ct.set_errno(0)
            rc = libc.readahead(ct.c_int(fd), ct.c_longlong(0), ct.c_size_t(block))
            out["readahead"] = {"rc": rc, "errno": ct.get_errno()}
        except BaseException as exc:  # noqa: BLE001
            out["readahead"] = {"callable": False, "error": type(exc).__name__}
        libc.munmap(ct.c_void_p(base), size)

    w_len = ((block + PAGE - 1) // PAGE) * PAGE
    ct.set_errno(0)
    t0 = time.perf_counter()
    a2 = int(libc.mmap(None, w_len, PROT_READ, MAP_PRIVATE | MAP_POPULATE, fd, 0))
    out["map_populate_window"] = {
        "ok": a2 not in (0, -1), "errno": ct.get_errno(),
        "map_ms": (time.perf_counter() - t0) * 1000.0}
    if a2 not in (0, -1):
        out["mincore_populate_window"] = mincore(a2, w_len)
        libc.munmap(ct.c_void_p(a2), w_len)

    # Functional MADV_WILLNEED test. mincore is meaningless here, so the only
    # honest test is whether advising BEFORE a cold first touch makes that first
    # touch faster. Two fresh windows over disjoint ranges, same block size.
    def _first_touch_ms(advise):
        """Map a fresh window and return ms to fully touch it once."""
        scratch2 = (ct.c_char * block)()
        w = int(libc.mmap(None, w_len, PROT_READ, MAP_PRIVATE, fd, 0))
        if w in (0, -1):
            return None
        try:
            if advise:
                libc.madvise(ct.c_void_p(w), ct.c_size_t(w_len), MADV_WILLNEED)
            t = time.perf_counter()
            libc.memcpy(ct.addressof(scratch2), ct.c_void_p(w), block)
            return (time.perf_counter() - t) * 1000.0
        finally:
            libc.munmap(ct.c_void_p(w), w_len)

    try:
        cold_a = _first_touch_ms(False)
        advised = _first_touch_ms(True)
        out["willneed_functional_test"] = {
            "cold_first_touch_ms": cold_a,
            "willneed_first_touch_ms": advised,
            "note": ("Same container and file, fresh windows. A real hint would make the "
                     "advised first touch materially faster than the cold one."),
        }
    except BaseException as exc:  # noqa: BLE001
        out["willneed_functional_test"] = {"error": f"{type(exc).__name__}:{str(exc)[:120]}"}

    os.close(fd)
    return out


@app.function(
    image=_image,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=1800,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
)
def fio_source_probe(
    ioengine: str = "pvsync",
    block_mib: int = 64,
    nblocks_per_job: int = 29,
    attempt_id: str = "",
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
) -> dict:
    """Independent fio cross-check: pvsync vs mmap, 4 concurrent independent jobs.

    CPU-only (no `gpu=`). Each job reads its own non-overlapping contiguous quarter.
    Synchronous engines only: `iodepth` is NOT set, because it would not create real
    QD4 for these engines - concurrency comes from the 4 separate job processes.
    """
    import json
    import os
    import subprocess
    import time

    path = _resolve_model_path(role, model_name)
    size = os.stat(path).st_size
    bs = f"{block_mib}m"
    per = int(nblocks_per_job) * int(block_mib) * 1024 * 1024
    stride = (int(nblocks_per_job) + 1) * int(block_mib) * 1024 * 1024

    lines = [
        "[global]",
        f"ioengine={ioengine}",
        "rw=read",
        f"bs={bs}",
        "direct=0",
        "invalidate=0",
        "norandommap=1",
        "group_reporting=1",
        "time_based=0",
        "randrepeat=0",
        "thread=0",
        f"filename={path}",
        "",
    ]
    for j in range(4):
        off = j * stride
        if off + per > size:
            per_j = max(0, size - off)
        else:
            per_j = per
        lines += [f"[job{j}]", f"offset={off}", f"size={per_j}", ""]
    jobfile = "/tmp/fio_source.job"
    with open(jobfile, "w") as fh:
        fh.write("\n".join(lines))

    ver = subprocess.run(["fio", "--version"], capture_output=True, text=True)
    cmd = ["fio", "--output-format=json", jobfile]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    out: dict = {
        "status": "ok",
        "attempt_id": str(attempt_id),
        "ioengine": ioengine,
        "fio_version": (ver.stdout or ver.stderr or "").strip(),
        "jobfile": "\n".join(lines),
        "command": " ".join(cmd),
        "wall_ms": wall_ms,
        "returncode": proc.returncode,
    }
    if proc.returncode != 0:
        out["status"] = "error"
        out["stderr"] = (proc.stderr or "")[:800]
        return out
    try:
        raw = json.loads(proc.stdout)
    except Exception as exc:  # noqa: BLE001
        out["status"] = "error"
        out["parse_error"] = f"{type(exc).__name__}"
        return out

    jobs = []
    total_bw = 0.0
    total_bytes = 0
    for j in raw.get("jobs", []):
        r = j.get("read") or {}
        lat = (r.get("lat_ns") or {}).get("percentile") or {}
        jobs.append({
            "jobname": j.get("jobname"),
            "bw_bytes_per_s": r.get("bw_bytes"),
            "bw_mib_per_s": (r.get("bw_bytes") or 0) / 1024.0 / 1024.0,
            "iops": r.get("iops"),
            "io_bytes": r.get("io_bytes"),
            "runtime_ms": r.get("runtime"),
            "clat_ns_mean": (r.get("clat_ns") or {}).get("mean"),
            "lat_ns_percentile": lat,
        })
        total_bw += float(r.get("bw_bytes") or 0)
        total_bytes += int(r.get("io_bytes") or 0)
    out["jobs"] = jobs
    out["aggregate_bw_mib_per_s"] = total_bw / 1024.0 / 1024.0
    out["aggregate_gbps"] = (total_bytes / (wall_ms / 1000.0) / 1e9) if wall_ms else None
    out["total_io_bytes"] = total_bytes
    out["file_size"] = size
    ident = _identity("", _observed_gpu())
    out["identity"] = ident
    out["provider"] = ident.get("provider")
    out["region"] = ident.get("region")
    out["container_session_id"] = ident.get("container_session_id")
    return out


def _observed_gpu() -> str:
    """Read the real device name without importing torch."""
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return next(
            (line.strip() for line in completed.stdout.splitlines() if line.strip()),
            "",
        )
    except Exception:
        return ""


def _identity(requested_gpu: str, observed_gpu: str) -> dict[str, Any]:
    """Observed container identity. Provider/region are recorded, never pinned."""
    return {
        "provider": os.environ.get("MODAL_CLOUD_PROVIDER", ""),
        "region": os.environ.get("MODAL_REGION", ""),
        "image_id": os.environ.get("MODAL_IMAGE_ID", ""),
        "container_session_id": (
            os.environ.get("CONTAINER_SESSION_ID", "")
            or os.environ.get("MODAL_TASK_ID", "")
        ),
        "hostname": platform.node(),
        "requested_gpu": requested_gpu,
        "observed_gpu": observed_gpu,
        "gpu": observed_gpu,
    }


def _call_id() -> str:
    """Modal call id so a result binds to its dashboard invocation row."""
    try:
        import modal as _modal
        return str(_modal.current_function_call_id() or "")
    except Exception:  # noqa: BLE001
        return ""


def _resolve_model_path(role: str, model_name: str) -> Path:
    """Resolve a basename under the read-only models mount.

    Mirrors comfymodal_runtime.source_ceiling_oracle: CLIP lives in
    text_encoders, UNET in diffusion_models.
    """
    role = str(role).strip().lower()
    model_name = str(model_name).strip()
    if role not in {"clip", "unet"}:
        raise ValueError(f"unsupported_role:{role}")
    if not model_name or Path(model_name).name != model_name:
        raise ValueError("model_name_must_be_a_basename")
    folder = "text_encoders" if role == "clip" else "diffusion_models"
    path = _MODELS_ROOT / folder / model_name
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def _run_source_race(
    requested_gpu: str,
    role: str,
    model_name: str,
    race_width: int,
    logical_qd: int,
    read_bytes: int,
    max_blocks: int,
    fd_mode: str,
    hash_mode: str,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_race_oracle

        engine_result = run_race_oracle(
            file_path=str(path),
            race_width=int(race_width),
            logical_qd=int(logical_qd),
            read_bytes=int(read_bytes),
            fd_mode=str(fd_mode),
            max_blocks=None if int(max_blocks) == 0 else int(max_blocks),
            offset_start=0,
            expected_sha256=None,
            hash_mode=str(hash_mode),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_race_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    race_width: int = 1,
    logical_qd: int = 2,
    read_bytes: int = 134217728,
    max_blocks: int = 0,
    fd_mode: str = "independent",
    hash_mode: str = "winners_in_order",
    attempt_id: str = "",
) -> dict:
    return _run_source_race(
        _H100_MODAL_GPU, role, model_name, race_width, logical_qd,
        read_bytes, max_blocks, fd_mode, hash_mode, attempt_id,
    )


@app.function(
    image=_image,
    gpu=_RTX_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _RTX_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_race_rtx(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    race_width: int = 1,
    logical_qd: int = 2,
    read_bytes: int = 134217728,
    max_blocks: int = 0,
    fd_mode: str = "independent",
    hash_mode: str = "winners_in_order",
    attempt_id: str = "",
) -> dict:
    return _run_source_race(
        _RTX_MODAL_GPU, role, model_name, race_width, logical_qd,
        read_bytes, max_blocks, fd_mode, hash_mode, attempt_id,
    )


def _run_source_conc(
    requested_gpu: str,
    role: str,
    model_name: str,
    widths: Any,
    read_bytes: int,
    attempt_id: str,
    order: str = "forward",
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_concurrency_probe

        engine_result = run_concurrency_probe(
            file_path=str(path),
            widths=tuple(int(w) for w in widths),
            read_bytes=int(read_bytes),
            order=str(order),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_conc_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    widths: tuple = (1, 2, 4, 8, 16),
    read_bytes: int = 134217728,
    attempt_id: str = "",
    order: str = "forward",
) -> dict:
    return _run_source_conc(
        _H100_MODAL_GPU, role, model_name, widths, read_bytes, attempt_id, order,
    )


@app.function(
    image=_image,
    gpu=_RTX_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _RTX_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_conc_rtx(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    widths: tuple = (1, 2, 4, 8, 16),
    read_bytes: int = 134217728,
    attempt_id: str = "",
    order: str = "forward",
) -> dict:
    return _run_source_conc(
        _RTX_MODAL_GPU, role, model_name, widths, read_bytes, attempt_id, order,
    )


def _run_source_roll(
    requested_gpu: str,
    role: str,
    model_name: str,
    workers: Any,
    read_bytes: int,
    blocks_per_worker: int,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_rolling_source_probe

        engine_result = run_rolling_source_probe(
            file_path=str(path),
            workers=tuple(int(w) for w in workers),
            read_bytes=int(read_bytes),
            blocks_per_worker=int(blocks_per_worker),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_roll_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    workers: tuple = (1, 2, 4, 8),
    read_bytes: int = 134217728,
    blocks_per_worker: int = 6,
    attempt_id: str = "",
) -> dict:
    return _run_source_roll(
        _H100_MODAL_GPU, role, model_name, workers, read_bytes,
        blocks_per_worker, attempt_id,
    )


@app.function(
    image=_image,
    gpu=_RTX_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _RTX_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_roll_rtx(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    workers: tuple = (1, 2, 4, 8),
    read_bytes: int = 134217728,
    blocks_per_worker: int = 6,
    attempt_id: str = "",
) -> dict:
    return _run_source_roll(
        _RTX_MODAL_GPU, role, model_name, workers, read_bytes,
        blocks_per_worker, attempt_id,
    )


def _run_source_geom(
    requested_gpu: str,
    role: str,
    model_name: str,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_geometry_sweep

        engine_result = run_geometry_sweep(
            file_path=str(path),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_geom_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    attempt_id: str = "",
) -> dict:
    return _run_source_geom(_H100_MODAL_GPU, role, model_name, attempt_id)


@app.function(
    image=_image,
    gpu=_RTX_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _RTX_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_geom_rtx(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    attempt_id: str = "",
) -> dict:
    return _run_source_geom(_RTX_MODAL_GPU, role, model_name, attempt_id)


def _run_fullfile(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    min_launch_gap_ms: float,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_fullfile_probe

        engine_result = run_fullfile_probe(
            file_path=str(path),
            read_bytes=int(read_mib) * 1024 * 1024,
            qd=int(qd),
            min_launch_gap_ns=int(round(float(min_launch_gap_ms) * 1e6)),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_fullfile_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 128,
    qd: int = 2,
    min_launch_gap_ms: float = 0.0,
    attempt_id: str = "",
) -> dict:
    return _run_fullfile(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, min_launch_gap_ms, attempt_id
    )


def _run_worker_model(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    min_launch_gap_ms: float,
    worker_model: str,
    attempt_id: str,
    pin_cloud: str = "",
    pin_region: str = "",
    hedge_delay_ms: float = 0.0,
    hedge_slots_per_worker: int = 0,
    witness: bool = False,
    hedge_process: bool = False,
    hedge_alt_file: str = "",
    hedge_shift_blocks: int = 0,
    allocator: bool = False,
    sticky_lanes: bool = True,
    selfservice: bool = False,
    split_arm: str = "none",
    mmap_mode: str = "none",
    odirect: bool = False,
    wall_profile: bool = False,
    m0_rescue: bool = False,
    mmap_src: str = "none",
    consume_mode: str = "memcpy",
    touch_ahead: int = 0,
    lifecycle: str = "none",
    populate: bool = False,
    deferred_unmap: bool = False,
    max_retired: int = 2,
    map_shared: bool = False,
    cpu_instrument: bool = False,
    affinity: bool = False,
    fixed_va: bool = False,
) -> dict[str, Any]:
    import time as _time
    _t0 = _time.perf_counter()
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
        "pin_cloud": str(pin_cloud),
        "pin_region": str(pin_region),
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        read_bytes = int(read_mib) * 1024 * 1024
        gap_ns = int(round(float(min_launch_gap_ms) * 1e6))
        if deferred_unmap:
            from comfymodal_runtime.source_race_oracle import run_deferred_unmap_probe

            engine_result = run_deferred_unmap_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                max_retired=int(max_retired),
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif lifecycle in ("whole", "segmented", "fresh"):
            from comfymodal_runtime.source_race_oracle import run_mmap_lifecycle_probe

            engine_result = run_mmap_lifecycle_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                lifecycle=str(lifecycle),
                populate=bool(populate),
                map_shared=bool(map_shared),
                cpu_instrument=bool(cpu_instrument),
                affinity=bool(affinity),
                fixed_va=bool(fixed_va),
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif mmap_src in ("persistent", "window"):
            from comfymodal_runtime.source_race_oracle import run_mmap_source_probe

            engine_result = run_mmap_source_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                mmap_mode=str(mmap_src),
                consume_mode=str(consume_mode),
                touch_ahead=int(touch_ahead),
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif m0_rescue:
            from comfymodal_runtime.source_race_oracle import run_m0_rescue_probe

            engine_result = run_m0_rescue_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                rescue_delay_ns=250_000_000,
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif wall_profile:
            from comfymodal_runtime.source_race_oracle import run_wall_profile_probe

            engine_result = run_wall_profile_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif odirect:
            from comfymodal_runtime.source_race_oracle import run_odirect_rescue_probe

            engine_result = run_odirect_rescue_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                rescue_delay_ns=250_000_000,
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif mmap_mode in ("m0", "m1", "m2"):
            from comfymodal_runtime.source_race_oracle import run_mmap_probe

            engine_result = run_mmap_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                mmap_mode=str(mmap_mode),
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif split_arm in ("2x64", "4x32"):
            from comfymodal_runtime.source_race_oracle import run_split_rescue_probe

            engine_result = run_split_rescue_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                sub_count=(2 if split_arm == "2x64" else 4),
                rescue_delay_ns=250_000_000,
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif selfservice:
            from comfymodal_runtime.source_race_oracle import run_selfservice_allocator_probe

            engine_result = run_selfservice_allocator_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                rescue_delay_ns=250_000_000,
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif allocator:
            from comfymodal_runtime.source_race_oracle import run_greedy_allocator_probe

            engine_result = run_greedy_allocator_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                rescue_delay_ns=250_000_000,
                sticky_lanes=bool(sticky_lanes),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif witness:
            from comfymodal_runtime.source_race_oracle import run_worker_model_witness_probe

            engine_result = run_worker_model_witness_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif hedge_process:
            from comfymodal_runtime.source_race_oracle import (
                run_worker_model_hedge_process_probe,
            )

            engine_result = run_worker_model_hedge_process_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                hedge_delay_ns=int(round(float(hedge_delay_ms or 250.0) * 1e6)),
                hedge_file_path=(str(hedge_alt_file) if hedge_alt_file else None),
                hedge_shift_blocks=int(hedge_shift_blocks),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        elif float(hedge_delay_ms) > 0.0:
            from comfymodal_runtime.source_race_oracle import run_worker_model_hedge_probe

            engine_result = run_worker_model_hedge_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                hedge_delay_ns=int(round(float(hedge_delay_ms) * 1e6)),
                hedge_slots_per_worker=int(hedge_slots_per_worker),
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        else:
            from comfymodal_runtime.source_race_oracle import run_worker_model_probe

            engine_result = run_worker_model_probe(
                file_path=str(path),
                read_bytes=read_bytes,
                qd=int(qd),
                worker_model="processes",
                min_launch_gap_ns=gap_ns,
                requested_gpu=requested_gpu,
                observed_gpu=observed_gpu,
            )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        # ENFORCED FUNNEL: every worker-model engine (present or future) must
        # satisfy the campaign result contract, or fail here loudly instead of
        # making every run in a campaign look invalid.
        from comfymodal_runtime.source_race_oracle import assert_result_contract

        assert_result_contract(
            engine_result, str(engine_result.get("kind") or "unknown_engine"))
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    result["function_wall_ms"] = (_time.perf_counter() - _t0) * 1000.0
    result["modal_call_id"] = _call_id()
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_worker_model_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    min_launch_gap_ms: float = 4.0,
    worker_model: str = "threads",
    attempt_id: str = "",
    pin_cloud: str = "",
    pin_region: str = "",
    hedge_delay_ms: float = 0.0,
    hedge_slots_per_worker: int = 0,
    witness: bool = False,
    hedge_process: bool = False,
    hedge_alt_file: str = "",
    hedge_shift_blocks: int = 0,
    allocator: bool = False,
    sticky_lanes: bool = True,
    selfservice: bool = False,
    split_arm: str = "none",
    mmap_mode: str = "none",
    odirect: bool = False,
    wall_profile: bool = False,
    m0_rescue: bool = False,
    mmap_src: str = "none",
    consume_mode: str = "memcpy",
    touch_ahead: int = 0,
    lifecycle: str = "none",
    populate: bool = False,
    deferred_unmap: bool = False,
    max_retired: int = 2,
    map_shared: bool = False,
    cpu_instrument: bool = False,
    affinity: bool = False,
    fixed_va: bool = False,
) -> dict:
    return _run_worker_model(
        _H100_MODAL_GPU,
        role,
        model_name,
        read_mib,
        qd,
        min_launch_gap_ms,
        worker_model,
        attempt_id,
        pin_cloud,
        pin_region,
        hedge_delay_ms=hedge_delay_ms,
        hedge_slots_per_worker=hedge_slots_per_worker,
        witness=witness,
        hedge_process=hedge_process,
        hedge_alt_file=hedge_alt_file,
        hedge_shift_blocks=hedge_shift_blocks,
        allocator=allocator,
        sticky_lanes=sticky_lanes,
        selfservice=selfservice,
        split_arm=split_arm,
        mmap_mode=mmap_mode,
        odirect=odirect,
        wall_profile=wall_profile,
        m0_rescue=m0_rescue,
        mmap_src=mmap_src,
        consume_mode=consume_mode,
        touch_ahead=touch_ahead,
        lifecycle=lifecycle,
        populate=populate,
        deferred_unmap=deferred_unmap,
        max_retired=max_retired,
        map_shared=map_shared,
        cpu_instrument=cpu_instrument,
        affinity=affinity,
        fixed_va=fixed_va,
    )


def _run_hedge(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    min_launch_gap_ms: float,
    hedge_delay_ms: float,
    hedge_slots_per_worker: int,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_hedge_probe

        engine_result = run_hedge_probe(
            file_path=str(path),
            read_bytes=int(read_mib) * 1024 * 1024,
            qd=int(qd),
            min_launch_gap_ns=int(round(float(min_launch_gap_ms) * 1e6)),
            hedge_delay_ns=int(round(float(hedge_delay_ms) * 1e6)),
            hedge_slots_per_worker=int(hedge_slots_per_worker),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_hedge_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    min_launch_gap_ms: float = 4.0,
    hedge_delay_ms: float = 0.0,
    hedge_slots_per_worker: int = 3,
    attempt_id: str = "",
) -> dict:
    return _run_hedge(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, min_launch_gap_ms,
        hedge_delay_ms, hedge_slots_per_worker, attempt_id,
    )


@app.function(
    image=_image,
    gpu=_RTX_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _RTX_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_worker_model_rtx(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    min_launch_gap_ms: float = 4.0,
    worker_model: str = "",
    attempt_id: str = "",
    pin_cloud: str = "",
    pin_region: str = "",
    hedge_delay_ms: float = 0.0,
    hedge_slots_per_worker: int = 0,
    witness: bool = False,
    hedge_process: bool = False,
    hedge_alt_file: str = "",
    hedge_shift_blocks: int = 0,
    allocator: bool = False,
    sticky_lanes: bool = True,
    selfservice: bool = False,
    split_arm: str = "none",
    mmap_mode: str = "none",
    odirect: bool = False,
    wall_profile: bool = False,
    m0_rescue: bool = False,
    mmap_src: str = "none",
    consume_mode: str = "memcpy",
    touch_ahead: int = 0,
    lifecycle: str = "none",
    populate: bool = False,
    deferred_unmap: bool = False,
    max_retired: int = 2,
    map_shared: bool = False,
    cpu_instrument: bool = False,
    affinity: bool = False,
    fixed_va: bool = False,
) -> dict:
    return _run_worker_model(
        _RTX_MODAL_GPU,
        role,
        model_name,
        read_mib,
        qd,
        min_launch_gap_ms,
        worker_model,
        attempt_id,
        pin_cloud,
        pin_region,
        hedge_delay_ms=hedge_delay_ms,
        hedge_slots_per_worker=hedge_slots_per_worker,
        witness=witness,
        hedge_process=hedge_process,
        hedge_alt_file=hedge_alt_file,
        hedge_shift_blocks=hedge_shift_blocks,
        allocator=allocator,
        sticky_lanes=sticky_lanes,
        selfservice=selfservice,
        split_arm=split_arm,
        mmap_mode=mmap_mode,
        odirect=odirect,
        wall_profile=wall_profile,
        m0_rescue=m0_rescue,
        mmap_src=mmap_src,
        consume_mode=consume_mode,
        touch_ahead=touch_ahead,
        lifecycle=lifecycle,
        populate=populate,
        deferred_unmap=deferred_unmap,
        max_retired=max_retired,
        map_shared=map_shared,
        cpu_instrument=cpu_instrument,
        affinity=affinity,
        fixed_va=fixed_va,
    )


def _gpu_telemetry(engine_result: dict, consumer_state: dict) -> dict:
    """Combine source and H2D clocks into the two authoritative walls."""
    gpu = dict(consumer_state)
    records = engine_result.get("physical_attempts_log") or []
    last_done = consumer_state.get("last_done_ns")
    if records and last_done is not None:
        first = min(int(r["preadv_enter_ns"]) for r in records)
        last = max(int(r["preadv_exit_ns"]) for r in records)
        gpu["source_first_enter_ns"] = first
        gpu["source_last_exit_ns"] = last
        gpu["source_wall_ms"] = (last - first) / 1e6
        gpu["gpu_ready_wall_ms"] = (int(last_done) - first) / 1e6
        gpu["exposed_h2d_tail_ms"] = (int(last_done) - last) / 1e6
    cov = engine_result.get("coverage") or {}
    expected = cov.get("blocks_expected")
    gpu["blocks_expected"] = expected
    gpu["coverage_offsets_exact"] = bool(
        expected is not None
        and consumer_state.get("coverage_offsets") == expected
        and consumer_state.get("coverage_exact"))
    return gpu


def _run_mmap_gpu(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    min_launch_gap_ms: float,
    mode: str,
    slots: int,
    attempt_id: str,
    verify: bool,
) -> dict[str, Any]:
    """Minimal additive GPU variant of the frozen fresh-window mmap harness.

    mode="private"    : staging disabled - byte-identical to the frozen CPU harness.
    mode="shared"     : produced bytes land in POSIX shared-memory staging (Phase 1).
    mode="registered" : staging is additionally CUDA-pinned (Phase 2).
    mode="h2d"        : blocks are cudaMemcpyAsync'd to the GPU as produced (Phase 3).

    The reader processes never touch CUDA; all CUDA stays in this parent process.
    """
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
        "gpu_mode": str(mode),
        "staging_slots": int(slots),
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        read_bytes = int(read_mib) * 1024 * 1024
        from comfymodal_runtime.source_race_oracle import run_mmap_source_probe
        from comfymodal_runtime import source_race_gpu

        staging = None
        consumer = None
        consumer_state: dict[str, Any] = {}
        reg_state: dict[str, Any] = {}
        gpu_bytes = os.path.getsize(str(path)) if str(mode) == "h2d" else 0

        def _on_ready() -> None:
            assert staging is not None
            try:
                reg_state.update(source_race_gpu.setup_cuda(staging, str(mode), gpu_bytes))
            except Exception as exc:  # noqa: BLE001
                reg_state["registered"] = False
                reg_state["register_error"] = f"{type(exc).__name__}:{str(exc)[:300]}"

        on_ready = None
        if str(mode) != "private":
            staging = source_race_gpu.build_staging(int(qd), int(slots), read_bytes)
            consumer, consumer_state = source_race_gpu.start_consumer(
                staging, int(qd), read_bytes, str(mode), verify=bool(verify), file_path=str(path))
            if str(mode) in ("registered", "h2d"):
                on_ready = _on_ready
        engine_result = run_mmap_source_probe(
            file_path=str(path),
            read_bytes=read_bytes,
            qd=int(qd),
            mmap_mode="window",
            consume_mode="memcpy",
            staging=staging,
            on_ready=on_ready,
            min_launch_gap_ns=int(round(float(min_launch_gap_ms) * 1e6)),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
            ready_timeout_s=120.0,
            max_idle_s=60.0,
        )
        if consumer is not None:
            assert staging is not None
            staging["alive"].value = 0
            consumer.join(timeout=300.0)
            engine_result["staging_consumer"] = dict(consumer_state)
            if consumer.is_alive():
                engine_result["staging_consumer"]["consumer_alive_after_join"] = True
            if str(mode) in ("registered", "h2d"):
                engine_result["staging_registration"] = dict(reg_state)
                if not reg_state.get("registered"):
                    raise RuntimeError(
                        f"staging_registration_failed:{reg_state.get('register_error')}")
            if str(mode) == "h2d":
                engine_result["gpu"] = _gpu_telemetry(engine_result, consumer_state)
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:800]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_mmap_gpu_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    min_launch_gap_ms: float = 4.0,
    mode: str = "shared",
    slots: int = 2,
    attempt_id: str = "",
    verify: bool = False,
) -> dict:
    import time as _time
    _t0 = _time.perf_counter()
    result = _run_mmap_gpu(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, min_launch_gap_ms,
        mode, slots, attempt_id, verify,
    )
    result["function_wall_ms"] = (_time.perf_counter() - _t0) * 1000.0
    result["modal_call_id"] = _call_id()
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=300,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def cuda_h2d_probe_h100(n_bytes: int = 67108864) -> dict:
    """Bounded CUDA H2D self-test: pin -> HtoDAsync -> event -> DtoH -> compare."""
    import ctypes as ct
    import hashlib
    import time as _time

    from comfymodal_runtime import source_race_gpu as g

    out: dict = {"status": "ok"}
    try:
        lib = g._load_driver()
        g._check(lib["cuInit"](0), "cuInit")
        dev = ct.c_int()
        g._check(lib["cuDeviceGet"](ct.byref(dev), 0), "cuDeviceGet")
        name = ct.create_string_buffer(128)
        lib["cuDeviceGetName"](name, 128, dev)
        ctx = ct.c_void_p()
        g._check(lib["cuCtxCreate_v2"](ct.byref(ctx), 0, dev), "cuCtxCreate")
        out["device"] = name.value.decode("utf-8", "replace").split("\x00")[0]
        buf = (ct.c_char * int(n_bytes))()
        t0 = _time.perf_counter()
        g._check(lib["cuMemHostRegister_v2"](
            ct.addressof(buf), ct.c_size_t(int(n_bytes)), ct.c_uint(0)), "cuMemHostRegister")
        out["register_ms"] = (_time.perf_counter() - t0) * 1000.0
        ct.memset(ct.addressof(buf), 0x5A, int(n_bytes))
        dptr = ct.c_uint64(0)
        g._check(lib["cuMemAlloc_v2"](ct.byref(dptr), ct.c_size_t(int(n_bytes))), "cuMemAlloc")
        stream = ct.c_void_p()
        g._check(lib["cuStreamCreate"](ct.byref(stream), ct.c_uint(1)), "cuStreamCreate")
        ev = ct.c_void_p()
        g._check(lib["cuEventCreate"](ct.byref(ev), ct.c_uint(0)), "cuEventCreate")
        t0 = _time.perf_counter()
        g._check(lib["cuMemcpyHtoDAsync_v2"](
            dptr, ct.c_void_p(ct.addressof(buf)), ct.c_size_t(int(n_bytes)), stream), "cuMemcpyHtoDAsync")
        g._check(lib["cuEventRecord"](ev, stream), "cuEventRecord")
        done = g._wait_event(lib, ev, 30.0)
        out["h2d_ms"] = (_time.perf_counter() - t0) * 1000.0
        out["event_done"] = bool(done)
        if done:
            back = (ct.c_char * int(n_bytes))()
            g._check(lib["cuMemcpyDtoH_v2"](ct.addressof(back), dptr, ct.c_size_t(int(n_bytes))), "cuMemcpyDtoH")
            out["match"] = (hashlib.sha256(bytes(back)).hexdigest() == hashlib.sha256(bytes(buf)).hexdigest())
    except Exception as exc:  # noqa: BLE001
        out["status"] = "error"
        out["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    return out


@app.function(
    image=_image,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
)
def run_worker_model_cpu(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    min_launch_gap_ms: float = 4.0,
    worker_model: str = "",
    attempt_id: str = "",
    pin_cloud: str = "",
    pin_region: str = "",
    hedge_delay_ms: float = 0.0,
    hedge_slots_per_worker: int = 0,
    witness: bool = False,
    hedge_process: bool = False,
    hedge_alt_file: str = "",
    hedge_shift_blocks: int = 0,
    allocator: bool = False,
    sticky_lanes: bool = True,
    selfservice: bool = False,
    split_arm: str = "none",
    mmap_mode: str = "none",
    odirect: bool = False,
    wall_profile: bool = False,
    m0_rescue: bool = False,
    mmap_src: str = "none",
    consume_mode: str = "memcpy",
    touch_ahead: int = 0,
    lifecycle: str = "none",
    populate: bool = False,
    deferred_unmap: bool = False,
    max_retired: int = 2,
    map_shared: bool = False,
    cpu_instrument: bool = False,
    affinity: bool = False,
    fixed_va: bool = False,
) -> dict:
    """CPU-only worker-model wrapper: identical dispatch, NO gpu= argument.

    These source engines never touch the GPU, so the same experiment runs without
    allocating one.  Placement class differs from the H100 wrappers.
    """
    return _run_worker_model(
        "",
        role,
        model_name,
        read_mib,
        qd,
        min_launch_gap_ms,
        worker_model,
        attempt_id,
        pin_cloud,
        pin_region,
        hedge_delay_ms=hedge_delay_ms,
        hedge_slots_per_worker=hedge_slots_per_worker,
        witness=witness,
        hedge_process=hedge_process,
        hedge_alt_file=hedge_alt_file,
        hedge_shift_blocks=hedge_shift_blocks,
        allocator=allocator,
        sticky_lanes=sticky_lanes,
        selfservice=selfservice,
        split_arm=split_arm,
        mmap_mode=mmap_mode,
        odirect=odirect,
        wall_profile=wall_profile,
        m0_rescue=m0_rescue,
        mmap_src=mmap_src,
        consume_mode=consume_mode,
        touch_ahead=touch_ahead,
        lifecycle=lifecycle,
        populate=populate,
        deferred_unmap=deferred_unmap,
        max_retired=max_retired,
        map_shared=map_shared,
        cpu_instrument=cpu_instrument,
        affinity=affinity,
        fixed_va=fixed_va,
    )


@app.function(
    image=_image,
    gpu=_RTX_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _RTX_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_fullfile_rtx(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 128,
    qd: int = 2,
    min_launch_gap_ms: float = 0.0,
    attempt_id: str = "",
) -> dict:
    return _run_fullfile(
        _RTX_MODAL_GPU, role, model_name, read_mib, qd, min_launch_gap_ms, attempt_id
    )


def _run_startup_arm(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    arm: str,
    stagger_ms: int,
    attempt_id: str,
    primer_bytes: int = 0,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_startup_arm_probe

        engine_result = run_startup_arm_probe(
            file_path=str(path),
            read_bytes=int(read_mib) * 1024 * 1024,
            qd=int(qd),
            arm=str(arm),
            stagger_ms=int(stagger_ms),
            primer_bytes=int(primer_bytes) or None,
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_startup_arm_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    arm: str = "control",
    stagger_ms: int = 250,
    attempt_id: str = "",
    primer_bytes: int = 0,
) -> dict:
    return _run_startup_arm(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, arm, stagger_ms,
        attempt_id, primer_bytes,
    )


def _run_primer_mechanism(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    arm: str,
    wait_target_ms: float,
    attempt_id: str,
    primer_size_override: int = 0,
    primer_count_override: int = 0,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_primer_mechanism_probe

        engine_result = run_primer_mechanism_probe(
            file_path=str(path),
            arm=str(arm),
            read_bytes=int(read_mib) * 1024 * 1024,
            qd=int(qd),
            wait_target_ms=float(wait_target_ms),
            primer_size_override=int(primer_size_override) or None,
            primer_count_override=int(primer_count_override) or None,
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_primer_mechanism_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    arm: str = "A",
    wait_target_ms: float = 135.0,
    attempt_id: str = "",
    primer_size_override: int = 0,
    primer_count_override: int = 0,
) -> dict:
    return _run_primer_mechanism(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, arm, wait_target_ms,
        attempt_id, primer_size_override, primer_count_override,
    )


def _run_flight_recorder(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    sample_ms: int,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_flight_recorder_probe

        engine_result = run_flight_recorder_probe(
            file_path=str(path),
            read_bytes=int(read_mib) * 1024 * 1024,
            qd=int(qd),
            sample_ms=int(sample_ms),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_flight_recorder_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    sample_ms: int = 15,
    attempt_id: str = "",
) -> dict:
    return _run_flight_recorder(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, sample_ms, attempt_id,
    )


_ALT_VOLUME_FILE = "/root/models/diffusion_models/z_image_turbo_bf16.safetensors"


def _run_cross_source(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    probe_mib: int,
    trigger_ms: int,
    clean_probe_at_ms: int,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_cross_source_probe

        engine_result = run_cross_source_probe(
            file_path=str(path),
            alternate_file_path=_ALT_VOLUME_FILE,
            read_bytes=int(read_mib) * 1024 * 1024,
            qd=int(qd),
            probe_bytes=int(probe_mib) * 1024 * 1024,
            trigger_ms=int(trigger_ms),
            clean_probe_at_ms=int(clean_probe_at_ms),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_cross_source_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    probe_mib: int = 4,
    trigger_ms: int = 250,
    clean_probe_at_ms: int = 0,
    attempt_id: str = "",
) -> dict:
    return _run_cross_source(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, probe_mib,
        trigger_ms, clean_probe_at_ms, attempt_id,
    )


def _run_sentinel(
    requested_gpu: str,
    role: str,
    model_name: str,
    read_mib: int,
    qd: int,
    diagnostics: bool,
    sentinel_kib: int,
    sentinel_cadence_ms: int,
    settle_ms: int,
    native_canary: bool,
    attempt_id: str,
) -> dict[str, Any]:
    observed_gpu = _observed_gpu()
    identity = _identity(requested_gpu, observed_gpu)
    result: dict[str, Any] = {
        "role": str(role).strip().lower(),
        "attempt_id": str(attempt_id),
        "model_name": str(model_name).strip(),
        "identity": identity,
    }
    try:
        path = _resolve_model_path(role, model_name)
        result["resolved_path"] = str(path)
        from comfymodal_runtime.source_race_oracle import run_sentinel_probe

        engine_result = run_sentinel_probe(
            file_path=str(path),
            alternate_file_path=_ALT_VOLUME_FILE,
            read_bytes=int(read_mib) * 1024 * 1024,
            qd=int(qd),
            sentinel_bytes=int(sentinel_kib) * 1024,
            sentinel_cadence_ms=int(sentinel_cadence_ms),
            settle_ms=int(settle_ms),
            diagnostics=bool(diagnostics),
            native_canary=bool(native_canary),
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        if not isinstance(engine_result, dict):
            raise TypeError(f"engine_returned_{type(engine_result).__name__}")
        result.update(engine_result)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        result["status"] = "error"
    result["identity"] = identity
    result["requested_gpu"] = requested_gpu
    result["observed_gpu"] = observed_gpu
    result["provider"] = identity["provider"]
    result["region"] = identity["region"]
    result["container_session_id"] = identity["container_session_id"]
    result["image_id"] = identity["image_id"]
    result["hostname"] = identity["hostname"]
    result.setdefault("status", "ok")
    return result


@app.function(
    image=_image,
    gpu=_H100_MODAL_GPU,
    cpu=_DECLARED_CPU,
    memory=_DECLARED_MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={str(_MODELS_ROOT): _models_mount},
    env={
        "COMFYMODAL_V2_GPU": _H100_MODAL_GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_sentinel_h100(
    role: str = "clip",
    model_name: str = "qwen_3_4b.safetensors",
    read_mib: int = 64,
    qd: int = 4,
    diagnostics: bool = True,
    sentinel_kib: int = 256,
    sentinel_cadence_ms: int = 25,
    settle_ms: int = 0,
    native_canary: bool = True,
    attempt_id: str = "",
) -> dict:
    return _run_sentinel(
        _H100_MODAL_GPU, role, model_name, read_mib, qd, diagnostics,
        sentinel_kib, sentinel_cadence_ms, settle_ms, native_canary, attempt_id,
    )


@app.function(
    image=_image,
    cpu=1,
    memory=512,
    timeout=300,
    retries=0,
    single_use_containers=True,
)
def probe_platform() -> dict:
    """Read-only gVisor platform identification. No GPU, no model, no benchmarks."""
    import subprocess

    def sh(cmd: str, limit: int = 3000) -> str:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=25)
            return ((r.stdout or "") + (r.stderr or ""))[:limit]
        except Exception as exc:  # noqa: BLE001
            return f"ERR {type(exc).__name__}:{exc}"

    env_hits = {
        k: v[:200] for k, v in os.environ.items()
        if any(s in k.upper() for s in
               ("MODAL", "GVISOR", "RUNSC", "SANDBOX", "PLATFORM", "CONTAINER",
                "HOST", "KERNEL", "SECCOMP"))
    }
    return {
        "uname_a": sh("uname -a"),
        "proc_version": sh("cat /proc/version"),
        "osrelease": sh("cat /proc/sys/kernel/osrelease; cat /proc/sys/kernel/version"),
        "proc_self_status": sh("cat /proc/self/status"),
        "tracerpid_line": sh("grep -i tracer /proc/self/status /proc/1/status 2>&1"),
        "seccomp_line": sh("grep -i seccomp /proc/self/status"),
        "which_runsc": sh("which runsc; command -v runsc; ls -la /usr/local/bin/ 2>&1 | head -40"),
        "runsc_version": sh("runsc --version 2>&1 | head -20"),
        "proc1_cmdline": sh("tr '\\0' ' ' < /proc/1/cmdline; echo; ls -la /proc/1/ 2>&1 | head"),
        "task_count": sh("ls /proc/self/task | wc -l"),
        "ps_elf": sh("ps -eLf 2>&1 | head -40"),
        "env_hits": env_hits,
        "maps_head": sh("head -50 /proc/self/maps"),
        "dev_shm": sh("ls -la /dev/shm 2>&1 | head -20"),
        "mounts": sh("cat /proc/self/mountinfo 2>&1 | head -30"),
        "root_bins": sh("ls / 2>&1; echo ---; ls /usr/local/bin 2>&1 | head -30"),
        "hostproc": sh("ls -la /proc/ 2>&1 | head -30"),
        "cgroup": sh("cat /proc/self/cgroup; echo ---; cat /proc/1/cgroup"),
        "capabilities": sh("grep -i cap /proc/self/status"),
        "systrap_strings": sh(
            "ls -la /proc/self/ | head -20; echo ---; "
            "find / -maxdepth 3 -name '*runsc*' -o -maxdepth 3 -name '*systrap*' 2>/dev/null | head -20"
        ),
    }
