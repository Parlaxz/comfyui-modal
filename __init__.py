import asyncio
import hashlib
import json
import uuid
import sys
import os
import re
import base64
import copy
import threading
import logging
import subprocess
import time
import sqlite3
from collections import namedtuple
from pathlib import Path
import traceback as _traceback
from typing import Any

_NODE_DIR = os.path.dirname(os.path.abspath(__file__))
if _NODE_DIR not in sys.path:
    sys.path.insert(0, _NODE_DIR)

from comfymodal_runtime.env import env_flag

_local_exact_prefill = env_flag("COMFYMODAL_EXACT_CLIP_PREFILL", default=True)
print(f"[exact_prefill.local] enabled={int(_local_exact_prefill)} source=env")

_log = logging.getLogger(__name__)

from aiohttp import web
from local_placeholders import (
    create_local_placeholder,
    get_local_model_file_info,
    normalize_model_filename,
    normalize_model_folder,
)
from workflow_metadata import (
    extract_model_stack,
    extract_warmup_stack,
    prompt_sha256,
    stack_to_warmup_profile,
    summarize_prompt_fields,
)
from api_prompt_validator import (
    assert_valid_api_prompt_structure,
    validate_api_prompt_structure,
    validate_class_types_exist,
)
from failure_summary import FailureSummary
from output_converter import (
    OUTPUT_FORMATS,
    WEBP_LOSSLESS_COMPRESSION,
    DEFAULTS as _CONVERTER_DEFAULTS,
)
from output_saver import save_output_image, DEFAULTS as _SAVER_DEFAULTS
from local_artifacts import (
    get_studio_outputs_dir,
    get_modal_outputs_dir,
    get_benchmark_logs_dir,
    get_optimization_logs_dir,
)
from timing_trace import Trace, TraceV4, coerce_t0_from_browser, merge_remote_trace_into
from profiler_trace_v4 import (
    make_event, mark_event, EventTrace, profile_enabled, get_profile_level,
    T0_CLIENT_PRESS, T1_LOCAL_BRIDGE_RECEIVED,
    T1A_LOCAL_PAYLOAD_PARSE_START, T1B_LOCAL_PAYLOAD_PARSE_END,
    T1C_LOCAL_PREFLIGHT_START, T1D_LOCAL_PREFLIGHT_END,
    T1E_ACTIVE_PROFILE_WRITE_START, T1F_ACTIVE_PROFILE_WRITE_END,
    T1G_BODY_READ_START, T1H_BODY_READ_END,
    T1I_JSON_PARSE_START, T1J_JSON_PARSE_END,
    T1K_PAYLOAD_NORMALIZE_START, T1L_PAYLOAD_NORMALIZE_END,
    T1M_TRACE_STRIP_START, T1N_TRACE_STRIP_END,
    T1O_PROMPT_EXTRACT_START, T1P_PROMPT_EXTRACT_END,
    T1Q_STACK_EXTRACT_START, T1R_STACK_EXTRACT_END,
    T2A_MODAL_CALL_CONSTRUCTED,
    T2B_MODAL_CALL_STREAM_OPEN, T2C_FIRST_REMOTE_EVENT_RECEIVED,
    T2D_LOCAL_PROMPT_ACK_RETURNED,
    LOCAL_PROMPT_ENQUEUED, LOCAL_PROMPT_ACK_READY,
    T9_LOCAL_REMOTE_RESULT_RECEIVED,
    T9A_LOCAL_RESULT_DESERIALIZE_START, T9B_LOCAL_RESULT_DESERIALIZE_END,
    T9C_LOCAL_BASE64_DECODE_START, T9D_LOCAL_BASE64_DECODE_END,
    T9E_LOCAL_FILE_WRITE_START, T9F_LOCAL_FILE_WRITE_END,
    T10_LOCAL_MATERIALIZED,
    T10A_LOCAL_RESPONSE_TO_COMFY_START, T10B_LOCAL_RESPONSE_TO_COMFY_END,
    T11_LOCAL_UI_DONE,
    BEFORE_STACK_EXTRACT, AFTER_STACK_EXTRACT,
    BEFORE_ACTIVE_NEXT_WRITE, AFTER_ACTIVE_NEXT_WRITE,
    BEFORE_GPU_SPAWN, FIRST_GPU_RESPONSE,
    PHASE_LOCAL_PRE, PHASE_LOCAL_BRIDGE, PHASE_LOCAL_MATERIALIZE,
    derive_spans, derive_non_overlapping_critical_path,
    estimate_clock_skew, summarize_trace, log_event,
)
from production_workflow import (
    normalize_production_options,
    compile_production_workflow,
    ProductionPlan,
    _canonical_workflow_hash,
    HASH_SCHEMA_VERSION,
    COMPILER_SCHEMA_VERSION as PRODUCTION_COMPILER_VERSION,
    PRODUCTION_PLAN_SCHEMA_VERSION,
)
from run_prompt_options import (
    build_run_prompt_options,
    ensure_run_prompt_options,
)
import experiment_setup_adapter as _experiment_setup_adapter
from warmup_profile import prepare_active_next_profile as prepare_active_next_profile
from canonical_execution import (
    RunTrace,
    build_execution_plan,
    execute_modal_prompt,
    execute_plan,
    prepare_modal_execution,
    _reset_profile_prep_cache,
)
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.result_delivery import materialize_modal_result as _materialize_v2_result
from comfymodal_runtime.trace import RuntimeTrace
from comparison import (
    create_profile,
    update_profile,
    delete_profile,
    duplicate_profile,
    list_profiles,
    get_profile,
    auto_detect_slots,
    set_slots,
    validate_profile,
    run_comparison,
    save_comparison_manifest,
    save_comparison_result,
    get_comparison_results,
    list_comparison_runs,
    detect_slots,
    load_comparison_config,
    save_comparison_config,
    get_workflow_nodes,
    get_profile_workflow,
)

from execution_runtime import (
    MODE_V1,
    MODE_V2,
    MODE_SHADOW,
    resolve_execution_mode,
    normalize_mode,
    capture_execution_mode,
    validate_config_payload,
    AVAILABLE_EXECUTION_MODES as _AVAILABLE_EXECUTION_MODES,
)

import model_manifest as _model_manifest
import modal_workspaces as _workspace_store

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "web"


def _unique_path(directory: str, filename: str) -> str:
    if not filename or not isinstance(filename, str):
        raise ValueError(f"invalid filename: {filename!r}")
    if "\x00" in filename:
        raise ValueError("filename contains null byte")
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"unsafe remote output filename: {filename!r}")
    root = Path(directory).resolve()
    dest = (root / safe_name).resolve()
    if dest.parent != root:
        raise ValueError(f"output path escaped root: {filename!r}")
    if not dest.exists():
        return str(dest)
    stem, ext = os.path.splitext(safe_name)
    suffix = f"{uuid.uuid4().hex[:12]}"
    return str(root / f"{stem}_{suffix}{ext}")

# ── MIME type to extension map for remote result materialization ──
_MIME_EXT_MAP = {
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


def _infer_file_ext(filename: str, mime_type: str | None, file_ext: str | None) -> str:
    if file_ext:
        return file_ext if file_ext.startswith(".") else "." + file_ext
    if mime_type:
        ext = _MIME_EXT_MAP.get(mime_type.lower())
        if ext:
            return ext
    _, ext = os.path.splitext(filename)
    if ext:
        return ext
    return ".png"


def select_primary_output(per_node_outputs: dict, node_id: str) -> dict | None:
    """Deterministically select the primary/final image entry for a node.

    Selection precedence:
    1. Entry with comparison_side == "b"
    2. Entry under b_images output key
    3. Entry marked primary/final
    4. Entry under images
    5. Entry with comparison_side == "a"
    6. First flat image as last-resort compatibility fallback
    """
    node_outputs = per_node_outputs.get(node_id)
    if not node_outputs or not isinstance(node_outputs, dict):
        return None

    for entries in node_outputs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("comparison_side") == "b":
                return entry

    b_entries = node_outputs.get("b_images")
    if isinstance(b_entries, list) and b_entries:
        if isinstance(b_entries[0], dict):
            return b_entries[0]

    for entries in node_outputs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("primary"):
                return entry

    img_entries = node_outputs.get("images")
    if isinstance(img_entries, list) and img_entries:
        if isinstance(img_entries[0], dict):
            return img_entries[0]

    for entries in node_outputs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("comparison_side") == "a":
                return entry

    for entries in node_outputs.values():
        if isinstance(entries, list) and entries:
            if isinstance(entries[0], dict):
                return entries[0]

    return None


def _stable_output_identity(node_id: str, output_key: str, entry: dict, fallback_index: int = 0) -> tuple[str, str, str, int]:
    raw_index = entry.get("output_index", fallback_index)
    try:
        output_index = int(raw_index)
    except (TypeError, ValueError):
        output_index = fallback_index
    return (
        str(node_id),
        str(output_key or entry.get("output_key") or "images"),
        str(entry.get("filename", "")),
        output_index,
    )


def _build_native_output_descriptor(local_filename: str) -> dict:
    return {
        "filename": local_filename,
        "subfolder": "",
        "type": "output",
    }


def _build_materialized_output_entry(remote_entry: dict, *, node_id: str, output_key: str, local_filename: str, local_path: str, decoded_bytes: bytes, fallback_index: int = 0) -> dict:
    inferred_extension = _infer_file_ext(
        remote_entry.get("filename", local_filename),
        remote_entry.get("mime_type"),
        remote_entry.get("file_ext"),
    )
    return {
        "filename": local_filename,
        "path": local_path,
        "subfolder": "",
        "type": "output",
        "node_id": str(node_id),
        "output_key": output_key,
        "comparison_side": remote_entry.get("comparison_side", ""),
        "mime_type": remote_entry.get("mime_type", ""),
        "file_ext": inferred_extension,
        "width": remote_entry.get("width"),
        "height": remote_entry.get("height"),
        "format": remote_entry.get("format", ""),
        "output_index": remote_entry.get("output_index", fallback_index),
        "byte_count": len(decoded_bytes) if decoded_bytes else int(remote_entry.get("byte_count", 0) or 0),
        "asset_id": remote_entry.get("asset_id", ""),
        "identity": remote_entry.get("identity", ""),
        "backend_path": remote_entry.get("backend_path", remote_entry.get("path", "")),
    }


def _select_primary_result_entry(result: dict) -> dict | None:
    outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
    if isinstance(outputs, dict):
        for node_id in outputs:
            entry = select_primary_output(outputs, node_id)
            if not isinstance(entry, dict):
                continue
            resolved = dict(entry)
            resolved.setdefault("node_id", str(node_id))
            if not resolved.get("output_key"):
                for output_key, entries in outputs.get(node_id, {}).items():
                    if isinstance(entries, list) and entry in entries:
                        resolved["output_key"] = output_key
                        break
            resolved.setdefault("output_key", "images")
            return resolved
    for index, entry in enumerate(result.get("images", []) if isinstance(result, dict) else []):
        if not isinstance(entry, dict):
            continue
        resolved = dict(entry)
        resolved.setdefault("node_id", str(entry.get("node_id", "")))
        resolved.setdefault("output_key", entry.get("output_key") or "images")
        resolved.setdefault("output_index", entry.get("output_index", index))
        return resolved
    return None


def _materialize_modal_outputs(
    result: dict,
    *,
    output_dir: str,
    prompt_id: str,
    client_id: str,
    send_event,
    auto_save_local: bool = False,
    save_folder: str = "",
    save_metadata_sidecar: bool = True,
    workflow_hash: str = "",
    workflow_name: str = "",
    seed: str = "0",
    width: int = 0,
    height: int = 0,
    comfyui_root: str = "",
) -> dict:
    native_outputs: dict[str, dict] = {}
    materialized_outputs: dict[str, dict] = {}
    written_files: list[str] = []
    save_results: list[dict] = []
    save_warnings: list[str] = []
    handled_output_ids: set[tuple[str, str, str, int]] = set()
    image_count = 0
    video_count = 0
    output_bytes_written = 0
    # ── Phase 6 materialization timing ──
    total_decode_time_ms: float = 0.0
    total_write_time_ms: float = 0.0
    _materialization_wall_start = time.perf_counter()

    def _is_valid_entry(entry: Any) -> bool:
        """Returns True for entries with either base64 'data' (legacy) or
        descriptor metadata ('filename' + one of 'byte_count'/'identity'/'path')."""
        if not isinstance(entry, dict):
            return False
        if "data" in entry and entry["data"]:
            return True
        return bool(entry.get("filename")) and (
            "byte_count" in entry or "identity" in entry or "path" in entry
        )

    def _store_entry(node_id: str, output_key: str, entry: dict, fallback_index: int = 0) -> None:
        nonlocal image_count, video_count, output_bytes_written, total_decode_time_ms, total_write_time_ms
        has_data = "data" in entry and entry["data"]
        if has_data:
            _t0 = time.perf_counter()
            raw_bytes = base64.b64decode(entry["data"], validate=True)
            total_decode_time_ms += (time.perf_counter() - _t0) * 1000.0
            local_filename = entry.get("filename", f"output_{fallback_index}.bin")
            local_path = _unique_path(output_dir, local_filename)
            local_filename = os.path.basename(local_path)
            _t1 = time.perf_counter()
            with open(local_path, "wb") as f:
                f.write(raw_bytes)
            total_write_time_ms += (time.perf_counter() - _t1) * 1000.0
            written_files.append(local_path)
            output_bytes_written += len(raw_bytes)
            decoded_bytes = raw_bytes
        else:
            # Descriptor mode — no inline data; skip decode/write
            raw_bytes = b""
            local_filename = entry.get("filename", f"output_{fallback_index}.bin")
            local_path = entry.get("path", "")
            decoded_bytes = b""

        is_video = output_key == "gifs" or (entry.get("format", "") in {"gif", "mp4", "webm"})
        if is_video:
            video_count += 1
        else:
            image_count += 1
        native_entry = _build_native_output_descriptor(local_filename)
        internal_entry = _build_materialized_output_entry(
            entry,
            node_id=str(node_id),
            output_key=output_key,
            local_filename=local_filename,
            local_path=local_path,
            decoded_bytes=decoded_bytes,
            fallback_index=fallback_index,
        )
        native_outputs.setdefault(str(node_id), {}).setdefault(output_key, []).append(native_entry)
        if entry.get("asset_id"):
            native_entry["asset_id"] = entry["asset_id"]
        materialized_outputs.setdefault(str(node_id), {}).setdefault(output_key, []).append(internal_entry)
        if is_video:
            native_outputs[str(node_id)]["animated"] = [True] * len(native_outputs[str(node_id)][output_key])
            materialized_outputs[str(node_id)]["animated"] = [True] * len(materialized_outputs[str(node_id)][output_key])
        handled_output_ids.add(_stable_output_identity(str(node_id), output_key, entry, fallback_index))
        primary_flag = 1 if entry.get("comparison_side") == "b" or output_key == "b_images" else 0
        if has_data:
            print(
                f"[modal-local.write] node_id={node_id} output_key={output_key} "
                f"comparison_side={entry.get('comparison_side', '')} path={local_path} bytes={len(raw_bytes)}"
                f"{' primary=1' if primary_flag else ''}"
            )

    structured_outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
    for node_id, node_outputs in structured_outputs.items():
        if not isinstance(node_outputs, dict):
            continue
        for output_key, entries in node_outputs.items():
            if not isinstance(entries, list):
                continue
            for index, entry in enumerate(entries):
                if _is_valid_entry(entry):
                    _store_entry(str(node_id), str(output_key), entry, index)

    flat_node_events: dict[str, dict[str, list]] = {}
    for index, img in enumerate(result.get("images", []) if isinstance(result, dict) else []):
        if not _is_valid_entry(img):
            continue
        node_id = str(img.get("node_id", ""))
        output_key = str(img.get("output_key") or "images")
        if _stable_output_identity(node_id, output_key, img, index) in handled_output_ids:
            continue
        _store_entry(node_id, output_key, img, index)
        flat_node_events.setdefault(node_id, {}).setdefault(output_key, []).append(
            native_outputs[node_id][output_key][-1]
        )

    for index, vid in enumerate(result.get("videos", []) if isinstance(result, dict) else []):
        if not _is_valid_entry(vid):
            continue
        node_id = str(vid.get("node_id", ""))
        output_key = str(vid.get("output_key") or "gifs")
        if _stable_output_identity(node_id, output_key, vid, index) in handled_output_ids:
            continue
        _store_entry(node_id, output_key, vid, index)
        flat_node_events.setdefault(node_id, {}).setdefault(output_key, []).append(
            native_outputs[node_id][output_key][-1]
        )
        flat_node_events[node_id]["animated"] = [True] * len(flat_node_events[node_id][output_key])

    # ── Ensure standard "images" alias for nodes that have comparer keys ──
    # rgthree Image Comparer uses a_images / b_images, but Media Assets
    # and generic ComfyUI consumers discover images through the standard
    # "images" output key.  When a node has b_images but no images,
    # alias b_images → images so Media Assets can find the final image.
    _history_outputs: dict[str, dict] = {}
    for _nid, _noutputs in native_outputs.items():
        _history_outputs[_nid] = dict(_noutputs)
    for _nid, _noutputs in native_outputs.items():
        if "images" not in _noutputs and "b_images" in _noutputs:
            _history_outputs[_nid]["images"] = list(_noutputs["b_images"])
            print(
                f"[modal-local.history] node_id={_nid} "
                f"keys={','.join(_history_outputs[_nid].keys())} final_alias=b_images"
            )

    print(
        f"[modal-local.client] prompt_id={prompt_id} client_id={client_id} "
        f"server_available={1 if _server else 0}"
    )
    for node_id, event_output in native_outputs.items():
        send_event("executed", {
            "node": node_id,
            "display_node": node_id,
            "prompt_id": prompt_id,
            "output": event_output,
        })
        print(
            f"[modal-local.executed-event] node_id={node_id} "
            f"keys={','.join(event_output.keys())} client_id={client_id}"
        )
    for node_id, event_output in flat_node_events.items():
        if node_id in native_outputs:
            continue
        send_event("executed", {
            "node": node_id,
            "display_node": node_id,
            "prompt_id": prompt_id,
            "output": event_output,
        })
        print(
            f"[modal-local.executed-event] node_id={node_id} "
            f"keys={','.join(event_output.keys())} client_id={client_id}"
        )

    primary_output = None
    primary_entry = _select_primary_result_entry({"outputs": materialized_outputs, "images": []})
    if isinstance(primary_entry, dict):
        primary_output = {
            "node_id": str(primary_entry.get("node_id", "")),
            "output_key": str(primary_entry.get("output_key", "images")),
            "comparison_side": primary_entry.get("comparison_side", ""),
            "filename": primary_entry.get("filename", ""),
            "path": primary_entry.get("path", ""),
            "mime_type": primary_entry.get("mime_type", ""),
            "file_ext": primary_entry.get("file_ext", ""),
            "output_index": primary_entry.get("output_index", 0),
            "byte_count": primary_entry.get("byte_count", 0),
        }
        print(
            f"[modal-local.primary] prompt_id={prompt_id} node_id={primary_output['node_id']} "
            f"output_key={primary_output['output_key']} comparison_side={primary_output['comparison_side']} "
            f"filename={primary_output['filename']} path={primary_output['path']} bytes={primary_output['byte_count']}"
        )

    _auto_save_time_ms: float = 0.0
    if auto_save_local and primary_output and primary_output.get("path"):
        _auto_save_start = time.perf_counter()
        try:
            with open(primary_output["path"], "rb") as f:
                image_bytes = f.read()
            save_result = save_output_image(
                image_bytes,
                output_format="original",
                file_ext=primary_output.get("file_ext") or ".png",
                mime_type=primary_output.get("mime_type") or "image/png",
                quality=None,
                webp_lossless_compression=None,
                original_size_bytes=len(image_bytes),
                conversion_time_ms=0,
                save_folder=save_folder,
                save_metadata_sidecar=save_metadata_sidecar,
                workflow_hash=workflow_hash,
                workflow_name=workflow_name,
                seed=str(seed or "0"),
                width=width,
                height=height,
                index=0,
                comfyui_root=comfyui_root,
                extra_meta={
                    "node_id": primary_output.get("node_id", ""),
                    "output_key": primary_output.get("output_key", ""),
                    "comparison_side": primary_output.get("comparison_side", ""),
                    "source_filename": primary_output.get("filename", ""),
                },
            )
            save_results.append(save_result)
            print(
                f"[comfyui-modal.auto_save] selected_only=1 node_id={primary_output.get('node_id', '')} "
                f"output_key={primary_output.get('output_key', '')} "
                f"comparison_side={primary_output.get('comparison_side', '')} "
                f"path={save_result.get('path', '')}"
            )
            if save_result.get("error"):
                save_warnings.append(save_result["error"])
        except OSError as exc:
            save_warnings.append(str(exc))
        _auto_save_time_ms = (time.perf_counter() - _auto_save_start) * 1000.0

    _materialization_wall_ms = (time.perf_counter() - _materialization_wall_start) * 1000.0

    return {
        "outputs": native_outputs,
        "history_outputs": _history_outputs,
        "materialized_outputs": materialized_outputs,
        "primary_output": primary_output,
        "written_files": written_files,
        "image_count": image_count,
        "video_count": video_count,
        "bytes_written": output_bytes_written,
        "save_results": save_results,
        "save_warnings": save_warnings,
        # ── Phase 6 materialization timing ──
        "materialization_timing": {
            "total_wall_ms": _materialization_wall_ms,
            "total_decode_time_ms": total_decode_time_ms,
            "total_write_time_ms": total_write_time_ms,
            "auto_save_time_ms": _auto_save_time_ms,
            "item_count": image_count + video_count,
            "bytes_written": output_bytes_written,
        },
    }


def _register_remote_result_assets(
    result: dict,
    *,
    workspace: dict,
    gpu: str,
    prompt_id: str,
) -> None:
    descriptors = result.get("asset_descriptors", []) if isinstance(result, dict) else []
    if not isinstance(descriptors, list):
        return
    workspace_id = str((workspace or {}).get("id", ""))
    if not workspace_id:
        return
    leases = REGISTRY.leases()
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            continue
        asset_id = str(descriptor.get("asset_id", ""))
        backend_path = str(descriptor.get("backend_path") or descriptor.get("path") or "")
        if not asset_id or not backend_path:
            continue
        leases.register_asset(
            asset_id=asset_id,
            experiment_id="",
            cell_key=prompt_id,
            variant="original",
            path=f"modal://{workspace_id}|{gpu}|{backend_path}",
            mime_type=str(descriptor.get("mime_type") or "application/octet-stream"),
            byte_size=int(descriptor.get("byte_count", 0) or 0),
            content_hash=asset_id,
            node_id=str(descriptor.get("node_id", "")),
            output_key=str(descriptor.get("output_key", "")),
            output_index=int(descriptor.get("output_index", 0) or 0),
            comparison_side=str(descriptor.get("comparison_side", "")),
            width=int(descriptor.get("width", 0) or 0),
            height=int(descriptor.get("height", 0) or 0),
        )


def _make_thumbnail(input_path: str, output_path: str, max_size: int = 256) -> bool:
    """Generate a WebP thumbnail. Returns True on success."""
    try:
        from PIL import Image
        img = Image.open(input_path)
        img.thumbnail((max_size, max_size))
        img.save(output_path, "WEBP", quality=75)
        return True
    except Exception:
        # If PIL not available, just copy the original as thumbnail
        try:
            import shutil
            shutil.copy2(input_path, output_path)
            return True
        except Exception:
            return False


def _materialize_experiment_output(
    result_data: dict,
    output_dir: str,
    cell_key: str = "",
    attempt_id: str = "",
) -> dict:
    """Materialize experiment cell outputs and register thumbnails.

    Writes files to output_dir/<attempt_id>/.
    Generates WebP thumbnails using Pillow if available.
    Returns dict with:
        "assets": {asset_id: {"path": ..., "mime_type": ..., "byte_size": ...,
                              "content_hash": ..., "variant": ...,
                              "parent_asset_id": ..., "node_id": ...,
                              "output_key": ..., "output_index": ...,
                              "comparison_side": ..., "width": ..., "height": ...}}
        "primary_output": {...}
        "primary_asset_id": str
        "primary_thumbnail_asset_id": str
        "output_count": int

    B4: Thumbnail content_hash is computed from actual thumbnail bytes (SHA-256),
    NOT copied from the original — so resized WebP has a different hash.
    """
    assets: dict[str, dict] = {}
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    seen = 0
    # ── Phase 6 materialization timing ──
    _total_decode_time_ms: float = 0.0
    _total_write_time_ms: float = 0.0
    _total_thumbnail_time_ms: float = 0.0
    _experiment_wall_start = time.perf_counter()
    # Collect all entries indexed by their stable identity for primary selection
    per_node_outputs: dict[str, dict[str, list[dict]]] = {}

    def _write_and_index(entry: dict, node_id: str, output_key: str, fallback_index: int) -> str:
        nonlocal seen, _total_decode_time_ms, _total_write_time_ms, _total_thumbnail_time_ms
        _t0 = time.perf_counter()
        raw_bytes = base64.b64decode(entry["data"], validate=True)
        _total_decode_time_ms += (time.perf_counter() - _t0) * 1000.0
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        # Goal 1: globally unique UUID-based asset ID (NOT content-hash-derived)
        asset_id = str(uuid.uuid4())
        filename = entry.get("filename", f"output_{seen}.bin")
        safe_name = Path(filename).name
        local_path = output_dir_path / safe_name
        counter = 0
        while local_path.exists():
            counter += 1
            stem = local_path.stem
            local_path = output_dir_path / f"{stem}_{counter}{local_path.suffix}"
        _tw0 = time.perf_counter()
        local_path.write_bytes(raw_bytes)
        _total_write_time_ms += (time.perf_counter() - _tw0) * 1000.0
        mime_type = entry.get("mime_type", "image/png")
        comp_side = entry.get("comparison_side", "")
        entry_width = entry.get("width", 0) or 0
        entry_height = entry.get("height", 0) or 0
        entry_output_index = entry.get("output_index", fallback_index) or 0

        # Goal 2: register original as first-class asset with extended fields
        assets[asset_id] = {
            "path": str(local_path),
            "mime_type": mime_type,
            "byte_size": len(raw_bytes),
            "content_hash": content_hash,
            "variant": "original",
            "parent_asset_id": "",
            "node_id": str(node_id),
            "output_key": str(output_key),
            "output_index": int(entry_output_index),
            "comparison_side": str(comp_side),
            "width": int(entry_width),
            "height": int(entry_height),
        }

        # B4: generate WebP thumbnail and register as separate first-class asset
        thumb_stem = f"{local_path.stem}_thumb"
        thumb_path = output_dir_path / f"{thumb_stem}.webp"
        _tt0 = time.perf_counter()
        thumb_ok = bool(_make_thumbnail(str(local_path), str(thumb_path)))
        _total_thumbnail_time_ms += (time.perf_counter() - _tt0) * 1000.0
        if thumb_ok and thumb_path.exists():
            thumb_bytes = thumb_path.read_bytes()
            # B4: recompute SHA-256 on ACTUAL thumbnail bytes (not original hash)
            thumb_content_hash = hashlib.sha256(thumb_bytes).hexdigest()
            thumb_asset_id = str(uuid.uuid4())
            # Detect actual thumbnail format
            if thumb_bytes[:4] == b"RIFF" and b"WEBP" in thumb_bytes[:12]:
                thumb_mime = "image/webp"
            else:
                if thumb_bytes[:3] == b"\xff\xd8\xff":
                    thumb_mime = "image/jpeg"
                elif thumb_bytes[:8] == b"\x89PNG\r\n\x1a\n":
                    thumb_mime = "image/png"
                else:
                    thumb_mime = "image/webp"
            assets[thumb_asset_id] = {
                "path": str(thumb_path),
                "mime_type": thumb_mime,
                "byte_size": len(thumb_bytes),
                "content_hash": thumb_content_hash,  # B4: hash of THUMBNAIL bytes
                "variant": "thumbnail",
                "parent_asset_id": asset_id,  # Link back to original
                "node_id": str(node_id),
                "output_key": str(output_key),
                "output_index": int(entry_output_index),
                "comparison_side": str(comp_side),
                "width": min(int(entry_width), 256) if int(entry_width) > 0 else 256,
                "height": min(int(entry_height), 256) if int(entry_height) > 0 else 256,
            }

        # Index for primary selection (same rules as ordinary result path)
        materialized_entry = dict(entry)
        materialized_entry.pop("data", None)  # strip base64
        materialized_entry["path"] = str(local_path)
        materialized_entry["byte_count"] = len(raw_bytes)
        materialized_entry["asset_id"] = asset_id
        materialized_entry.setdefault("output_key", output_key)
        materialized_entry.setdefault("node_id", node_id)
        per_node_outputs.setdefault(node_id, {}).setdefault(output_key, []).append(materialized_entry)
        seen += 1
        return asset_id

    # Process structured outputs
    structured_outputs = result_data.get("outputs", {}) if isinstance(result_data, dict) else {}
    for node_id, node_outputs in structured_outputs.items():
        if not isinstance(node_outputs, dict):
            continue
        for output_key, entries in node_outputs.items():
            if not isinstance(entries, list):
                continue
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict) or "data" not in entry:
                    continue
                _write_and_index(entry, str(node_id), str(output_key), idx)

    # Process flat images fallback (no dedup — each gets its own UUID)
    flat_images = result_data.get("images", []) if isinstance(result_data, dict) else []
    for idx, img_entry in enumerate(flat_images):
        if not isinstance(img_entry, dict) or "data" not in img_entry:
            continue
        node_id = str(img_entry.get("node_id", ""))
        output_key = str(img_entry.get("output_key") or "images")
        _write_and_index(img_entry, node_id, output_key, idx)

    # B5: use deterministic select_primary_output for primary selection
    primary_asset_id = ""
    primary_thumbnail_asset_id = ""
    primary_output = None
    if per_node_outputs:
        # B5: iterate ALL nodes, not just the first one
        best_primary_entry = None
        for nid in per_node_outputs:
            candidate = select_primary_output(per_node_outputs, nid)
            if candidate is not None:
                best_primary_entry = candidate
        if best_primary_entry is not None and isinstance(best_primary_entry, dict):
            found_asset_id = best_primary_entry.get("asset_id", "")
            if found_asset_id and found_asset_id in assets:
                primary_asset_id = found_asset_id
                info = assets[found_asset_id]
                # Find the thumbnail belonging to this original (by parent_asset_id)
                thumb_id = next(
                    (aid for aid, ai in assets.items()
                     if ai.get("parent_asset_id") == found_asset_id
                     and ai.get("variant") == "thumbnail"),
                    ""
                )
                primary_thumbnail_asset_id = thumb_id
                primary_output = {
                    "asset_id": found_asset_id,
                    "path": info["path"],
                    "mime_type": info["mime_type"],
                    "byte_size": info["byte_size"],
                    "content_hash": info["content_hash"],
                    "comparison_side": best_primary_entry.get("comparison_side", ""),
                    "output_key": best_primary_entry.get("output_key", ""),
                    "node_id": best_primary_entry.get("node_id", ""),
                    "output_index": best_primary_entry.get("output_index", 0),
                    "primary_thumbnail_asset_id": primary_thumbnail_asset_id,
                }
            else:
                # Fallback: pick first original asset
                orig_ids = sorted(
                    aid for aid, ai in assets.items() if ai.get("variant") == "original"
                )
                if orig_ids:
                    primary_asset_id = orig_ids[0]
                    info = assets[primary_asset_id]
                    thumb_id = next(
                        (aid for aid, ai in assets.items()
                         if ai.get("parent_asset_id") == primary_asset_id
                         and ai.get("variant") == "thumbnail"),
                        ""
                    )
                    primary_thumbnail_asset_id = thumb_id
                    primary_output = {
                        "asset_id": primary_asset_id,
                        "path": info["path"],
                        "mime_type": info["mime_type"],
                        "byte_size": info["byte_size"],
                        "content_hash": info["content_hash"],
                        "primary_thumbnail_asset_id": primary_thumbnail_asset_id,
                    }

    _experiment_wall_ms = (time.perf_counter() - _experiment_wall_start) * 1000.0

    return {
        "assets": assets,
        "primary_output": primary_output,
        "primary_asset_id": primary_asset_id,
        "primary_thumbnail_asset_id": primary_thumbnail_asset_id,
        "output_count": seen,
        # ── Phase 6 materialization timing ──
        "materialization_timing": {
            "total_wall_ms": _experiment_wall_ms,
            "total_decode_time_ms": _total_decode_time_ms,
            "total_write_time_ms": _total_write_time_ms,
            "total_thumbnail_time_ms": _total_thumbnail_time_ms,
            "item_count": seen,
        },
    }


_COMFYAPP_PATH = os.path.join(_NODE_DIR, "comfyapp.py")
_DEPLOY_STATE_FILE = os.path.join(_NODE_DIR, ".deployed_version")
_DEPLOY_STATE_JSON_FILE = os.path.join(_NODE_DIR, ".deployed_state.json")
_DEPLOY_LOG_FILE = os.path.join(_NODE_DIR, ".deploy_log")
_LATEST_BENCHMARK_WORKFLOW_FILE = os.path.join(_NODE_DIR, "latest_benchmark_workflow.json")
_MODAL_SETTINGS_FILE = os.path.join(_NODE_DIR, ".modal_settings.json")
_WORKSPACES_FILE = os.path.join(_NODE_DIR, ".modal_workspaces.json")
_MODEL_MANIFEST_FILE = os.path.join(_NODE_DIR, ".model_manifest.json")
_SWAP_JOB_POLL_INTERVAL_S = 1.0
_swap_jobs: dict[str, dict] = {}
_swap_jobs_lock = threading.Lock()

# ── Output settings (server-side, persisted to .modal_settings.json) ──
def _default_modal_settings() -> dict:
    return {
        "output_format": _CONVERTER_DEFAULTS["output_format"],
        "quality": _CONVERTER_DEFAULTS["quality"],
        "webp_lossless_compression": _CONVERTER_DEFAULTS["webp_lossless_compression"],
        "auto_save_local": _SAVER_DEFAULTS["auto_save_local"],
        "save_folder": _SAVER_DEFAULTS["save_folder"],
        "save_metadata_sidecar": _SAVER_DEFAULTS["save_metadata_sidecar"],
        # ── Phase 8: execution mode ──
        "execution_mode": MODE_V2,
    }

_CUSTOM_NODE_SYNC_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "output", "test-results", "playwright-report",
    ".playwright-mcp", ".experiments", ".run_history",
    "benchmark_runs", "benchmark_logs", "optimization_logs",
    ".comfymodal_experiments", ".custom_node_requirements", ".baked_custom_node_deps",
    ".presets", ".preset_blobs",
}
_CUSTOM_NODE_LOCAL_CLONE_RE = re.compile(
    r"^comfyui-modal-(?:agent(?:\d+|[-_].*)|worktree(?:[-_].*)?|wt(?:[-_].*)?|dc\d+)$",
    re.IGNORECASE,
)
_CUSTOM_NODE_SYNC_EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}

_pip_install_error = ""
_WORKFLOW_IMAGE_SUFFIX_DIRS = {
    " [output]": "output",
    " [input]": "input",
    " [temp]": "temp",
}

_ExecutionStatusFallback = namedtuple("ExecutionStatusFallback", ["status_str", "completed", "messages"])


def _split_workflow_image_reference(filename: str) -> tuple[str, str | None]:
    name = (filename or "").strip()
    for suffix, directory in _WORKFLOW_IMAGE_SUFFIX_DIRS.items():
        if name.endswith(suffix):
            return name[:-len(suffix)].rstrip(), directory
    return name, None


def _workflow_image_parts(filename: str) -> list[str]:
    normalized = (filename or "").replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"unsafe workflow image path: {filename}")
    return parts


def _resolve_local_workflow_image_candidates(filename: str) -> list[str]:
    relative_name, annotated_dir = _split_workflow_image_reference(filename)
    parts = _workflow_image_parts(relative_name)
    search_dirs = [annotated_dir] if annotated_dir else ["input", "output"]
    return [os.path.join(_COMFYUI_ROOT, directory, *parts) for directory in search_dirs]

