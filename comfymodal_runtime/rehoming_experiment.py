"""Post-restore rehoming shadow experiment (no graph execution).

A dedicated Modal method (``run_rehoming_experiment``) that, on a restored
single-use container, measures synchronized CPU→GPU transfer of the
RETAINED restored UNET storages vs the SAME model rehomed into fresh
anonymous RAM.  The order of the two measurements alternates per run so no
order/prewarming bias survives:

  order="original_first": measure restored-storage H2D -> clone -> measure
                          fresh-clone H2D
  order="clone_first":    clone -> measure fresh-clone H2D -> measure
                          restored-storage H2D

Every measurement uses the model's ACTUAL CPU storages (per-storage
``to(cuda, non_blocking=True)`` + final sync — the same loop shape as the
real ComfyUI UNET load) and never mutates the CPU model, so both
measurements are valid on the same container.  Correctness is proven by a
full per-parameter byte-equality pass and metadata fingerprints AFTER all
timing measurements.  Everything is recorded JSON-safe; nothing raises.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any


def _capture_identity() -> dict[str, Any]:
    """Best-effort remote identity (provider/region/GPU/task)."""
    result: dict[str, Any] = {}
    try:
        from comfymodal_runtime.modal_app import _capture_remote_identity
        result.update(dict(_capture_remote_identity()))
    except Exception:
        pass
    try:
        from comfymodal_runtime.model_preload import _capture_host_info
        result["host"] = dict(_capture_host_info())
    except Exception:
        pass
    return result


def _rusage_deltas(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("major_faults", "minor_faults", "voluntary_context_switches",
                "involuntary_context_switches"):
        b = before.get(key)
        a = after.get(key)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            out[key] = max(0, int(a) - int(b))
        else:
            out[key] = None
    return out


def _rusage_snapshot() -> dict[str, Any]:
    try:
        import resource as _r
        ru = _r.getrusage(_r.RUSAGE_SELF)
        return {
            "major_faults": int(ru.ru_majflt),
            "minor_faults": int(ru.ru_minflt),
            "voluntary_context_switches": int(ru.ru_nvcsw),
            "involuntary_context_switches": int(ru.ru_nivcsw),
        }
    except Exception:
        return {}


def _rss_mib() -> float | None:
    try:
        for _line in open("/proc/self/status", encoding="utf-8", errors="replace"):
            if _line.startswith("VmRSS:"):
                return round(float(_line.split()[1]) / 1024.0, 1)
    except Exception:
        pass
    return None


def _cuda_ready() -> dict[str, Any]:
    out: dict[str, Any] = {"available": False}
    try:
        import torch
        out["available"] = bool(torch.cuda.is_available())
        if out["available"]:
            out["device_name"] = str(torch.cuda.get_device_name(0))
            out["gpu_uuid"] = ""
            try:
                out["gpu_uuid"] = str(torch.cuda.get_device_properties(0).uuid)
            except Exception:
                pass
            out["free_bytes"] = int(torch.cuda.mem_get_info()[0])
            out["total_bytes"] = int(torch.cuda.mem_get_info()[1])
    except Exception as exc:
        out["error"] = str(exc)[:200]
    return out


def run_rehoming_experiment_impl(
    entrypoint: Any,
    *,
    order: str = "original_first",
    request_id: str = "",
) -> dict[str, Any]:
    """Execute one paired post-restore rehoming measurement on this container.

    *entrypoint* — the ModalRuntimeEntrypoint instance (for the retained
    snapshot models and runtime config).  Returns the full JSON-safe
    record.  Never raises: every failure is captured in the record.
    """
    started_wall_ns = int(time.time() * 1_000_000_000)
    started_mono_ns = time.monotonic_ns()
    record: dict[str, Any] = {
        "method": "run_rehoming_experiment",
        "request_id": request_id or "",
        "order": order,
        "started_wall_ns": started_wall_ns,
        "started_mono_ns": started_mono_ns,
        "status": "running",
    }
    try:
        identity = _capture_identity()
        record["identity"] = identity
        # ── Runtime config (torch threads) + snapshot state ──
        try:
            entrypoint._configure_runtime()
            entrypoint._lazy_init_snapshot_state()
        except Exception as exc:
            record["runtime_config_error"] = str(exc)[:200]
        try:
            from comfymodal_runtime.model_preload import _capture_torch_thread_counts
            record["torch"] = _capture_torch_thread_counts()
        except Exception:
            pass
        record["restored_instance_id"] = getattr(
            entrypoint, "_restored_instance_id", ""
        )
        record["restore_count"] = getattr(entrypoint, "_restore_count", 0)
        record["cuda"] = _cuda_ready()
        if not record["cuda"].get("available"):
            record["status"] = "failed"
            record["reason"] = "cuda_unavailable"
            return record

        # ── The retained restored UNET ──
        import torch
        from comfymodal_runtime.unet_backing import (
            _iter_unet_tensors,
            clone_unet_to_fresh_ram_after_restore,
            measure_tensors_synced_h2d,
            unet_metadata_fingerprint,
        )

        def _model_tensor_pairs(model: Any) -> list[tuple[str, Any]]:
            """(name, tensor) pairs of *model*'s unique storages (dedup)."""
            return [
                (_name, _tensor)
                for _name, _tensor, _st, _addr, _nbytes in _iter_unet_tensors(model)
            ]

        _models = getattr(entrypoint, "_cpu_snapshot_models", None)
        unet = getattr(_models, "unet", None) if _models is not None else None
        if unet is None:
            # Fallback: the preload bridge's retained preparation UNET.
            try:
                prep = getattr(entrypoint._preload_bridge, "_preparation", None)
                if prep is not None and getattr(prep, "unet_future", None) is not None:
                    unet = prep.unet_future.result()
            except Exception:
                unet = None
        if unet is None:
            record["status"] = "failed"
            record["reason"] = "no_retained_unet"
            return record
        record["unet_object_id"] = str(id(unet))
        record["unet_type"] = f"{type(unet).__module__}.{type(unet).__qualname__}"
        try:
            from comfymodal_runtime.unet_backing import unet_storage_sizes
            record["storage_sizes"] = unet_storage_sizes(unet)
            record["storage_count"] = len(record["storage_sizes"])
            record["unet_bytes"] = sum(record["storage_sizes"])
        except Exception:
            pass
        # Residency + backing of the RESTORED storages (before any clone).
        try:
            from comfymodal_runtime.unet_backing import (
                capture_unet_backing_evidence,
                mincore_unet_residency,
            )
            record["restored_residency"] = mincore_unet_residency(unet)
            record["restored_backing"] = capture_unet_backing_evidence(
                unet, label="restored_before_rehome",
            )
        except Exception as exc:
            record["restored_residency_error"] = str(exc)[:200]

        order = str(order or "original_first").strip()
        if order not in ("original_first", "clone_first"):
            order = "original_first"
        record["order"] = order
        try:
            _f0 = unet_metadata_fingerprint(unet)
            record["fingerprint_before"] = _f0
        except Exception:
            pass
        _rusage_0 = _rusage_snapshot()

        # ── Retained restored UNET tensor references (pre-clone) ──
        # The rehome clone rebinds the model IN PLACE; to measure the
        # ORIGINAL restored storages in either order, hold strong refs to
        # the original (name, tensor) pairs BEFORE any clone.  The clone
        # then replaces ``.data``/buffers; the captured tensors still pin
        # the original restored storages, so their H2D measurement always
        # reads the restored pages regardless of order.
        _orig_tensors: list[tuple[str, Any]] = [
            (_name, _tensor)
            for _name, _tensor, _st, _addr, _nbytes in _iter_unet_tensors(unet)
        ]
        record["original_tensor_count"] = len(_orig_tensors)

        # ── Paired measurements (alternating order) ──
        # The ORIGINAL H2D measurement keeps its GPU tensors (paired 1:1
        # with names) so the clone can be byte-compared against the bytes
        # that were actually moved from the restored storages (a real
        # correctness proof, run AFTER all timing measurements).
        _original_gpu: tuple[list[Any], list[str]] | None = None
        if order == "clone_first":
            record["clone"] = clone_unet_to_fresh_ram_after_restore(unet)
            record["clone_h2d"] = measure_tensors_synced_h2d(
                _model_tensor_pairs(unet), label="clone", keep_gpu=False,
            )[0]
            record["original_h2d"], _original_gpu = measure_tensors_synced_h2d(
                _orig_tensors, label="original", keep_gpu=True,
            )
        else:
            record["original_h2d"], _original_gpu = measure_tensors_synced_h2d(
                _orig_tensors, label="original", keep_gpu=True,
            )
            record["clone"] = clone_unet_to_fresh_ram_after_restore(unet)
            record["clone_h2d"] = measure_tensors_synced_h2d(
                _model_tensor_pairs(unet), label="clone", keep_gpu=False,
            )[0]

        # ── Correctness + identity (AFTER all timing measurements) ──
        try:
            record["fingerprint_after"] = unet_metadata_fingerprint(unet)
        except Exception:
            pass
        # Byte equality: the rehomed CPU model vs the GPU copy of the
        # ORIGINAL restored storages (both live after the measurements).
        # Paired by NAME (the GPU list was built 1:1 from the same
        # (name, tensor) iteration).
        _eq: dict[str, Any] = {"compared": 0, "equal": 0, "status": ""}
        try:
            _gpu_names: list[str] = []
            _gpu_list: list[Any] = []
            if _original_gpu is not None:
                _gpu_list, _gpu_names = _original_gpu
            _cpu_map: dict[str, Any] = {}
            for _n, _t in _model_tensor_pairs(unet):
                _cpu_map[_n] = _t
            if len(_gpu_list) != len(_gpu_names):
                _eq["status"] = "internal_mismatch"
            elif len(_gpu_list) != len(_cpu_map):
                _eq["status"] = (
                    f"count_mismatch gpu={len(_gpu_list)} cpu={len(_cpu_map)}"
                )
            else:
                for _idx, _name in enumerate(_gpu_names):
                    _cpu_t = _cpu_map.get(_name)
                    if _cpu_t is None:
                        _eq["status"] = f"missing_cpu:{_name}"
                        break
                    try:
                        # torch.equal requires same-device tensors; move the
                        # kept GPU copy to CPU for the byte comparison.
                        _gpu_cpu = _gpu_list[_idx].to(device="cpu")
                        if not torch.equal(_cpu_t, _gpu_cpu):
                            _eq["status"] = f"mismatch:{_name}"
                            break
                    except Exception as exc:
                        _eq["status"] = f"compare_error:{_name}:{type(exc).__name__}"
                        break
                    _eq["compared"] += 1
                    _eq["equal"] += 1
                if not _eq["status"]:
                    _eq["status"] = "all_equal"
        except Exception as exc:
            _eq["status"] = f"error:{type(exc).__name__}"
        record["byte_equality_original_gpu_vs_clone"] = _eq
        # Release the kept GPU copy.
        try:
            del _original_gpu
            torch.cuda.empty_cache()
        except Exception:
            pass
        _rusage_1 = _rusage_snapshot()
        record["faults"] = _rusage_deltas(_rusage_0, _rusage_1)
        record["rss_mib_final"] = _rss_mib()
        record["ended_mono_ns"] = time.monotonic_ns()
        record["total_wall_ms"] = round(
            (record["ended_mono_ns"] - started_mono_ns) / 1_000_000, 3
        )
        record["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - never raises out
        record["status"] = "failed"
        record["reason"] = str(exc)[:300]
        try:
            record["error_type"] = type(exc).__name__
        except Exception:
            pass
    # JSON-safe flattening guard.
    try:
        json.dumps(record)
    except Exception:
        record = {"method": "run_rehoming_experiment", "status": "failed",
                  "reason": "record_not_json_serializable"}
    return record
