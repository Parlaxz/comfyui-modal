"""V2 "fastsafetensors" UNET loader (Batch C9 production integration; default OFF).

Consumes the C9 queue-depth result (same-file concurrency scales: QD8
preadv = 40.72 GB/s) and the C10 fastsafetensors finding (nogds concurrent
pread pool -> pinned bounce -> direct CUDA; tuned 16 threads / 1 GiB blocks
=> 13.32 GB/s GPU-ready, byte-identical) combined with the C8-proven meta
construction strategy:

  header/config
        ├──────────────→ meta ZImage construction (worker A)
        │
        └──────────────→ fastsafetensors concurrent file→CUDA (worker B)
                                 ↓
                         GPU state_dict
                                 ↓
                  diffusion_model.load_state_dict(assign=True)
                                 ↓
                      ModelPatcher / final sweep / validation
                                 ↓
                           GPU-ready UNET
                                 ↓
                  existing future / graph / sampler

NO native mmap read. NO native bulk H2D. NO to_empty(cuda). NO preadv->pinned
Python ring. NO ComfyUI core changes.

Gate: ``COMFYMODAL_V2_UNET_FASTSAFETENSORS`` (default OFF; on values
"1"/"true"/"yes"/"on"; off values "", "0", "false", "no", "off", "none";
anything else -> invalid, fail-closed, one-time print).  The historical
flags (PINNED_RING / META_DIRECT / READ_H2D_PIPELINE / C9QD_EXTRAS) are
untouched.  The ``_load_unet`` branch lives in ``model_preload.py`` and
lazy-imports this module so the off-path import surface is zero.

Ownership (Gate 1, from the 0.3.3 upstream source):
  * ``copy_files_to_device`` returns a ``FilesBufferOnDevice`` that OWNS the
    backing storage for tensors created from it; ``get_tensor`` returns
    zero-copy views sharing the device buffer ("gbuf") lifetime.
  * The upstream contract is explicit: tensors are valid ONLY while the
    buffer stays open; ``FilesBufferOnDevice.close()`` (and loader
    destruction) frees the device pointers and invalidates the views.
  * Therefore this pipeline RETAINS the loader + buffer as an explicit owner
    attached to the ModelPatcher for the model's full lifetime
    (``patcher._comfymodal_fastsafe_owner``), never calls ``close()`` on
    success, and releases everything when the patcher (and thus the UNET) is
    genuinely released.  No 12.31 GB clone is performed.
  * The empirical ownership micro-test runs in the structural gate
    (unet_qd_probe smoke extension) on the first valid container.

Config correctness gates mirror C8/I-3 fail-closed semantics: config class
ZImage; param count 6,154,908,736; uniform bf16 sd dtype within
supported_inference_dtypes; allow_fp16 value probe resolved; transform
classification INDEPENDENT (identity); exact sd key mapping into the
diffusion_model param/buffer sets.
"""

from __future__ import annotations

import gc as _gc
import inspect as _inspect
import os as _os
import time as _time
from collections.abc import Mapping as _Mapping
from typing import Any

from .model_preload import (
    _ACTIVE_LANE_TRACE,
    _ACTIVE_REQUEST_TRACE,
    _c6_comfy_fn,
    _c6_json_safe,
    _c6_safetensors_dtype_map,
    _c6_value_probe_allow_fp16,
    _fast_disk_high_vram,
    _fast_disk_model_config_evidence,
    _fast_disk_torch_future_enabled,
    _ring_derive_config,
    _ring_resolve_unet_path,
)
from .unet_qd_probe import (
    key_set_ok,
    spot_check_tensors,
)
from .unet_salvage_probe import (
    collect_meta_tensors,
)
from .env import env_flag as _env_flag
from . import gpu_lane_coordination as _gpu_coord
from .trace import (
    cpu_affinity_count as _trace_cpu_affinity_count,
    effective_cores_from as _trace_effective_cores_from,
    forensic_intervals as _trace_forensic_intervals,
    forensic_intervals_disjoint as _trace_forensic_intervals_disjoint,
    forensic_overlap_ms as _trace_forensic_overlap_ms,
    register_forensic_interval as _trace_register_forensic_interval,
)

# ── Constants (bounded budgets) ───────────────────────────────────────────
# E27 Follow-Up A first-touch screening winner (fresh container, RTX PRO
# 6000): UNET control T16/B1GiB = 4287.4 ms (2.87 GB/s); best T8/B256MiB =
# 699.4 ms (17.60 GB/s) — 6.1x.  Env-overridable per-role (Target B):
#   COMFYMODAL_V2_UNET_FASTSAFE_THREADS   (default 8)
#   COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES (default 256 MiB)
# Read at call time so an integrated campaign can tune per run without a
# code change.
_FS_THREADS: int = 8
_FS_MAX_COPY_BLOCK_BYTES: int = 256 * 1024 * 1024  # 256 MiB (E28 winner)
# E28: the fastsafe nogds copier's bounce-buffer pool (``bbuf_size_kb``)
# limits in-flight I/O.  The library default is 16 MiB — with 8 threads and
# 256 MiB copy blocks the cold file read serializes to ~1.2 GB/s (the
# 12.27 s worker-B wall measured in the first E28 cold run).  A large pool
# (512 MiB) lets all 8 reader threads keep large reads in flight, matching
# the E27 QD8 evidence (49 GB/s preadv).  Env-overridable.
_FS_BBUF_KB: int = 512 * 1024  # 512 MiB bounce-buffer pool
_FS_NOGDS: bool = True
_FS_USE_BUF_REGISTER: bool = False  # cudaHostRegister unsupported (C6 rc=304)
_FS_THREADS_ENV: str = "COMFYMODAL_V2_UNET_FASTSAFE_THREADS"
_FS_BLOCK_BYTES_ENV: str = "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES"
_FS_BBUF_KB_ENV: str = "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB"


def _fs_effective_threads() -> int:
    try:
        raw = _os.environ.get(_FS_THREADS_ENV, "").strip()
        if raw:
            value = int(raw)
            if value >= 1:
                return value
    except Exception:
        pass
    return _FS_THREADS


def _fs_effective_block_bytes() -> int:
    try:
        raw = _os.environ.get(_FS_BLOCK_BYTES_ENV, "").strip()
        if raw:
            value = int(raw)
            if value >= 1024 * 1024:
                return value
    except Exception:
        pass
    return _FS_MAX_COPY_BLOCK_BYTES


def _fs_effective_bbuf_kb() -> int:
    """Effective nogds bounce-buffer pool size in KiB (env override, then
    default 512 MiB).  Minimum 16 MiB (the library default floor)."""
    try:
        raw = _os.environ.get(_FS_BBUF_KB_ENV, "").strip()
        if raw:
            value = int(raw)
            if value >= 16 * 1024:
                return value
    except Exception:
        pass
    return _FS_BBUF_KB
# ZImage identity gates (exact, from the C6/I-3 authoritative records).
_FS_EXPECTED_PARAM_COUNT: int = 6_154_908_736
_FS_EXPECTED_TOTAL_BYTES: int = 12_309_817_472
_FS_FINAL_TO_DUPLICATE_THRESHOLD_MS: float = 500.0
_FS_DATA_PTR_SAMPLE_KEYS: int = 8
_FS_META_SWEEP_DEPTH: int = 6
_FS_OWNER_ATTR: str = "_comfymodal_fastsafe_owner"
_STAGED_OWNER_ATTR: str = "_comfymodal_staged_transport_owner"
_STAGED_TRANSPORT_FLAG: str = "COMFYMODAL_V2_STAGED_SAFETENSORS"


def _fs_forensics_enabled() -> bool:
    """Call-time deep-profiler gate (DEFAULT OFF).  ``COMFYMODAL_V2_UNET_FORENSICS=1``
    enables the deep profile (nn.Module.__init__ wrapping, gc.callbacks, first-op
    proxy); unset or ``=0`` keeps only the low-overhead timestamp accounting.
    Read at each call so tests can toggle it between runs."""
    return _env_flag("COMFYMODAL_V2_UNET_FORENSICS", default=False)

_FASTSAFE_MODULE = None
_STAGED_MODULE = None


def _fs_fast_module():
    """Lazy import of fastsafetensors (cached).  None when unavailable."""
    global _FASTSAFE_MODULE
    if _FASTSAFE_MODULE is None:
        try:
            import importlib as _il
            _FASTSAFE_MODULE = _il.import_module("fastsafetensors")
        except Exception:
            _FASTSAFE_MODULE = False
    return _FASTSAFE_MODULE or None


def _fs_fastsafe_version() -> str:
    try:
        _m = _fs_fast_module()
        return str(getattr(_m, "__version__", "") or "")
    except Exception:
        return ""


def _fs_staged_transport_enabled() -> bool:
    return _env_flag(_STAGED_TRANSPORT_FLAG, default=False)


def _fs_staged_module():
    global _STAGED_MODULE
    if _STAGED_MODULE is None:
        try:
            from . import staged_safetensors as _staged
            _STAGED_MODULE = _staged
        except Exception:
            _STAGED_MODULE = False
    return _STAGED_MODULE or None


def _fs_staged_fn(module, names):
    for _name in names:
        _fn = getattr(module, _name, None)
        if callable(_fn):
            return _fn
    return None


def _fs_staged_invoke(fn, args, kwargs):
    try:
        _sig = _inspect.signature(fn)
    except Exception:
        return fn(*args)
    _filtered = {k: v for k, v in kwargs.items() if k in _sig.parameters}
    _candidates = [
        (tuple(args), {}),
        (tuple(args), _filtered),
        (tuple(args[:-1]), _filtered),
        (tuple(args[:-1]), {}),
    ]
    for _call_args, _call_kwargs in _candidates:
        try:
            _sig.bind(*_call_args, **_call_kwargs)
        except TypeError:
            continue
        return fn(*_call_args, **_call_kwargs)
    raise TypeError(f"unsupported staged transport signature: {fn!r}")


def _fs_staged_plan(path, manifest, target=None):
    _module = _fs_staged_module()
    _fn = _fs_staged_fn(
        _module,
        ("build_plan", "build_staged_plan", "plan_staged_transport",
         "make_staged_plan", "plan"),
    ) if _module is not None else None
    if _fn is None:
        raise RuntimeError("staged_transport_unavailable")
    return _fs_staged_invoke(
        _fn,
        (path, manifest),
        {"path": path, "manifest": manifest, "header": manifest,
         "device": target},
    )


def _fs_staged_prepare(plan):
    _module = _fs_staged_module()
    _fn = _fs_staged_fn(
        _module,
        ("prepare", "prepare_staged", "prepare_staged_transport",
         "prepare_plan"),
    ) if _module is not None else None
    if _fn is None:
        raise RuntimeError("staged_transport_unavailable")
    return _fs_staged_invoke(_fn, (plan,), {"plan": plan})


def _fs_staged_commit(prepared, target):
    _module = _fs_staged_module()
    _fn = _fs_staged_fn(
        _module,
        ("commit", "commit_staged", "commit_staged_transport",
         "commit_plan"),
    ) if _module is not None else None
    if _fn is None:
        raise RuntimeError("staged_transport_unavailable")
    return _fs_staged_invoke(
        _fn,
        (prepared, target),
        {"prepared": prepared, "plan": prepared,
         "target": target, "target_device": target, "device": target},
    )


