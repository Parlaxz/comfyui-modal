"""V2 "meta-direct" UNET loader (Batch C6 salvage, generation 2).

Eliminates the three measured host costs of the V1 pinned-ring loader by:

  (a) constructing the ZImage model under ``torch.device("meta")`` and
      materializing parameters DIRECTLY on CUDA via ``Module.to_empty``
      (meta get_model ~20 ms + to_empty ~818 ms vs V1's ~2.39 s cold
      real-device get_model);
  (b) eliminating CPU staging entirely with ``os.preadv`` reading file
      bytes DIRECTLY into preallocated pinned buffers (byte-exact vs
      ``safetensors.get_tensor`` per the C6 mechanism probe), then async
      non-blocking DMA pinned -> GPU.

Gate: ``COMFYMODAL_V2_UNET_META_DIRECT`` (default OFF; on values
"1"/"true"/"yes"/"on"; off values "", "0", "false", "no", "off", "none";
anything else -> invalid, fail-closed, one-time print).  V1 ring
(``COMFYMODAL_V2_UNET_PINNED_RING``) and the probe-mode machinery are
untouched.  The ``_load_unet`` branch lives in ``model_preload.py`` and
lazy-imports this module so the off-path import surface is zero.

Measured mechanism-probe facts this relies on (trusted):
  * meta construction works on the real ZImage; model.model_sampling is
    poisoned (meta tensors) but rebuilding it with the SAME helper
    ``comfy.model_base`` imports fixes it (verified zero meta tensors).
  * ``to_empty(device=cuda)`` = ~818 ms, all params cuda:0 bf16.
  * os.preadv into a preallocated torch pinned buffer is byte-exact vs
    safetensors and hits 6.6-12 GB/s per 64/128/256 MiB wave.
  * cudaHostRegister is NOT supported on this environment (rc=304); GDS
    not supported (nvidia-fs absent) -> preadv is the chosen I/O path.
"""

from __future__ import annotations

import os as _os
import struct as _struct
import time as _time
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
from .unet_salvage_probe import (
    build_wave_ranges,
    collect_meta_tensors,
    slice_tensor_from_buffer,
)

# ── Constants (bounded budgets) ───────────────────────────────────────────
# 12.31 GB / 128 MiB ~= 96 waves; a single tensor > 256 MiB -> fallback.
_MD_WAVE_TARGET_BYTES: int = 128 * 1024 * 1024
_MD_MAX_WAVE_BYTES: int = 256 * 1024 * 1024
_MD_DEPTH: int = 2
_MD_PINNED_MAX_SLOT_BYTES: int = 256 * 1024 * 1024
_MD_FINAL_TO_DUPLICATE_THRESHOLD_MS: float = 500.0
# Preadv is issued in bounded sub-chunks (the C6 mechanism probe verified
# full reads up to 256 MiB on the Modal Volume; 32 MiB chunks keep each
# syscall well inside the proven regime and bound retry granularity).
_MD_PREADV_CHUNK_BYTES: int = 32 * 1024 * 1024
# 1 MiB preadv capability self-test before the wave loop (fail fast).
_MD_PREADV_SELFTEST_BYTES: int = 1 * 1024 * 1024


def _md_data_start_offset(path) -> int | None:
    """safetensors data buffer start == 8 (LE uint64 header length) + N."""
    try:
        with open(path, "rb") as _f:
            _head_len = _struct.unpack("<Q", _f.read(8))[0]
        return 8 + int(_head_len)
    except Exception:
        return None


def _md_preadv_all(preadv, fd, mv, offset, nbytes) -> int:
    """os.preadv with a SHORT-READ RETRY LOOP: preadv may return partial
    reads; loop until all bytes are read or EOF/error.  Returns total bytes
    read (caller compares against nbytes)."""
    _total = 0
    while _total < int(nbytes):
        _n = preadv(fd, [mv[_total:]], int(offset) + _total)
        if _n is None or _n <= 0:
            break
        _total += int(_n)
    return _total


