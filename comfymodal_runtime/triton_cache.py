"""Durable, identity-checked Triton cache handling for Golden H100.

This module deliberately does not replace or wrap Triton's JIT.  The builder
invokes the installed Triton/PyTorch code and records the files that those
implementations create.  Request containers only hydrate a cache whose
software, CUDA, GPU, and specialization identities match exactly.
"""

from __future__ import annotations

import hashlib
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
# Real observed bmm_outer_product specializations (see install_bmm_shape_observer).
_SHAPE_EVENTS: list[dict[str, Any]] = []
# Real observed Triton compile requests (see install_compile_request_observer).
_COMPILE_REQUEST_EVENTS: list[dict[str, Any]] = []


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


def install_bmm_shape_observer() -> dict[str, Any]:
    """Record the REAL bmm_outer_product specialization this request compiles.

    Triton's ``jit_post_compile_hook`` is not invoked on this deployment, so the
    specialization has to be read where it is unambiguous: the arguments the
    installed PyTorch native op actually receives. This wraps that plain Python
    entry point to record the shapes/dtype of the real tensors and the block
    sizes the kernel derives from them via its own ``_pick_block_sizes``.

    Nothing is synthesised and nothing is replaced: the original function is
    called with the original arguments, and the record is a side effect only.
    """
    global _SHAPE_EVENTS
    try:
        from torch._native.ops.bmm_outer_product import (  # noqa: PLC0415
            triton_kernels as _kernels,
        )

        original = _kernels.bmm_outer_product
        if getattr(original, "_comfymodal_shape_observer", False):
            return {"installed": True, "reason": "already_installed"}

        def _observed(a, b, _original=original):
            try:
                block_m, block_n = _kernels._pick_block_sizes(
                    int(a.shape[1]), int(b.shape[2])
                )
                _SHAPE_EVENTS.append({
                    "B": int(a.shape[0]),
                    "M": int(a.shape[1]),
                    "N": int(b.shape[2]),
                    "dtype": str(a.dtype),
                    "BLOCK_M": int(block_m),
                    "BLOCK_N": int(block_n),
                    "a_shape": list(a.shape),
                    "b_shape": list(b.shape),
                })
            except Exception:  # noqa: BLE001 - observation must never break the op
                pass
            return _original(a, b)

        _observed._comfymodal_shape_observer = True  # type: ignore[attr-defined]
        _kernels.bmm_outer_product = _observed
        return {"installed": True, "observed_calls": len(_SHAPE_EVENTS)}
    except Exception as exc:  # pragma: no cover - torch-version dependent
        return {"installed": False, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}


def shape_events() -> list[dict[str, Any]]:
    return [dict(event) for event in _SHAPE_EVENTS]