def _fs_staged_result(result):
    _success = getattr(result, "success", getattr(result, "ok", True))
    if _success is False:
        _reason = getattr(result, "fallback_reason", None) or "unknown"
        _error = str(getattr(result, "error", "") or "")[:160]
        raise RuntimeError(f"staged_result:{_reason}:{_error}")
    _tensors = None
    _owner = None
    _metrics = {}
    if isinstance(result, tuple):
        if result:
            _tensors = result[0]
        if len(result) > 1:
            _owner = result[1]
        if len(result) > 2 and isinstance(result[2], _Mapping):
            _metrics = dict(result[2])
    elif isinstance(result, _Mapping):
        if "tensors" in result:
            _tensors = result.get("tensors")
            _owner = result.get("owner")
            _metrics = dict(result.get("metrics") or {})
        elif "state_dict" in result:
            _tensors = result.get("state_dict")
            _owner = result.get("owner")
            _metrics = dict(result.get("metrics") or {})
        else:
            _tensors = result
    else:
        _tensors = getattr(result, "tensors", None)
        if _tensors is None:
            _tensors = getattr(result, "state_dict", None)
        _owner = getattr(result, "owner", None)
        if _owner is None:
            _owner = getattr(result, "_owner", None)
        _metrics = dict(getattr(result, "metrics", {}) or {})
    if not isinstance(_tensors, _Mapping):
        raise RuntimeError("staged_transport_missing_tensors")
    return dict(_tensors), _owner, _metrics


def _fs_staged_metric(metrics, staged_metrics, target, names):
    for _name in names:
        _value = staged_metrics.get(_name)
        if isinstance(_value, (int, float)):
            metrics[target] = float(_value)
            return


class _StagedTransportOwner:
    __slots__ = ("plan", "prepared", "committed", "owner", "kind", "closed")

    def __init__(self, plan, prepared, committed, owner=None):
        self.plan = plan
        self.prepared = prepared
        self.committed = committed
        self.owner = owner
        self.kind = "staged_safetensors.transport"
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        _seen = set()
        for _value in (self.owner, self.committed, self.prepared, self.plan):
            if _value is None or id(_value) in _seen:
                continue
            _seen.add(id(_value))
            for _name in ("close", "release", "dispose"):
                _fn = getattr(_value, _name, None)
                if callable(_fn):
                    try:
                        _fn()
                    except Exception:
                        pass
                    break


# ── Device / capability helpers (patchable for offline tests) ────────────


def _fs_cuda_available() -> bool:
    try:
        import torch as _t
        return bool(_t.cuda.is_available())
    except Exception:
        return False


def _fs_get_target():
    try:
        _mgmt = _c6_comfy_fn("comfy.model_management", "get_torch_device")
        _t = _mgmt() if _mgmt is not None else None
        if _t is not None and str(getattr(_t, "type", "") or "").lower() == "cuda":
            return _t
    except Exception:
        pass
    try:
        import torch as _t2
        return _t2.device("cuda")
    except Exception:
        return None


def _fs_get_offload():
    try:
        _fn = _c6_comfy_fn("comfy.model_management", "unet_offload_device")
        _d = _fn() if _fn is not None else None
        if _d is not None:
            return _d
    except Exception:
        pass
    try:
        import torch as _t3
        return _t3.device("cpu")
    except Exception:
        return None


def _fs_scoped_cuda_readiness_enabled() -> bool:
    """Keep the optional event path compatible with minimal coordinators."""
    try:
        _fn = getattr(_gpu_coord, "scoped_cuda_readiness_enabled", None)
        return bool(_fn()) if callable(_fn) else False
    except Exception:
        return False


# ── Memory instrumentation (Gate 2; never raises, always JSON-safe) ───────


def _fs_proc_status_field(field: str):
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as _f:
            for _line in _f:
                if _line.startswith(field + ":"):
                    _val = _line.split(":", 1)[1].strip().split()[0]
                    return int(_val) * 1024
    except Exception:
        pass
    return None


def _fs_cgroup_bytes(path: str):
    try:
        with open(path, "r", encoding="utf-8") as _f:
            return int(_f.read().strip())
    except Exception:
        return None


def _fs_memory_snapshot() -> dict:
    """Host + cgroup + CUDA memory snapshot.  Every value is optional;
    deltas are computed by the caller against a prior snapshot."""
    _out: dict[str, Any] = {
        "rss_bytes": None, "rss_peak_bytes": None,
        "cgroup_current_bytes": None, "cgroup_peak_bytes": None,
        "cuda_allocated_bytes": None, "cuda_reserved_bytes": None,
        "cuda_allocated_peak_bytes": None, "cuda_reserved_peak_bytes": None,
    }
    _out["rss_bytes"] = _fs_proc_status_field("VmRSS")
    _out["rss_peak_bytes"] = _fs_proc_status_field("VmHWM")
    _cg = None
    for _p in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.usage_in_bytes"):
        _v = _fs_cgroup_bytes(_p)
        if _v is not None:
            _cg = _v
            break
    _out["cgroup_current_bytes"] = _cg
    _cgp = None
    for _p in ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory.max_usage_in_bytes"):
        _v = _fs_cgroup_bytes(_p)
        if _v is not None:
            _cgp = _v
            break
    _out["cgroup_peak_bytes"] = _cgp
    if _fs_cuda_available():
        try:
            import torch as _t
            _out["cuda_allocated_bytes"] = int(_t.cuda.memory_allocated())
            _out["cuda_reserved_bytes"] = int(_t.cuda.memory_reserved())
            _out["cuda_allocated_peak_bytes"] = int(_t.cuda.max_memory_allocated())
            _out["cuda_reserved_peak_bytes"] = int(_t.cuda.max_memory_reserved())
        except Exception:
            pass
    return _out


def _fs_delta(a: dict, b: dict, key: str):
    try:
        _va, _vb = a.get(key), b.get(key)
        if _va is not None and _vb is not None:
            return int(_vb) - int(_va)
    except Exception:
        pass
    return None


def _fs_mem_report(prefix: str, before: dict, after: dict) -> dict:
    """Delta report between two snapshots (all optional values)."""
    return {
        f"{prefix}_rss_delta_bytes": _fs_delta(before, after, "rss_bytes"),
        f"{prefix}_rss_peak_bytes": after.get("rss_peak_bytes"),
        f"{prefix}_cgroup_delta_bytes": _fs_delta(before, after, "cgroup_current_bytes"),
        f"{prefix}_cgroup_peak_bytes": after.get("cgroup_peak_bytes"),
        f"{prefix}_cuda_alloc_delta_bytes": _fs_delta(before, after, "cuda_allocated_bytes"),
        f"{prefix}_cuda_reserved_delta_bytes": _fs_delta(before, after, "cuda_reserved_bytes"),
        f"{prefix}_cuda_alloc_peak_bytes": after.get("cuda_allocated_peak_bytes"),
        f"{prefix}_cuda_reserved_peak_bytes": after.get("cuda_reserved_peak_bytes"),
    }


# ── Telemetry ─────────────────────────────────────────────────────────────


def _fs_emit(status, reason, metrics, trace=None) -> None:
    """Lean telemetry: ONE unet_fastsafetensors_pipeline event (JSON-safe)
    plus one console line.  Never raises."""
    try:
        _m = _c6_json_safe(dict(metrics))
        _m["status"] = status
        _m["reason"] = reason or ""
        _m.setdefault(
            "loader_execution_identity",
            "fastsafetensors" if status == "ok" else "fallback",
        )
        if trace is not None:
            trace.emit("unet_fastsafetensors_pipeline", phase="restore", metadata=_m)
    except Exception as _exc:
        print(f"[v2.fastsafetensors] emit_error={type(_exc).__name__}", flush=True)
    try:
        print(
            f"[v2.fastsafetensors] status={status} reason={reason or ''} "
            f"total_wall_ms={metrics.get('total_pipeline_wall_ms')} "
            f"gbps={metrics.get('fastsafe_gbps')} "
            f"fallback_count={metrics.get('fallback_count')}",
            flush=True,
        )
    except Exception:
        pass


def _fs_fail(metrics, trace, reason, t0_total, loader=None, fb=None) -> None:
    """Fallback helper: release the fastsafe loader/buffer (device pointers),
    drop tensors, empty the CUDA cache, emit status=fallback with the named
    stage reason.  The caller then runs ``_invoke_original`` fresh exactly
    once.  Never raises."""
    try:
        if fb is not None:
            try:
                fb.close()
            except Exception:
                pass
        elif loader is not None:
            try:
                loader.close()
            except Exception:
                pass
    except Exception:
        pass
    try:
        del fb
    except Exception:
        pass
    try:
        del loader
    except Exception:
        pass
    try:
        _gc.collect()
        import torch as _torch_mf
        _torch_mf.cuda.empty_cache()
    except Exception:
        pass
    try:
        metrics.update({
            "status": "fallback", "reason": reason, "fallback_count": 1,
            "loader_execution_identity": "fallback",
            "total_pipeline_wall_ms": round((_time.monotonic_ns() - t0_total) / 1_000_000, 4),
        })
    except Exception:
        pass
    _fs_emit(metrics.get("status", "fallback"), metrics.get("reason", reason),
             metrics, trace)
    return None


# ── Eligibility ───────────────────────────────────────────────────────────


def _fs_eligible(model_key, kwargs, lane) -> tuple[bool, str]:
    """Narrow ZImage-only eligibility (conditions 2-N; the caller has already
    checked the flag).  Never raises."""
    try:
        import torch as _torch_fe
        _unet_name = str(kwargs.get("unet_name", "") or "")
        _path = _ring_resolve_unet_path(_unet_name, lane)
        if not _path:
            return (False, "path_unresolved")
        _derived = _ring_derive_config(_path)
        if _derived is None:
            return (False, "config_derivation_failed")
        _config, _meta_sd, _header, _n_layers, _prefix = _derived
        if type(_config).__name__ != "ZImage":
            return (False, "family_not_zimage")
        _allow = _c6_value_probe_allow_fp16(_path, _header, _n_layers)
        if _allow is None:
            return (False, "value_probe_unresolved")
        if not _fast_disk_high_vram():
            return (False, "not_high_vram")
        if _fast_disk_torch_future_enabled():
            return (False, "torch_future")
        _evidence = _fast_disk_model_config_evidence(_config)
        if _evidence.get("quant_config_present"):
            return (False, "quant_config_present")
        if _evidence.get("custom_operations_present"):
            return (False, "custom_operations_present")
        if _evidence.get("fp8_optimization"):
            return (False, "fp8_optimization")
        if _evidence.get("force_channels_last"):
            return (False, "force_channels_last")
        _req_wd = str(kwargs.get("weight_dtype", "default") or "default")
        if _req_wd != "default":
            return (False, "dtype_conversion_requested")
        _dtypes = set()
        for _k, _info in _header.items():
            if _k == "__metadata__":
                continue
            _dt = _info.get("dtype", "")
            if _dt:
                _dtypes.add(_dt)
        if len(_dtypes) != 1:
            return (False, "non_uniform_dtype")
        _sd_dt = _c6_safetensors_dtype_map().get(_dtypes.pop())
        if _sd_dt is None:
            return (False, "unsupported_dtype")
        _supported = list(getattr(_config, "supported_inference_dtypes", None) or [])
        if _sd_dt not in _supported:
            return (False, "unsupported_dtype")
        if not _fs_cuda_available():
            return (False, "cuda_unavailable")
        if _fs_fast_module() is None:
            return (False, "fastsafetensors_unavailable")
        _fs_cls = getattr(_fs_fast_module(), "SafeTensorsFileLoader", None)
        if not callable(_fs_cls):
            return (False, "fastsafetensors_unavailable")
        _torch_fe.empty(0)  # touch torch (already imported)
        return (True, "")
    except Exception:
        return (False, "eligibility_error")