def _md_eligible(record, model_key, kwargs, lane) -> tuple[bool, str]:
    """Meta-direct eligibility gate (conditions 2-12; the caller has already
    checked the flag).  Reuses V1 helpers for identical conditions.  Config
    "parity" is satisfied by construction: ``_ring_derive_config`` runs the
    same header-only derivation path the authoritative loader uses."""
    try:
        import torch as _torch_me
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
        try:
            if not _torch_me.cuda.is_available():
                return (False, "cuda_unavailable")
        except Exception:
            return (False, "cuda_unavailable")
        try:
            _mgmt = _c6_comfy_fn("comfy.model_management", "get_torch_device")
            _target = _mgmt() if _mgmt is not None else None
        except Exception:
            _target = None
        if _target is None or str(getattr(_target, "type", "") or "").lower() != "cuda":
            return (False, "cuda_unavailable")
        if not callable(getattr(_os, "preadv", None)):
            return (False, "preadv_unavailable")
        try:
            _p = _torch_me.empty(1 * 1024 * 1024, dtype=_torch_me.uint8, pin_memory=True)
            del _p
        except Exception:
            return (False, "pinned_unavailable")
        return (True, "")
    except Exception:
        return (False, "eligibility_error")


def _md_emit(status, reason, metrics, trace=None) -> None:
    """Lean telemetry: one unet_meta_direct_pipeline event (JSON-safe) plus
    one console line.  Never raises."""
    try:
        _m = _c6_json_safe(dict(metrics))
        _m["status"] = status
        _m["reason"] = reason or ""
        if trace is not None:
            trace.emit("unet_meta_direct_pipeline", phase="restore", metadata=_m)
    except Exception as _exc:
        print(f"[v2.meta_direct] emit_error={type(_exc).__name__}", flush=True)
    try:
        print(
            f"[v2.meta_direct] status={status} reason={reason or ''} "
            f"waves={metrics.get('wave_count')} "
            f"total_wall_ms={metrics.get('total_pipeline_wall_ms')} "
            f"hidden_overlap_ms={metrics.get('hidden_overlap_ms')}",
            flush=True,
        )
    except Exception:
        pass


def _md_fail(metrics, trace, reason, t0_total) -> None:
    """Fallback helper: emit status=fallback with the named stage reason and
    release the CUDA cache.  The caller then runs ``_invoke_original`` fresh."""
    try:
        metrics.update({
            "status": "fallback", "reason": reason, "fallback_count": 1,
            "total_pipeline_wall_ms": round((_time.monotonic_ns() - t0_total) / 1_000_000, 4),
        })
    except Exception:
        pass
    try:
        import torch as _torch_mf
        _torch_mf.cuda.empty_cache()
    except Exception:
        pass
    _md_emit(metrics.get("status", "fallback"), metrics.get("reason", reason), metrics, trace)
    return None


