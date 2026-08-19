"""Dedicated Modal source-only E16 endpoint."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("COMFYMODAL_E16_SOURCE_BENCHMARK", "1")

import modal

import e16_source_io as io

_ROOT = Path(__file__).resolve().parent
_PLAN_SOURCE = _ROOT / "v2_restore_plan.json"
_PLAN_IMAGE_PATH = "/opt/comfymodal_e16_restore_plan.json"
_MODELS_ROOT = "/root/models"
_VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")
_APP_NAME = os.environ.get("COMFYMODAL_E16_APP_NAME", "comfyui-modal-e16-source-io")
_GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
_V2_MODULES = (
    "api_prompt_validator", "canonical_execution", "comfyapp",
    "comfymodal_runtime", "failure_summary", "gpu_catalog", "modal_client",
    "optimizations", "production_workflow", "profiler_trace_v4",
    "run_prompt_options", "timing_trace", "wall_clock_trace_v3",
    "warmup_profile", "workflow_metadata",
)

try:
    import comfyapp as _production_image_source
    _image = _production_image_source._image_base.pip_install("fastsafetensors==0.3.3")
    _image = _image.add_local_file(str(_ROOT / "e16_source_io.py"), "/root/e16_source_io.py", copy=True)
    _image = _image.add_local_file(str(_ROOT / "e16_source_io_modal.py"), "/root/e16_source_io_modal.py", copy=True)
    _image = _image.add_local_file(str(_PLAN_SOURCE), _PLAN_IMAGE_PATH, copy=True)
    for _module in _V2_MODULES:
        _image = _image.add_local_python_source(_module, copy=True)
except Exception as exc:
    raise RuntimeError("E16 production image construction failed") from exc

_models_volume = modal.Volume.from_name(_VOLUME_NAME, create_if_missing=False)
if not callable(getattr(_models_volume, "with_mount_options", None)):
    raise RuntimeError("Modal SDK lacks read-only Volume mount options")
_models_mount = _models_volume.with_mount_options(read_only=True)

app = modal.App(_APP_NAME, image=_image, include_source=False)


def _remote_identity() -> dict[str, Any]:
    return {
        "provider": os.environ.get("MODAL_CLOUD_PROVIDER", ""),
        "region": os.environ.get("MODAL_REGION", ""),
        "image_id": os.environ.get("MODAL_IMAGE_ID", ""),
        "container_session_id": os.environ.get("MODAL_TASK_ID", ""),
        "hostname": platform.node(),
        "gpu": _GPU,
        "models_volume": _VOLUME_NAME,
        "models_mount": _MODELS_ROOT,
        "models_mount_read_only": True,
    }


def _probe_volume_generation() -> dict[str, Any]:
    try:
        volume = modal.Volume.from_name(
            _VOLUME_NAME,
            create_if_missing=False,
            version=1,
        )
        volume.hydrate()
        return {"classification": "V1", "outcome": "existing Volume accepts v1 pin"}
    except Exception as exc:
        text = str(exc)
        lowered = text.lower()
        if "version" in lowered and "v2" in lowered:
            return {"classification": "V2", "outcome": text[:500]}
        return {"classification": "UNKNOWN", "outcome": text[:500]}


def _resolve_with_authoritative_logic(folder: str, filename: str) -> tuple[str, str]:
    sys.path.insert(0, "/root/comfy/ComfyUI")
    try:
        import folder_paths

        resolved = folder_paths.get_full_path(folder, filename)
        if resolved and os.path.isfile(resolved):
            return os.path.realpath(resolved), "folder_paths.get_full_path"
    except Exception:
        pass
    candidate = os.path.join(_MODELS_ROOT, folder, filename)
    if os.path.isfile(candidate):
        return os.path.realpath(candidate), "mounted_models_fallback"
    raise FileNotFoundError(f"model resolver did not find {folder}/{filename}")


def _load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("model plan is not an object")
    return value


def _cache_reset(paths: list[str]) -> dict[str, Any]:
    return io.reset_file_cache(paths)


def _build_model_state(request: dict[str, str], path: str, torch: Any, staged: Any, source_order: Any) -> dict[str, Any]:
    manifest = io.manifest_for_path(path, request["role"])
    config = staged.StagedConfig(
        enabled=True,
        producers=4,
        pool_mb=1024,
        bucket_mb=256,
        source_order_enabled=True,
    )
    plan = staged.plan(path, config=config)
    eligibility = io.build_eligibility(manifest, plan, source_order, torch)
    return {
        "request": request,
        "manifest": manifest,
        "path_resolution": request.get("resolution", ""),
        "staged_plan": plan,
        "source_layout": plan.source_layout,
        "eligibility": eligibility,
    }


def _preadv_probe(states: list[dict[str, Any]], source_order: Any, torch: Any, slabs: list[Any]) -> dict[str, Any]:
    all_pinned = all(bool(slab.is_pinned()) for slab in slabs)
    result: dict[str, Any] = {
        "PREADV_BRANCH_USED": False,
        "PREADV_CALLS": 0,
        "PREADV_BYTES": 0,
        "HOST_SLAB_IS_PINNED_ALL": all_pinned,
        "BYTE_VALIDATION": True,
        "DIRECT_SOURCE_TO_PINNED_COPY_BYTES": 0,
        "per_model": [],
    }
    if not bool(getattr(source_order, "_PREADV", False)) or getattr(source_order, "_preadv", None) is None:
        result["BYTE_VALIDATION"] = False
        result["error"] = "E11 preadv branch is unavailable"
        return result
    original = source_order._preadv

    def counted(fd: int, buffers: list[Any], offset: int) -> int:
        value = original(fd, buffers, offset)
        result["PREADV_CALLS"] += 1
        result["PREADV_BYTES"] += max(0, int(value))
        return value

    source_order._preadv = counted
    try:
        for state in states:
            layout = state["source_layout"]
            manifest = state["manifest"]
            checked = 0
            valid = True
            calls_before = result["PREADV_CALLS"]
            fd = os.open(manifest["path"], os.O_RDONLY)
            try:
                for index, block in enumerate(source_order.iter_blocks(layout, io.BLOCK_BYTES)):
                    if checked >= io.PINNED_PROBE_BYTES:
                        break
                    count = min(int(block.size), io.PINNED_PROBE_BYTES - checked)
                    slab = slabs[index % len(slabs)]
                    source_order.read_into(fd, slab, count, int(block.file_offset))
                    expected = getattr(os, "pread")(fd, count, int(block.file_offset))
                    actual = memoryview(slab.numpy())[:count].tobytes()
                    valid = valid and actual == expected
                    checked += count
            finally:
                os.close(fd)
            result["per_model"].append({
                "role": manifest["role"],
                "bytes_checked": checked,
                "preadv_calls": result["PREADV_CALLS"] - calls_before,
                "byte_validation": valid,
            })
            result["BYTE_VALIDATION"] = result["BYTE_VALIDATION"] and valid
    except Exception as exc:
        result["BYTE_VALIDATION"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        source_order._preadv = original
    result["PREADV_BRANCH_USED"] = bool(result["PREADV_CALLS"] > 0)
    result["HOST_SLAB_IS_PINNED_ALL"] = all_pinned
    result["DIRECT_SOURCE_TO_PINNED_COPY_BYTES"] = 0
    return result


def _primary_valid(state: dict[str, Any]) -> bool:
    arms = state.get("arms", {})
    current = arms.get(io.CURRENT_RANGE)
    source = arms.get(io.SOURCE_ORDER)
    if not current or not source:
        return False
    return bool(
        current.get("status") == "ok"
        and source.get("status") == "ok"
        and current.get("digest_match") is True
        and source.get("digest_match") is True
        and current.get("source_bytes_read") == source.get("source_bytes_read")
        and source.get("density_gap_bytes") == 0
    )


@app.function(
    image=_image,
    gpu=_GPU,
    cpu=12,
    memory=32768,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={_MODELS_ROOT: _models_mount},
    env={
        "COMFYMODAL_E16_SOURCE_BENCHMARK": "1",
        "COMFYMODAL_RUNTIME": "1",
        "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "1",
        "COMFYMODAL_V2_GPU": _GPU,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_e16_source_benchmark(run_id: str = "RUN1", strategy_order: str = "CLIP_CURRENT_FIRST") -> dict[str, Any]:
    started = time.perf_counter()
    identity = _remote_identity()
    result: dict[str, Any] = {
        "tool": "benchmark_source_io_e16",
        "run_id": run_id,
        "strategy_order": strategy_order,
        "identity": identity,
        "volume_generation_probe": _probe_volume_generation(),
        "models": [],
        "preadv_probe": None,
        "tmp": None,
        "cache": None,
        "pinned_fill": None,
        "structural_validity": "UNKNOWN",
        "status": "ok",
    }
    try:
        plan = _load_json(_PLAN_IMAGE_PATH)
        requests = io.model_requests_from_plan(plan)
        resolved: list[dict[str, str]] = []
        for request in requests:
            path, method = _resolve_with_authoritative_logic(request["folder"], request["filename"])
            resolved.append({**request, "path": path, "resolution": method})
        import torch
        import comfymodal_runtime.source_order_safetensors as source_order
        import comfymodal_runtime.staged_safetensors as staged

        states = [
            _build_model_state(request, request["path"], torch, staged, source_order)
            for request in resolved
        ]
        required_bytes = sum(int(state["manifest"]["size_bytes"]) for state in states)
        result["tmp"] = io.inspect_tmp("/tmp", required_bytes)
        result["cache"] = io.inspect_cache_capability(states[0]["manifest"]["path"])
        result["eligibility"] = {
            state["manifest"]["role"]: state["eligibility"] for state in states
        }
        if not all(state["eligibility"]["source_order_eligible"] for state in states):
            result["status"] = "E11_REMOTE_PATH_FAILURE"
            result["structural_validity"] = "INVALID_E11_ELIGIBILITY"
            return result
        empty = getattr(torch, "empty")
        uint8 = getattr(torch, "uint8")
        slabs = [empty(io.BLOCK_BYTES, dtype=uint8, pin_memory=True) for _ in range(4)]
        result["preadv_probe"] = _preadv_probe(states, source_order, torch, slabs)
        if not (
            result["preadv_probe"]["PREADV_BRANCH_USED"]
            and result["preadv_probe"]["HOST_SLAB_IS_PINNED_ALL"]
            and result["preadv_probe"]["BYTE_VALIDATION"]
            and result["preadv_probe"]["DIRECT_SOURCE_TO_PINNED_COPY_BYTES"] == 0
        ):
            result["status"] = "E11_REMOTE_PATH_FAILURE"
            result["structural_validity"] = "INVALID_PREADV_PROOF"
            return result

        for state in states:
            manifest = state["manifest"]
            expected_digest = None
            arms: dict[str, dict[str, Any]] = {}
            role = manifest["role"]
            current_first = (
                strategy_order.upper() == "CLIP_CURRENT_FIRST" and role == "CLIP"
            ) or (
                strategy_order.upper() != "CLIP_CURRENT_FIRST" and role == "UNET"
            )
            ordered = [io.CURRENT_RANGE, io.SOURCE_ORDER] if current_first else [io.SOURCE_ORDER, io.CURRENT_RANGE]
            for arm in ordered:
                reset = _cache_reset([manifest["path"]])
                if arm == io.CURRENT_RANGE:
                    measurement = io.run_current_range(manifest, expected_digest=expected_digest)
                else:
                    measurement = io.run_source_order(
                        manifest,
                        state["source_layout"],
                        source_order,
                        slabs,
                        expected_digest=None,
                    )
                measurement["cache_reset_before"] = reset
                arms[arm] = measurement
                if arm == io.CURRENT_RANGE:
                    expected_digest = measurement.get("digest")
                    measurement["digest_match"] = True
            current_digest = arms[io.CURRENT_RANGE].get("digest")
            source_arm = arms[io.SOURCE_ORDER]
            source_arm["digest_match"] = bool(
                manifest["gap_bytes"] == 0
                and source_arm.get("source_bytes_read") == manifest["tensor_bytes"]
                and source_arm.get("digest") == current_digest
            )
            state["arms"] = arms
            if not _primary_valid(state):
                result["status"] = "INCONCLUSIVE"
                result["structural_validity"] = "INVALID_PRIMARY_BYTE_ACCOUNTING"
                result["models"].append(_serialize_state(state))
                return result
            for arm in (io.MMAP, io.TMP_STAGE):
                reset = _cache_reset([manifest["path"]])
                measurement: dict[str, Any]
                if arm == io.MMAP:
                    measurement = io.run_mmap(manifest, expected_digest=current_digest)
                elif result["tmp"]["capacity"] == "PASS":
                    measurement = io.run_tmp_stage([manifest], expected_digest=current_digest)
                else:
                    measurement = {"arm": arm, "status": "unsupported", "reason": "TMP_STAGE_CAPACITY_FAIL"}
                measurement["cache_reset_before"] = reset
                arms[arm] = measurement
            result["models"].append(_serialize_state(state))

        representative = next(state for state in states if state["manifest"]["role"] == "UNET")
        _cache_reset([representative["manifest"]["path"]])
        result["pinned_fill"] = io.run_pinned_fill(representative["manifest"], torch)
        result["combined"] = _combined_results(result["models"])
        source_gbps = result["combined"][io.SOURCE_ORDER].get("effective_GBps")
        result["prewarm_estimate"] = {
            "basis": "ESTIMATE_FROM_MEASURED_THROUGHPUT",
            "bytes_at_0_5s": int((source_gbps or 0) * 1e9 * 0.5),
            "bytes_at_1s": int((source_gbps or 0) * 1e9),
            "bytes_at_2s": int((source_gbps or 0) * 1e9 * 2),
        }
        result["structural_validity"] = "VALID_PRIMARY_AND_DIGESTS"
        return result
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        result["elapsed_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)


def _serialize_state(state: dict[str, Any]) -> dict[str, Any]:
    manifest = state["manifest"]
    return {
        "role": manifest["role"],
        "filename": manifest["filename"],
        "path": manifest["path"],
        "resolution": state["path_resolution"],
        "file_bytes": manifest["size_bytes"],
        "tensor_bytes": manifest["tensor_bytes"],
        "tensor_count": manifest["tensor_count"],
        "data_region_bytes": manifest["data_bytes"],
        "gap_bytes": manifest["gap_bytes"],
        "payload_digest": state.get("payload_digest"),
        "eligibility": state["eligibility"],
        "arms": state.get("arms", {}),
    }


def _combined_results(models: list[dict[str, Any]]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for arm in (io.CURRENT_RANGE, io.SOURCE_ORDER, io.MMAP, io.TMP_STAGE):
        rows = [model["arms"].get(arm) for model in models if model["arms"].get(arm, {}).get("status") == "ok"]
        if not rows:
            combined[arm] = {"status": "unsupported"}
            continue
        wall = sum(float(row.get("wall_ms") or 0) for row in rows)
        payload = sum(int(row.get("bytes") or 0) for row in rows)
        combined[arm] = {
            "status": "ok",
            "bytes": payload,
            "wall_ms": round(wall, 3),
            "process_cpu_ms": round(sum(float(row.get("process_cpu_ms") or 0) for row in rows), 3),
            "effective_GBps": io._gbps(payload, wall),
        }
    return combined


@app.local_entrypoint()
def main(
    run_id: str = "RUN1",
    strategy_order: str = "CLIP_CURRENT_FIRST",
    output: str = "",
) -> None:
    result = run_e16_source_benchmark.remote(run_id, strategy_order)
    target = Path(output or f"V2_BATCH_E16_{run_id}.json")
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "run_id": run_id,
        "status": result.get("status"),
        "provider": result.get("identity", {}).get("provider", ""),
        "region": result.get("identity", {}).get("region", ""),
        "output": str(target),
    }, sort_keys=True))