def _fs_staged_eligible(model_key, kwargs, lane) -> tuple[bool, str]:
    try:
        _unet_name = str(kwargs.get("unet_name", "") or "")
        _path = _ring_resolve_unet_path(_unet_name, lane)
        if not _path:
            return (False, "path_unresolved")
        _derived = _ring_derive_config(_path)
        if _derived is None:
            return (False, "config_derivation_failed")
        _config, _meta_sd, _header, _n_layers, _prefix = _derived
        if _c6_value_probe_allow_fp16(_path, _header, _n_layers) is None:
            return (False, "value_probe_unresolved")
        if not _fast_disk_high_vram():
            return (False, "not_high_vram")
        if _fast_disk_torch_future_enabled():
            return (False, "torch_future")
        _evidence = _fast_disk_model_config_evidence(_config)
        if _evidence.get("quant_config_present"):
            return (False, "quant_config_present")
        if _evidence.get("custom_operations_present"):
            return (False, "custom_operations_present")
        if _evidence.get("fp8_optimization"):
            return (False, "fp8_optimization")
        if _evidence.get("force_channels_last"):
            return (False, "force_channels_last")
        if str(kwargs.get("weight_dtype", "default") or "default") != "default":
            return (False, "dtype_conversion_requested")
        _dtypes = {
            _info.get("dtype", "")
            for _key, _info in _header.items()
            if _key != "__metadata__" and _info.get("dtype", "")
        }
        if len(_dtypes) != 1:
            return (False, "non_uniform_dtype")
        _sd_dtype = _c6_safetensors_dtype_map().get(next(iter(_dtypes)))
        if _sd_dtype is None:
            return (False, "unsupported_dtype")
        if _sd_dtype not in list(getattr(_config, "supported_inference_dtypes", None) or []):
            return (False, "unsupported_dtype")
        if not _fs_cuda_available():
            return (False, "cuda_unavailable")
        _module = _fs_staged_module()
        if _module is None:
            return (False, "staged_transport_unavailable")
        for _names in (
            ("build_plan", "build_staged_plan", "plan_staged_transport", "make_staged_plan", "plan"),
            ("prepare", "prepare_staged", "prepare_staged_transport", "prepare_plan"),
            ("commit", "commit_staged", "commit_staged_transport", "commit_plan"),
        ):
            if _fs_staged_fn(_module, _names) is None:
                return (False, "staged_transport_unavailable")
        return (True, "")
    except Exception:
        return (False, "staged_eligibility_error")


# ── Worker A: meta construction (C8 strategy) ─────────────────────────────


def _fs_meta_construct(config, meta_sd, metrics, *, worker_ident=None) -> Any:
    """Meta ZImage construction + model_sampling repair OUTSIDE the meta
    context.  Returns the model; raises RuntimeError on any gate failure."""
    import threading as _th_f
    _t_import = _time.monotonic_ns()
    _t_func_cpu0 = None
    try:
        _t_func_cpu0 = _time.thread_time()
    except Exception:
        pass
    # High-resolution entry stamp for the direct-call execution wall.  On
    # Windows, time.monotonic_ns() has ~15.6 ms granularity (GetTickCount64),
    # which cannot resolve sub-ms direct calls; perf_counter_ns (QPC) can.
    _t_func_perf0 = _time.perf_counter_ns()
    import torch as _torch_ma
    # When no worker ident is supplied (direct calls), profile the current
    # thread so the deep-profiler accumulation matches.
    _wid = worker_ident if worker_ident is not None else _th_f.get_ident()
    _forensics_on = _fs_forensics_enabled()
    metrics["meta_import_wall_ms"] = round(
        (_time.monotonic_ns() - _t_import) / 1_000_000, 4)
    _t_gm = _time.monotonic_ns()
    with _torch_ma.no_grad(), _torch_ma.device("meta"):
        metrics["meta_context_entry_wall_ms"] = round(
            (_time.monotonic_ns() - _t_gm) / 1_000_000, 4)
        # ── Forensics-gated deep profile (never breaks the load) ──
        _forensics_error = None
        _construct_agg: dict[str, Any] = {}
        _first_op = {"ns": None}
        _gc_state: dict[str, Any] = {"total_ns": 0, "count": 0, "cur": None}
        _orig_init = None
        _gc_cb = None
        if _forensics_on:
            try:
                _orig_init = _torch_ma.nn.Module.__init__

                def _forensic_init(self, *a, **k):
                    _m_t0 = _time.monotonic_ns()
                    try:
                        _orig_init(self, *a, **k)
                    finally:
                        if _th_f.get_ident() == _wid:
                            if _first_op["ns"] is None:
                                _first_op["ns"] = _m_t0
                            _entry = _construct_agg.setdefault(
                                type(self).__name__, {"count": 0, "wall_ms": 0.0})
                            _entry["count"] += 1
                            _entry["wall_ms"] += (
                                _time.monotonic_ns() - _m_t0) / 1_000_000

                _torch_ma.nn.Module.__init__ = _forensic_init
            except Exception as _exc:
                _forensics_error = f"module_init_install:{type(_exc).__name__}"
            try:
                def _forensic_gc(_phase, _info):
                    _now = _time.monotonic_ns()
                    if _phase == "start":
                        _gc_state["cur"] = _now
                    elif _phase == "stop" and _gc_state["cur"] is not None:
                        _gc_state["total_ns"] += _now - _gc_state["cur"]
                        _gc_state["cur"] = None
                        _gc_state["count"] += 1

                _gc_cb = _forensic_gc
                _gc.callbacks.append(_gc_cb)
            except Exception as _exc:
                _forensics_error = _forensics_error or (
                    f"gc_callback_install:{type(_exc).__name__}")
        try:
            _model = config.get_model(meta_sd, "")
        finally:
            if _forensics_on:
                try:
                    if _orig_init is not None:
                        _torch_ma.nn.Module.__init__ = _orig_init
                except Exception as _exc:
                    _forensics_error = _forensics_error or (
                        f"module_init_restore:{type(_exc).__name__}")
                try:
                    if _gc_cb is not None:
                        try:
                            _gc.callbacks.remove(_gc_cb)
                        except Exception:
                            pass
                except Exception as _exc:
                    _forensics_error = _forensics_error or (
                        f"gc_callback_remove:{type(_exc).__name__}")
                try:
                    metrics["meta_module_construct_ms_by_class"] = _construct_agg
                    metrics["meta_module_construct_total_wall_ms"] = round(
                        sum(_e["wall_ms"] for _e in _construct_agg.values()), 4)
                    metrics["meta_module_construct_count"] = sum(
                        _e["count"] for _e in _construct_agg.values())
                    if _first_op["ns"] is not None:
                        metrics["meta_module_first_op_wall_ms"] = round(
                            (_first_op["ns"] - _t_gm) / 1_000_000, 4)
                    metrics["meta_gc_wall_ms"] = round(
                        _gc_state["total_ns"] / 1_000_000, 4)
                    metrics["meta_gc_count"] = _gc_state["count"]
                    if _forensics_error is not None:
                        metrics["meta_forensics_error"] = _forensics_error
                except Exception as _exc:
                    metrics["meta_forensics_error"] = (
                        f"forensics_finalize:{type(_exc).__name__}")
    metrics["meta_get_model_wall_ms"] = round(
        (_time.monotonic_ns() - _t_gm) / 1_000_000, 4)
    _t_validate = _time.monotonic_ns()
    _meta_params = list(_model.parameters())
    if not _meta_params or not all(_p.device.type == "meta" for _p in _meta_params):
        metrics["meta_param_validate_wall_ms"] = round(
            (_time.monotonic_ns() - _t_validate) / 1_000_000, 4)
        raise RuntimeError("meta_construction_failed")
    metrics["meta_param_validate_wall_ms"] = round(
        (_time.monotonic_ns() - _t_validate) / 1_000_000, 4)
    _t_detect = _time.monotonic_ns()
    _sampling = getattr(_model, "model_sampling", None)
    _poisoned = collect_meta_tensors(_sampling) if _sampling is not None else []
    metrics["meta_sampling_detect_wall_ms"] = round(
        (_time.monotonic_ns() - _t_detect) / 1_000_000, 4)
    metrics["sampling_poisoned_tensors"] = len(_poisoned)
    if _poisoned:
        _ms_fn = _c6_comfy_fn("comfy.model_base", "model_sampling")
        if not callable(_ms_fn):
            raise RuntimeError("sampling_fix_unavailable")
        _t_fix = _time.monotonic_ns()
        _model.model_sampling = _ms_fn(_model.model_config, _model.model_type)
        metrics["sampling_fix_wall_ms"] = round(
            (_time.monotonic_ns() - _t_fix) / 1_000_000, 4)
        _after = collect_meta_tensors(getattr(_model, "model_sampling", None))
        if _after:
            raise RuntimeError("sampling_fix_incomplete")
    else:
        metrics["sampling_fix_wall_ms"] = 0.0
    _t_retprep = _time.monotonic_ns()
    metrics["meta_return_prep_wall_ms"] = round(
        (_time.monotonic_ns() - _t_retprep) / 1_000_000, 4)
    # Direct-call reconcile support: when invoked WITHOUT the _worker_a closure
    # (e.g. the D4 tests), publish this function's own entry->exit wall;
    # lifecycle == execution (no measurable start delay).  The closure runs
    # AFTER this function and overwrites these with closure-scoped stamps, so
    # pipeline values remain unchanged.  The wall uses perf_counter_ns (see the
    # entry-stamp comment above) so warm sub-ms direct calls still read > 0.
    # Never raises.
    try:
        _t_func_end = _time.perf_counter_ns()
        _func_wall_ms = round(
            (_t_func_end - _t_func_perf0) / 1_000_000, 4)
        _func_cpu_ms = None
        if _t_func_cpu0 is not None:
            try:
                _func_cpu_ms = round(
                    (_time.thread_time() - _t_func_cpu0) * 1000, 4)
            except Exception:
                _func_cpu_ms = None
        metrics["meta_worker_execution_wall_ms"] = _func_wall_ms
        metrics["meta_lifecycle_total_ms"] = _func_wall_ms
        metrics["meta_worker_thread_cpu_ms"] = _func_cpu_ms
        metrics["meta_non_thread_cpu_wall_ms"] = (
            None if _func_cpu_ms is None
            else round(max(0.0, _func_wall_ms - _func_cpu_ms), 4))
        metrics["meta_worker_effective_cores"] = _trace_effective_cores_from(
            _func_cpu_ms, _func_wall_ms)
        metrics.update(_fs_meta_reconcile(
            start_delay_ms=0.0,
            execution_wall_ms=_func_wall_ms,
            import_ms=metrics.get("meta_import_wall_ms"),
            context_entry_ms=metrics.get("meta_context_entry_wall_ms"),
            get_model_ms=metrics.get("meta_get_model_wall_ms"),
            param_validate_ms=metrics.get("meta_param_validate_wall_ms"),
            sampling_detect_ms=metrics.get("meta_sampling_detect_wall_ms"),
            sampling_fix_ms=metrics.get("sampling_fix_wall_ms"),
            return_prep_ms=metrics.get("meta_return_prep_wall_ms"),
            lifecycle_total_ms=_func_wall_ms,
        ))
    except Exception:
        pass
    return _model