def _md_run_waves(params, buffers, path, waves, sd_dtype,
                  data_start_offset) -> tuple[dict, list] | tuple[None, str] | tuple[None, str, dict]:
    """Meta-direct wave H2D runner: two pinned uint8 slots, one event pair
    per wave, os.preadv DIRECTLY into the pinned slot in bounded sub-chunks
    (single pass, no mmap->pinned memcpy), async copy_ into the ALREADY-CUDA
    params from ``to_empty`` (no param.data rebinding).

    Returns ``(metrics, wave_events)`` on success; on failure
    ``(None, "<stage>:<detail>", partial_metrics)`` where *partial_metrics*
    carries the accumulated progress so the caller can emit real
    diagnostics.  Never performs a global synchronize (the single final sync
    is the caller's); only per-slot reuse waits on pending events."""
    import torch as _torch_rw
    _preadv = getattr(_os, "preadv", None)
    if not callable(_preadv):
        return (None, "preadv_unavailable")
    _pin_slots: list[Any] = [None, None]
    _pin_bytes: list[int] = [0, 0]
    _ev_pending: list[Any] = [None, None]
    _fd = None
    _metrics: dict[str, Any] = {
        "preadv_io_wall_ms": 0.0, "preadv_bytes": 0, "fadvise_wall_ms": None,
        "fadvise_error": None, "preadv_selftest_wall_ms": None,
        "h2d_host_issue_wall_ms": 0.0, "reuse_wait_total_ms": 0.0,
        "max_reuse_wait_ms": 0.0, "pinned_bytes": 0,
    }
    _wave_events: list[tuple[Any, Any, dict[str, Any]]] = []
    try:
        try:
            _fd = _os.open(path, _os.O_RDONLY)
        except Exception as _exc:
            return (None, "open:" + type(_exc).__name__, _metrics)
        # 1 MiB preadv capability self-test (fail fast): prove the volume
        # services preadv before the wave loop.  The probe size is bounded by
        # the file's remaining data length so small test files still pass.
        try:
            _avail = 0
            try:
                _avail = max(0, int(_os.path.getsize(path)) - int(data_start_offset))
            except Exception:
                _avail = 0
            _probe_bytes = min(_MD_PREADV_SELFTEST_BYTES, _avail) if _avail > 0 else 0
            if _probe_bytes > 0:
                _st_probe = _torch_rw.empty(_probe_bytes, dtype=_torch_rw.uint8,
                                            pin_memory=True)
                _st_t0 = _time.monotonic_ns()
                _st_got = _md_preadv_all(
                    _preadv, _fd, memoryview(_st_probe.numpy()),
                    int(data_start_offset), _probe_bytes)
                _metrics["preadv_selftest_wall_ms"] = round(
                    (_time.monotonic_ns() - _st_t0) / 1_000_000, 4)
                del _st_probe
                if _st_got != _probe_bytes:
                    return (None, "preadv_volume_unsupported:%d/%d" % (
                        int(_st_got or 0), _probe_bytes), _metrics)
        except Exception as _exc:
            return (None, "preadv_selftest:" + type(_exc).__name__, _metrics)
        _fadv = getattr(_os, "posix_fadvise", None)
        if callable(_fadv):
            try:
                _t0 = _time.monotonic_ns()
                _fadv(_fd, 0, 0, getattr(_os, "POSIX_FADV_WILLNEED", 3))
                _metrics["fadvise_wall_ms"] = round((_time.monotonic_ns() - _t0) / 1_000_000, 4)
            except Exception as _exc:
                _metrics["fadvise_error"] = type(_exc).__name__ + ":" + str(_exc)[:200]
        for _w_idx, _wave in enumerate(waves):
            _s = _w_idx % _MD_DEPTH
            _wm: dict[str, Any] = {
                "keys": list(_wave.get("keys", [])),
                "bytes": int(_wave.get("tensor_bytes", 0)),
                "preadv_ms": 0.0, "issue_ms": 0.0, "device_ms": None,
                "reuse_wait_ms": None,
            }
            if _ev_pending[_s] is not None:
                _t0 = _time.monotonic_ns()
                try:
                    _ev_pending[_s].synchronize()
                except Exception:
                    pass
                _t1 = _time.monotonic_ns()
                _wait_ms = round((_t1 - _t0) / 1_000_000, 4)
                _wm["reuse_wait_ms"] = _wait_ms
                _metrics["reuse_wait_total_ms"] += _wait_ms
                _metrics["max_reuse_wait_ms"] = max(_metrics["max_reuse_wait_ms"], _wait_ms)
                _ev_pending[_s] = None
            _wave_bytes = int(_wave.get("tensor_bytes", 0))
            if _wave_bytes <= 0:
                return (None, "empty_wave", _metrics)
            if _wave_bytes > _MD_PINNED_MAX_SLOT_BYTES:
                return (None, "wave_exceeds_slot_cap", _metrics)
            # Slot capacity (grow-to-largest, realloc replaces).
            if _pin_slots[_s] is None or _pin_bytes[_s] < _wave_bytes:
                _old = _pin_slots[_s]
                try:
                    _pin_slots[_s] = _torch_rw.empty(_wave_bytes, dtype=_torch_rw.uint8,
                                                     pin_memory=True)
                    _pin_bytes[_s] = _wave_bytes
                    _metrics["pinned_bytes"] += _wave_bytes
                except Exception as _exc:
                    return (None, "pinned_alloc:" + type(_exc).__name__, _metrics)
                finally:
                    if _old is not None:
                        try:
                            del _old
                        except Exception:
                            pass
            # os.preadv DIRECTLY into the pinned slot, sub-chunked to at most
            # _MD_PREADV_CHUNK_BYTES per syscall (short-read retry per chunk),
            # accumulating until the wave's tensor_bytes are fully read.
            _mv = memoryview(_pin_slots[_s].numpy())
            _read_t0 = _time.monotonic_ns()
            _got_total = 0
            _wave_abs = int(data_start_offset) + int(_wave.get("rel_byte_start", 0))
            try:
                while _got_total < _wave_bytes:
                    _chunk = min(_MD_PREADV_CHUNK_BYTES, _wave_bytes - _got_total)
                    # Pass a view limited to EXACTLY the chunk size so the
                    # preadv call reads at most _chunk bytes (os.preadv reads
                    # up to the buffer size); internal retry slices
                    # mv[_total:] then map onto the correct slot region.
                    _got = _md_preadv_all(
                        _preadv, _fd, _mv[_got_total:_got_total + _chunk],
                        _wave_abs + _got_total, _chunk)
                    if _got != _chunk:
                        _metrics["fail_wave_idx"] = _w_idx
                        _metrics["fail_wave_offset"] = _wave_abs + _got_total
                        _metrics["fail_requested_bytes"] = _chunk
                        _metrics["fail_got_bytes"] = int(_got or 0)
                        return (None, "preadv_short_read", _metrics)
                    _got_total += _got
                    _metrics["preadv_bytes"] += _got
            except Exception as _exc:
                return (None, "preadv:" + type(_exc).__name__, _metrics)
            _read_t1 = _time.monotonic_ns()
            _wm["preadv_ms"] = round((_read_t1 - _read_t0) / 1_000_000, 4)
            _metrics["preadv_io_wall_ms"] += _wm["preadv_ms"]
            # Wave-start event, then async H2D into the ALREADY-CUDA params.
            _ev_start = _torch_rw.cuda.Event(enable_timing=True)
            _ev_start.record()
            _issue_t0 = _time.monotonic_ns()
            try:
                _wave_start = int(_wave.get("rel_byte_start", 0))
                # copy_ into a leaf nn.Parameter requires no_grad (the params
                # keep requires_grad=True after to_empty, exactly like
                # ComfyUI's load_state_dict which runs under no_grad).
                with _torch_rw.no_grad():
                    for _t in _wave.get("tensors", []):
                        _dst = params.get(_t["key"])
                        if _dst is None and buffers is not None:
                            _dst = buffers.get(_t["key"])
                        if _dst is None:
                            return (None, "dma_dst_missing", _metrics)
                        _view = slice_tensor_from_buffer(
                            _pin_slots[_s], sd_dtype, _t["shape"],
                            int(_t["rel_off"]) - _wave_start, int(_t["nbytes"]))
                        _dst.copy_(_view, non_blocking=True)
            except Exception as _exc:
                return (None, "dma:" + type(_exc).__name__, _metrics)
            _issue_t1 = _time.monotonic_ns()
            _ev_end = _torch_rw.cuda.Event(enable_timing=True)
            _ev_end.record()
            _ev_pending[_s] = _ev_end
            _wave_events.append((_ev_start, _ev_end, _wm))
            _metrics["h2d_host_issue_wall_ms"] += round((_issue_t1 - _issue_t0) / 1_000_000, 4)
        return (_metrics, _wave_events)
    except Exception as _exc:
        return (None, "md_run:" + type(_exc).__name__, _metrics)
    finally:
        if _fd is not None:
            try:
                _os.close(_fd)
            except Exception:
                pass
        for _s in range(_MD_DEPTH):
            try:
                if _pin_slots[_s] is not None:
                    del _pin_slots[_s]
                    _pin_slots[_s] = None
            except Exception:
                pass
        try:
            _torch_rw.cuda.empty_cache()
        except Exception:
            pass


