"""Durable, identity-checked Triton cache handling for Golden H100.

This module deliberately does not replace or wrap Triton's JIT.  The builder
invokes the installed Triton/PyTorch code and records the files that those
implementations create.  Request containers only hydrate a cache whose
software, CUDA, GPU, and specialization identities match exactly.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping


TRITON_CACHE_SCHEMA = 1
TRITON_CACHE_DIR = "/tmp/triton_cache"
TRITON_CACHE_VOLUME_NAME = "comfymodal-triton-cache-h100-sm90"
TRITON_CACHE_VOLUME_PATH = "/mnt/comfymodal_triton_cache"
TRITON_CACHE_MANIFEST = "comfymodal_triton_cache_manifest.json"
_COMPILE_EVENTS: list[dict[str, Any]] = []


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    return value


def cache_identity(
    *,
    triton_version: str,
    torch_version: str,
    cuda_version: str,
    target_arch: str,
    device_name: str = "",
    specialization: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the complete identity used for cache reuse decisions."""
    required = ("B", "M", "N", "dtype", "BLOCK_M", "BLOCK_N")
    missing = [name for name in required if name not in specialization]
    if missing:
        raise ValueError("specialization missing: " + ", ".join(missing))
    return {
        "schema": TRITON_CACHE_SCHEMA,
        "triton_version": str(triton_version),
        "torch_version": str(torch_version),
        "cuda_version": str(cuda_version),
        "target_arch": str(target_arch),
        "device_name": str(device_name),
        "specialization": _jsonable(dict(specialization)),
    }