# ── Worker B: fastsafetensors concurrent file→CUDA ────────────────────────


def _fs_fastsafe_load(path, device, metrics) -> tuple[dict, Any, Any]:
    """Run the fastsafetensors nogds pool (E28 tuned: threads=8, 256 MiB
    blocks, use_buf_register=False — env-overridable) against the file on
    the target device.  Returns (tensors, loader, fb).  The loader+fb MUST
    be retained by the caller for the tensors' lifetime (Gate 1) — close()
    is only ever called on failure.  Raises RuntimeError on any failure."""
    _mod = _fs_fast_module()
    if _mod is None:
        raise RuntimeError("fastsafetensors_unavailable")
    _cls = getattr(_mod, "SafeTensorsFileLoader", None)
    if not callable(_cls):
        raise RuntimeError("fastsafetensors_unavailable")
    _t_setup = _time.monotonic_ns()
    _loader = _cls(None, str(device), max_threads=_fs_effective_threads(),
                   bbuf_size_kb=_fs_effective_bbuf_kb(),
                   nogds=_FS_NOGDS, disable_cache=True)
    try:
        _loader.add_filenames({0: [str(path)]})
        metrics["fastsafe_setup_wall_ms"] = round(
            (_time.monotonic_ns() - _t_setup) / 1_000_000, 4)
        _t_copy = _time.monotonic_ns()
        _fb = _loader.copy_files_to_device(
            use_buf_register=_FS_USE_BUF_REGISTER,
            max_copy_block_size=_fs_effective_block_bytes(),
        )
        metrics["fastsafe_file_gpu_wall_ms"] = round(
            (_time.monotonic_ns() - _t_copy) / 1_000_000, 4)
        _t_inst = _time.monotonic_ns()
        _keys = list(_loader.get_keys())
        _tensors = {_k: _fb.get_tensor(_k) for _k in _keys}
        metrics["fastsafe_instantiate_wall_ms"] = round(
            (_time.monotonic_ns() - _t_inst) / 1_000_000, 4)
        return _tensors, _loader, _fb
    except Exception:
        try:
            _loader.close()
        except Exception:
            pass
        raise


# ── Residual meta sweep + final validation ────────────────────────────────


def _fs_sweep_meta(model, target) -> int:
    """Materialize residual meta tensors (non-sd buffers and plain-attribute
    tensors) on the target device.  Params are expected to be already
    assigned by the bind; any meta PARAM remaining is a bind failure (raised).
    Returns the number of meta tensors found BEFORE the sweep.  Raises
    RuntimeError when residual meta remains after the sweep."""
    import torch as _torch_sm
    _found = collect_meta_tensors(model)
    _meta_count = len(_found)
    if _meta_count == 0:
        return 0
    # Module buffers/params: replace via setattr on the owning module.
    _seen = set()

    def _walk(o, p, depth):
        if depth > _FS_META_SWEEP_DEPTH or id(o) in _seen:
            return
        _seen.add(id(o))
        if isinstance(o, _torch_sm.nn.Module):
            for _name, _param in list(o._parameters.items()):
                if isinstance(_param, _torch_sm.Tensor) and _param.device.type == "meta":
                    raise RuntimeError("meta_param_after_bind:" + f"{p}.{_name}")
            for _name, _buf in list(o._buffers.items()):
                if isinstance(_buf, _torch_sm.Tensor) and _buf.device.type == "meta":
                    _fresh = _torch_sm.zeros(
                        list(_buf.shape), dtype=_buf.dtype, device=target)
                    try:
                        setattr(o, _name, _fresh)
                    except Exception:
                        raise RuntimeError("meta_buffer_sweep_failed:" + f"{p}.{_name}")
            for _name, _mod in list(o._modules.items()):
                if _mod is not None:
                    _walk(_mod, f"{p}.{_name}" if p else _name, depth + 1)
            try:
                _plain = dict(vars(o))
            except Exception:
                _plain = {}
            for _name, _v in _plain.items():
                if _name in ("_parameters", "_buffers", "_modules",
                             "_non_persistent_buffers_set"):
                    continue
                if _name in o._parameters or _name in o._buffers or _name in o._modules:
                    continue
                if isinstance(_v, _torch_sm.Tensor) and _v.device.type == "meta":
                    _fresh = _torch_sm.zeros(
                        list(_v.shape), dtype=_v.dtype, device=target)
                    try:
                        setattr(o, _name, _fresh)
                    except Exception:
                        raise RuntimeError("meta_attr_sweep_failed:" + f"{p}.{_name}")
                elif _v is not None and not callable(_v):
                    _walk(_v, f"{p}.{_name}" if p else _name, depth + 1)
            return
        if isinstance(o, dict):
            _seen.add(id(o))
            for _k, _v in o.items():
                if isinstance(_v, _torch_sm.Tensor) and _v.device.type == "meta":
                    raise RuntimeError("meta_dict_value:" + f"{p}[{_k}]")
                _walk(_v, f"{p}[{_k}]", depth + 1)
            return
        if isinstance(o, (list, tuple)):
            _seen.add(id(o))
            for _i, _v in enumerate(o):
                if isinstance(_v, _torch_sm.Tensor) and _v.device.type == "meta":
                    raise RuntimeError("meta_list_value:" + f"{p}[{_i}]")
                _walk(_v, f"{p}[{_i}]", depth + 1)
            return
        if isinstance(o, _torch_sm.Tensor) and o.device.type == "meta":
            raise RuntimeError("meta_plain_tensor:" + p)

    _walk(model, "", 0)
    _after = collect_meta_tensors(model)
    if _after:
        raise RuntimeError("residual_meta_after_sweep")
    return _meta_count


def _fs_validate_final(model, target) -> dict:
    """Final GPU-ready validation: every parameter on the target device,
    uniform supported dtype, first param on target, zero meta tensors."""
    import torch as _torch_vf
    _params = list(model.parameters())
    _devs = {str(_p.device) for _p in _params}
    _dtypes = {str(_p.dtype) for _p in _params}
    _first = _params[0] if _params else None
    _meta = collect_meta_tensors(model)
    return {
        "param_count": len(_params),
        "param_devices": sorted(_devs),
        "param_dtypes": sorted(_dtypes),
        "first_param_device": str(getattr(_first, "device", None)) if _first is not None else None,
        "first_param_dtype": str(getattr(_first, "dtype", None)) if _first is not None else None,
        "residual_meta_count": len(_meta),
        "all_params_on_target": bool(_params) and all(
            str(_p.device) == str(target) for _p in _params),
    }


# ── Pure reconciliation helpers (Task 1 + Task 4 audit) ───────────────────


def _fs_pipeline_reconcile(total_ms, accounting_intervals) -> dict:
    """Reconcile the serial accounting intervals against the pipeline total.

    *accounting_intervals* is a list of ``(name, start_mono_ns, end_mono_ns)``
    ABSOLUTE monotonic stamps (relative to the pipeline t0).  Returns a dict
    with ``pipeline_total_ms``, ``accounting_children_ms`` (sum of interval
    durations), ``residual_ms``, ``reconciliation_status`` ("OK" when
    |residual| < 10.0), ``accounting_disjoint`` and
    ``accounting_overlap_detail`` (from ``forensic_intervals_disjoint``).
    Never raises."""
    _children = 0.0
    try:
        for _name, _start, _end in accounting_intervals or []:
            _children += max(0, int(_end) - int(_start)) / 1_000_000
    except Exception:
        pass
    _residual = None
    if isinstance(total_ms, (int, float)):
        _residual = float(total_ms) - _children
    _status = "OK" if (isinstance(_residual, (int, float))
                       and abs(_residual) < 10.0) else "GAP"
    try:
        _disjoint, _detail = _trace_forensic_intervals_disjoint(
            list(accounting_intervals or []))
    except Exception:
        _disjoint, _detail = True, None
    return {
        "pipeline_total_ms": total_ms,
        "accounting_children_ms": round(_children, 4),
        "residual_ms": (round(_residual, 4)
                        if isinstance(_residual, (int, float)) else None),
        "reconciliation_status": _status,
        "accounting_disjoint": bool(_disjoint),
        "accounting_overlap_detail": _detail,
    }


def _fs_meta_reconcile(*, start_delay_ms, execution_wall_ms, import_ms,
                       context_entry_ms, get_model_ms, param_validate_ms,
                       sampling_detect_ms, sampling_fix_ms, return_prep_ms,
                       lifecycle_total_ms) -> dict:
    """Compute the meta-worker reconciliation keys (Task 1 semantics).

    Execution children are nested detail INSIDE the execution wall and are
    counted once: lifecycle children = start_delay + execution_wall.  All
    arithmetic is None-safe (None treated as 0.0).  Returns the five derived
    keys: ``meta_execution_children_ms``, ``meta_execution_residual_ms``,
    ``meta_lifecycle_children_ms``, ``meta_lifecycle_residual_ms``,
    ``meta_reconcile_status``.
    """
    def _f(v):
        return float(v) if isinstance(v, (int, float)) else 0.0

    _exec_children = (_f(import_ms) + _f(context_entry_ms) + _f(get_model_ms)
                      + _f(param_validate_ms) + _f(sampling_detect_ms)
                      + _f(sampling_fix_ms) + _f(return_prep_ms))
    _exec_residual = _f(execution_wall_ms) - _exec_children
    _life_children = _f(start_delay_ms) + _f(execution_wall_ms)
    _life_residual = _f(lifecycle_total_ms) - _life_children
    return {
        "meta_execution_children_ms": round(_exec_children, 4),
        "meta_execution_residual_ms": round(_exec_residual, 4),
        "meta_lifecycle_children_ms": round(_life_children, 4),
        "meta_lifecycle_residual_ms": round(_life_residual, 4),
        "meta_reconcile_status": "OK" if abs(_life_residual) < 5.0 else "GAP",
    }


# ── Orchestrator ──────────────────────────────────────────────────────────