def _md_try_pipeline(bridge, model_key, kwargs, lane) -> tuple[Any, ...] | None:
    """Meta-direct UNET fast path.  Returns ``(patcher,)`` on success (flows
    through the unchanged ``_load_unet`` tail); None on ineligible/fallback
    (the caller then runs ``_invoke_original`` fresh exactly once)."""
    _lane = lane if lane is not None else _ACTIVE_LANE_TRACE.get()
    _trace = getattr(_lane, "_trace", None) if _lane is not None else None
    if _trace is None:
        _trace = _ACTIVE_REQUEST_TRACE.get()
    _t0_total = _time.monotonic_ns()
    _metrics: dict[str, Any] = {
        "flag": "on", "eligibility": "ok", "family": "ZImage", "reason": "",
        "header_config_wall_ms": None, "value_probe_wall_ms": None,
        "meta_get_model_wall_ms": None, "sampling_fix_wall_ms": None,
        "sampling_poisoned_tensors": 0, "to_empty_wall_ms": None,
        "param_count": 0, "tensor_count": 0, "total_bytes": 0, "wave_count": 0,
        "wave_target_bytes": _MD_WAVE_TARGET_BYTES, "max_wave_bytes": _MD_MAX_WAVE_BYTES,
        "actual_max_wave_bytes": 0, "actual_mean_wave_bytes": 0,
        "pinned_bytes": 0, "preadv_io_wall_ms": 0.0, "preadv_gbps": 0.0,
        "preadv_bytes": 0, "fadvise_wall_ms": None,
        "h2d_device_wall_ms": 0.0, "h2d_host_issue_wall_ms": 0.0,
        "reuse_wait_total_ms": 0.0, "max_reuse_wait_ms": 0.0,
        "final_to_wall_ms": 0.0, "final_sync_wall_ms": 0.0,
        "total_pipeline_wall_ms": 0.0, "serial_equivalent_ms": 0.0,
        "hidden_overlap_ms": 0.0, "fallback_count": 0, "status": "ok",
        "sd_unmapped_keys": [], "model_only_param_count": 0, "model_only_buffer_count": 0,
    }
    _wave_events: list[tuple[Any, Any, dict[str, Any]]] = []
    _run_metrics: dict[str, Any] = {}
    _model = None
    try:
        import torch as _torch_tp
        _unet_name = str(kwargs.get("unet_name", "") or "")
        _path = _ring_resolve_unet_path(_unet_name, _lane)
        if not _path:
            return _md_fail(_metrics, _trace, "stage:path_unresolved", _t0_total)
        # S1 eligibility (pre-construction).
        _ok, _reason = _md_eligible(None, model_key, kwargs, _lane)
        if not _ok:
            _metrics.update({"eligibility": "ineligible", "reason": _reason,
                             "status": "ineligible"})
            _md_emit(_metrics.get("status"), _metrics.get("reason"), _metrics, _trace)
            return None
        # S1 config derivation (header only; metrics capture).
        _t_cfg = _time.monotonic_ns()
        _probe_wall: dict[str, Any] = {}
        _derived = _ring_derive_config(_path, _probe_wall=_probe_wall)
        if _derived is None:
            return _md_fail(_metrics, _trace, "stage:config_derivation_failed", _t0_total)
        _config, _meta_sd, _header, _n_layers, _prefix = _derived
        _metrics["header_config_wall_ms"] = round((_time.monotonic_ns() - _t_cfg) / 1_000_000, 4)
        _metrics["value_probe_wall_ms"] = _probe_wall.get("value_probe_wall_ms")
        if type(_config).__name__ != "ZImage":
            _metrics.update({"family": type(_config).__name__, "eligibility": "ineligible",
                             "reason": "family_not_zimage", "status": "ineligible"})
            _md_emit(_metrics.get("status"), _metrics.get("reason"), _metrics, _trace)
            return None
        # S2 meta construction (~20 ms): build under torch.device("meta").
        _t_gm = _time.monotonic_ns()
        with _torch_tp.no_grad(), _torch_tp.device("meta"):
            _model = _config.get_model(_meta_sd, "")
        _metrics["meta_get_model_wall_ms"] = round((_time.monotonic_ns() - _t_gm) / 1_000_000, 4)
        _meta_params = list(_model.parameters())
        if not _meta_params or not all(_p.device.type == "meta" for _p in _meta_params):
            return _md_fail(_metrics, _trace, "stage:meta_construction_failed", _t0_total)
        # model.model_sampling is poisoned (meta sigma schedules): rebuild it
        # OUTSIDE the meta context with the same helper comfy.model_base uses.
        _sampling = getattr(_model, "model_sampling", None)
        _poisoned = collect_meta_tensors(_sampling) if _sampling is not None else []
        _metrics["sampling_poisoned_tensors"] = len(_poisoned)
        if _poisoned:
            _ms_fn = _c6_comfy_fn("comfy.model_base", "model_sampling")
            if not callable(_ms_fn):
                return _md_fail(_metrics, _trace, "stage:sampling_fix_unavailable", _t0_total)
            _t_fix = _time.monotonic_ns()
            _model.model_sampling = _ms_fn(_model.model_config, _model.model_type)
            _metrics["sampling_fix_wall_ms"] = round((_time.monotonic_ns() - _t_fix) / 1_000_000, 4)
            _after = collect_meta_tensors(getattr(_model, "model_sampling", None))
            if _after:
                return _md_fail(_metrics, _trace, "stage:sampling_fix_incomplete", _t0_total)
        # S3 patcher (plain non-dynamic ModelPatcher, mirroring sd.py).
        _mgmt_fn = _c6_comfy_fn("comfy.model_management", "get_torch_device")
        _target = _mgmt_fn() if _mgmt_fn is not None else _torch_tp.device("cuda")
        _offload_fn = _c6_comfy_fn("comfy.model_management", "unet_offload_device")
        _offload = _offload_fn() if _offload_fn is not None else _torch_tp.device("cpu")
        _mp_cls = _c6_comfy_fn("comfy.model_patcher", "ModelPatcher")
        if _mp_cls is None:
            return _md_fail(_metrics, _trace, "stage:patcher_unavailable", _t0_total)
        _patcher = _mp_cls(_model, load_device=_target, offload_device=_offload)
        # S4 materialize directly on CUDA (~818 ms).
        _t_te = _time.monotonic_ns()
        _model.to_empty(device=_torch_tp.device("cuda"))
        _metrics["to_empty_wall_ms"] = round((_time.monotonic_ns() - _t_te) / 1_000_000, 4)
        # S5 key map + transform identity + uniform dtype (mirror V1 S5).
        _unet = getattr(_model, "diffusion_model", None) or _model
        _params = dict(_unet.named_parameters())
        _buffers = dict(_unet.named_buffers())
        _metrics["param_count"] = len(_params)
        try:
            _transformed = _config.process_unet_state_dict(dict(_meta_sd))
        except Exception:
            _transformed = None
        if not isinstance(_transformed, dict):
            return _md_fail(_metrics, _trace, "stage:transform_not_independent", _t0_total)
        _sd_keys = set(_transformed.keys())
        if _sd_keys != set(_meta_sd.keys()):
            return _md_fail(_metrics, _trace, "stage:transform_not_independent", _t0_total)
        _dest_key_set = set(_params.keys()) | set(_buffers.keys())
        _unmapped = sorted(_k for _k in _sd_keys if _k not in _dest_key_set)
        _metrics["sd_unmapped_keys"] = _unmapped[:20]
        if _unmapped:
            return _md_fail(_metrics, _trace, "stage:key_param_mismatch", _t0_total)
        _metrics["model_only_param_count"] = sum(
            1 for _k in _params.keys() if _k not in _sd_keys)
        _metrics["model_only_buffer_count"] = sum(
            1 for _k in _buffers.keys() if _k not in _sd_keys)
        _dtypes = set()
        for _k, _info in _header.items():
            if _k == "__metadata__":
                continue
            if _info.get("dtype"):
                _dtypes.add(_info["dtype"])
        if len(_dtypes) != 1:
            return _md_fail(_metrics, _trace, "stage:non_uniform_dtype", _t0_total)
        _sd_dt = _c6_safetensors_dtype_map().get(_dtypes.pop())
        if _sd_dt is None or _sd_dt not in list(getattr(_config, "supported_inference_dtypes", None) or []):
            return _md_fail(_metrics, _trace, "stage:unsupported_dtype", _t0_total)
        _dest_dtypes = set()
        for _k in _sd_keys:
            _dst = _params.get(_k)
            if _dst is None:
                _dst = _buffers.get(_k)
            if _dst is None:
                continue
            _dest_dtypes.add(_dst.dtype)
        if not _dest_dtypes or len(_dest_dtypes) != 1 or _sd_dt not in _dest_dtypes:
            return _md_fail(_metrics, _trace, "stage:dtype_mismatch", _t0_total)
        # S6 byte-contiguous waves from the header (reuse probe builder).
        _waves = build_wave_ranges(
            _header, wave_target_bytes=_MD_WAVE_TARGET_BYTES,
            max_wave_bytes=_MD_MAX_WAVE_BYTES)
        if _waves is None:
            return _md_fail(_metrics, _trace, "stage:tensor_exceeds_wave_cap", _t0_total)
        _metrics["tensor_count"] = len(_header) - (1 if "__metadata__" in _header else 0)
        _metrics["total_bytes"] = int(sum(
            _t["nbytes"] for _w in _waves for _t in _w["tensors"]))
        _metrics["wave_count"] = len(_waves)
        _wave_bytes_list = [int(_w["tensor_bytes"]) for _w in _waves]
        _metrics["actual_max_wave_bytes"] = max(_wave_bytes_list) if _wave_bytes_list else 0
        _metrics["actual_mean_wave_bytes"] = (
            int(sum(_wave_bytes_list) / len(_wave_bytes_list)) if _wave_bytes_list else 0)
        # S7 preadv wave ring.
        _data_start = _md_data_start_offset(_path)
        if _data_start is None:
            return _md_fail(_metrics, _trace, "stage:data_start_unavailable", _t0_total)
        _run_result = _md_run_waves(
            _params, _buffers, _path, _waves, _sd_dt, _data_start)
        if _run_result is None or _run_result[0] is None:
            _md_detail = ""
            if isinstance(_run_result, tuple) and len(_run_result) > 1:
                _md_detail = ":" + str(_run_result[1])
            # Merge partial progress (real preadv_bytes / io wall / fail
            # details) so the emitted fallback event carries diagnostics.
            if (isinstance(_run_result, tuple) and len(_run_result) > 2
                    and isinstance(_run_result[2], dict)):
                for _pk, _pv in _run_result[2].items():
                    _metrics[_pk] = _pv
            return _md_fail(_metrics, _trace, "stage:md_run" + _md_detail, _t0_total)
        _run_metrics, _wave_events = _run_result
        # S8 final model.to (params are ALREADY cuda from to_empty; the
        # final to only moves model-only leftovers / buffers still on cpu).
        _unbound_cpu = [k for k in _sd_keys
                        if k in _params and str(_params[k].device).startswith("cpu")]
        if _unbound_cpu:
            return _md_fail(_metrics, _trace, "stage:md_bind_incomplete", _t0_total)
        _t_to = _time.monotonic_ns()
        try:
            _model.to(_target)
        except Exception:
            return _md_fail(_metrics, _trace, "stage:final_model_to", _t0_total)
        _metrics["final_to_wall_ms"] = round((_time.monotonic_ns() - _t_to) / 1_000_000, 4)
        if _metrics["final_to_wall_ms"] > _MD_FINAL_TO_DUPLICATE_THRESHOLD_MS:
            return _md_fail(_metrics, _trace, "stage:final_to_duplicates_transfer", _t0_total)
        # S9 exactly ONE final synchronize (no per-tensor syncs).
        _t_sync = _time.monotonic_ns()
        try:
            _torch_tp.cuda.synchronize()
        except Exception:
            return _md_fail(_metrics, _trace, "stage:final_sync", _t0_total)
        _metrics["final_sync_wall_ms"] = round((_time.monotonic_ns() - _t_sync) / 1_000_000, 4)
        # wave device elapsed (realized by the final sync).
        _h2d_dev = 0.0
        for _ev_s, _ev_e, _wm in _wave_events:
            try:
                _ms = float(_ev_s.elapsed_time(_ev_e))
            except Exception:
                _ms = None
            _wm["device_ms"] = round(_ms, 4) if _ms is not None else None
            if _ms is not None:
                _h2d_dev += _ms
        _metrics["h2d_device_wall_ms"] = round(_h2d_dev, 4)
        # S10 totals + emit.
        _metrics["pinned_bytes"] = int(_run_metrics.get("pinned_bytes", 0))
        _metrics["preadv_io_wall_ms"] = round(float(_run_metrics.get("preadv_io_wall_ms", 0.0)), 4)
        _metrics["preadv_bytes"] = int(_run_metrics.get("preadv_bytes", 0))
        _metrics["fadvise_wall_ms"] = _run_metrics.get("fadvise_wall_ms")
        _metrics["h2d_host_issue_wall_ms"] = round(
            float(_run_metrics.get("h2d_host_issue_wall_ms", 0.0)), 4)
        _metrics["reuse_wait_total_ms"] = round(
            float(_run_metrics.get("reuse_wait_total_ms", 0.0)), 4)
        _metrics["max_reuse_wait_ms"] = round(
            float(_run_metrics.get("max_reuse_wait_ms", 0.0)), 4)
        _preadv_bytes = float(_metrics["preadv_bytes"])
        _preadv_ms = float(_metrics["preadv_io_wall_ms"])
        _metrics["preadv_gbps"] = round(
            _preadv_bytes / (_preadv_ms * 1e6) if _preadv_ms > 0 else 0.0, 4)
        _metrics["total_pipeline_wall_ms"] = round((_time.monotonic_ns() - _t0_total) / 1_000_000, 4)
        _metrics["serial_equivalent_ms"] = round(
            (float(_metrics["preadv_io_wall_ms"] or 0)
             + float(_metrics["h2d_device_wall_ms"] or 0)
             + float(_metrics["meta_get_model_wall_ms"] or 0)
             + float(_metrics["sampling_fix_wall_ms"] or 0)
             + float(_metrics["to_empty_wall_ms"] or 0)
             + float(_metrics["final_to_wall_ms"] or 0)
             + float(_metrics["final_sync_wall_ms"] or 0)), 4)
        _metrics["hidden_overlap_ms"] = round(
            max(0.0, float(_metrics["serial_equivalent_ms"]) - float(_metrics["total_pipeline_wall_ms"])), 4)
        _metrics["status"] = "ok"
        _metrics["reason"] = ""
        _md_emit("ok", "", _metrics, _trace)
        return (_patcher,)
    except Exception as _exc:
        return _md_fail(_metrics, _trace, f"stage:{type(_exc).__name__}", _t0_total)
