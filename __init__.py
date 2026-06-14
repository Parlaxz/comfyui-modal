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
import subprocess
import time
from collections import namedtuple
from pathlib import Path
import traceback as _traceback

_NODE_DIR = os.path.dirname(os.path.abspath(__file__))
if _NODE_DIR not in sys.path:
    sys.path.insert(0, _NODE_DIR)

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
from timing_trace import Trace, TraceV4, coerce_t0_from_browser
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
    T2_LOCAL_MODAL_SUBMIT_START, T2A_MODAL_CALL_CONSTRUCTED,
    T2B_MODAL_CALL_STREAM_OPEN, T2C_FIRST_REMOTE_EVENT_RECEIVED,
    T2D_LOCAL_PROMPT_ACK_RETURNED,
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
)
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
)

import model_manifest as _model_manifest
import modal_workspaces as _workspace_store

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "web"


def _unique_path(directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(filename)
    suffix = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1_000_000) % 1_000_000:06d}"
    return os.path.join(directory, f"{stem}_{suffix}{ext}")

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
        "byte_count": len(decoded_bytes),
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

    def _store_entry(node_id: str, output_key: str, entry: dict, fallback_index: int = 0) -> None:
        nonlocal image_count, video_count, output_bytes_written
        raw_bytes = base64.b64decode(entry["data"])
        local_filename = entry.get("filename", f"output_{fallback_index}.bin")
        local_path = _unique_path(output_dir, local_filename)
        local_filename = os.path.basename(local_path)
        with open(local_path, "wb") as f:
            f.write(raw_bytes)
        written_files.append(local_path)
        output_bytes_written += len(raw_bytes)
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
            decoded_bytes=raw_bytes,
            fallback_index=fallback_index,
        )
        native_outputs.setdefault(str(node_id), {}).setdefault(output_key, []).append(native_entry)
        materialized_outputs.setdefault(str(node_id), {}).setdefault(output_key, []).append(internal_entry)
        if is_video:
            native_outputs[str(node_id)]["animated"] = [True] * len(native_outputs[str(node_id)][output_key])
            materialized_outputs[str(node_id)]["animated"] = [True] * len(materialized_outputs[str(node_id)][output_key])
        handled_output_ids.add(_stable_output_identity(str(node_id), output_key, entry, fallback_index))
        primary_flag = 1 if entry.get("comparison_side") == "b" or output_key == "b_images" else 0
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
                if isinstance(entry, dict) and "data" in entry:
                    _store_entry(str(node_id), str(output_key), entry, index)

    flat_node_events: dict[str, dict[str, list]] = {}
    for index, img in enumerate(result.get("images", []) if isinstance(result, dict) else []):
        if not isinstance(img, dict) or "data" not in img:
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
        if not isinstance(vid, dict) or "data" not in vid:
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

    if auto_save_local and primary_output and primary_output.get("path"):
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
    }

