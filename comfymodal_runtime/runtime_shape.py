"""Normalized runtime-shape configuration for controlled experiments."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping


_THREAD_POLICY_DEFAULTS: dict[str, dict[str, int | None]] = {
    "TBASE": {"intraop": None, "interop": None, "native": None},
    "T1": {"intraop": 12, "interop": 4, "native": 12},
    "T2": {"intraop": 8, "interop": 2, "native": 8},
    "T3": {"intraop": 16, "interop": 4, "native": 16},
}
_SNAPSHOT_MODEL_ORDERS = ("O0", "O1", "O2", "O3")
_SHAPE_LABEL_ALLOWED = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-"
)


def _positive_int(name: str, raw: str) -> int:
    if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
        raise RuntimeError(f"{name}={raw!r} must be a positive base-10 integer")
    return int(raw)


def _env_positive(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return _positive_int(name, raw.strip())


def _env_shape_int(names: tuple[str, ...], default: int) -> int:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return _positive_int(name, raw.strip())
    return default


def _memory_request() -> int:
    request_raw = os.environ.get("COMFYMODAL_V2_MEMORY_REQUEST")
    mb_raw = os.environ.get("COMFYMODAL_V2_MEMORY_MB")
    request_present = request_raw is not None and bool(request_raw.strip())
    mb_present = mb_raw is not None and bool(mb_raw.strip())
    if request_present and mb_present:
        request = _positive_int("COMFYMODAL_V2_MEMORY_REQUEST", request_raw.strip())
        mb = _positive_int("COMFYMODAL_V2_MEMORY_MB", mb_raw.strip())
        if request != mb:
            raise RuntimeError(
                "COMFYMODAL_V2_MEMORY_REQUEST and COMFYMODAL_V2_MEMORY_MB "
                f"conflict: {request} != {mb}"
            )
        return request
    if request_present:
        return _positive_int("COMFYMODAL_V2_MEMORY_REQUEST", request_raw.strip())
    if mb_present:
        return _positive_int("COMFYMODAL_V2_MEMORY_MB", mb_raw.strip())
    return 49152


def _shape_label() -> str | None:
    raw = os.environ.get("COMFYMODAL_V2_RUNTIME_SHAPE_LABEL", "").strip()
    if not raw:
        return None
    if len(raw) > 80 or any(char not in _SHAPE_LABEL_ALLOWED for char in raw):
        raise RuntimeError(
            "COMFYMODAL_V2_RUNTIME_SHAPE_LABEL must contain at most 80 "
            "letters, digits, '_', '.', ':', or '-'"
        )
    return raw


@dataclass(frozen=True)
class RuntimeShapeConfig:
    thread_policy: str
    torch_intraop_threads: int | None
    torch_interop_threads: int | None
    omp_num_threads: int | None
    mkl_num_threads: int | None
    openblas_num_threads: int | None
    numexpr_num_threads: int | None
    malloc_arena_max: int | None
    snapshot_model_order: str
    cpu_request: int
    memory_request: int
    runtime_shape_fingerprint: str
    runtime_shape_label: str | None = None

    @property
    def runtime_shape_id(self) -> str:
        """Compatibility alias for callers migrating from the old ID field."""
        return self.runtime_shape_fingerprint

    @property
    def is_baseline_thread_policy(self) -> bool:
        return self.thread_policy == "TBASE"

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
            "runtime_shape_fingerprint": self.runtime_shape_fingerprint,
            "runtime_shape_label": self.runtime_shape_label,
        }

    def environment(self) -> dict[str, str]:
        env = {
            "COMFYMODAL_V2_THREAD_POLICY": self.thread_policy,
            "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": self.snapshot_model_order,
            "COMFYMODAL_V2_CPU_REQUEST": str(self.cpu_request),
            "COMFYMODAL_V2_MEMORY_REQUEST": str(self.memory_request),
            "COMFYMODAL_V2_MEMORY_MB": str(self.memory_request),
            "COMFYMODAL_V2_RUNTIME_SHAPE_FINGERPRINT": self.runtime_shape_fingerprint,
        }
        if self.runtime_shape_label is not None:
            env["COMFYMODAL_V2_RUNTIME_SHAPE_LABEL"] = self.runtime_shape_label
        if not self.is_baseline_thread_policy:
            env.update({
                "COMFYMODAL_V2_TORCH_INTRAOP_THREADS": str(self.torch_intraop_threads),
                "COMFYMODAL_V2_TORCH_INTEROP_THREADS": str(self.torch_interop_threads),
                "OMP_NUM_THREADS": str(self.omp_num_threads),
                "MKL_NUM_THREADS": str(self.mkl_num_threads),
                "OPENBLAS_NUM_THREADS": str(self.openblas_num_threads),
                "NUMEXPR_NUM_THREADS": str(self.numexpr_num_threads),
                "MALLOC_ARENA_MAX": str(self.malloc_arena_max),
            })
        return env


def _runtime_shape_fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def runtime_shape_config(
    *,
    cpu_request: int | None = None,
    memory_request: int | None = None,
) -> RuntimeShapeConfig:
    legacy_id = os.environ.get("COMFYMODAL_V2_RUNTIME_SHAPE_ID", "").strip()
    if legacy_id:
        raise RuntimeError(
            "COMFYMODAL_V2_RUNTIME_SHAPE_ID is not accepted; use "
            "COMFYMODAL_V2_RUNTIME_SHAPE_LABEL for a human label"
        )
    legacy_thread_limit = os.environ.get(
        "COMFYMODAL_V2_RESTORE_TORCH_THREADS", ""
    ).strip()
    if legacy_thread_limit:
        raise RuntimeError(
            "COMFYMODAL_V2_RESTORE_TORCH_THREADS is incompatible with "
            "C8 runtime-shape policies; use COMFYMODAL_V2_THREAD_POLICY"
        )
    policy = os.environ.get("COMFYMODAL_V2_THREAD_POLICY", "TBASE").strip().upper() or "TBASE"
    if policy == "T0":
        policy = "TBASE"
    if policy not in _THREAD_POLICY_DEFAULTS:
        raise RuntimeError(
            f"COMFYMODAL_V2_THREAD_POLICY={policy!r} is invalid; "
            "expected TBASE, T1, T2, or T3"
        )
    defaults = _THREAD_POLICY_DEFAULTS[policy]
    if policy == "TBASE":
        intraop = interop = native = None
        omp = mkl = openblas = numexpr = malloc_arena = None
    else:
        intraop = _env_positive(
            "COMFYMODAL_V2_TORCH_INTRAOP_THREADS", int(defaults["intraop"])
        )
        interop = _env_positive(
            "COMFYMODAL_V2_TORCH_INTEROP_THREADS", int(defaults["interop"])
        )
        native = _env_positive("COMFYMODAL_V2_NATIVE_THREADS", int(defaults["native"]))
        omp = _env_shape_int(("OMP_NUM_THREADS",), native)
        mkl = _env_shape_int(("MKL_NUM_THREADS",), native)
        openblas = _env_shape_int(("OPENBLAS_NUM_THREADS",), native)
        numexpr = _env_shape_int(("NUMEXPR_NUM_THREADS",), native)
        malloc_arena = _env_shape_int(("MALLOC_ARENA_MAX",), 2)
    snapshot_order = (
        os.environ.get("COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER", "O0").strip().upper()
        or "O0"
    )
    if snapshot_order not in _SNAPSHOT_MODEL_ORDERS:
        raise RuntimeError(
            f"COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER={snapshot_order!r} is invalid; "
            "expected O0, O1, O2, or O3"
        )
    env_cpu_request = _env_shape_int(("COMFYMODAL_V2_CPU_REQUEST",), 16)
    env_memory_request = _memory_request()
    if cpu_request is not None:
        if isinstance(cpu_request, bool) or not isinstance(cpu_request, int) or cpu_request <= 0:
            raise RuntimeError("cpu_request must be a positive integer")
        env_cpu_request = cpu_request
    if memory_request is not None:
        if isinstance(memory_request, bool) or not isinstance(memory_request, int) or memory_request <= 0:
            raise RuntimeError("memory_request must be a positive integer")
        env_memory_request = memory_request
    payload = {
        "thread_policy": policy,
        "torch_intraop_threads": intraop,
        "torch_interop_threads": interop,
        "omp_num_threads": omp,
        "mkl_num_threads": mkl,
        "openblas_num_threads": openblas,
        "numexpr_num_threads": numexpr,
        "malloc_arena_max": malloc_arena,
        "snapshot_model_order": snapshot_order,
        "cpu_request": env_cpu_request,
        "memory_request": env_memory_request,
    }
    return RuntimeShapeConfig(
        thread_policy=policy,
        torch_intraop_threads=intraop,
        torch_interop_threads=interop,
        omp_num_threads=omp,
        mkl_num_threads=mkl,
        openblas_num_threads=openblas,
        numexpr_num_threads=numexpr,
        malloc_arena_max=malloc_arena,
        snapshot_model_order=snapshot_order,
        cpu_request=env_cpu_request,
        memory_request=env_memory_request,
        runtime_shape_fingerprint=_runtime_shape_fingerprint(payload),
        runtime_shape_label=_shape_label(),
    )


_TORCH_POLICY_APPLIED: tuple[int, int] | None = None


def _native_thread_count() -> int | None:
    try:
        return len(os.listdir("/proc/self/task"))
    except Exception:
        return None


def _observed_native_settings() -> dict[str, str | None]:
    return {
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS"),
        "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
        "NUMEXPR_NUM_THREADS": os.environ.get("NUMEXPR_NUM_THREADS"),
        "MALLOC_ARENA_MAX": os.environ.get("MALLOC_ARENA_MAX"),
    }


def effective_runtime_shape(*, stage: str) -> dict[str, Any]:
    config = runtime_shape_config()
    actual: dict[str, Any] = {
        "stage": stage,
        "runtime_shape_fingerprint": config.runtime_shape_fingerprint,
        "runtime_shape_label": config.runtime_shape_label,
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
        "native_library_settings": _observed_native_settings(),
    }
    try:
        import torch
        actual["torch_intraop_threads"] = int(torch.get_num_threads())
        actual["torch_interop_threads"] = int(torch.get_num_interop_threads())
    except Exception:
        actual["torch_intraop_threads"] = None
        actual["torch_interop_threads"] = None
    actual["actual_torch_intraop_threads"] = actual["torch_intraop_threads"]
    actual["actual_torch_interop_threads"] = actual["torch_interop_threads"]
    actual["requested_torch_intraop_threads"] = config.torch_intraop_threads
    actual["requested_torch_interop_threads"] = config.torch_interop_threads
    if config.is_baseline_thread_policy:
        actual["requested_vs_actual_match"] = True
    else:
        actual["requested_vs_actual_match"] = (
            actual["torch_intraop_threads"] == config.torch_intraop_threads
            and actual["torch_interop_threads"] == config.torch_interop_threads
        )
    return actual


def _emit_runtime_shape_event(trace: Any, values: Mapping[str, Any]) -> None:
    if trace is None:
        return
    trace.emit(
        "runtime_shape_observed",
        phase="lifecycle" if values.get("stage") != "request_entry" else "request",
        metadata=dict(values),
    )


def apply_torch_thread_policy(
    *,
    stage: str,
    trace: Any = None,
    enforce: bool = True,
) -> dict[str, Any]:
    global _TORCH_POLICY_APPLIED
    config = runtime_shape_config()
    import torch

    before = {
        "torch_intraop_threads": int(torch.get_num_threads()),
        "torch_interop_threads": int(torch.get_num_interop_threads()),
    }
    if config.is_baseline_thread_policy:
        result = effective_runtime_shape(stage=stage)
        result.update({
            "status": "baseline_passthrough",
            "error": "",
            "before": before,
        })
        _emit_runtime_shape_event(trace, result)
        _print_runtime_shape(result)
        return result

    target = (int(config.torch_intraop_threads), int(config.torch_interop_threads))
    if _TORCH_POLICY_APPLIED == target and before == {
        "torch_intraop_threads": target[0],
        "torch_interop_threads": target[1],
    }:
        status = "already_applied"
        errors: list[str] = []
    else:
        status = "pending"
        errors = []
        if before["torch_interop_threads"] != target[1]:
            try:
                torch.set_num_interop_threads(target[1])
            except Exception as exc:
                errors.append(f"interop:{type(exc).__name__}: {exc}")
        if before["torch_intraop_threads"] != target[0]:
            try:
                torch.set_num_threads(target[0])
            except Exception as exc:
                errors.append(f"intraop:{type(exc).__name__}: {exc}")
        observed = effective_runtime_shape(stage=stage)
        if errors or not observed["requested_vs_actual_match"]:
            status = "late_or_failed"
        else:
            status = "applied"
            _TORCH_POLICY_APPLIED = target
    result = effective_runtime_shape(stage=stage)
    result.update({
        "status": status,
        "error": "; ".join(errors),
        "before": before,
    })
    _emit_runtime_shape_event(trace, result)
    _print_runtime_shape(result)
    if enforce and status not in ("applied", "already_applied"):
        raise RuntimeError(
            f"runtime shape thread policy failed closed at {stage}: "
            f"policy={config.thread_policy} status={status} "
            f"requested=({target[0]},{target[1]}) "
            f"actual=({result.get('torch_intraop_threads')},{result.get('torch_interop_threads')}) "
            f"error={result.get('error', '')}"
        )
    return result


def validate_torch_thread_policy(
    *,
    stage: str,
    trace: Any = None,
    enforce: bool = True,
) -> dict[str, Any]:
    config = runtime_shape_config()
    result = effective_runtime_shape(stage=stage)
    result["status"] = (
        "baseline_passthrough"
        if config.is_baseline_thread_policy
        else "validated" if result["requested_vs_actual_match"] else "late_or_failed"
    )
    result.setdefault("error", "")
    _emit_runtime_shape_event(trace, result)
    _print_runtime_shape(result)
    if enforce and result["status"] == "late_or_failed":
        raise RuntimeError(
            f"runtime shape thread policy mismatch at {stage}: "
            f"policy={config.thread_policy} requested="
            f"({config.torch_intraop_threads},{config.torch_interop_threads}) "
            f"actual=({result.get('torch_intraop_threads')},{result.get('torch_interop_threads')})"
        )
    return result


def log_effective_runtime_shape(*, stage: str, trace: Any = None) -> dict[str, Any]:
    values = effective_runtime_shape(stage=stage)
    _emit_runtime_shape_event(trace, values)
    _print_runtime_shape(values)
    return values


def _print_runtime_shape(values: Mapping[str, Any]) -> None:
    print(
        "[v2.runtime_shape] "
        + " ".join(f"{key}={value}" for key, value in values.items()),
        flush=True,
    )