def install_compile_observer() -> dict[str, Any]:
    """Install Triton's own post-compile hook, without replacing JIT code."""
    try:
        from triton import knobs  # noqa: PLC0415

        def _describe(value: Any) -> Any:
            """Keep hook arguments inspectable without retaining Triton objects."""
            if value is None or isinstance(value, (bool, int, float, str)):
                return value if not isinstance(value, str) else value[:8192]
            if isinstance(value, Mapping):
                return {
                    str(key): _describe(item)
                    for key, item in list(value.items())[:64]
                }
            if isinstance(value, (tuple, list)):
                return [_describe(item) for item in value[:64]]
            result: dict[str, Any] = {
                "type": type(value).__name__,
                "repr": repr(value)[:8192],
            }
            # Triton has changed the concrete compiled-kernel wrapper over
            # time; preserve the public-looking fields when this version
            # exposes them instead of guessing a hook signature.
            for name in (
                "name", "key", "cache_key", "specialization", "constants",
                "constexprs", "metadata", "options", "kernel", "src",
            ):
                try:
                    field = getattr(value, name)
                except Exception:
                    continue
                result[name] = _describe(field)
            return result

        def _hook(*args: Any, **kwargs: Any) -> None:
            _COMPILE_EVENTS.append({
                "args": [type(value).__name__ for value in args],
                "kwargs": sorted(str(key) for key in kwargs),
                "args_detail": [_describe(value) for value in args],
                "kwargs_detail": {
                    str(key): _describe(value) for key, value in kwargs.items()
                },
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


def _describe_compile_arg(value: Any) -> Any:
    """Render one compile argument without retaining a live tensor.

    Triton specializes on shape, stride, dtype and device, so exactly those are
    recorded.  Anything unrecognised degrades to a bounded repr rather than
    being guessed at.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:512]
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is not None and dtype is not None:
        record: dict[str, Any] = {
            "type": type(value).__name__,
            "shape": [int(dim) for dim in list(shape)[:8]],
            "dtype": str(dtype),
        }
        try:
            record["stride"] = [int(s) for s in list(value.stride())[:8]]
        except Exception:  # noqa: BLE001
            record["stride"] = None
        try:
            record["device"] = str(value.device)
        except Exception:  # noqa: BLE001
            record["device"] = None
        return record
    for field in ("num_warps", "num_stages", "num_ctas", "maxnreg", "debug", "name"):
        if hasattr(value, field):
            try:
                inner = getattr(value, field)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(inner, (bool, int, float, str)):
                return {field: inner}
    return {"type": type(value).__name__, "repr": repr(value)[:256]}


def _kernel_identity(jit_function: Any) -> tuple[str, str]:
    """Return ``(name, source)`` for a JITFunction *instance*.

    A JITFunction instance does not expose ``__name__``; only the decorated
    function and the stored source carry the kernel name.  Reading
    ``self.__name__`` alone yields an empty string, which is precisely how an
    observer can be installed successfully, match nothing, and be
    indistinguishable from a kernel that never compiled.  The source is also
    what proves *which* specialization is being compiled.
    """
    name = ""
    for holder in (jit_function, getattr(jit_function, "fn", None)):
        try:
            candidate = getattr(holder, "__name__", "")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(candidate, str) and candidate:
            name = candidate
            break
    try:
        source = str(getattr(jit_function, "src", "") or "")
    except Exception:  # noqa: BLE001
        source = ""
    if not name and source:
        # Triton stores the decorated function verbatim, so the definition line
        # carries the real name.
        marker = "def "
        start = source.find(marker)
        if start >= 0:
            rest = source[start + len(marker):]
            end = rest.find("(")
            if end > 0:
                name = rest[:end].strip()
    return name, source


def install_compile_request_observer(*, name_filter: str = "bmm") -> dict[str, Any]:
    """Observe the real Triton compile request at ``JITFunction._do_compile``.

    This is the boundary the exhaustive profile proved actually runs for this
    kernel (~286 ms of the ~967 ms first-use cost), and it executes immediately
    before Triton computes its cache key and looks up or populates the on-disk
    cache.  It is therefore the last point at which the true specialization and
    the true compile options are both still observable.

    Observation only: the wrapper records and then calls the installed function
    with the original arguments.  ``uninstall_compile_request_observer`` puts
    the installed attribute back, leaving Triton exactly as shipped.
    """
    try:
        from triton.runtime.jit import JITFunction  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - Triton-only runtime branch
        return {"installed": False, "reason": f"{type(exc).__name__}:{str(exc)[:160]}"}

    original = getattr(JITFunction, "_do_compile", None)
    if original is None:
        return {"installed": False, "reason": "no__do_compile"}
    if getattr(original, "_comfymodal_compile_request_observer", False):
        return {"installed": True, "reason": "already_installed"}

    target = str(name_filter).strip().lower()

    def _observed(self, *args: Any, **kwargs: Any) -> Any:
        try:
            kernel_name, source = _kernel_identity(self)
            # Match on the name OR the source: whichever the installed Triton
            # happens to expose, the target kernel is still recognised.
            matched = bool(target) and (
                target in kernel_name.lower() or target in source.lower()
            )
            record: dict[str, Any] = {
                "kernel": kernel_name,
                "matched": matched,
                "arg_count": len(args),
                "kwargs": sorted(str(key) for key in kwargs),
            }
            if matched:
                options = kwargs.get("options")
                if options is None and len(args) >= 2:
                    options = args[1]
                # ``_do_compile(kernel, options, *args)``: everything after the
                # options object is what Triton actually specializes on.
                specialization_args = list(args[2:]) if len(args) >= 2 else list(args)
                record["kernel_arg"] = _describe_compile_arg(args[0]) if args else None
                record["specialization_args"] = [
                    _describe_compile_arg(a) for a in specialization_args
                ]
                record["kwargs_detail"] = {
                    str(key): _describe_compile_arg(val)
                    for key, val in kwargs.items()
                }
                record["options"] = _describe_compile_arg(options)
                for attr in ("num_warps", "num_stages", "num_ctas", "maxnreg", "debug"):
                    try:
                        record[f"option_{attr}"] = getattr(options, attr, None)
                    except Exception:  # noqa: BLE001
                        record[f"option_{attr}"] = None
                src = getattr(self, "src", None)
                if src is not None:
                    text = source or str(src)
                    record["src_sha256"] = hashlib.sha256(
                        text.encode("utf-8", "replace")
                    ).hexdigest()
                    record["src_excerpt"] = text[:6000]
            _COMPILE_REQUEST_EVENTS.append(record)
        except Exception:  # noqa: BLE001 - observation must never break Triton
            pass
        _started = time.perf_counter_ns()
        try:
            return original(self, *args, **kwargs)
        finally:
            # Triton 3.8 routes a disk-cache hit through this same boundary, so
            # the CALL COUNT cannot distinguish a compile from a cache hit.
            # The elapsed time is the only honest measure of whether the ~286 ms
            # compile actually happened.
            _elapsed_ms = (time.perf_counter_ns() - _started) / 1e6
            try:
                _index = len(_COMPILE_REQUEST_EVENTS) - 1
                if _index >= 0:
                    _COMPILE_REQUEST_EVENTS[_index]["duration_ms"] = _elapsed_ms
            except Exception:  # noqa: BLE001
                pass

    _observed._comfymodal_compile_request_observer = True  # type: ignore[attr-defined]
    _observed._comfymodal_original_do_compile = original  # type: ignore[attr-defined]
    JITFunction._do_compile = _observed  # type: ignore[method-assign]
    return {
        "installed": True,
        "boundary": "triton.runtime.jit.JITFunction._do_compile",
        "name_filter": target,
    }


def uninstall_compile_request_observer() -> dict[str, Any]:
    """Restore the installed ``_do_compile`` so Triton is exactly as shipped."""
    try:
        from triton.runtime.jit import JITFunction  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - Triton-only runtime branch
        return {"removed": False, "reason": f"{type(exc).__name__}:{str(exc)[:160]}"}
    current = getattr(JITFunction, "_do_compile", None)
    original = getattr(current, "_comfymodal_original_do_compile", None)
    if original is None:
        return {"removed": False, "reason": "not_installed"}
    JITFunction._do_compile = original  # type: ignore[method-assign]
    del _COMPILE_REQUEST_EVENTS[:]
    return {"removed": True}


def compile_request_events() -> list[dict[str, Any]]:
    return [dict(event) for event in _COMPILE_REQUEST_EVENTS]


def reset_compile_request_events() -> None:
    del _COMPILE_REQUEST_EVENTS[:]


def snapshot_triton_cache_tree(root: str | os.PathLike[str] = TRITON_CACHE_DIR) -> dict[str, Any]:
    """Enumerate Triton's own on-disk cache.

    Triton names each compiled artifact directory after its own cache key, so
    the directories and filenames observed here *are* the cache identity.  That
    is strictly better evidence than re-deriving the key from a remembered
    formula, which is exactly what Phase 2 refused to do.
    """
    base = Path(root)
    snapshot: dict[str, Any] = {
        "root": str(base),
        "exists": base.is_dir(),
        "dirs": [],
        "files": [],
    }
    if not base.is_dir():
        return snapshot
    for dirpath, dirnames, filenames in os.walk(base):
        relative = Path(dirpath).relative_to(base)
        for name in dirnames:
            snapshot["dirs"].append((relative / name).as_posix())
        for name in filenames:
            item = Path(dirpath) / name
            try:
                size = item.stat().st_size
            except OSError:
                size = None
            # as_posix() so the recorded cache-key directory names are identical
            # on the Linux container and on a Windows developer machine.
            snapshot["files"].append(
                {"path": (relative / name).as_posix(), "bytes": size}
            )
    snapshot["dirs"].sort()
    snapshot["files"].sort(key=lambda row: row["path"])
    return snapshot


def clear_cache(*, cache_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Empty a cache root and report what was removed.

    Used to establish a cold-Volume control on the *same* deployment and with
    the *same* instrumentation as the treatment, so the compile timings being
    compared come from one measurement method rather than two.
    """
    root = Path(cache_root)
    removed: list[str] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            try:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed.append(child.name)
            except OSError:
                continue
    return {"status": "cleared", "root": str(root), "removed": removed}


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