_CUSTOM_NODE_SYNC_EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
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
    print("[comfyui-modal] 'modal' package not found — installing...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "modal"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("[comfyui-modal] 'modal' installed successfully.")
    except subprocess.CalledProcessError as e:
        _pip_install_error = e.stderr or str(e)
        print(f"[comfyui-modal] ERROR: Failed to install 'modal' package: {e.stderr}")
        print("[comfyui-modal] Please install manually: pip install modal")
    except Exception as e:
        _pip_install_error = str(e)
        print(f"[comfyui-modal] ERROR: Unexpected error installing 'modal': {e}")
        print("[comfyui-modal] Please install manually: pip install modal")

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
        if node_dir.startswith(".") or node_dir in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
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
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


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


def _run_deploy_background(workspace: dict, custom_nodes_fingerprint: str | None = None):
    global _deploy_status

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
            _deploy_status = {"state": "ready", "message": f"Deployed {workspace['label']} v{version}"}
            print(f"[comfyui-modal] Deploy succeeded ({workspace['label']} v{version})")
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
    if os.environ.get("COMFYMODAL_RUNTIME") == "1":
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
    from modal_client import run_prompt, run_prompt_stream, get_object_info, health_check, download_model, download_model_stream, batch_download_models, list_models, delete_model, set_gpu, get_gpu, get_default_gpu, get_available_gpus, sync_custom_nodes, refresh_custom_nodes, get_sync_status, upload_model_to_volume, upload_model_chunk, clear_cache, resync_runtime, get_runtime_state, set_active_warmup_profile, set_workspace_resolver, get_handle_cache_stats, get_modal_app_name, get_modal_class_name, get_modal_lookup_target

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
    def get_default_gpu(): return "rtx-pro-6000"
    def get_available_gpus(): return [{"value": "rtx-pro-6000", "label": "RTX PRO 6000"}]
    def get_handle_cache_stats(): return {"hits": 0, "misses": 0}
    def set_gpu(gpu): pass
    def get_gpu(): return "rtx-pro-6000"
    def get_modal_app_name(): return "comfyui"
    def get_modal_class_name(gpu=None): return ""
    def get_modal_lookup_target(gpu=None, method_name="run_prompt"): return "unknown"

_COMFYUI_ROOT = os.path.dirname(os.path.dirname(_NODE_DIR))

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
    with open(_HF_TOKEN_PATH, "w") as f:
        f.write(token.strip())

def _read_civitai_token() -> str:
    try:
        with open(_CIVITAI_TOKEN_PATH, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def _write_civitai_token(token: str):
    with open(_CIVITAI_TOKEN_PATH, "w") as f:
        f.write(token.strip())

def _is_modal_token_set() -> bool:
    if _active_workspace() is not None:
        return True
    try:
        with open(_MODAL_TOML_PATH, "r") as f:
            content = f.read()
        return "token_id" in content and "token_secret" in content
    except FileNotFoundError:
        return False

def _write_modal_toml(token_id: str, token_secret: str):
    content = f'[default]\ntoken_id = "{token_id}"\ntoken_secret = "{token_secret}"\n'
    os.makedirs(os.path.dirname(_MODAL_TOML_PATH), exist_ok=True)
    with open(_MODAL_TOML_PATH, "w") as f:
        f.write(content)


_queue: asyncio.Queue = asyncio.Queue()
_queue_worker_started = False
_item_counter = 0
_counter_lock = asyncio.Lock()


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


async def _process_queue():
    while True:
        item, item_id = await _queue.get()
        try:
            await _execute_job(item, item_id)
        except asyncio.CancelledError:
            _queue.task_done()
            raise
        except Exception:
            import traceback
            traceback.print_exc()
            print("[comfyui-modal] Queue worker survived job exception, continuing")
        finally:
            _queue.task_done()


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

_last_written_stable_profile_key: str | None = None


def _compute_stable_warmup_profile_key(warmup_profile: dict, model_stack: dict) -> str:
    """Return a canonical stable key from only restore-relevant stacks.
    
    This excludes UUIDs, timestamps, workflow_hash, output nodes, and
    Production-mode settings so identical model stacks always produce
    the same key regardless of workflow display state.
    """
    stable = {
        "mode": warmup_profile.get("mode", ""),
    }
    if stable["mode"] == "checkpoint":
        stable["checkpoint"] = warmup_profile.get("checkpoint", "")
    elif stable["mode"] == "split":
        stack = dict(model_stack or {})
        stable["unet"] = stack.get("unet", "")
        stable["vae"] = stack.get("vae", "")
        stable["clip1"] = stack.get("clip1", "")
        stable["clip2"] = stack.get("clip2", "")
        stable["clip_type"] = stack.get("clip_type", "")
    stable["disable_warmup"] = warmup_profile.get("disable_warmup", False)
    # Sort keys for deterministic JSON
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _build_next_warmup_activation(workflow: dict, workflow_hash: str) -> dict:
    stack = extract_warmup_stack(workflow) if isinstance(workflow, dict) else {}
    profile = stack_to_warmup_profile(stack)
    now = time.time()
    return {
        "profile_token": str(uuid.uuid4()),
        "validation_token": str(uuid.uuid4()),
        "workflow_hash": workflow_hash,
        "created_at": now,
        "expires_at": now + _ACTIVE_NEXT_PROFILE_TTL_S,
        "mode": profile.get("mode", "none") if profile else "none",
        "model_stack": stack,
        "warmup_profile": profile,
        "disable_warmup": not bool(profile),
        "selected_at": None,
        "preflight_validated": True,
    }


async def _execute_job(item: tuple, item_id: int):
    global _last_written_stable_profile_key
    number, prompt_id, workflow, extra_data, _, _ = item
    execution_workflow = extra_data.get("execution_workflow") or workflow
    sid = extra_data.get("client_id", "")
    local_started = time.time()
    trace_payload = extra_data.get("trace", {}) if isinstance(extra_data, dict) else {}
    trace = Trace(prompt_id=prompt_id, t0=coerce_t0_from_browser(trace_payload) or local_started)
    trace.update(trace_payload)
    trace.mark("client_generate_clicked_or_request_start", trace.get("t0_client_press") or local_started)

    task_key = _register_running(item)

    _send(sid, "execution_start", {"prompt_id": prompt_id})
    _send(sid, "execution_cached", {"nodes": [], "prompt_id": prompt_id})

    success = False
    finalized = False
    outputs = {}
    prompt_hash = extra_data.get("workflow_hash", "")
    prompt_summary = extra_data.get("prompt_summary", {})
    model_stack = extra_data.get("model_stack", {})
    try:
        _send(sid, "modal_status", {"prompt_id": prompt_id, "message": "Starting up", "phase": "startup"})
        # Verify workflow integrity immediately before remote call
        current_hash = prompt_sha256(execution_workflow)
        expected_hash = extra_data.get("workflow_hash", "")
        if expected_hash and current_hash != expected_hash:
            raise RuntimeError(
                f"Workflow hash mismatch: expected {expected_hash[:12]}…, got {current_hash[:12]}…"
            )

        # API prompt structure validation (local defense-in-depth)
        assert_valid_api_prompt_structure(execution_workflow)

        # ── PART 2: Class-type validation before warmup profile write ──
        # Also validate that referenced node class types exist in the
        # local ComfyUI registry.  Missing nodes should fail fast rather
        # than wasting Modal worker time.
        try:
            import nodes as _validate_nodes
            _requested_types = set()
            for _spec in execution_workflow.values():
                if isinstance(_spec, dict):
                    _ct = _spec.get("class_type")
                    if isinstance(_ct, str) and _ct:
                        _requested_types.add(_ct)
            _missing = sorted(
                ct for ct in _requested_types
                if ct not in _validate_nodes.NODE_CLASS_MAPPINGS
            )
            if _missing:
                raise RuntimeError(
                    f"Missing custom node class(es): {_missing}. "
                    f"Install the missing custom nodes or fix the workflow."
                )
        except RuntimeError:
            raise
        except Exception as _val_exc:
            print(f"[comfyui-modal] Warning: class-type validation failed: {_val_exc}")

        # Log prompt metadata before remote execution
        print(f"[comfyui-modal] Running prompt {prompt_hash[:12]}… summary={prompt_summary} model_stack={model_stack}")

        collect_started = time.time()
        collect_started = time.time()
        input_collect_ms = 0
        input_collect_bytes = 0
        if workflow_needs_local_input_files(execution_workflow):
            input_images = _collect_input_images(execution_workflow)
            input_collect_ms = round((time.time() - collect_started) * 1000, 1)
            input_collect_bytes = sum(len(base64.b64decode(data)) for data in input_images.values())
            print(
                f"[comfyui-modal.profile] stage=input_collect prompt_id={prompt_id[:8]} "
                f"duration_ms={input_collect_ms} count={len(input_images)} bytes={input_collect_bytes}"
            )
        else:
            input_images = {}

        invocation_plan = _build_generation_invocation_plan(extra_data.get("gpu"), stream=True)
        _log_generation_invocation_plan(prompt_id, invocation_plan)

        # ── Active-next warmup profile (compact, skip if unchanged) ──
        _active_next_write_start = time.time()
        _active_next_payload_bytes = 0
        _active_next_status = "skipped"
        _active_next_changed = False
        _active_next_remote_call = 0
        if not os.environ.get("DISABLE_ACTIVE_NEXT_WRITE"):
            activation_payload = _build_next_warmup_activation(execution_workflow, prompt_hash)
            _active_next_payload_bytes = len(json.dumps(activation_payload, separators=(",", ":")))
            # Compute stable profile key from only restore-relevant fields
            _warmup_profile = activation_payload.get("warmup_profile", {})
            _model_stack = activation_payload.get("model_stack", {})
            _stable_key = _compute_stable_warmup_profile_key(_warmup_profile, _model_stack)
            if _last_written_stable_profile_key == _stable_key:
                _active_next_status = "unchanged"
                print(
                    f"[comfyui-modal.profile] stage=active_profile_write prompt_id={prompt_id[:8]} "
                    f"decision=unchanged profile_key={_stable_key[:12]} remote_call=0"
                )
            else:
                _active_next_remote_call = 1
                try:
                    activation_result = await set_active_warmup_profile(activation_payload)
                    _active_next_status = activation_result.get("status", "written")
                    _active_next_changed = activation_result.get("changed", True)
                    if _active_next_status not in ("error",):
                        _last_written_stable_profile_key = _stable_key
                    print(
                        f"[comfyui-modal.profile] stage=active_profile_write prompt_id={prompt_id[:8]} "
                        f"decision=changed profile_key={_stable_key[:12]} remote_call=1 "
                        f"status={_active_next_status} changed={_active_next_changed} bytes={_active_next_payload_bytes}"
                    )
                except Exception as exc:
                    _active_next_status = "error"
                    print(f"[comfyui-modal] active profile write failed: {exc}")
        else:
            print(f"[comfyui-modal] active_next_write SKIPPED (DISABLE_ACTIVE_NEXT_WRITE=1)")

        remote_started = time.time()
        trace.mark("t2_local_dispatch")
        trace.mark("t2b_modal_handle_resolved")
        trace.mark("t2c_modal_call_start")
        trace.mark("client_modal_call_start", trace.get("t2c_modal_call_start") or remote_started)
        trace.mark("client_modal_submit_done", trace.get("t2c_modal_call_start") or remote_started)
        if os.environ.get("COMFYMODAL_PREDISPATCH_DEBUG"):
            print(f"[predispatch] phase=before_gpu_spawn t={time.time()}")
        # Stream prompt execution with real-time progress from the Modal
        # container.  Progress events (executing, progress, execution_start)
        # are forwarded to the ComfyUI frontend as they arrive.
        _modal_result = None
        _first_msg = True
        _result_route_mode = extra_data.get("result_route", _RESULT_ROUTE)
        _mo = dict(extra_data.get("modal_options") or {})
        # Propagate runtime restore_background_unet flag to volume file
        # so the next container cold start can read it during restore().
        # Only active when EXPERIMENTAL_RESTORE_BACKGROUND_CODE is on.
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
        async for _msg in run_prompt_stream(
            execution_workflow,
            input_images,
            trace={**trace.fields(), "prompt_id": prompt_id},
            gpu=extra_data.get("gpu"),
            modal_options=_mo if _mo else None,
        ):
            if _first_msg:
                _first_msg = False
                trace.mark("client_first_remote_log_seen")
                if os.environ.get("COMFYMODAL_PREDISPATCH_DEBUG"):
                    print(f"[predispatch] phase=first_gpu_response t={time.time()}")
            if not isinstance(_msg, dict):
                continue
            if _msg["type"] == "progress":
                _evt = _msg["event"]
                if not isinstance(_msg.get("data"), dict):
                    continue
                _data = dict(_msg["data"])
                # Remote execution uses its own internal prompt_id, but the
                # local ComfyUI frontend is tracking the local prompt_id.
                # Rewrite streamed events so the frontend associates them with
                # the active local prompt and updates aggregate UI correctly.
                _data["prompt_id"] = prompt_id
                _send(sid, _evt, _data)
                await asyncio.sleep(0)
            elif _msg["type"] == "status":
                _send(sid, "modal_status", {
                    "prompt_id": prompt_id,
                    "message": _msg.get("message") or "Starting up",
                    "phase": _msg.get("phase") or "startup",
                })
                await asyncio.sleep(0)
            elif _msg["type"] == "result":
                _modal_result = _msg["data"]
                break
            elif _msg["type"] == "error":
                raise RuntimeError(_msg["message"])
        if _modal_result is None:
            raise RuntimeError("run_prompt_stream ended without result")
        result = _modal_result
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
    except asyncio.CancelledError:
        total_ms = round((time.time() - local_started) * 1000, 1)
        print(
            f"[comfyui-modal.profile] stage=local_total prompt_id={prompt_id[:8]} "
            f"duration_ms={total_ms} error=cancelled"
        )
        _send(sid, "execution_error", {"message": "cancelled", "prompt_id": prompt_id})
        _finish_job(task_key, prompt_id, outputs, success=False, meta={"error": "cancelled"})
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
        return

    # Update last successful model stack after successful remote result
    global _last_successful_model_stack
    _last_successful_model_stack.clear()
    _last_successful_model_stack.update(extra_data.get("model_stack", {}))

    # ── Post-materialization block: guarded so _finish_job always runs ──

    output_dir = os.path.join(_COMFYUI_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    trace.mark("t9e_local_materialize_start")
    materialize_started = time.time()
    trace.mark("client_result_decode_start", materialize_started)
    trace.mark("client_file_write_start", materialize_started)
    trace.mark("client_comfy_notify_start", materialize_started)
    _mo = extra_data.get("modal_options") if isinstance(extra_data, dict) else None
    _settings = _load_modal_settings()
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
    outputs.clear()
    outputs.update(delivery.get("history_outputs", delivery["outputs"]))
    output_bytes_written = delivery["bytes_written"]
    output_image_count = delivery["image_count"]
    output_video_count = delivery["video_count"]
    materialize_ms = round((time.time() - materialize_started) * 1000, 1)
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
    # Preserve restore timing from the Modal container's trace
    _remote_full = result.get("trace", {})
    if isinstance(_remote_full, dict):
        if "restore" in _remote_full:
            _merged_trace["restore"] = _remote_full["restore"]
        # Preserve dependency validation fields from remote trace
        for _dep_field in (
            "dependency_validation_ms", "dependency_total_ms",
            "dependency_validation_result", "dependency_validation_cache_layer",
            "dependency_validation_cache_hit", "dependency_validation_reason",
            "dependency_validation_baked_hash", "dependency_validation_current_hash",
            "dependency_validation_changed_nodes",
            "dependency_pre_key_check_ms", "dependency_baked_manifest_load_ms",
            "dependency_source_root_resolve_ms", "dependency_fingerprint_ms",
            "dependency_cache_key_ms", "dependency_memory_lookup_ms",
            "dependency_sentinel_lookup_ms", "dependency_full_validation_ms",
            "dependency_sentinel_write_ms",
        ):
            _dep_v = _remote_full.get(_dep_field)
            if _dep_v is not None:
                _merged_trace[_dep_field] = _dep_v
        # Also preserve from derived_ms
        _remote_derived = _remote_full.get("derived_ms", {})
        if isinstance(_remote_derived, dict):
            for _rdk, _rdv in _remote_derived.items():
                if _rdk not in _merged_trace.get("derived_ms", {}):
                    _merged_trace.setdefault("derived_ms", {})[_rdk] = _rdv
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

    trace.mark("t10d_local_response_sent")
    trace.mark("client_comfy_notify_start")
    trace.mark("client_comfy_notify_done")
    try:
        _send(sid, "executing", {"node": None, "display_node": None, "prompt_id": prompt_id})
        _send(sid, "modal_status", {"prompt_id": prompt_id, "message": None, "phase": "done"})
        _send(sid, "execution_success", {"prompt_id": prompt_id, "trace": result.get("trace")})
        _meta = {
            "model_stack": model_stack,
            "prompt_summary": prompt_summary,
            "trace": result.get("trace"),
            "workflow_hash": prompt_hash,
            "restore_timing": result.get("_restore_timing", {}),
            "scheduler_trace": result.get("scheduler_trace"),
            "primary_output": result.get("primary_output") or result.get("_local_primary_output"),
        }
        _finish_job(task_key, prompt_id, outputs, success=True, meta=_meta)
        finalized = True
    except Exception:
        import traceback
        traceback.print_exc()
        if not finalized and task_key != 0:
            try:
                _finish_job(task_key, prompt_id, outputs, success=False,
                          meta={"error": "completion notification exception"})
            except Exception as _fe:
                print(f"[comfyui-modal] _finish_job failed during error recovery: {_fe}")
        raise

    # ── Direct route: store completed result for non-polling retrieval ──
    if _result_route_mode == "direct" and isinstance(result, dict):
        with _COMPLETED_RESULTS_LOCK:
            _COMPLETED_RESULTS[prompt_id] = {
                "result": result,
                "trace": result.get("trace", {}),
                "outputs": outputs,
                "primary_output": result.get("primary_output") or result.get("_local_primary_output"),
                "materialize_ms": materialize_ms,
                "completed_at": time.time(),
                "direct_route": True,
            }

    total_ms = round((time.time() - local_started) * 1000, 1)
    print(
        f"[comfyui-modal.profile] stage=local_total prompt_id={prompt_id[:8]} "
        f"duration_ms={total_ms} images={output_image_count} videos={output_video_count} bytes={output_bytes_written}"
    )


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
    try:
        remote = await get_sync_status(workspace=workspace)
        remote_models = remote.get("models", [])
    except Exception:
        remote_models = []
    plan = _model_manifest.build_workspace_swap_plan(manifest, remote_models)
    return {
        "manifest_issues": issues,
        "blocking_issues": blocking,
        "already_present": plan.get("already_present", []),
        "to_install": plan.get("to_install", []),
        "unresolved": plan.get("unresolved", []),
        "to_remove": plan.get("to_remove", []),
    }


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
        total_ms = round(total * 1000, 2) if isinstance(total, float) else local_ts.get("local_recv_to_dispatch_ms", 0)
        if total_ms > 60000:
            degradation_flags.append("local_predispatch_stall_severe")
            print(f"[local_predispatch_stall] SEVERE request_id={request_id} total_ms={total_ms} dominant={dominant}={dominant_ms} body_read={body_read} json_parse={json_parse} stack_extract={stack_extract} active_next={active_next} lock_wait={lock_wait}")
        elif total_ms > 30000:
            degradation_flags.append("local_predispatch_stall")
            print(f"[local_predispatch_stall] CRITICAL request_id={request_id} total_ms={total_ms} dominant={dominant}={dominant_ms} body_read={body_read} json_parse={json_parse} stack_extract={stack_extract} active_next={active_next} lock_wait={lock_wait}")
        elif total_ms > 5000:
            print(f"[local_predispatch_stall] request_id={request_id} total_ms={total_ms} dominant={dominant}={dominant_ms} body_read={body_read} json_parse={json_parse} stack_extract={stack_extract} active_next={active_next} lock_wait={lock_wait}")
        return {"local_recv_to_dispatch_ms": total_ms, "dominant_phase": dominant, "dominant_ms": dominant_ms, "body_read_ms": body_read, "json_parse_ms": json_parse, "stack_extract_ms": stack_extract, "active_next_write_ms": active_next, "lock_wait_total_ms": lock_wait}

    @_server.routes.post("/comfymodal/prompt")
    async def modal_prompt(request: web.Request) -> web.Response:
        global _queue_worker_started, _item_counter

        # ── v4 local event trace ──
        local_et = _init_local_event_trace()
        local_et.mark(T0_CLIENT_PRESS, phase=PHASE_LOCAL_PRE)
        local_et.mark(T1_LOCAL_BRIDGE_RECEIVED, phase=PHASE_LOCAL_BRIDGE)
        _route_entry_ts = time.time()

        # ── Phase: body read + JSON parse ──
        local_et.mark(T1G_BODY_READ_START, phase=PHASE_LOCAL_BRIDGE)
        try:
            body = await asyncio.wait_for(request.json(), timeout=_BODY_READ_TIMEOUT_S)
        except asyncio.TimeoutError:
            print(f"[comfyui-modal] BODY READ TIMEOUT after {_BODY_READ_TIMEOUT_S}s")
            return web.json_response({"status": "error", "error": "Request body read timed out"}, status=408)
        local_et.mark(T1H_BODY_READ_END, phase=PHASE_LOCAL_BRIDGE)
        _body_read_done_ts = time.time()

        local_et.mark(T1I_JSON_PARSE_START, phase=PHASE_LOCAL_BRIDGE)
        _json_parse_done_ts = time.time()
        body_read_ms = round((_body_read_done_ts - _route_entry_ts) * 1000, 3)
        if body_read_ms > _JSON_PARSE_WARN_MS:
            print(f"[comfyui-modal] WARN slow body read: {body_read_ms}ms content_length={request.content_length if hasattr(request, 'content_length') else '?'}")
        if body_read_ms > _JSON_PARSE_FAIL_S * 1000:
            return web.json_response({"status": "error", "error": f"JSON read/parse took {body_read_ms}ms, exceeding limit"}, status=413)
        body_bytes = len(json.dumps(body).encode('utf-8'))
        if body_bytes > 10 * 1024 * 1024:
            print(f"[comfyui-modal] WARN large body: {body_bytes} bytes")
        local_et.mark(T1J_JSON_PARSE_END, phase=PHASE_LOCAL_BRIDGE)

        # ── Extract payload fields and inject detailed trace stages ──
        workflow = body.get("prompt", body)
        client_id = body.get("client_id", str(uuid.uuid4()))
        prompt_id = str(uuid.uuid4())
        request_state = _make_local_request_state(request, body, prompt_id)
        # Prefer request-level trace (body["trace"]["t0_client_press"]) over top-level
        request_trace = body.get("trace", {})
        browser_t0 = coerce_t0_from_browser(request_trace) or coerce_t0_from_browser(body)
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

        # ── Preflight validation ──
        local_et.mark(T1C_LOCAL_PREFLIGHT_START, phase=PHASE_LOCAL_BRIDGE)
        _preflight_start_ts = time.perf_counter()
        validation_errors = validate_api_prompt_structure(workflow)
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

        # ── Production workflow compilation ──
        modal_options_raw = body.get("modal_options", None)
        if not isinstance(modal_options_raw, dict):
            modal_options_raw = None
        production_options = normalize_production_options(modal_options_raw)
        production_report = None
        execution_workflow = workflow
        if production_options.get("enabled"):
            try:
                production_options["enabled"] = True
                if "schema_version" not in production_options:
                    production_options["schema_version"] = 1
                compiled, production_report = compile_production_workflow(
                    workflow, production_options, allow_direct_output_rewrite=False
                )
                execution_workflow = compiled
                kept = production_report.get("compiled_node_count", 0)
                removed = production_report.get("removed_node_count", 0)
                bypassed = len(production_options.get("bypass_node_ids", []))
                outputs = len(production_options.get("output_node_ids", []))
                print(
                    f"[comfyui-modal] Production plan: kept={kept} removed={removed} "
                    f"bypassed={bypassed} outputs={outputs}"
                )
            except Exception:
                print(f"[comfyui-modal] Production compile failed, failing closed")
                raise
        else:
            production_report = {"enabled": False}

        # ── Stack extraction (prompt hashing + model stack) ──
        print(f"[predispatch] phase=before_stack_extract t={time.time()}")
        trace.mark("t1k_stack_extract_start", time.time())
        local_et.mark(T1Q_STACK_EXTRACT_START, phase=PHASE_LOCAL_BRIDGE)
        _stack_start_ts = time.perf_counter()
        local_payload_hash = prompt_sha256(body)
        workflow_hash = prompt_sha256(execution_workflow)
        prompt_summary = summarize_prompt_fields(execution_workflow)
        model_stack = extract_model_stack(execution_workflow)
        _stack_end_ts = time.perf_counter()
        stack_extract_ms = round((_stack_end_ts - _stack_start_ts) * 1000, 3)
        if stack_extract_ms > _STACK_EXTRACT_WARN_MS:
            print(f"[comfyui-modal] CRITICAL slow stack extraction: {stack_extract_ms}ms")
        if stack_extract_ms > _STACK_EXTRACT_FAIL_S * 1000:
            _clear_request_state(prompt_id)
            return web.json_response({"status": "error", "error": f"Stack extraction took {stack_extract_ms}ms, exceeding {_STACK_EXTRACT_FAIL_S}s limit"}, status=500)
        _stack_end_ts_wall = time.time()
        trace.mark("t1l_stack_extract_end", _stack_end_ts_wall)
        local_et.mark(T1R_STACK_EXTRACT_END, phase=PHASE_LOCAL_BRIDGE)
        print(f"[predispatch] phase=after_stack_extract t={_stack_end_ts_wall}")

        # Extract modal_options from body
        modal_options = modal_options_raw
        scheduler_test = body.get("comfymodal_scheduler_test")

        # ── Lock + enqueue ──
        local_et.mark(T2_LOCAL_MODAL_SUBMIT_START, phase=PHASE_LOCAL_BRIDGE)

        _lock_trace = await _timed_async_lock_acquire(_counter_lock, "counter_lock", prompt_id)
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
                    T2_LOCAL_MODAL_SUBMIT_START: time.time_ns(),
                },
            }

            extra_data = {
                "client_id": client_id,
                "create_time": int(time.time() * 1000),
                "local_payload_hash": local_payload_hash,
                "workflow_hash": workflow_hash,
                "prompt_summary": prompt_summary,
                "model_stack": model_stack,
                "gpu": selected_gpu,
                "trace": {**trace.fields(), "prompt_id": prompt_id},
                "_client_trace": _client_trace_dict,
                "modal_options": modal_options,
                "scheduler_test": scheduler_test,
                "result_route": _result_route_mode,
                "execution_workflow": copy.deepcopy(execution_workflow),
                "production_report": production_report,
            }
            _queue_execution_workflow = copy.deepcopy(execution_workflow)
            item = (_item_counter, prompt_id, _queue_execution_workflow, extra_data, list(_queue_execution_workflow.keys()), {})
            print(f"[predispatch] prompt_bytes={body_bytes}")
        finally:
            if _lock_trace.get("acquired"):
                _counter_lock.release()

        pq = _pq()
        if pq:
            with pq.mutex:
                import heapq
                heapq.heappush(pq.queue, item)
                pq.server.queue_updated()

        await _queue.put((item, item_id))

        if not _queue_worker_started:
            _queue_worker_started = True
            asyncio.create_task(_process_queue())

        _dispatch_ts = time.time()
        local_recv_to_dispatch_ms = round((_dispatch_ts - _route_entry_ts) * 1000, 3)

        # ── Stall detector ──
        local_ts = {"t1_local_recv": _route_entry_ts, "t2_local_dispatch": _dispatch_ts,
                    "body_read_ms": body_read_ms, "json_parse_ms": body_read_ms, "preflight_ms": preflight_ms,
                    "stack_extract_ms": stack_extract_ms, "active_next_write_ms": 0,
                    "lock_wait_total_ms": _lock_trace.get("wait_ms", 0), "local_recv_to_dispatch_ms": local_recv_to_dispatch_ms}
        degradation_flags = []
        _detect_local_predispatch_stall(local_ts, prompt_id, degradation_flags)

        local_et.mark(T2D_LOCAL_PROMPT_ACK_RETURNED, phase=PHASE_LOCAL_BRIDGE)
        _clear_request_state(prompt_id)

        return web.json_response({
            "prompt_id": prompt_id,
            "number": _item_counter,
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
                asyncio.create_task(_run_workspace_swap_job(swap_id, workspace, plan))
                return web.json_response({"status": "started", "swap_id": swap_id, "workspace_label": workspace["label"]})

            scan = await _scan_swap_plan(workspace)
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

        return web.json_response(response_data)

    @_server.routes.post("/comfymodal/open-folder")
    async def modal_open_folder(request: web.Request) -> web.Response:
        import platform
        import subprocess as _sp
        body = await request.json()
        folder = (body.get("path") or body.get("folder") or "").strip()
        if not folder:
            return web.json_response({"status": "error", "message": "no path provided"}, status=400)
        # Resolve relative paths against ComfyUI root
        if not os.path.isabs(folder):
            folder = os.path.join(_COMFYUI_ROOT, folder)
        folder = os.path.normpath(folder)
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        try:
            _sys_name = platform.system()
            if _sys_name == "Windows":
                _sp.Popen(["explorer", folder], shell=True)
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
            entry = _COMPLETED_RESULTS.get(prompt_id)
            if entry is None:
                return web.json_response({"status": "pending", "message": "result not yet available"}, status=404)
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

    print("[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*")