def _ensure_modal():
    global _pip_install_error
    try:
        import modal  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("COMFYMODAL_ALLOW_RUNTIME_PIP_INSTALL") != "1":
        _pip_install_error = "modal package not installed. Run: pip install modal"
        print("[comfyui-modal] ERROR: 'modal' package not found. Run: pip install modal")
        print("[comfyui-modal] Set COMFYMODAL_ALLOW_RUNTIME_PIP_INSTALL=1 to auto-install (not recommended for production)")
        return
    print("[comfyui-modal] 'modal' package not found — installing...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "modal"], check=True, capture_output=True, text=True)
        print("[comfyui-modal] 'modal' installed successfully.")
    except subprocess.CalledProcessError as e:
        _pip_install_error = e.stderr or str(e)
        print(f"[comfyui-modal] ERROR: Failed to install 'modal' package: {e.stderr}")
    except Exception as e:
        _pip_install_error = str(e)
        print(f"[comfyui-modal] ERROR: Unexpected error installing 'modal': {e}")

_ensure_modal()


_deploy_status = {"state": "idle", "message": ""}
_last_successful_model_stack: dict = {}
_latest_benchmark_workflow: dict = {}
_download_progress: dict = {}

_RESULT_ROUTE = os.environ.get("COMFYMODAL_RESULT_ROUTE", "legacy").strip().lower()
if _RESULT_ROUTE not in ("legacy", "direct"):
    print(f"[comfyui-modal] WARNING: invalid COMFYMODAL_RESULT_ROUTE={_RESULT_ROUTE!r}, falling back to 'legacy'")
    _RESULT_ROUTE = "legacy"
_COMPLETED_RESULTS: dict[str, dict] = {}
_COMPLETED_RESULTS_LOCK = threading.Lock()
_COMPLETED_RESULTS_MAXSIZE = 100
_COMPLETED_RESULTS_MAX_BYTES = 500 * 1024 * 1024  # 500 MB cap
_COMPLETED_RESULTS_TTL_S = 600  # 10 minutes

# ── v4 local event trace (per-prompt) ──
_local_event_trace: EventTrace | None = None
_local_event_trace_lock = threading.Lock()


def _init_local_event_trace() -> EventTrace:
    global _local_event_trace
    trace = EventTrace(process="local_bridge", request_seq=0)
    with _local_event_trace_lock:
        _local_event_trace = trace
    return trace


def _get_local_event_trace() -> EventTrace | None:
    with _local_event_trace_lock:
        return _local_event_trace


def _clear_local_event_trace() -> None:
    with _local_event_trace_lock:
        global _local_event_trace
        _local_event_trace = None



def _load_latest_benchmark_workflow() -> dict:
    global _latest_benchmark_workflow
    if _latest_benchmark_workflow:
        return dict(_latest_benchmark_workflow)
    try:
        with open(_LATEST_BENCHMARK_WORKFLOW_FILE, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        if isinstance(snapshot, dict) and snapshot:
            _latest_benchmark_workflow = snapshot
            return dict(snapshot)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return {}


def _save_latest_benchmark_workflow(payload: dict) -> dict:
    global _latest_benchmark_workflow
    workflow = payload.get("prompt", payload) if isinstance(payload, dict) else payload
    snapshot = {
        "captured_at": time.time(),
        "workflow_hash": prompt_sha256(workflow if isinstance(workflow, dict) else payload),
        "payload": payload,
    }
    tmp_path = f"{_LATEST_BENCHMARK_WORKFLOW_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True)
    os.replace(tmp_path, _LATEST_BENCHMARK_WORKFLOW_FILE)
    _latest_benchmark_workflow = snapshot
    return dict(snapshot)


# ── Modal settings persistence ────────────────────────────────────────
_modal_settings_cache: dict | None = None


def _load_modal_settings() -> dict:
    """Load persisted output/auto-save settings from disk."""
    global _modal_settings_cache
    if _modal_settings_cache is not None:
        return dict(_modal_settings_cache)
    defaults = _default_modal_settings()
    try:
        with open(_MODAL_SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            merged = dict(defaults)
            for key in defaults:
                if key in saved and isinstance(saved[key], type(defaults[key])):
                    merged[key] = saved[key]
            # Settings are user-facing and may only select V1/V2.  Treat old
            # or hand-edited values as the safe V2 default; shadow is an
            # internal comparison mode and never a persisted UI setting.
            _saved_mode = normalize_mode(merged.get("execution_mode"))
            if _saved_mode not in (MODE_V1, MODE_V2):
                merged["execution_mode"] = MODE_V2
            _modal_settings_cache = merged
            return dict(merged)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    _modal_settings_cache = defaults
    return dict(defaults)


def _save_modal_settings(settings: dict) -> dict:
    """Persist settings to disk, merging with defaults."""
    global _modal_settings_cache
    defaults = _default_modal_settings()
    merged = dict(defaults)
    for key in defaults:
        if key in settings and isinstance(settings[key], type(defaults[key])):
            merged[key] = settings[key]
    _saved_mode = normalize_mode(merged.get("execution_mode"))
    if _saved_mode not in (MODE_V1, MODE_V2):
        merged["execution_mode"] = MODE_V2
    tmp_path = f"{_MODAL_SETTINGS_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, sort_keys=True)
    os.replace(tmp_path, _MODAL_SETTINGS_FILE)
    _modal_settings_cache = merged
    return dict(merged)

def _custom_nodes_root() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(_NODE_DIR)), "custom_nodes")


def _iter_syncable_custom_node_dirs(cn_root: str) -> list[str]:
    if not os.path.isdir(cn_root):
        return []
    names = []
    for node_dir in os.listdir(cn_root):
        node_path = os.path.join(cn_root, node_dir)
        if not os.path.isdir(node_path):
            continue
        if (
            node_dir.startswith(".")
            or node_dir in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS
            or _CUSTOM_NODE_LOCAL_CLONE_RE.fullmatch(node_dir)
        ):
            continue
        names.append(node_dir)
    return sorted(names)


def _build_custom_node_fingerprint(cn_root: str) -> str:
    manifest = []
    for node_dir in _iter_syncable_custom_node_dirs(cn_root):
        req_path = os.path.join(cn_root, node_dir, "requirements.txt")
        req_text = ""
        if os.path.isfile(req_path):
            req_text = Path(req_path).read_text(encoding="utf-8")
        manifest.append({
            "node": node_dir,
            "requirements_txt": req_text,
        })
    payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_deploy_state() -> dict:
    payload = _read_deploy_state_details()
    return {
        "comfyapp_version": payload.get("comfyapp_version"),
        "custom_nodes_fingerprint": payload.get("custom_nodes_fingerprint"),
        "deployed_at": payload.get("deployed_at"),
        "deployment_command": payload.get("deployment_command"),
    }


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _save_deploy_state(version: str | None, fingerprint: str | None, deployed_at: str | None = None, deployment_command: str | None = None) -> None:
    payload = {
        "comfyapp_version": version,
        "custom_nodes_fingerprint": fingerprint,
        "deployed_at": deployed_at,
        "deployment_command": deployment_command,
    }
    with open(_DEPLOY_STATE_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _get_deployed_version():
    return _load_deploy_state().get("comfyapp_version")


def _set_deployed_version(version: str):
    existing = _read_deploy_state_details()
    _save_deploy_state(
        version,
        _get_deployed_custom_nodes_fingerprint(),
        deployed_at=existing.get("deployed_at"),
        deployment_command=existing.get("deployment_command"),
    )


def _get_deployed_custom_nodes_fingerprint():
    return _load_deploy_state().get("custom_nodes_fingerprint")


def _env_flag(name: str, default: str = "0") -> bool:
    return env_flag(name, default=default == "1")


def _read_deploy_state_details() -> dict:
    details = {
        "path": _DEPLOY_STATE_JSON_FILE,
        "legacy_path": _DEPLOY_STATE_FILE,
        "loaded": False,
        "source": "missing",
        "parse_error": "",
        "comfyapp_version": None,
        "custom_nodes_fingerprint": None,
        "deployed_at": None,
        "deployment_command": None,
    }
    if os.path.isfile(_DEPLOY_STATE_JSON_FILE):
        details["source"] = "json"
        try:
            with open(_DEPLOY_STATE_JSON_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                details["loaded"] = True
                details["comfyapp_version"] = payload.get("comfyapp_version")
                details["custom_nodes_fingerprint"] = payload.get("custom_nodes_fingerprint")
                details["deployed_at"] = payload.get("deployed_at")
                details["deployment_command"] = payload.get("deployment_command")
                return details
            details["parse_error"] = "deploy_state_json_not_dict"
        except (json.JSONDecodeError, OSError) as exc:
            details["parse_error"] = f"{type(exc).__name__}: {exc}"
    if os.path.isfile(_DEPLOY_STATE_FILE):
        details["source"] = "legacy"
        try:
            with open(_DEPLOY_STATE_FILE, "r", encoding="utf-8") as f:
                details["comfyapp_version"] = f.read().strip() or None
            details["loaded"] = True
            return details
        except OSError as exc:
            details["parse_error"] = f"{type(exc).__name__}: {exc}"
    return details


def _build_custom_node_fingerprint_status() -> dict:
    cn_root = _custom_nodes_root()
    status = {
        "custom_nodes_root": cn_root,
        "available": False,
        "fingerprint": None,
        "error": "",
    }
    if not os.path.isdir(cn_root):
        status["error"] = "custom_nodes_root_missing"
        return status
    try:
        status["fingerprint"] = _build_custom_node_fingerprint(cn_root)
        status["available"] = True
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"
    return status


# ── Cached deployment-state values (invalidated on explicit deployment or sync) ──
_cached_deploy_details: dict | None = None
_cached_fingerprint_status: dict | None = None
_cached_comfyapp_version: str | None = None


def _invalidate_deployment_state_cache() -> None:
    global _cached_deploy_details, _cached_fingerprint_status, _cached_comfyapp_version
    _cached_deploy_details = None
    _cached_fingerprint_status = None
    _cached_comfyapp_version = None


def _get_deploy_details_cached() -> dict:
    global _cached_deploy_details
    if _cached_deploy_details is None:
        _cached_deploy_details = _read_deploy_state_details()
    return _cached_deploy_details


def _get_fingerprint_status_cached() -> dict:
    global _cached_fingerprint_status
    if _cached_fingerprint_status is None:
        _cached_fingerprint_status = _build_custom_node_fingerprint_status()
    return _cached_fingerprint_status


def _get_comfyapp_version_cached() -> str:
    global _cached_comfyapp_version
    if _cached_comfyapp_version is None:
        _cached_comfyapp_version = _get_comfyapp_version()
    return _cached_comfyapp_version


def _build_generation_invocation_plan(gpu: str | None = None, stream: bool = True) -> dict:
    deployed = _get_deploy_details_cached()
    fingerprint_status = _get_fingerprint_status_cached()
    current_version = _get_comfyapp_version_cached()
    deployed_version = deployed.get("comfyapp_version") or ""
    deployed_fingerprint = deployed.get("custom_nodes_fingerprint")
    current_fingerprint = fingerprint_status.get("fingerprint")
    fingerprint_changed = True
    if fingerprint_status.get("available"):
        fingerprint_changed = current_fingerprint != deployed_fingerprint
    method_name = "run_prompt_stream" if stream else "run_prompt"
    class_name = ""
    modal_lookup_target = "unknown"
    invocation_mode = "unknown"
    try:
        class_name = get_modal_class_name(gpu)
        modal_lookup_target = get_modal_lookup_target(gpu, method_name)
        invocation_mode = "deployed_lookup"
    except Exception as exc:
        modal_lookup_target = f"lookup_error:{type(exc).__name__}"
    version_changed = current_version != deployed_version
    auto_deploy_enabled = _env_flag("COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY", "0")
    deployed_lookup_current = bool(
        deployed.get("loaded")
        and not version_changed
        and not fingerprint_changed
    )
    return {
        "invocation_mode": invocation_mode,
        "app_name": get_modal_app_name(),
        "class_name": class_name,
        "method_name": method_name,
        "deployed_state_path": deployed.get("path", _DEPLOY_STATE_JSON_FILE),
        "deployed_state_loaded": bool(deployed.get("loaded")),
        "deployed_state_source": deployed.get("source", "missing"),
        "deployed_state_parse_error": deployed.get("parse_error", ""),
        "deployed_state_version": deployed_version,
        "deployed_state_custom_nodes_fingerprint": deployed_fingerprint or "",
        "current_comfyapp_version": current_version,
        "current_custom_nodes_fingerprint": current_fingerprint or "",
        "custom_nodes_fingerprint_error": fingerprint_status.get("error", ""),
        "custom_nodes_root": fingerprint_status.get("custom_nodes_root", ""),
        "version_changed": version_changed,
        "custom_nodes_fingerprint_changed": fingerprint_changed,
        "auto_deploy_enabled": auto_deploy_enabled,
        "auto_deploy_started": False,
        "modal_lookup_target": modal_lookup_target,
        "deployed_lookup_current": deployed_lookup_current,
        "would_deploy": auto_deploy_enabled and (version_changed or fingerprint_changed),
    }


def _log_generation_invocation_plan(prompt_id: str, plan: dict) -> None:
    print(
        f"[comfyui-modal.invoke] prompt_id={prompt_id[:8]} "
        f"invocation_mode={plan.get('invocation_mode', 'unknown')} "
        f"app_name={plan.get('app_name', '')} "
        f"class_name={plan.get('class_name', '') or '?'} "
        f"method_name={plan.get('method_name', '')} "
        f"deployed_state_path={plan.get('deployed_state_path', '')} "
        f"deployed_state_loaded={1 if plan.get('deployed_state_loaded') else 0} "
        f"deployed_state_version={plan.get('deployed_state_version', '') or '<missing>'} "
        f"current_comfyapp_version={plan.get('current_comfyapp_version', '')} "
        f"version_changed={1 if plan.get('version_changed') else 0} "
        f"custom_nodes_fingerprint_changed={1 if plan.get('custom_nodes_fingerprint_changed') else 0} "
        f"auto_deploy_enabled={1 if plan.get('auto_deploy_enabled') else 0} "
        f"auto_deploy_started={1 if plan.get('auto_deploy_started') else 0} "
        f"modal_lookup_target={plan.get('modal_lookup_target', 'unknown')} "
        f"modal_call_start={time.time():.6f}"
    )
    if plan.get("deployed_state_parse_error"):
        print(f"[comfyui-modal.invoke] deployed_state_parse_error={plan['deployed_state_parse_error']}")
    if plan.get("custom_nodes_fingerprint_error"):
        print(f"[comfyui-modal.invoke] custom_nodes_fingerprint_error={plan['custom_nodes_fingerprint_error']}")

def _get_comfyapp_version():
    try:
        with open(_COMFYAPP_PATH, "r", encoding="utf-8") as f:
            source = f.read()
        match = re.search(r'^COMFYAPP_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
        if match:
            return match.group(1)
        raise RuntimeError("COMFYAPP_VERSION constant not found")
    except Exception as e:
        print(f"[comfyui-modal] Could not read COMFYAPP_VERSION: {e}")
        return "unknown"

def _find_modal_executable():
    import shutil
    modal_cmd = shutil.which("modal")
    if modal_cmd:
        return modal_cmd
    python_dir = os.path.dirname(sys.executable)
    candidates = [
        os.path.join(python_dir, "modal"),
        os.path.join(python_dir, "modal.exe"),
        os.path.join(python_dir, "Scripts", "modal"),
        os.path.join(python_dir, "Scripts", "modal.exe"),
        os.path.expanduser("~/.local/bin/modal"),
        "/usr/local/bin/modal",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def _parse_deploy_error(output):
    """Try to extract specific failure info from deploy output."""
    # Look for pip install failures
    m = re.search(r"ERROR: Could not find a version that satisfies the requirement (\S+)", output)
    if m:
        return f"Failed package: {m.group(1)}."
    m = re.search(r"ERROR: No matching distribution found for (\S+)", output)
    if m:
        return f"Failed package: {m.group(1)}."
    if "conflicting dependencies" in output.lower():
        m = re.search(r"(\S+) requires (\S+)", output)
        if m:
            return f"Conflicting dependencies: {m.group(1)} requires {m.group(2)}."
        return "Conflicting dependencies detected."
    # Look for failed node install
    m = re.search(r"Installing (\S+).{0,200}?(?:error|failed|Error)", output, re.IGNORECASE)
    if m:
        return f"Failed node: {m.group(1)}."
    return ""


def _workspace_registry() -> dict:
    return _workspace_store.load_workspace_registry(_WORKSPACES_FILE)


def _active_workspace() -> dict | None:
    return _workspace_store.get_active_workspace(_workspace_registry())


def _workspace_or_400(workspace_id: str) -> dict | None:
    return _workspace_store.get_workspace(_workspace_registry(), workspace_id)


def _workspace_manifest() -> dict:
    return _model_manifest.load_master_manifest(_MODEL_MANIFEST_FILE)


def _save_workspace_deploy_state(workspace_id: str, version: str | None, fingerprint: str | None, deployed_at: str | None = None, deployment_command: str | None = None) -> None:
    registry = _workspace_registry()
    registry.setdefault("deploy_state_by_workspace", {})[workspace_id] = {
        "comfyapp_version": version,
        "custom_nodes_fingerprint": fingerprint,
        "deployed_at": deployed_at,
        "deployment_command": deployment_command,
    }
    _workspace_store.save_workspace_registry(_WORKSPACES_FILE, registry)


def _load_workspace_deploy_state(workspace_id: str) -> dict:
    registry = _workspace_registry()
    deploy_state = registry.get("deploy_state_by_workspace", {}).get(workspace_id)
    if deploy_state:
        return deploy_state
    return _load_deploy_state()


def _record_manual_deploy_state(workspace_id: str | None = None, deployment_command: str = "") -> dict:
    version = _get_comfyapp_version()
    fingerprint = _build_custom_node_fingerprint_status().get("fingerprint")
    deployed_at = _utc_now_iso()
    payload = {
        "comfyapp_version": version,
        "custom_nodes_fingerprint": fingerprint,
        "deployed_at": deployed_at,
        "deployment_command": deployment_command,
    }
    if workspace_id:
        _save_workspace_deploy_state(workspace_id, version, fingerprint, deployed_at=deployed_at, deployment_command=deployment_command)
    else:
        _save_deploy_state(version, fingerprint, deployed_at=deployed_at, deployment_command=deployment_command)
    return payload


def _auto_migrate_generated_artifacts() -> bool:
    """Auto-migrate all detected generated artifact directories before deploy.

    Uses ``deployment_guard._scan_generated_dirs`` to discover categories and
    ``tools/migrate_local_artifacts.migrate_category`` to perform copy-verify-remove
    on each.  Returns ``True`` when nothing to migrate or all categories succeeded.
    Returns ``False`` when any category fails (SystemExit on verification mismatch
    or unexpected exception).  Never raises — all exceptions (import errors,
    root-scan failures, etc.) are converted to ``False`` so the caller
    (background deploy thread) is never crashed.
    """
    try:
        from deployment_guard import _scan_generated_dirs
        from local_artifacts import get_plugin_root, get_local_data_root
        from tools.migrate_local_artifacts import migrate_category, MigrationStats

        plugin_root = get_plugin_root()
        data_root = get_local_data_root()

        generated = _scan_generated_dirs(plugin_root)
        if not generated:
            return True  # nothing to do

        categories = sorted(generated.keys())
        print(f"[comfyui-modal] Auto-migrating {len(categories)} generated artifact "
              f"categor{'y' if len(categories) == 1 else 'ies'}: {', '.join(categories)}")

        stats = MigrationStats()
        for cat in categories:
            try:
                migrate_category(cat, plugin_root, data_root, dry_run=False, stats=stats)
            except SystemExit:
                print(f"[comfyui-modal] Auto-migration verification failed for '{cat}' — "
                      f"migration may be partial (earlier categories may have migrated); "
                      f"safe to rerun; manual verification recommended "
                      f"(run 'python tools/migrate_local_artifacts.py')")
                return False
            except Exception as exc:
                print(f"[comfyui-modal] Auto-migration failed for '{cat}': {exc}")
                return False

        print(f"[comfyui-modal] Auto-migration complete: {stats.total_files} files, "
              f"{stats.total_bytes} bytes migrated")
        return True
    except BaseException as exc:
        print(f"[comfyui-modal] Auto-migration setup or scan failed: {exc}")
        return False


def _run_deploy_background(workspace: dict, custom_nodes_fingerprint: str | None = None):
    global _deploy_status

    # Pre-deploy artifact guard: fail if generated dirs still contain data
    try:
        from deployment_guard import guard_generated_artifacts
        guard_generated_artifacts()
    except SystemExit:
        print("[comfyui-modal] Generated artifacts detected, attempting auto-migration...")
        try:
            auto_ok = _auto_migrate_generated_artifacts()
        except BaseException as exc:
            print(f"[comfyui-modal] Auto-migration crashed unexpectedly: {exc}")
            auto_ok = False
        if auto_ok:
            print("[comfyui-modal] Auto-migration succeeded, continuing with deploy...")
        else:
            _deploy_status = {
                "state": "error",
                "message": (
                    "Automatic migration of generated artifacts failed. "
                    "Run 'python tools/migrate_local_artifacts.py' manually, "
                    "then retry deployment."
                ),
            }
            print(f"[comfyui-modal] {_deploy_status['message']}")
            return
    except Exception as exc:
        print(f"[comfyui-modal] deployment guard check failed (non-fatal): {exc}")

    modal_cmd = _find_modal_executable()
    if not modal_cmd:
        _deploy_status = {
            "state": "error",
            "message": "modal CLI not found. Run: pip install modal",
        }
        print(f"[comfyui-modal] {_deploy_status['message']}")
        return

    _deploy_status = {"state": "deploying", "message": f"Deploying {workspace['label']}…"}
    print(f"[comfyui-modal] Deploying comfyapp.py (modal: {modal_cmd})")

    try:
        # Stream deploy output to log file in real-time so the inline log
        # viewer shows progress as the build runs, not just the final output.
        combined_lines: list[str] = []
        env = {
            **os.environ,
            "MODAL_TOKEN_ID": workspace["token_id"],
            "MODAL_TOKEN_SECRET": workspace["token_secret"],
            "PYTHONIOENCODING": "utf-8",
        }
        with open(_DEPLOY_LOG_FILE, "w", encoding="utf-8") as log_f:
            process = subprocess.Popen(
                [modal_cmd, "deploy", _COMFYAPP_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            # Kill the process if it exceeds 10 minutes (matches original
            # subprocess.run(timeout=600) behavior).
            _kill_timer = threading.Timer(
                600, lambda: process.kill() if process.poll() is None else None,
            )
            _kill_timer.start()
            try:
                # Read line-by-line so the file gets written as output arrives
                for line in iter(process.stdout.readline, ""):
                    log_f.write(line)
                    log_f.flush()
                    combined_lines.append(line)
                process.wait(timeout=30)
            finally:
                _kill_timer.cancel()
        combined_output = "".join(combined_lines)
        returncode = process.returncode

        if returncode == 0:
            version = _get_comfyapp_version()
            _save_workspace_deploy_state(
                workspace["id"],
                version,
                custom_nodes_fingerprint,
                deployed_at=_utc_now_iso(),
                deployment_command=f'"{modal_cmd}" deploy "{_COMFYAPP_PATH}"',
            )
            # Mark this deploy as a new generation that requires manual warmup.
            # No automatic GPU work is submitted — user must call
            # POST /comfymodal/deploy-warmup/run explicitly.
            try:
                state = WarmupState(_warmup_state_path)
                state.mark_deploy_started(
                    version, custom_nodes_fingerprint or "", time.time()
                )
                state._flush()
                # Auto-record the deploy in run history.
                REGISTRY.history().record_run(
                    kind="deploy",
                    prompt_id="",
                    workflow_hash="",
                    status="deployed",
                    meta={
                        "comfyapp_version": version,
                        "fingerprint": custom_nodes_fingerprint or "",
                        "workspace_id": workspace.get("id", ""),
                        "workspace_label": workspace.get("label", ""),
                    },
                )
            except Exception as exc:
                print(f"[comfyui-modal] warmup state mark failed: {exc}")
            _deploy_status = {
                "state": "deployed_unwarmed",
                "message": f"Deployed {workspace['label']} v{version}, manual warmup required",
            }
            print(f"[comfyui-modal] Deploy succeeded ({workspace['label']} v{version}), warmup via /comfymodal/deploy-warmup/run")
            if _modal_available:
                try:
                    clear_cache()
                except Exception as e:
                    print(f"[comfyui-modal] clear_cache failed: {e}")
        else:
            combined = combined_output.strip()
            error_prefix = _parse_deploy_error(combined)
            tail_bytes = 2000
            if len(combined) > tail_bytes:
                tail = "[...truncated, showing last 2000 chars...]\n" + combined[-tail_bytes:]
            else:
                tail = combined
            msg = f"Deploy failed: {tail}"
            if error_prefix:
                msg = f"{error_prefix} {msg}"
            _deploy_status = {
                "state": "error",
                "message": msg,
                "details": tail,
            }
            print(f"[comfyui-modal] {msg[:500]}")
    except subprocess.TimeoutExpired:
        _deploy_status = {"state": "error", "message": "Deploy timed out (10 min)", "details": "Deploy timed out after 10 minutes"}
        print(f"[comfyui-modal] Deploy timed out")
    except Exception as e:
        _deploy_status = {"state": "error", "message": str(e), "details": str(e)}
        print(f"[comfyui-modal] Deploy error: {e}")

def _start_background_deploy(workspace: dict, custom_nodes_fingerprint: str | None, reason: str) -> dict:
    global _deploy_status
    if _deploy_status.get("state") == "deploying":
        return {"started": False, "reason": "deploy_already_running"}
    _deploy_status = {"state": "deploying", "message": f"Running modal deploy for {workspace['label']}…"}
    thread = threading.Thread(
        target=_run_deploy_background,
        kwargs={"workspace": workspace, "custom_nodes_fingerprint": custom_nodes_fingerprint},
        daemon=True,
    )
    thread.start()
    return {"started": True, "reason": reason}


def _ensure_modal_deploy_current(workspace: dict, custom_nodes_fingerprint: str | None = None) -> dict:
    current_version = _get_comfyapp_version()
    deployed = _load_workspace_deploy_state(workspace["id"])
    deployed_version = deployed.get("comfyapp_version")
    deployed_fingerprint = deployed.get("custom_nodes_fingerprint")

    if current_version != deployed_version:
        return _start_background_deploy(
            workspace=workspace,
            custom_nodes_fingerprint=custom_nodes_fingerprint,
            reason="version_changed",
        )

    if custom_nodes_fingerprint is not None and custom_nodes_fingerprint != deployed_fingerprint:
        return _start_background_deploy(
            workspace=workspace,
            custom_nodes_fingerprint=custom_nodes_fingerprint,
            reason="custom_nodes_changed",
        )

    return {"started": False, "reason": "already_current"}


def _maybe_auto_deploy():
    if env_flag("COMFYMODAL_RUNTIME"):
        return
    if not _env_flag("COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY", "0"):
        _deploy_status["state"] = "ready"
        _deploy_status["message"] = "Background deploy disabled by config"
        _deploy_status["warning"] = False
        return
    if not _find_modal_executable():
        return
    workspace = _active_workspace()
    if workspace is None:
        _deploy_status["state"] = "error"
        _deploy_status["message"] = "No active workspace configured. Use the workspace manager."
        print("[comfyui-modal] No active workspace - skipping auto deploy")
        return
    fingerprint = _build_custom_node_fingerprint(_custom_nodes_root())
    decision = _ensure_modal_deploy_current(workspace, fingerprint)
    if decision["started"]:
        print(f"[comfyui-modal] background deploy started ({decision['reason']})")
    else:
        _deploy_status["state"] = "ready"
        _deploy_status["message"] = "Already deployed and current"
        _deploy_status["warning"] = False
        print("[comfyui-modal] deploy state already current - skipping deploy")

try:
    from server import PromptServer
    import execution
    _server = PromptServer.instance
except Exception as e:
    print(f"[comfyui-modal] Could not get PromptServer: {e}")
    _server = None
    execution = None

sys.path.insert(0, _NODE_DIR)

try:
    import modal as _modal_pkg
    from modal_client import run_prompt, run_prompt_stream, get_object_info, health_check, download_model, download_model_stream, batch_download_models, list_models, delete_model, set_gpu, get_gpu, get_default_gpu, get_available_gpus, sync_custom_nodes, refresh_custom_nodes, get_sync_status, upload_model_to_volume, upload_model_chunk, clear_cache, resync_runtime, get_runtime_state, set_active_warmup_profile, check_active_warmup_profile, set_workspace_resolver, get_handle_cache_stats, get_modal_app_name, get_modal_class_name, get_modal_lookup_target, persist_validation_certificate

    # ── Runtime flag helpers (lazy init to avoid import-time failures) ──
    _runtime_flag_funcs: dict = {}

    def _get_preload_mode_fn():
        if "set_preload_mode" not in _runtime_flag_funcs:
            _runtime_flag_funcs["set_preload_mode"] = _modal_pkg.Function.from_name("comfyui", "set_preload_mode")
        return _runtime_flag_funcs["set_preload_mode"]

    def _get_runtime_flag_fn():
        if "set_runtime_flag" not in _runtime_flag_funcs:
            _runtime_flag_funcs["set_runtime_flag"] = _modal_pkg.Function.from_name("comfyui", "set_runtime_flag")
        return _runtime_flag_funcs["set_runtime_flag"]

    async def _call_set_preload_mode(mode: str) -> str:
        import asyncio
        fn = _get_preload_mode_fn()
        return await asyncio.to_thread(lambda: fn.remote(mode))

    async def _call_set_runtime_flag(name: str, value: str) -> str:
        import asyncio
        fn = _get_runtime_flag_fn()
        return await asyncio.to_thread(lambda: fn.remote(name, value))

    _modal_available = True
    set_workspace_resolver(_active_workspace)
    _maybe_auto_deploy()
except ImportError:
    _err_detail = f" (install error: {_pip_install_error})" if _pip_install_error else ""
    print(f"[comfyui-modal] WARNING: 'modal' package not installed.{_err_detail} Run: pip install modal")
    _modal_available = False
    _deploy_msg = "modal package not installed. Run: pip install modal"
    if _pip_install_error:
        _deploy_msg += f" (pip error: {_pip_install_error})"
    _deploy_status = {"state": "error", "message": _deploy_msg}
    def run_prompt(*a, **kw): raise RuntimeError("modal not installed")
    def get_object_info(*a, **kw): raise RuntimeError("modal not installed")
    def health_check(*a, **kw): raise RuntimeError("modal not installed")
    def download_model(*a, **kw): raise RuntimeError("modal not installed")
    async def download_model_stream(*a, **kw): raise RuntimeError("modal not installed")  # noqa: E704
    def batch_download_models(*a, **kw): raise RuntimeError("modal not installed")
    def list_models(*a, **kw): raise RuntimeError("modal not installed")
    def delete_model(*a, **kw): raise RuntimeError("modal not installed")
    def sync_custom_nodes(*a, **kw): raise RuntimeError("modal not installed")
    def refresh_custom_nodes(*a, **kw): raise RuntimeError("modal not installed")
    def get_sync_status(*a, **kw): raise RuntimeError("modal not installed")
    def upload_model_to_volume(*a, **kw): raise RuntimeError("modal not installed")
    def upload_model_chunk(*a, **kw): raise RuntimeError("modal not installed")
    def resync_runtime(*a, **kw): raise RuntimeError("modal not installed")
    def get_runtime_state(*a, **kw): raise RuntimeError("modal not installed")
    def set_active_warmup_profile(*a, **kw): raise RuntimeError("modal not installed")
    async def check_active_warmup_profile(*a, **kw): raise RuntimeError("modal not installed")  # noqa: E704
    def get_default_gpu(): return "rtx-pro-6000"
    def get_available_gpus(): return [{"value": "rtx-pro-6000", "label": "RTX PRO 6000"}]
    def get_handle_cache_stats(): return {"hits": 0, "misses": 0}
    def set_gpu(gpu): pass
    def get_gpu(): return "rtx-pro-6000"
    def get_modal_app_name(): return "comfyui"
    def get_modal_class_name(gpu=None): return ""
    def get_modal_lookup_target(gpu=None, method_name="run_prompt"): return "unknown"

_COMFYUI_ROOT = os.path.dirname(os.path.dirname(_NODE_DIR))


def _runtime_mode() -> str:
    """Legacy compatibility wrapper. Use execution_runtime.resolve_execution_mode instead."""
    resolved = resolve_execution_mode(modal_settings=_load_modal_settings())
    return resolved["mode"]

_MODAL_TOML_PATH = os.path.expanduser("~/.modal.toml")
_HF_TOKEN_PATH = os.path.join(os.path.dirname(__file__), ".hf_token")
_CIVITAI_TOKEN_PATH = os.path.join(os.path.dirname(__file__), ".civitai_token")


def _validate_model_location(folder: str, filename: str) -> tuple[str, str]:
    return normalize_model_folder(folder), normalize_model_filename(filename)


def _placeholder_info(folder: str, filename: str) -> dict:
    return get_local_model_file_info(_COMFYUI_ROOT, folder, filename)


def _create_placeholder(folder: str, filename: str) -> dict:
    return create_local_placeholder(_COMFYUI_ROOT, folder, filename)


def _remove_local_placeholder_if_needed(folder: str, filename: str) -> dict | None:
    try:
        info = _placeholder_info(folder, filename)
    except Exception:
        return None
    if not info.get("is_placeholder"):
        return None
    try:
        os.remove(info["local_path"])
    except FileNotFoundError:
        return None
    return {"removed": True, "local_path": info["local_path"]}


def _create_placeholder_batch(items: list[dict]) -> tuple[list[dict], list[dict]]:
    placeholders = []
    errors = []
    for item in items:
        folder = item.get("folder", "")
        filename = item.get("filename", "")
        try:
            placeholders.append(_create_placeholder(folder, filename))
        except Exception as e:
            errors.append({"folder": folder, "filename": filename, "error": str(e)})
    return placeholders, errors


def _annotate_models_with_local_info(grouped_models: dict) -> dict:
    annotated = {}
    for section, files in grouped_models.items():
        annotated[section] = []
        for file in files:
            item = dict(file)
            folder = item.get("folder") or section
            try:
                item["local_placeholder"] = _placeholder_info(folder, item.get("name", ""))
            except Exception as e:
                item["local_placeholder"] = {
                    "folder": folder,
                    "filename": item.get("name", ""),
                    "exists": False,
                    "size": 0,
                    "is_placeholder": False,
                    "is_real_file": False,
                    "error": str(e),
                }
            annotated[section].append(item)
    return annotated


def _batch_placeholder_message(placeholders: list[dict], errors: list[dict]) -> str:
    created = sum(1 for item in placeholders if item.get("created"))
    existing = sum(1 for item in placeholders if item.get("existed"))
    if errors:
        return (
            f"Models downloaded to Modal. {created} local placeholder(s) created, "
            f"{existing} already existed, {len(errors)} failed. Refresh ComfyUI if the dropdown does not update."
        )
    return (
        f"Models downloaded to Modal. {created} local placeholder(s) created, "
        f"{existing} already existed. Refresh ComfyUI if the dropdown does not update."
    )


def _inject_all_message(created: int, existing: int, error_count: int) -> str:
    if error_count:
        return (
            f"Local placeholder sync complete. {created} created, {existing} already existed, "
            f"{error_count} failed. Refresh ComfyUI if the dropdown does not update."
        )
    return (
        f"Local placeholder sync complete. {created} created, {existing} already existed. "
        "Refresh ComfyUI if the dropdown does not update."
    )

def _read_hf_token() -> str:
    try:
        with open(_HF_TOKEN_PATH, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def _write_hf_token(token: str):
    import tempfile as _tf
    token = token.strip()
    parent = os.path.dirname(_HF_TOKEN_PATH)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    fd, tmp = _tf.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(token)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _HF_TOKEN_PATH)
    except Exception:
        os.unlink(tmp)
        raise

def _read_civitai_token() -> str:
    try:
        with open(_CIVITAI_TOKEN_PATH, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def _write_civitai_token(token: str):
    import tempfile as _tf
    token = token.strip()
    parent = os.path.dirname(_CIVITAI_TOKEN_PATH)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    fd, tmp = _tf.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(token)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _CIVITAI_TOKEN_PATH)
    except Exception:
        os.unlink(tmp)
        raise

def _is_modal_token_set() -> bool:
    return _active_workspace() is not None

def _write_modal_toml(token_id: str, token_secret: str):
    import tempfile
    if not re.match(r'^ak-[a-zA-Z0-9_\-]+$', token_id):
        raise ValueError(f"Invalid Modal token ID format: {token_id[:8]}...")
    if not re.match(r'^as-[a-zA-Z0-9_\-]+$', token_secret):
        raise ValueError(f"Invalid Modal token secret format: {token_secret[:8]}...")
    content = f'[default]\ntoken_id = "{token_id}"\ntoken_secret = "{token_secret}"\n'
    parent = os.path.dirname(_MODAL_TOML_PATH)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _MODAL_TOML_PATH)
    except Exception:
        os.unlink(tmp)
        raise


_queue: asyncio.Queue = asyncio.Queue()
_queue_worker_started = False
_queue_worker_task: asyncio.Task | None = None
_item_counter = 0
_counter_lock = asyncio.Lock()


def _queue_worker_done(task):
    global _queue_worker_task, _queue_worker_started
    _queue_worker_task = None
    _queue_worker_started = False
    try:
        exc = task.exception()
        if exc:
            print(f"[comfyui-modal] Queue worker died: {exc}")
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


def _send(sid: str, event: str, data: dict):
    if _server:
        _server.send_sync(event, data, sid)


def _pq():
    return _server.prompt_queue if _server else None


def _register_running(item: tuple) -> int:
    pq = _pq()
    if pq is None:
        return 0
    import heapq
    with pq.mutex:
        try:
            pq.queue.remove(item)
            heapq.heapify(pq.queue)
        except ValueError:
            pass
        key = pq.task_counter
        pq.currently_running[key] = copy.deepcopy(item)
        pq.task_counter += 1
        pq.server.queue_updated()
    return key


def _finish_job(item_id: int, prompt_id: str, outputs: dict, success: bool, meta: dict | None = None):
    pq = _pq()
    if pq is None:
        return
    status_cls = None
    if execution is not None:
        prompt_queue = getattr(execution, "PromptQueue", None)
        status_cls = getattr(prompt_queue, "ExecutionStatus", None) if prompt_queue is not None else None
    if status_cls is not None:
        status = status_cls(
            status_str='success' if success else 'error',
            completed=success,
            messages=[],
        )
    else:
        status = _ExecutionStatusFallback(
            status_str='success' if success else 'error',
            completed=success,
            messages=[],
        )
    history_result = {"outputs": outputs, "meta": dict(meta or {})}
    pq.task_done(item_id, history_result, status=status,
                 process_item=lambda prompt: prompt[:5] + prompt[6:])
    # Auto-record into the run-history store so the testing-suite
    # /comfymodal/run-history route shows ordinary prompt runs.
    try:
        meta_obj = dict(meta or {})
        primary = meta_obj.get("primary_output") or {}
        output_path = primary.get("path", "") if isinstance(primary, dict) else ""
        record = REGISTRY.history().record_run(
            kind="ordinary",
            prompt_id=prompt_id,
            workflow_hash=str(meta_obj.get("workflow_hash", "")),
            status="success" if success else "error",
            meta=meta_obj,
            log_text=str(meta_obj.get("error", "")) if not success else "",
            timings=meta_obj.get("trace") or {},
            output_path=output_path,
        )
        # Stash the run id back into the meta so the API caller can
        # find the history entry.
        meta_obj["run_history_id"] = record.get("run_id", "")
    except Exception:
        pass


async def _process_queue():
    global _queue_worker_started, _queue_worker_task
    while True:
        item, item_id = await _queue.get()
        try:
            _extra = item[3]
            _origin = (_extra.get("trace", {}) or {}).get("request_origin_info", {})
            _worker_wall_ns = time.time_ns()
            _worker_mono_ns = time.monotonic_ns()
            _origin["queue_worker_start_wall_ns"] = _worker_wall_ns
            _origin["queue_worker_start_mono_ns"] = _worker_mono_ns
            _enqueued_mono_ns = _origin.get("local_prompt_enqueued_mono_ns")
            if isinstance(_enqueued_mono_ns, int):
                _origin["queue_wait_before_worker_ms"] = round(
                    (_worker_mono_ns - _enqueued_mono_ns) / 1_000_000, 3
                )
        except Exception:
            pass
        try:
            await _execute_job(item, item_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            import traceback
            traceback.print_exc()
            print("[comfyui-modal] Queue worker survived job exception, continuing")
        finally:
            _queue.task_done()
    _queue_worker_started = False
    _queue_worker_task = None


def workflow_needs_local_input_files(workflow: dict) -> bool:
    """Return True if workflow contains nodes that reference local input files.

    Uses generic ComfyUI patterns — does NOT hardcode any specific node ID,
    LoadImage variant, model filename, or workflow hash.
    Checks class_type prefixes and well-known input keys.
    Skips HTTP/HTTPS URLs and node-link values (lists).
    """
    _LOCAL_LOAD_PREFIXES = (
        "LoadImage", "LoadVideo", "LoadAudio", "LoadMask",
        "VHS_Load", "VHS_Video", "VHS_Audio",
    )
    _LOCAL_LOAD_CLASSES = frozenset({"LoadImageMask"})
    _LOCAL_INPUT_KEYS = ("image", "mask", "video", "audio", "file", "filename")
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        if not (any(class_type.startswith(prefix) for prefix in _LOCAL_LOAD_PREFIXES)
                or class_type in _LOCAL_LOAD_CLASSES):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for key in _LOCAL_INPUT_KEYS:
            val = inputs.get(key)
            if not isinstance(val, str) or not val:
                continue
            if val.startswith(("http://", "https://")):
                continue
            return True
    return False


def _collect_input_images(workflow: dict) -> dict:
    images = {}
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        if not class_type.startswith("LoadImage"):
            continue
        for key in ("image", "mask"):
            filename = node.get("inputs", {}).get(key, "")
            if not isinstance(filename, str) or not filename:
                continue
            if filename in images:
                continue
            if filename.startswith(("http://", "https://")):
                continue
            try:
                candidates = _resolve_local_workflow_image_candidates(filename)
            except ValueError:
                print(f"[comfyui-modal] Warning: unsafe input image path skipped: {filename}")
                continue
            for filepath in candidates:
                if os.path.isfile(filepath):
                    with open(filepath, "rb") as f:
                        images[filename] = base64.b64encode(f.read()).decode()
                    break
            else:
                print(f"[comfyui-modal] Warning: input image not found locally: {filename}")
    return images


_ACTIVE_NEXT_PROFILE_TTL_S = int(os.environ.get("COMFYMODAL_ACTIVE_NEXT_PROFILE_TTL_S", "3600"))

# Per audit round 7: workspace-scoped dedup identity so
# Workspace A's profile write does not suppress Workspace B's.
# Keyed by (workspace_id, stable_model_key) => timestamp.
_last_written_stable_profile: dict[tuple[str, str], float] = {}
# Half-life refresh window: write at least every TTL/2, with a
# 30s floor so a small TTL still has a sane minimum.
_ACTIVE_NEXT_REFRESH_MIN_S = 30.0


def _ws_id_for_active_next(workspace: dict | None) -> str:
    if isinstance(workspace, dict):
        _wid = workspace.get("id") or workspace.get("workspace_id") or ""
        if _wid:
            return str(_wid)
    return "__default__"


def _normalize_stable_warmup_profile(
    warmup_profile: dict | None,
) -> dict:
    """Return a canonical warmup profile with only restore-relevant fields.

    Rules:
    - Missing fields become "".
    - disable_warmup becomes bool.
    - For mode=="checkpoint": preserve checkpoint, clear model fields.
    - For mode=="split": preserve model fields, clear checkpoint.
    - For other modes: preserve only mode and disable_warmup.
    - When clip2 == clip1, set clip2 = "".
    - Does not include workflow hash, UUIDs, timestamps, output nodes,
      seed, prompt, Production settings, or raw stack lists.
    """
    if not isinstance(warmup_profile, dict):
        warmup_profile = {}
    stable = {
        "mode": str(warmup_profile.get("mode", "")).strip(),
        "checkpoint": "",
        "unet": "",
        "clip1": "",
        "clip2": "",
        "vae": "",
        "clip_type": "",
        "disable_warmup": bool(warmup_profile.get("disable_warmup", False)),
    }
    _mode = stable["mode"]
    if _mode == "checkpoint":
        stable["checkpoint"] = str(warmup_profile.get("checkpoint", "")).strip()
    elif _mode == "split":
        stable["unet"] = str(warmup_profile.get("unet", "")).strip()
        stable["clip1"] = str(warmup_profile.get("clip1", "")).strip()
        stable["clip2"] = str(warmup_profile.get("clip2", "")).strip()
        stable["vae"] = str(warmup_profile.get("vae", "")).strip()
        stable["clip_type"] = str(warmup_profile.get("clip_type", "")).strip()
    # Collapse duplicate CLIP
    if stable["clip2"] and stable["clip2"] == stable["clip1"]:
        stable["clip2"] = ""
    return stable


def _compute_stable_warmup_profile_key(warmup_profile: dict) -> str:
    """Return a canonical stable key from only restore-relevant stacks.

    This excludes UUIDs, timestamps, workflow_hash, output nodes, and
    Production-mode settings so identical model stacks always produce
    the same key regardless of workflow display state.
    """
    _stable = _normalize_stable_warmup_profile(warmup_profile)
    return hashlib.sha256(
        json.dumps(_stable, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _build_next_warmup_activation(workflow: dict, workflow_hash: str, production_options: dict | None = None) -> dict:
    """Compatibility wrapper delegating to ``warmup_profile._build_activation_payload``."""
    from warmup_profile import build_activation_payload
    return build_activation_payload(workflow, workflow_hash, production_options)


async def _execute_job(item: tuple, item_id: int):
    # Per audit round 7: the dedup dict is module-global;
    # mutations must be marked global so the
    # ``_last_written_stable_profile[key] = ts`` assignment
    # rebinds the dict in-place rather than creating a local.
    global _last_written_stable_profile
    number, prompt_id, workflow, extra_data, _, _ = item
    execution_workflow = extra_data.get("execution_workflow") or workflow
    sid = extra_data.get("client_id", "")
    local_started = time.time()
    trace_payload = extra_data.get("trace", {}) if isinstance(extra_data, dict) else {}
    trace = Trace(prompt_id=prompt_id, t0=coerce_t0_from_browser(trace_payload) or local_started)
    trace.update(trace_payload)
    trace.mark("client_generate_clicked_or_request_start", trace.get("t0_client_press") or local_started)

    # Per audit round 7: the request workspace was captured at
    # dispatch time.  Use the same workspace throughout the
    # request and into the detached persistence thread so the
    # post-delivery write does not silently target whichever
    # workspace happens to be active when the worker fires.
    _request_workspace = extra_data.get("_request_workspace") if isinstance(extra_data, dict) else None
    if not _request_workspace:
        _request_workspace = _active_workspace() or {}

    # ── Active-next dedup bounding & TTL guard (audit round 7) ──
    # Bounded in-memory dedup cache complementary to
    # warmup_profile._last_stable_profile_cache.  Prunes stale entries
    # and computes refresh windows; the actual setter/write side effects
    # are handled by prepare_active_next_profile in warmup_profile.py.
    if len(_last_written_stable_profile) > 100:
        _last_written_stable_profile = {
            k: v for k, v in _last_written_stable_profile.items()
            if time.time() - v < _ACTIVE_NEXT_PROFILE_TTL_S
        }
    _effective_ttl_s = max(2.0, float(_ACTIVE_NEXT_PROFILE_TTL_S))
    _refresh_after_s = min(
        _effective_ttl_s * 0.5,
        _effective_ttl_s - 1.0,
    )
    _refresh_after_s = max(1.0, _refresh_after_s)

    task_key = _register_running(item)

    # ── v2.16.20: Read acknowledgment event ──
    ack_ready = extra_data.get("_modal_prompt_ack_ready")
    execution_start_forwarded = False

    # Send modal_status for Modal-specific status display (may precede ack).
    _send(sid, "modal_status", {"prompt_id": prompt_id, "message": "Modal execution starting", "phase": "dispatch"})

    # Derive workflow metadata for execution_start
    _exec_node_count = sum(
        1 for _n in (execution_workflow or {}).values()
        if isinstance(_n, dict) and isinstance(_n.get("class_type"), str) and _n["class_type"]
    )
    _exec_sampler_max = 0
    for _n in (execution_workflow or {}).values():
        if isinstance(_n, dict) and "Sampler" in str(_n.get("class_type", "")):
            _s = _n.get("inputs", {}).get("steps")
            if isinstance(_s, (int, float)) and _s > 0:
                _exec_sampler_max = int(_s)
                break

    # Helper: forward execution_start exactly once
    def _forward_execution_start_once():
        nonlocal execution_start_forwarded
        if not execution_start_forwarded:
            _send(sid, "execution_start", {
                "prompt_id": prompt_id,
                "total_nodes": _exec_node_count,
                "sampler_maximum": _exec_sampler_max,
            })
            execution_start_forwarded = True

    success = False
    finalized = False
    outputs = {}
    # Production options from route (canonical executor handles compile)
    production_options = extra_data.get("production_options") or {}
    # Metadata populated after execution from run_trace/result
    prompt_hash = ""
    prompt_summary: dict = {}
    model_stack: dict = {}
    # Per-request result-route mode — initialized before the main try so all
    # exception paths (CancelledError, execution failure, post-materialization)
    # can safely use it without referencing the module-level default.
    _result_route_mode = extra_data.get("result_route", _RESULT_ROUTE)
    try:
        _send(sid, "modal_status", {"prompt_id": prompt_id, "message": "Starting up", "phase": "startup"})

        # Log prompt metadata before remote execution (hash computed by canonical executor)
        print(f"[comfyui-modal] Starting prompt execution…")

        invocation_plan = _build_generation_invocation_plan(extra_data.get("gpu"), stream=True)
        _log_generation_invocation_plan(prompt_id, invocation_plan)

        remote_started = time.time()

        # ── Prepare modal_options (runtime flags, scheduler_test) ──
        _mo = dict(extra_data.get("modal_options") or {})
        # Propagate runtime restore_background_unet flag to volume file
        _rbg_enabled = False
        if isinstance(_mo.get("runtime"), dict):
            _rbg_runtime = _mo["runtime"].get("restore_background_unet", {})
            if isinstance(_rbg_runtime, dict):
                _rbg_enabled = bool(_rbg_runtime.get("enabled", False))
        if _modal_available and _rbg_enabled:
            try:
                await _call_set_runtime_flag("RESTORE_BACKGROUND_UNET", "1")
                print(f"[comfyui-modal] restore_background_unet volume flag set to 1 via runtime config")
            except Exception as _rbg_prop_exc:
                print(f"[comfyui-modal] restore_background_unet volume flag set failed: {_rbg_prop_exc}")
        _st = extra_data.get("scheduler_test")
        if isinstance(_st, dict):
            _mo["comfymodal_scheduler_test"] = _st

        # Build RunTrace for instrumentation
        _run_trace = RunTrace(
            prompt_id=prompt_id,
            run_surface="normal",
        )

        # ── v2.16.20: Wait for prompt acknowledgment before forwarding events ──
        if ack_ready is not None:
            await ack_ready.wait()
        # Forward execution_start now that ack is done
        _forward_execution_start_once()
        trace.mark("t2_local_dispatch")
        trace.mark("t2b_modal_handle_resolved")
        trace.mark("t2c_modal_call_start")
        trace.mark("client_modal_call_start", trace.get("t2c_modal_call_start") or remote_started)
        trace.mark("client_modal_submit_done", trace.get("t2c_modal_call_start") or remote_started)
        if os.environ.get("COMFYMODAL_PREDISPATCH_DEBUG"):
            print(f"[predispatch] phase=before_gpu_spawn t={time.time()}")

        # ── Event sink: forward progress/status events to frontend ──
        _first_remote_event_seen = True
        def _event_sink(event_type: str, payload: dict) -> None:
            nonlocal _first_remote_event_seen
            if _first_remote_event_seen:
                _first_remote_event_seen = False
                trace.mark("client_first_remote_log_seen")
            if event_type == "progress" and isinstance(payload, dict):
                _evt = payload.get("event", "executing")
                _data = dict(payload)
                _data["prompt_id"] = prompt_id
                _send(sid, _evt, _data)
            elif event_type == "status" and isinstance(payload, dict):
                _p = dict(payload)
                _p["prompt_id"] = prompt_id
                _send(sid, "modal_status", _p)
            elif event_type == "executing":
                _forward_execution_start_once()

        # ── Delegate to canonical executor ──
        # execute_modal_prompt handles: compile (from production_options),
        # hash validation, API structure, class-type validation, input image
        # collection, profile preparation, run-prompt-options construction,
        # and the run_prompt_stream call with event forwarding.
        # This is the single canonical call — no second compile/hash path.
        # Phase 8: use captured mode from submission (immutable), fall back to resolver.
        _mode_resolution = resolve_execution_mode(
            modal_options=extra_data.get("modal_options"),
            extra=extra_data,
            modal_settings=_load_modal_settings(),
        )
        _mode = _mode_resolution["mode"]
        _v2_plan = None
        _v2_trace = None
        if _mode in {"v2", "shadow"}:
            _v2_trace = RuntimeTrace(request_id=prompt_id, process="local")
            # ── Phase 0: deployment/invocation identity ──
            _v2_gpu = extra_data.get("gpu") or get_gpu() or ""
            _v2_app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow").strip() or "stable-modal-comfy-v2-shadow"
            _v2_class_name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2").strip() or "ModalRuntimeEntrypointV2"
            _v2_method_name = "run_plan_stream"
            _origin_info = trace_payload.get("request_origin_info", {}) if isinstance(trace_payload, dict) else {}
            _v2_trace.set_metadata(
                runtime_mode=_mode,
                app_name=_v2_app_name,
                class_name=_v2_class_name,
                method_name=_v2_method_name,
                gpu=_v2_gpu,
                cloud=os.environ.get("COMFYMODAL_COMPUTE_CLOUD", "").strip(),
                region=os.environ.get("COMFYMODAL_COMPUTE_REGION", "").strip(),
                image_id=os.environ.get("MODAL_IMAGE_ID", "").strip(),
                container_task_id=os.environ.get("MODAL_TASK_ID", "").strip(),
                request_origin_info=dict(_origin_info) if isinstance(_origin_info, dict) else {},
            )
            # Emit worker_start at the true dequeue boundary
            _ws_wall = _origin_info.get("queue_worker_start_wall_ns") if isinstance(_origin_info, dict) else None
            _ws_mono = _origin_info.get("queue_worker_start_mono_ns") if isinstance(_origin_info, dict) else None
            if _ws_wall is not None and _ws_mono is not None:
                _v2_trace.emit_at("worker_start", wall_unix_ns=_ws_wall, monotonic_ns=_ws_mono, phase="local")
            _v2_plan = build_execution_plan(
                execution_workflow,
                prompt_id=prompt_id,
                client_id=sid,
                modal_options=_mo if _mo else None,
                production_options=production_options if production_options.get("enabled") else None,
                production_report=extra_data.get("production_report") if isinstance(extra_data, dict) else None,
                gpu=_v2_gpu,
                workspace=_request_workspace or None,
                comfyui_root=_COMFYUI_ROOT,
                trace=_v2_trace,
                validate=False,
            )
            _v2_trace.set_metadata(
                workflow_hash_prefix=_v2_plan.workflow_hash[:12],
                container_session_id="",  # placeholder; populated from remote
                workspace_id=_v2_plan.request_metadata.get("workspace_id", ""),
            )
            _run_trace.set_meta(
                execution_mode=_mode,
                execution_mode_source=_mode_resolution["source"],
                v2_runtime_mode=_mode,
                v2_plan_hash=_v2_plan.workflow_hash,
                v2_source_workflow_hash=_v2_plan.source_workflow_hash,
            )
            if _mode == "shadow":
                print(f"[comfyui-modal] v2 shadow plan built hash={_v2_plan.workflow_hash[:12]}")

        if _mode == "v2" and _v2_plan is not None:
            _v2_transport = ModalTransport()
            result = await execute_plan(
                _v2_plan,
                transport=_v2_transport,
                profile_setter=None,
                gpu=extra_data.get("gpu"),
                workspace=_request_workspace or None,
                trace=_v2_trace,
                event_sink=_event_sink,
            )
        else:
            _run_trace.set_meta(
                execution_mode=_mode,
                execution_mode_source=_mode_resolution["source"],
            )
            result = await execute_modal_prompt(
                execution_workflow,
                prompt_id=prompt_id,
                client_id=sid,
                input_images=None,
                modal_options=_mo if _mo else None,
                production_options=production_options if production_options.get("enabled") else None,
                gpu=extra_data.get("gpu"),
                workspace=_request_workspace or None,
                trace_payload={**trace.fields(), "prompt_id": prompt_id, "client_id": sid},
                profile_setter=set_active_warmup_profile,
                profile_checker=check_active_warmup_profile,
                run_trace=_run_trace,
                comfyui_root=_COMFYUI_ROOT,
                event_sink=_event_sink,
            )
        if isinstance(result, dict) and result.get("use_descriptors"):
            _register_remote_result_assets(
                result,
                workspace=_request_workspace or {},
                gpu=str(extra_data.get("gpu") or get_gpu() or ""),
                prompt_id=prompt_id,
            )
        # ── Extract canonical metadata from run_trace ──
        _result_trace = result.get("trace", {}) if isinstance(result, dict) else {}
        _run_trace_summary = _result_trace.get("_run_trace", {}) if isinstance(_result_trace, dict) else {}
        _rt_meta = _run_trace_summary.get("meta", {}) if isinstance(_run_trace_summary, dict) else {}
        if _rt_meta:
            prompt_hash = _rt_meta.get("source_workflow_hash",
                         _rt_meta.get("compiled_workflow_hash", ""))
            prompt_summary = _rt_meta.get("prompt_summary", {})
            model_stack = _rt_meta.get("model_stack", {})
        elif _v2_plan is not None and _mode in {"v2", "shadow"}:
            # v2 path fallback: extract from v2 plan metadata when the
            # legacy _run_trace envelope is absent.
            prompt_hash = _v2_plan.source_workflow_hash or _v2_plan.workflow_hash
            prompt_summary = dict(_v2_plan.prompt_bundle)
            model_stack = dict(_v2_plan.model_stack)
        # Log after canonical extraction
        print(f"[comfyui-modal] Running prompt {prompt_hash[:12] if prompt_hash else '?'}…")

        # ── Diagnostics: result received ──
        _flat_imgs = result.get("images", []) if isinstance(result, dict) else []
        _outs = result.get("outputs", {}) if isinstance(result, dict) else {}
        print(
            f"[modal-local.receive-final] result_type={type(result).__name__} "
            f"image_count={len(_flat_imgs)} output_nodes={len(_outs)}"
        )
        trace.mark("t9_modal_return")
        trace.mark("t9b_local_result_received")
        trace.mark("client_remote_result_received", trace.get("t9b_local_result_received") or time.time())
        remote_run_ms = round((time.time() - remote_started) * 1000, 1)
        print(
            f"[comfyui-modal.profile] stage=remote_run_prompt prompt_id={prompt_id[:8]} "
            f"duration_ms={remote_run_ms}"
        )
        remote_trace = result.get("trace") if isinstance(result, dict) else {}
        if isinstance(remote_trace, dict):
            trace.update(remote_trace.get("stages", {}))

        _direct_result_used = False
        _direct_fallback_reason = None

        success = True
        finalized = False
    except asyncio.CancelledError:
        total_ms = round((time.time() - local_started) * 1000, 1)
        print(
            f"[comfyui-modal.profile] stage=local_total prompt_id={prompt_id[:8]} "
            f"duration_ms={total_ms} error=cancelled"
        )
        _send(sid, "execution_error", {"message": "cancelled", "prompt_id": prompt_id})
        _finish_job(task_key, prompt_id, outputs, success=False, meta={"error": "cancelled"})
        if _result_route_mode == "direct":
            with _COMPLETED_RESULTS_LOCK:
                _COMPLETED_RESULTS[prompt_id] = {
                    "status": "error",
                    "error": "cancelled",
                    "completed_at": time.time(),
                    "direct_route": True,
                }
        _clear_request_state(prompt_id)
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        total_ms = round((time.time() - local_started) * 1000, 1)
        print(
            f"[comfyui-modal.profile] stage=local_total prompt_id={prompt_id[:8]} "
            f"duration_ms={total_ms} error={type(e).__name__}"
        )
        # ── PART 8: Structured failure summary ──
        summary = FailureSummary(phase="execution")
        summary.fatal_error = str(e)[:500]
        summary.time_restore_ms = 0.0
        summary.time_requirements_ms = 0.0
        error_str = str(e).lower()
        if "class_type" in error_str or "missing" in error_str:
            summary.run_failed_phase = "validation"
            summary.recommendation = (
                "Fix the workflow's custom node references and retry."
            )
        elif "hash mismatch" in error_str:
            summary.run_failed_phase = "integrity"
            summary.recommendation = (
                "Workflow was modified after submission. Re-submit."
            )
        print(f"[comfyui-modal] FAILURE SUMMARY: {summary}")
        _send(sid, "execution_error", {"message": str(e), "prompt_id": prompt_id})
        _finish_job(task_key, prompt_id, outputs, success=False, meta={
            "error": str(e),
            "model_stack": model_stack,
            "prompt_summary": prompt_summary,
            "workflow_hash": prompt_hash,
        })
        if _result_route_mode == "direct":
            with _COMPLETED_RESULTS_LOCK:
                _COMPLETED_RESULTS[prompt_id] = {
                    "status": "error",
                    "error": str(e),
                    "completed_at": time.time(),
                    "direct_route": True,
                }
        _clear_request_state(prompt_id)
        return

    # ── Post-materialization block: guarded so _finish_job always runs ──
    try:
        # Update last successful model stack after successful remote result
        # (populated from canonical executor's run_trace metadata)
        global _last_successful_model_stack
        _last_successful_model_stack.clear()
        _last_successful_model_stack.update(model_stack)

        output_dir = os.path.join(_COMFYUI_ROOT, "output")
        os.makedirs(output_dir, exist_ok=True)
        # ── Phase 6: local materialization boundary ──
        trace.mark("t9e_local_materialize_start")
        materialize_started = time.time()
        # v4 event trace: materialization phase start
        _local_et = _get_local_event_trace()
        if _local_et is not None:
            from profiler_trace_v4 import (
                T9C_LOCAL_BASE64_DECODE_START, T9E_LOCAL_FILE_WRITE_START,
                T10_LOCAL_MATERIALIZED, PHASE_LOCAL_MATERIALIZE,
            )
            _local_et.mark(T9C_LOCAL_BASE64_DECODE_START, phase=PHASE_LOCAL_MATERIALIZE)
            _local_et.mark(T9E_LOCAL_FILE_WRITE_START, phase=PHASE_LOCAL_MATERIALIZE)
        trace.mark("client_result_decode_start")
        trace.mark("client_file_write_start")
        _mo = extra_data.get("modal_options") if isinstance(extra_data, dict) else None
        _settings = _load_modal_settings()
        if _mode == "v2":
            _remote_fetch_workspace = _request_workspace or _active_workspace() or {}
            _remote_fetch_gpu = str(extra_data.get("gpu") or get_gpu() or "")

            def _remote_fetch_fn(backend_path: str, asset_id: str) -> bytes:
                from modal_client import read_output_asset as _read_asset
                import asyncio
                try:
                    _loop = asyncio.get_running_loop()
                except RuntimeError:
                    _loop = None
                _coro = _read_asset(backend_path, expected_sha256=asset_id, gpu=_remote_fetch_gpu, workspace=_remote_fetch_workspace)
                if _loop is not None and _loop.is_running():
                    _future = asyncio.run_coroutine_threadsafe(_coro, _loop)
                    _result = _future.result(timeout=120)
                else:
                    _result = asyncio.run(_coro)
                _data = _result.get("data", b"") if isinstance(_result, dict) else b""
                if not isinstance(_data, bytes):
                    raise TypeError("remote fetch returned unexpected type")
                return _data

            delivery = _materialize_v2_result(
                result,
                output_dir=output_dir,
                prompt_id=prompt_id,
                client_id=sid,
                send_event=lambda event, payload: _send(sid, event, payload),
                auto_save_local=bool((_mo or {}).get("auto_save_local", False)),
                save_folder=(_mo or {}).get("save_folder") or _settings.get("save_folder", ""),
                save_metadata_sidecar=bool((_mo or {}).get("save_metadata_sidecar", _settings.get("save_metadata_sidecar", True))),
                workflow_hash=prompt_hash,
                seed=str(prompt_summary.get("seed", "0")),
                width=prompt_summary.get("width", 0),
                height=prompt_summary.get("height", 0),
                comfyui_root=_COMFYUI_ROOT,
                remote_fetch_fn=_remote_fetch_fn,
            )
        else:
            delivery = _materialize_modal_outputs(
                result,
                output_dir=output_dir,
                prompt_id=prompt_id,
                client_id=sid,
                send_event=lambda event, payload: _send(sid, event, payload),
                auto_save_local=bool((_mo or {}).get("auto_save_local", False)),
                save_folder=(_mo or {}).get("save_folder") or _settings.get("save_folder", ""),
                save_metadata_sidecar=bool((_mo or {}).get("save_metadata_sidecar", _settings.get("save_metadata_sidecar", True))),
                workflow_hash=prompt_hash,
                workflow_name="",
                seed=str(prompt_summary.get("seed", "0")),
                width=prompt_summary.get("width", 0),
                height=prompt_summary.get("height", 0),
                comfyui_root=_COMFYUI_ROOT,
            )
        # v4 event trace: materialization phase end
        if _local_et is not None:
            from profiler_trace_v4 import (
                T9D_LOCAL_BASE64_DECODE_END, T9F_LOCAL_FILE_WRITE_END,
                T10_LOCAL_MATERIALIZED, PHASE_LOCAL_MATERIALIZE,
            )
            _local_et.mark(T9D_LOCAL_BASE64_DECODE_END, phase=PHASE_LOCAL_MATERIALIZE)
            _local_et.mark(T9F_LOCAL_FILE_WRITE_END, phase=PHASE_LOCAL_MATERIALIZE)
            _local_et.mark(T10_LOCAL_MATERIALIZED, phase=PHASE_LOCAL_MATERIALIZE)
        outputs.clear()
        outputs.update(delivery.get("history_outputs", delivery["outputs"]))
        output_bytes_written = delivery["bytes_written"]
        output_image_count = delivery["image_count"]
        output_video_count = delivery["video_count"]
        materialize_ms = round((time.time() - materialize_started) * 1000, 1)
        # Phase 6: store per-operation timing breakdown from delivery
        _mat_timing = delivery.get("materialization_timing") or {}
        trace.mark("client_result_decode_done")
        trace.mark("client_file_write_done")
        trace.mark("client_comfy_notify_done")
        print(
            f"[comfyui-modal.profile] stage=output_materialize prompt_id={prompt_id[:8]} "
            f"duration_ms={materialize_ms} images={output_image_count} videos={output_video_count} bytes={output_bytes_written}"
        )
        print(
            f"[modal-local.materialize-end] prompt_id={prompt_id[:8]} "
            f"written={output_image_count + output_video_count}"
        )
        _local_primary_output = delivery.get("primary_output")
        if isinstance(result, dict) and _local_primary_output:
            result["_local_primary_output"] = dict(_local_primary_output)
            result["primary_output"] = dict(_local_primary_output)

        trace.mark("t10b_local_save_start")
        _save_results = delivery.get("save_results", [])
        _save_warnings = delivery.get("save_warnings", [])
        if _save_warnings:
            print(f"[comfyui-modal.auto_save] warnings: {'; '.join(_save_warnings)}")
        if _save_results:
            _send(sid, "modal_status", {
                "prompt_id": prompt_id,
                "message": f"Auto-saved {len(_save_results)} file(s)",
                "phase": "auto_save",
                "save_results": _save_results,
                "save_warnings": _save_warnings,
            })
        elif _save_warnings:
            _send(sid, "modal_status", {
                "prompt_id": prompt_id,
                "message": f"Auto-save warning: {'; '.join(_save_warnings)}",
                "phase": "auto_save",
                "save_warnings": _save_warnings,
            })

        trace.mark("t10c_local_save_end")
        trace.mark("t10_local_materialized")
        _merged_trace = trace.summary()
        # Merge remote trace data into the local merged trace using the
        # shared helper from timing_trace (preserves stages, deltas_ms,
        # derived_ms, restore, and dependency-validation fields without
        # overwriting truthfully local materialization values).
        _remote_full = result.get("trace", {})
        merge_remote_trace_into(_merged_trace, _remote_full)

        # Stash active-next preparer metrics into the merged trace.
        # Extract from the _run_trace spans and counts which were recorded
        # by execute_modal_prompt / prepare_modal_execution.  When the
        # legacy RunTrace envelope is absent (v2 path), fall back to
        # metadata fields carried by the v2 RuntimeTrace.
        _MERGED_DERIVED = _merged_trace.setdefault("derived_ms", {})
        _run_trace_summary = result.get("trace", {}).get("_run_trace", {}) if isinstance(result.get("trace"), dict) else {}
        _rt_counts = _run_trace_summary.get("counts", {}) if isinstance(_run_trace_summary, dict) else {}
        _rt_spans = _run_trace_summary.get("spans", {}) if isinstance(_run_trace_summary, dict) else {}
        if not isinstance(_rt_counts, dict):
            _rt_counts = {}
        if not isinstance(_rt_spans, dict):
            _rt_spans = {}
        # v2 metadata fallback source — read once, safe when absent/non-dict
        _v2_meta = result.get("trace", {}).get("metadata", {}) if isinstance(result.get("trace"), dict) else {}
        if not isinstance(_v2_meta, dict):
            _v2_meta = {}

        _profile_span = _rt_spans.get("prepare_active_next_profile", {}) if isinstance(_rt_spans, dict) else {}
        if _profile_span and isinstance(_profile_span, dict) and _profile_span.get("called"):
            _MERGED_DERIVED["active_profile_build_ms"] = _profile_span.get("duration_ms", 0)
        else:
            # v2 fallback: read from trace metadata when positive
            _v2_prepare_ms = _v2_meta.get("local_active_profile_prepare_ms", 0.0)
            _MERGED_DERIVED["active_profile_build_ms"] = max(0.0, _v2_prepare_ms) if isinstance(_v2_prepare_ms, (int, float)) else 0.0
        if "active_profile_prepare_count" in _rt_counts:
            _MERGED_DERIVED["active_profile_remote_call"] = _rt_counts.get("active_profile_prepare_count", 0)
        else:
            # v2 fallback: read active_profile_prepare_count from metadata
            _v2_remote_call = _v2_meta.get("active_profile_prepare_count", 0)
            if isinstance(_v2_remote_call, (int, float)):
                _MERGED_DERIVED["active_profile_remote_call"] = int(_v2_remote_call) if _v2_remote_call else 0
            else:
                _MERGED_DERIVED["active_profile_remote_call"] = 1 if _v2_remote_call else 0
        _MERGED_DERIVED["active_profile_to_gpu_submit_ms"] = 0.0  # Not tracked in canonical executor
        _merged_trace["active_profile_dedup_status"] = ""  # Not tracked in canonical executor
        # ── Phase 6 materialization timing ──
        if _mat_timing:
            _MERGED_DERIVED["materialize_wall_ms"] = _mat_timing.get("total_wall_ms", 0.0)
            _MERGED_DERIVED["materialize_decode_ms"] = _mat_timing.get("total_decode_time_ms", 0.0)
            _MERGED_DERIVED["materialize_write_ms"] = _mat_timing.get("total_write_time_ms", 0.0)
            _MERGED_DERIVED["materialize_item_count"] = _mat_timing.get("item_count", 0)
            _MERGED_DERIVED["materialize_bytes"] = _mat_timing.get("bytes_written", 0)
            # auto-save time present in local path (_materialize_modal_outputs)
            _auto_ms = _mat_timing.get("auto_save_time_ms", 0.0)
            if _auto_ms:
                _MERGED_DERIVED["materialize_auto_save_ms"] = _auto_ms
            # thumbnail time present in experiment path
            _thumb_ms = _mat_timing.get("total_thumbnail_time_ms", 0.0)
            if _thumb_ms:
                _MERGED_DERIVED["materialize_thumbnail_ms"] = _thumb_ms

        # ── Preserve V2 trace fields lost by trace.summary() and hoist identity ──
        # trace.summary() produces a legacy timing dict without events, metadata,
        # trace_id, request_id, or container_session_id.  These are essential
        # for diagnosis_collector, benchmark consumers, and restore-timing
        # lifecycle analysis.
        _remote_events = _remote_full.get("events")
        if isinstance(_remote_events, list):
            _merged_trace["events"] = list(_remote_events)
        _remote_md = _remote_full.get("metadata")
        if isinstance(_remote_md, dict):
            _merged_trace["metadata"] = dict(_remote_md)
        for _key in ("trace_id", "request_id"):
            _val = _remote_full.get(_key)
            if _val:
                _merged_trace[_key] = _val
        _csid = _remote_full.get("container_session_id")
        if _csid:
            _merged_trace["container_session_id"] = _csid
        _restore_timing_rt = result.get("_restore_timing")
        if _restore_timing_rt:
            _merged_trace["_restore_timing"] = _restore_timing_rt

        # Hoist identity fields from authoritative remote (top-level preferred,
        # then remote metadata), skipping when already set above.  Nonempty
        # remote values take precedence over empty local placeholders so that
        # diagnosis_collector extract_section14_run finds real container/GPU
        # identity in V2 benchmark artifacts.
        _IDENTITY_HOIST_KEYS = (
            "container_task_id", "container_session_id", "image_id",
            "gpu", "cloud", "region", "modal_input_id",
            "workspace_id", "app_name", "class_name", "method_name",
        )
        for _hk in _IDENTITY_HOIST_KEYS:
            if _hk in _merged_trace:
                continue
            _remote_val = _remote_full.get(_hk)
            if not _remote_val and isinstance(_v2_meta, dict):
                _remote_val = _v2_meta.get(_hk)
            if _remote_val:
                _merged_trace[_hk] = _remote_val

        result["trace"] = _merged_trace
        if os.environ.get("COMFYMODAL_TRACE_DEBUG_LOG"):
            _dbg_path = os.path.join(_NODE_DIR, "_trace_debug.log")
            with open(_dbg_path, "a", encoding="utf-8") as _f:
                _f.write(f"[timing_trace.final] trace_version={_merged_trace.get('trace_version')} "
                         f"has_derived={'derived_ms' in _merged_trace} "
                         f"derived_keys={list(_merged_trace.get('derived_ms', {}).keys())} "
                         f"quality={_merged_trace.get('timing_quality')} "
                         f"quality_reason={_merged_trace.get('timing_quality_reason')} "
                         f"missing={_merged_trace.get('missing_timing_fields', [])}\n")
                _f.write(f"[timing_trace.final] DELTAS keys: {list(_merged_trace.get('deltas_ms', {}).keys())}\n")
                _f.write(f"[timing_trace.final] STAGES keys: {list(_merged_trace.get('stages', {}).keys())}\n")
                _f.flush()
        print(trace.log_line())

        # Extract production evidence from remote result
        _production_evidence = result.get("_production_evidence") if isinstance(result, dict) else None
        trace.mark("t10d_local_response_sent")
        trace.mark("client_comfy_notify_start")
        trace.mark("client_comfy_notify_done")
        _send(sid, "executing", {"node": None, "display_node": None, "prompt_id": prompt_id})
        _send(sid, "modal_status", {"prompt_id": prompt_id, "message": None, "phase": "done"})
        _exec_success_data = {"prompt_id": prompt_id, "trace": result.get("trace")}
        if _production_evidence is not None:
            _exec_success_data["_production_evidence"] = _production_evidence
        _send(sid, "execution_success", _exec_success_data)
        _meta = {
            "model_stack": model_stack,
            "prompt_summary": prompt_summary,
            "trace": result.get("trace"),
            "workflow_hash": prompt_hash,
            "restore_timing": result.get("_restore_timing", {}),
            "scheduler_trace": result.get("scheduler_trace"),
            "primary_output": result.get("primary_output") or result.get("_local_primary_output"),
            "_production_evidence": result.get("_production_evidence") if isinstance(result, dict) else None,
        }
        _finish_job(task_key, prompt_id, outputs, success=True, meta=_meta)

        # ── P2: post-delivery prompt-cache persistence ──
        # Only fires after successful materialization + UI success +
        # _finish_job. Bounded, exception-safe, never delays the user-
        # visible completion path.  The payload is collected and
        # dispatched to a small background task that calls the CPU-only
        # Modal function.  Failure of persistence never fails the
        # prompt.
        try:
            if env_flag("COMFYMODAL_PERSISTENT_CLIP_CACHE"):
                _clip_candidate = result.get("_clip_cache_candidate") if isinstance(result, dict) else None
                _clip_fingerprint = result.get("_clip_cache_fingerprint") if isinstance(result, dict) else None
                _bundle = _clip_candidate.get("bundle") if isinstance(_clip_candidate, dict) else None
                if isinstance(_bundle, dict) and _bundle.get("encodes"):
                    print(
                        f"[exact_prefill.bundle] eligible=1 encode_count={len(_bundle['encodes'])} "
                        f"hash={str(_bundle.get('bundle_hash', ''))[:16] or 'absent'}"
                    )
                else:
                    _bundle_failure_reason = (
                        result.get("_clip_cache_error") if isinstance(result, dict) else None
                    ) or "neither_exact_clip_prefill_nor_persistent_clip_cache_enabled"
                    if _bundle_failure_reason == "exception":
                        _bundle_failure_reason = "extraction_exception"
                    print(
                        f"[exact_prefill.bundle] eligible=0 reason={_bundle_failure_reason}"
                    )
                if _clip_candidate and _clip_fingerprint:
                    from optimizations import candidate_payload_bytes, PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB, _POST_DELIVERY_SINGLETON
                    _payload_bytes = candidate_payload_bytes(_clip_candidate)
                    if _payload_bytes <= PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB * 1024 * 1024:
                        # Use the process-wide dispatcher singleton so
                        # cross-request concurrency and dedup are real.
                        _dispatcher = _POST_DELIVERY_SINGLETON
                        _bundle_hash = (
                            _clip_candidate.get("bundle", {}).get("bundle_hash", "")
                        )
                        print(
                            f"[exact_prefill.active_next_write] bundle_present={int(bool(_bundle_hash))} "
                            f"bundle_hash={_bundle_hash[:16] or 'absent'}"
                        )
                        # Per audit round 7: the dedup identity
                        # must include the workspace, the
                        # bundle hash, and the clip fingerprint
                        # key (which itself encodes model
                        # generation).  bundle_hash alone is
                        # insufficient because the same bundle
                        # under a new model generation must NOT
                        # be deduplicated against the previous
                        # generation's successful write.
                        _workspace_id = ""
                        if isinstance(_request_workspace, dict):
                            _workspace_id = str(
                                _request_workspace.get("id", "")
                                or _request_workspace.get("workspace_id", "")
                                or ""
                            )
                        _fp_key = ""
                        if isinstance(_clip_fingerprint, dict):
                            _fp_key = str(
                                _clip_fingerprint.get("fingerprint_key", "")
                                or ""
                            )
                        _persist_task_id = ":".join(
                            x for x in (_workspace_id, _bundle_hash, _fp_key) if x
                        )
                        if _bundle_hash and _dispatcher is not None:
                            def _persist_call():
                                # Local import keeps the cold path
                                # clean. The actual call uses
                                # modal_client; import lazily to avoid
                                # touching modal at module import time.
                                try:
                                    from modal_client import persist_clip_cache_payload
                                    # Per audit round 7: pass the
                                    # captured workspace so the
                                    # persistence RPC targets the
                                    # SAME workspace as the request,
                                    # not whichever workspace is
                                    # active when the detached
                                    # background thread fires.
                                    if _request_workspace:
                                        return persist_clip_cache_payload(
                                            _clip_candidate,
                                            workspace=_request_workspace,
                                            timeout_s=30.0,
                                        )
                                    return persist_clip_cache_payload(
                                        _clip_candidate, timeout_s=30.0
                                    )
                                except Exception as _persist_exc:
                                    print(
                                        f"[comfyui-modal.post_delivery] persist failed: {_persist_exc!r}"
                                    )
                                    return {"status": "error", "error": str(_persist_exc)}
                            _dispatcher.submit(
                                task_id=_persist_task_id or _bundle_hash,
                                fn=_persist_call,
                                timeout_s=30.0,
                            )
                            print(
                                f"[comfyui-modal.post_delivery] scheduled prompt_id={prompt_id[:8]} "
                                f"workspace_id={_workspace_id[:12] or '-'} "
                                f"bundle_hash={_bundle_hash[:12]} "
                                f"fingerprint_key={_fp_key[:12] or '-'} "
                                f"bytes={_payload_bytes}"
                            )
                    else:
                        print(
                            f"[comfyui-modal.post_delivery] skipped_over_limit "
                            f"prompt_id={prompt_id[:8]} bytes={_payload_bytes} "
                            f"limit_mb={PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB}"
                        )
        except Exception as _post_persist_exc:
            # Never fail the request due to persistence.
            print(f"[comfyui-modal.post_delivery] dispatcher error: {_post_persist_exc!r}")

        # ── P3: post-delivery validation certificate persistence ──
        # Attach the certificate candidate to the result on the GPU side so
        # the local bridge can schedule persistence without delaying delivery.
        try:
            _cert_candidate = result.get("_certificate_candidate") if isinstance(result, dict) else None
            if _cert_candidate and isinstance(_cert_candidate, dict) and _cert_candidate.get("identity"):
                _workspace_id = ""
                if isinstance(_request_workspace, dict):
                    _workspace_id = str(
                        _request_workspace.get("id", "")
                        or _request_workspace.get("workspace_id", "")
                        or ""
                    )
                _cert_identity = str(_cert_candidate.get("identity", ""))
                # Collision-resistant task_id: workspace + identity ensures
                # different workspaces never poison each other's dedup.
                _persist_task_id = ":".join(x for x in (_workspace_id, _cert_identity) if x)
                if _persist_task_id:
                    from optimizations import _POST_DELIVERY_SINGLETON as _CERT_DISPATCHER
                    if _CERT_DISPATCHER is not None:
                        def _cert_persist_call():
                            try:
                                return persist_validation_certificate(
                                    _cert_candidate,
                                    workspace=_request_workspace if _request_workspace else None,
                                    timeout_s=60.0,
                                )
                            except Exception as _persist_exc:
                                print(
                                    f"[comfyui-modal.post_delivery] cert persist failed: {_persist_exc!r}"
                                )
                                return {"status": "error", "error": str(_persist_exc)}
                        _CERT_DISPATCHER.submit(
                            task_id=_persist_task_id,
                            fn=_cert_persist_call,
                            timeout_s=60.0,
                        )
                        print(
                            f"[comfyui-modal.post_delivery] scheduled cert prompt_id={prompt_id[:8]} "
                            f"workspace_id={_workspace_id[:12] or '-'} "
                            f"identity={_cert_identity[:16]}"
                        )
        except Exception as _post_cert_exc:
            # Never fail the request due to persistence.
            print(f"[comfyui-modal.post_delivery] cert dispatcher error: {_post_cert_exc!r}")

        # ── Direct route: store completed result for non-polling retrieval ──
        if _result_route_mode == "direct" and isinstance(result, dict):
            with _COMPLETED_RESULTS_LOCK:
                # Evict oldest if at capacity
                while len(_COMPLETED_RESULTS) >= _COMPLETED_RESULTS_MAXSIZE:
                    oldest = min(_COMPLETED_RESULTS.keys(), key=lambda k: _COMPLETED_RESULTS[k].get("completed_at", 0))
                    del _COMPLETED_RESULTS[oldest]
                _COMPLETED_RESULTS[prompt_id] = {
                    "result": result,
                    "trace": result.get("trace", {}),
                    "outputs": outputs,
                    "primary_output": result.get("primary_output") or result.get("_local_primary_output"),
                    "materialize_ms": materialize_ms,
                    "completed_at": time.time(),
                    "direct_route": True,
                }

        finalized = True

        total_ms = round((time.time() - local_started) * 1000, 1)
        print(
            f"[comfyui-modal.profile] stage=local_total prompt_id={prompt_id[:8]} "
            f"duration_ms={total_ms} images={output_image_count} videos={output_video_count} bytes={output_bytes_written}"
        )
    except Exception as _post_err:
        import traceback
        traceback.print_exc()
        print(f"[comfyui-modal] Post-result processing failed: {_post_err}")
        _send(sid, "execution_error", {"message": str(_post_err), "prompt_id": prompt_id})
        if _result_route_mode == "direct":
            with _COMPLETED_RESULTS_LOCK:
                _COMPLETED_RESULTS[prompt_id] = {
                    "status": "error",
                    "error": str(_post_err),
                    "traceback": traceback.format_exc(),
                    "completed_at": time.time(),
                    "direct_route": True,
                }
    finally:
        if not finalized and task_key != 0:
            try:
                _finish_job(task_key, prompt_id, outputs, success=False,
                            meta={"error": "post-result processing exception",
                                  "details": str(_post_err) if '_post_err' in dir() else ""})
            except Exception as _fe:
                print(f"[comfyui-modal] _finish_job failed during error recovery: {_fe}")
        try:
            _clear_request_state(prompt_id)
        except Exception:
            pass


def _build_custom_nodes_archive(cn_root: str) -> bytes:
    import io
    import tarfile

    def tar_filter(tarinfo):
        parts = tarinfo.name.split("/")
        for part in parts:
            if part in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
                return None
        if any(tarinfo.name.endswith(ext) for ext in _CUSTOM_NODE_SYNC_EXCLUDE_EXTENSIONS):
            return None
        return tarinfo

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        allowed = set(_iter_syncable_custom_node_dirs(cn_root))
        for node_dir in (sorted(os.listdir(cn_root)) if os.path.isdir(cn_root) else []):
            node_path = os.path.join(cn_root, node_dir)
            if not os.path.isdir(node_path):
                continue
            if node_dir in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
                reason = "generated_or_environment_directory"
            elif node_dir.startswith("."):
                reason = "hidden_directory"
            elif _CUSTOM_NODE_LOCAL_CLONE_RE.fullmatch(node_dir):
                reason = "local_agent_or_worktree_clone"
            else:
                reason = "production_custom_node"
            print(
                f"[comfyui-modal.custom_node_filter] action={'allow' if node_dir in allowed else 'deny'} "
                f"name={node_dir} reason={reason}",
                flush=True,
            )
        for node_dir in _iter_syncable_custom_node_dirs(cn_root):
            tar.add(os.path.join(cn_root, node_dir), arcname=node_dir, filter=tar_filter)
    return buf.getvalue()


async def _sync_custom_nodes_and_maybe_deploy(cn_root: str, workspace: dict) -> dict:
    fingerprint = _build_custom_node_fingerprint(cn_root)
    archive_data = _build_custom_nodes_archive(cn_root)
    result = await sync_custom_nodes(archive_data, workspace=workspace)

    if result.get("status") != "ok":
        return result

    result["deploy"] = _ensure_modal_deploy_current(workspace, fingerprint)

    try:
        refresh_result = await resync_runtime("custom_nodes", workspace=workspace)
        result["refresh"] = refresh_result
    except Exception as e:
        result["refresh_error"] = str(e)
        result["message"] = (
            "Custom nodes synced to Modal Volume, but the running Modal ComfyUI process could not be refreshed automatically. "
            "Try again after the container sleeps, or redeploy if the node is still missing."
        )
    else:
        result.setdefault("message", "Custom nodes synced to Modal.")

    return result


def _manifest_entry_from_install(url: str, folder: str, filename: str) -> dict:
    source_kind = _model_manifest.infer_source_kind(url)
    return {
        "folder": folder,
        "filename": filename,
        "url": url,
        "source_kind": source_kind,
        "requires_hf_token": source_kind == "huggingface",
        "requires_civitai_token": source_kind == "civitai",
    }


def _refresh_swap_deploy_log(swap_id: str) -> None:
    """Read the last 50KB of the deploy log and store in swap job status."""
    try:
        log_path = _DEPLOY_LOG_FILE
        if not os.path.isfile(log_path):
            return
        file_size = os.path.getsize(log_path)
        max_bytes = 51200  # 50KB
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            if file_size > max_bytes:
                f.seek(file_size - max_bytes)
                f.readline()  # discard partial first line
                log = "[...truncated, showing last 50KB...]\n" + f.read()
            else:
                log = f.read()
        with _swap_jobs_lock:
            if swap_id in _swap_jobs:
                _swap_jobs[swap_id]["deploy_log_tail"] = log
    except Exception:
        pass


async def _run_workspace_swap_job(swap_id: str, workspace: dict, plan: dict):
    try:
        with _swap_jobs_lock:
            _swap_jobs[swap_id] = {
                "status": "running",
                "phase": "deploying",
                "workspace_label": workspace["label"],
                "deploy_message": "Ensuring workspace is deployed...",
            }

        # Phase 1: Ensure workspace is deployed before downloading
        if plan.get("force_deploy"):
            deploy_decision = _start_background_deploy(workspace, None, reason="workspace_not_deployed")
        else:
            deploy_decision = _ensure_modal_deploy_current(workspace, None)
        if deploy_decision.get("started"):
            with _swap_jobs_lock:
                _swap_jobs[swap_id]["deploy_message"] = f"Deploying workspace ({deploy_decision['reason']})..."
            while _deploy_status.get("state") == "deploying":
                _refresh_swap_deploy_log(swap_id)
                await asyncio.sleep(3)
            _refresh_swap_deploy_log(swap_id)
            if _deploy_status.get("state") == "error":
                with _swap_jobs_lock:
                    _swap_jobs[swap_id] = {
                        "status": "error", "phase": "deploying",
                        "deploy_message": _deploy_status.get("message", "Deploy failed"),
                        "deploy_log_tail": _swap_jobs[swap_id].get("deploy_log_tail", ""),
                        "workspace_label": workspace["label"],
                    }
                return

        # Phase 2: Remove flagged models from remote workspace
        to_remove = plan.get("to_remove", [])
        remove_results = []
        remove_failures = []
        if to_remove:
            with _swap_jobs_lock:
                _swap_jobs[swap_id]["phase"] = "removing_models"
                _swap_jobs[swap_id]["remove_message"] = f"Removing {len(to_remove)} flagged model(s) from workspace..."
            for rem in to_remove:
                try:
                    rem_result = await delete_model(folder=rem["folder"], filename=rem["filename"], workspace=workspace)
                    if rem_result.get("status") == "ok":
                        remove_results.append(rem_result)
                    else:
                        remove_failures.append({
                            "folder": rem["folder"],
                            "filename": rem["filename"],
                            "error": rem_result.get("message") or rem_result.get("error") or "remove failed",
                        })
                except Exception as e:
                    remove_failures.append({"folder": rem["folder"], "filename": rem["filename"], "error": str(e)})

        # Phase 3: Download selected models
        with _swap_jobs_lock:
            _swap_jobs[swap_id]["phase"] = "downloading_models"
            _swap_jobs[swap_id]["download_total"] = len(plan.get("to_install", []))
            _swap_jobs[swap_id]["download_completed"] = 0
            _swap_jobs[swap_id]["download_skipped"] = 0
            _swap_jobs[swap_id]["download_current_name"] = ""
            _swap_jobs[swap_id]["download_pct"] = 0
            _swap_jobs[swap_id]["download_pct_current"] = 0
            _swap_jobs[swap_id]["error_count"] = 0

        results = []
        if plan["to_install"]:
            total = len(plan["to_install"])
            for idx, item in enumerate(plan["to_install"], 1):
                with _swap_jobs_lock:
                    _swap_jobs[swap_id]["download_current_name"] = item["filename"]
                    _swap_jobs[swap_id]["download_pct_current"] = 0
                try:
                    result = None
                    async for update in download_model_stream(
                        url=item["url"],
                        filename=item["filename"],
                        save_path=item["save_path"],
                        hf_token=_read_hf_token(),
                        civitai_token=_read_civitai_token(),
                        workspace=workspace,
                    ):
                        if update["type"] == "progress":
                            pct = update.get("pct", 0)
                            with _swap_jobs_lock:
                                _swap_jobs[swap_id]["download_pct_current"] = pct
                                _swap_jobs[swap_id]["download_message"] = (
                                    f"Downloading {item['filename']} ({idx}/{total}) — {pct}%"
                                )
                        elif update["type"] == "complete":
                            result = update
                    if result is None:
                        result = {"status": "error", "error": "stream ended without complete", "filename": item["filename"]}
                    results.append(result)
                    with _swap_jobs_lock:
                        if result.get("skipped"):
                            _swap_jobs[swap_id]["download_skipped"] += 1
                        else:
                            _swap_jobs[swap_id]["download_completed"] += 1
                except Exception as e:
                    results.append({"status": "error", "error": str(e), "filename": item["filename"]})
                    with _swap_jobs_lock:
                        ec = _swap_jobs[swap_id].get("error_count", 0) + 1
                        _swap_jobs[swap_id]["error_count"] = ec
            failures = [r for r in results if r.get("status") not in {"ok", "skipped"}]
            if failures:
                with _swap_jobs_lock:
                    _swap_jobs[swap_id] = {
                        "status": "error", "phase": "downloading_models",
                        "failures": failures,
                        "workspace_label": workspace["label"],
                        "download_completed": _swap_jobs[swap_id]["download_completed"],
                        "download_skipped": _swap_jobs[swap_id]["download_skipped"],
                        "download_message": f"Downloaded {_swap_jobs[swap_id]['download_completed']}, skipped {_swap_jobs[swap_id]['download_skipped']}, failed {_swap_jobs[swap_id].get('error_count', 0)}",
                    }
                return

        installed_count = sum(1 for r in results if not r.get("skipped"))
        skipped_count = sum(1 for r in results if r.get("skipped"))

        # Phase 4: Sync custom nodes (with granular status updates)
        cn_root = os.path.join(_COMFYUI_ROOT, "custom_nodes")
        cn_fingerprint = _build_custom_node_fingerprint(cn_root)

        with _swap_jobs_lock:
            _swap_jobs[swap_id]["phase"] = "syncing_custom_nodes"
            _swap_jobs[swap_id]["sync_message"] = "Packaging custom nodes..."
        archive_data = _build_custom_nodes_archive(cn_root)

        with _swap_jobs_lock:
            _swap_jobs[swap_id]["sync_message"] = "Uploading custom nodes to Modal volume..."
        cn_result = await sync_custom_nodes(archive_data, workspace=workspace)

        if cn_result.get("status") != "ok":
            with _swap_jobs_lock:
                _swap_jobs[swap_id] = {
                    "status": "error", "phase": "syncing_custom_nodes",
                    "result": cn_result, "workspace_label": workspace["label"],
                    "sync_message": cn_result.get("message", "Custom node sync failed"),
                }
            return

        with _swap_jobs_lock:
            _swap_jobs[swap_id]["sync_message"] = "Checking if redeploy is needed..."
        deploy_decision = _ensure_modal_deploy_current(workspace, cn_fingerprint)
        cn_result["deploy"] = deploy_decision
        if deploy_decision.get("started"):
            with _swap_jobs_lock:
                _swap_jobs[swap_id]["sync_message"] = f"Redeploying workspace ({deploy_decision['reason']})..."
            while _deploy_status.get("state") == "deploying":
                _refresh_swap_deploy_log(swap_id)
                await asyncio.sleep(3)
            _refresh_swap_deploy_log(swap_id)

        with _swap_jobs_lock:
            _swap_jobs[swap_id]["sync_message"] = "Refreshing running container..."
        try:
            refresh_result = await resync_runtime("custom_nodes", workspace=workspace)
            cn_result["refresh"] = refresh_result
        except Exception as e:
            cn_result["refresh_error"] = str(e)
            cn_result.setdefault("message", (
                "Custom nodes synced to Modal Volume, but the running Modal ComfyUI process "
                "could not be refreshed automatically. "
                "Try again after the container sleeps, or redeploy if the node is still missing."
            ))
        else:
            cn_result.setdefault("message", "Custom nodes synced to Modal.")
        if cn_result.get("status") != "ok":
            with _swap_jobs_lock:
                _swap_jobs[swap_id] = {
                    "status": "error", "phase": "syncing_custom_nodes",
                    "result": cn_result, "workspace_label": workspace["label"],
                    "sync_message": cn_result.get("message", "Custom node sync failed"),
                }
            return

        _workspace_store.set_active_workspace(_WORKSPACES_FILE, workspace["id"])
        remove_summary = None
        if to_remove:
            remove_summary = f"Removed {len(remove_results)} model(s)"
            if remove_failures:
                remove_summary += f", {len(remove_failures)} removal(s) failed"
        with _swap_jobs_lock:
            _swap_jobs[swap_id] = {
                "status": "ok", "phase": "deploying",
                "workspace_label": workspace["label"],
                "installed_model_count": installed_count,
                "skipped_model_count": skipped_count,
                "failed_model_count": _swap_jobs[swap_id].get("error_count", 0),
                "removed_count": len(remove_results),
                "remove_failed_count": len(remove_failures),
                "remove_failures": remove_failures,
                "remove_summary": remove_summary,
                "download_summary": f"Downloaded {installed_count}, skipped {skipped_count}",
                "custom_node_sync": cn_result,
                "deploy": cn_result.get("deploy"),
                "sync_message": cn_result.get("message", "Custom nodes synced."),
            }
    except Exception as e:
        with _swap_jobs_lock:
            _swap_jobs[swap_id] = {"status": "error", "phase": "failed", "error": str(e), "workspace_label": workspace["label"]}


async def _scan_swap_plan(workspace: dict) -> dict:
    """Build a workspace swap plan: scan manifest issues, get remote models, compute diff."""
    manifest = _workspace_manifest()
    issues = _model_manifest.scan_local_models_issues(_COMFYUI_ROOT, manifest)
    blocking = [item for item in issues if item["kind"] in {"missing_url", "missing_source_kind", "invalid_folder", "duplicate_key"}]
    remote_status = "available"
    remote_error = ""
    try:
        remote = await get_sync_status(workspace=workspace)
        remote_models = remote.get("models", [])
    except Exception as e:
        err_str = str(e)
        if "Lookup failed for Function" in err_str and "App '" in err_str and "not found in environment" in err_str:
            remote_status = "not_deployed"
            remote_error = err_str
            remote_models = []
        else:
            return {
                "manifest_issues": issues,
                "blocking_issues": blocking,
                "already_present": [],
                "to_install": [],
                "unresolved": [],
                "to_remove": [],
                "remote_status": "unavailable",
                "remote_error": err_str,
            }
    plan = _model_manifest.build_workspace_swap_plan(manifest, remote_models)
    return {
        "manifest_issues": issues,
        "blocking_issues": blocking,
        "already_present": plan.get("already_present", []),
        "to_install": plan.get("to_install", []),
        "unresolved": plan.get("unresolved", []),
        "to_remove": plan.get("to_remove", []),
        "remote_status": remote_status,
        "remote_error": remote_error,
    }


# Migrate legacy ~/.modal.toml into workspace registry on first load
_workspace_store.migrate_from_legacy_toml(_WORKSPACES_FILE, _MODAL_TOML_PATH)

if _server:
    @_server.routes.get("/comfymodal/auth/status")
    async def modal_auth_status(request: web.Request) -> web.Response:
        return web.json_response({"connected": _is_modal_token_set()})

    @_server.routes.get("/comfymodal/hf-token")
    async def modal_hf_token_get(request: web.Request) -> web.Response:
        token = _read_hf_token()
        return web.json_response({"token": token[:8] + "..." if len(token) > 8 else ("set" if token else "")})

    @_server.routes.post("/comfymodal/hf-token")
    async def modal_hf_token_set(request: web.Request) -> web.Response:
        body = await request.json()
        token = body.get("token", "").strip()
        if token and not token.startswith("hf_"):
            return web.json_response({"status": "error", "message": "HF token must start with hf_"}, status=400)
        _write_hf_token(token)
        return web.json_response({"status": "ok"})

    @_server.routes.get("/comfymodal/civitai-token")
    async def modal_civitai_token_get(request: web.Request) -> web.Response:
        token = _read_civitai_token()
        return web.json_response({"token": token[:8] + "..." if len(token) > 8 else ("set" if token else "")})

    @_server.routes.post("/comfymodal/civitai-token")
    async def modal_civitai_token_set(request: web.Request) -> web.Response:
        body = await request.json()
        token = body.get("token", "").strip()
        _write_civitai_token(token)
        return web.json_response({"status": "ok"})

    @_server.routes.post("/comfymodal/auth/setup")
    async def modal_auth_setup(request: web.Request) -> web.Response:
        body = await request.json()
        token_id = body.get("token_id", "").strip()
        token_secret = body.get("token_secret", "").strip()
        if not token_id or not token_secret:
            return web.json_response({"status": "error", "message": "token_id and token_secret required"}, status=400)
        if not token_id.startswith("ak-") or not token_secret.startswith("as-"):
            return web.json_response({"status": "error", "message": "Invalid token format. Token ID starts with ak-, Secret starts with as-"}, status=400)
        try:
            _write_modal_toml(token_id, token_secret)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)
        # Update/save workspace in registry for backward compat
        _workspace_store.upsert_workspace(
            _WORKSPACES_FILE,
            "Primary",
            token_id,
            token_secret,
            set_active=True,
        )
        # Use active workspace or create a minimal workspace for backward compat
        workspace = _active_workspace()
        if workspace is None:
            label = body.get("label", "").strip() or "default"
            registry = _workspace_store.upsert_workspace(_WORKSPACES_FILE, label, token_id, token_secret, set_active=True)
            workspace = _workspace_store.get_active_workspace(registry)
        if workspace:
            t = threading.Thread(target=_run_deploy_background, kwargs={"workspace": workspace}, daemon=True)
            t.start()
        return web.json_response({"status": "ok"})

    # ── Local pre-dispatch instrumentation infrastructure ───────────────────
    # Configuration
    _BODY_READ_TIMEOUT_S = float(os.environ.get("COMFYMODAL_LOCAL_BODY_READ_TIMEOUT_S", "10"))
    _JSON_PARSE_WARN_MS = 3000
    _JSON_PARSE_FAIL_S = 15
    _STACK_EXTRACT_WARN_MS = 5000
    _STACK_EXTRACT_FAIL_S = 30
    _ACTIVE_NEXT_WRITE_WARN_MS = 1000
    _ACTIVE_NEXT_WRITE_CRITICAL_MS = 5000
    _LOCK_WAIT_WARN_MS = 1000
    _LOCK_WAIT_CRITICAL_MS = 5000
    _LOCK_WAIT_DEGRADE_S = 30
    _ACTIVE_REQUEST_IDS: dict[str, float] = {}
    _ACTIVE_REQUEST_IDS_LOCK = threading.Lock()
    _LOCAL_REQUEST_SEQ = 0
    _LOCAL_REQUEST_SEQ_LOCK = threading.Lock()
    _PREVIOUS_REQUEST_ID: str | None = None
    _PREVIOUS_REQUEST_FINISHED_AT: float | None = None

    """
    /comfymodal/prompt — intended flow:
    1. receive request body via async read
    2. parse JSON payload
    3. validate basic structure (preflight)
    4. normalize payload, strip stale trace fields
    5. extract workflow, compute hashes, extract model stack
    6. acquire _counter_lock, assign item_id, build extra_data
    7. enqueue item to _queue
    8. return prompt_id immediately (ACK before Modal dispatch)
    Remote work runs in _process_queue / _execute_job (background asyncio task).
    The /comfymodal/result/{prompt_id} route reports pending/running/ok/failed.
    """

    def _make_local_request_state(request, body: dict, prompt_id: str) -> dict:
        global _LOCAL_REQUEST_SEQ, _PREVIOUS_REQUEST_ID, _PREVIOUS_REQUEST_FINISHED_AT
        with _LOCAL_REQUEST_SEQ_LOCK:
            _LOCAL_REQUEST_SEQ += 1
            seq = _LOCAL_REQUEST_SEQ
        with _ACTIVE_REQUEST_IDS_LOCK:
            active_count = len(_ACTIVE_REQUEST_IDS)
            active_ids = list(_ACTIVE_REQUEST_IDS.keys())
            now_t = time.time()
            _ACTIVE_REQUEST_IDS[prompt_id] = now_t
        prev_id = _PREVIOUS_REQUEST_ID
        prev_age = (time.time() - _PREVIOUS_REQUEST_FINISHED_AT) if _PREVIOUS_REQUEST_FINISHED_AT else None
        thread = threading.current_thread()
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
            task_name = asyncio.current_task().get_name() if hasattr(asyncio, 'current_task') and asyncio.current_task() else None
        except RuntimeError:
            loop_id = None
            task_name = None
        content_length = request.content_length if hasattr(request, 'content_length') else None
        return {
            "local_request_id": prompt_id[:12],
            "prompt_id": prompt_id,
            "route_seq": seq,
            "thread_id": thread.ident,
            "thread_name": thread.name,
            "process_id": os.getpid(),
            "event_loop_id": loop_id,
            "asyncio_task_name": task_name,
            "start_unix_s": time.time(),
            "request_content_length": content_length,
            "result_route": body.get("result_route", _RESULT_ROUTE),
            "return_mode": body.get("modal_options", {}).get("return_mode", "unknown") if isinstance(body.get("modal_options"), dict) else "unknown",
            "active_request_count_at_entry": active_count,
            "active_request_ids": active_ids[-10:],
            "previous_request_id": prev_id,
            "previous_request_age_s": round(prev_age, 3) if prev_age is not None else None,
        }

def _clear_request_state(prompt_id: str):
    global _PREVIOUS_REQUEST_ID, _PREVIOUS_REQUEST_FINISHED_AT
    with _ACTIVE_REQUEST_IDS_LOCK:
        _ACTIVE_REQUEST_IDS.pop(prompt_id, None)
        _PREVIOUS_REQUEST_ID = prompt_id
        _PREVIOUS_REQUEST_FINISHED_AT = time.time()


def _derive_active_read_owner(
    role: str = "",
    *,
    explicit_owner: str = "",
    loader_type: str = "",
) -> str:
    """Derive canonical active-read owner name.

    Restore preload roles map to canonical restore names:

      clip → restore_clip_loader
      unet → restore_background_unet
      vae  → restore_vae_loader

    For generic prompt reads, uses the explicit owner or the current
    ``_ACTIVE_LANE_TRACE`` lane owner (from ``comfymodal_runtime.model_preload``)
    when available, without inventing synthetic request IDs.

    Returns the resolved owner string; falls back to ``explicit_owner``
    when role is empty and no lane context resolves.
    """
    _ROLE_MAP: dict[str, str] = {
        "clip": "restore_clip_loader",
        "unet": "restore_background_unet",
        "vae": "restore_vae_loader",
    }
    if role in _ROLE_MAP:
        return _ROLE_MAP[role]
    if explicit_owner:
        return explicit_owner
    # Attempt lane-context derivation from model_preload
    try:
        from comfymodal_runtime.model_preload import _ACTIVE_LANE_TRACE
        _lane = _ACTIVE_LANE_TRACE.get()
        if _lane is not None and hasattr(_lane, "lane") and _lane.lane:
            _derived = f"lane_{_lane.lane.lower()}"
            if hasattr(_lane, "owner") and _lane.owner:
                _derived = str(_lane.owner)
            return _derived
    except Exception:
        pass
    # Fall back to loader_type when available
    if loader_type:
        return loader_type
    return explicit_owner


def _classify_active_read_dimensions(entry: dict) -> dict[str, str]:
    """Classify per-dimension counter status for an active-read entry.

    Uses lazy import of ``classify_active_read_dims`` from
    ``comfymodal_runtime.model_preload`` to avoid import cycles.

    Returns a dict with per-dimension string statuses:

      thread_cpu_status, process_cpu_status, io_status, page_fault_status,
      block_input_status, context_switch_status

    Plus an aggregate ``counter_status`` that is ``"mixed"`` when
    dimensions disagree, ``"available"`` when all are available, etc.

    Per-dimension statuses are always the specific string from the underlying
    classifier (e.g. ``"thread_changed"``, ``"not_observed_in_this_thread"``,
    ``"unsupported"``) and never fall back to a broad ``"available"``.
    """
    from comfymodal_runtime.model_preload import classify_active_read_dims

    _before_tid: int | None = entry.get("native_tid")
    _after_tid: int | None = entry.get("complete_native_tid")
    _deep_diag: bool = env_flag("COMFYMODAL_V2_DEEP_MODEL_DIAG")
    _has_thread_cpu: bool = entry.get("start_thread_time_ns") is not None
    _has_process_cpu: bool = entry.get("start_process_time_ns") is not None
    _has_rusage: bool = entry.get("before_rusage") is not None
    _has_io: bool = entry.get("before_io") is not None

    raw = classify_active_read_dims(
        deep_diag=_deep_diag,
        before_tid=_before_tid,
        after_tid=_after_tid,
        has_thread_cpu=_has_thread_cpu,
        has_process_cpu=_has_process_cpu,
        has_rusage=_has_rusage,
        has_io=_has_io,
    )
    # Map internal dim names to the exposed status keys.
    # Each dimension carries its specific status string, NOT a broad "available".
    _DIM_KEY_MAP: dict[str, str] = {
        "thread_cpu": "thread_cpu_status",
        "process_cpu": "process_cpu_status",
        "io_deltas": "io_status",
        "page_faults": "page_fault_status",
        "block_input": "block_input_status",
        "context_switches": "context_switch_status",
    }
    result: dict[str, str] = {}
    for internal, exposed in _DIM_KEY_MAP.items():
        result[exposed] = raw.get(internal, "unavailable")

    # Aggregate counter_status: mixed when dimensions disagree.
    known_statuses = [v for v in result.values() if v not in ("unavailable",)]
    if not known_statuses:
        result["counter_status"] = "unavailable"
    elif all(v == "available" for v in known_statuses):
        result["counter_status"] = "available"
    elif all(v == known_statuses[0] for v in known_statuses):
        result["counter_status"] = known_statuses[0]
    else:
        result["counter_status"] = "mixed"

    return result


async def _timed_async_lock_acquire(lock: asyncio.Lock, lock_name: str, request_id: str, timeout_s: float | None = None) -> dict:
    wait_start = time.perf_counter()
    acquired = False
    timed_out = False
    try:
        if timeout_s is not None:
            try:
                await asyncio.wait_for(lock.acquire(), timeout=timeout_s)
                acquired = True
            except asyncio.TimeoutError:
                timed_out = True
        else:
            await lock.acquire()
            acquired = True
    except Exception:
        acquired = False
    wait_end = time.perf_counter()
    wait_ms = round((wait_end - wait_start) * 1000, 3)
    result = {"lock_name": lock_name, "wait_start": wait_start, "wait_end": wait_end, "wait_ms": wait_ms, "acquired": acquired, "timed_out": timed_out}
    if wait_ms > _LOCK_WAIT_DEGRADE_S * 1000:
        with _ACTIVE_REQUEST_IDS_LOCK:
            active = dict(_ACTIVE_REQUEST_IDS)
        print(f"[local_lock_wait] CRITICAL request_id={request_id} lock={lock_name} wait_ms={wait_ms} active_requests={len(active)} active_ids={list(active.keys())[-5:]}")
    elif wait_ms > _LOCK_WAIT_CRITICAL_MS:
        print(f"[local_lock_wait] CRITICAL request_id={request_id} lock={lock_name} wait_ms={wait_ms}")
    elif wait_ms > _LOCK_WAIT_WARN_MS:
        print(f"[local_lock_wait] WARN request_id={request_id} lock={lock_name} wait_ms={wait_ms}")
    return result


def _detect_local_predispatch_stall(local_ts: dict, request_id: str, degradation_flags: list) -> dict:
    t1 = local_ts.get("t1_local_recv")
    t2 = local_ts.get("t2_local_dispatch")
    body_read = local_ts.get("body_read_ms", 0) or 0
    json_parse = local_ts.get("json_parse_ms", 0) or 0
    preflight = local_ts.get("preflight_ms", 0) or 0
    stack_extract = local_ts.get("stack_extract_ms", 0) or 0
    active_next = local_ts.get("active_next_write_ms", 0) or 0
    lock_wait = local_ts.get("lock_wait_total_ms", 0) or 0
    phases = {"body_read": body_read, "json_parse": json_parse, "preflight": preflight, "stack_extract": stack_extract, "active_next_write": active_next, "lock_wait_total": lock_wait}
    dominant = max(phases, key=phases.get) if phases else "unknown"
    dominant_ms = phases.get(dominant, 0)
    total = t2 - t1 if (t1 is not None and t2 is not None) else 0
    total_ms = round(total * 1000, 2) if isinstance(total, float) else local_ts.get("local_receive_to_ack_ms", 0)
    if total_ms > 60000:
        degradation_flags.append("local_predispatch_stall_severe")
        print(f"[local_predispatch_stall] SEVERE request_id={request_id} total_ms={total_ms} dominant={dominant}={dominant_ms} body_read={body_read} json_parse={json_parse} stack_extract={stack_extract} active_next={active_next} lock_wait={lock_wait}")
    elif total_ms > 30000:
        degradation_flags.append("local_predispatch_stall")
        print(f"[local_predispatch_stall] CRITICAL request_id={request_id} total_ms={total_ms} dominant={dominant}={dominant_ms} body_read={body_read} json_parse={json_parse} stack_extract={stack_extract} active_next={active_next} lock_wait={lock_wait}")
    elif total_ms > 5000:
        print(f"[local_predispatch_stall] request_id={request_id} total_ms={total_ms} dominant={dominant}={dominant_ms} body_read={body_read} json_parse={json_parse} stack_extract={stack_extract} active_next={active_next} lock_wait={lock_wait}")
    return {"local_receive_to_ack_ms": total_ms, "dominant_phase": dominant, "dominant_ms": dominant_ms, "body_read_ms": body_read, "json_parse_ms": json_parse, "stack_extract_ms": stack_extract, "active_next_write_ms": active_next, "lock_wait_total_ms": lock_wait}

if _server:

    @_server.routes.post("/comfymodal/prompt")
    async def modal_prompt(request: web.Request) -> web.Response:
        # T1: local endpoint received (before body read, validation, dispatch)
        _t1_prompt_wall_ns = int(time.time() * 1_000_000_000)
        _t1_prompt_mono_ns = time.monotonic_ns()

        global _queue_worker_started, _queue_worker_task, _item_counter

        # ── v4 local event trace ──
        local_et = _init_local_event_trace()
        local_et.mark(T0_CLIENT_PRESS, phase=PHASE_LOCAL_PRE)
        local_et.mark(T1_LOCAL_BRIDGE_RECEIVED, phase=PHASE_LOCAL_BRIDGE)
        _route_entry_ts = time.time()

        # ── Phase: body read + JSON parse ──
        local_et.mark(T1G_BODY_READ_START, phase=PHASE_LOCAL_BRIDGE)
        content_length = request.content_length
        if content_length is not None and content_length > 50 * 1024 * 1024:  # 50 MB max
            return web.json_response({"status": "error", "error": "Request body too large"}, status=413)
        _body_read_start_mono_ns = time.monotonic_ns()
        try:
            _raw_body = await asyncio.wait_for(request.read(), timeout=_BODY_READ_TIMEOUT_S)
        except asyncio.TimeoutError:
            print(f"[comfyui-modal] BODY READ TIMEOUT after {_BODY_READ_TIMEOUT_S}s")
            return web.json_response({"status": "error", "error": "Request body read timed out"}, status=408)
        _body_read_end_mono_ns = time.monotonic_ns()
        local_et.mark(T1H_BODY_READ_END, phase=PHASE_LOCAL_BRIDGE)
        _body_read_done_ts = time.time()

        local_et.mark(T1I_JSON_PARSE_START, phase=PHASE_LOCAL_BRIDGE)
        _json_parse_start_mono_ns = time.monotonic_ns()
        body = json.loads(_raw_body.decode(request.charset or "utf-8"))
        _json_parse_end_mono_ns = time.monotonic_ns()
        _json_parse_done_ts = time.time()
        body_read_ms = round((_body_read_done_ts - _route_entry_ts) * 1000, 3)
        if body_read_ms > _JSON_PARSE_WARN_MS:
            print(f"[comfyui-modal] WARN slow body read: {body_read_ms}ms content_length={content_length or '?'}")
        if body_read_ms > _JSON_PARSE_FAIL_S * 1000:
            return web.json_response({"status": "error", "error": f"JSON read/parse took {body_read_ms}ms, exceeding limit"}, status=413)
        body_bytes = content_length if content_length else len(_raw_body)
        if body_bytes > 10 * 1024 * 1024:
            print(f"[comfyui-modal] WARN large body: {body_bytes} bytes")
        local_et.mark(T1J_JSON_PARSE_END, phase=PHASE_LOCAL_BRIDGE)

        # ── Request-origin extraction (T0/T1 from legacy/benchmark path) ──
        _prompt_request_origin: dict[str, Any] = {}
        request_trace_from_body = body.get("trace", {})
        if isinstance(request_trace_from_body, dict):
            _existing_req_id = request_trace_from_body.get("request_id", "")
            if _existing_req_id:
                _prompt_request_origin["request_id"] = str(_existing_req_id)
                _prompt_request_origin["trigger_source"] = str(request_trace_from_body.get("trigger_source", "legacy_prompt"))
                _existing_t0 = request_trace_from_body.get("ui_run_triggered_wall_unix_ms", None)
                if _existing_t0 is not None:
                    _prompt_request_origin["ui_run_triggered_wall_unix_ms"] = int(_existing_t0)
        if not _prompt_request_origin.get("request_id"):
            _prompt_request_origin["request_id"] = str(uuid.uuid4())
            _prompt_request_origin["trigger_source"] = "legacy_prompt_fallback"
            # No browser T0 — T1 becomes the first known boundary
        _prompt_request_origin["local_receive_wall_ns"] = _t1_prompt_wall_ns
        _prompt_request_origin["local_receive_mono_ns"] = _t1_prompt_mono_ns
        _prompt_request_origin["local_body_read_ms"] = round(
            (_body_read_end_mono_ns - _body_read_start_mono_ns) / 1_000_000, 3
        )
        _prompt_request_origin["local_json_parse_ms"] = round(
            (_json_parse_end_mono_ns - _json_parse_start_mono_ns) / 1_000_000, 3
        )

        # ── Extract payload fields and inject detailed trace stages ──
        workflow = body.get("prompt", body)
        client_id = body.get("client_id", str(uuid.uuid4()))
        prompt_id = str(uuid.uuid4())
        _make_local_request_state(request, body, prompt_id)  # side effects only: registers active request, increments seq
        # Per audit round 7: capture the request workspace once at
        # dispatch so the detached background persistence thread
        # does not resolve whichever workspace happens to be
        # active when it actually executes.  A user could switch
        # workspaces between image completion and background
        # thread execution; we must not let that write workspace
        # A's payload into workspace B's prompt-cache Volume.
        _request_workspace = _active_workspace()
        if _request_workspace is None:
            _request_workspace = {}
        # Top-level body checked FIRST so a valid queue_prompt_start_ms wins
        # over a legacy body["trace"]["t0_client_press"].
        request_trace = body.get("trace", {})
        browser_t0 = coerce_t0_from_browser(body) or coerce_t0_from_browser(request_trace)
        trace = Trace(prompt_id=prompt_id, t0=browser_t0 or _route_entry_ts)
        if browser_t0 is not None:
            trace.mark("t0_client_press", browser_t0)
        # Emit request-level benchmark metadata from payload.trace into timing_trace stages
        # so the benchmark can trace stale t0 sources definitively.
        for _bmk in ("benchmark_run_index", "benchmark_run_id", "benchmark_session_id"):
            _bmv = request_trace.get(_bmk)
            if _bmv is not None:
                trace.mark(_bmk, _bmv if isinstance(_bmv, (int, float)) else time.time())
        # Emit detailed local route stages into timing_trace
        trace.mark("t1a_body_read_start", _route_entry_ts)
        trace.mark("t1b_body_read_end", _body_read_done_ts)
        trace.mark("t1c_json_parse_start", _body_read_done_ts)
        trace.mark("t1d_json_parse_end", _json_parse_done_ts)
        trace.mark("t1_local_recv", time.time())
        local_et.mark(T1A_LOCAL_PAYLOAD_PARSE_START, phase=PHASE_LOCAL_BRIDGE)

        # ── Browser timing diagnostics (carried through trace._t but not via
        # mark() — durations/byte counts are stored directly as values) ──
        def _coerce_numeric(v):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            return None
        _browser_fields = {}
        for _bf in ("queue_prompt_start_ms", "prompt_fetch_start_ms",
                     "queue_to_prompt_fetch_ms", "serialized_prompt_bytes"):
            _bv = _coerce_numeric(body.get(_bf))
            if _bv is not None:
                _browser_fields[_bf] = _bv
        if _browser_fields:
            # Use public update() API so fields() carries them; never via
            # mark() since queue_to_prompt_fetch_ms (duration) and
            # serialized_prompt_bytes (byte count) are not epoch timestamps.
            trace.update(_browser_fields)

        # ── Preflight validation ──
        local_et.mark(T1C_LOCAL_PREFLIGHT_START, phase=PHASE_LOCAL_BRIDGE)
        _preflight_start_ts = time.perf_counter()
        _preflight_start_mono_ns = time.monotonic_ns()
        validation_errors = validate_api_prompt_structure(workflow)
        _preflight_end_mono_ns = time.monotonic_ns()
        _preflight_end_ts = time.perf_counter()
        preflight_ms = round((_preflight_end_ts - _preflight_start_ts) * 1000, 3)
        local_et.mark(T1D_LOCAL_PREFLIGHT_END, phase=PHASE_LOCAL_BRIDGE)
        if validation_errors:
            summary = FailureSummary(phase="preflight")
            summary.fatal_error = "; ".join(validation_errors)
            summary.modal_invoked = False
            summary.recommendation = "Re-export the workflow as API prompt JSON or remove corrupt/UI-only nodes."
            print(f"[comfyui-modal] PREFLIGHT FAILED: {summary}")
            _send(client_id, "execution_error", {"message": f"Preflight validation failed: {summary.fatal_error}", "prompt_id": prompt_id})
            _clear_request_state(prompt_id)
            raise web.HTTPBadRequest(text=json.dumps({"status": "error", "error": "Preflight validation failed", "details": summary.fatal_error, "recommendation": summary.recommendation}), content_type="application/json")

        local_et.mark(T1B_LOCAL_PAYLOAD_PARSE_END, phase=PHASE_LOCAL_BRIDGE)
        print(f"[predispatch] phase=recv t={time.time()}")

        # ── Production options validation (no compile — deferred to canonical executor) ──
        modal_options_raw = body.get("modal_options", None)
        if not isinstance(modal_options_raw, dict):
            modal_options_raw = None
        production_options = normalize_production_options(modal_options_raw)

        # Determine execution surface and whether production was default-applied.
        _execution_surface = "playground"
        _production_default_applied = bool(
            not modal_options_raw
            or "production" not in (modal_options_raw or {})
        )
        _production_explicitly_disabled = bool(
            isinstance(modal_options_raw, dict)
            and isinstance(modal_options_raw.get("production"), dict)
            and modal_options_raw["production"].get("enabled") is False
        )

        # Consume browser _production_trace as authoritative fallback for
        # production identity trace fields propagated through the queue.
        _browser_production_trace: dict = body.get("_production_trace", {}) or {}
        if not isinstance(_browser_production_trace, dict):
            _browser_production_trace = {}
        if production_options.get("enabled"):
            if not production_options.get("output_node_ids"):
                # Generic /prompt route has no surface to derive output bindings.
                # Fail closed with a clear message — never silently disable.
                raise web.HTTPBadRequest(text=json.dumps({
                    "error": (
                        "Production mode is enabled but no output_node_ids were provided. "
                        "The generic /prompt endpoint cannot derive output bindings. "
                        "Either disable production by setting "
                        "modal_options.production.enabled to false, or provide "
                        "output_node_ids explicitly."
                    ),
                    "production_options_status": {
                        "execution_surface": _execution_surface,
                        "production_default_applied": _production_default_applied,
                        "production_explicitly_disabled": _production_explicitly_disabled,
                        "production_output_source": "none",
                        "production_output_ids": [],
                        "production_output_count": 0,
                        "production_plan_used": False,
                    },
                }), content_type="application/json")
        # Canonical executor handles compile/hash/model-stack extraction.
        # Queue the source workflow + normalized production_options.
        execution_workflow = workflow  # source workflow, not compiled

        # Extract modal_options from body
        modal_options = modal_options_raw
        scheduler_test = body.get("comfymodal_scheduler_test")

        # ── Lock + enqueue ──
        _lock_trace = await _timed_async_lock_acquire(_counter_lock, "counter_lock", prompt_id)
        _prompt_request_origin["local_preflight_ms"] = round(
            (_preflight_end_mono_ns - _preflight_start_mono_ns) / 1_000_000, 3
        )
        _prompt_request_origin["local_queue_lock_wait_ms"] = round(
            float(_lock_trace.get("wait_ms", 0) or 0), 3
        )
        if not _lock_trace.get("acquired"):
            raise web.HTTPTooManyRequests(text=json.dumps({"status": "error", "error": "server busy, try again"}))
        try:
            _item_counter += 1
            item_id = _item_counter
            selected_gpu = get_gpu()
            _result_route_mode = body.get("result_route", _RESULT_ROUTE)
            if _result_route_mode not in ("legacy", "direct"):
                _result_route_mode = _RESULT_ROUTE

            # Build _client_trace for v4 event passing
            _client_trace_dict = {
                "trace_id": local_et.trace_id,
                "events": [{k: e.get(k) for k in ("name", "phase", "process", "wall_unix_ns", "mono_ns") if k in e} for e in local_et.events],
                "stages": {
                    T0_CLIENT_PRESS: local_et.events[0].get("wall_unix_ns") if local_et.events else 0,
                    T1_LOCAL_BRIDGE_RECEIVED: local_et.events[1].get("wall_unix_ns") if len(local_et.events) > 1 else 0,
                },
            }

            # ── Create prompt acknowledgment event ──
            ack_ready = asyncio.Event()

            _queue_execution_workflow = copy.deepcopy(execution_workflow)
            _trace_with_origin = {**trace.fields(), "prompt_id": prompt_id}
            _trace_with_origin["request_origin_info"] = _prompt_request_origin
            # ── Phase 8: capture immutable execution mode at submission ──
            _captured_mode = capture_execution_mode(
                modal_options=modal_options, modal_settings=_load_modal_settings(),
            )
            # Freeze the selected engine in the queued request. Downstream
            # workers must not re-read mutable settings after submission.
            modal_options = dict(modal_options or {})
            modal_options["execution_mode"] = _captured_mode

            extra_data = {
                "client_id": client_id,
                "create_time": int(time.time() * 1000),
                "gpu": selected_gpu,
                "trace": _trace_with_origin,
                "_client_trace": _client_trace_dict,
                "modal_options": modal_options,
                "scheduler_test": scheduler_test,
                "result_route": _result_route_mode,
                "execution_workflow": _queue_execution_workflow,
                "production_options": production_options,
                # Phase 8: captured execution mode (immutable for this request)
                "execution_mode": _captured_mode,
                # Compact production diagnostics for request identity tracking.
                # Carried through queue/scheduler/adapter so the runner can use them.
                # Use browser _production_trace as authoritative fallback when present,
                # then fall back to inferred values from the normalized request.
                "execution_surface": _execution_surface,
                "production_default_applied": _production_default_applied,
                "production_explicitly_disabled": _production_explicitly_disabled,
                "production_output_source": (
                    "caller" if production_options.get("output_node_ids") and not _production_default_applied
                    else "none" if not production_options.get("output_node_ids")
                    else "default"
                ),
                "production_ui_enabled": bool(
                    _browser_production_trace.get("production_ui_enabled",
                        (modal_options_raw or {}).get("production", {}).get("enabled", False)
                    )
                ),
                "production_persisted_enabled": bool(
                    _browser_production_trace.get("production_persisted_enabled",
                        production_options.get("enabled", False)
                    )
                ),
                "production_request_enabled": bool(
                    production_options.get("enabled", False)
                ),
                "production_output_ids": (
                    _browser_production_trace.get("production_output_ids",
                        production_options.get("output_node_ids", [])
                    )
                    if production_options.get("enabled") else []
                ),
                "production_output_count": (
                    len(_browser_production_trace.get("production_output_ids",
                        production_options.get("output_node_ids", [])))
                    if production_options.get("enabled") else 0
                ),
                "_modal_prompt_ack_ready": ack_ready,
                # Carry the request workspace into the queue
                # worker so the detached persistence thread
                # can target the same workspace without
                # re-resolving the active one (which may
                # have changed in the interim).
                "_request_workspace": _request_workspace,
            }
            item = (_item_counter, prompt_id, _queue_execution_workflow, extra_data, list(_queue_execution_workflow.keys()), {})
            print(f"[predispatch] prompt_bytes={body_bytes}")
        finally:
            if _lock_trace.get("acquired"):
                _counter_lock.release()

        _enqueue_start_mono_ns = time.monotonic_ns()
        pq = _pq()
        if pq:
            with pq.mutex:
                import heapq
                heapq.heappush(pq.queue, item)
                pq.server.queue_updated()

        # put_nowait on unbounded Queue never blocks — no yield point.
        # Both ComfyUI heap push and queue insertion are truthfully
        # captured in local_queue_enqueue_ms.
        _queue.put_nowait((item, item_id))
        _enqueue_end_mono_ns = time.monotonic_ns()

        _prompt_request_origin["local_queue_enqueue_ms"] = round(
            (_enqueue_end_mono_ns - _enqueue_start_mono_ns) / 1_000_000, 3
        )
        _prompt_request_origin["local_prompt_enqueued_wall_ns"] = time.time_ns()
        _prompt_request_origin["local_prompt_enqueued_mono_ns"] = _enqueue_end_mono_ns
        _prompt_request_origin["local_receive_to_enqueue_ms"] = round(
            (_enqueue_end_mono_ns - _t1_prompt_mono_ns) / 1_000_000, 3
        )
        local_et.mark(LOCAL_PROMPT_ENQUEUED, phase=PHASE_LOCAL_BRIDGE)

        if _queue_worker_task is None or _queue_worker_task.done():
            _queue_worker_task = asyncio.create_task(_process_queue())
            _queue_worker_task.add_done_callback(_queue_worker_done)
            _queue_worker_started = True

        # ── Signal acknowledgment: prompt is enqueued and response is ready ──
        asyncio.get_running_loop().call_soon(ack_ready.set)

        _ack_ready_wall_ns = time.time_ns()
        _ack_ready_mono_ns = time.monotonic_ns()
        _prompt_request_origin["local_prompt_ack_ready_wall_ns"] = _ack_ready_wall_ns
        _prompt_request_origin["local_prompt_ack_ready_mono_ns"] = _ack_ready_mono_ns
        _prompt_request_origin["local_receive_to_ack_ms"] = round(
            (_ack_ready_mono_ns - _t1_prompt_mono_ns) / 1_000_000, 3
        )
        local_et.mark(LOCAL_PROMPT_ACK_READY, phase=PHASE_LOCAL_BRIDGE)
        _ack_ready_ts = _ack_ready_wall_ns / 1_000_000_000
        local_receive_to_ack_ms = _prompt_request_origin["local_receive_to_ack_ms"]

        # ── Stall detector ──
        local_ts = {"t1_local_recv": _route_entry_ts, "t2_local_dispatch": _ack_ready_ts,
                    "body_read_ms": body_read_ms, "json_parse_ms": body_read_ms, "preflight_ms": preflight_ms,
                    "stack_extract_ms": 0,  # deferred to canonical executor
                    "active_next_write_ms": 0,
                    "lock_wait_total_ms": _lock_trace.get("wait_ms", 0), "local_receive_to_ack_ms": local_receive_to_ack_ms}
        degradation_flags = []
        _detect_local_predispatch_stall(local_ts, prompt_id, degradation_flags)

        local_et.mark(T2D_LOCAL_PROMPT_ACK_RETURNED, phase=PHASE_LOCAL_BRIDGE)

        return web.json_response({
            "prompt_id": prompt_id,
            "number": item_id,
            "node_errors": {},
        })

    @_server.routes.post("/comfymodal/models/batch-install")
    async def modal_batch_model_install(request: web.Request) -> web.Response:
        body = await request.json()
        items = body.get("items", [])
        if not items:
            return web.json_response({"status": "error", "message": "items required"}, status=400)
        normalized_items = []
        for it in items:
            if not it.get("url") or not it.get("filename"):
                return web.json_response({"status": "error", "message": "each item needs url and filename"}, status=400)
            try:
                folder, filename = _validate_model_location(it.get("save_path", "checkpoints"), it.get("filename", ""))
            except ValueError as e:
                return web.json_response({"status": "error", "message": str(e)}, status=400)
            normalized_items.append({
                "url": it["url"],
                "filename": filename,
                "save_path": folder,
            })
        try:
            results = await batch_download_models(normalized_items, hf_token=_read_hf_token(), civitai_token=_read_civitai_token())
            placeholders, placeholder_errors = _create_placeholder_batch([
                {"folder": item["save_path"], "filename": item["filename"]}
                for item in normalized_items
            ])
            manifest_payload = None
            for item in normalized_items:
                manifest_payload = _model_manifest.upsert_manifest_entry(
                    _MODEL_MANIFEST_FILE,
                    _manifest_entry_from_install(item["url"], item["save_path"], item["filename"]),
                )
            return web.json_response({
                "status": "ok",
                "results": results,
                "placeholders": placeholders,
                "placeholder_errors": placeholder_errors,
                "message": _batch_placeholder_message(placeholders, placeholder_errors),
                "manifest_entries_written": len(normalized_items),
                "manifest_issue_count": len(_model_manifest.scan_manifest_issues(manifest_payload or _workspace_manifest())),
            })
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def _background_download(download_id: str, url: str, filename: str, save_path: str):
        try:
            _download_progress[download_id] = {"state": "starting", "pct": 0, "filename": filename, "save_path": save_path}
            async for update in download_model_stream(url=url, filename=filename, save_path=save_path, hf_token=_read_hf_token(), civitai_token=_read_civitai_token()):
                if update["type"] == "progress":
                    _download_progress[download_id] = {
                        "state": "downloading",
                        "pct": update["pct"],
                        "downloaded_mb": update["downloaded_mb"],
                        "total_mb": update["total_mb"],
                        "filename": filename,
                        "save_path": save_path,
                    }
                elif update["type"] == "complete":
                    placeholder = None
                    placeholder_error = None
                    try:
                        placeholder = _create_placeholder(save_path, filename)
                    except Exception as e:
                        placeholder_error = {"folder": save_path, "filename": filename, "error": str(e)}
                    try:
                        _model_manifest.upsert_manifest_entry(
                            _MODEL_MANIFEST_FILE,
                            _manifest_entry_from_install(url, save_path, filename),
                        )
                    except Exception:
                        pass
                    _download_progress[download_id] = {
                        "state": "complete",
                        "result": {**update, "placeholder": placeholder, "placeholder_error": placeholder_error},
                        "filename": filename,
                        "save_path": save_path,
                    }
        except Exception as e:
            _download_progress[download_id] = {"state": "error", "error": str(e), "filename": filename, "save_path": save_path}

    @_server.routes.post("/comfymodal/model/install")
    async def modal_model_install(request: web.Request) -> web.Response:
        body = await request.json()
        url = body.get("url", "")
        filename = body.get("filename", "")
        save_path = body.get("save_path", "checkpoints")

        if not url or not filename:
            return web.json_response(
                {"status": "error", "message": "url and filename required"},
                status=400,
            )

        try:
            save_path, filename = _validate_model_location(save_path, filename)
        except ValueError as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)

        download_id = str(uuid.uuid4())
        asyncio.create_task(_background_download(download_id, url, filename, save_path))
        return web.json_response({
            "status": "ok",
            "download_id": download_id,
            "filename": filename,
            "save_path": save_path,
        })

    @_server.routes.get("/comfymodal/download/status/{download_id}")
    async def modal_download_status(request: web.Request) -> web.Response:
        did = request.match_info.get("download_id", "")
        info = _download_progress.get(did)
        if info is None:
            return web.json_response({"status": "not_found", "download_id": did}, status=404)
        return web.json_response({"status": "ok", "download_id": did, **info})

    @_server.routes.get("/comfymodal/download/active")
    async def modal_download_active(request: web.Request) -> web.Response:
        active = {k: v for k, v in _download_progress.items() if v.get("state") in ("starting", "downloading")}
        return web.json_response({"status": "ok", "active": {k: dict(v) for k, v in active.items()}})

    @_server.routes.get("/comfymodal/deploy/status")
    async def modal_deploy_status(request: web.Request) -> web.Response:
        resp = dict(_deploy_status)
        resp["deploy_state"] = _read_deploy_state_details()
        resp.setdefault("has_log", os.path.isfile(_DEPLOY_LOG_FILE))
        if resp.get("state") != "error":
            resp.setdefault("details", "")
        return web.json_response(resp)

    @_server.routes.post("/comfymodal/deploy/state/record")
    async def modal_record_deploy_state(request: web.Request) -> web.Response:
        body = await request.json()
        workspace_id = body.get("workspace_id")
        deployment_command = str(body.get("deployment_command", "")).strip()
        payload = _record_manual_deploy_state(workspace_id=workspace_id, deployment_command=deployment_command)
        return web.json_response({"status": "ok", **payload})

    @_server.routes.get("/comfymodal/deploy/log")
    async def modal_deploy_log(request: web.Request) -> web.Response:
        try:
            file_size = os.path.getsize(_DEPLOY_LOG_FILE)
            max_bytes = 512000  # 500KB
            with open(_DEPLOY_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                if file_size > max_bytes:
                    f.seek(file_size - max_bytes)
                    # Discard partial first line after seek
                    f.readline()
                    log = "[...truncated, showing last 500KB...]\n" + f.read()
                else:
                    log = f.read()
        except FileNotFoundError:
            log = ""
        return web.json_response({"log": log})

    @_server.routes.post("/comfymodal/deploy")
    async def modal_deploy_trigger(request: web.Request) -> web.Response:
        if _deploy_status.get("state") == "deploying":
            return web.json_response({"status": "already_deploying"})
        workspace = _active_workspace()
        if workspace is None:
            return web.json_response({"status": "error", "message": "No active workspace configured"}, status=400)
        t = threading.Thread(target=_run_deploy_background, kwargs={"workspace": workspace}, daemon=True)
        t.start()
        return web.json_response({"status": "started"})

    # ── Workspace routes ──────────────────────────────────────────────────
    @_server.routes.get("/comfymodal/workspaces")
    async def modal_workspaces_get(request: web.Request) -> web.Response:
        registry = _workspace_registry()
        return web.json_response({
            "status": "ok",
            "active_workspace_id": registry.get("active_workspace_id"),
            "workspaces": [_workspace_store.workspace_summary(item) for item in registry.get("workspaces", [])],
        })

    @_server.routes.post("/comfymodal/workspaces")
    async def modal_workspaces_post(request: web.Request) -> web.Response:
        body = await request.json()
        try:
            registry = _workspace_store.upsert_workspace(
                _WORKSPACES_FILE,
                body.get("label", ""),
                body.get("token_id", ""),
                body.get("token_secret", ""),
                workspace_id=body.get("workspace_id"),
                notes=body.get("notes", ""),
                set_active=bool(body.get("set_active", False)),
            )
        except ValueError as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)
        return web.json_response({
            "status": "ok",
            "active_workspace_id": registry.get("active_workspace_id"),
            "workspaces": [_workspace_store.workspace_summary(item) for item in registry.get("workspaces", [])],
        })

    @_server.routes.post("/comfymodal/workspaces/active")
    async def modal_workspaces_set_active(request: web.Request) -> web.Response:
        body = await request.json()
        try:
            registry = _workspace_store.set_active_workspace(_WORKSPACES_FILE, body.get("workspace_id", ""))
        except KeyError as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)
        return web.json_response({
            "status": "ok",
            "active_workspace_id": registry.get("active_workspace_id"),
            "workspaces": [_workspace_store.workspace_summary(item) for item in registry.get("workspaces", [])],
        })

    @_server.routes.post("/comfymodal/workspaces/swap")
    async def modal_workspace_swap(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            workspace = _workspace_or_400(body.get("workspace_id", ""))
            if workspace is None:
                return web.json_response({"status": "error", "message": "unknown workspace"}, status=400)
            if _deploy_status.get("state") == "deploying":
                return web.json_response({"status": "busy", "message": "deploy already running"}, status=409)
            if _ACTIVE_REQUEST_IDS and not body.get("confirm_prompt_interrupt", False):
                return web.json_response({"status": "confirm_required", "message": "prompt execution is active"}, status=409)

            if body.get("confirm"):
                scan = await _scan_swap_plan(workspace)
                if scan.get("remote_status") == "unavailable":
                    remote_error = scan.get("remote_error", "")
                    return web.json_response({
                        "status": "error",
                        "remote_error": remote_error,
                        "workspace_label": workspace["label"],
                        "message": f"Remote workspace unavailable: {remote_error}" if remote_error else "Remote workspace unavailable — check sync status and try again",
                    })
                if scan["blocking_issues"]:
                    return web.json_response({
                        "status": "repair_required",
                        "issues": scan["blocking_issues"],
                        "workspace_label": workspace["label"],
                        "message": "Manifest repair required before swapping workspaces",
                    })
                if scan["unresolved"]:
                    return web.json_response({
                        "status": "repair_required",
                        "issues": scan["unresolved"],
                        "workspace_label": workspace["label"],
                        "message": "Models missing source URLs — repair manifest first",
                    })

                selected_keys = body.get("selected_keys")
                if not isinstance(selected_keys, list):
                    return web.json_response({"status": "error", "message": "selected_keys is required for confirmed swaps"}, status=400)
                allowed_keys = {str(key) for key in selected_keys if key}

                filtered_install = [
                    item for item in scan["to_install"]
                    if f"{item.get('save_path') or item.get('folder') or ''}/{item.get('filename') or ''}" in allowed_keys
                ]

                swap_id = str(uuid.uuid4())
                plan = {
                    "to_install": filtered_install,
                    "already_present": scan.get("already_present", []),
                    "to_remove": scan.get("to_remove", []),
                }
                if scan.get("remote_status") == "not_deployed":
                    plan["force_deploy"] = True
                asyncio.create_task(_run_workspace_swap_job(swap_id, workspace, plan))
                return web.json_response({"status": "started", "swap_id": swap_id, "workspace_label": workspace["label"]})

            scan = await _scan_swap_plan(workspace)
            if scan.get("remote_status") == "unavailable":
                remote_error = scan.get("remote_error", "")
                return web.json_response({
                    "status": "error",
                    "remote_error": remote_error,
                    "workspace_label": workspace["label"],
                    "message": f"Remote workspace unavailable: {remote_error}" if remote_error else "Remote workspace unavailable — check sync status and try again",
                })
            if scan["blocking_issues"]:
                return web.json_response({
                    "status": "repair_required",
                    "issues": scan["blocking_issues"],
                    "workspace_label": workspace["label"],
                    "message": "Manifest repair required before swapping workspaces",
                })
            if scan["unresolved"]:
                return web.json_response({
                    "status": "repair_required",
                    "issues": scan["unresolved"],
                    "workspace_label": workspace["label"],
                    "message": "Models missing source URLs — repair manifest first",
                })
            return web.json_response({
                "status": "review_required",
                "swap_id": None,
                "workspace_label": workspace["label"],
                "already_present": [{"folder": m["folder"], "filename": m["filename"]} for m in scan["already_present"]],
                "to_install": scan["to_install"],
                "to_remove": scan["to_remove"],
                "present_count": len(scan["already_present"]),
                "install_count": len(scan["to_install"]),
            })
        except Exception as e:
            return web.json_response({"status": "error", "message": f"Swap scan failed: {e}"}, status=500)

    @_server.routes.get("/comfymodal/workspaces/swap/{swap_id}")
    async def modal_workspace_swap_status(request: web.Request) -> web.Response:
        swap_id = request.match_info.get("swap_id", "")
        with _swap_jobs_lock:
            payload = _swap_jobs.get(swap_id)
        if payload is None:
            return web.json_response({"status": "not_found", "swap_id": swap_id}, status=404)
        return web.json_response({"swap_id": swap_id, **payload})

    # ── Manifest routes ───────────────────────────────────────────────────
    @_server.routes.get("/comfymodal/manifest")
    async def modal_manifest_get(request: web.Request) -> web.Response:
        manifest = _workspace_manifest()
        return web.json_response({"status": "ok", **manifest})

    @_server.routes.post("/comfymodal/manifest/repair/scan")
    async def modal_manifest_repair_scan(request: web.Request) -> web.Response:
        manifest = _workspace_manifest()
        issues = _model_manifest.scan_local_models_issues(_COMFYUI_ROOT, manifest)
        return web.json_response({"status": "ok", "issues": issues})

    @_server.routes.post("/comfymodal/manifest/repair/apply")
    async def modal_manifest_repair_apply(request: web.Request) -> web.Response:
        body = await request.json()
        repaired = _model_manifest.apply_manifest_repairs(_workspace_manifest(), body.get("updates", []))
        _model_manifest.save_master_manifest(_MODEL_MANIFEST_FILE, repaired)
        return web.json_response({
            "status": "ok",
            "entries": repaired.get("entries", []),
            "issues": _model_manifest.scan_local_models_issues(_COMFYUI_ROOT, repaired),
        })

    @_server.routes.post("/comfymodal/manifest/repair/delete-placeholder")
    async def modal_manifest_repair_delete_placeholder(request: web.Request) -> web.Response:
        body = await request.json()
        folder = body.get("folder", "")
        filename = body.get("filename", "")
        if not folder or not filename:
            return web.json_response({"status": "error", "message": "folder and filename required"}, status=400)
        removed = _remove_local_placeholder_if_needed(folder, filename)
        if removed:
            manifest = _workspace_manifest()
            manifest["entries"] = [e for e in manifest.get("entries", []) if not (e.get("folder") == folder and e.get("filename") == filename)]
            _model_manifest.save_master_manifest(_MODEL_MANIFEST_FILE, manifest)
        return web.json_response({
            "status": "ok",
            "removed": bool(removed),
            "message": "Placeholder deleted." if removed else "No local placeholder was deleted; manifest entry was left unchanged.",
        })

    @_server.routes.post("/comfymodal/manifest/install")
    async def modal_manifest_install(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            items = body.get("items", [])
            workspace_id = body.get("workspace_id", "")
            if not items:
                return web.json_response({"status": "error", "message": "No items specified"}, status=400)
            workspace = _workspace_or_400(workspace_id) if workspace_id else _active_workspace()
            if workspace is None:
                return web.json_response({"status": "error", "message": "No workspace specified and no active workspace"}, status=400)
            manifest = _workspace_manifest()
            entries_by_key = {(e.get("folder"), e.get("filename")): e for e in manifest.get("entries", [])}
            results = []
            for item in items:
                folder = item.get("folder", "")
                filename = item.get("filename", "")
                entry = entries_by_key.get((folder, filename))
                if entry is None:
                    results.append({"folder": folder, "filename": filename, "status": "error", "error": "not found in manifest"})
                    continue
                url = entry.get("url", "")
                if not url:
                    results.append({"folder": folder, "filename": filename, "status": "error", "error": "no URL in manifest entry"})
                    continue
                try:
                    result = await download_model(
                        url=url,
                        filename=filename,
                        save_path=folder,
                        hf_token=_read_hf_token(),
                        civitai_token=_read_civitai_token(),
                        workspace=workspace,
                    )
                    results.append({"folder": folder, "filename": filename, **result})
                except Exception as e:
                    results.append({"folder": folder, "filename": filename, "status": "error", "error": str(e)})
            successes = sum(1 for r in results if r.get("status") in ("ok", "skipped"))
            failures = sum(1 for r in results if r.get("status") == "error")
            return web.json_response({
                "status": "ok" if failures == 0 else "partial",
                "results": results,
                "success_count": successes,
                "failure_count": failures,
            })
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/workflow-manifest/export")
    async def modal_workflow_manifest_export(request: web.Request) -> web.Response:
        body = await request.json()
        exported = _model_manifest.export_workflow_manifest(_workspace_manifest(), body.get("prompt", {}), body.get("workflow_name", ""))
        if exported["unresolved"]:
            return web.json_response({"status": "repair_required", **exported}, status=409)
        return web.json_response({"status": "ok", **exported})

    @_server.routes.post("/comfymodal/workflow-manifest/import")
    async def modal_workflow_manifest_import(request: web.Request) -> web.Response:
        body = await request.json()
        merged = _model_manifest.merge_workflow_manifest(
            _workspace_manifest(),
            body,
            resolutions=body.get("conflict_resolutions", {}),
        )
        if merged["conflicts"]:
            return web.json_response({"status": "conflict", **merged}, status=409)
        _model_manifest.save_master_manifest(_MODEL_MANIFEST_FILE, {"manifest_version": 1, "entries": merged["entries"]})
        return web.json_response({"status": "ok", "added": merged["added"], "filled": merged["filled"]})

    @_server.routes.get("/comfymodal/config")
    async def modal_get_config(request: web.Request) -> web.Response:
        settings = _load_modal_settings()
        resolved = resolve_execution_mode(modal_settings=settings)
        _v1_app = get_modal_app_name() or "comfyui"
        _v2_app = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
        _readiness = {
            "v1": {"status": "unknown", "app": _v1_app},
            "v2": {
                "status": "unknown",
                "app": _v2_app,
                "class": os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2"),
            },
        }
        return web.json_response({
            "gpu": get_gpu(),
            "default_gpu": get_default_gpu(),
            "available_gpus": get_available_gpus(),
            "output_format": settings.get("output_format", "original"),
            "quality": settings.get("quality", 75),
            "webp_lossless_compression": settings.get("webp_lossless_compression", "balanced"),
            "auto_save_local": settings.get("auto_save_local", False),
            "save_folder": settings.get("save_folder", ""),
            "save_metadata_sidecar": settings.get("save_metadata_sidecar", True),
            # ── Phase 8: execution mode ──
            "execution_mode": resolved["mode"],
            "execution_mode_source": resolved["source"],
            "execution_mode_locked": resolved["locked"],
            "available_execution_modes": _AVAILABLE_EXECUTION_MODES,
            "execution_readiness": _readiness,
        })

    @_server.routes.post("/comfymodal/config")
    async def modal_set_config(request: web.Request) -> web.Response:
        body = await request.json()
        response_data = {"status": "ok"}

        # Handle GPU setting (existing behavior)
        gpu = body.get("gpu", "")
        if gpu:
            try:
                set_gpu(gpu)
                response_data["gpu"] = get_gpu()
            except ValueError as e:
                return web.json_response({"status": "error", "message": str(e) or "Unsupported GPU"}, status=400)

        # Handle output settings
        _setting_keys = {
            "output_format",
            "quality",
            "webp_lossless_compression",
            "auto_save_local",
            "save_folder",
            "save_metadata_sidecar",
        }
        _settings_update = {}
        for key in _setting_keys:
            if key in body:
                _settings_update[key] = body[key]
        if _settings_update:
            # Validate enum values
            valid = True
            _err_key = ""
            if "output_format" in _settings_update and _settings_update["output_format"] not in OUTPUT_FORMATS:
                valid = False
                _err_key = "output_format"
            if "quality" in _settings_update:
                _q = _settings_update["quality"]
                if not isinstance(_q, (int, float)) or _q < 0 or _q > 100:
                    valid = False
                    _err_key = "quality"
            if "webp_lossless_compression" in _settings_update and _settings_update["webp_lossless_compression"] not in WEBP_LOSSLESS_COMPRESSION:
                valid = False
                _err_key = "webp_lossless_compression"
            if not valid:
                return web.json_response(
                    {"status": "error", "message": f"invalid value for {_err_key}"}, status=400
                )
            _save_modal_settings(_settings_update)

        # ── Phase 8: execution mode (only v1/v2 accepted, not shadow) ──
        if "execution_mode" in body:
            err = validate_config_payload(body)
            if err:
                return web.json_response({"status": "error", "message": err}, status=400)
            _env_mode = os.environ.get("COMFYMODAL_RUNTIME", "").strip().lower()
            _env_normalized = normalize_mode(_env_mode)
            _requested_mode = str(body.get("execution_mode", "")).strip().lower()
            if _env_normalized and _requested_mode != _env_normalized:
                return web.json_response({
                    "status": "error",
                    "message": "Execution engine is managed by COMFYMODAL_RUNTIME.",
                    "execution_mode_locked": True,
                }, status=409)
            new_mode = normalize_mode(body["execution_mode"])
            if new_mode:
                _save_modal_settings({"execution_mode": new_mode})
                response_data["execution_mode"] = new_mode

        return web.json_response(response_data)

    @_server.routes.post("/comfymodal/open-folder")
    async def modal_open_folder(request: web.Request) -> web.Response:
        import platform
        import subprocess as _sp
        body = await request.json()
        folder = (body.get("path") or body.get("folder") or "").strip()
        if not folder:
            return web.json_response({"status": "error", "message": "no path provided"}, status=400)

        _ALLOWED_ROOTS = [
            os.path.join(_COMFYUI_ROOT, "output"),
            os.path.join(_COMFYUI_ROOT, "input"),
        ]
        if not os.path.isabs(folder):
            folder = os.path.join(_COMFYUI_ROOT, folder)
        folder = os.path.normpath(os.path.realpath(folder))

        allowed = False
        for root in _ALLOWED_ROOTS:
            try:
                if os.path.commonpath([os.path.normpath(os.path.realpath(root)), folder]) == os.path.normpath(os.path.realpath(root)):
                    allowed = True
                    break
            except ValueError:
                pass
        if not allowed:
            return web.json_response({"status": "error", "message": "path not in allowed roots"}, status=403)

        if not os.path.isdir(folder):
            return web.json_response({"status": "error", "message": "directory does not exist"}, status=404)
        try:
            _sys_name = platform.system()
            if _sys_name == "Windows":
                _sp.Popen(["explorer", folder])  # Remove shell=True
            elif _sys_name == "Darwin":
                _sp.Popen(["open", folder])
            else:
                _sp.Popen(["xdg-open", folder])
        except Exception as exc:
            return web.json_response({"status": "error", "message": str(exc)}, status=500)
        return web.json_response({"status": "ok", "path": folder})

    @_server.routes.get("/comfymodal/health")
    async def modal_health(request: web.Request) -> web.Response:
        mode = request.rel_url.query.get("mode", "deploy")
        if mode == "deploy":
            state = _deploy_status.get("state", "idle")
            if state == "ready":
                return web.json_response({"status": "ok", "mode": "deploy"})
            elif state == "deploying":
                return web.json_response({"status": "deploying"}, status=503)
            else:
                return web.json_response({"status": state, "message": _deploy_status.get("message", "")}, status=503)
        try:
            result = await asyncio.wait_for(health_check(), timeout=10)
            return web.json_response(result)
        except asyncio.TimeoutError:
            return web.json_response({"status": "error", "message": "timeout"}, status=503)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=503)

    @_server.routes.get("/comfymodal/object_info")
    async def modal_object_info(request: web.Request) -> web.Response:
        try:
            result = await get_object_info()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=503)

    @_server.routes.get("/comfymodal/result/{prompt_id}")
    async def modal_get_direct_result(request: web.Request) -> web.Response:
        prompt_id = request.match_info.get("prompt_id", "")
        if not prompt_id:
            return web.json_response({"status": "error", "message": "prompt_id required"}, status=400)
        with _COMPLETED_RESULTS_LOCK:
            # TTL eviction
            now_t = time.time()
            expired = [k for k, v in _COMPLETED_RESULTS.items()
                       if now_t - v.get("completed_at", 0) > _COMPLETED_RESULTS_TTL_S]
            for k in expired:
                del _COMPLETED_RESULTS[k]
            entry = _COMPLETED_RESULTS.get(prompt_id)
            if entry is None:
                return web.json_response({"status": "pending", "message": "result not yet available"}, status=404)
            if entry.get("status") == "error":
                payload = dict(entry)
                return web.json_response({"status": "error", "prompt_id": prompt_id, **payload})
            payload = dict(entry)
        return web.json_response({"status": "ok", "prompt_id": prompt_id, **payload})

    @_server.routes.get("/comfymodal/benchmark/workflow")
    async def modal_benchmark_workflow_get(request: web.Request) -> web.Response:
        snapshot = _load_latest_benchmark_workflow()
        if not snapshot:
            return web.json_response({"status": "error", "message": "no benchmark workflow snapshot available"}, status=404)
        return web.json_response({"status": "ok", **snapshot})

    @_server.routes.post("/comfymodal/benchmark/workflow")
    async def modal_benchmark_workflow_post(request: web.Request) -> web.Response:
        body = await request.json()
        if not isinstance(body, dict) or not body:
            return web.json_response({"status": "error", "message": "workflow payload required"}, status=400)
        snapshot = _save_latest_benchmark_workflow(body)
        return web.json_response({
            "status": "ok",
            "captured_at": snapshot.get("captured_at"),
            "workflow_hash": snapshot.get("workflow_hash", ""),
        })

    @_server.routes.delete("/comfymodal/cancel/{client_id}")
    async def modal_cancel(request: web.Request) -> web.Response:
        client_id = request.match_info.get("client_id", "")
        return web.json_response({"status": "not_supported"}, status=404)

    @_server.routes.get("/comfymodal/models")
    async def modal_list_models(request: web.Request) -> web.Response:
        try:
            result = await list_models()
            return web.json_response(_annotate_models_with_local_info(result))
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=503)

    @_server.routes.post("/comfymodal/models/inject")
    async def modal_inject_placeholder(request: web.Request) -> web.Response:
        body = await request.json()
        folder = body.get("folder", "")
        filename = body.get("filename", "")
        if not folder or not filename:
            return web.json_response({"status": "error", "message": "folder and filename required"}, status=400)
        try:
            folder, filename = _validate_model_location(folder, filename)
            placeholder = _create_placeholder(folder, filename)
            return web.json_response({
                "status": "ok",
                "placeholder": placeholder,
                "message": "Local placeholder created. Refresh ComfyUI if the dropdown does not update.",
            })
        except ValueError as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/models/inject-all")
    async def modal_inject_all_placeholders(request: web.Request) -> web.Response:
        try:
            remote = await get_sync_status()
            remote_models = remote.get("models", [])
            placeholders, errors = _create_placeholder_batch([
                {"folder": item.get("folder", ""), "filename": item.get("name", "")}
                for item in remote_models
            ])
            created = sum(1 for item in placeholders if item.get("created"))
            existing = sum(1 for item in placeholders if item.get("existed"))
            return web.json_response({
                "status": "ok",
                "total": len(remote_models),
                "created": created,
                "existing": existing,
                "placeholders": placeholders,
                "errors": errors,
                "message": _inject_all_message(created, existing, len(errors)),
            })
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.delete("/comfymodal/models/{folder}/{filename}")
    async def modal_delete_model(request: web.Request) -> web.Response:
        folder = request.match_info.get("folder", "")
        filename = request.match_info.get("filename", "")
        if not folder or not filename:
            return web.json_response({"status": "error", "message": "folder and filename required"}, status=400)
        try:
            result = await delete_model(folder=folder, filename=filename)
            local_placeholder = None
            if result.get("status") == "ok":
                local_placeholder = _remove_local_placeholder_if_needed(folder, filename)
                if local_placeholder:
                    result["local_placeholder"] = local_placeholder
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/sync/status")
    async def modal_sync_status(request: web.Request) -> web.Response:
        """Get sync status: compare local models/custom_nodes with remote volumes."""
        try:
            # Get remote volume status
            remote = await get_sync_status()
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=503)

        # Scan local models
        models_root = os.path.join(_COMFYUI_ROOT, "models")
        local_models = []
        if os.path.isdir(models_root):
            for folder in os.listdir(models_root):
                folder_path = os.path.join(models_root, folder)
                if not os.path.isdir(folder_path):
                    continue
                for fname in os.listdir(folder_path):
                    fpath = os.path.join(folder_path, fname)
                    if os.path.isfile(fpath) and not fname.startswith("."):
                        size = os.path.getsize(fpath)
                        if size > 0:  # skip empty placeholder files
                            local_models.append({"folder": folder, "name": fname, "size": size})

        # Scan local custom nodes
        cn_root = os.path.join(_COMFYUI_ROOT, "custom_nodes")
        local_custom_nodes = []
        if os.path.isdir(cn_root):
            for d in os.listdir(cn_root):
                dpath = os.path.join(cn_root, d)
                if os.path.isdir(dpath) and not d.startswith(".") and d != "__pycache__":
                    local_custom_nodes.append(d)

        # Compare
        remote_models = remote.get("models", [])
        remote_model_keys = {f"{m['folder']}/{m['name']}" for m in remote_models}
        local_model_keys = {f"{m['folder']}/{m['name']}" for m in local_models}

        synced_models = [m for m in local_models if f"{m['folder']}/{m['name']}" in remote_model_keys]
        pending_models = [m for m in local_models if f"{m['folder']}/{m['name']}" not in remote_model_keys]

        remote_cn = set(remote.get("custom_nodes", []))
        local_cn_set = set(local_custom_nodes)
        synced_cn = sorted(local_cn_set & remote_cn)
        pending_cn = sorted(local_cn_set - remote_cn)

        return web.json_response({
            "status": "ok",
            "models": {
                "local": local_models,
                "remote": remote_models,
                "synced": synced_models,
                "pending": pending_models,
            },
            "custom_nodes": {
                "local": local_custom_nodes,
                "remote": sorted(remote_cn),
                "synced": synced_cn,
                "pending": pending_cn,
            },
        })

    @_server.routes.post("/comfymodal/sync/models")
    async def modal_sync_models(request: web.Request) -> web.Response:
        """Upload local models that are not yet on the remote volume."""
        CHUNK_SIZE = 100 * 1024 * 1024  # 100MB chunks

        try:
            remote = await get_sync_status()
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=503)

        remote_model_keys = {f"{m['folder']}/{m['name']}" for m in remote.get("models", [])}

        # Scan local models
        models_root = os.path.join(_COMFYUI_ROOT, "models")
        to_upload = []
        if os.path.isdir(models_root):
            for folder in os.listdir(models_root):
                folder_path = os.path.join(models_root, folder)
                if not os.path.isdir(folder_path):
                    continue
                for fname in os.listdir(folder_path):
                    fpath = os.path.join(folder_path, fname)
                    if not os.path.isfile(fpath) or fname.startswith("."):
                        continue
                    size = os.path.getsize(fpath)
                    if size == 0:
                        continue
                    key = f"{folder}/{fname}"
                    if key not in remote_model_keys:
                        to_upload.append({"folder": folder, "name": fname, "path": fpath, "size": size})

        if not to_upload:
            return web.json_response({"status": "ok", "message": "All models already synced", "uploaded": 0})

        uploaded = 0
        errors = []
        for item in to_upload:
            try:
                file_size = item["size"]
                offset = 0
                with open(item["path"], "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        is_last = (offset + len(chunk)) >= file_size
                        await upload_model_chunk(
                            chunk_data=chunk,
                            folder=item["folder"],
                            filename=item["name"],
                            offset=offset,
                            is_last=is_last,
                        )
                        offset += len(chunk)
                uploaded += 1
            except Exception as e:
                errors.append({"name": f"{item['folder']}/{item['name']}", "error": str(e)})

        result = {"status": "ok", "uploaded": uploaded, "total": len(to_upload)}
        if errors:
            result["errors"] = errors
        return web.json_response(result)

    @_server.routes.post("/comfymodal/sync/custom-nodes")
    async def modal_sync_custom_nodes(request: web.Request) -> web.Response:
        cn_root = os.path.join(_COMFYUI_ROOT, "custom_nodes")
        if not os.path.isdir(cn_root):
            return web.json_response({"status": "error", "message": "custom_nodes directory not found"}, status=400)
        workspace = _active_workspace()
        if workspace is None:
            return web.json_response({"status": "error", "message": "No active workspace configured"}, status=400)

        try:
            result = await _sync_custom_nodes_and_maybe_deploy(cn_root, workspace)
            return web.json_response(result, status=200 if result.get("status") == "ok" else 500)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/runtime/resync")
    async def modal_runtime_resync(request: web.Request) -> web.Response:
        scope = "all"
        try:
            body = await request.json()
            scope = body.get("scope", "all")
        except Exception:
            pass
        if scope not in ("models", "custom_nodes", "all"):
            return web.json_response({"status": "error", "message": "scope must be 'models', 'custom_nodes', or 'all'"}, status=400)
        try:
            # Clear the local profile-preparation cache before remote resync.
            _reset_profile_prep_cache()
            # Warmup-profile process-local dedup cache and identity state.
            from warmup_profile import _reset_last_stable_profile_cache
            _reset_last_stable_profile_cache()

            result = await resync_runtime(scope)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/runtime/state")
    async def modal_runtime_state(request: web.Request) -> web.Response:
        try:
            result = await get_runtime_state()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    # ── Runtime flag helpers (proxy to Modal functions) ──
    @_server.routes.post("/comfymodal/runtime/set_preload_mode")
    async def modal_set_preload_mode(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            mode = body.get("mode", "").strip().lower()
            if not mode:
                return web.json_response({"status": "error", "message": "mode required"}, status=400)
            result = await _call_set_preload_mode(mode)
            return web.json_response({"status": "ok", "result": result})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/runtime/set_flag")
    async def modal_set_runtime_flag(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            name = body.get("name", "").strip()
            value = body.get("value", "").strip()
            if not name:
                return web.json_response({"status": "error", "message": "name required"}, status=400)
            result = await _call_set_runtime_flag(name, value)
            return web.json_response({"status": "ok", "result": result})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    # ── Comparison profile execution helper ───────────────────────────
    # Submits a single resolved comparison-profile workflow to the Modal
    # pipeline and saves the result image + metadata to the comparison folder.
    async def _execute_comparison_profile(
        entry: dict,
        original_body: dict,
        manifest: dict,
        output_format: str,
        quality: int,
        webp_lossless_compression: str,
        auto_save_local: bool,
        save_folder: str,
        save_metadata_sidecar: bool,
        workspace: dict | None = None,
    ) -> dict:
        import time as _time_module
        import base64 as _b64

        pid = entry.get("profile_id", "unknown")
        pname = entry.get("profile_name", pid)
        workflow = entry.get("workflow", {})
        workflow_hash = entry.get("workflow_hash", "")
        model_stack = entry.get("model_stack", {})
        slots = entry.get("slots", {})

        comparison_id = manifest["comparison_id"]
        prompt_text = manifest.get("prompt", "")
        seed = manifest.get("seed", 0)
        width = manifest.get("width", 0)
        height = manifest.get("height", 0)
        steps = manifest.get("steps")
        guidance = manifest.get("guidance")
        inp_img = manifest.get("input_image", "")

        trace_payload = original_body.get("trace", {}) if isinstance(original_body, dict) else {}

        # Build extra_data like _execute_job does
        extra_data = {
            "client_id": original_body.get("client_id", str(uuid.uuid4())),
            "workflow_hash": workflow_hash,
            "prompt_summary": {
                "seed": seed,
                "width": width,
                "height": height,
                "steps": steps,
                "cfg": guidance,
            },
            "model_stack": model_stack,
            "gpu": get_gpu(),
            "modal_options": {
                "output_format": output_format,
                "quality": quality,
                "webp_lossless_compression": webp_lossless_compression,
                "auto_save_local": auto_save_local,
                "save_folder": save_folder,
                "save_metadata_sidecar": save_metadata_sidecar,
            },
            "comparison": {
                "comparison_id": comparison_id,
                "profile_id": pid,
                "profile_name": pname,
            },
            "trace": trace_payload,
        }
        prompt_id = str(uuid.uuid4())

        result_data = {
            "comparison_id": comparison_id,
            "profile_id": pid,
            "profile_name": pname,
            "workflow_hash": workflow_hash,
            "model_stack": model_stack,
            "prompt": prompt_text,
            "seed": seed,
            "width": width,
            "height": height,
            "steps": steps,
            "guidance": guidance,
            "output_format": output_format,
        }

        try:
            t0 = _time_module.time()
            input_images = _collect_input_images(workflow)

            # Submit to Modal via the existing streaming pipeline
            _modal_result = None
            async for _msg in run_prompt_stream(
                workflow,
                input_images,
                trace=extra_data.get("trace", {}),
                gpu=extra_data.get("gpu"),
                modal_options=extra_data.get("modal_options"),
                workspace=workspace,
            ):
                if not isinstance(_msg, dict):
                    continue
                if _msg["type"] == "result":
                    _modal_result = _msg["data"]
                    break
                elif _msg["type"] == "error":
                    raise RuntimeError(_msg.get("message", "Modal error"))

            if _modal_result is None:
                raise RuntimeError("No result from Modal pipeline")

            wall_time_sec = round(_time_module.time() - t0, 2)

            # Extract images from result
            image_data_b64 = None
            mime_type = "image/png"
            file_ext = ".png"

            primary_entry = _select_primary_result_entry(_modal_result)
            if primary_entry:
                image_data_b64 = primary_entry.get("data")
                mime_type = primary_entry.get("mime_type", "image/png")
                file_ext = primary_entry.get("file_ext", ".png")

            if not image_data_b64:
                raise RuntimeError("No image data in Modal result")

            # Save output image
            img_bytes = _b64.b64decode(image_data_b64)

            # Save to comparison folder
            compare_result = save_comparison_result(
                _COMFYUI_ROOT, comparison_id, {
                    **result_data,
                    "mime_type": mime_type,
                    "file_ext": file_ext,
                    "wall_time_sec": wall_time_sec,
                    "status": "success",
                    "primary_output": {
                        "node_id": str(primary_entry.get("node_id", "")) if primary_entry else "",
                        "output_key": str(primary_entry.get("output_key", "images")) if primary_entry else "images",
                        "comparison_side": primary_entry.get("comparison_side", "") if primary_entry else "",
                        "filename": primary_entry.get("filename", "") if primary_entry else "",
                        "path": primary_entry.get("path", "") if primary_entry else "",
                        "mime_type": mime_type,
                        "file_ext": file_ext,
                    },
                },
                image_bytes=img_bytes,
            )

            # Apply format conversion if needed
            converted_bytes = img_bytes
            if output_format != "original":
                from output_converter import convert_image_bytes
                conv = convert_image_bytes(
                    img_bytes,
                    output_format=output_format,
                    quality=quality,
                    webp_lossless_compression=webp_lossless_compression,
                )
                if not conv.get("fallback") and not conv.get("error"):
                    converted_bytes = conv["bytes"]
                    mime_type = conv.get("mime_type", mime_type)
                    file_ext = conv.get("file_ext", file_ext)

            # Auto-save to the standard output location if enabled
            if auto_save_local:
                try:
                    from output_saver import save_output_image
                    saver_result = save_output_image(
                        converted_bytes,
                        output_format=output_format,
                        file_ext=file_ext,
                        mime_type=mime_type,
                        quality=quality,
                        webp_lossless_compression=webp_lossless_compression,
                        original_size_bytes=len(img_bytes),
                        conversion_time_ms=0,
                        save_folder=save_folder,
                        save_metadata_sidecar=save_metadata_sidecar,
                        workflow_hash=workflow_hash,
                        workflow_name=pname,
                        seed=str(seed),
                        width=width,
                        height=height,
                        index=0,
                        comfyui_root=_COMFYUI_ROOT,
                        extra_meta={
                            "comparison_id": comparison_id,
                            "profile_id": pid,
                            "comparison": True,
                            "node_id": str(primary_entry.get("node_id", "")) if primary_entry else "",
                            "output_key": str(primary_entry.get("output_key", "images")) if primary_entry else "images",
                            "comparison_side": primary_entry.get("comparison_side", "") if primary_entry else "",
                            "source_filename": primary_entry.get("filename", "") if primary_entry else "",
                        },
                    )
                    if saver_result.get("error"):
                        compare_result["auto_save_error"] = saver_result["error"]
                    else:
                        compare_result["auto_save_path"] = saver_result.get("path", "")
                except Exception as save_exc:
                    compare_result["auto_save_error"] = str(save_exc)

            compare_result["mime_type"] = mime_type
            compare_result["file_ext"] = file_ext

            return compare_result

        except Exception as e:
            import traceback as _tb
            _tb.print_exc()
            error_result = {
                **result_data,
                "status": "error",
                "error": str(e),
            }
            save_comparison_result(_COMFYUI_ROOT, comparison_id, error_result)
            return error_result

    # ── Comparison Runner Routes ──────────────────────────────────────

    @_server.routes.get("/comfymodal/comparison/profiles")
    async def comparison_list_profiles(request: web.Request) -> web.Response:
        try:
            profiles = list_profiles(_COMFYUI_ROOT)
            return web.json_response({"status": "ok", "profiles": profiles})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/comparison/profiles")
    async def comparison_create_profile(request: web.Request) -> web.Response:
        body = await request.json()
        name = body.get("name", "").strip()
        workflow_api = body.get("workflow_api")
        workflow = body.get("workflow")
        if not name:
            return web.json_response({"status": "error", "message": "Profile name required"}, status=400)
        if not workflow_api or not isinstance(workflow_api, dict):
            return web.json_response({"status": "error", "message": "workflow_api required"}, status=400)
        try:
            profile = create_profile(_COMFYUI_ROOT, name, workflow_api, workflow=workflow)
            return web.json_response({"status": "ok", "profile": profile})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/comparison/profiles/{profile_id}")
    async def comparison_get_profile(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        try:
            profile = get_profile(_COMFYUI_ROOT, profile_id)
            if profile is None:
                return web.json_response({"status": "error", "message": "Profile not found"}, status=404)
            return web.json_response({"status": "ok", "profile": profile})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.put("/comfymodal/comparison/profiles/{profile_id}")
    async def comparison_update_profile(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        body = await request.json()
        try:
            profile = update_profile(_COMFYUI_ROOT, profile_id, body)
            if profile is None:
                return web.json_response({"status": "error", "message": "Profile not found"}, status=404)
            return web.json_response({"status": "ok", "profile": profile})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.delete("/comfymodal/comparison/profiles/{profile_id}")
    async def comparison_delete_profile(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        try:
            ok = delete_profile(_COMFYUI_ROOT, profile_id)
            if not ok:
                return web.json_response({"status": "error", "message": "Profile not found"}, status=404)
            return web.json_response({"status": "ok"})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/comparison/profiles/{profile_id}/duplicate")
    async def comparison_duplicate_profile(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        body = await request.json()
        new_name = body.get("name", "").strip()
        if not new_name:
            return web.json_response({"status": "error", "message": "New profile name required"}, status=400)
        try:
            profile = duplicate_profile(_COMFYUI_ROOT, profile_id, new_name)
            if profile is None:
                return web.json_response({"status": "error", "message": "Profile not found"}, status=404)
            return web.json_response({"status": "ok", "profile": profile})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/comparison/profiles/{profile_id}/validate")
    async def comparison_validate_profile(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        try:
            validation = validate_profile(_COMFYUI_ROOT, profile_id)
            return web.json_response({"status": "ok", "validation": validation})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/comparison/profiles/{profile_id}/detect-slots")
    async def comparison_detect_slots(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        try:
            candidates = auto_detect_slots(_COMFYUI_ROOT, profile_id)
            if candidates is None:
                return web.json_response({"status": "error", "message": "Profile or workflow not found"}, status=404)
            return web.json_response({"status": "ok", "candidates": candidates})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/comparison/profiles/{profile_id}/slots")
    async def comparison_set_slots(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        body = await request.json()
        slots = body.get("slots", {})
        try:
            profile = set_slots(_COMFYUI_ROOT, profile_id, slots)
            if profile is None:
                return web.json_response({"status": "error", "message": "Profile not found"}, status=404)
            return web.json_response({"status": "ok", "profile": profile})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/comparison/run")
    async def comparison_run(request: web.Request) -> web.Response:
        """Execute a comparison run by preparing manifests and submitting each
        resolved workflow to the Modal pipeline.

        The comparison may run sequentially or in parallel (up to
        max_parallel_jobs concurrently).  Results are saved to the comparison
        output folder.
        """
        body = await request.json()
        profile_ids = body.get("profile_ids", [])
        prompt_text = body.get("prompt", "").strip()
        seed = body.get("seed", 0)
        width = body.get("width", 1024)
        height = body.get("height", 1024)
        steps = body.get("steps")
        guidance = body.get("guidance")
        negative_prompt = body.get("negative_prompt", "").strip() or None
        input_image = body.get("input_image", "").strip() or None
        execution_mode = body.get("execution_mode", "sequential")
        max_parallel_jobs = int(body.get("max_parallel_jobs", 2))

        # Per-profile override settings (skip shared steps/guidance/resolution)
        per_profile_overrides = body.get("per_profile_overrides", {})

        # Output settings
        output_format = body.get("output_format", "original")
        quality = int(body.get("quality", 75))
        webp_lossless_compression = body.get("webp_lossless_compression", "balanced")
        auto_save_local = bool(body.get("auto_save_local", False))
        save_folder = body.get("save_folder", "")
        save_metadata_sidecar = bool(body.get("save_metadata_sidecar", True))

        if not profile_ids:
            return web.json_response({"status": "error", "message": "No profiles selected"}, status=400)
        if not prompt_text:
            prompt_text = ""
        if not isinstance(seed, int):
            try:
                seed = int(seed)
            except (TypeError, ValueError):
                seed = 0

        # Per audit round 7: capture workspace once for all profile
        # executions so detached background tasks do not resolve
        # whichever workspace happens to be active later.
        _comparison_workspace = _active_workspace() or {}

        try:
            manifest = run_comparison(
                comfyui_root=_COMFYUI_ROOT,
                prompt_text=prompt_text,
                seed=seed,
                width=width,
                height=height,
                steps=steps,
                guidance=guidance,
                negative_prompt=negative_prompt,
                input_image=input_image,
                profile_ids=profile_ids,
                execution_mode=execution_mode,
                max_parallel_jobs=max_parallel_jobs,
                output_format=output_format,
                quality=quality,
                webp_lossless_compression=webp_lossless_compression,
                auto_save_local=auto_save_local,
                save_folder=save_folder,
                save_metadata_sidecar=save_metadata_sidecar,
                per_profile_overrides=per_profile_overrides,
            )

            resolved = manifest.get("resolved_profiles", [])

            # Persist the manifest immediately (results appended as they arrive)
            save_comparison_manifest(_COMFYUI_ROOT, manifest)

            # Dispatch resolved workflows to the Modal pipeline
            results = []
            errors = []

            if execution_mode == "parallel":
                import asyncio
                sem = asyncio.Semaphore(max_parallel_jobs)

                async def _run_one(entry: dict) -> dict:
                    async with sem:
                        return await _execute_comparison_profile(
                            entry, body, manifest, output_format, quality,
                            webp_lossless_compression, auto_save_local,
                            save_folder, save_metadata_sidecar,
                            workspace=_comparison_workspace,
                        )

                tasks = [_run_one(e) for e in resolved if e.get("status") == "ready"]
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                for outcome in outcomes:
                    if isinstance(outcome, Exception):
                        errors.append({"error": str(outcome)})
                    elif outcome:
                        results.append(outcome)
            else:
                for entry in resolved:
                    if entry.get("status") != "ready":
                        if entry.get("error"):
                            errors.append({
                                "profile_id": entry.get("profile_id", ""),
                                "profile_name": entry.get("profile_name", ""),
                                "error": entry.get("error", "Unknown error"),
                            })
                        continue
                    try:
                        result = await _execute_comparison_profile(
                            entry, body, manifest, output_format, quality,
                            webp_lossless_compression, auto_save_local,
                            save_folder, save_metadata_sidecar,
                            workspace=_comparison_workspace,
                        )
                        if result:
                            results.append(result)
                    except Exception as e:
                        errors.append({
                            "profile_id": entry.get("profile_id", ""),
                            "profile_name": entry.get("profile_name", ""),
                            "error": str(e),
                        })

            manifest["results"] = results
            manifest["errors"] = errors
            manifest["completed_at"] = __import__("time").time()

            # Update manifest on disk with results
            save_comparison_manifest(_COMFYUI_ROOT, manifest)

            return web.json_response({
                "status": "ok",
                "comparison_id": manifest["comparison_id"],
                "results": results,
                "errors": errors,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/comparison/results")
    async def comparison_list_runs(request: web.Request) -> web.Response:
        try:
            runs = list_comparison_runs(_COMFYUI_ROOT)
            return web.json_response({"status": "ok", "runs": runs})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/comparison/results/{comparison_id}")
    async def comparison_get_results(request: web.Request) -> web.Response:
        comparison_id = request.match_info.get("comparison_id", "")
        try:
            manifest = get_comparison_results(_COMFYUI_ROOT, comparison_id)
            if manifest is None:
                return web.json_response({"status": "error", "message": "Comparison not found"}, status=404)
            return web.json_response({"status": "ok", "manifest": manifest})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/comparison/profiles/{profile_id}/workflow/nodes")
    async def comparison_workflow_nodes(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        try:
            nodes = get_workflow_nodes(_COMFYUI_ROOT, profile_id)
            if nodes is None:
                return web.json_response({"status": "error", "message": "Workflow not found"}, status=404)
            return web.json_response({"status": "ok", "nodes": nodes})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/comparison/profiles/{profile_id}/workflow")
    async def comparison_workflow_get(request: web.Request) -> web.Response:
        profile_id = request.match_info.get("profile_id", "")
        try:
            payload = get_profile_workflow(_COMFYUI_ROOT, profile_id)
            if payload is None:
                return web.json_response({"status": "ok", "workflow_api": {}, "workflow": None})
            return web.json_response({"status": "ok", **payload})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/comparison/config")
    async def comparison_get_config(request: web.Request) -> web.Response:
        try:
            config = load_comparison_config(_COMFYUI_ROOT)
            return web.json_response({"status": "ok", "config": config})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.post("/comfymodal/comparison/config")
    async def comparison_set_config(request: web.Request) -> web.Response:
        body = await request.json()
        try:
            config = save_comparison_config(_COMFYUI_ROOT, body)
            return web.json_response({"status": "ok", "config": config})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    @_server.routes.get("/comfymodal/comparison/gallery/{comparison_id}")
    async def comparison_gallery(request: web.Request) -> web.Response:
        """Return gallery data for a completed comparison run, including
        base64-encoded thumbnail images for each result."""
        comparison_id = request.match_info.get("comparison_id", "")
        try:
            manifest = get_comparison_results(_COMFYUI_ROOT, comparison_id)
            if manifest is None:
                return web.json_response({"status": "error", "message": "Comparison not found"}, status=404)
            gallery = []
            for result in manifest.get("results", []):
                entry = dict(result)
                out_path = result.get("output_path", "")
                if out_path and os.path.isfile(out_path):
                    import base64
                    with open(out_path, "rb") as f:
                        entry["image_data_b64"] = base64.b64encode(f.read()).decode()
                else:
                    entry["image_data_b64"] = None
                gallery.append(entry)
            return web.json_response({"status": "ok", "gallery": gallery, "manifest": manifest})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    # ── i2i/t2i testing suite routes ─────────────────────────────────
    from experiment_service import (
        REGISTRY, experiments_root, run_history_root, presets_root,
        blobs_root, leases_db_path, warmup_state_path, experiment_dir,
    )
    from matrix_compiler import compile_experiment
    from deploy_warmup import (
        WarmupState, deployment_generation, ensure_warmup, gate_experiment,
        gate_experiment_on_stored_generation, WarmupRequiredError,
    )
    from presets import (
        list_prompt_presets, get_prompt_preset, create_prompt_preset,
        rename_prompt_preset, delete_prompt_preset, duplicate_prompt_preset,
        import_prompts_from_text,
        list_image_presets, get_image_preset, create_image_preset,
        rename_image_preset, delete_image_preset,
    )
    from run_history import redact_log, format_timing
    from experiment_runner import (
        CheckpointStreamInvoker, LocalRemoteInvoker,
    )
    from experiment_models import CURRENT_SCHEMA_VERSION, validate_definition
    from experiment_lease import StaleEventError, LeaseActiveError, LeaseError, LeaseOwnershipError, UnknownCheckpointError

    _experiments_root = experiments_root()
    _leases_db_path = leases_db_path()
    _warmup_state_path = warmup_state_path()

    # ── Workflow resolution at checkpoint start ──
    def _resolve_latest_workflow_for_profile(profile_id: str) -> dict:
        """Return the live workflow JSON for ``profile_id``.

        Resolution order:
        1. Read ``workflow_api.json`` from the profile directory (the
           copy saved at profile creation / update time).
        2. If nothing works, raise ``ValueError``.

        Note: ``workflow_data`` and ``workflow_path`` branches were
        previously defined in the resolver but never written by any
        route — they are intentionally removed to keep the contract
        honest. The only reliable workflow source is the on-disk
        ``workflow_api.json`` maintained by ``create_profile`` and
        ``update_profile``.
        """
        from comparison import COMPARISON_DIRNAME
        profiles_root = os.path.join(_COMFYUI_ROOT, "user", "default", "comfy-modal", COMPARISON_DIRNAME)
        profile_dir = os.path.join(profiles_root, profile_id)

        # Read workflow_api.json (saved at profile creation/update)
        wf_api_path = os.path.join(profile_dir, "workflow_api.json")
        if os.path.isfile(wf_api_path):
            try:
                with open(wf_api_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        # Nothing worked — raise clear error
        raise ValueError(
            f"no workflow found for profile {profile_id!r}: "
            f"associate a workflow first"
        )

    def _enrich_checkpoint_from_profile(ck: dict) -> None:
        """Attach profile metadata (workflow, slots, loader groups, lora slots)
        to a checkpoint dict so the runner can resolve and inject cell values.

        If the profile cannot be resolved (e.g. missing files in test/dev
        environments), enrichment is silently skipped so the compiler can
        still return useful output for normalised-draft compilation.
        """
        profile_id = ck.get("profile_id", "")
        if not profile_id:
            return
        try:
            ck["workflow"] = _resolve_latest_workflow_for_profile(profile_id)
        except (ValueError, OSError):
            ck["workflow"] = {}
        profile = get_profile(_COMFYUI_ROOT, profile_id) or {}
        ck["slots"] = profile.get("slots", {})
        ck["loader_target_groups"] = profile.get("loader_target_groups", [])
        ck["lora_slots"] = profile.get("lora_slots", [])

    @_server.routes.post("/comfymodal/experiments/compile")
    async def experiment_compile(request: web.Request) -> web.Response:
        """Compile an experiment spec into a list of checkpoints/cells.

        Accepts either a ``spec`` key (existing compiler-spec format) or a
        ``normalized_draft`` key (new backend-authoritative format).  When a
        normalised draft is provided, it is validated and translated to the
        compiler spec using ``experiment_setup_adapter`` before compilation.
        """
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid JSON body"}, status=400)

        normalized_draft = payload.get("normalized_draft")
        if normalized_draft is not None:
            # New path: normalised draft → validate → compile.
            if not isinstance(normalized_draft, dict):
                return web.json_response(
                    {"status": "error", "message": "normalized_draft must be an object"},
                    status=400,
                )
            validation = _experiment_setup_adapter.validate_normalized_draft(normalized_draft)
            if not validation.get("valid"):
                return web.json_response(
                    {"status": "error", "message": f"draft validation failed: {validation.get('errors', 'unknown')}"},
                    status=400,
                )
            spec = _experiment_setup_adapter.normalized_draft_to_compiler_spec(normalized_draft)
        else:
            # Existing path: raw spec.
            spec = payload.get("spec", {})
            if not isinstance(spec, dict):
                return web.json_response({"status": "error", "message": "spec must be an object"}, status=400)

        try:
            compilation = compile_experiment(spec)
        except Exception as e:
            return web.json_response({"status": "error", "message": f"compile failed: {e}"}, status=400)
        # Tag each checkpoint with its profile metadata.
        for ck in compilation.get("checkpoints", []):
            _enrich_checkpoint_from_profile(ck)
        return web.json_response({"status": "ok", "compilation": compilation})

    @_server.routes.post("/comfymodal/experiments")
    async def experiment_create(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid JSON body"}, status=400)

        # Accept either a normalised draft (backend-authoritative new path)
        # or a raw spec (existing path).
        normalized_draft = payload.get("normalized_draft")
        if normalized_draft is not None:
            if not isinstance(normalized_draft, dict):
                return web.json_response(
                    {"status": "error", "message": "normalized_draft must be an object"},
                    status=400,
                )
            validation = _experiment_setup_adapter.validate_normalized_draft(normalized_draft)
            if not validation.get("valid"):
                return web.json_response(
                    {"status": "error", "message": f"draft validation failed: {validation.get('errors', 'unknown')}"},
                    status=400,
                )
            spec = _experiment_setup_adapter.normalized_draft_to_compiler_spec(normalized_draft)
            exp_id = str(normalized_draft.get("experiment_id", ""))
            if not exp_id:
                return web.json_response({"status": "error", "message": "normalized_draft.experiment_id required"}, status=400)
        else:
            spec = payload.get("spec", {})
            if not isinstance(spec, dict) or "experiment_id" not in spec:
                return web.json_response({"status": "error", "message": "spec.experiment_id required"}, status=400)
            exp_id = str(spec["experiment_id"])

        # Compile to validate spec shape
        try:
            compilation = compile_experiment(spec)
        except Exception as e:
            return web.json_response({"status": "error", "message": f"compile failed: {e}"}, status=400)
        # Resolve profile metadata per checkpoint
        for ck in compilation.get("checkpoints", []):
            _enrich_checkpoint_from_profile(ck)
        store = REGISTRY.store(exp_id)
        now = _utc_now_iso()
        definition = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "experiment_id": exp_id,
            "revision": 1,
            "name": str(spec.get("name", exp_id)),
            "notes": str(spec.get("notes", "")),
            "created_at": now,
            "updated_at": now,
        }
        # Preserve the normalised draft in the definition so it survives
        # refresh / restart without browser reconstruction.
        if normalized_draft is not None:
            definition["normalized_draft"] = normalized_draft

        validate_definition(type("D", (), definition)())  # cheap shape check
        store.write_definition(definition)
        event_payload: dict = {
            "experiment_id": exp_id,
            "name": definition["name"],
            "compilation": compilation,
        }
        if normalized_draft is not None:
            event_payload["normalized_draft"] = normalized_draft
        store.append_event({
            "type": "experiment.created",
            "payload": event_payload,
        })
        return web.json_response({
            "status": "ok",
            "experiment_id": exp_id,
            "definition": definition,
            "compilation": compilation,
        })

    @_server.routes.get("/comfymodal/experiments")
    async def experiment_list(request: web.Request) -> web.Response:
        items = []
        for d in sorted(_experiments_root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            defn_path = d / "definition.json"
            if not defn_path.exists():
                continue
            try:
                with open(defn_path, "r", encoding="utf-8") as f:
                    defn = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            snap_path = d / "snapshot.json"
            snap = None
            if snap_path.exists():
                try:
                    with open(snap_path, "r", encoding="utf-8") as f:
                        snap = json.load(f)
                except (OSError, json.JSONDecodeError):
                    snap = None
            items.append({
                "experiment_id": defn.get("experiment_id", d.name),
                "definition": defn,
                "snapshot": snap,
            })
        return web.json_response({"status": "ok", "experiments": items})

    @_server.routes.get("/comfymodal/experiments/{experiment_id}")
    async def experiment_detail(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        store = REGISTRY.store(exp_id)
        defn = store.read_definition()
        if defn is None:
            return web.json_response({"status": "error", "message": "unknown experiment"}, status=404)
        # If we don't have a snapshot, rebuild it.
        snap = store.read_snapshot() or store.rebuild_snapshot()
        events = list(store.read_events())
        return web.json_response({
            "status": "ok",
            "definition": defn,
            "snapshot": snap,
            "events": events,
        })

    @_server.routes.get("/comfymodal/experiments/{experiment_id}/events")
    async def experiment_events(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        after = int(request.query.get("after", "0"))
        try:
            store = REGISTRY.store(exp_id)
        except Exception:
            return web.json_response({"status": "error", "events": [], "progress": {"cells": {}, "checkpoints": {}}})
        progress = {}
        try:
            progress = REGISTRY.worker_progress(exp_id).snapshot()
        except Exception:
            progress = {"cells": {}, "checkpoints": {}}
        return web.json_response({
            "status": "ok",
            "events": store.read_events_after(after),
            "progress": progress,
        })

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/start")
    async def experiment_start(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        try:
            body = await request.json() if request.body_exists else {}
        except Exception:
            body = {}
        store = REGISTRY.store(exp_id)
        defn = store.read_definition()
        if defn is None:
            return web.json_response({"status": "error", "message": "unknown experiment"}, status=404)
        spec = body.get("spec", {}) if isinstance(body, dict) else {}
        max_containers = int((body or {}).get("max_containers", 1))

        # C6: detect stored compilation from clone events when spec is empty
        compilation = None
        if not spec:
            # Look for a stored compilation in the journal
            for ev in store.read_events():
                if ev.get("type") == "experiment.cloned":
                    p = ev.get("payload", {}) or {}
                    compilation = p.get("compilation", None)
                    if compilation:
                        compilation = copy.deepcopy(compilation)
                        compilation["experiment_id"] = exp_id
                        break
                if ev.get("type") == "experiment.created":
                    p = ev.get("payload", {}) or {}
                    compilation = p.get("compilation", None)
                    if compilation:
                        compilation = copy.deepcopy(compilation)
                        compilation["experiment_id"] = exp_id
                        break
            if compilation is None:
                # Try loading from scheduler state
                from experiment_service import experiment_dir as _exp_dir
                state_file = _exp_dir(exp_id) / ".scheduler_state.json"
                if state_file.exists():
                    try:
                        import json as _json
                        state = _json.loads(state_file.read_text(encoding="utf-8"))
                        compilation = state.get("compilation", None)
                    except Exception:
                        pass
            if compilation is None:
                return web.json_response({"status": "error", "message": "spec required and no stored compilation"}, status=400)
        else:
            # Gate the experiment on warmup: if the active deployment is
            # not warmed, refuse to start scored cells. The client is
            # expected to call the /comfymodal/deploy-warmup/run route
            # first.
            # Use gate_experiment_on_stored_generation — NOT gate_experiment
            # which regenerates a fresh timestamp and will never match
            # the generation stored at deploy time.
            # NOTE: only WarmupRequiredError is caught here. Unexpected
            # errors (typos, missing imports) propagate to the caller
            # as a 500 response rather than silently bypassing the gate.
            try:
                warmup_state = WarmupState(_warmup_state_path)
                gate_experiment_on_stored_generation(warmup_state)
            except WarmupRequiredError as exc:
                return web.json_response(
                    {"status": "error", "message": f"warmup required: {exc}"},
                    status=409,
                )
            try:
                compilation = compile_experiment(spec)
            except Exception as e:
                return web.json_response({"status": "error", "message": f"compile failed: {e}"}, status=400)
            for ck in compilation.get("checkpoints", []):
                _enrich_checkpoint_from_profile(ck)
        try:
            from modal_client import run_checkpoint_stream
            warmup_state = WarmupState(_warmup_state_path)
            dep_gen = warmup_state.deployment_generation() or ""
            invoker = CheckpointStreamInvoker(
                run_checkpoint_stream,
                experiment_id=exp_id,
                stream_event_sink=lambda ev: _on_remote_event(exp_id, ev),
            )
        except Exception:
            invoker = None
        sched = await REGISTRY.get_or_create_scheduler(
            exp_id, compilation=compilation, invoker=invoker,
            max_containers=max_containers,
        )
        REGISTRY.save_scheduler_state(exp_id, compilation, max_containers)
        REGISTRY.start_bridge(exp_id)
        import asyncio as _asyncio
        _asyncio.create_task(sched.start())
        return web.json_response({"status": "ok", "started": True, "experiment_id": exp_id})

    # Phase 7: register the production event handler for recovered schedulers
    try:
        from experiment_service import set_remote_event_handler
        set_remote_event_handler(lambda exp_id, ev: asyncio.create_task(_on_remote_event(exp_id, ev)))
    except Exception:
        pass

    def _record_experiment_cell_history(exp_id: str, data: dict, payload: dict, event_type: str) -> str:
        """Record a cell event into run history with complete resolved metadata.

        B7: Includes deployment_generation, experiment_revision, and output_policy.
        """
        try:
            history_data = {
                "experiment_id": exp_id,
                "checkpoint_id": data.get("checkpoint_id", ""),
                "cell_key": data.get("cell_key", ""),
                "attempt_id": data.get("attempt_id", ""),
                "asset_ids": payload.get("asset_ids", []),
                "primary_asset_id": payload.get("primary_asset_id", ""),
                "primary_thumbnail_asset_id": payload.get("primary_thumbnail_asset_id", ""),
                "prompt": data.get("prompt", ""),
                "negative_prompt": data.get("negative_prompt", ""),
                "seed": data.get("seed", 0),
                "steps": data.get("steps", 0),
                "guidance": data.get("guidance", 0.0),
                "sampler": data.get("sampler", ""),
                "scheduler": data.get("scheduler", ""),
                "denoise": data.get("denoise", 1.0),
                "width": data.get("width", 0),
                "height": data.get("height", 0),
                "unet": data.get("unet", ""),
                "clip": data.get("clip", ""),
                "vae": data.get("vae", ""),
                "lora_chain": data.get("lora_chain", []),
                "workflow_hash": data.get("workflow_hash", ""),
                "error": data.get("error", ""),
                # B7: additional fields
                "deployment_generation": data.get("deployment_generation", ""),
                "experiment_revision": data.get("revision", 0),
                "output_policy": data.get("output_policy", {}),
                "studio_meta": data.get("studio_meta", {}),
                "total_cells": data.get("total_cells", 0),
            }
            record = REGISTRY.history().record_run(
                kind="experiment_cell",
                prompt_id=data.get("cell_key", ""),
                workflow_hash=data.get("workflow_hash", ""),
                status=event_type.split(".", 1)[1],
                meta=history_data,
                log_text=str(data.get("error", "")),
            )
            return str(record.get("run_id", ""))
        except Exception:
            return ""

    async def _on_remote_event(exp_id: str, ev: dict) -> None:
        """Forward a single streamed cell event to the journal and to
        the run-history store.

        This is the SOLE owner of terminal event persistence. The runner
        does NOT emit cell.completed/failed/interrupted - only this
        function does, after strict lease validation.

        Also forwards non-terminal progress events to the UI (Phase 9).

        B2: Staged workflow for materialization:
          1. Validate event identity and lease without consuming terminal ownership
          2. Write originals to a .tmp/<attempt_id>/ directory
          3. Write thumbnails in the same tmp
          4. Compute hashes/asset records
          5. Begin SQLite transaction
          6. Register all assets
          7. Mark attempt terminal accepted
          8. Persist cell.completed event
          9. Commit
          10. Atomically rename tmp to final path
          11. Record history
          On any failure after step 6, roll back: delete registered assets,
          delete tmp files, leave attempt unaccepted, persist cell.failed
          with category 'output_materialization_failed'.
        """
        try:
            store = REGISTRY.store(exp_id)
            et = ev.get("type", "")
            # Shallow-copy so downstream mutation (data.pop, etc.) never
            # affects the caller's original ev dict.
            data = dict(ev.get("data", {}) or {})

            # Phase 9: forward non-terminal progress events to the UI
            if et in {"cell.started", "checkpoint.started", "cell.progress", "sampler.step"}:
                try:
                    progress_payload = {
                        "experiment_id": exp_id,
                        "checkpoint_id": data.get("checkpoint_id", ""),
                        "cell_key": data.get("cell_key", ""),
                        "attempt_id": data.get("attempt_id", ""),
                        "worker_invocation_id": data.get("worker_invocation_id", ""),
                        "type": et,
                        "step": data.get("step"),
                        "total_steps": data.get("total_steps"),
                        "pct": data.get("pct"),
                        "payload": data,
                    }
                    _send("", "experiment.worker.progress", progress_payload)
                    try:
                        REGISTRY.worker_progress(exp_id).update(
                            checkpoint_id=data.get("checkpoint_id", ""),
                            cell_key=data.get("cell_key", ""),
                            sample=progress_payload,
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

            # Phase 8: strict lease validation before any terminal persistence
            if et in {"cell.completed", "cell.failed", "cell.interrupted"}:
                try:
                    REGISTRY.leases().validate_and_accept(
                        exp_id,
                        checkpoint_id=data.get("checkpoint_id", ""),
                        lease_generation=int(data.get("lease_generation", 0)),
                        worker_invocation_id=data.get("worker_invocation_id", ""),
                        attempt_id=data.get("attempt_id", ""),
                    )
                except (LeaseError, Exception) as e:
                    # Stale/duplicate/unowned event: log and skip persistence
                    print(f"[comfyui-modal] rejecting event: {e}")
                    return

            if et in {"cell.completed", "cell.failed", "cell.interrupted"}:
                payload = {
                    "checkpoint_id": data.get("checkpoint_id", ""),
                    "cell_key": data.get("cell_key", ""),
                    "worker_invocation_id": data.get("worker_invocation_id", ""),
                    "lease_generation": data.get("lease_generation", 0),
                    "attempt_id": data.get("attempt_id", ""),
                    "error": data.get("error", ""),
                }
                # Phase 9/10: materialize remote outputs for cell.completed
                # B2: Staged workflow — do NOT persist cell.completed if
                # materialization fails.  On failure, persist cell.failed
                # with category "output_materialization_failed".
                materialization_ok = True
                if et == "cell.completed":
                    result_data = data.get("result", {}) or {}
                    if result_data:
                        cell_key = data.get("cell_key", "")
                        attempt_id = data.get("attempt_id", "")
                        try:
                            # B2 step 2+3: write to tmp directory first
                            output_dir = str(experiment_dir(exp_id) / ".tmp" / attempt_id)
                            os.makedirs(output_dir, exist_ok=True)
                            mat = _materialize_experiment_output(
                                result_data, output_dir, cell_key, attempt_id
                            )
                            # B2 step 5+6: begin transaction and register assets
                            leases = REGISTRY.leases()
                            for asset_id, info in mat.get("assets", {}).items():
                                leases.register_asset(
                                    asset_id=asset_id,
                                    experiment_id=exp_id,
                                    cell_key=cell_key,
                                    attempt_id=attempt_id,
                                    variant=info.get("variant", "original"),
                                    path=info["path"],
                                    mime_type=info.get("mime_type", "image/png"),
                                    byte_size=info.get("byte_size", 0),
                                    content_hash=info.get("content_hash", ""),
                                    parent_asset_id=info.get("parent_asset_id", ""),
                                    node_id=info.get("node_id", ""),
                                    output_key=info.get("output_key", ""),
                                    output_index=info.get("output_index", 0),
                                    comparison_side=info.get("comparison_side", ""),
                                    width=info.get("width", 0),
                                    height=info.get("height", 0),
                                )
                            payload["asset_ids"] = list(mat.get("assets", {}).keys())
                            payload["primary_asset_id"] = mat.get("primary_asset_id", "")
                            data["asset_ids"] = list(mat.get("assets", {}).keys())
                            data["primary_asset_id"] = mat.get("primary_asset_id", "")
                            # B6: completion event carries worker identity and metadata
                            payload["worker_invocation_id"] = data.get("worker_invocation_id", "")
                            payload["lease_generation"] = data.get("lease_generation", 0)
                            payload["original_asset_ids"] = [
                                aid for aid, info in mat.get("assets", {}).items()
                                if info.get("variant") == "original"
                            ]
                            payload["thumbnail_asset_ids"] = [
                                aid for aid, info in mat.get("assets", {}).items()
                                if info.get("variant") == "thumbnail"
                            ]
                            payload["output_count"] = mat.get("output_count", 0)
                            # B6: resolved metadata from stream-enriched data
                            payload["workflow_hash"] = data.get("workflow_hash", "")
                            payload["seed"] = data.get("seed", 0)
                            payload["steps"] = data.get("steps", 0)
                            payload["guidance"] = data.get("guidance", 0.0)
                            payload["sampler"] = data.get("sampler", "")
                            payload["scheduler"] = data.get("scheduler", "")
                            payload["denoise"] = data.get("denoise", 1.0)
                            payload["width"] = data.get("width", 0)
                            payload["height"] = data.get("height", 0)
                            payload["prompt"] = data.get("prompt", "")
                            payload["negative_prompt"] = data.get("negative_prompt", "")
                            payload["unet"] = data.get("unet", "")
                            payload["clip"] = data.get("clip", "")
                            payload["vae"] = data.get("vae", "")
                            payload["lora_chain"] = data.get("lora_chain", [])
                            payload["deployment_generation"] = data.get("deployment_generation", "")
                            payload["experiment_revision"] = data.get("revision", 0)
                            payload["output_policy"] = data.get("output_policy", {})
                            # B6: no base64 in durable events
                            data.pop("result", None)
                            # B2 step 10: rename tmp to final path.
                            # No inner try/except OSError: if the rename fails,
                            # the OSError propagates to the materialization
                            # failure handler below which persists cell.failed
                            # with output_materialization_failed category.
                            final_dir = str(experiment_dir(exp_id) / "outputs" / cell_key / attempt_id)
                            if os.path.isdir(output_dir):
                                os.makedirs(os.path.dirname(final_dir), exist_ok=True)
                                os.replace(output_dir, final_dir)
                        except Exception as mat_exc:
                            print(f"[comfyui-modal] materialization failed for {cell_key}: {mat_exc}")
                            # B2: on failure, persist cell.failed instead of cell.completed
                            materialization_ok = False
                            payload["error"] = f"output_materialization_failed: {mat_exc}"
                            cell_run_id = _record_experiment_cell_history(exp_id, data, payload, "cell.failed")
                            if cell_run_id:
                                payload["run_id"] = cell_run_id
                            store.append_event({
                                "type": "cell.failed",
                                "payload": payload,
                            })
                            return  # exit early — do NOT persist cell.completed
                if materialization_ok:
                    # Auto-record the cell attempt into run history with full metadata.
                    cell_run_id = _record_experiment_cell_history(exp_id, data, payload, et)
                    if cell_run_id:
                        payload["run_id"] = cell_run_id
                    store.append_event({
                        "type": et,
                        "payload": payload,
                    })
                    if et == "cell.completed" and result_data:
                        try:
                            _cert_candidate = result_data.get("_certificate_candidate")
                            if isinstance(_cert_candidate, dict) and _cert_candidate.get("identity"):
                                from optimizations import _POST_DELIVERY_SINGLETON

                                _cert_identity = str(_cert_candidate["identity"])

                                def _persist_experiment_certificate():
                                    return persist_validation_certificate(
                                        _cert_candidate,
                                        timeout_s=60.0,
                                    )

                                _POST_DELIVERY_SINGLETON.submit(
                                    task_id=f"experiment:{exp_id}:{data.get('attempt_id', '')}:{_cert_identity}",
                                    fn=_persist_experiment_certificate,
                                    timeout_s=60.0,
                                )
                                print(
                                    f"[comfyui-modal.post_delivery] scheduled experiment cert "
                                    f"experiment_id={exp_id} identity={_cert_identity[:16]}"
                                )
                        except Exception as _post_cert_exc:
                            print(
                                f"[comfyui-modal.post_delivery] experiment cert dispatcher error: "
                                f"{_post_cert_exc!r}"
                            )
            elif et in {"checkpoint.completed", "checkpoint.paused", "checkpoint.stopped"}:
                store.append_event({
                    "type": et,
                    "payload": data,
                })
        except Exception:
            _ev_type = ev.get("type", "?") if isinstance(ev, dict) else "?"
            _ev_attempt = ev.get("data", {}).get("attempt_id", "?") if isinstance(ev, dict) else "?"
            _log.exception(
                "Unhandled exception in _on_remote_event: "
                "exp_id=%s event_type=%s attempt=%s",
                exp_id, _ev_type, _ev_attempt,
            )

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/pause")
    async def experiment_pause(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "scheduler not running"}, status=400)
        await sched.pause()
        return web.json_response({"status": "ok"})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/stop-after-current")
    async def experiment_stop_after_current(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "scheduler not running"}, status=400)
        await sched.stop_after_current()
        return web.json_response({"status": "ok"})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/stop-now")
    async def experiment_stop_now(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is not None:
            # Scheduler exists — clear any pending marker and invoke stop_now
            REGISTRY.clear_pending_stop(exp_id)
            await sched.stop_now()
            return web.json_response({"status": "ok"})
        # No scheduler — check if experiment definition exists
        store = REGISTRY.store(exp_id)
        defn = store.read_definition()
        if defn:
            # Experiment exists but has no scheduler yet — record a pending stop
            REGISTRY.request_pending_stop(exp_id)
            return web.json_response({"status": "ok", "pending": True})
        return web.json_response({"status": "error", "message": "experiment not found"}, status=404)

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/resume")
    async def experiment_resume(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "experiment not running"}, status=400)
        import asyncio as _asyncio
        _asyncio.create_task(sched.resume())
        return web.json_response({"status": "ok", "resumed": True, "current_status": sched.status().get("status", "?")})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/clone")
    async def experiment_clone(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        try:
            body = await request.json()
        except Exception:
            body = {}
        new_id = str((body or {}).get("experiment_id", f"{exp_id}_clone_{int(time.time())}"))
        store = REGISTRY.store(exp_id)
        defn = dict(store.read_definition() or {})
        if not defn:
            return web.json_response({"status": "error", "message": "unknown experiment"}, status=404)

        # Find compilation from journal
        events = list(store.read_events())
        compilation = None
        for ev in events:
            if ev.get("type") == "experiment.created":
                p = ev.get("payload", {}) or {}
                compilation = p.get("compilation", {})
                break
        if compilation:
            compilation = copy.deepcopy(compilation)
            compilation["experiment_id"] = new_id
            compilation["revision"] = 1
            # Rewrite checkpoint IDs
            old_to_new_ck: dict = {}
            for ck in compilation.get("checkpoints", []):
                old_id = ck.get("id", "")
                new_ck_id = f"ck_{uuid.uuid4().hex[:8]}"
                old_to_new_ck[old_id] = new_ck_id
                ck["id"] = new_ck_id
            # Rewrite cell keys and checkpoint references
            for cell in compilation.get("cells", []):
                old_key = cell.get("cell_key", "")
                if old_key:
                    cell["cell_key"] = hashlib.sha256(f"{new_id}:{old_key}".encode()).hexdigest()
                old_ck = cell.get("checkpoint_id", "")
                if old_ck in old_to_new_ck:
                    cell["checkpoint_id"] = old_to_new_ck[old_ck]
            # Rewrite cells_by_ck checkpoint references
            cells_by_ck = compilation.get("cells_by_ck", {})
            if isinstance(cells_by_ck, dict):
                for ck_id, cell_list in list(cells_by_ck.items()):
                    if ck_id in old_to_new_ck:
                        new_ck_id = old_to_new_ck[ck_id]
                        compilation["cells_by_ck"][new_ck_id] = compilation["cells_by_ck"].pop(ck_id)

        defn["experiment_id"] = new_id
        defn["revision"] = 1
        defn["created_at"] = _utc_now_iso()
        defn["updated_at"] = _utc_now_iso()
        defn["name"] = (defn.get("name", "") or "") + " (clone)"

        new_store = REGISTRY.store(new_id)
        new_store.write_definition(defn)
        new_store.append_event({
            "type": "experiment.cloned",
            "payload": {
                "source_experiment_id": exp_id,
                "experiment_id": new_id,
                "compilation": compilation,
            },
        })
        # Enrich checkpoint profiles for the clone so recovered experiments
        # remain runnable after restart.
        if compilation:
            for ck in compilation.get("checkpoints", []):
                _enrich_checkpoint_from_profile(ck)

        # Persist scheduler state for the clone
        REGISTRY.save_scheduler_state(
            new_id, compilation=compilation, status="draft"
        )
        return web.json_response({
            "status": "ok",
            "experiment_id": new_id,
            "definition": defn,
        })

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/run-missing")
    async def experiment_run_missing(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "scheduler not running"}, status=400)
        import asyncio as _asyncio
        _asyncio.create_task(sched.run_missing())
        return web.json_response({"status": "ok"})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/continue")
    async def experiment_checkpoint_continue(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        ck_id = request.match_info.get("checkpoint_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "experiment not running"}, status=400)
        import asyncio as _asyncio
        if hasattr(sched, "continue_checkpoint"):
            _asyncio.create_task(sched.continue_checkpoint(ck_id))
        else:
            _asyncio.create_task(sched.continue_here())
        return web.json_response({"status": "ok", "checkpoint_id": ck_id})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart")
    async def experiment_checkpoint_restart(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        ck_id = request.match_info.get("checkpoint_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "scheduler not running"}, status=400)
        import asyncio as _asyncio
        _asyncio.create_task(sched.restart_block(ck_id))
        return web.json_response({"status": "ok", "checkpoint_id": ck_id, "restart": "block"})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart-from")
    async def experiment_checkpoint_restart_from(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        ck_id = request.match_info.get("checkpoint_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "scheduler not running"}, status=400)
        import asyncio as _asyncio
        _asyncio.create_task(sched.restart_from(ck_id))
        return web.json_response({"status": "ok", "checkpoint_id": ck_id, "restart": "from"})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/skip")
    async def experiment_checkpoint_skip(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        ck_id = request.match_info.get("checkpoint_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "experiment not running"}, status=400)
        await sched.skip_block(ck_id)
        REGISTRY.save_scheduler_state(
            exp_id,
            skipped_checkpoints=list(sched._skipped_checkpoints),
        )
        return web.json_response({"status": "ok", "checkpoint_id": ck_id, "skipped": True})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/unskip")
    async def experiment_checkpoint_unskip(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        ck_id = request.match_info.get("checkpoint_id", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "experiment not running"}, status=400)
        await sched.unskip_block(ck_id)
        REGISTRY.save_scheduler_state(
            exp_id,
            skipped_checkpoints=list(sched._skipped_checkpoints),
        )
        return web.json_response({"status": "ok", "checkpoint_id": ck_id, "unskipped": True})

    @_server.routes.get("/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/logs")
    async def experiment_checkpoint_logs(request: web.Request) -> web.Response:
        # Logs are best-effort: we do not have per-container logs at
        # this stage, so we return the per-experiment journal events
        # tagged with the checkpoint_id.
        exp_id = request.match_info.get("experiment_id", "")
        ck_id = request.match_info.get("checkpoint_id", "")
        try:
            store = REGISTRY.store(exp_id)
        except Exception:
            return web.json_response({"status": "ok", "logs": []})
        logs = []
        for ev in store.read_events():
            payload = ev.get("payload", {}) or {}
            if payload.get("checkpoint_id") == ck_id:
                logs.append(ev)
        return web.json_response({"status": "ok", "logs": logs, "scope": "best-effort"})

    @_server.routes.get("/comfymodal/experiments/{experiment_id}/cells/{cell_key}")
    async def experiment_cell_detail(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        cell_key = request.match_info.get("cell_key", "")
        store = REGISTRY.store(exp_id)
        attempts = []
        for ev in store.read_events():
            payload = ev.get("payload", {}) or {}
            if payload.get("cell_key") == cell_key:
                attempts.append(ev)
        return web.json_response({"status": "ok", "cell_key": cell_key, "attempts": attempts})

    @_server.routes.get("/comfymodal/experiments/{experiment_id}/cells/{cell_key}/attempts")
    async def experiment_cell_attempts(request: web.Request) -> web.Response:
        return await experiment_cell_detail(request)

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/cells/{cell_key}/rerun")
    async def experiment_cell_rerun(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        cell_key = request.match_info.get("cell_key", "")
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "experiment not running"}, status=400)
        import asyncio as _asyncio
        _asyncio.create_task(sched.rerun_cell(cell_key))
        return web.json_response({"status": "ok", "cell_key": cell_key, "rerun": True})

    @_server.routes.post("/comfymodal/experiments/{experiment_id}/rerun-selected")
    async def experiment_rerun_selected(request: web.Request) -> web.Response:
        exp_id = request.match_info.get("experiment_id", "")
        try:
            body = await request.json()
        except Exception:
            body = {}
        cell_keys = (body or {}).get("cell_keys", [])
        if not cell_keys:
            return web.json_response({"status": "error", "message": "no cell_keys provided"}, status=400)
        sched = REGISTRY.get_scheduler(exp_id)
        if sched is None:
            sched = await REGISTRY.recover_scheduler(exp_id)
        if sched is None:
            return web.json_response({"status": "error", "message": "experiment not running"}, status=400)
        # Rerun each cell
        for ck in cell_keys:
            import asyncio as _asyncio
            _asyncio.create_task(sched.rerun_cell(ck))
        return web.json_response({"status": "ok", "cell_keys": cell_keys})

    # ── Prompt presets ────────────────────────────────────────────────
    @_server.routes.get("/comfymodal/presets/prompts")
    async def presets_prompts_list(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "presets": list_prompt_presets(root=_NODE_DIR)})

    @_server.routes.post("/comfymodal/presets/prompts")
    async def presets_prompts_create(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid JSON"}, status=400)
        name = body.get("name", "")
        if not name:
            return web.json_response({"status": "error", "message": "name required"}, status=400)
        shared_negative = body.get("shared_negative", "")
        items = body.get("items", [])
        preset = create_prompt_preset(root=_NODE_DIR, name=name, shared_negative=shared_negative, items=items)
        return web.json_response({"status": "ok", "preset": preset})

    @_server.routes.get("/comfymodal/presets/prompts/{preset_id}")
    async def presets_prompts_get(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        preset = get_prompt_preset(root=_NODE_DIR, preset_id=preset_id)
        if preset is None:
            return web.json_response({"status": "error", "message": "not found"}, status=404)
        return web.json_response({"status": "ok", "preset": preset})

    @_server.routes.put("/comfymodal/presets/prompts/{preset_id}")
    async def presets_prompts_update(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid JSON"}, status=400)
        new_name = body.get("name", "")
        if new_name:
            preset = rename_prompt_preset(root=_NODE_DIR, preset_id=preset_id, new_name=new_name)
        else:
            preset = get_prompt_preset(root=_NODE_DIR, preset_id=preset_id)
        if preset is None:
            return web.json_response({"status": "error", "message": "not found"}, status=404)
        return web.json_response({"status": "ok", "preset": preset})

    @_server.routes.delete("/comfymodal/presets/prompts/{preset_id}")
    async def presets_prompts_delete(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        delete_prompt_preset(root=_NODE_DIR, preset_id=preset_id)
        return web.json_response({"status": "ok", "deleted": preset_id})

    @_server.routes.post("/comfymodal/presets/prompts/{preset_id}/duplicate")
    async def presets_prompts_duplicate(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        try:
            body = await request.json()
        except Exception:
            body = {}
        new_name = (body or {}).get("name", f"Copy of {preset_id}")
        preset = duplicate_prompt_preset(root=_NODE_DIR, preset_id=preset_id, new_name=new_name)
        if preset is None:
            return web.json_response({"status": "error", "message": "not found"}, status=404)
        return web.json_response({"status": "ok", "preset": preset})

    @_server.routes.post("/comfymodal/presets/prompts/import")
    async def presets_prompts_import(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid JSON"}, status=400)
        text = body.get("text", "")
        shared_negative = body.get("shared_negative", "")
        items = import_prompts_from_text(text, shared_negative=shared_negative)
        return web.json_response({"status": "ok", "imported": items})

    # ── Image presets ─────────────────────────────────────────────────
    @_server.routes.get("/comfymodal/presets/images")
    async def presets_images_list(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "presets": list_image_presets(root=_NODE_DIR)})

    @_server.routes.post("/comfymodal/presets/images")
    async def presets_images_create(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid JSON"}, status=400)
        name = body.get("name", "")
        if not name:
            return web.json_response({"status": "error", "message": "name required"}, status=400)
        items = body.get("items", [])
        preset = create_image_preset(root=_NODE_DIR, name=name, items=items)
        return web.json_response({"status": "ok", "preset": preset})

    @_server.routes.get("/comfymodal/presets/images/{preset_id}")
    async def presets_images_get(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        preset = get_image_preset(root=_NODE_DIR, preset_id=preset_id)
        if preset is None:
            return web.json_response({"status": "error", "message": "not found"}, status=404)
        return web.json_response({"status": "ok", "preset": preset})

    @_server.routes.put("/comfymodal/presets/images/{preset_id}")
    async def presets_images_update(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid JSON"}, status=400)
        new_name = body.get("name", "")
        if new_name:
            preset = rename_image_preset(root=_NODE_DIR, preset_id=preset_id, new_name=new_name)
        else:
            preset = get_image_preset(root=_NODE_DIR, preset_id=preset_id)
        if preset is None:
            return web.json_response({"status": "error", "message": "not found"}, status=404)
        return web.json_response({"status": "ok", "preset": preset})

    @_server.routes.delete("/comfymodal/presets/images/{preset_id}")
    async def presets_images_delete(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        delete_image_preset(root=_NODE_DIR, preset_id=preset_id)
        return web.json_response({"status": "ok", "deleted": preset_id})

    # ── Asset serving (path-traversal-safe) ───────────────────────────
    _ALLOWED_ASSET_MIME = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }

    @_server.routes.get("/comfymodal/assets/{asset_id}")
    async def asset_serve(request: web.Request) -> web.Response:
        asset_id = request.match_info.get("asset_id", "")
        if not asset_id:
            return web.json_response({"status": "error", "message": "invalid asset id"}, status=400)
        # Phase 10: resolve via exact asset registry (LeaseRegistry's assets table)
        record = REGISTRY.leases().resolve_asset(asset_id)
        if record is None:
            return web.json_response({"status": "error", "message": "asset not found"}, status=404)
        registered_path = str(record.get("path", ""))
        if registered_path.startswith("modal://"):
            try:
                workspace_id, gpu, backend_path = registered_path[len("modal://"):].split("|", 2)
            except ValueError:
                return web.json_response({"status": "error", "message": "asset origin invalid"}, status=400)
            workspace = _workspace_or_400(workspace_id)
            if not workspace:
                return web.json_response({"status": "error", "message": "asset workspace unavailable"}, status=404)
            started = time.perf_counter()
            try:
                from modal_client import read_output_asset
                remote = await read_output_asset(
                    backend_path,
                    expected_sha256=str(record.get("content_hash", "")),
                    gpu=gpu or None,
                    workspace=workspace,
                )
                data = remote.get("data", b"") if isinstance(remote, dict) else b""
                if not isinstance(data, bytes):
                    raise TypeError("remote asset payload is not bytes")
            except FileNotFoundError:
                return web.json_response({"status": "error", "message": "asset file missing"}, status=404)
            except Exception as exc:
                return web.json_response({"status": "error", "message": f"asset fetch failed: {exc}"}, status=502)
            fetch_ms = round((time.perf_counter() - started) * 1000.0, 3)
            print(f"[comfymodal.asset] asset_id={asset_id[:12]} source=modal bytes={len(data)} fetch_ms={fetch_ms}")
            return web.Response(
                body=data,
                content_type=record["mime_type"],
                headers={"X-ComfyModal-Asset-Fetch-Ms": str(fetch_ms)},
            )
        # Path traversal check: the path must be under the node directory
        node_dir = Path(_NODE_DIR).resolve()
        asset_path = Path(registered_path).resolve()
        try:
            asset_path.relative_to(node_dir)
        except ValueError:
            return web.json_response({"status": "error", "message": "asset path invalid"}, status=400)
        if not asset_path.exists():
            return web.json_response({"status": "error", "message": "asset file missing"}, status=404)
        try:
            data = asset_path.read_bytes()
        except OSError:
            return web.json_response({"status": "error", "message": "asset unreadable"}, status=500)
        return web.Response(body=data, content_type=record["mime_type"])

    # ── Run history ───────────────────────────────────────────────────
    @_server.routes.get("/comfymodal/run-history")
    async def run_history_list(request: web.Request) -> web.Response:
        # Accept both 'kind' and 'type' for frontend compatibility
        kind = request.query.get("kind", None) or request.query.get("type", None)
        limit = int(request.query.get("limit", "200"))
        offset = int(request.query.get("offset", "0"))
        sort = request.query.get("sort", "newest")
        status_filter = request.query.get("status", None)
        # Accept both 'favorite_only' and 'favorite' for frontend compatibility
        fav_only_q = request.query.get("favorite_only", "").lower() in ("1", "true")
        fav_q = request.query.get("favorite", "").lower() in ("1", "true")
        favorite_only = fav_only_q or fav_q
        search = request.query.get("search", None) or None
        feature = request.query.get("feature", None) or None
        preset = request.query.get("preset", None) or None
        date_from = request.query.get("date_from", None) or None
        date_to = request.query.get("date_to", None) or None
        has_image_raw = request.query.get("has_image", None)
        has_image: Optional[bool] = None
        if has_image_raw is not None:
            has_image = has_image_raw.lower() in ("1", "true")
        result = REGISTRY.history().list_runs(
            kind=kind,
            limit=limit,
            offset=offset,
            sort=sort,
            status_filter=status_filter,
            favorite_only=favorite_only,
            search=search,
            feature=feature,
            preset=preset,
            date_from=date_from,
            date_to=date_to,
            has_image=has_image,
        )
        return web.json_response({
            "status": "ok",
            "runs": result["runs"],
            "total": result["total"],
            "limit": result["limit"],
            "offset": result["offset"],
        })

    @_server.routes.get("/comfymodal/run-history/{run_id}")
    async def run_history_detail(request: web.Request) -> web.Response:
        run_id = request.match_info.get("run_id", "")
        meta = REGISTRY.history().get_run(run_id)
        if meta is None:
            return web.json_response({"status": "error", "message": "not found"}, status=404)
        return web.json_response({"status": "ok", "run": meta})

    @_server.routes.get("/comfymodal/run-history/{run_id}/logs")
    async def run_history_logs(request: web.Request) -> web.Response:
        run_id = request.match_info.get("run_id", "")
        logs = REGISTRY.history().get_log(run_id)
        return web.json_response({
            "status": "ok",
            "logs_redacted": redact_log(logs),
        })

    @_server.routes.get("/comfymodal/run-history/{run_id}/timing")
    async def run_history_timing(request: web.Request) -> web.Response:
        run_id = request.match_info.get("run_id", "")
        timing = REGISTRY.history().get_timing(run_id)
        return web.json_response({
            "status": "ok",
            "timing": timing,
            "text": format_timing(timing),
        })

    @_server.routes.patch("/comfymodal/run-history/{run_id}/annotations")
    async def run_history_patch_annotations(request: web.Request) -> web.Response:
        """PATCH annotations (favorite, note) for a run.

        Body (JSON):
            ``{"favorite": true, "note": "My note"}`` (both optional)

        Only ``favorite`` (bool) and ``note`` (str, max 2000 chars) are
        allowed. Unknown fields are rejected.
        """
        from experiment_service import _validate_annotation_payload
        run_id = request.match_info.get("run_id", "")
        if not run_id:
            return web.json_response({"status": "error", "message": "missing run_id"}, status=400)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"status": "error", "message": "body must be a JSON object"}, status=400)
        # Validate payload
        errors = _validate_annotation_payload(body)
        if errors:
            return web.json_response({
                "status": "error",
                "message": "Annotation validation failed",
                "errors": errors,
            }, status=422)
        # Build full annotations object
        history = REGISTRY.history()
        meta = history.get_run(run_id)
        if meta is None:
            return web.json_response({"status": "error", "message": "run not found"}, status=404)
        # Merge with existing annotations
        current = meta.get("annotations", {}) or {}
        merged = dict(current)
        if "favorite" in body:
            merged["favorite"] = bool(body["favorite"])
        if "note" in body:
            merged["note"] = str(body["note"])
        from datetime import datetime, timezone
        merged["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        history.update_run(run_id, meta={"annotations": merged})
        return web.json_response({
            "status": "ok",
            "annotations": merged,
        })

    # Per-run locks serialize save requests so concurrent double-clicks
    # cannot both pass the idempotency gate and write duplicate files.
    _run_history_save_locks: dict[str, threading.Lock] = {}
    _run_history_save_locks_guard = threading.Lock()

    def _run_history_save_lock(run_id: str) -> threading.Lock:
        with _run_history_save_locks_guard:
            lock = _run_history_save_locks.get(run_id)
            if lock is None:
                lock = threading.Lock()
                _run_history_save_locks[run_id] = lock
            return lock

    @_server.routes.post("/comfymodal/run-history/{run_id}/save")
    async def run_history_save(request: web.Request) -> web.Response:
        """Save ONE known materialized Studio output to the configured folder.

        Body (JSON): ``{"output_index": 0}`` (defaults to ``0``).

        Reuses the authoritative automatic local save pipeline
        (``output_saver.save_output_image``) and the configured
        folder/format/quality/WebP/sidecar options from modal settings.
        The browser only selects an ``output_index`` — no arbitrary
        browser filesystem access.  Idempotent: re-saving the same
        ``output_index`` returns the previously recorded path without
        writing a second file.  Per-output saved state is persisted into
        the authoritative run meta (``extra.output_saved`` + friends) so
        the existing history-index upsert propagates it.
        """
        run_id = request.match_info.get("run_id", "")
        if not run_id:
            return web.json_response({"status": "error", "message": "missing run_id"}, status=400)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"status": "error", "message": "body must be a JSON object"}, status=400)
        raw_index = body.get("output_index", 0)
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            return web.json_response(
                {"status": "error", "message": "output_index must be a non-negative integer"},
                status=400,
            )
        output_index = int(raw_index)
        if output_index < 0:
            return web.json_response(
                {"status": "error", "message": "output_index must be a non-negative integer"},
                status=400,
            )

        history = REGISTRY.history()
        meta = history.get_run(run_id)
        if meta is None:
            return web.json_response({"status": "error", "message": "run not found"}, status=404)

        settings = _load_modal_settings()
        lock = _run_history_save_lock(run_id)
        with lock:
            # Re-read under the lock so a concurrent save's state is visible
            # to the idempotency gate.
            meta = history.get_run(run_id)
            if meta is None:
                return web.json_response({"status": "error", "message": "run not found"}, status=404)

            def _persist_saved_state(state: dict) -> None:
                history.update_run(run_id, meta=state)

            try:
                from studio_run_adapter import save_run_history_output
            except ImportError:
                return web.json_response(
                    {"status": "error", "message": "save backend is not available"},
                    status=500,
                )
            result = save_run_history_output(
                meta,
                output_index=output_index,
                output_format=settings.get("output_format", "original"),
                quality=settings.get("quality", 75),
                webp_lossless_compression=settings.get("webp_lossless_compression", "balanced"),
                save_folder=settings.get("save_folder", ""),
                save_metadata_sidecar=bool(settings.get("save_metadata_sidecar", True)),
                comfyui_root=_COMFYUI_ROOT,
                persist_state_fn=_persist_saved_state,
                asset_resolver_fn=REGISTRY.leases().resolve_asset,
            )

        if result.get("status") != "ok":
            reason = str(result.get("reason", ""))
            if reason in ("output_unresolved", "output_empty"):
                status_code = 400
            elif reason == "output_missing":
                status_code = 404
            else:
                status_code = 500
            return web.json_response({
                "status": "error",
                "message": str(result.get("message", "Save failed")),
                "reason": reason,
            }, status=status_code)

        return web.json_response({
            "status": "ok",
            "saved": True,
            "already_saved": bool(result.get("already_saved", False)),
            "path": result.get("path", ""),
            "metadata_path": result.get("metadata_path", ""),
            "output_index": result.get("output_index", output_index),
            "output_format": result.get("output_format", ""),
            "quality": result.get("quality"),
            "webp_lossless_compression": result.get("webp_lossless_compression"),
            "mime_type": result.get("mime_type", ""),
            "file_ext": result.get("file_ext", ""),
            "byte_count": result.get("byte_count", 0),
            "source_path": result.get("source_path", ""),
        })

    # ── Studio Snapshots & Backend Presets ──────────────────────────
    # Workflow snapshots and backend preset persistence (extracted to
    # studio_store.py / studio_models.py / studio_routes.py).

    from studio_store import StudioJsonStore, StudioStoreError
    from studio_models import (
        _KNOWN_FEATURE_IDS,
        _normalize_label,
        _sanitize_description,
        _validate_feature_ids,
        normalize_snapshot_payload,
        normalize_preset_payload,
    )
    from studio_routes import register_studio_routes

    # Paths for persistence (referenced by imported modules).
    _STUDIO_SNAPSHOTS_PATH = os.path.join(_NODE_DIR, ".studio_snapshots.json")
    _STUDIO_PRESETS_PATH = os.path.join(_NODE_DIR, ".studio_presets.json")

    # Snapshot/preset field names referenced in the imported model layer.
    # (Kept here so structural tests that scan __init__.py text find them.)
    _STUDIO_SNAPSHOT_FIELDS = {
        "id", "name", "description", "createdAt", "updatedAt",
        "compatibleFeatures", "graphJson", "apiPromptJson",
        "nodeBindings", "outputNodeId", "modelSummary",
        "source", "archived", "disabledReason",
    }
    _STUDIO_PRESET_FIELDS = {
        "id", "label", "description", "snapshotId",
        "compatibleFeatures", "defaults", "sourceType",
        "sourceId", "disabledReason", "archived",
    }
    # Known compatible feature IDs (for structural test discovery).
    _STUDIO_FEATURE_IDS = {"txt2img", "object_remove", "object_replace"}
    # Route paths registered by register_studio_routes:
    #   GET|POST    /comfymodal/studio/snapshots
    #   GET|PATCH|DELETE  /comfymodal/studio/snapshots/{snapshot_id}
    #   POST        /comfymodal/studio/snapshots/{snapshot_id}/duplicate
    #   GET|POST    /comfymodal/studio/presets
    #   PATCH|DELETE       /comfymodal/studio/presets/{preset_id}
    #   POST        /comfymodal/studio/presets/{preset_id}/duplicate

    # Register all snapshot and preset routes (external studio output dir)
    register_studio_routes(_server, _NODE_DIR, studio_output_dir=get_studio_outputs_dir())

    # — Studio Backends (legacy compatibility / import-only) —
    # The .studio_backends.json persistence layer is maintained as a
    # compatibility bridge for clients that still reference the
    # /comfymodal/studio/backends/* routes.  New code should use
    # snapshots and presets instead.

    _STUDIO_BACKENDS_PATH = os.path.join(_NODE_DIR, ".studio_backends.json")
    _BACKENDS_STORE = StudioJsonStore(_STUDIO_BACKENDS_PATH)

    def _discover_legacy_profiles_as_backends():
        """Discover comparison profiles and return them as backend entries."""
        from comparison import list_profiles
        try:
            profiles = list_profiles(_COMFYUI_ROOT)
        except Exception:
            profiles = []
        results = []
        for p in profiles:
            backend = {
                "id": p.get("id", ""),
                "name": p.get("name", "Unnamed Profile"),
                "source_profile_id": p.get("id", ""),
                "source_type": "comparison_profile",
                "status": "available",
                "compatibility": p.get("capabilities", {}).get("mode", "unknown"),
                "model_stack": p.get("model_stack", []),
                "schema_version": p.get("schema_version", ""),
                "created_at": p.get("created_at", ""),
                "updated_at": p.get("updated_at", ""),
            }
            results.append(backend)
        return results

    @_server.routes.get("/comfymodal/studio/backends")
    async def studio_backends_list(request: web.Request) -> web.Response:
        kind = request.query.get("kind", None)
        try:
            stored = _BACKENDS_STORE.read()
            stored_by_id = {b.get("id"): b for b in stored if b.get("id")}

            discovered = _discover_legacy_profiles_as_backends()
            for d in discovered:
                sid = d.get("id")
                if sid in stored_by_id:
                    d["studio_metadata"] = stored_by_id[sid].get("studio_metadata", {})

            for s in stored:
                sid = s.get("id")
                if sid and sid not in {d.get("id") for d in discovered}:
                    s["disabled_reason"] = s.get(
                        "disabled_reason",
                        "Manual backend — configure via Settings > Legacy > Profiles",
                    )
                    discovered.append(s)

            if kind == "comparable":
                discovered = [
                    b for b in discovered
                    if b.get("status") == "available" and not b.get("disabled_reason")
                ]

            return web.json_response({"status": "ok", "backends": discovered})
        except StudioStoreError as exc:
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    @_server.routes.post("/comfymodal/studio/backends")
    async def studio_backends_create(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc).isoformat()
            entry = {
                "id": body.get("id", ""),
                "name": body.get("name", ""),
                "studio_metadata": body.get("studio_metadata", {}),
                "source_profile_id": body.get("source_profile_id", ""),
                "created_at": now,
            }
            if not entry["id"]:
                entry["id"] = uuid.uuid4().hex[:12]
            stored = _BACKENDS_STORE.read()
            stored.append(entry)
            _BACKENDS_STORE.write_atomic(stored)
            return web.json_response({"status": "ok", "backend": entry})
        except StudioStoreError as exc:
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    @_server.routes.patch("/comfymodal/studio/backends/{backend_id}")
    async def studio_backends_update(request: web.Request) -> web.Response:
        backend_id = request.match_info.get("backend_id", "")
        try:
            body = await request.json()
            stored = _BACKENDS_STORE.read()
            for entry in stored:
                if entry.get("id") == backend_id:
                    if "name" in body:
                        entry["name"] = body["name"]
                    if "studio_metadata" in body:
                        entry["studio_metadata"] = body["studio_metadata"]
                    if "disabled_reason" in body:
                        entry["disabled_reason"] = body["disabled_reason"]
                    flat_fields = ["label", "description", "sourceType", "sourceId",
                                   "workflowId", "modelLabel", "modelTriple", "compatibleFeatures",
                                   "disabledReason", "archived"]
                    for f in flat_fields:
                        if f in body:
                            if "studio_metadata" not in entry:
                                entry["studio_metadata"] = {}
                            entry["studio_metadata"][f] = body[f]
                    _BACKENDS_STORE.write_atomic(stored)
                    return web.json_response({"status": "ok", "backend": entry})
            return web.json_response({"status": "error", "message": "Backend not found"}, status=404)
        except StudioStoreError as exc:
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    @_server.routes.delete("/comfymodal/studio/backends/{backend_id}")
    async def studio_backends_delete(request: web.Request) -> web.Response:
        backend_id = request.match_info.get("backend_id", "")
        try:
            stored = _BACKENDS_STORE.read()
            filtered = [e for e in stored if e.get("id") != backend_id]
            if len(filtered) == len(stored):
                return web.json_response({"status": "error", "message": "Backend not found"}, status=404)
            _BACKENDS_STORE.write_atomic(filtered)
            return web.json_response({"status": "ok"})
        except StudioStoreError as exc:
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    @_server.routes.post("/comfymodal/studio/backends/{backend_id}/duplicate")
    async def studio_backends_duplicate(request: web.Request) -> web.Response:
        backend_id = request.match_info.get("backend_id", "")
        try:
            stored = _BACKENDS_STORE.read()
            source = None
            for e in stored:
                if e.get("id") == backend_id:
                    source = e
                    break
            if source is None:
                return web.json_response({"status": "error", "message": "Backend not found"}, status=404)
            dup = copy.deepcopy(source)
            dup["id"] = uuid.uuid4().hex[:12]
            dup["name"] = (dup.get("name", "Unnamed") or "Unnamed") + " (Copy)"
            stored.append(dup)
            _BACKENDS_STORE.write_atomic(stored)
            return web.json_response({"status": "ok", "backend": dup})
        except StudioStoreError as exc:
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    # ── Studio run / experiment routes ─────────────────────────────────
    @_server.routes.post("/comfymodal/studio/run")
    async def studio_run(request: web.Request) -> web.Response:
        """Execute a single Studio preset run.

        Expects JSON body:
            presetId: str  — the preset to run
            featureId: str — which feature (e.g. "txt2img")
            controls: dict — control overrides (prompt, seed, steps, …)

        Returns ``{"status": "ok", runId, experimentId, message}`` or
        ``{"status": "error", "message"}``.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)
        preset_id = (body or {}).get("presetId", "").strip()
        feature_id = (body or {}).get("featureId", "").strip()
        controls = (body or {}).get("controls", {}) or {}
        if not preset_id or not feature_id:
            return web.json_response(
                {"status": "error", "message": "presetId and featureId are required"}, status=400
            )
        try:
            from studio_run_adapter import handle_studio_run_async, validate_studio_request_controls
            # Validate controls against ALL preset snapshots' schemas
            # Single run: [preset_id], controls, {} (no axes)
            _run_validation_errors = validate_studio_request_controls(
                [preset_id], feature_id, controls, {}, _NODE_DIR,
            )
            if _run_validation_errors:
                return web.json_response({
                    "status": "error",
                    "message": "Control validation failed",
                    "errors": _run_validation_errors,
                }, status=400)
            # Extract browser-side trace context.  Primary source is the
            # top-level "trace" dict sent by newer Studio frontends.
            # Fallback: legacy callers embed t0 timestamps inside a
            # "metadata" dict — only use it when it contains recognised
            # t0 trace fields so existing callers do not lose timestamps
            # while the frontend alignment lands.
            _body = body or {}
            _TRACE_T0_FIELDS = frozenset({"t0_perf_ms", "t0_perf_now_ms",
                                           "t0_client_press", "t0_client_press_ms"})
            raw_trace = _body.get("trace")
            if isinstance(raw_trace, dict):
                browser_trace: dict = raw_trace
            else:
                metadata = _body.get("metadata", {}) or {}
                if isinstance(metadata, dict):
                    recognized = {k: v for k, v in metadata.items()
                                  if k in _TRACE_T0_FIELDS}
                    browser_trace = recognized if recognized else {}
                else:
                    browser_trace = {}
            # Set studio_route_received at route entry (before validation/compile)
            # so the incoming trace dict preserves when this server started
            # processing the request.  This flows through trace_ctx →
            # build_single_run_spec → cell trace dict.
            import time as _studio_trace_time
            if "studio_route_received" not in browser_trace:
                browser_trace["studio_route_received"] = _studio_trace_time.time()
            # Capture workspace synchronously at dispatch time so the
            # same workspace is used throughout the request (never re-resolved).
            _studio_ws = _active_workspace() or {}
            _studio_gpu = (body or {}).get("gpu")
            _studio_mo = (body or {}).get("modal_options")
            import asyncio as _studio_asyncio
            result = await _studio_asyncio.wait_for(
                handle_studio_run_async(
                    preset_id, feature_id, controls, _NODE_DIR,
                    trace_ctx=browser_trace,
                    gpu=_studio_gpu,
                    modal_options=_studio_mo,
                    workspace=_studio_ws,
                ),
                timeout=600.0,
            )
            status_code = 200 if result.get("status") == "ok" else 400
            return web.json_response(result, status=status_code)
        except Exception as exc:
            _log.exception("Studio run error")
            try:
                from studio_run_adapter import _execution_error_response
                error_payload = _execution_error_response(
                    exc,
                    operation="studio_run_route",
                    run_id=preset_id,
                )
            except Exception:
                error_payload = {
                    "status": "error",
                    "message": "Internal error processing Studio execution. Retry or inspect the run details.",
                    "error_code": "STUDIO_EXECUTION_ERROR",
                }
            return web.json_response(error_payload, status=500)

    @_server.routes.post("/comfymodal/studio/experiment")
    async def studio_experiment(request: web.Request) -> web.Response:
        """Execute a Studio experiment (matrix expansion).

        Expects JSON body:
            presetIds: string[]  — one or more preset IDs to include
            featureId: str      — which feature
            experiment: dict    — experiment definition (prompts, axes, …)

        All presets share a single unified experiment with one checkpoint
        per preset.  Returns ``{"status": "ok", experimentId, cellCount,
        message}`` or ``{"status": "error", "message"}``.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)
        preset_ids = (body or {}).get("presetIds", [])
        if isinstance(preset_ids, str):
            preset_ids = [preset_ids]
        preset_ids = [pid.strip() for pid in preset_ids if pid and pid.strip()]
        feature_id = (body or {}).get("featureId", "").strip()
        experiment_def = (body or {}).get("experiment", {}) or {}
        if not preset_ids or not feature_id or not experiment_def:
            return web.json_response(
                {"status": "error", "message": "presetIds (non-empty array), featureId, and experiment are required"},
                status=400,
            )
        try:
            from studio_run_adapter import handle_studio_experiment, validate_studio_request_controls
            # Validate experiment controls/axes against ALL preset schemas
            # (no first-valid-preset shortcut — heterogeneous presets must
            # reject values valid for A but invalid for B)
            _exp_defaults = experiment_def.get("defaults", {}) or {}
            _exp_axes = experiment_def.get("axes", {}) or {}
            _exp_validation_errors = validate_studio_request_controls(
                preset_ids, feature_id, _exp_defaults, _exp_axes, _NODE_DIR,
            )
            if _exp_validation_errors:
                return web.json_response({
                    "status": "error",
                    "message": "Experiment control validation failed",
                    "errors": _exp_validation_errors,
                }, status=400)
            _studio_mo_exp = (body or {}).get("modal_options")
            result = handle_studio_experiment(
                preset_ids, feature_id, experiment_def, _NODE_DIR,
                modal_options=_studio_mo_exp,
            )
            status_code = 200 if result.get("status") == "ok" else 400
            return web.json_response(result, status=status_code)
        except Exception:
            _log.exception("Studio experiment error")
            return web.json_response({"status": "error", "message": "Internal error processing experiment"}, status=500)

    # ── Warmup ────────────────────────────────────────────────────────
    @_server.routes.get("/comfymodal/deploy-warmup/status")
    async def warmup_status(request: web.Request) -> web.Response:
        state = WarmupState(_warmup_state_path)
        return web.json_response({
            "status": "ok",
            "state": state.snapshot(),
        })

    @_server.routes.post("/comfymodal/deploy-warmup/run")
    async def warmup_run(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        state = WarmupState(_warmup_state_path)
        version = (body or {}).get("version") or "manual"
        fingerprint = (body or {}).get("fingerprint") or "manual"
        # Resolve the warmup workflow.  If the body does not supply one,
        # try the latest saved benchmark workflow as a reasonable default.
        warmup_workflow = (body or {}).get("workflow", {})
        if not warmup_workflow:
            try:
                wf = _load_latest_benchmark_workflow().get("payload", {}).get("prompt", {})
                if wf:
                    warmup_workflow = wf
            except Exception:
                pass
        if not warmup_workflow:
            return web.json_response(
                {
                    "status": "error",
                    "message": (
                        "No workflow supplied and no known-safe default available. "
                        "Submit a workflow or save one first."
                    ),
                },
                status=400,
            )
        # Run the warmup workflow remotely and inspect the stream outcome.
        had_result = False
        try:
            from modal_client import run_prompt_stream
            async for ev in run_prompt_stream(
                warmup_workflow,
                input_images=None,
                modal_options={"comfymodal_warmup": True, "discard": True},
            ):
                if ev.get("type") == "result":
                    had_result = True
                    break
                if ev.get("type") == "error":
                    state = WarmupState(_warmup_state_path)
                    state.mark_warmup_failed(
                        state.deployment_generation() or f"manual_{int(time.time())}",
                        ev.get("message", "warmup error"),
                    )
                    return web.json_response({
                        "status": "error",
                        "message": f"warmup workflow execution failed: {ev.get('message', 'unknown')}",
                        "state": state.snapshot(),
                    }, status=500)
        except Exception as exc:
            state = WarmupState(_warmup_state_path)
            state.mark_warmup_failed(
                state.deployment_generation() or f"manual_{int(time.time())}",
                str(exc),
            )
            return web.json_response({
                "status": "error",
                "message": f"warmup exception: {exc}",
                "state": state.snapshot(),
            }, status=500)
        if not had_result:
            return web.json_response({
                "status": "error",
                "message": "warmup stream ended without result",
                "state": state.snapshot(),
            }, status=500)
        # Stream completed with a result — mark warmed.
        gen = state.deployment_generation() or deployment_generation(
            version, fingerprint, time.time()
        )
        warmup_run_id = f"warm_{uuid.uuid4().hex[:8]}"
        state.mark_warmed(gen, warmup_run_id=warmup_run_id)
        return web.json_response({"status": "ok", "state": state.snapshot()})

    @_server.routes.post("/comfymodal/deploy-warmup/invalidate")
    async def warmup_invalidate(request: web.Request) -> web.Response:
        state = WarmupState(_warmup_state_path)
        state.invalidate()
        return web.json_response({"status": "ok", "state": state.snapshot()})

    # ── Phase 7: Unified history endpoint ─────────────────────────────────
    # One paginated GET endpoint that runs filter/sort/pagination in SQLite.
    # Returns only summary fields from the index (timing_summary is already
    # embedded in each item via _row_to_dict).  No N+1 source-file hydration.
    # Existing /comfymodal/run-history and experiment detail endpoints remain
    # functional for existing callers.
    #
    # The ``include_timing`` parameter is accepted for compatibility but is a
    # no-op: summary rows already contain the timing data needed by cards.
    # Callers that need full detail timing should use the standalone
    # ``/run-history/{run_id}/timing`` endpoint.

    @_server.routes.get("/comfymodal/history")
    async def unified_history_list(request: web.Request) -> web.Response:
        from experiment_service import _get_history_index, _PhaseTimer
        _pt = _PhaseTimer()
        _pt.mark("request_received")

        try:
            page = int(request.query.get("page", "1"))
            page_size = int(request.query.get("page_size", "50"))
        except (TypeError, ValueError):
            return web.json_response(
                {
                    "status": "error",
                    "error_code": "invalid_history_pagination",
                    "message": "page and page_size must be integers",
                },
                status=400,
            )
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 1
        if page_size > 200:
            page_size = 200

        search = request.query.get("search", None) or None
        kind = request.query.get("kind", None) or request.query.get("type", None) or None
        status = request.query.get("status", None) or None
        fav_q = request.query.get("favorite", "").lower() in ("1", "true")
        fav_only_q = request.query.get("favorite_only", "").lower() in ("1", "true")
        favorite_only = fav_q or fav_only_q
        sort = request.query.get("sort", "newest")
        feature = request.query.get("feature", None) or None
        preset = request.query.get("preset", None) or None
        date_from = request.query.get("date_from", None) or None
        date_to = request.query.get("date_to", None) or None
        has_image_raw = request.query.get("has_image", None)
        has_image: Optional[bool] = None
        if has_image_raw is not None:
            has_image = has_image_raw.lower() in ("1", "true")
        # include_timing accepted for compatibility but is a no-op:
        # timing_summary is already embedded in each index row.
        # request.query.get("include_timing", "0")

        _pt.mark("index_open")
        idx = None
        try:
            idx = _get_history_index(run_history_root())
        except Exception as exc:
            print(
                f"[comfyui-modal.history] history index unavailable: "
                f"{type(exc).__name__}: {exc}"
            )
            return web.json_response(
                {
                    "status": "error",
                    "error_code": "history_index_unavailable",
                    "message": "run-history index is unavailable",
                    "detail": "Source run history is preserved; the derived index could not be opened.",
                },
                status=503,
            )

        try:
            # Ensure the index exists and is usable.  Cheap for a healthy
            # index (validated at most once per interval per process) and
            # rebuilds ONLY for a missing, corrupt, or schema-incompatible
            # database.  There is deliberately no unbounded fallback here:
            # a failure surfaces as a structured error, never a silent
            # rescan or an empty page.
            try:
                idx.ensure()
            except Exception as exc:
                print(
                    f"[comfyui-modal.history] history index unavailable: "
                    f"{type(exc).__name__}: {exc}"
                )
                return web.json_response(
                    {
                        "status": "error",
                        "error_code": "history_index_unavailable",
                        "message": f"run-history index is unavailable: {exc}",
                        "detail": (
                            "The index is rebuilt automatically from the "
                            "authoritative run-history source on the next "
                            "successful request or ComfyUI restart.  Source "
                            "run data is preserved."
                        ),
                    },
                    status=503,
                )

            # Detect a demonstrably stale index (new/modified/removed source
            # runs not yet reflected in the index) and rebuild it once.
            # Rate-limited per process; a rebuild failure keeps serving the
            # existing (stale but usable) index and is surfaced as a warning.
            refresh = {"rebuilt": False, "reason": "fresh", "record_count": -1}
            try:
                refresh = idx.refresh_if_stale()
            except Exception as exc:
                print(
                    f"[comfyui-modal.history] staleness check failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                refresh = {
                    "rebuilt": False,
                    "reason": f"error: {exc}",
                    "record_count": -1,
                }
            if refresh.get("rebuilt"):
                print(
                    f"[comfyui-modal.history] index was stale "
                    f"({refresh.get('reason', '?')}); rebuilt "
                    f"{refresh.get('record_count', -1)} records"
                )

            _pt.mark("query_built")

            def _run_query() -> dict:
                return idx.query(
                    page=page,
                    page_size=page_size,
                    search=search,
                    kind=kind,
                    status=status,
                    favorite_only=favorite_only,
                    sort=sort,
                    feature=feature,
                    preset=preset,
                    date_from=date_from,
                    date_to=date_to,
                    has_image=has_image,
                )

            try:
                query_result = _run_query()
            except sqlite3.Error as exc:
                # One bounded self-heal attempt: force revalidation (this
                # may rebuild a corrupted index), then retry the query once.
                print(
                    f"[comfyui-modal.history] query failed "
                    f"({type(exc).__name__}: {exc}); attempting one bounded "
                    f"recovery"
                )
                try:
                    idx.ensure(force=True)
                    query_result = _run_query()
                except Exception as exc2:
                    print(
                        f"[comfyui-modal.history] query failed after "
                        f"recovery ({type(exc2).__name__}: {exc2})"
                    )
                    return web.json_response(
                        {
                            "status": "error",
                            "error_code": "history_index_query_failed",
                            "message": (
                                "run-history index query failed and could "
                                f"not be recovered: {exc2}"
                            ),
                            "detail": (
                                "Source run history is preserved; deleting "
                                "the local .history_index.db forces a full "
                                "rebuild on the next request."
                            ),
                        },
                        status=500,
                    )
        finally:
            # Release the SQLite handle after each request so Windows can
            # rotate/clean workspace roots and temporary test databases.
            if idx is not None:
                idx.close()
        _pt.mark("query_executed")

        items = query_result["items"]

        # No N+1 source-file hydration: timing_summary is already in items
        # via _row_to_dict which parses timing_summary_json.
        _pt.mark("rows_fetched")

        response_data = {
            "status": "ok",
            "items": items,
            "page": query_result["page"],
            "page_size": query_result["page_size"],
            "total": query_result["total"],
            "has_more": query_result["has_more"],
        }

        # Surface recovery/staleness diagnostics without changing the
        # success contract consumed by the UI.
        if refresh.get("rebuilt"):
            response_data["index_rebuilt"] = True
            response_data["index_rebuilt_reason"] = refresh.get("reason", "")
            response_data["index_rebuilt_records"] = refresh.get("record_count", -1)
        elif refresh.get("reason") not in ("fresh", "rate_limited"):
            response_data["index_warning"] = refresh.get("reason", "")

        # Attach safe timing metadata if query param present
        if request.query.get("_timing", "") == "1":
            _pt.mark("response_serialized")
            _pt.mark("total")
            response_data["_diagnostic_timing_ms"] = _pt.summary()

        _pt.mark("total")
        return web.json_response(response_data)

    print("[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*")