def cache_compatible(
    manifest: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> bool:
    """Return true only for an exact, schema-versioned identity match."""
    if not isinstance(manifest, Mapping):
        return False
    actual = manifest.get("identity")
    return isinstance(actual, Mapping) and dict(actual) == dict(expected)


def manifest_path(root: str | os.PathLike[str]) -> Path:
    return Path(root) / TRITON_CACHE_MANIFEST


def read_manifest(root: str | os.PathLike[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(manifest_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def write_manifest(root: str | os.PathLike[str], payload: Mapping[str, Any]) -> Path:
    target = manifest_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_jsonable(dict(payload)), handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target


def cache_files(root: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Return stable file evidence without following symlinks."""
    base = Path(root)
    result: list[dict[str, Any]] = []
    if not base.is_dir():
        return result
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        result.append({
            "path": path.relative_to(base).as_posix(),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        })
    return result


def hydrate_cache(
    *,
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
    expected_identity: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Copy a valid Volume cache into Triton's request cache directory.

    A missing or stale cache is deliberately a non-fatal result: Triton then
    follows its ordinary request-time compile path.  No compiler is called by
    this function.
    """
    source_path = Path(source)
    target_path = Path(target)
    manifest = read_manifest(source_path)
    if expected_identity is not None and not cache_compatible(manifest, expected_identity):
        if target_path.is_dir():
            for child in target_path.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        return {"status": "stale_or_missing", "source": str(source_path)}
    if not source_path.is_dir() or manifest is None:
        return {"status": "stale_or_missing", "source": str(source_path)}

    target_path.mkdir(parents=True, exist_ok=True)
    for child in target_path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    copied = 0
    for item in cache_files(source_path):
        relative = Path(str(item["path"]))
        source_file = source_path / relative
        target_file = target_path / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        copied += 1
    return {
        "status": "hydrated",
        "source": str(source_path),
        "target": str(target_path),
        "files": copied,
        "manifest_mtime_ns": manifest_path(source_path).stat().st_mtime_ns,
    }


def runtime_identity() -> dict[str, Any]:
    """Read identity from the currently running H100 container."""
    import torch  # noqa: PLC0415
    import triton  # noqa: PLC0415

    major, minor = torch.cuda.get_device_capability()
    device_name = str(torch.cuda.get_device_name())
    return {
        "triton_version": str(getattr(triton, "__version__", "")),
        "torch_version": str(torch.__version__),
        "cuda_version": str(getattr(torch.version, "cuda", "") or ""),
        "target_arch": f"sm{major}{minor}",
        "device_name": device_name,
    }


def install_compile_observer() -> dict[str, Any]:
    """Install Triton's own post-compile hook, without replacing JIT code."""
    try:
        from triton import knobs  # noqa: PLC0415

        def _hook(*args: Any, **kwargs: Any) -> None:
            _COMPILE_EVENTS.append({
                "args": [type(value).__name__ for value in args],
                "kwargs": sorted(str(key) for key in kwargs),
                "time_ns": time.time_ns(),
            })

        knobs.runtime.jit_post_compile_hook = _hook
        return {"installed": True}
    except Exception as exc:  # pragma: no cover - Triton-only runtime branch
        return {"installed": False, "reason": type(exc).__name__}


def compile_events() -> list[dict[str, Any]]:
    return [dict(event) for event in _COMPILE_EVENTS]


def reset_compile_events() -> None:
    del _COMPILE_EVENTS[:]


def build_cache(
    *,
    cache_root: str | os.PathLike[str],
    specialization: Mapping[str, Any],
) -> dict[str, Any]:
    """Build genuine helper and kernel artifacts using installed runtimes.

    ``specialization`` must come from a real CLIP RoPE observation.  Refusing
    an omitted shape is intentional; this method must never invent a warm-up
    shape.
    """
    identity_parts = runtime_identity()
    if identity_parts["target_arch"] != "sm90" or "H100" not in identity_parts["device_name"]:
        raise RuntimeError("triton_cache_builder_requires_sm90")
    root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    # This is a dedicated Volume, not a shared application cache.  Start from
    # an empty root so every recorded artifact was produced by this exact H100
    # build rather than silently mixing identities from an older build.
    for child in root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    os.environ["TRITON_CACHE_DIR"] = str(root)
    before = {row["path"] for row in cache_files(root)}

    # This is the module-level helper in Triton 3.8.0.  CudaUtils.__init__
    # calls it and Triton owns the resulting .so cache key and file format.
    import triton.backends.nvidia.driver as driver  # noqa: PLC0415
    from triton.backends.nvidia.driver import CudaUtils  # noqa: PLC0415

    helper = CudaUtils()
    after_helper = cache_files(root)
    helper_before_kernel = {row["path"] for row in after_helper}
    helper_created = [row for row in after_helper if row["path"] not in before]

    # The PyTorch native op is the real dispatch path used by CLIP RoPE.  The
    # supplied dimensions are validated by the caller and are not replaced by
    # a synthetic candidate here.  Calling torch.bmm lets the installed
    # dispatch override and Triton produce its own genuine artifact.
    import torch  # noqa: PLC0415
    b = int(specialization["B"])
    m = int(specialization["M"])
    n = int(specialization["N"])
    dtype_name = str(specialization["dtype"])
    dtype = getattr(torch, dtype_name.removeprefix("torch."), None)
    if dtype is None:
        raise ValueError(f"unsupported specialization dtype: {dtype_name}")
    a = torch.empty((b, m, 1), device="cuda", dtype=dtype)
    rhs = torch.empty((b, 1, n), device="cuda", dtype=dtype)
    torch.bmm(a, rhs)
    torch.cuda.synchronize()

    after = cache_files(root)
    kernel_created = [
        row for row in after if row["path"] not in helper_before_kernel
    ]
    created = [row for row in after if row["path"] not in before]
    if not helper_created or not kernel_created:
        raise RuntimeError("triton_cache_builder_created_no_artifacts")
    identity = cache_identity(
        **identity_parts,
        specialization=specialization,
    )
    manifest = {
        "schema": TRITON_CACHE_SCHEMA,
        "created_at": time.time(),
        "identity": identity,
        "helper": {
            "module": str(driver.__file__),
            "class": type(helper).__name__,
            "artifacts": helper_created,
        },
        "kernel": {
            "dispatch": "torch.bmm -> aten::bmm Triton override",
            "artifacts": kernel_created,
        },
        "files": after,
    }
    write_manifest(root, manifest)
    return {
        "status": "built",
        "identity": identity,
        "manifest": str(manifest_path(root)),
        "created_files": created,
    }


__all__ = [
    "TRITON_CACHE_DIR",
    "TRITON_CACHE_MANIFEST",
    "TRITON_CACHE_VOLUME_NAME",
    "TRITON_CACHE_VOLUME_PATH",
    "build_cache",
    "cache_compatible",
    "cache_files",
    "cache_identity",
    "compile_events",
    "hydrate_cache",
    "install_compile_observer",
    "manifest_path",
    "read_manifest",
    "runtime_identity",
    "reset_compile_events",
    "write_manifest",
]
