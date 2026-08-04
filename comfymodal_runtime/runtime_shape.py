"""Normalized runtime-shape configuration for controlled experiments."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping


_THREAD_POLICY_DEFAULTS: dict[str, dict[str, int]] = {
    "T0": {"intraop": 16, "interop": 32, "native": 16},
    "T1": {"intraop": 12, "interop": 4, "native": 12},
    "T2": {"intraop": 8, "interop": 2, "native": 8},
    "T3": {"intraop": 16, "interop": 4, "native": 16},
}
_SNAPSHOT_MODEL_ORDERS = ("O0", "O1", "O2", "O3")


def _positive_int(name: str, raw: str, *, allow_empty: bool = False) -> int | None:
    if allow_empty and not raw.strip():
        return None
    if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
        raise RuntimeError(f"{name}={raw!r} must be a positive base-10 integer")
    return int(raw)


def _env_positive(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = _positive_int(name, raw.strip())
    assert value is not None
    return value


def _env_shape_int(names: tuple[str, ...], default: int) -> int:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return _env_positive(name, default)
    return default


@dataclass(frozen=True)
class RuntimeShapeConfig:
    thread_policy: str
    torch_intraop_threads: int
    torch_interop_threads: int
    omp_num_threads: int
    mkl_num_threads: int
    openblas_num_threads: int
    numexpr_num_threads: int
    malloc_arena_max: int
    snapshot_model_order: str
    cpu_request: int
    memory_request: int
    runtime_shape_id: str

    def identity_payload(self) -> dict[str, Any]:
        return {
            "thread_policy": self.thread_policy,
            "torch_intraop_threads": self.torch_intraop_threads,
            "torch_interop_threads": self.torch_interop_threads,
            "omp_num_threads": self.omp_num_threads,
            "mkl_num_threads": self.mkl_num_threads,
            "openblas_num_threads": self.openblas_num_threads,
            "numexpr_num_threads": self.numexpr_num_threads,
            "malloc_arena_max": self.malloc_arena_max,
            "snapshot_model_order": self.snapshot_model_order,
            "cpu_request": self.cpu_request,
            "memory_request": self.memory_request,
            "runtime_shape_id": self.runtime_shape_id,
        }

    def environment(self) -> dict[str, str]:
        return {
            "COMFYMODAL_V2_THREAD_POLICY": self.thread_policy,
            "COMFYMODAL_V2_TORCH_INTRAOP_THREADS": str(self.torch_intraop_threads),
            "COMFYMODAL_V2_TORCH_INTEROP_THREADS": str(self.torch_interop_threads),
            "OMP_NUM_THREADS": str(self.omp_num_threads),
            "MKL_NUM_THREADS": str(self.mkl_num_threads),
            "OPENBLAS_NUM_THREADS": str(self.openblas_num_threads),
            "NUMEXPR_NUM_THREADS": str(self.numexpr_num_threads),
            "MALLOC_ARENA_MAX": str(self.malloc_arena_max),
            "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": self.snapshot_model_order,
            "COMFYMODAL_V2_CPU_REQUEST": str(self.cpu_request),
            "COMFYMODAL_V2_MEMORY_REQUEST": str(self.memory_request),
            "COMFYMODAL_V2_MEMORY_MB": str(self.memory_request),
            "COMFYMODAL_V2_RUNTIME_SHAPE_ID": self.runtime_shape_id,
        }


def _runtime_shape_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def runtime_shape_config(
    *,
    cpu_request: int | None = None,
    memory_request: int | None = None,
) -> RuntimeShapeConfig:
    cpu_override = cpu_request
    memory_override = memory_request
    policy = os.environ.get("COMFYMODAL_V2_THREAD_POLICY", "T0").strip().upper() or "T0"
    if policy not in _THREAD_POLICY_DEFAULTS:
        raise RuntimeError(
            f"COMFYMODAL_V2_THREAD_POLICY={policy!r} is invalid; expected T0, T1, T2, or T3"
        )
    defaults = _THREAD_POLICY_DEFAULTS[policy]
    intraop = _env_positive("COMFYMODAL_V2_TORCH_INTRAOP_THREADS", defaults["intraop"])
    interop = _env_positive("COMFYMODAL_V2_TORCH_INTEROP_THREADS", defaults["interop"])
    native = _env_positive("COMFYMODAL_V2_NATIVE_THREADS", defaults["native"])
    snapshot_order = os.environ.get("COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER", "O0").strip().upper() or "O0"
    if snapshot_order not in _SNAPSHOT_MODEL_ORDERS:
        raise RuntimeError(
            f"COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER={snapshot_order!r} is invalid; "
            "expected O0, O1, O2, or O3"
        )
    env_cpu_request = _env_shape_int(("COMFYMODAL_V2_CPU_REQUEST",), 16)
    env_memory_request = _env_shape_int(
        ("COMFYMODAL_V2_MEMORY_REQUEST", "COMFYMODAL_V2_MEMORY_MB"), 40960
    )
    payload = {
        "thread_policy": policy,
        "torch_intraop_threads": intraop,
        "torch_interop_threads": interop,
        "omp_num_threads": _env_shape_int(("OMP_NUM_THREADS",), native),
        "mkl_num_threads": _env_shape_int(("MKL_NUM_THREADS",), native),
        "openblas_num_threads": _env_shape_int(("OPENBLAS_NUM_THREADS",), native),
        "numexpr_num_threads": _env_shape_int(("NUMEXPR_NUM_THREADS",), native),
        "malloc_arena_max": _env_shape_int(("MALLOC_ARENA_MAX",), 2),
        "snapshot_model_order": snapshot_order,
        "cpu_request": env_cpu_request,
        "memory_request": env_memory_request,
    }
    if cpu_override is not None:
        if isinstance(cpu_override, bool) or not isinstance(cpu_override, int) or cpu_override <= 0:
            raise RuntimeError("cpu_request must be a positive integer")
        payload["cpu_request"] = cpu_override
    if memory_override is not None:
        if isinstance(memory_override, bool) or not isinstance(memory_override, int) or memory_override <= 0:
            raise RuntimeError("memory_request must be a positive integer")
        payload["memory_request"] = memory_override
    explicit_id = os.environ.get("COMFYMODAL_V2_RUNTIME_SHAPE_ID", "").strip()
    shape_id = explicit_id or _runtime_shape_id(payload)
    if not shape_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for ch in shape_id):
        raise RuntimeError(
            "COMFYMODAL_V2_RUNTIME_SHAPE_ID must contain only letters, digits, '_', '.', ':', or '-'"
        )
    return RuntimeShapeConfig(
        thread_policy=policy,
        torch_intraop_threads=intraop,
        torch_interop_threads=interop,
        omp_num_threads=payload["omp_num_threads"],
        mkl_num_threads=payload["mkl_num_threads"],
        openblas_num_threads=payload["openblas_num_threads"],
        numexpr_num_threads=payload["numexpr_num_threads"],
        malloc_arena_max=payload["malloc_arena_max"],
        snapshot_model_order=snapshot_order,
        cpu_request=payload["cpu_request"],
        memory_request=payload["memory_request"],
        runtime_shape_id=shape_id,
    )


_TORCH_POLICY_APPLIED: tuple[int, int] | None = None


def _native_thread_count() -> int | None:
    try:
        return len(os.listdir("/proc/self/task"))
    except Exception:
        return None


def apply_torch_thread_policy(*, stage: str) -> dict[str, Any]:
    global _TORCH_POLICY_APPLIED
    config = runtime_shape_config()
    import torch

    before = {
        "torch_intraop_threads": int(torch.get_num_threads()),
        "torch_interop_threads": int(torch.get_num_interop_threads()),
    }
    status = "already_applied" if _TORCH_POLICY_APPLIED == (
        config.torch_intraop_threads, config.torch_interop_threads
    ) else "pending"
    error = ""
    if status != "already_applied":
        try:
            if before["torch_interop_threads"] != config.torch_interop_threads:
                torch.set_num_interop_threads(config.torch_interop_threads)
            if torch.get_num_threads() != config.torch_intraop_threads:
                torch.set_num_threads(config.torch_intraop_threads)
            _TORCH_POLICY_APPLIED = (
                config.torch_intraop_threads, config.torch_interop_threads
            )
            status = "applied"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            status = "late_or_failed"
    result = effective_runtime_shape(stage=stage)
    result.update({"status": status, "error": error, "before": before})
    _print_runtime_shape(result)
    return result


def effective_runtime_shape(*, stage: str) -> dict[str, Any]:
    config = runtime_shape_config()
    actual: dict[str, Any] = {
        "stage": stage,
        "runtime_shape_id": config.runtime_shape_id,
        "thread_policy": config.thread_policy,
        "snapshot_model_order": config.snapshot_model_order,
        "cpu_request": config.cpu_request,
        "memory_request": config.memory_request,
        "native_thread_count": _native_thread_count(),
        "configured_omp": config.omp_num_threads,
        "configured_mkl": config.mkl_num_threads,
        "configured_openblas": config.openblas_num_threads,
        "configured_numexpr": config.numexpr_num_threads,
        "malloc_arena_max": config.malloc_arena_max,
    }
    try:
        import torch
        actual["torch_intraop_threads"] = int(torch.get_num_threads())
        actual["torch_interop_threads"] = int(torch.get_num_interop_threads())
    except Exception:
        actual["torch_intraop_threads"] = None
        actual["torch_interop_threads"] = None
    return actual


def log_effective_runtime_shape(*, stage: str) -> dict[str, Any]:
    values = effective_runtime_shape(stage=stage)
    _print_runtime_shape(values)
    return values


def _print_runtime_shape(values: Mapping[str, Any]) -> None:
    print(
        "[v2.runtime_shape] "
        + " ".join(f"{key}={value}" for key, value in values.items()),
        flush=True,
    )