def _fs_try_pipeline(bridge, model_key, kwargs, lane) -> tuple[Any, ...] | None:
    """Fastsafetensors UNET fast path.  Returns ``(patcher,)`` on success
    (flows through the unchanged ``_load_unet`` tail); None on ineligible /
    fallback (the caller then runs ``_invoke_original`` fresh exactly once).

    Worker A (meta construction) runs CONCURRENTLY with worker B (fastsafe
    file→CUDA); the join cost and both worker walls are measured."""
    _lane = lane if lane is not None else _ACTIVE_LANE_TRACE.get()
    _trace = getattr(_lane, "_trace", None) if _lane is not None else None
    if _trace is None:
        _trace = _ACTIVE_REQUEST_TRACE.get()
    _t0_total = _time.monotonic_ns()
    # Forensic registry request id (from the resolved trace, when available).
    _fs_req_id = getattr(_trace, "request_id", None) if _trace is not None else None
    if not isinstance(_fs_req_id, str) or not _fs_req_id:
        _fs_req_id = None
    if _fs_req_id:
        _gpu_coord.start_request(_fs_req_id, _trace)
    # Process CPU affinity count (shared by both worker registry records).
    _cpu_affinity_count = _trace_cpu_affinity_count()
    # Serial accounting intervals (name, start_mono_ns, end_mono_ns), absolute
    # monotonic stamps relative to t0.  The parallel worker executions are
    # NESTED detail inside join_delay and are intentionally NOT added here.
    _acct: list[tuple[str, int, int]] = []

    def _acct_add(name, start_ns):
        try:
            _acct.append((name, int(start_ns), _time.monotonic_ns()))
        except Exception:
            pass

    _metrics: dict[str, Any] = {
        "flag": "on", "eligibility": "ok", "family": "", "reason": "",
        "loader_version": _fs_fastsafe_version(), "threads": _fs_effective_threads(),
        "max_copy_block_size_bytes": _fs_effective_block_bytes(),
        "nogds": _FS_NOGDS, "use_buf_register": _FS_USE_BUF_REGISTER,
        "header_config_wall_ms": None, "value_probe_wall_ms": None,
        "meta_get_model_wall_ms": None, "sampling_fix_wall_ms": None,
        "sampling_poisoned_tensors": 0, "fastsafe_setup_wall_ms": None,
        "fastsafe_file_gpu_wall_ms": None, "fastsafe_instantiate_wall_ms": None,
        "worker_a_wall_ms": None, "worker_b_wall_ms": None, "join_delay_ms": None,
        "tensor_count": 0, "param_count": 0, "total_bytes": 0,
        "fastsafe_gbps": 0.0, "bind_wall_ms": None,
        "copy_event_recorded": False, "copy_event_waited": False,
        "copy_event_sync_method": "",
        "owner_mode": "loader_retained", "owner_attr": _FS_OWNER_ATTR,
        "clone_required": False, "data_ptr_sample_match": None,
        "data_ptr_sample_keys": [], "residual_meta_before_sweep": 0,
        "residual_meta_after": 0, "final_to_wall_ms": None,
        "final_sync_wall_ms": None, "final_validation": {},
        "transform_independent": None, "key_set_ok": None,
        "spot_check": {}, "sd_unmapped_keys": [],
        "model_only_param_count": 0, "model_only_buffer_count": 0,
        "staged_transport": False,
        "unet_staged_prepare_ms": None,
        "unet_staged_commit_ms": None,
        "unet_staged_h2d_ms": None,
        "unet_staged_bind_ms": None,
        "unet_staged_fallback_reason": "",
        "native_pin_budget_available": None,
        "local_bounded_budget_used": False,
        "native_pin_budget_rejected": False,
        "fallback_count": 0, "total_pipeline_wall_ms": 0.0, "status": "ok",
    }
    _metrics["metrics_init_wall_ms"] = round(
        (_time.monotonic_ns() - _t0_total) / 1_000_000, 4)
    _acct_add("metrics_init", _t0_total)
    _metrics["forensics_enabled"] = _fs_forensics_enabled()
    _metrics["cpu_affinity_count"] = _cpu_affinity_count
    _loader = None
    _fb = None
    _tensors: dict[str, Any] = {}
    _worker_b_result: dict[str, Any] = {}
    _staged_active = False
    try:
        import torch as _torch_tp
        _unet_name = str(kwargs.get("unet_name", "") or "")
        _path = _ring_resolve_unet_path(_unet_name, _lane)
        if not _path:
            return _fs_fail(_metrics, _trace, "stage:path_unresolved", _t0_total)
        try:
            from .fast_cold_orchestration import get_controller

            _orchestration = get_controller(_fs_req_id or "", _trace)
            if _orchestration is not None:
                _orchestration.set_paths("unet", [_path])
        except Exception:
            _orchestration = None
        # Eligibility (pre-construction; cheap).
        _t_el = _time.monotonic_ns()
        _staged_requested = _fs_staged_transport_enabled()
        if _staged_requested:
            _ok, _reason = _fs_staged_eligible(model_key, kwargs, _lane)
            if _ok:
                _staged_active = True
            else:
                _ok, _reason = _fs_eligible(model_key, kwargs, _lane)
        else:
            _ok, _reason = _fs_eligible(model_key, kwargs, _lane)
        _metrics["eligibility_wall_ms"] = round(
            (_time.monotonic_ns() - _t_el) / 1_000_000, 4)
        _acct_add("eligibility", _t_el)
        if not _ok:
            _metrics.update({"eligibility": "ineligible", "reason": _reason,
                             "status": "ineligible"})
            _fs_emit(_metrics.get("status"), _metrics.get("reason"), _metrics, _trace)
            return None
        _metrics["eligibility"] = "ok"
        # Config derivation (header only).
        _t_cfg = _time.monotonic_ns()
        _probe_wall: dict[str, Any] = {}
        _derived = _ring_derive_config(_path, _probe_wall=_probe_wall)
        if _derived is None:
            return _fs_fail(_metrics, _trace, "stage:config_derivation_failed", _t0_total)
        _config, _meta_sd, _header, _n_layers, _prefix = _derived
        _metrics["header_config_wall_ms"] = round(
            (_time.monotonic_ns() - _t_cfg) / 1_000_000, 4)
        _acct_add("header_config", _t_cfg)
        _metrics["value_probe_wall_ms"] = _probe_wall.get("value_probe_wall_ms")
        _metrics["family"] = type(_config).__name__
        if not _staged_active and type(_config).__name__ != "ZImage":
            _metrics.update({"family": type(_config).__name__, "eligibility": "ineligible",
                             "reason": "family_not_zimage", "status": "ineligible"})
            _fs_emit(_metrics.get("status"), _metrics.get("reason"), _metrics, _trace)
            return None
        # Config parity gates (mirror C8/I-3 fail-closed semantics).
        _t_pg = _time.monotonic_ns()
        _exp_count = _FS_EXPECTED_PARAM_COUNT
        _hdr_count = 0
        for _k, _info in _header.items():
            if _k == "__metadata__":
                continue
            try:
                _n = 1
                for _s in (_info.get("shape") or []):
                    _n *= int(_s)
                _hdr_count += _n
            except Exception:
                _hdr_count = -1
                break
        if not _staged_active and _hdr_count != _exp_count:
            return _fs_fail(_metrics, _trace,
                            f"stage:param_count_mismatch:{_hdr_count}", _t0_total)
        _supported = list(getattr(_config, "supported_inference_dtypes", None) or [])
        try:
            _bf16_ok = _torch_tp.bfloat16 in _supported
        except Exception:
            _bf16_ok = False
        if not _staged_active and not _bf16_ok:
            return _fs_fail(_metrics, _trace, "stage:bf16_not_supported", _t0_total)
        _metrics["staged_transport"] = _staged_active
        _metrics["loader_execution_identity"] = (
            "staged" if _staged_active else "fastsafetensors"
        )
        if _staged_active:
            _metrics["owner_mode"] = "staged_retained"
            _metrics["owner_attr"] = _STAGED_OWNER_ATTR
        _metrics["parity_gate_wall_ms"] = round(
            (_time.monotonic_ns() - _t_pg) / 1_000_000, 4)
        _acct_add("parity_gate", _t_pg)
        _t_tm = _time.monotonic_ns()
        _target = _fs_get_target()
        if _target is None:
            return _fs_fail(_metrics, _trace, "stage:cuda_unavailable", _t0_total)
        # Memory baseline (Gate 2).
        _mem0 = _fs_memory_snapshot()
        _metrics["target_and_mem_wall_ms"] = round(
            (_time.monotonic_ns() - _t_tm) / 1_000_000, 4)
        _acct_add("target_and_mem", _t_tm)
        # ── Workers: A meta construction ∥ B fastsafe file→CUDA ──
        _worker_a_result: dict[str, Any] = {}

        def _worker_a():
            _wa0 = _time.monotonic_ns()
            _wa_ident = None
            _wa_cpu0 = None
            try:
                try:
                    if _trace is not None:
                        _trace.emit(
                            "unet_cpu_prepare_start",
                            phase="execution",
                            metadata={
                                "request_id": _fs_req_id or "",
                                "reason": "meta_model_construction",
                                "cache_state": "not_applicable",
                            },
                        )
                except Exception:
                    pass
                try:
                    _wa_ident = _th.get_ident()
                    _wa_cpu0 = _time.thread_time()
                except Exception:
                    pass
                if _orchestration is not None:
                    _orchestration.record_meta("start")
                _m = _fs_meta_construct(_config, _meta_sd, _metrics,
                                        worker_ident=_wa_ident)
                _worker_a_result["model"] = _m
                _worker_a_result["wall_ms"] = round(
                    (_time.monotonic_ns() - _wa0) / 1_000_000, 4)
                try:
                    if _trace is not None:
                        _trace.emit(
                            "unet_cpu_prepare_ready",
                            phase="execution",
                            metadata={
                                "request_id": _fs_req_id or "",
                                "reason": "meta_model_construction",
                                "cache_state": "not_applicable",
                                "prepare_ms": _worker_a_result["wall_ms"],
                            },
                        )
                except Exception:
                    pass
                if _orchestration is not None:
                    _orchestration.record_meta("ready")
                _metrics["meta_worker_execution_wall_ms"] = (
                    _worker_a_result["wall_ms"])
                if _wa_cpu0 is not None:
                    try:
                        _cpu_ms = round(
                            (_time.thread_time() - _wa_cpu0) * 1000, 4)
                    except Exception:
                        _cpu_ms = None
                    _metrics["meta_worker_thread_cpu_ms"] = _cpu_ms
                    _metrics["worker_a_thread_cpu_ms"] = _cpu_ms
                else:
                    _metrics["meta_worker_thread_cpu_ms"] = None
                    _metrics["worker_a_thread_cpu_ms"] = None
                try:
                    _exec = _metrics.get("meta_worker_execution_wall_ms")
                    _tcp = _metrics.get("meta_worker_thread_cpu_ms")
                    _metrics["meta_non_thread_cpu_wall_ms"] = (
                        None if _tcp is None or _exec is None
                        else round(max(0.0, float(_exec) - float(_tcp)), 4))
                    _metrics["meta_worker_effective_cores"] = (
                        _trace_effective_cores_from(_tcp, _exec))
                    _metrics["worker_a_effective_cores"] = (
                        _metrics["meta_worker_effective_cores"])
                except Exception:
                    _metrics["meta_non_thread_cpu_wall_ms"] = None
            except Exception as _exc:
                _worker_a_result["error"] = f"{type(_exc).__name__}:{str(_exc)[:160]}"
            finally:
                try:
                    _wa_end = _time.monotonic_ns()
                    _worker_a_result["start_mono_ns"] = _wa0
                    _worker_a_result["end_mono_ns"] = _wa_end
                    _metrics["meta_lifecycle_total_ms"] = round(
                        max(0, _wa_end - _t_ta_create) / 1_000_000, 4)
                    _trace_register_forensic_interval(
                        "fastsafe_worker_a",
                        start_mono_ns=_wa0,
                        end_mono_ns=_wa_end,
                        cpu_ms=_metrics.get("meta_worker_thread_cpu_ms"),
                        metadata={
                            "request_id": _fs_req_id,
                            "cpu_affinity_count": _cpu_affinity_count,
                            "effective_cores": _metrics.get(
                                "meta_worker_effective_cores"),
                        },
                    )
                except Exception:
                    pass

        def _worker_b():
            _wb0 = _time.monotonic_ns()
            _wb_cpu0 = None
            _transfer_started_ns = 0
            _transfer_started = False
            _staged_plan_value = None
            _staged_prepared_value = None
            _staged_committed_value = None
            _staged_inner_owner = None
            try:
                try:
                    _wb_cpu0 = _time.thread_time()
                except Exception:
                    pass
                # ── E28: the D15 UNET GPU gate must NOT cover the source
                # read / CPU preparation (the user-visible serialization bug:
                # the gate token was held from worker start across the full
                # cold file read, blocking the CLIP encode for ~11.6 s).  The
                # source fence + orchestration start remain here (not GPU
                # gates); the D15 token is acquired only for the actual GPU
                # commit section (copy-event record + H2D wait + bind/sync)
                # later in this worker.
                if _orchestration is not None:
                    if not _orchestration.before_unet_demand([_path]):
                        raise RuntimeError("structural_source_fence_failure:unet")
                    _orchestration.record_fastsafe("unet", "start", event_recorded=False)
                if _staged_active:
                    _staged_plan_value = _fs_staged_plan(
                        _path, _header, _target)
                    _t_prepare = _time.monotonic_ns()
                    try:
                        _staged_prepared_value = _fs_staged_prepare(
                            _staged_plan_value)
                    finally:
                        _metrics["unet_staged_prepare_ms"] = round(
                            (_time.monotonic_ns() - _t_prepare) / 1_000_000, 4)
                    _t_commit = _time.monotonic_ns()
                    try:
                        _staged_committed_value = _fs_staged_commit(
                            _staged_prepared_value, _target)
                        _t, _staged_inner_owner, _staged_metrics = (
                            _fs_staged_result(_staged_committed_value))
                        for _name in (
                            "checkpoint_bytes",
                            "disk_to_stage_ms",
                            "cpu_cast_ms",
                            "cpu_cast_bytes",
                            "exact_copy_bytes",
                            "h2d_enqueue_ms",
                            "h2d_device_ms",
                            "effective_h2d_gbps",
                            "producer_wait_ms",
                            "consumer_wait_ms",
                            "peak_pinned_bytes",
                            "pinned_fast_path_active",
                            "contiguous_gpu_buckets_active",
                            "native_pin_budget_available",
                            "local_bounded_budget_used",
                            "native_pin_budget_rejected",
                            "host_slab_is_pinned",
                            "host_slab_is_pinned_all",
                            "host_slab_is_pinned_per_slot",
                            "bucket_bytes",
                            "host_bucket_bytes_configured",
                            "host_slab_count",
                            "gpu_bucket_count",
                            "packed_model_bytes",
                            "h2d_bucket_count",
                            "h2d_full_bucket_count",
                            "h2d_final_bucket_bytes",
                            "min_h2d_copy_bytes",
                            "median_h2d_copy_bytes",
                            "max_h2d_copy_bytes",
                            "h2d_stream_span_ms",
                            "h2d_dma_busy_ms",
                            "h2d_stream_idle_estimate_ms",
                            "h2d_dma_gbps",
                            "h2d_span_gbps",
                            "slab_reuse_wait_ms",
                            "tensor_count",
                            "producer_count",
                            "copy_count",
                            "non_blocking",
                            "stream_count",
                            "source_read_ms",
                            "source_materialization_ms",
                            "bucket_pack_cpu_ms",
                            "bucket_ready_wait_ms",
                            "source_order_enabled",
                            "source_order_eligible",
                            "source_order_fallback_reason",
                            "source_file_count",
                            "source_tensor_count",
                            "source_model_bytes",
                            "source_read_calls",
                            "source_read_min_bytes",
                            "source_read_median_bytes",
                            "source_read_max_bytes",
                            "source_sequential_bytes",
                            "source_repack_bytes",
                            "source_read_wall_ms",
                            "source_read_worker_accumulated_ms",
                            "source_to_pinned_copy_bytes",
                            "source_to_pinned_copy_ms",
                            "alignment_fallback_tensor_count",
                        ):
                            _value = _staged_metrics.get(_name)
                            if _value is not None:
                                _metrics[_name] = _value
                                _metrics[f"unet_staged_{_name}"] = _value
                        _fs_staged_metric(
                            _metrics, _staged_metrics, "unet_staged_h2d_ms",
                            ("h2d_ms", "h2d_wall_ms", "h2d_device_ms",
                             "h2d_enqueue_ms", "cuda_ms", "gpu_ms"),
                        )
                    finally:
                        _metrics["unet_staged_commit_ms"] = round(
                            (_time.monotonic_ns() - _t_commit) / 1_000_000, 4)
                    if _metrics.get("unet_staged_h2d_ms") is None:
                        _metrics["unet_staged_h2d_ms"] = (
                            _metrics.get("unet_staged_commit_ms"))
                    _worker_b_result["tensors"] = _t
                    _worker_b_result["loader"] = None
                    _worker_b_result["fb"] = _StagedTransportOwner(
                        _staged_plan_value,
                        _staged_prepared_value,
                        _staged_committed_value,
                        _staged_inner_owner,
                    )
                    _worker_b_result["transport"] = "staged"
                else:
                    _e27_uread_start = _time.monotonic_ns()
                    _t, _ld, _f = _fs_fastsafe_load(_path, _target, _metrics)
                    _e27_uread_end = _time.monotonic_ns()
                    # E27: UNET source-read span on the shared monotonic axis.
                    try:
                        from .e27_forensics import emit_e27_span

                        emit_e27_span(
                            "unet_source_read",
                            start_ns=_e27_uread_start,
                            end_ns=_e27_uread_end,
                            path=_path,
                            total_bytes=_metrics.get("total_bytes"),
                        )
                    except Exception:
                        pass
                    _worker_b_result["tensors"] = _t
                    _worker_b_result["loader"] = _ld
                    _worker_b_result["fb"] = _f
                    _worker_b_result["transport"] = "fastsafe"
                # ── E28: acquire the D15 UNET GPU token HERE — only for the
                # GPU-committing section (copy-event record, H2D wait, and
                # the later bind/sync).  The cold source read above ran
                # WITHOUT the token so the CLIP encode is never blocked
                # behind the UNET file read.  The token is released in the
                # pipeline ``finally`` via ``end_unet_gpu_phase``.
                _gate = _gpu_coord.begin_unet_gpu_phase(
                    _fs_req_id or "", _trace,
                    reason="clip_gpu_critical_active",
                )
                _worker_b_result["gpu_gate"] = _gate
                _transfer_started_ns = _gpu_coord.unet_transfer_start(
                    _gate,
                    reason=("staged_transport" if _staged_active
                            else "direct_gpu_fastsafetensors"),
                )
                _transfer_started = True
                _copy_event = None
                if _fs_scoped_cuda_readiness_enabled():
                    _copy_event = _gpu_coord.record_copy_event(
                        "unet",
                        _trace,
                        stream=_torch_tp.cuda.current_stream(device=_target),
                    )
                    if _copy_event is None:
                        raise RuntimeError("scoped_copy_event_unavailable")
                _worker_b_result["copy_event"] = _copy_event
                _metrics["copy_event_recorded"] = bool(_copy_event)
                if _orchestration is not None:
                    _orchestration.record_fastsafe(
                        "unet", "end", event_recorded=bool(_copy_event),
                        execution_identity=_metrics.get("loader_execution_identity"),
                    )
                _worker_b_result["wall_ms"] = round(
                    (_time.monotonic_ns() - _wb0) / 1_000_000, 4)
                if _transfer_started:
                    _gpu_coord.unet_transfer_end(
                        _gate, _transfer_started_ns,
                        success=True,
                        reason=("staged_transport" if _staged_active
                                else "direct_gpu_fastsafetensors"),
                    )
                if _wb_cpu0 is not None:
                    try:
                        _metrics["worker_b_thread_cpu_ms"] = round(
                            (_time.thread_time() - _wb_cpu0) * 1000, 4)
                    except Exception:
                        _metrics["worker_b_thread_cpu_ms"] = None
                else:
                    _metrics["worker_b_thread_cpu_ms"] = None
                try:
                    _metrics["worker_b_effective_cores"] = (
                        _trace_effective_cores_from(
                            _metrics.get("worker_b_thread_cpu_ms"),
                            _worker_b_result.get("wall_ms")))
                except Exception:
                    _metrics["worker_b_effective_cores"] = None
            except Exception as _exc:
                if _orchestration is not None:
                    _orchestration.record_fastsafe(
                        "unet", "end", event_recorded=False,
                        execution_identity=_metrics.get("loader_execution_identity"),
                    )
                if _staged_active and _worker_b_result.get("transport") != "staged":
                    _metrics["unet_staged_fallback_reason"] = (
                        f"{type(_exc).__name__}:{str(_exc)[:160]}")
                    _metrics["fallback_count"] = 1
                    _fallback_owner = _StagedTransportOwner(
                        _staged_plan_value,
                        _staged_prepared_value,
                        _staged_committed_value,
                        _staged_inner_owner,
                    )
                    _fallback_owner.close()
                    try:
                        _t, _ld, _f = _fs_fastsafe_load(
                            _path, _target, _metrics)
                        _worker_b_result["tensors"] = _t
                        _worker_b_result["loader"] = _ld
                        _worker_b_result["fb"] = _f
                        _worker_b_result["transport"] = "fastsafe_fallback"
                        _worker_b_result["wall_ms"] = round(
                            (_time.monotonic_ns() - _wb0) / 1_000_000, 4)
                    except Exception as _fallback_exc:
                        _worker_b_result["error"] = (
                            f"{type(_fallback_exc).__name__}:"
                            f"{str(_fallback_exc)[:160]}")
                else:
                    _worker_b_result["error"] = (
                        f"{type(_exc).__name__}:{str(_exc)[:160]}")
                if _transfer_started:
                    try:
                        _gpu_coord.unet_transfer_end(
                            _worker_b_result.get("gpu_gate"),
                            _transfer_started_ns,
                            success="error" not in _worker_b_result,
                            reason=("staged_transport" if _staged_active
                                    else "direct_gpu_fastsafetensors"),
                        )
                    except Exception:
                        pass
            finally:
                try:
                    _wb_end = _time.monotonic_ns()
                    _worker_b_result["start_mono_ns"] = _wb0
                    _worker_b_result["end_mono_ns"] = _wb_end
                    _trace_register_forensic_interval(
                        "fastsafe_worker_b",
                        start_mono_ns=_wb0,
                        end_mono_ns=_wb_end,
                        cpu_ms=_metrics.get("worker_b_thread_cpu_ms"),
                        metadata={
                            "request_id": _fs_req_id,
                            "cpu_affinity_count": _cpu_affinity_count,
                            "effective_cores": _metrics.get(
                                "worker_b_effective_cores"),
                        },
                    )
                except Exception:
                    pass

        import threading as _th
        _t_wc = _time.monotonic_ns()
        _t_ta_create = None
        _t_tb_create = None
        _ta = _th.Thread(target=_worker_a, daemon=True)
        _t_ta_create = _time.monotonic_ns()
        _tb = _th.Thread(target=_worker_b, daemon=True)
        _t_tb_create = _time.monotonic_ns()
        _metrics["worker_creation_wall_ms"] = round(
            (_time.monotonic_ns() - _t_wc) / 1_000_000, 4)
        _acct_add("worker_creation", _t_wc)
        _t_ws = _time.monotonic_ns()
        _ta.start()
        _tb.start()
        _metrics["worker_submit_wall_ms"] = round(
            (_time.monotonic_ns() - _t_ws) / 1_000_000, 4)
        _acct_add("worker_submit", _t_ws)
        _t_join = _time.monotonic_ns()
        _ta.join()
        _tb.join()
        _metrics["join_delay_ms"] = round(
            (_time.monotonic_ns() - _t_join) / 1_000_000, 4)
        _acct_add("join_delay", _t_join)
        _metrics["worker_a_wall_ms"] = _worker_a_result.get("wall_ms")
        _metrics["worker_b_wall_ms"] = _worker_b_result.get("wall_ms")
        # ── Worker stamps: start delays + AB overlap ──
        _ta_first = _worker_a_result.get("start_mono_ns")
        _tb_first = _worker_b_result.get("start_mono_ns")
        _metrics["worker_a_start_delay_ms"] = (
            round(max(0, _ta_first - _t_ta_create) / 1_000_000, 4)
            if _ta_first is not None and _t_ta_create is not None else None)
        _metrics["worker_b_start_delay_ms"] = (
            round(max(0, _tb_first - _t_tb_create) / 1_000_000, 4)
            if _tb_first is not None and _t_tb_create is not None else None)
        _metrics["meta_worker_start_delay_ms"] = _metrics["worker_a_start_delay_ms"]
        _wa_iv = (_worker_a_result.get("start_mono_ns"),
                  _worker_a_result.get("end_mono_ns"))
        _wb_iv = (_worker_b_result.get("start_mono_ns"),
                  _worker_b_result.get("end_mono_ns"))
        if all(isinstance(_v, int) for _v in _wa_iv + _wb_iv):
            _metrics["worker_ab_overlap_ms"] = round(
                _trace_forensic_overlap_ms(
                    _wa_iv[0], _wa_iv[1], _wb_iv[0], _wb_iv[1]), 4)
        else:
            _metrics["worker_ab_overlap_ms"] = None
        # ── Task B: input_types_warm overlap (request-id scoped) ──
        try:
            _warm = _trace_forensic_intervals().get("input_types_warm")
        except Exception:
            _warm = None
        _warm_req = None
        _warm_start = None
        _warm_end = None
        if isinstance(_warm, dict):
            _warm_meta = _warm.get("metadata")
            _warm_req = (_warm_meta or {}).get("request_id")
            _warm_start = _warm.get("start_mono_ns")
            _warm_end = _warm.get("end_mono_ns")
        if (isinstance(_warm, dict)
                and _warm_req is not None and _fs_req_id is not None
                and str(_warm_req) == str(_fs_req_id)):
            _metrics["input_types_warm_overlap_scope"] = "complete"
            if (isinstance(_warm_start, int) and isinstance(_warm_end, int)
                    and all(isinstance(_v, int) for _v in _wa_iv)):
                _metrics["input_types_warm_overlap_meta_ms"] = round(
                    _trace_forensic_overlap_ms(
                        _wa_iv[0], _wa_iv[1], _warm_start, _warm_end), 4)
            else:
                _metrics["input_types_warm_overlap_meta_ms"] = None
            if (isinstance(_warm_start, int) and isinstance(_warm_end, int)
                    and all(isinstance(_v, int) for _v in _wb_iv)):
                _metrics["input_types_warm_overlap_fastsafe_ms"] = round(
                    _trace_forensic_overlap_ms(
                        _wb_iv[0], _wb_iv[1], _warm_start, _warm_end), 4)
            else:
                _metrics["input_types_warm_overlap_fastsafe_ms"] = None
        elif isinstance(_warm, dict):
            _metrics["input_types_warm_overlap_meta_ms"] = None
            _metrics["input_types_warm_overlap_fastsafe_ms"] = None
            _metrics["input_types_warm_overlap_scope"] = "partial"
        else:
            _metrics["input_types_warm_overlap_meta_ms"] = None
            _metrics["input_types_warm_overlap_fastsafe_ms"] = None
            _metrics["input_types_warm_overlap_scope"] = "unavailable"
        _t_pjp = _time.monotonic_ns()
        if "error" in _worker_a_result:
            _stage = "stage:meta_construct:" + str(_worker_a_result["error"])
            return _fs_fail(_metrics, _trace, _stage, _t0_total,
                            loader=_worker_b_result.get("loader"),
                            fb=_worker_b_result.get("fb"))
        if "error" in _worker_b_result:
            _stage = "stage:fastsafe_load:" + str(_worker_b_result["error"])
            if "structural_source_fence_failure" in str(_worker_b_result["error"]):
                _fs_fail(_metrics, _trace, _stage, _t0_total)
                from .fast_cold_orchestration import SourceFenceFailure

                raise SourceFenceFailure(_stage)
            return _fs_fail(_metrics, _trace, _stage, _t0_total)
        _model = _worker_a_result["model"]
        _tensors = _worker_b_result["tensors"]
        _loader = _worker_b_result["loader"]
        _fb = _worker_b_result["fb"]
        _staged_used = _worker_b_result.get("transport") == "staged"
        _copy_event = _worker_b_result.get("copy_event")
        if _fs_scoped_cuda_readiness_enabled():
            _copy_waited = _gpu_coord.wait_copy_event(
                "unet",
                _copy_event,
                _trace,
                stream=_torch_tp.cuda.current_stream(device=_target),
            )
            if not _copy_waited:
                return _fs_fail(
                    _metrics,
                    _trace,
                    "stage:scoped_copy_event_wait_failed",
                    _t0_total,
                    loader=_loader,
                    fb=_fb,
                )
            _metrics["copy_event_waited"] = True
            _metrics["copy_event_sync_method"] = "stream.wait_event"
        _mem1 = _fs_memory_snapshot()
        _metrics.update(_fs_mem_report("after_load", _mem0, _mem1))
        _metrics["post_join_prep_wall_ms"] = round(
            (_time.monotonic_ns() - _t_pjp) / 1_000_000, 4)
        _acct_add("post_join_prep", _t_pjp)
        # ── Post-load gates: count / bytes / keys / shapes / dtypes ──
        _t_plg = _time.monotonic_ns()
        _metrics["tensor_count"] = len(_tensors)
        _expected_keys = [k for k in _header if k != "__metadata__"]
        _metrics["key_set_ok"] = key_set_ok(_tensors.keys(), _header)
        _metrics["spot_check"] = spot_check_tensors(_tensors, _header)
        _total_bytes = 0
        for _k in _expected_keys:
            try:
                _info = _header[_k]
                _offs = _info.get("data_offsets") or [0, 0]
                _total_bytes += int(_offs[1]) - int(_offs[0])
            except Exception:
                _total_bytes = -1
                break
        _metrics["total_bytes"] = _total_bytes
        _tensor_bytes = int(sum(
            _t.numel() * _t.element_size() for _t in _tensors.values()))
        if (_metrics["tensor_count"] != len(_expected_keys)
                or not _metrics["key_set_ok"]
                or not (_metrics["spot_check"] or {}).get("ok")
                or _tensor_bytes != _total_bytes
                or (not _staged_active
                    and _total_bytes != _FS_EXPECTED_TOTAL_BYTES)):
            return _fs_fail(_metrics, _trace, "stage:tensor_validity", _t0_total,
                            loader=_loader, fb=_fb)
        _metrics["post_load_gates_wall_ms"] = round(
            (_time.monotonic_ns() - _t_plg) / 1_000_000, 4)
        _acct_add("post_load_gates", _t_plg)
        _fwall = float(_metrics.get("fastsafe_file_gpu_wall_ms") or 0.0)
        _metrics["fastsafe_gbps"] = round(
            _total_bytes / (_fwall * 1e6) if _fwall > 0 else 0.0, 4)
        # Transform INDEPENDENT (identity) gate.
        _t_tg = _time.monotonic_ns()
        try:
            _transformed = _config.process_unet_state_dict(dict(_meta_sd))
        except Exception:
            _transformed = None
        _metrics["transform_independent"] = bool(
            isinstance(_transformed, dict)
            and set(_transformed.keys()) == set(_meta_sd.keys()))
        if not _metrics["transform_independent"]:
            return _fs_fail(_metrics, _trace, "stage:transform_not_independent",
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _metrics["transform_gate_wall_ms"] = round(
            (_time.monotonic_ns() - _t_tg) / 1_000_000, 4)
        _acct_add("transform_gate", _t_tg)
        # ── Bind: assign=True zero-copy into the meta model ──
        _unet = getattr(_model, "diffusion_model", None) or _model
        _params = dict(_unet.named_parameters())
        _buffers = dict(_unet.named_buffers())
        _metrics["param_count"] = len(_params)
        _sd_keys = set(_tensors.keys())
        _dest_key_set = set(_params.keys()) | set(_buffers.keys())
        _unmapped = sorted(_k for _k in _sd_keys if _k not in _dest_key_set)
        _metrics["sd_unmapped_keys"] = _unmapped[:20]
        if _unmapped:
            return _fs_fail(_metrics, _trace, "stage:key_param_mismatch",
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _metrics["model_only_param_count"] = sum(
            1 for _k in _params if _k not in _sd_keys)
        _metrics["model_only_buffer_count"] = sum(
            1 for _k in _buffers if _k not in _sd_keys)
        _t_bind = _time.monotonic_ns()
        try:
            with _torch_tp.no_grad():
                _unet.load_state_dict(_tensors, assign=True)
        except Exception as _exc:
            return _fs_fail(_metrics, _trace,
                            "stage:assign:" + type(_exc).__name__,
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _metrics["bind_wall_ms"] = round(
            (_time.monotonic_ns() - _t_bind) / 1_000_000, 4)
        if _staged_used:
            _metrics["unet_staged_bind_ms"] = _metrics["bind_wall_ms"]
        _acct_add("bind", _t_bind)
        # Zero-copy proof: data_ptr equality for a bounded sample.  torch's
        # assign=True REPLACES the Parameter/buffer entries, so the sample
        # must re-walk named_parameters/named_buffers AFTER the bind.
        _t_zc = _time.monotonic_ns()
        try:
            _ptr_ok = True
            _ptr_sample = []
            _params_after = dict(_unet.named_parameters())
            _buffers_after = dict(_unet.named_buffers())
            _sample_keys = sorted(_sd_keys)[::max(
                1, len(_sd_keys) // _FS_DATA_PTR_SAMPLE_KEYS)][:_FS_DATA_PTR_SAMPLE_KEYS]
            for _k in _sample_keys:
                _dst = _params_after.get(_k)
                if _dst is None:
                    _dst = _buffers_after.get(_k)
                _src_ptr = int(_tensors[_k].data_ptr())
                _dst_ptr = int(_dst.data_ptr()) if _dst is not None else -1
                if _src_ptr != _dst_ptr:
                    _ptr_ok = False
                _ptr_sample.append({
                    "key": _k, "src_ptr": _src_ptr, "dst_ptr": _dst_ptr,
                    "match": _src_ptr == _dst_ptr,
                })
            _metrics["data_ptr_sample_match"] = bool(_ptr_ok)
            _metrics["data_ptr_sample_keys"] = _ptr_sample
        except Exception:
            _metrics["data_ptr_sample_match"] = None
        _metrics["zero_copy_proof_wall_ms"] = round(
            (_time.monotonic_ns() - _t_zc) / 1_000_000, 4)
        _acct_add("zero_copy_proof", _t_zc)
        _t_m2 = _time.monotonic_ns()
        _mem2 = _fs_memory_snapshot()
        _metrics.update(_fs_mem_report("after_bind", _mem1, _mem2))
        _metrics["mem2_wall_ms"] = round(
            (_time.monotonic_ns() - _t_m2) / 1_000_000, 4)
        _acct_add("mem2", _t_m2)
        # ── Residual meta sweep + bounded final .to + single sync ──
        _t_sw = _time.monotonic_ns()
        try:
            _pre = _fs_sweep_meta(_model, _target)
            _metrics["residual_meta_before_sweep"] = _pre
        except Exception as _exc:
            return _fs_fail(_metrics, _trace,
                            "stage:sweep:" + type(_exc).__name__,
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _metrics["sweep_wall_ms"] = round(
            (_time.monotonic_ns() - _t_sw) / 1_000_000, 4)
        _acct_add("sweep", _t_sw)
        _t_to = _time.monotonic_ns()
        try:
            _model.to(_target)
        except Exception:
            return _fs_fail(_metrics, _trace, "stage:final_model_to",
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _metrics["final_to_wall_ms"] = round(
            (_time.monotonic_ns() - _t_to) / 1_000_000, 4)
        _acct_add("final_to", _t_to)
        if _metrics["final_to_wall_ms"] > _FS_FINAL_TO_DUPLICATE_THRESHOLD_MS:
            return _fs_fail(_metrics, _trace, "stage:final_to_duplicates_transfer",
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        if _fs_cuda_available():
            _t_sync = _time.monotonic_ns()
            if _fs_scoped_cuda_readiness_enabled():
                _metrics["final_sync_wall_ms"] = 0.0
                _metrics["final_sync_method"] = "stream.wait_event"
            else:
                try:
                    _gpu_coord.record_device_wide_sync("unet", _trace)
                    _torch_tp.cuda.synchronize()
                except Exception:
                    pass
                _metrics["final_sync_wall_ms"] = round(
                    (_time.monotonic_ns() - _t_sync) / 1_000_000, 4)
                _metrics["final_sync_method"] = "torch.cuda.synchronize"
            _acct_add("final_sync", _t_sync)
        else:
            _metrics["final_sync_wall_ms"] = None
        # Final validation (GPU-ready contract).
        _t_vl = _time.monotonic_ns()
        try:
            _val = _fs_validate_final(_model, _target)
        except Exception as _exc:
            return _fs_fail(_metrics, _trace,
                            "stage:final_validation:" + type(_exc).__name__,
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _metrics["validate_wall_ms"] = round(
            (_time.monotonic_ns() - _t_vl) / 1_000_000, 4)
        _acct_add("validate", _t_vl)
        _metrics["final_validation"] = _val
        _metrics["residual_meta_after"] = int(_val.get("residual_meta_count") or 0)
        if (not _val.get("all_params_on_target")
                or int(_val.get("residual_meta_count") or 0) != 0):
            return _fs_fail(_metrics, _trace, "stage:final_validation_failed",
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        # ModelPatcher (plain non-dynamic, mirroring sd.py).
        _t_pa = _time.monotonic_ns()
        _mp_cls = _c6_comfy_fn("comfy.model_patcher", "ModelPatcher")
        if _mp_cls is None:
            return _fs_fail(_metrics, _trace, "stage:patcher_unavailable",
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _offload = _fs_get_offload()
        _patcher = _mp_cls(_model, load_device=_target, offload_device=_offload)
        _metrics["patcher_wall_ms"] = round(
            (_time.monotonic_ns() - _t_pa) / 1_000_000, 4)
        _acct_add("patcher", _t_pa)
        # Owner retention (Gate 1): transport storage lives as long as patcher.
        _t_oa = _time.monotonic_ns()
        _metrics["owner_mode"] = (
            "staged_retained" if _staged_used else "loader_retained"
        )
        _metrics["owner_attr"] = (
            _STAGED_OWNER_ATTR if _staged_used else _FS_OWNER_ATTR
        )
        _owner = (
            _fb if _staged_used else _FastsafeOwner(_loader, _fb)
        )
        _owner_attr = _STAGED_OWNER_ATTR if _staged_used else _FS_OWNER_ATTR
        try:
            setattr(_patcher, _owner_attr, _owner)
        except Exception:
            return _fs_fail(_metrics, _trace, "stage:owner_attach_failed",
                            t0_total=_t0_total, loader=_loader, fb=_fb)
        _metrics["owner_attach_wall_ms"] = round(
            (_time.monotonic_ns() - _t_oa) / 1_000_000, 4)
        _acct_add("owner_attach", _t_oa)
        _t_tele0 = _time.monotonic_ns()
        _mem3 = _fs_memory_snapshot()
        _metrics.update(_fs_mem_report("final", _mem0, _mem3))
        _metrics["total_pipeline_wall_ms"] = round(
            (_time.monotonic_ns() - _t0_total) / 1_000_000, 4)
        _metrics["status"] = "ok"
        _metrics["reason"] = ""
        _gpu_coord.record_unet_ready(
            _fs_req_id or "", _trace, reason="unet_ready"
        )
        if _orchestration is not None:
            from .fast_cold_orchestration import record_unet_ready

            record_unet_ready(_fs_req_id or "", _trace)
        _fs_emit("ok", "", _metrics, _trace)
        _t_tele_end = _time.monotonic_ns()
        _metrics["telemetry_wall_ms"] = round(
            (_t_tele_end - _t_tele0) / 1_000_000, 4)
        _acct.append(("telemetry", _t_tele0, _t_tele_end))
        _t_rg = _time.monotonic_ns()
        _metrics["return_gap_wall_ms"] = round(
            (_t_rg - _t_tele_end) / 1_000_000, 4)
        _acct.append(("return_gap", _t_tele_end, _t_rg))
        # ── Task 4 pipeline reconciliation: serial accounting intervals only.
        #    The parallel worker executions are nested inside join_delay and
        #    are NEVER part of accounting_intervals. ──
        try:
            _metrics.update(_fs_pipeline_reconcile(
                _metrics.get("total_pipeline_wall_ms"), _acct))
        except Exception:
            _metrics.setdefault("reconciliation_status", "GAP")
            _metrics.setdefault("accounting_children_ms", None)
            _metrics.setdefault("residual_ms", None)
            _metrics.setdefault("accounting_disjoint", None)
            _metrics.setdefault("accounting_overlap_detail", None)
        # ── Task 1 meta reconciliation (execution nested in lifecycle) ──
        try:
            _metrics.update(_fs_meta_reconcile(
                start_delay_ms=_metrics.get("meta_worker_start_delay_ms"),
                execution_wall_ms=_metrics.get("meta_worker_execution_wall_ms"),
                import_ms=_metrics.get("meta_import_wall_ms"),
                context_entry_ms=_metrics.get("meta_context_entry_wall_ms"),
                get_model_ms=_metrics.get("meta_get_model_wall_ms"),
                param_validate_ms=_metrics.get("meta_param_validate_wall_ms"),
                sampling_detect_ms=_metrics.get("meta_sampling_detect_wall_ms"),
                sampling_fix_ms=_metrics.get("sampling_fix_wall_ms"),
                return_prep_ms=_metrics.get("meta_return_prep_wall_ms"),
                lifecycle_total_ms=_metrics.get("meta_lifecycle_total_ms"),
            ))
        except Exception:
            _metrics.setdefault("meta_reconcile_status", "GAP")
        try:
            print(
                f"[v2.fastsafe.reconcile] pipeline_total_ms="
                f"{_metrics.get('pipeline_total_ms')} "
                f"accounting_children_ms={_metrics.get('accounting_children_ms')} "
                f"residual_ms={_metrics.get('residual_ms')} "
                f"status={_metrics.get('reconciliation_status')} "
                f"disjoint={_metrics.get('accounting_disjoint')} "
                f"meta_execution_wall_ms={_metrics.get('meta_worker_execution_wall_ms')} "
                f"meta_execution_children_ms={_metrics.get('meta_execution_children_ms')} "
                f"meta_execution_residual_ms={_metrics.get('meta_execution_residual_ms')} "
                f"meta_lifecycle_total_ms={_metrics.get('meta_lifecycle_total_ms')} "
                f"meta_lifecycle_residual_ms={_metrics.get('meta_lifecycle_residual_ms')} "
                f"meta_status={_metrics.get('meta_reconcile_status')} "
                f"forensics={_metrics.get('forensics_enabled')}",
                flush=True,
            )
        except Exception:
            pass
        # Machine-readable reconcile emit (success path only; separate event so
        # the one-event unet_fastsafetensors_pipeline contract stays intact).
        try:
            if _trace is not None:
                _trace.emit(
                    "unet_fastsafetensors_reconcile",
                    phase="restore",
                    metadata=_c6_json_safe({
                        "pipeline_total_ms": _metrics.get("pipeline_total_ms"),
                        "accounting_children_ms": _metrics.get(
                            "accounting_children_ms"),
                        "residual_ms": _metrics.get("residual_ms"),
                        "reconciliation_status": _metrics.get(
                            "reconciliation_status"),
                        "accounting_disjoint": _metrics.get(
                            "accounting_disjoint"),
                        "accounting_overlap_detail": _metrics.get(
                            "accounting_overlap_detail"),
                        "forensics_enabled": _metrics.get("forensics_enabled"),
                        "meta_worker_start_delay_ms": _metrics.get(
                            "meta_worker_start_delay_ms"),
                        "meta_worker_execution_wall_ms": _metrics.get(
                            "meta_worker_execution_wall_ms"),
                        "meta_lifecycle_total_ms": _metrics.get(
                            "meta_lifecycle_total_ms"),
                        "meta_execution_children_ms": _metrics.get(
                            "meta_execution_children_ms"),
                        "meta_execution_residual_ms": _metrics.get(
                            "meta_execution_residual_ms"),
                        "meta_lifecycle_children_ms": _metrics.get(
                            "meta_lifecycle_children_ms"),
                        "meta_lifecycle_residual_ms": _metrics.get(
                            "meta_lifecycle_residual_ms"),
                        "meta_reconcile_status": _metrics.get(
                            "meta_reconcile_status"),
                        "meta_worker_thread_cpu_ms": _metrics.get(
                            "meta_worker_thread_cpu_ms"),
                        "meta_worker_effective_cores": _metrics.get(
                            "meta_worker_effective_cores"),
                        "meta_non_thread_cpu_wall_ms": _metrics.get(
                            "meta_non_thread_cpu_wall_ms"),
                        "worker_ab_overlap_ms": _metrics.get(
                            "worker_ab_overlap_ms"),
                        "input_types_warm_overlap_meta_ms": _metrics.get(
                            "input_types_warm_overlap_meta_ms"),
                        "input_types_warm_overlap_fastsafe_ms": _metrics.get(
                            "input_types_warm_overlap_fastsafe_ms"),
                        "input_types_warm_overlap_scope": _metrics.get(
                            "input_types_warm_overlap_scope"),
                    }),
                )
        except Exception:
            pass
        return (_patcher,)
    except Exception as _exc:
        if "structural_source_fence_failure" in str(_exc) or _exc.__class__.__name__ == "SourceFenceFailure":
            raise
        return _fs_fail(_metrics, _trace, f"stage:{type(_exc).__name__}",
                        _t0_total, loader=_loader, fb=_fb)
    finally:
        _gate = _worker_b_result.get("gpu_gate")
        if _gate is not None:
            try:
                _gpu_coord.end_unet_gpu_phase(
                    _gate,
                    success="error" not in _worker_b_result,
                )
            except Exception:
                pass


class _FastsafeOwner:
    """Explicit owner of the fastsafetensors loader + device buffer.  Held by
    the ModelPatcher for the model's full lifetime; released (and the gbuf
    freed) when the patcher — and thus the UNET — is genuinely released."""

    __slots__ = ("loader", "fb", "kind")

    def __init__(self, loader, fb):
        self.loader = loader
        self.fb = fb
        self.kind = "fastsafetensors.FilesBufferOnDevice"
