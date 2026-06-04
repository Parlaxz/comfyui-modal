import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import modal

from gpu_catalog import GPU_CATALOG, get_supported_gpus, is_gpu_hidden
from timing_trace import Trace, coerce_t0_from_browser

PROFILING_ENABLED = os.getenv("COMFYMODAL_PROFILING", "0") == "1"
DEFAULT_EXECUTION_BACKEND = os.getenv("COMFYMODAL_EXECUTION_BACKEND", "in_process")
ENABLE_WARMUP = os.getenv("COMFYMODAL_ENABLE_WARMUP", "1") == "1"
ENABLE_TORCH_COMPILE = os.getenv("COMFYMODAL_ENABLE_TORCH_COMPILE", "0") == "1"
ENABLE_GPU_SNAPSHOT = os.getenv("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"
WARMUP_PROFILE = os.getenv("COMFYMODAL_WARMUP_PROFILE", "off")
WARMUP_CHECKPOINT = os.getenv("COMFYMODAL_WARMUP_CHECKPOINT", "").strip()
WARMUP_UNET = os.getenv("COMFYMODAL_WARMUP_UNET", "").strip()
WARMUP_CLIP1 = os.getenv("COMFYMODAL_WARMUP_CLIP1", "").strip()
WARMUP_CLIP2 = os.getenv("COMFYMODAL_WARMUP_CLIP2", "").strip()
WARMUP_VAE = os.getenv("COMFYMODAL_WARMUP_VAE", "").strip()
WARMUP_CLIP_TYPE = os.getenv("COMFYMODAL_WARMUP_CLIP_TYPE", "flux").strip() or "flux"
WARMUP_TEXT = "A Jew steals baby kittens from their mother cat. the mother cat is anthropamorphic and wearing an apron and chef's hat and crying. The jew is a rabbi and is wearing a suit and holding the kittens. The jew has a long nose and an evil smile. They are in a crowded market, and the mother cat has her hands outstretched longinly in the direction of the jew and her babies. The jew is running away with his back to the mother and looking back at her. He is wearing a kippa and is a rabbi, and is laughing"

# Preload mode controls which model files are loaded to CPU during restore
# and the concurrency/ordering:
#   default      — UNET + CLIP concurrent, 4 workers
#   sequential   — UNET first then CLIP, 1 worker
#   unet_only    — UNET only
#   clip_only    — CLIP only
#   vae          — UNET + CLIP + VAE concurrent, 4 workers
#   workers_1    — UNET + CLIP concurrent, 1 worker
#   workers_2    — UNET + CLIP concurrent, 2 workers
PRELOAD_MODE = os.getenv("COMFYMODAL_PRELOAD_MODE", "workers_2").strip().lower()
PRELOAD_MODE_PATH = "/root/models/.preload_mode"
RUNTIME_CONFIG_DIR = "/root/models/runtime_config"
RUNTIME_WCE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "warmup_clip_encode.txt")
RUNTIME_RETURN_MODE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "return_mode.txt")
RUNTIME_CLIP_CACHE_CLEAR_PATH = os.path.join(RUNTIME_CONFIG_DIR, "clear_clip_encode_cache.txt")
RUNTIME_EXEC_PROFILE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "exec_profile.txt")
RUNTIME_SAMPLER_PROFILE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "sampler_profile.txt")
RUNTIME_GUIDER_PROFILE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "guider_profile.txt")
RUNTIME_DEEP_PROFILE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "deep_profile.txt")
RUNTIME_LMG_FASTPATH_DRYRUN_PATH = os.path.join(RUNTIME_CONFIG_DIR, "lmg_fastpath_dryrun.txt")
RUNTIME_LMG_FASTPATH_PATH = os.path.join(RUNTIME_CONFIG_DIR, "lmg_fastpath.txt")
RUNTIME_MODELPATCHER_CACHE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "modelpatcher_cache.txt")
RUNTIME_MODELPATCHER_CACHE_DRYRUN_PATH = os.path.join(RUNTIME_CONFIG_DIR, "modelpatcher_cache_dryrun.txt")


def _resolve_preload_mode() -> str:
    """Return the effective preload mode.

    Priority:
    1. File on the model volume (set by ``set_preload_mode``).
    2. Module-level env-var default (``PRELOAD_MODE``).
    """
    try:
        if os.path.isfile(PRELOAD_MODE_PATH):
            _v = open(PRELOAD_MODE_PATH).read().strip().lower()
            if _v:
                return _v
    except Exception:
        pass
    return PRELOAD_MODE


def _resolve_wce() -> tuple[bool, str]:
    """Return (enabled, source) for warmup CLIP encode.

    Priority:
    1. File on the model volume (set by ``set_warmup_clip_encode``).
    2. Env var ``COMFYMODAL_WARMUP_CLIP_ENCODE`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_WCE_PATH):
            _v = open(RUNTIME_WCE_PATH).read().strip().lower()
            if _v in ("1", "true", "on"):
                return True, "file"
            if _v in ("0", "false", "off"):
                return False, "file"
    except Exception:
        pass
    _env = os.environ.get("COMFYMODAL_WARMUP_CLIP_ENCODE", "1").strip().lower()
    return _env in ("1", "true", "on"), "env"


def _resolve_return_mode() -> str:
    """Return the effective return mode.

    Priority:
    1. File on the model volume (set by ``set_return_mode``).
    2. Env var ``COMFYMODAL_RETURN_MODE`` (default ``"full_base64"``).
    """
    try:
        if os.path.isfile(RUNTIME_RETURN_MODE_PATH):
            _v = open(RUNTIME_RETURN_MODE_PATH).read().strip().lower()
            if _v in ("full_base64", "first_image_only", "metadata_only", "paths_only", "urls_only"):
                return _v
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_RETURN_MODE", "full_base64").strip().lower()


def _resolve_exec_profile() -> bool:
    """Return whether executor profiling is enabled.

    Priority:
    1. File on the model volume (set by ``set_exec_profile``).
    2. Env var ``COMFYMODAL_EXEC_PROFILE`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_EXEC_PROFILE_PATH):
            _v = open(RUNTIME_EXEC_PROFILE_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_EXEC_PROFILE", "0").strip().lower() in ("1", "true", "on")


def _resolve_clip_cache_clear() -> bool:
    """Return True if CLIP encode cache should be cleared on restore.

    Priority:
    1. File on the model volume (set by ``set_clear_clip_encode_cache``).
    2. Env var ``COMFYMODAL_CLEAR_CLIP_ENCODE_CACHE`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_CLIP_CACHE_CLEAR_PATH):
            _v = open(RUNTIME_CLIP_CACHE_CLEAR_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_CLEAR_CLIP_ENCODE_CACHE", "0").strip().lower() in ("1", "true", "on")


def _resolve_sampler_profile() -> bool:
    """Return whether sampler internal profiling is enabled.

    Priority:
    1. File on the model volume (set by ``set_sampler_profile``).
    2. Env var ``COMFYMODAL_SAMPLER_PROFILE`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_SAMPLER_PROFILE_PATH):
            _v = open(RUNTIME_SAMPLER_PROFILE_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_SAMPLER_PROFILE", "0").strip().lower() in ("1", "true", "on")


def _resolve_guider_profile() -> bool:
    """Return whether guider overhead profiling is enabled.

    Priority:
    1. File on the model volume (set by ``set_guider_profile``).
    2. Env var ``COMFYMODAL_GUIDER_PROFILE`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_GUIDER_PROFILE_PATH):
            _v = open(RUNTIME_GUIDER_PROFILE_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_GUIDER_PROFILE", "0").strip().lower() in ("1", "true", "on")


def _resolve_deep_profile() -> bool:
    """Return whether deep sampler wrapper profiling is enabled.

    Priority:
    1. File on the model volume (set by ``set_deep_profile``).
    2. Env var ``COMFYMODAL_DEEP_PROFILE`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_DEEP_PROFILE_PATH):
            _v = open(RUNTIME_DEEP_PROFILE_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_DEEP_PROFILE", "0").strip().lower() in ("1", "true", "on")


def _resolve_lmg_fastpath_dryrun() -> bool:
    """Return whether LMG fast-path dry-run diagnostics are enabled.

    Priority:
    1. File on the model volume.
    2. Env var ``COMFYMODAL_LMG_FASTPATH_DRYRUN`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_LMG_FASTPATH_DRYRUN_PATH):
            _v = open(RUNTIME_LMG_FASTPATH_DRYRUN_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_LMG_FASTPATH_DRYRUN", "0").strip().lower() in ("1", "true", "on")


def _resolve_lmg_fastpath() -> bool:
    """Return whether LMG fast-path is enabled (active skip).

    Priority:
    1. File on the model volume.
    2. Env var ``COMFYMODAL_LMG_FASTPATH`` (default ``"0"``).
    """
    try:
        if os.path.isfile(RUNTIME_LMG_FASTPATH_PATH):
            _v = open(RUNTIME_LMG_FASTPATH_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_LMG_FASTPATH", "0").strip().lower() in ("1", "true", "on")


def _resolve_modelpatcher_cache() -> bool:
    """Return whether canonical ModelPatcher cache is enabled."""
    try:
        if os.path.isfile(RUNTIME_MODELPATCHER_CACHE_PATH):
            _v = open(RUNTIME_MODELPATCHER_CACHE_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_MODELPATCHER_CACHE", "0").strip().lower() in ("1", "true", "on")


def _resolve_modelpatcher_cache_dryrun() -> bool:
    """Return whether canonical ModelPatcher cache dry-run is enabled."""
    try:
        if os.path.isfile(RUNTIME_MODELPATCHER_CACHE_DRYRUN_PATH):
            _v = open(RUNTIME_MODELPATCHER_CACHE_DRYRUN_PATH).read().strip().lower()
            return _v in ("1", "true", "on")
    except Exception:
        pass
    return os.environ.get("COMFYMODAL_MODELPATCHER_CACHE_DRYRUN", "0").strip().lower() in ("1", "true", "on")


_EXCLUDED_CUSTOM_NODE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}

# ── Custom-node volume helpers ────────────────────────────────────────────
# These are intentionally duplicated (inlined) here rather than imported from
# `custom_node_sync.py` to keep Modal packaging simple.  Modal serialises the
# entire module closure; importing a sibling module would require an explicit
# `modal.Image` dependency or risk missing files at deploy time.  Keep these
# helpers in sync with `custom_node_sync.py` if changes are made there.

def _safe_listdir(path: str) -> list[str]:
    if not os.path.isdir(path):
        return []
    return sorted(os.listdir(path))


def _is_volume_managed_link(link_path: str, volume_root: str) -> bool:
    if not os.path.islink(link_path):
        return False
    target = os.path.realpath(link_path)
    try:
        common = os.path.commonpath([os.path.abspath(volume_root), os.path.abspath(target)])
    except ValueError:
        return False
    return common == os.path.abspath(volume_root)


def custom_node_volume_state(volume_root: str) -> tuple:
    volume_root = os.path.abspath(volume_root)
    state = []
    for name in _safe_listdir(volume_root):
        path = os.path.join(volume_root, name)
        if not os.path.isdir(path) or name in _EXCLUDED_CUSTOM_NODE_DIRS:
            continue
        stat = os.stat(path)
        req_file = os.path.join(path, "requirements.txt")
        req_mtime_ns = os.stat(req_file).st_mtime_ns if os.path.isfile(req_file) else None
        state.append((name, stat.st_mtime_ns, req_mtime_ns))
    return tuple(state)


def missing_expected_nodes(state: tuple, expected_nodes: list[str]) -> list[str]:
    visible = {name for name, *_ in state}
    return [name for name in expected_nodes if name not in visible]


def sync_custom_nodes_into_comfy(volume_root: str, comfy_custom_nodes_root: str) -> dict:
    volume_root = os.path.abspath(volume_root)
    comfy_custom_nodes_root = os.path.abspath(comfy_custom_nodes_root)
    os.makedirs(comfy_custom_nodes_root, exist_ok=True)

    volume_dirs = {
        name
        for name in _safe_listdir(volume_root)
        if os.path.isdir(os.path.join(volume_root, name)) and name not in _EXCLUDED_CUSTOM_NODE_DIRS
    }

    removed = []
    created = []
    kept = []
    blocked = []

    for name in _safe_listdir(comfy_custom_nodes_root):
        dst = os.path.join(comfy_custom_nodes_root, name)
        if not _is_volume_managed_link(dst, volume_root):
            continue
        expected_src = os.path.join(volume_root, name)
        if name not in volume_dirs or os.path.realpath(dst) != os.path.realpath(expected_src):
            os.unlink(dst)
            removed.append(name)

    for name in sorted(volume_dirs):
        src = os.path.join(volume_root, name)
        dst = os.path.join(comfy_custom_nodes_root, name)
        if os.path.islink(dst) and os.path.realpath(dst) == os.path.realpath(src):
            kept.append(name)
            continue
        if os.path.lexists(dst):
            blocked.append(name)
            continue
        os.symlink(src, dst)
        created.append(name)

    return {
        "created": created,
        "removed": removed,
        "kept": kept,
        "blocked": blocked,
    }

RUNTIME_METADATA_PATH = "/root/comfy/runtime_metadata.json"


def requirements_file_hash(path: str) -> str | None:
    """Return sha256 hex of a requirements.txt file, or None if missing."""
    if not os.path.isfile(path):
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_volume_state(volume_root: str) -> tuple:
    """Snapshot of (folder, name, mtime_ns, size) for every file on a model volume."""
    volume_root = os.path.abspath(volume_root)
    state = []
    for folder in _safe_listdir(volume_root):
        folder_path = os.path.join(volume_root, folder)
        if not os.path.isdir(folder_path):
            continue
        for name in _safe_listdir(folder_path):
            path = os.path.join(folder_path, name)
            if not os.path.isfile(path):
                continue
            try:
                st = os.stat(path)
            except (OSError, FileNotFoundError):
                continue
            state.append((folder, name, st.st_mtime_ns, st.st_size))
    return tuple(state)


def load_runtime_metadata() -> dict:
    """Load JSON metadata from the container filesystem."""
    if not os.path.isfile(RUNTIME_METADATA_PATH):
        return {"requirements": {}, "runtime": {}}
    try:
        with open(RUNTIME_METADATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"requirements": {}, "runtime": {}}
        return data
    except (json.JSONDecodeError, OSError):
        return {"requirements": {}, "runtime": {}}


def save_runtime_metadata(data: dict) -> None:
    """Persist JSON metadata to the container filesystem."""
    os.makedirs(os.path.dirname(RUNTIME_METADATA_PATH), exist_ok=True)
    with open(RUNTIME_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def set_manager_network_mode_offline() -> list[str]:
    """Force ComfyUI-Manager into offline mode for runtime containers."""
    config_paths = [
        "/root/comfy/ComfyUI/user/default/__manager/config.ini",
        "/root/comfy/ComfyUI/user/default/ComfyUI-Manager/config.ini",
    ]
    written = []
    for config_path in config_paths:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("[default]\nnetwork_mode = offline\n")
        written.append(config_path)
    return written


def _get_system_ram_gb() -> float:
    """Return total system RAM in GB by parsing /proc/meminfo.

    Falls back to 16 GB if the file cannot be read (e.g. non-Linux).
    """
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    val = kb / (1024 * 1024)
                    return round(val, 1)
    except Exception:
        pass
    return 16.0


def load_warmup_profile() -> dict:
    """Return the configured pinned warmup profile, if any.

    Prefers runtime-set env vars over module-level constants so that
    dynamically-set env vars (e.g. restore-time defaults) take effect.
    """
    _get = lambda k, dflt="": (os.environ.get(k) or dflt).strip()
    checkpoint = _get("COMFYMODAL_WARMUP_CHECKPOINT", WARMUP_CHECKPOINT)
    unet = _get("COMFYMODAL_WARMUP_UNET", WARMUP_UNET)
    clip1 = _get("COMFYMODAL_WARMUP_CLIP1", WARMUP_CLIP1)
    clip2 = _get("COMFYMODAL_WARMUP_CLIP2", WARMUP_CLIP2)
    vae = _get("COMFYMODAL_WARMUP_VAE", WARMUP_VAE)
    clip_type = _get("COMFYMODAL_WARMUP_CLIP_TYPE", WARMUP_CLIP_TYPE) or "flux"
    if checkpoint:
        return {
            "mode": "checkpoint",
            "checkpoint": checkpoint,
        }
    if unet and clip1 and clip2 and vae:
        c1, c2 = normalize_flux_clip_pair(clip1, clip2) if clip_type == "flux" else (clip1, clip2)
        return {
            "mode": "split",
            "unet": unet,
            "clip1": c1,
            "clip2": c2,
            "vae": vae,
            "clip_type": clip_type,
        }
    return {}


def extract_requested_model_stack(workflow: dict) -> dict:
    """Extract a minimal model stack from a workflow for warmup matching."""
    stack: dict = {"checkpoint": [], "unet": [], "clip": [], "vae": [], "clip_type": "flux"}
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if class_type in {"CheckpointLoaderSimple", "CheckpointLoader"}:
            value = inputs.get("ckpt_name")
            if isinstance(value, str) and value and value not in stack["checkpoint"]:
                stack["checkpoint"].append(value)
        elif class_type == "UNETLoader":
            value = inputs.get("unet_name")
            if isinstance(value, str) and value and value not in stack["unet"]:
                stack["unet"].append(value)
        elif class_type == "DualCLIPLoader":
            for key in ("clip_name1", "clip_name2"):
                value = inputs.get(key)
                if isinstance(value, str) and value and value not in stack["clip"]:
                    stack["clip"].append(value)
            # Capture clip_type from the actual workflow loader node
            _ct = inputs.get("type", "")
            if isinstance(_ct, str) and _ct:
                stack["clip_type"] = _ct
        elif class_type == "CLIPLoader":
            value = inputs.get("clip_name")
            if isinstance(value, str) and value and value not in stack["clip"]:
                stack["clip"].append(value)
            _ct = inputs.get("type", "")
            if isinstance(_ct, str) and _ct:
                stack["clip_type"] = _ct
        elif class_type == "VAELoader":
            value = inputs.get("vae_name")
            if isinstance(value, str) and value and value not in stack["vae"]:
                stack["vae"].append(value)
    return stack


def warmup_profile_matches_workflow(profile: dict, requested: dict) -> bool:
    """Return True when the requested workflow matches the pinned warmup profile."""
    if not profile:
        return True
    mode = profile.get("mode")
    if mode == "checkpoint":
        checkpoint = profile.get("checkpoint", "")
        return bool(checkpoint) and checkpoint in requested.get("checkpoint", [])
    if mode == "split":
        return (
            profile.get("unet", "") in requested.get("unet", [])
            and profile.get("clip1", "") in requested.get("clip", [])
            and profile.get("clip2", "") in requested.get("clip", [])
            and profile.get("vae", "") in requested.get("vae", [])
        )
    return False


def normalize_flux_clip_pair(clip1: str, clip2: str) -> tuple[str, str]:
    """Return ComfyUI's expected FLUX DualCLIPLoader order: clip-l, then T5.

    Current ComfyUI documents DualCLIPLoader ``type='flux'`` as
    ``clip-l, t5``.  Keep already-correct pairs unchanged, but fix common
    reversed env/profile ordering.
    """
    a = clip1.lower()
    b = clip2.lower()
    a_is_t5 = "t5" in a
    b_is_clip_l = "clip_l" in b or "clip-l" in b or "clip-vit" in b
    if a_is_t5 and b_is_clip_l:
        return clip2, clip1
    return clip1, clip2


def list_sageattention_extension_files(site_packages_root: str) -> list[Path]:
    root = Path(site_packages_root) / "sageattention"
    if not root.is_dir():
        return []
    return sorted(root.glob("*.so"))


def choose_sage_runtime_mode(enabled: bool, extension_files: list[Path], import_ok: bool, smoke_ok: bool) -> tuple[str, str]:
    if not enabled:
        return "disabled", "explicitly-disabled"
    if not extension_files:
        return "triton_fallback", "compiled-extensions-missing"
    if not import_ok:
        return "triton_fallback", "compiled-extensions-unusable"
    if not smoke_ok:
        return "triton_fallback", "smoke-test-failed"
    return "baked_cuda", "compiled-extensions-usable"


def patch_kjnodes_get_sage_func(module, baked_cuda_available: bool) -> bool:
    original = getattr(module, "get_sage_func", None)
    fallback = getattr(module, "attention_pytorch", None)
    wrap_attn_fn = getattr(module, "wrap_attn", None)
    if original is None or fallback is None or wrap_attn_fn is None:
        return False

    module._comfy_modal_baked_cuda_available = baked_cuda_available
    if getattr(module, "_comfy_modal_get_sage_func_patched", False):
        return True

    def wrapped_get_sage_func(sage_attention, allow_compile=False):
        if getattr(module, "_comfy_modal_baked_cuda_available", False) or sage_attention == "disabled":
            return original(sage_attention, allow_compile=allow_compile)
        if sage_attention != "auto" and "sageattn" not in str(sage_attention):
            return original(sage_attention, allow_compile=allow_compile)

        @wrap_attn_fn
        def attention_fallback(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False, skip_output_reshape=False, **kwargs):
            return fallback(
                q,
                k,
                v,
                heads,
                mask=mask,
                attn_precision=attn_precision,
                skip_reshape=skip_reshape,
                skip_output_reshape=skip_output_reshape,
                **kwargs,
            )

        return attention_fallback

    module.get_sage_func = wrapped_get_sage_func
    module._comfy_modal_get_sage_func_patched = True
    return True


def build_replay_warmup_workflow(workflow: dict) -> dict:
    """Create a lightweight warmup from a real successful workflow.

    This preserves the exact loader nodes, clip order/type, UNET dtype, model
    sampling nodes, custom options, and graph topology that already worked for
    the user.  Only generation cost is reduced: samplers run one step and
    generated latent sizes are capped to 512x512.
    """
    import copy

    def is_numeric(value) -> bool:
        return isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit())

    warmup = copy.deepcopy(workflow)
    for node in warmup.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue

        # Reduce common sampler fields across built-in and custom samplers.
        # The previous exact-class check missed custom Flux samplers, causing
        # restore warmup to run full 20/30-step generations.
        for key in ("steps", "num_steps", "total_steps", "sampling_steps"):
            if key in inputs and is_numeric(inputs[key]):
                inputs[key] = 1
        if "start_at_step" in inputs and is_numeric(inputs["start_at_step"]):
            inputs["start_at_step"] = 0
        if "end_at_step" in inputs and is_numeric(inputs["end_at_step"]):
            inputs["end_at_step"] = 1

        # Cap any latent/model dimensions in the replay graph. This is warmup,
        # not final output generation, so smaller tensors preserve model-load
        # benefits without paying full inference cost.
        for key in ("width", "height"):
            if key in inputs and is_numeric(inputs[key]):
                inputs[key] = min(int(inputs[key]), 512)
        if "batch_size" in inputs and is_numeric(inputs["batch_size"]):
            inputs["batch_size"] = min(int(inputs["batch_size"]), 1)
        if class_type == "SaveImage" and "filename_prefix" in inputs:
            inputs["filename_prefix"] = "warmup"
    return warmup


def stack_to_profile(stack: dict) -> dict:
    """Convert an extracted model stack into a warmup-profile-compatible dict.

    The warmup profile uses either "checkpoint" mode (single ckpt_name) or
    "split" mode (individual unet/clip1/clip2/vae).  The stack from
    ``extract_requested_model_stack()`` uses lists; we pick the first
    entry from each list.

    If the stack was saved with a ``clip_type`` key (from the actual
    workflow's loader node), that clip_type is preserved.  Otherwise
    defaults to ``"flux"`` for backward compatibility.
    """
    if stack.get("checkpoint"):
        return {"mode": "checkpoint", "checkpoint": stack["checkpoint"][0]}
    if stack.get("unet") and stack.get("clip") and stack.get("vae"):
        clips = stack["clip"]
        clip1, clip2 = normalize_flux_clip_pair(clips[0], clips[-1] if len(clips) > 1 else clips[0])
        # Preserve clip_type from the actual workflow; fall back to "flux"
        _clip_type = stack.get("clip_type", "flux")
        return {
            "mode": "split",
            "unet": stack["unet"][0],
            "clip1": clip1,
            "clip2": clip2,
            "vae": stack["vae"][0],
            "clip_type": _clip_type,
        }
    return {}


# Bump this version whenever comfyapp.py changes.
# The custom node compares this against the last deployed version
# and re-runs `modal deploy` only when the version changes.
COMFYAPP_VERSION = "2.14.0"

APP_NAME = "comfyui"
VOLUME_NAME = "comfyui-models"
CUSTOM_NODES_VOLUME_NAME = "comfyui-custom-nodes"
COMFYUI_PORT = 8188
COMFYUI_API_PORT = 8189
MODELS_PATH = "/root/models"
CUSTOM_NODES_PATH = "/root/custom_nodes_vol"
LAST_MODEL_STACK_PATH = "/root/models/.last_model_stack.json"
LAST_WARMUP_WORKFLOW_PATH = "/root/models/.last_warmup_workflow.json"
SAGE_RUNTIME_CACHE_PATH = "/root/models/.sage_runtime_cache.json"

SUPPORTED_GPUS = get_supported_gpus()

GPU_PROFILES = {
    "budget": {"cpu": 2, "memory": 8192, "target_inputs": 1, "max_inputs": 1},
    "standard": {"cpu": 4, "memory": 32768, "target_inputs": 1, "max_inputs": 1},
    "high_mem": {"cpu": 4, "memory": 32768, "target_inputs": 1, "max_inputs": 1},
}

SAGEATTENTION_GIT_REF = "v2.2.0"
SAGEATTENTION_SITE_PACKAGES = "/usr/local/lib/python3.11/site-packages"

image = (
    modal.Image.from_registry(
        "nvidia/cuda:13.0.0-devel-ubuntu24.04",
        add_python="3.11",
    )
    .entrypoint([])
    .apt_install(
        "git",
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxrender1",
        "libxext6",
        "ffmpeg",
        "build-essential",
        "ninja-build",
        # CUDA 13.0 on Ubuntu 24.04 supports both GCC 13 (default) and clang
        # as host compilers for nvcc.  We install clang as a reliable fallback
        # since the nvidia/cuda:13.0.0-devel-ubuntu24.04 image may not ship a
        # full GCC toolchain.
        "clang",
    )
    .pip_install("comfy-cli==1.3.7", "httpx>=0.27.0")
    .run_commands(
        "comfy --skip-prompt install --nvidia",
        gpu="a10g",
    )
    # Force CUDA 13.0 PyTorch after comfy install (which may install older CUDA build)
    .run_commands(
        "python -m pip install --upgrade --force-reinstall "
        "torch torchvision torchaudio "
        "--index-url https://download.pytorch.org/whl/cu130",
        gpu="a10g",
    )
    # Triton >= 3.0 required for SageAttention2 on Blackwell
    .run_commands(
        "python -m pip install --upgrade 'triton>=3.0.0'",
    )
    .run_commands(
        "CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=12.0+PTX MAX_JOBS=4 "
        "python -m pip install --upgrade --force-reinstall "
        "git+https://github.com/thu-ml/SageAttention.git@v2.2.0 "
        "--no-build-isolation --no-deps",
        gpu="a10g",
    )
    .run_commands(
        "python -X utf8 -c \"import pathlib, site; "
        "site_root = next((p for p in site.getsitepackages() if 'site-packages' in p), site.getsitepackages()[0]); "
        "files = list(pathlib.Path(site_root).joinpath('sageattention').glob('*.so')); "
        "print([f.name for f in files]); "
        "assert files, 'no sageattention shared objects built'\"",
        gpu="a10g",
    )
    .run_commands(
        'python -X utf8 -c "import sageattention._fused; print(\'sageattention._fused ok\')"',
        gpu="a10g",
    )
    .env(
        {
            "TORCHINDUCTOR_CACHE_DIR": "/root/models/.inductor-cache",
            "TORCHINDUCTOR_FX_GRAPH_CACHE": "1",
            "TRITON_CACHE_DIR": "/tmp/triton_cache",
            "TORCHINDUCTOR_EMULATE_PRECISION_CASTS": "1",
            "TORCHINDUCTOR_COMPILE_THREADS": "1",
            "COMFYMODAL_ENABLE_TORCH_COMPILE": "0",
            "COMFYMODAL_ENABLE_GPU_SNAPSHOT": "0",
            "COMFYMODAL_WARMUP_UNET": "flux-2-klein-9b-fp8.safetensors",
            "COMFYMODAL_WARMUP_CLIP1": "qwen_3_8b_fp8mixed.safetensors",
            "COMFYMODAL_WARMUP_CLIP2": "qwen_3_8b_fp8mixed.safetensors",
            "COMFYMODAL_WARMUP_VAE": "flux2-vae.safetensors",
            "COMFYMODAL_WARMUP_CLIP_TYPE": "flux2",
            "COMFYMODAL_WARMUP_TEXT": "warmup",
        }
    )
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace")
)

download_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("httpx>=0.27.0")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace")
)

app = modal.App(APP_NAME, image=image)
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
custom_nodes_vol = modal.Volume.from_name(CUSTOM_NODES_VOLUME_NAME, create_if_missing=True)


@app.function(
    gpu="a10g",
    cpu=4,
    memory=16384,
    timeout=3600,
    min_containers=0,
    scaledown_window=2,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
)
@modal.web_server(COMFYUI_PORT, startup_timeout=300)
def ui():
    subprocess.Popen(
        f"comfy launch -- --listen 0.0.0.0 --port {COMFYUI_PORT}",
        shell=True,
    )


@app.function(
    image=download_image,
    cpu=2,
    memory=512,
    timeout=1800,
    volumes={MODELS_PATH: vol},
)
def download_model_to_volume(url: str, filename: str, save_path: str = "checkpoints", hf_token: str = ""):
    import httpx
    from pathlib import Path

    dest = Path(MODELS_PATH) / save_path / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        return {"status": "ok", "skipped": True, "path": str(dest)}

    headers = {}
    if hf_token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {hf_token}"

    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=1800) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1048576):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    sys.stdout.write(f"\r  {pct:.1f}%  ({downloaded // 1024**2} MB / {total // 1024**2} MB)")
                    sys.stdout.flush()

    vol.commit()
    return {"status": "ok", "path": str(dest)}


@app.function(
    image=download_image,
    cpu=2,
    memory=512,
    timeout=1800,
    volumes={MODELS_PATH: vol},
)
def batch_download_models(items: list, hf_token: str = "") -> list:
    results = list(
        download_model_to_volume.starmap(
            [(item["url"], item["filename"], item.get("save_path", "checkpoints"), hf_token) for item in items]
        )
    )
    return results


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=2,
    memory=4096,
    timeout=1800,
    volumes={CUSTOM_NODES_PATH: custom_nodes_vol},
)
def sync_custom_nodes_to_volume(archive_data: bytes) -> dict:
    """Receive a tar.gz archive of custom nodes and extract to volume."""
    import tarfile
    import io
    import os
    import shutil

    staging_dir = os.path.join(CUSTOM_NODES_PATH, ".staging")

    # Clean any leftover staging dir
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir)

    # Extract to staging with path traversal protection
    buf = io.BytesIO(archive_data)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for member in tar.getmembers():
            # Reject absolute paths and parent references
            if member.name.startswith("/") or ".." in member.name.split("/"):
                raise ValueError(f"Tar member '{member.name}' contains unsafe path")
            # Verify resolved path stays within staging directory
            member_path = os.path.normpath(os.path.join(staging_dir, member.name))
            if not member_path.startswith(os.path.normpath(staging_dir)):
                raise ValueError(f"Tar member '{member.name}' would extract outside target directory")
        # Reset buffer and extract after validation
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar2:
            tar2.extractall(path=staging_dir)

    # Swap: remove old content, move staging content into place
    for item in os.listdir(CUSTOM_NODES_PATH):
        if item == ".staging":
            continue
        item_path = os.path.join(CUSTOM_NODES_PATH, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)

    # Move extracted items from staging to volume root
    for item in os.listdir(staging_dir):
        src = os.path.join(staging_dir, item)
        dst = os.path.join(CUSTOM_NODES_PATH, item)
        shutil.move(src, dst)

    # Clean up staging
    shutil.rmtree(staging_dir)

    custom_nodes_vol.commit()

    # List what was extracted
    nodes = [d for d in os.listdir(CUSTOM_NODES_PATH) if os.path.isdir(os.path.join(CUSTOM_NODES_PATH, d))]
    return {"status": "ok", "nodes": nodes}


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=60,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
)
def get_volume_status() -> dict:
    """Return current state of both volumes."""
    import os

    vol.reload()
    custom_nodes_vol.reload()

    # Scan models
    models = []
    if os.path.isdir(MODELS_PATH):
        for folder in os.listdir(MODELS_PATH):
            folder_path = os.path.join(MODELS_PATH, folder)
            if not os.path.isdir(folder_path):
                continue
            for fname in os.listdir(folder_path):
                fpath = os.path.join(folder_path, fname)
                if os.path.isfile(fpath):
                    models.append({"folder": folder, "name": fname, "size": os.path.getsize(fpath)})

    # Scan custom nodes
    custom_nodes = []
    if os.path.isdir(CUSTOM_NODES_PATH):
        for d in os.listdir(CUSTOM_NODES_PATH):
            if os.path.isdir(os.path.join(CUSTOM_NODES_PATH, d)):
                custom_nodes.append(d)

    return {"models": models, "custom_nodes": custom_nodes}


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_preload_mode(mode: str) -> str:
    """Set the preload mode for the next cold restore.

    Writes the mode to ``/root/models/.preload_mode`` on the volume so
    the lifecycle restore function reads it before CPU preload.
    """
    import os
    mode = mode.strip().lower()
    valid = {"default", "sequential", "unet_only", "clip_only", "vae", "workers_1", "workers_2"}
    if mode not in valid:
        return f"invalid mode: {mode}  valid={valid}"
    os.makedirs("/root/models", exist_ok=True)
    with open(PRELOAD_MODE_PATH, "w") as f:
        f.write(mode)
    vol.commit()
    print(f"[comfyapp] set_preload_mode: {mode}")
    return f"preload_mode={mode}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_warmup_clip_encode(enabled: bool) -> str:
    """Set warmup CLIP encode for the next cold restore.

    Writes to ``/root/models/runtime_config/warmup_clip_encode.txt``
    so the lifecycle restore function reads it before warmup.
    """
    import os
    val = "1" if enabled else "0"
    os.makedirs("/root/models/runtime_config", exist_ok=True)
    with open(RUNTIME_WCE_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_warmup_clip_encode: {val}")
    return f"warmup_clip_encode={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_return_mode(mode: str) -> str:
    """Set return mode for the next prompt execution.

    Modes:
      full_base64       — return all images as base64 (current behavior)
      first_image_only  — return only the first image as base64
      metadata_only     — no image bytes, only counts/sizes/filenames
      paths_only        — return local output paths only (for local-volume testing)
      urls_only         — placeholder for object storage URL mode

    Writes to ``/root/models/runtime_config/return_mode.txt``
    so run_prompt() reads it before returning results.
    """
    import os
    mode = mode.strip().lower()
    valid = {"full_base64", "first_image_only", "metadata_only", "paths_only", "urls_only"}
    if mode not in valid:
        return f"invalid mode: {mode}  valid={valid}"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_RETURN_MODE_PATH, "w") as f:
        f.write(mode)
    vol.commit()
    print(f"[comfyapp] set_return_mode: {mode}")
    return f"return_mode={mode}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_clear_clip_encode_cache(enabled: bool) -> str:
    """Set CLIP encode cache clear flag for the next restore.

    When enabled, the CLIPTextEncode cache is cleared at restore start
    before warmup, ensuring clean WCE comparison runs.

    Writes to ``/root/models/runtime_config/clear_clip_encode_cache.txt``.
    """
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_CLIP_CACHE_CLEAR_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_clear_clip_encode_cache: {val}")
    return f"clear_clip_encode_cache={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_exec_profile(enabled: bool) -> str:
    """Enable/disable per-node executor profiling.

    When enabled, ``execution.execute()`` is monkey-patched to collect
    per-class-type timing data reported as ``_exec_profile`` in the
    ``run_prompt`` result.

    Writes to ``/root/models/runtime_config/exec_profile.txt``.
    """
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_EXEC_PROFILE_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_exec_profile: {val}")
    return f"exec_profile={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_sampler_profile(enabled: bool) -> str:
    """Enable/disable per-step sampler profiling.

    When enabled, ``KSAMPLER.sample`` is monkey-patched to capture
    per-step timing (setup, step_1..step_N, teardown) reported as
    ``_sampler_profile`` in the ``run_prompt`` result.

    Writes to ``/root/models/runtime_config/sampler_profile.txt``.
    """
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_SAMPLER_PROFILE_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_sampler_profile: {val}")
    return f"sampler_profile={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_guider_profile(enabled: bool) -> str:
    """Enable/disable guider overhead profiling.

    When enabled, CFGGuider methods (sample/outer_sample/inner_sample)
    and sampler_helpers (prepare_sampling/cleanup_models) are
    monkey-patched to capture per-segment timing.

    Writes to ``/root/models/runtime_config/guider_profile.txt``.
    """
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_GUIDER_PROFILE_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_guider_profile: {val}")
    return f"guider_profile={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_deep_profile(enabled: bool) -> str:
    """Enable/disable deep sampler wrapper profiling.

    Instruments prepare_sampling internals, SamplerCustomAdvanced
    pre/post, and KSAMPLER.sample setup.

    Writes to ``/root/models/runtime_config/deep_profile.txt``.
    """
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_DEEP_PROFILE_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_deep_profile: {val}")
    return f"deep_profile={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_lmg_fastpath_dryrun(enabled: bool) -> str:
    """Enable/disable LMG fast-path dry-run diagnostics (no behavior change)."""
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_LMG_FASTPATH_DRYRUN_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_lmg_fastpath_dryrun: {val}")
    return f"lmg_fastpath_dryrun={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_lmg_fastpath(enabled: bool) -> str:
    """Enable/disable LMG fast-path (skips load_models_gpu for already-loaded models)."""
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_LMG_FASTPATH_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_lmg_fastpath: {val}")
    return f"lmg_fastpath={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_modelpatcher_cache(enabled: bool) -> str:
    """Enable/disable canonical ModelPatcher cache for warmup→prompt reuse."""
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_MODELPATCHER_CACHE_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_modelpatcher_cache: {val}")
    return f"modelpatcher_cache={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_modelpatcher_cache_dryrun(enabled: bool) -> str:
    """Enable/disable canonical ModelPatcher cache dry-run diagnostics."""
    import os
    val = "1" if enabled else "0"
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_MODELPATCHER_CACHE_DRYRUN_PATH, "w") as f:
        f.write(val)
    vol.commit()
    print(f"[comfyapp] set_modelpatcher_cache_dryrun: {val}")
    return f"modelpatcher_cache_dryrun={val}"


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=2,
    memory=4096,
    timeout=1800,
    volumes={MODELS_PATH: vol},
)
def upload_model_to_volume(file_data: bytes, folder: str, filename: str) -> dict:
    """Upload a model file directly to the volume."""
    import os
    from pathlib import Path

    dest = Path(MODELS_PATH) / folder / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "wb") as f:
        f.write(file_data)

    vol.commit()
    return {"status": "ok", "path": str(dest), "size": len(file_data)}


@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=2,
    memory=4096,
    timeout=3600,
    volumes={MODELS_PATH: vol},
)
def upload_model_chunk(chunk_data: bytes, folder: str, filename: str, offset: int, is_last: bool) -> dict:
    """Upload a model file chunk to the volume. Chunks are appended sequentially."""
    import os
    from pathlib import Path

    dest = Path(MODELS_PATH) / folder / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    mode = "ab" if offset > 0 else "wb"
    with open(dest, mode) as f:
        f.write(chunk_data)

    if is_last:
        vol.commit()
        return {"status": "ok", "path": str(dest), "size": os.path.getsize(dest)}

    return {"status": "partial", "offset": offset + len(chunk_data)}


class _ComfyAPIMixin:
    """Shared implementation for all GPU-specific ComfyAPI classes."""

    # Cached localhost HTTP client for ComfyUI API calls.
    _http_client_obj = None

    def _profile_ms(self, started_at: float) -> float:
        return round((time.time() - started_at) * 1000, 1)

    def _log_profile(self, stage: str, **fields) -> None:
        if not PROFILING_ENABLED:
            return
        payload = " ".join(f"{k}={v}" for k, v in fields.items())
        print(f"[comfyapp.profile] stage={stage} {payload}".rstrip())

    @property
    def _http_client(self):
        """Lazily-initialised httpx.Client pointed at the local ComfyUI API."""
        import httpx
        if self._http_client_obj is None:
            self._http_client_obj = httpx.Client(base_url=f"http://127.0.0.1:{COMFYUI_API_PORT}")
        return self._http_client_obj

    def _ensure_models_symlink(self):
        """Ensure /root/comfy/ComfyUI/models symlink → MODELS_PATH exists."""
        _t0 = time.time()
        comfy_models = "/root/comfy/ComfyUI/models"
        if not os.path.islink(comfy_models):
            if os.path.isdir(comfy_models):
                import shutil
                shutil.rmtree(comfy_models)
            os.symlink(MODELS_PATH, comfy_models)
            print(f"[comfyapp] models_symlink created -> {MODELS_PATH} "
                  f"in {(time.time()-_t0)*1000:.1f}ms")
        else:
            print(f"[comfyapp] models_symlink already exists -> {os.readlink(comfy_models)} "
                  f"in {(time.time()-_t0)*1000:.1f}ms")

    def _save_last_model_stack(self, stack: dict) -> None:
        """Persist the workflow's model stack to the volume for the next restore.

        Writes the file synchronously but commits to volume in a background
        thread to avoid blocking the response path with network I/O (~370ms).
        """
        import json
        import threading
        try:
            os.makedirs(os.path.dirname(LAST_MODEL_STACK_PATH), exist_ok=True)
            tmp_path = f"{LAST_MODEL_STACK_PATH}.tmp"
            with open(tmp_path, "w") as f:
                json.dump(stack, f)
            os.replace(tmp_path, LAST_MODEL_STACK_PATH)
            # Background commit so the response isn't blocked by volume I/O
            t = threading.Thread(target=vol.commit, daemon=True)
            t.start()
        except Exception as exc:
            print(f"[comfyapp] failed to save last model stack: {exc}")

    def _load_last_model_stack(self) -> dict:
        """Read the previously-saved model stack from the volume."""
        try:
            if os.path.isfile(LAST_MODEL_STACK_PATH):
                with open(LAST_MODEL_STACK_PATH) as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[comfyapp] failed to load last model stack: {exc}")
        return {}

    def _save_last_warmup_workflow(self, workflow: dict) -> None:
        """Persist a cheap warmup replay derived from a successful prompt."""
        try:
            os.makedirs(os.path.dirname(LAST_WARMUP_WORKFLOW_PATH), exist_ok=True)
            warmup = build_replay_warmup_workflow(workflow)
            tmp_path = f"{LAST_WARMUP_WORKFLOW_PATH}.tmp"
            with open(tmp_path, "w") as f:
                json.dump(warmup, f, indent=2, sort_keys=True)
            os.replace(tmp_path, LAST_WARMUP_WORKFLOW_PATH)
        except Exception as exc:
            print(f"[comfyapp] failed to save last warmup workflow: {exc}")

    def _load_last_warmup_workflow(self) -> dict:
        """Read the replay warmup workflow saved from the last successful prompt."""
        try:
            if os.path.isfile(LAST_WARMUP_WORKFLOW_PATH):
                with open(LAST_WARMUP_WORKFLOW_PATH) as f:
                    workflow = json.load(f)
                if isinstance(workflow, dict) and workflow:
                    return workflow
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[comfyapp] failed to load last warmup workflow: {exc}")
        return {}

    def _find_model_file(self, bucket: str, filename: str) -> str | None:
        """Best-effort model file lookup for warmup preflight checks."""
        candidates = {
            "checkpoint": ["checkpoints"],
            "unet": ["diffusion_models", "unet", "unets"],
            "clip": ["text_encoders", "clip"],
            "vae": ["vae"],
        }.get(bucket, [])
        direct = os.path.join(MODELS_PATH, filename)
        if os.path.isfile(direct):
            return direct
        for folder in candidates:
            path = os.path.join(MODELS_PATH, folder, filename)
            if os.path.isfile(path):
                return path
        return None

    def _validate_warmup_profile_files(self, profile: dict) -> None:
        """Fail fast for missing/placeholder warmup files before expensive execution."""
        checks: list[tuple[str, str]] = []
        if profile.get("mode") == "checkpoint":
            checks.append(("checkpoint", profile.get("checkpoint", "")))
        elif profile.get("mode") == "split":
            checks.extend([
                ("unet", profile.get("unet", "")),
                ("clip", profile.get("clip1", "")),
                ("clip", profile.get("clip2", "")),
                ("vae", profile.get("vae", "")),
            ])
        missing = []
        too_small = []
        for bucket, filename in checks:
            if not filename:
                missing.append(f"{bucket}:<empty>")
                continue
            path = self._find_model_file(bucket, filename)
            if path is None:
                missing.append(f"{bucket}:{filename}")
                continue
            size = os.path.getsize(path)
            print(f"[comfyapp] warmup_validate: bucket={bucket} name={filename} path={path} size_mb={round(size/(1024*1024),1)}")
            if size < 1024 * 1024:
                too_small.append(f"{bucket}:{filename} ({size} bytes)")
        if missing or too_small:
            raise RuntimeError(
                "Warmup model preflight failed; "
                f"missing={missing or []}; too_small={too_small or []}"
            )

    def _sync_custom_nodes_from_volume(self):
        custom_nodes_vol.reload()
        comfy_custom_nodes = "/root/comfy/ComfyUI/custom_nodes"
        summary = sync_custom_nodes_into_comfy(CUSTOM_NODES_PATH, comfy_custom_nodes)
        state = custom_node_volume_state(CUSTOM_NODES_PATH)
        return summary, state

    def _snapshot_preload_profile(self) -> dict:
        """Return the warmup profile, preferring actual workflow history over env vars.

        Priority:
        1. last_model_stack from the most recent real prompt — this matches the
           actual workflow being served.
        2. env var profile — fallback for first cold run when no history exists.
        3. Empty dict — no warmup.

        Logs the source and warns when env profile differs from actual workflow.
        Returns the profile with a ``_source`` key added.
        """
        last_stack = self._load_last_model_stack()
        env_profile = load_warmup_profile()
        profile = None
        source = "none"

        if last_stack:
            profile = stack_to_profile(last_stack)
            source = "last_stack"
            if env_profile and profile != env_profile:
                print(f"[comfyapp] snapshot_preload_profile WARNING: "
                      f"env profile {env_profile} differs from "
                      f"last_workflow stack {last_stack}")
            print(f"[comfyapp] snapshot_preload_profile source={source} "
                  f"mode={profile.get('mode','?') if profile else 'none'} "
                  f"data={profile}")
        elif env_profile:
            profile = env_profile
            source = "env_vars"
            print(f"[comfyapp] snapshot_preload_profile source={source} "
                  f"mode={profile.get('mode','?')} data={profile}")
            print(f"[comfyapp] snapshot_preload_profile WARNING: using env "
                  f"warmup profile; may not match actual workflow")

        if profile:
            profile["_source"] = source
        else:
            print(f"[comfyapp] snapshot_preload_profile source=none — no warmup profile configured")
        return profile

    def _log_warmup_vs_workflow_diagnostics(self, warmup_profile: dict, workflow_model_stack: dict, raw_workflow: dict | None = None) -> dict:
        """Compare what the warmup loaded vs what the workflow actually needs.
        Logs a side-by-side diff and returns a match dict.
        """
        result = {
            "warmup_profile": dict(warmup_profile) if warmup_profile else {},
            "workflow_stack": dict(workflow_model_stack) if workflow_model_stack else {},
            "match": {},
        }
        wu = warmup_profile or {}
        ws = workflow_model_stack or {}
        wu_unets = [wu.get("unet", "")] if wu.get("mode") == "split" else wu.get("checkpoint", []) if wu.get("mode") == "checkpoint" else []
        ws_unets = ws.get("unet", []) or ws.get("checkpoint", [])
        wu_clips = [wu.get("clip1", ""), wu.get("clip2", "")] if wu.get("mode") == "split" else []
        ws_clips = ws.get("clip", [])
        wu_vaes = [wu.get("vae", "")] if wu.get("mode") == "split" else []
        ws_vaes = ws.get("vae", [])

        unet_match = bool(set(wu_unets) & set(ws_unets)) if wu_unets and ws_unets else None
        clip_match = bool(set(wu_clips) & set(ws_clips)) if wu_clips and ws_clips else None
        vae_match = bool(set(wu_vaes) & set(ws_vaes)) if wu_vaes and ws_vaes else None
        result["match"] = {"unet": unet_match, "clip": clip_match, "vae": vae_match}

        # Log clip_type from warmup profile and raw workflow nodes
        _wu_clip_type = wu.get("clip_type", "?")
        _wf_clip_types: list[str] = []
        if raw_workflow:
            for _node in raw_workflow.values():
                if isinstance(_node, dict):
                    _ct = _node.get("class_type", "")
                    if _ct in ("CLIPLoader", "DualCLIPLoader"):
                        _t = str(_node.get("inputs", {}).get("type", "?"))
                        if _t not in _wf_clip_types:
                            _wf_clip_types.append(_t)
        ws_clip_type = _wf_clip_types[0] if _wf_clip_types else "?"
        print(f"[comfyapp] warmup_vs_workflow diagnostics:")
        print(f"  WARMUP_PROFILE: unet={wu_unets} clip={wu_clips} vae={wu_vaes} clip_type={_wu_clip_type} mode={wu.get('mode','?')}")
        print(f"  WORKFLOW_STACK: unet={ws_unets} clip={ws_clips} vae={ws_vaes}")
        print(f"  MATCH: unet={unet_match} clip={clip_match} vae={vae_match}")
        if clip_match is False:
            print(f"  CLIP MISMATCH: warmup clips={set(wu_clips)-set(ws_clips)} "
                  f"workflow clips={set(ws_clips)-set(wu_clips)}")
        print(f"  CLIP_TYPE: warmup={_wu_clip_type} workflow={ws_clip_type} match={_wu_clip_type==ws_clip_type}")
        return result

    def _snapshot_preload_paths(self, profile: dict) -> list[str]:
        """Resolve model file paths for snapshot CPU preload.

        Preloads all model files (checkpoint or split) into CPU RAM during
        startup so Modal's memory snapshot captures them.  On restore, the
        cached state dicts are returned by ``_patch_model_cpu_cache``,
        eliminating volume reads during the first prompt execution.

        Which files are preloaded is controlled by PRELOAD_MODE (env var
        ``COMFYMODAL_PRELOAD_MODE``).
        """
        if not profile:
            print("[comfyapp] snapshot_preload_paths: no profile, nothing to preload")
            return []
        profile_mode = profile.get("mode", "")
        checks: list[tuple[str, str]] = []
        if profile_mode == "checkpoint":
            checks.append(("checkpoint", profile.get("checkpoint", "")))
        elif profile_mode == "split":
            unet_f = profile.get("unet", "")
            clip1_f = profile.get("clip1", "")
            clip2_f = profile.get("clip2", "")
            vae_f = profile.get("vae", "")
            _pm = _resolve_preload_mode()
            if _pm == "unet_only":
                checks.append(("unet", unet_f))
            elif _pm == "clip_only":
                checks.append(("clip", clip1_f))
                checks.append(("clip", clip2_f))
            elif _pm == "vae":
                checks.extend([
                    ("unet", unet_f),
                    ("clip", clip1_f),
                    ("clip", clip2_f),
                    ("vae", vae_f),
                ])
            else:
                checks.extend([
                    ("unet", unet_f),
                    ("clip", clip1_f),
                    ("clip", clip2_f),
                ])
        # Resolve paths concurrently: each _find_model_file call does FUSE
        # stat requests (network round-trips to Modal's volume service).
        # Running them sequentially adds ~50-150ms per stat → 200-600ms
        # for a full profile.  ThreadPoolExecutor hides this latency.
        active = [(b, f) for b, f in checks if f]
        paths = []
        seen = set()
        path_times: dict[str, float] = {}
        if active:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            def _resolve(bucket, filename):
                _t = time.time()
                p = self._find_model_file(bucket, filename)
                return filename, p, round((time.time() - _t) * 1000, 1)
            with ThreadPoolExecutor(max_workers=min(len(active), 4)) as _pool:
                _futs = {_pool.submit(_resolve, b, f): (b, f) for b, f in active}
                for _fut in as_completed(_futs):
                    bucket, filename = _futs[_fut]
                    try:
                        fn, path, d_ms = _fut.result()
                        path_times[fn] = d_ms
                        if path and path not in seen:
                            seen.add(path)
                            paths.append(path)
                            print(f"[comfyapp] snapshot_preload_paths: resolved bucket={bucket} name={fn} -> {path} in {d_ms}ms")
                        else:
                            print(f"[comfyapp] snapshot_preload_paths: NOT FOUND bucket={bucket} name={fn} in {d_ms}ms")
                    except Exception as exc:
                        print(f"[comfyapp] snapshot_preload_paths: ERROR bucket={bucket} name={filename}: {exc}")
        print(f"[comfyapp] snapshot_preload_paths: resolved {len(paths)} paths: {[os.path.basename(p) for p in paths]} per-file: {path_times}")
        return paths

    def _preload_models_to_cpu(self, file_paths: list[str], on_file_loaded=None) -> dict:
        """Preload model state dicts into CPU RAM.

        Loaded state dicts are stored in ``_model_cpu_cache``.  The
        ``_patch_model_cpu_cache`` wrapper returns shallow copies of cached
        state dicts when ComfyUI requests a model file, eliminating volume
        reads during the first real-prompt execution.

        This is safe to call during ``restore(snap=False)`` because the
        cache is populated *after* the memory snapshot is already loaded,
        so it does not increase snapshot size (unlike the startup-time
        preload that was disabled for causing 3x restore regression).

        Model files are loaded concurrently via ``ThreadPoolExecutor``
        since FUSE volume reads are I/O-bound and independent across files.

        When ``on_file_loaded`` is callable, it's invoked with ``(filename,)``
        as each file completes loading.  Used by the parallel warmup to
        start text encoding as soon as the CLIP state dict is available.
        """
        if not file_paths:
            return {"count": 0, "cached": [], "file_timing_ms": {}}
        if not hasattr(self, "_model_cpu_cache"):
            self._model_cpu_cache = {}
        _total_start = time.time()
        _total_bytes = 0
        for p in file_paths:
            try:
                _total_bytes += os.path.getsize(p)
            except OSError:
                pass
        # Determine worker count from PRELOAD_MODE
        _preload_max_workers = 4
        _pm = _resolve_preload_mode()
        if _pm == "workers_1":
            _preload_max_workers = 1
        elif _pm == "workers_2":
            _preload_max_workers = 2
        elif _pm in ("sequential",):
            _preload_max_workers = 1

        print(
            f"[comfyapp] preload_models_to_cpu: files={len(file_paths)} "
            f"total_gb={round(_total_bytes / (1024**3), 2)} "
            f"mode={_pm} workers={_preload_max_workers} starting"
        )
        original_loader = getattr(self, "_original_model_loader", None)
        if original_loader is None:
            raise RuntimeError("Original ComfyUI model loader unavailable for CPU preload")

        # Determine which files need loading (skip already-cached)
        to_load = []
        for path in file_paths:
            filename = os.path.basename(path)
            if filename not in self._model_cpu_cache:
                to_load.append((path, filename))

        cached = []
        file_timing_ms: dict[str, float] = {}

        if to_load:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _load_one(path: str, filename: str) -> tuple[str, object, object | None, float]:
                started = time.time()
                loaded = original_loader(path, return_metadata=True)
                d_ms = round((time.time() - started) * 1000, 1)
                if isinstance(loaded, tuple) and len(loaded) == 2:
                    return filename, loaded[0], loaded[1], d_ms
                return filename, loaded, None, d_ms

            batch = _total_bytes
            with ThreadPoolExecutor(max_workers=min(len(to_load), _preload_max_workers)) as pool:
                fut_map = {pool.submit(_load_one, p, f): f for p, f in to_load}
                for future in as_completed(fut_map):
                    filename = fut_map[future]
                    try:
                        fn, state_dict, metadata, d_ms = future.result()
                        self._model_cpu_cache[fn] = (state_dict, metadata)
                        file_timing_ms[fn] = d_ms
                        cached.append(fn)
                        if callable(on_file_loaded):
                            try:
                                on_file_loaded(fn)
                            except Exception:
                                pass
                        size_mb = "?"
                        for p, f in to_load:
                            if f == fn:
                                try:
                                    size_mb = round(os.path.getsize(p) / (1024 * 1024), 1)
                                except OSError:
                                    pass
                                break
                        self._log_profile(
                            "snapshot_preload_model",
                            file=fn,
                            size_mb=size_mb,
                            duration_ms=d_ms,
                        )
                    except Exception as exc:
                        file_timing_ms[filename] = -1.0
                        self._log_profile("snapshot_preload_model_failed", file=filename, error=str(exc)[:200])
        else:
            # All files already cached — just report them
            for path in file_paths:
                filename = os.path.basename(path)
                cached.append(filename)

        _total_ms = self._profile_ms(_total_start)
        _total_loaded_gb = sum(os.path.getsize(p) for p in file_paths if os.path.isfile(p)) / (1024**3)
        # Detect preload outliers: any single file >5s
        _slowest_fn = ""
        _slowest_ms = 0.0
        for _fn, _d in file_timing_ms.items():
            if _d > _slowest_ms:
                _slowest_ms = _d
                _slowest_fn = _fn
        if _total_ms > 5000 and _slowest_fn:
            _slowest_size_gb = 0.0
            for p in file_paths:
                if os.path.basename(p) == _slowest_fn:
                    try:
                        _slowest_size_gb = os.path.getsize(p) / (1024**3)
                    except OSError:
                        pass
                    break
            _sl_throughput = round(_slowest_size_gb / max(_slowest_ms / 1000, 0.001), 2) if _slowest_size_gb else 0.0
            print(f"[comfyapp] preload_outlier: true total_ms={_total_ms} "
                  f"slowest_file={_slowest_fn} slowest_ms={_slowest_ms:.0f} "
                  f"size_gb={_slowest_size_gb:.2f} throughput_gbps={_sl_throughput} "
                  f"workers={_preload_max_workers}")

        print(
            f"[comfyapp] preload_models_to_cpu: done in {_total_ms}ms "
            f"loaded={len(cached)} files={len(file_paths)} "
            f"loaded_gb={round(_total_loaded_gb, 2)} "
            f"throughput_gbps={round(_total_loaded_gb / max(_total_ms/1000, 0.001), 2)}"
        )
        return {
            "count": len(cached),
            "cached": cached,
            "file_timing_ms": file_timing_ms,
        }

    def _patch_model_cpu_cache(self, comfy_utils) -> None:
        """Patch ComfyUI model loading to reuse CPU-cached state dicts."""
        if getattr(self, "_model_cpu_cache_patched", False):
            return
        original_load = comfy_utils.load_torch_file
        self._original_model_loader = original_load
        # Instrumentation counters for cache diagnostics
        self._cpu_cache_hits: dict[str, int] = {}
        self._cpu_cache_misses: dict[str, int] = {}

        def cached_load(path, *args, **kwargs):
            import copy

            filename = os.path.basename(path)
            cache = getattr(self, "_model_cpu_cache", {})
            if filename in cache:
                self._cpu_cache_hits[filename] = self._cpu_cache_hits.get(filename, 0) + 1
                _dc_start = time.time()
                cached = cache[filename]
                if isinstance(cached, tuple) and len(cached) == 2:
                    state_dict, metadata = copy.copy(cached[0]), copy.copy(cached[1])
                else:
                    state_dict, metadata = copy.copy(cached), None
                _dc_ms = round((time.time() - _dc_start) * 1000, 1)
                acc = getattr(self, "_exec_deepcopy_ms", 0.0)
                self._exec_deepcopy_ms = acc + _dc_ms
                self._log_profile("model_cache_hit", file=filename, deepcopy_ms=_dc_ms)
                if kwargs.get("return_metadata"):
                    return state_dict, metadata
                return state_dict
            self._cpu_cache_misses[filename] = self._cpu_cache_misses.get(filename, 0) + 1
            started = time.time()
            result = original_load(path, *args, **kwargs)
            duration_ms = self._profile_ms(started)
            try:
                size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
            except OSError:
                size_mb = "?"
            self._log_profile(
                "model_volume_load",
                file=filename,
                size_mb=size_mb,
                return_metadata=1 if kwargs.get("return_metadata") else 0,
                duration_ms=duration_ms,
            )
            # Accumulate into execution-profile accumulator
            acc = getattr(self, "_exec_model_load_io_ms", 0.0)
            self._exec_model_load_io_ms = acc + duration_ms
            return result

        comfy_utils.load_torch_file = cached_load
        self._model_cpu_cache_patched = True

    def _install_custom_node_requirements(self, force: bool = False) -> dict:
        """Install requirements.txt for each custom node, skipping cached hashes."""
        metadata = load_runtime_metadata()
        cached = metadata.get("requirements", {})
        installed = []
        skipped = []
        failures = []
        updated_hashes = {}

        for node_dir in sorted(os.listdir(CUSTOM_NODES_PATH)) if os.path.isdir(CUSTOM_NODES_PATH) else []:
            src = os.path.join(CUSTOM_NODES_PATH, node_dir)
            if not os.path.isdir(src):
                continue
            req_file = os.path.join(src, "requirements.txt")
            if not os.path.isfile(req_file):
                continue
            current_hash = requirements_file_hash(req_file)
            if not force and current_hash and cached.get(node_dir) == current_hash:
                skipped.append(node_dir)
                continue

            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                failures.append({
                    "node": node_dir,
                    "stderr": (result.stderr or result.stdout or "requirements install failed")[:1000],
                })
            else:
                installed.append(node_dir)
                if current_hash:
                    updated_hashes[node_dir] = current_hash

        if failures:
            raise RuntimeError(f"Custom node requirements install failed: {failures}")

        # Persist updated hashes
        if updated_hashes or force:
            metadata["requirements"] = {**cached, **updated_hashes}
            save_runtime_metadata(metadata)

        return {"installed": installed, "skipped": skipped}

    # ── sageattention runtime policy helpers ──────────────────────────────

    def _preferred_sage_backend(self):
        import sageattention

        for name, kwargs in (
            ("sageattn_qk_int8_pv_fp16_cuda", {"pv_accum_dtype": "fp32"}),
            ("sageattn_qk_int8_pv_fp8_cuda", {"pv_accum_dtype": "fp32+fp32"}),
        ):
            candidate = getattr(sageattention, name, None)
            if callable(candidate):
                return name, candidate, kwargs
        return None, None, {}

    def _verify_baked_sageattention_runtime(self) -> tuple[bool, list[str]]:
        import importlib
        import torch

        extension_files = list_sageattention_extension_files(SAGEATTENTION_SITE_PACKAGES)
        if not extension_files:
            return False, ["compiled-extensions-missing"]

        try:
            import sageattention._fused  # noqa: F401
            importlib.invalidate_caches()
            import sageattention  # noqa: F401
        except Exception as exc:
            return False, [f"_fused-import-failed:{type(exc).__name__}"]

        try:
            backend_name, backend, backend_kwargs = self._preferred_sage_backend()
            if backend is None:
                return False, ["no-supported-kjnodes-backend-symbol"]
            q = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            k = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            v = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            _ = backend(q, k, v, is_causal=False, attn_mask=None, tensor_layout="NHD", **backend_kwargs)
            torch.cuda.synchronize()
            return True, [str(backend_name or "unknown-backend"), *[p.name for p in extension_files]]
        except Exception as exc:
            return False, [f"cuda-smoke-test-failed:{type(exc).__name__}"]

    def _select_sage_runtime_mode(self) -> tuple[str, str]:
        if getattr(self, "_sage_runtime_mode", None) is not None:
            return self._sage_runtime_mode, getattr(self, "_sage_runtime_reason", "sticky")

        # Check persistent cache on volume
        import json, os
        cached = self._load_sage_runtime_cache()
        if cached:
            print(f"[comfyapp] sage_runtime_cache hit mode={cached['mode']} reason={cached['reason']} "
                  f"gpu={cached['gpu_name']} sage_v={cached['sage_version']}")
            self._sage_runtime_mode = cached["mode"]
            self._sage_runtime_reason = cached["reason"]
            return self._sage_runtime_mode, self._sage_runtime_reason

        import torch
        extension_files = list_sageattention_extension_files(SAGEATTENTION_SITE_PACKAGES)
        ok, details = self._verify_baked_sageattention_runtime()
        mode, reason = choose_sage_runtime_mode(
            enabled=True,
            extension_files=extension_files,
            import_ok=ok,
            smoke_ok=ok,
        )
        self._sage_runtime_mode = mode
        self._sage_runtime_reason = details[0] if details else reason
        print(f"[comfyapp] sage_runtime_mode={self._sage_runtime_mode} reason={self._sage_runtime_reason}")
        # Persist to volume for future restores
        self._save_sage_runtime_cache(mode, self._sage_runtime_reason)
        return self._sage_runtime_mode, self._sage_runtime_reason

    def _load_sage_runtime_cache(self) -> dict | None:
        """Read cached sage runtime mode from volume. Returns None if stale or missing."""
        import json, os, torch
        try:
            if not os.path.isfile(SAGE_RUNTIME_CACHE_PATH):
                return None
            with open(SAGE_RUNTIME_CACHE_PATH) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unknown"
            sage_version = ""
            try:
                import sageattention
                sage_version = getattr(sageattention, "__version__", "") or ""
            except ImportError:
                pass
            # Cache is valid if GPU and sage version match
            if data.get("gpu_name") == gpu_name and data.get("sage_version") == sage_version:
                return data
            print(f"[comfyapp] sage_runtime_cache stale: gpu {data.get('gpu_name')}->{gpu_name} "
                  f"sage {data.get('sage_version')}->{sage_version}")
        except Exception as exc:
            print(f"[comfyapp] sage_runtime_cache error: {exc}")
        return None

    def _save_sage_runtime_cache(self, mode: str, reason: str) -> None:
        """Persist sage runtime mode to volume for faster future restores."""
        import json, os, torch, time
        try:
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unknown"
            sage_version = ""
            try:
                import sageattention
                sage_version = getattr(sageattention, "__version__", "") or ""
            except ImportError:
                pass
            data = {
                "mode": mode,
                "reason": reason,
                "gpu_name": gpu_name,
                "sage_version": sage_version,
                "created_at": time.time(),
            }
            os.makedirs(os.path.dirname(SAGE_RUNTIME_CACHE_PATH), exist_ok=True)
            tmp = f"{SAGE_RUNTIME_CACHE_PATH}.tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp, SAGE_RUNTIME_CACHE_PATH)
            print(f"[comfyapp] sage_runtime_cache saved mode={mode} gpu={gpu_name} sage_v={sage_version}")
        except Exception as exc:
            print(f"[comfyapp] sage_runtime_cache save error: {exc}")

    def _apply_sage_attention_policy(self):
        _t0 = time.time()
        baked_cuda_available = getattr(self, "_sage_runtime_mode", "triton_fallback") == "baked_cuda"
        found = False
        patched = False
        for mod in list(sys.modules.values()):
            file_name = getattr(mod, "__file__", "") or ""
            if file_name.endswith("model_optimization_nodes.py"):
                found = True
                patched = patch_kjnodes_get_sage_func(mod, baked_cuda_available=baked_cuda_available)
                _dur = round((time.time() - _t0) * 1000, 1)
                print(f"[comfyapp] sage_policy module=model_optimization_nodes.py "
                      f"found=True patched={patched} "
                      f"baked_cuda_available={baked_cuda_available} "
                      f"duration={_dur}ms")
                return patched
        _dur = round((time.time() - _t0) * 1000, 1)
        print(f"[comfyapp] sage_policy module=model_optimization_nodes.py "
              f"found=False baked_cuda_available={baked_cuda_available} "
              f"duration={_dur}ms")
        return False

    # ── Backend scaffold (warmup + execution backend selection) ──────────

    def _begin_prompt_profile(self, workflow: dict, prompt_id: str, outputs_to_execute) -> None:
        node_map: dict[str, str] = {}
        class_counts: dict[str, int] = {}
        for node_id, spec in (workflow or {}).items():
            if not isinstance(spec, dict):
                continue
            class_type = str(spec.get("class_type", "?"))
            node_map[str(node_id)] = class_type
            class_counts[class_type] = class_counts.get(class_type, 0) + 1

        self._current_prompt_node_map = node_map
        self._current_prompt_id = prompt_id[:8]
        self._perf_last_node = None
        self._perf_last_ts = None
        self._ksampler_state = None

        # Stage windows for the per-node timing trace (t4..t7).
        # Each window records first/last seen timestamps for a given
        # class_type so that CLIPLoader, CLIPTextEncode, Sampler and
        # VAEDecode each have a clean start/end pair even when a single
        # node execution spans multiple event dispatches.
        self._stage_windows: dict[str, dict[str, float]] = {
            "unet_load": {},
            "clip_load": {},
            "vae_load": {},
            "clip_encode": {},
            "sampler": {},
            "vae_decode": {},
        }

        if not PROFILING_ENABLED:
            return

        self._log_profile(
            "inproc_node_map",
            prompt_id=prompt_id[:8],
            outputs=len(outputs_to_execute or []),
            map=json.dumps(node_map, sort_keys=True, separators=(",", ":")),
        )
        self._log_profile(
            "inproc_node_counts",
            prompt_id=prompt_id[:8],
            counts=json.dumps(class_counts, sort_keys=True, separators=(",", ":")),
        )

    def _node_class_type(self, node_id) -> str:
        return getattr(self, "_current_prompt_node_map", {}).get(str(node_id), "?")

    def _begin_profiled_node(self, node, now: float) -> None:
        node = str(node)
        class_type = self._node_class_type(node)
        self._perf_last_node = node
        self._perf_last_ts = now
        if "Sampler" in class_type:
            self._ksampler_state = {
                "node": node,
                "class_type": class_type,
                "started": now,
                "first_progress": None,
                "last_progress": None,
                "progress_events": 0,
                "max_step": 0,
                "max_steps": 0,
            }
        # Trace t4..t7 stage windows: record the first time a node of the
        # given class starts so we have a clean t<N>_start timestamp even
        # when the class appears multiple times in the graph (e.g. dual
        # CLIPTextEncode nodes).  The matching t<N>_end is recorded in
        # _finish_profiled_node.
        stage = self._stage_for_class(class_type)
        if stage:
            windows = getattr(self, "_stage_windows", None)
            if windows is not None and stage != "sampler" and "start" not in windows[stage]:
                windows[stage]["start"] = now
                windows[stage]["start_node"] = node
                windows[stage]["start_class"] = class_type
        if not PROFILING_ENABLED:
            return
        self._log_profile(
            "inproc_exec_progress",
            event="executing_node",
            node=node[:40],
            class_type=class_type[:80],
        )

    @staticmethod
    def _stage_for_class(class_type: str) -> str | None:
        """Map a node class_type to one of the t4..t7 or warmup trace stages."""
        ct = class_type or ""
        if "UNETLoader" in ct:
            return "unet_load"
        if "CLIPLoader" in ct or "DualCLIPLoader" in ct:
            return "clip_load"
        if "VAELoader" in ct:
            return "vae_load"
        if "TextEncode" in ct or "CLIPTextEncode" in ct:
            return "clip_encode"
        if "Sampler" in ct or "SamplerAdvanced" in ct or "SamplerCustom" in ct:
            return "sampler"
        if "VAEDecode" in ct:
            return "vae_decode"
        return None

    def _commit_stage_windows_to_trace(self, trace: Trace) -> None:
        """Copy the t4..t7 stage windows onto the given trace."""
        windows = getattr(self, "_stage_windows", None) or {}
        for stage, fields in windows.items():
            if not fields:
                continue
            start = fields.get("start")
            end = fields.get("end")
            if start is not None and end is not None:
                trace._t[f"t4_clip_load_start" if stage == "clip_load"
                         else f"t5_text_encode_start" if stage == "clip_encode"
                         else f"t6_sampler_start" if stage == "sampler"
                         else f"t7_vae_decode_start"] = start
                trace._t[f"t4_clip_load_end" if stage == "clip_load"
                         else f"t5_text_encode_end" if stage == "clip_encode"
                         else f"t6_sampler_end" if stage == "sampler"
                         else f"t7_vae_decode_end"] = end

    def _note_progress_event(self, data: dict) -> None:
        state = getattr(self, "_ksampler_state", None)
        if not state:
            return
        node = str(data.get("node", ""))
        if node != str(state.get("node")):
            return
        now = time.time()
        if state["first_progress"] is None:
            state["first_progress"] = now
        state["last_progress"] = now
        state["progress_events"] += 1
        state["max_step"] = max(state["max_step"], int(data.get("step", 0)))
        state["max_steps"] = max(state["max_steps"], int(data.get("max", 0)))

    def _finish_profiled_node(self, now: float) -> None:
        last_node = getattr(self, "_perf_last_node", None)
        last_ts = getattr(self, "_perf_last_ts", None)
        if last_node is None or last_ts is None:
            return
        class_type = self._node_class_type(last_node)
        duration_ms = round((now - last_ts) * 1000, 1)
        # Trace: close the matching t<N>_end timestamp for this stage.
        stage = self._stage_for_class(class_type)
        windows = getattr(self, "_stage_windows", None)
        if stage and windows and stage != "sampler" and "start" in windows[stage] and "end" not in windows[stage]:
            windows[stage]["end"] = now
            windows[stage]["end_node"] = last_node

        sampler_phase = None
        state = getattr(self, "_ksampler_state", None)
        if stage == "sampler" and state and str(state.get("node")) == str(last_node):
            first = state.get("first_progress")
            last = state.get("last_progress")
            if first is None:
                prep_ms = duration_ms
                denoise_ms = 0.0
                teardown_ms = 0.0
            else:
                prep_ms = round(max(0.0, (first - state["started"]) * 1000), 1)
                denoise_ms = round(max(0.0, ((last or first) - first) * 1000), 1)
                teardown_ms = round(max(0.0, duration_ms - prep_ms - denoise_ms), 1)
            if windows and stage in windows:
                # Prefer the sampler node that actually emitted progress callbacks.
                # This avoids latching onto earlier light-weight sampler-like
                # nodes that finish instantly but still match the class-name heuristic.
                if first is not None:
                    windows[stage]["node_start"] = state["started"]
                    windows[stage]["start"] = first
                    windows[stage]["end"] = last or first
                    windows[stage]["progress_start"] = first
                    windows[stage]["progress_end"] = last or first
                    windows[stage]["progress_events"] = state.get("progress_events", 0)
                    windows[stage]["max_step"] = state.get("max_step", 0)
                    windows[stage]["max_steps"] = state.get("max_steps", 0)
                    windows[stage]["duration_ms"] = duration_ms
                    windows[stage]["source"] = "progress"
                else:
                    previous_duration = float(windows[stage].get("duration_ms", -1.0))
                    if duration_ms > previous_duration:
                        windows[stage]["start"] = state["started"]
                        windows[stage]["end"] = now
                        windows[stage]["duration_ms"] = duration_ms
                        windows[stage]["source"] = "node_duration"
            sampler_phase = {
                "prep_ms": prep_ms,
                "denoise_ms": denoise_ms,
                "teardown_ms": teardown_ms,
                "progress_events": state.get("progress_events", 0),
                "max_step": state.get("max_step", 0),
                "max_steps": state.get("max_steps", 0),
                "duration_ms": duration_ms,
            }
            self._ksampler_state = None

        if not PROFILING_ENABLED:
            return
        print(f"[comfyapp.perf] node={last_node} class_type={class_type} duration_ms={duration_ms:.1f}")

        if sampler_phase is not None:
            self._log_profile(
                "ksampler_phase",
                node=str(last_node)[:40],
                class_type=class_type[:80],
                prep_ms=sampler_phase["prep_ms"],
                denoise_ms=sampler_phase["denoise_ms"],
                teardown_ms=sampler_phase["teardown_ms"],
                progress_events=sampler_phase["progress_events"],
                max_step=sampler_phase["max_step"],
                max_steps=sampler_phase["max_steps"],
                duration_ms=sampler_phase["duration_ms"],
            )

    def _patch_model_clone_profiling(self, model_patcher_module) -> None:
        if getattr(self, "_model_clone_profile_patched", False):
            return

        for method_name in ("clone", "patch_model", "unpatch_model"):
            original = getattr(model_patcher_module.ModelPatcher, method_name, None)
            if not callable(original):
                continue

            def _wrapped(patcher, *args, __orig=original, __name=method_name, **kwargs):
                started = time.time()
                result = __orig(patcher, *args, **kwargs)
                model_obj = getattr(patcher, "model", None)
                self._log_profile(
                    "model_clone",
                    call=__name,
                    patcher=type(patcher).__name__,
                    model=type(model_obj).__name__[:80],
                    duration_ms=self._profile_ms(started),
                )
                return result

            setattr(model_patcher_module.ModelPatcher, method_name, _wrapped)

        self._model_clone_profile_patched = True

    def _loaded_model_names(self, model_management_module) -> list[str]:
        names: list[str] = []
        loaded = getattr(model_management_module, "current_loaded_models", None)
        if not isinstance(loaded, list):
            loaded = getattr(model_management_module, "loaded_models", None)
        if not isinstance(loaded, list):
            return names
        for entry in loaded:
            candidate = entry
            model_obj = getattr(candidate, "model", None)
            if model_obj is not None:
                names.append(type(model_obj).__name__[:80])
                continue
            model = getattr(candidate, "model_patcher", None)
            model_obj = getattr(model, "model", None)
            if model_obj is not None:
                names.append(type(model_obj).__name__[:80])
                continue
            names.append(type(candidate).__name__[:80])
        names.sort()
        return names

    def _gpu_mem_profile(self):
        alloc_gb = reserved_gb = None
        try:
            import torch
            if torch.cuda.is_available():
                alloc_gb = round(torch.cuda.memory_allocated() / (1024 ** 3), 3)
                reserved_gb = round(torch.cuda.memory_reserved() / (1024 ** 3), 3)
        except Exception:
            pass
        return alloc_gb, reserved_gb

    def _patch_model_management_profiling(self, model_management_module) -> None:
        if getattr(self, "_model_management_profile_patched", False):
            return

        for func_name in ("load_models_gpu", "load_model_gpu", "cleanup_models_gc", "soft_empty_cache", "free_memory"):
            original = getattr(model_management_module, func_name, None)
            if not callable(original):
                continue

            def _wrapped(*args, __orig=original, __name=func_name, **kwargs):
                loaded_before = self._loaded_model_names(model_management_module)
                alloc_before_gb, reserved_before_gb = self._gpu_mem_profile()
                vram_state_before = getattr(model_management_module, "vram_state", None)
                disable_smart_memory = getattr(model_management_module, "DISABLE_SMART_MEMORY", None)
                started = time.time()
                result = __orig(*args, **kwargs)
                loaded_after = self._loaded_model_names(model_management_module)
                alloc_after_gb, reserved_after_gb = self._gpu_mem_profile()
                vram_state_after = getattr(model_management_module, "vram_state", None)
                model_count = "?"
                if args:
                    first = args[0]
                    if isinstance(first, (list, tuple, set)):
                        model_count = len(first)
                    elif first is not None:
                        model_count = 1
                self._log_profile(
                    "model_mgmt",
                    call=__name,
                    models=model_count,
                    loaded_count_before=len(loaded_before),
                    loaded_count_after=len(loaded_after),
                    loaded_before=json.dumps(loaded_before, separators=(",", ":")),
                    loaded_after=json.dumps(loaded_after, separators=(",", ":")),
                    alloc_before_gb=alloc_before_gb if alloc_before_gb is not None else "?",
                    alloc_after_gb=alloc_after_gb if alloc_after_gb is not None else "?",
                    reserved_before_gb=reserved_before_gb if reserved_before_gb is not None else "?",
                    reserved_after_gb=reserved_after_gb if reserved_after_gb is not None else "?",
                    vram_state_before=vram_state_before if vram_state_before is not None else "?",
                    vram_state_after=vram_state_after if vram_state_after is not None else "?",
                    disable_smart_memory=disable_smart_memory if disable_smart_memory is not None else "?",
                    duration_ms=self._profile_ms(started),
                )
                return result

            setattr(model_management_module, func_name, _wrapped)

        self._model_management_profile_patched = True

    def _patch_offload_devices_for_high_vram(self, model_management_module) -> None:
        """When vram_state is HIGH_VRAM, keep text encoders, VAE, and
        intermediate tensors on GPU instead of offloading to CPU.

        ComfyUI's ``unet_offload_device()`` already respects HIGH_VRAM,
        but ``text_encoder_offload_device()``, ``vae_offload_device()`` and
        ``intermediate_device()`` only check ``args.gpu_only``.  This patch
        makes them consistent so that HIGH_VRAM truly means "keep everything
        on GPU when possible".
        """
        if getattr(self, "_offload_devices_patched", False):
            return
        mm = model_management_module
        torch_dev = mm.get_torch_device()
        high_vram = mm.VRAMState.HIGH_VRAM

        for func_name in ("text_encoder_offload_device", "vae_offload_device", "intermediate_device"):
            original = getattr(mm, func_name, None)
            if not callable(original):
                continue

            def _wrapper(*args, __orig=original, **kwargs):
                if getattr(mm, "vram_state", None) == high_vram:
                    return torch_dev
                return __orig(*args, **kwargs)

            setattr(mm, func_name, _wrapper)

        self._offload_devices_patched = True

    def _enable_torch_compile_on_unet(self) -> None:
        """Apply ``torch.compile`` directly to ``diffusion_model._forward``
        on any loaded diffusion model.

        Unlike the old approach (``set_torch_compile_wrapper`` which hooked into
        ``APPLY_MODEL`` wrappers with ``fullgraph=True``), this compiles the
        inner ``_forward`` method of the Flux/UNET module directly.  This avoids:

        - Graph breaks from ``WrapperExecutor`` dispatch in Flux's ``forward()``
        - Wrapper overhead on every denoising step
        - ``fullgraph=True`` raising on Python-level control flow

        Enabled by ``COMFYMODAL_ENABLE_TORCH_COMPILE=1`` env var.
        """
        if not ENABLE_TORCH_COMPILE:
            return
        if getattr(self, "_torch_compile_enabled", False):
            return
        import comfy.model_management as _mm
        import torch

        # torch.compile is disabled on this branch.  It triggers
        # "invalid argument to getCurrentStream" CUDA errors during Dynamo
        # tracing in the post-restore CUDA context — a known interaction
        # between torch.compile and Modal's memory snapshot infrastructure.
        # SageAttention's pre-compiled CUDA/Blackwell kernels already provide
        # optimal performance; torch.compile adds overhead without benefit.
        if not ENABLE_TORCH_COMPILE:
            return

    def _compute_workflow_struct_hash(self, workflow: dict) -> str:
        import hashlib
        _mutable_keys = {"seed", "text", "width", "height", "batch_size"}
        stripped = {}
        for _nid, _spec in workflow.items():
            if not isinstance(_spec, dict):
                continue
            _inp = dict(_spec.get("inputs", {}))
            for _k in _mutable_keys:
                _inp.pop(_k, None)
            stripped[_nid] = {"class_type": _spec.get("class_type"), "inputs": _inp}
        return hashlib.md5(json.dumps(stripped, sort_keys=True).encode()).hexdigest()[:16]

    def _execute_in_process(self, workflow: dict, input_images: dict | None = None, collect_outputs: bool = True, trace: Trace | None = None) -> dict:
        """Execute a ComfyUI workflow directly in-process.

        Args:
            workflow: ComfyUI workflow (dict of node-id → node-spec).
            input_images: Optional mapping of filename → base64-encoded data.
            collect_outputs: When False, skip output collection (warmup mode).
            trace: Optional Trace to populate with timing markers.

        Returns:
            ``{"images": [...], "videos": [...]}`` where each entry contains
            ``filename``, ``data`` (base64), and ``node_id``.
        """
        # Enable torch.compile on UNET models if configured.
        # Patches load_models_gpu so any diffusion model loaded during this
        # execution (or any subsequent one) gets compiled via ComfyUI's
        # set_torch_compile_wrapper.  The compile triggers lazily on the
        # first forward pass during the denoising loop.
        self._enable_torch_compile_on_unet()

        import base64
        import execution
        from pathlib import Path

        prompt_id = str(uuid.uuid4())
        prompt_start_time: float | None = None

        # ── Write input images to ComfyUI's input directory ──
        stage_started = time.time()
        if input_images:
            inp = Path("/root/comfy/ComfyUI/input")
            inp.mkdir(parents=True, exist_ok=True)
            for fname, b64 in input_images.items():
                (inp / Path(fname).name).write_bytes(base64.b64decode(b64))
        self._log_profile("inproc_input_prepare", prompt_id=prompt_id[:8], count=len(input_images or {}), duration_ms=self._profile_ms(stage_started))

        # Start the execution window after source-image uploads land on
        # disk so the fallback output scan does not echo them back as
        # generated outputs.
        prompt_start_time = time.time()

        # ── Fixed-workflow fast path: skip validation if hash matches ──
        _wf_hash = self._compute_workflow_struct_hash(workflow)
        _wf_cache_key = f"wf_exec:{_wf_hash}"
        _wf_cache = getattr(self, "_workflow_exec_cache", {})
        _cached = _wf_cache.get(_wf_cache_key) if collect_outputs else None
        stage_started = time.time()
        if _cached is not None and collect_outputs:
            outputs_to_execute, node_errors = _cached
            valid = True
            error = {}
            _validate_ms = self._profile_ms(stage_started)
            self._log_profile("inproc_validate_cached", prompt_id=prompt_id[:8], hash=_wf_hash, duration_ms=_validate_ms)
        elif not collect_outputs:
            # Warmup-only mode: skip output validation since warmup workflows
            # may have no output consumers (e.g. UNETLoader + DualCLIPLoader).
            # Treat all workflow nodes as outputs to execute.
            outputs_to_execute = list(workflow.keys())
            self._log_profile("inproc_validate_skip", prompt_id=prompt_id[:8], outputs=len(outputs_to_execute), duration_ms=self._profile_ms(stage_started))
            valid = True
            node_errors = {}
            error = {}
        else:
            valid, error, outputs_to_execute, node_errors = self._event_loop.run_until_complete(
                execution.validate_prompt(prompt_id, workflow, None)
            )
            _validate_ms = self._profile_ms(stage_started)
            self._log_profile("inproc_validate", prompt_id=prompt_id[:8], valid=1 if valid else 0, outputs=len(outputs_to_execute or []), duration_ms=_validate_ms)
            # Cache for future requests with same structure
            if valid and outputs_to_execute:
                if not hasattr(self, '_workflow_exec_cache'):
                    self._workflow_exec_cache = {}
                self._workflow_exec_cache[_wf_cache_key] = (outputs_to_execute, node_errors)
        self._last_graph_validate_ms = self._profile_ms(stage_started)
        if trace is not None:
            trace.mark("t3b_validate_done")
        if not valid:
            parts = [error.get("message", str(error)) if isinstance(error, dict) else str(error)]
            if node_errors:
                for nid, info in node_errors.items():
                    ct = info.get("class_type", f"Node {nid}")
                    for e in info.get("errors", []):
                        parts.append(f"{ct}: {e.get('message', 'unknown error')}")
            raise RuntimeError(f"Workflow validation failed: {'; '.join(parts)}")

        self._begin_prompt_profile(workflow, prompt_id, outputs_to_execute)

        # ── Reset execution-level accumulators ──
        self._exec_model_load_io_ms = 0.0
        self._exec_deepcopy_ms = 0.0
        self._log_profile("inproc_prep_done", prompt_id=prompt_id[:8], duration_ms=self._profile_ms(stage_started))
        if trace is not None:
            trace.mark("t3c_prep_done")
        _exec_stage = time.time()

        # ── Instrument executor for overhead breakdown ──
        import execution as _exec_mod
        _perf_data = {}
        _exec_profiling = _resolve_exec_profile()
        if _exec_profiling and not getattr(_exec_mod, '_comfy_modal_exec_patched', False):
            _orig_exec_fn = _exec_mod.execute
            _exec_prof_data = {"nodes": {}, "_first_call_start": None, "_last_call_end": None, "_call_count": 0}
            async def _profiled_exec(*args, **kwargs):
                _t0 = time.perf_counter()
                if _exec_prof_data["_first_call_start"] is None:
                    _exec_prof_data["_first_call_start"] = _t0
                try:
                    return await _orig_exec_fn(*args, **kwargs)
                finally:
                    _t1 = time.perf_counter()
                    _exec_prof_data["_last_call_end"] = _t1
                    _exec_prof_data["_call_count"] += 1
                    _node_id = kwargs.get('current_item') or (args[3] if len(args) > 3 else None)
                    _ct = "?"
                    try:
                        _dyn = kwargs.get('dynprompt') or (args[1] if len(args) > 1 else None)
                        if _dyn and _node_id is not None:
                            _n = _dyn.get_node(str(_node_id))
                            if _n:
                                _ct = _n.get('class_type', '?')
                    except Exception:
                        pass
                    _duration_ms = (_t1 - _t0) * 1000
                    _nodes = _exec_prof_data["nodes"]
                    if _ct not in _nodes:
                        _nodes[_ct] = {"ms": 0.0, "count": 0}
                    _nodes[_ct]["ms"] += _duration_ms
                    _nodes[_ct]["count"] += 1
            _exec_mod.execute = _profiled_exec
            _exec_mod._comfy_modal_exec_patched = True
            _exec_mod._comfy_modal_exec_prof = _exec_prof_data

        # ── Instrument sampler for per-step breakdown ──
        _sampler_profiling = _resolve_sampler_profile()
        if _sampler_profiling:
            import comfy.samplers as _samplers_mod
            if not getattr(_samplers_mod, '_comfy_modal_sampler_prof_patched', False):
                _orig_ksampler_sample = _samplers_mod.KSAMPLER.sample
                _sampler_prof_data = {}
                def _profiled_ksampler_sample(self, model_wrap, sigmas, extra_args, callback, noise, latent_image=None, denoise_mask=None, disable_pbar=False):
                    _t0 = time.perf_counter()
                    _times = {}
                    _last_cb_time = None
                    _step_count = 0
                    if callback is not None:
                        _orig_cb = callback
                        def _ts_cb(step_idx, denoised, x, total_steps):
                            nonlocal _last_cb_time, _step_count
                            _now = time.perf_counter()
                            if _last_cb_time is None:
                                _times["setup_ms"] = (_now - _t0) * 1000
                            else:
                                _step_count += 1
                                _times[f"step_{_step_count}_ms"] = (_now - _last_cb_time) * 1000
                            _last_cb_time = _now
                            return _orig_cb(step_idx, denoised, x, total_steps)
                        callback = _ts_cb
                    result = _orig_ksampler_sample(self, model_wrap, sigmas, extra_args, callback, noise, latent_image, denoise_mask, disable_pbar)
                    _t1 = time.perf_counter()
                    if _last_cb_time is not None:
                        _times["teardown_ms"] = (_t1 - _last_cb_time) * 1000
                    _times["total_ms"] = (_t1 - _t0) * 1000
                    _sampler_prof_data.update(_times)
                    return result
                _samplers_mod.KSAMPLER.sample = _profiled_ksampler_sample
                _samplers_mod._comfy_modal_sampler_prof_patched = True
                _samplers_mod._comfy_modal_sampler_prof = _sampler_prof_data

        # ── Instrument guider for overhead breakdown ──
        _guider_profiling = _resolve_guider_profile()
        if _guider_profiling:
            import comfy.samplers as _gs_mod
            import comfy.sampler_helpers as _gsh_mod
            if not getattr(_gs_mod, '_comfy_modal_guider_prof_patched', False):
                _guider_prof_data = {"segments": {}}
                def _gwrap(label):
                    def _deco(orig_fn):
                        def _wrapper(*args, **kwargs):
                            _t0 = time.perf_counter()
                            try:
                                return orig_fn(*args, **kwargs)
                            finally:
                                _d = (time.perf_counter() - _t0) * 1000
                                segs = _guider_prof_data["segments"]
                                segs[label] = segs.get(label, 0.0) + _d
                        return _wrapper
                    return _deco
                _gs_mod.CFGGuider.sample = _gwrap("guider_sample")(_gs_mod.CFGGuider.sample)
                _gs_mod.CFGGuider.outer_sample = _gwrap("guider_outer_sample")(_gs_mod.CFGGuider.outer_sample)
                _gs_mod.CFGGuider.inner_sample = _gwrap("guider_inner_sample")(_gs_mod.CFGGuider.inner_sample)
                _gsh_mod.prepare_sampling = _gwrap("prepare_sampling")(_gsh_mod.prepare_sampling)
                _gsh_mod.cleanup_models = _gwrap("cleanup_models")(_gsh_mod.cleanup_models)
                _gs_mod._comfy_modal_guider_prof_patched = True
                _gs_mod._comfy_modal_guider_prof = _guider_prof_data

        # ── Deep sampler wrapper profiling ──
        _deep_profiling = _resolve_deep_profile()
        if _deep_profiling:
            import comfy.sampler_helpers as _dsh_mod
            import comfy.model_management as _dmm_mod
            import comfy_extras.nodes_custom_sampler as _dcs_mod
            _deep_prof = {}
            def _dp_wrap(module, name, label):
                orig = getattr(module, name, None)
                if orig is None:
                    return
                def _dp(*args, **kwargs):
                    _t0 = time.perf_counter()
                    try:
                        return orig(*args, **kwargs)
                    finally:
                        _deep_prof[label] = _deep_prof.get(label, 0) + (time.perf_counter() - _t0) * 1000
                setattr(module, name, _dp)
            _dp_wrap(_dsh_mod, 'get_additional_models', 'ps_get_additional_models')
            _dp_wrap(_dsh_mod, 'get_additional_models_from_model_options', 'ps_get_additional_models_opts')
            _dp_wrap(_dsh_mod, 'estimate_memory', 'ps_estimate_memory')
            # ── Comprehensive load_models_gpu profiler + fastpath diagnostics ──
            _fp_dryrun = _resolve_lmg_fastpath_dryrun()
            _fp_enabled = _resolve_lmg_fastpath()
            _orig_lmg = _dmm_mod.load_models_gpu
            _lmg_calls = []
            def _profiled_lmg(models, memory_required=0, force_patch_weights=False, minimum_memory_required=None, force_full_load=False):
                _classes = [m.model.__class__.__name__ for m in models if hasattr(m, 'model')]
                _lm_models = list(getattr(_dmm_mod, 'current_loaded_models', []))
                _loaded_before = len(_lm_models)
                # Identity diagnostics for each requested model
                _diag = []
                _matched_idx = None
                _model_patcher = models[0] if models else None
                for mi, m in enumerate(models):
                    _md = {
                        "class": m.model.__class__.__name__ if hasattr(m, 'model') else '?',
                        "patcher_id": id(m) if hasattr(m, 'model') else 0,
                        "model_id": id(m.model) if hasattr(m, 'model') else 0,
                        "matched_idx": -1,
                        "same_patcher": False,
                    }
                    for li, lm in enumerate(_lm_models):
                        _lm_p = lm.model if hasattr(lm, 'model') else None
                        if _lm_p is not None and _lm_p is m:
                            _md["matched_idx"] = li
                            _md["same_patcher"] = True
                            _matched_idx = li
                            break
                    _diag.append(_md)
                # Fastpath decision
                _would_fastpath = _matched_idx is not None and len(models) == 1
                _fp_reject = "none" if _would_fastpath else ("no_identity_match" if _matched_idx is None else "multiple_models")
                _vram_ok = getattr(_dmm_mod, 'vram_state', None) == _dmm_mod.VRAMState.HIGH_VRAM
                # ── Guarded fast path execution ──
                if _fp_enabled and _would_fastpath and _vram_ok:
                    _t0 = time.perf_counter()
                    _lm = _lm_models[_matched_idx]
                    _lm.currently_used = True
                    _t1 = time.perf_counter()
                    _call_data = {
                        "ms": round((_t1 - _t0) * 1000, 1),
                        "models": _classes,
                        "count": len(models),
                        "loaded_before": _loaded_before,
                        "loaded_after": len(getattr(_dmm_mod, 'current_loaded_models', [])),
                        "identity": _diag,
                        "fastpath_hit": True,
                        "fastpath_saved_ms": 0,
                    }
                    _lmg_calls.append(_call_data)
                    _deep_prof["lmg"] = list(_lmg_calls)
                    return
                else:
                    _t0 = time.perf_counter()
                    try:
                        return _orig_lmg(models, memory_required, force_patch_weights, minimum_memory_required, force_full_load)
                    finally:
                        _t1 = time.perf_counter()
                        _call_data = {
                            "ms": round((_t1 - _t0) * 1000, 1),
                            "models": _classes,
                            "count": len(models),
                            "loaded_before": _loaded_before,
                            "loaded_after": len(getattr(_dmm_mod, 'current_loaded_models', [])),
                            "identity": _diag,
                            "would_fastpath": _would_fastpath,
                            "fp_reject": _fp_reject if not _would_fastpath else ("not_high_vram" if not _vram_ok else "none"),
                            "fastpath_hit": False,
                        }
                        _lmg_calls.append(_call_data)
                        _deep_prof["lmg"] = list(_lmg_calls)
            _dmm_mod.load_models_gpu = _profiled_lmg
            # ── Warmup registration logging ──
            _warmup_lm = list(getattr(_dmm_mod, 'current_loaded_models', []))
            _deep_prof["warmup"] = {
                "registered_count": len(_warmup_lm),
                "entries": [{
                    "class": lm.model.__class__.__name__ if hasattr(lm, 'model') else '?',
                    "actual_model": lm.model.model.__class__.__name__ if hasattr(lm, 'model') and hasattr(lm.model, 'model') else '?',
                    "actual_model_id": id(lm.model.model) if hasattr(lm, 'model') and hasattr(lm.model, 'model') else 0,
                    "patcher_id": id(lm) if hasattr(lm, 'model') else 0,
                } for lm in _warmup_lm],
            }
            # KSAMPLER.sample setup proved ~0.35ms — no further breakdown needed
            import comfy as _comfy_mod
            _comfy_mod._comfy_modal_deep_prof = _deep_prof

        # ── Execute ──
        stage_started = time.time()
        self._executor.execute(
            prompt=workflow,
            prompt_id=prompt_id,
            extra_data={"client_id": prompt_id},
            execute_outputs=outputs_to_execute,
        )
        total_exec_ms = self._profile_ms(stage_started)
        _deepcopy_total = getattr(self, "_exec_deepcopy_ms", 0.0)
        self._log_profile(
            "inproc_execute", prompt_id=prompt_id[:8],
            duration_ms=total_exec_ms,
            load_io_ms=round(self._exec_model_load_io_ms, 1),
            deepcopy_ms=round(_deepcopy_total, 1),
            non_io_exec_ms=round(max(0.0, total_exec_ms - self._exec_model_load_io_ms - _deepcopy_total), 1),
            success=1 if getattr(self._executor, "success", True) else 0,
        )
        # Commit t4..t7 stage windows from the node events to the trace.
        if trace is not None:
            self._commit_stage_windows_to_trace(trace)
        # t8 — final image was written by SaveImage.  The actual file
        # mtime is a more truthful marker than "executor returned" so we
        # query the youngest png/jpg in the output directory that
        # appeared during this prompt's window.
        if trace is not None and collect_outputs:
            try:
                from pathlib import Path as _P
                out_dir = _P("/root/comfy/ComfyUI/output")
                if out_dir.is_dir():
                    candidates = []
                    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"):
                        for f in out_dir.glob(f"*{ext}"):
                            try:
                                mt = f.stat().st_mtime
                            except OSError:
                                continue
                            if mt >= prompt_start_time - 1.0:
                                candidates.append((mt, f))
                    if candidates:
                        latest_mt = max(c[0] for c in candidates)
                        trace.mark("t8_image_written", t=latest_mt)
            except Exception as exc:
                print(f"[comfyapp] trace t8 lookup failed: {exc}")
        if getattr(self._executor, "success", True) is False:
            messages = getattr(self._executor, "status_messages", [])
            error_messages = []
            for event, payload in messages:
                if event == "execution_error" and isinstance(payload, dict):
                    error_messages.append(payload.get("exception_message", str(payload)))
            detail = "; ".join(error_messages) if error_messages else "ComfyUI execution failed"
            raise RuntimeError(detail)

        if not collect_outputs:
            # Store executor timing breakdown for warmup analysis
            self._warmup_exec_timing = {
                "we_load_io_ms": round(self._exec_model_load_io_ms, 1),
                "we_deepcopy_ms": round(_deepcopy_total, 1),
                "we_non_io_ms": round(max(0.0, total_exec_ms - self._exec_model_load_io_ms - _deepcopy_total), 1),
            }
            return {"images": [], "videos": []}
        stage_started = time.time()
        result = self._collect_in_process_outputs(prompt_id, prompt_start_time=prompt_start_time)
        self._log_profile("inproc_collect", prompt_id=prompt_id[:8], images=len(result.get("images", [])), videos=len(result.get("videos", [])), duration_ms=self._profile_ms(stage_started))
        if trace is not None:
            trace.mark("t8b_outputs_collected")
        return result

    def _collect_in_process_outputs(self, prompt_id: str, prompt_start_time: float | None = None) -> dict:
        """Read generated outputs after an in-process execution.

        Tries four sources, in priority order, returning the union:

        1. ``self._executor.history_result`` — set by ``PromptExecutor.execute()``
           when the last execution populated it.
        2. ``self._dummy_server.prompt_queue.history[prompt_id]`` — populated
           by the PromptQueue (typically empty for direct executor calls).
        3. **Directory scan scoped to the prompt's execution window** —
           finds any image/video file written to ComfyUI's ``output``,
           ``temp``, or ``input`` directory *after* ``prompt_start_time``.
           This catches every file the workflow actually wrote regardless
           of whether history metadata is structured as expected.
        4. **Directory scan of the most-recent 20 files** — last-resort
           fallback when no ``prompt_start_time`` is available (e.g. older
           callers).

        Each image/video entry is ``{"filename", "data" (base64), "node_id"}``.

        The ``type`` field on image metadata is honoured: ``output`` is
        looked up under ``ComfyUI/output``, ``temp`` under ``ComfyUI/temp``,
        ``input`` under ``ComfyUI/input``.  The supplemental directory-scan
        path only walks ``output`` and ``temp`` so uploaded source images do
        not get returned as generated outputs.
        """
        import base64
        from pathlib import Path

        images: list[dict] = []
        videos: list[dict] = []
        seen_filenames: set[str] = set()  # de-dupe across sources

        comfy_root = Path("/root/comfy/ComfyUI")
        dir_for_type = {
            "output": comfy_root / "output",
            "temp": comfy_root / "temp",
            "input": comfy_root / "input",
        }

        def _try_read_file(fp: Path, node_id: str, animated: bool) -> None:
            """Read a single file and append to images/videos if successful."""
            if not fp.is_file():
                return
            key = str(fp)
            if key in seen_filenames:
                return
            seen_filenames.add(key)
            _r_start = time.time()
            raw = fp.read_bytes()
            _r_ms = round((time.time() - _r_start) * 1000, 1)
            if _r_ms > 100:
                print(f"[comfyapp] slow output read: file={fp.name} size={len(raw)} duration_ms={_r_ms}")
            entry = {"filename": fp.name, "data": base64.b64encode(raw).decode(), "node_id": node_id}
            if animated or fp.suffix.lower() in (".gif", ".mp4", ".webm", ".webp"):
                videos.append(entry)
            else:
                images.append(entry)

        def _scan_dir_for_files(base: Path, since_ts: float | None, limit: int = 20) -> None:
            """Scan a base directory for image/video files, optionally
            filtered to ``mtime >= since_ts``.  Adds to images/videos via
            ``_try_read_file``."""
            if not base.is_dir():
                return
            candidates: list[Path] = []
            for f in base.iterdir():
                if not f.is_file():
                    continue
                if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"):
                    continue
                if since_ts is not None:
                    try:
                        if f.stat().st_mtime < since_ts - 1.0:  # 1s slack for clock drift
                            continue
                    except OSError:
                        continue
                candidates.append(f)
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for f in candidates[:limit]:
                _try_read_file(f, node_id="0", animated=f.suffix.lower() in (".gif", ".mp4", ".webm"))

        # ── Source 1: executor.history_result ─────────────────────────
        outputs: dict = {}
        try:
            history_result = getattr(self._executor, "history_result", None)
            if isinstance(history_result, dict):
                outputs = history_result.get("outputs", {}) or {}
        except Exception as exc:
            print(f"[comfyapp] executor.history_result read failed: {exc}")
        if outputs:
            for node_id, node_out in outputs.items():
                if not isinstance(node_out, dict):
                    continue
                for img in node_out.get("images", []):
                    if not isinstance(img, dict):
                        continue
                    base = dir_for_type.get(img.get("type", "output"), comfy_root / "output")
                    sub = img.get("subfolder", "") or ""
                    fp = base / sub / img.get("filename", "")
                    if not fp.is_file():
                        print(f"[comfyapp] history-listed file not found: {fp}")
                    animated = bool(node_out.get("animated", False))
                    _try_read_file(fp, node_id=node_id, animated=animated)
                for vid in node_out.get("gifs", []):
                    if not isinstance(vid, dict):
                        continue
                    base = dir_for_type.get(vid.get("type", "output"), comfy_root / "output")
                    sub = vid.get("subfolder", "") or ""
                    fp = base / sub / vid.get("filename", "")
                    animated = True
                    _try_read_file(fp, node_id=node_id, animated=animated)

        # ── Source 2: dummy_server.prompt_queue.history[prompt_id] ───
        if not seen_filenames:
            try:
                history = self._dummy_server.prompt_queue.history
                if isinstance(history, dict) and prompt_id in history:
                    queue_outputs = history[prompt_id].get("outputs", {}) or {}
                    if queue_outputs:
                        for node_id, node_out in queue_outputs.items():
                            if not isinstance(node_out, dict):
                                continue
                            for img in node_out.get("images", []):
                                if not isinstance(img, dict):
                                    continue
                                base = dir_for_type.get(img.get("type", "output"), comfy_root / "output")
                                sub = img.get("subfolder", "") or ""
                                fp = base / sub / img.get("filename", "")
                                animated = bool(node_out.get("animated", False))
                                _try_read_file(fp, node_id=node_id, animated=animated)
            except Exception as exc:
                print(f"[comfyapp] prompt_queue.history read failed: {exc}")

        # ── Source 3: directory scan scoped to the prompt's time window ─
        # Always run as a supplement — catches files the workflow wrote
        # that the executor didn't return in its history metadata.
        if prompt_start_time is not None:
            for base in (comfy_root / "output", comfy_root / "temp"):
                _scan_dir_for_files(base, since_ts=prompt_start_time)

        # ── Source 4: most-recent-files fallback ──────────────────────
        if not seen_filenames and prompt_start_time is None:
            print("[comfyapp] output history not found, scanning output directory")
            _scan_dir_for_files(comfy_root / "output", since_ts=None)

        if not seen_filenames:
            print(
                f"[comfyapp] no outputs found for prompt_id={prompt_id[:8]} "
                f"(history_result_empty={not bool(outputs)} "
                f"prompt_start_time={'set' if prompt_start_time else 'none'})"
            )
        print(f"[comfyapp] collected {len(images)} images, {len(videos)} videos")
        return {"images": images, "videos": videos}

    def _select_backend(self) -> str:
        """Return the backend to use, sticky on subprocess fallback."""
        if getattr(self, "_backend_fallback", False):
            return "subprocess"
        return DEFAULT_EXECUTION_BACKEND

    @contextlib.contextmanager
    def _force_cpu_during_snapshot(self):
        """Lie to PyTorch about CUDA availability during snap=True.

        Modal's GPU memory snapshot captures the parent's CUDA driver state
        (context handles, streams, events) along with the Python state.
        On restore the driver context is fresh — the captured handles are
        dangling pointers → SIGSEGV (exit code 139) the first time the
        restored process touches a CUDA tensor.

        Workaround: monkey-patch ``torch.cuda.is_available()`` and
        ``torch.cuda.current_device()`` to lie about CUDA during snap=True
        so ComfyUI's ``model_management`` thinks there is no GPU and skips
        all CUDA initialisation.  The snapshot then captures a CPU-only
        Python state (imported modules, registered nodes, PromptExecutor,
        DummyServer, etc.) with zero CUDA driver state.

        On restore, ``_warmup_cuda()`` reconnects the real GPU; the first
        ``executor.execute()`` allocates fresh CUDA tensors.

        Additionally, this context manager blocks imports of CUDA C
        extension modules (``sageattn_qk_int8_pv_fp16_cuda``,
        ``sageattn_qk_int8_pv_fp8_cuda``, and any other module matching
        the ``*_cuda`` / ``cuda_*`` pattern).  These C extensions'
        ``PyInit_*`` functions call CUDA APIs directly (bypassing the
        ``torch.cuda.is_available()`` patch) and allocate GPU memory
        during module load — which would land in the snapshot and
        trigger SIGSEGV on restore.  The block makes any custom node
        that imports sageattention fall back to Triton mode for the
        duration of the snapshot; restore later selects a baked runtime
        mode after CUDA is available again.

        This is the technique used by tolgaouz/modal-comfy-worker for the
        "ComfyUI Cold Starts Down to Under 3 Seconds on Modal" example.
        The patch is removed in the ``finally`` block, so the snapshot
        does **not** contain the monkey-patched functions.
        """
        import sys
        import warnings
        import torch

        comfy_path = "/root/comfy/ComfyUI"
        if comfy_path not in sys.path:
            sys.path.insert(0, comfy_path)
        import comfy.cli_args

        # ── Monkey-patch torch.cuda query functions ──
        # The first access to torch.cuda triggers its __init__.py which calls
        # _check_driver() — this detects the real GPU and emits a noisy
        # "compute capability (CC) 12.0 is unsupported" warning.  During
        # snap=True we deliberately hide the GPU; suppress the warning at
        # the import point.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            original_is_available = torch.cuda.is_available
            original_current_device = torch.cuda.current_device
        original_args_cpu = getattr(comfy.cli_args.args, "cpu", False)
        torch.cuda.is_available = lambda: False
        torch.cuda.current_device = lambda: torch.device("cpu")
        # ComfyUI's model_management defaults cpu_state=GPU at import time
        # unless CLI args explicitly force CPU mode. During snap=True we
        # must also lie at the ComfyUI argument layer so its import-time
        # feature probes don't touch CUDA.
        comfy.cli_args.args.cpu = True

        # ── Block CUDA C extension imports during snapshot creation ─────
        # The C extension's PyInit_* runs CUDA driver calls (cudaGetDevice,
        # cudaMalloc, …) that bypass torch.cuda.is_available and create
        # state in the captured snapshot.  Raising ImportError makes
        # sageattention's __init__.py fall back to its Triton path.
        class _BlockCudaModuleImport:
            def find_spec(self, name, path=None, target=None):
                if self._is_cuda_module(name):
                    raise ImportError(
                        f"[comfyapp] blocked CUDA module import "
                        f"{name!r} during snap=True to keep snapshot clean"
                    )
                return None

            def find_module(self, name, path=None):
                if self._is_cuda_module(name):
                    return self
                return None

            def load_module(self, name):
                raise ImportError(
                    f"[comfyapp] blocked CUDA module import "
                    f"{name!r} during snap=True to keep snapshot clean"
                )

            @staticmethod
            def _is_cuda_module(name: str) -> bool:
                # Matches:
                #   sageattn_qk_int8_pv_fp16_cuda
                #   sageattn_qk_int8_pv_fp8_cuda
                #   comfy_*/cuda_*
                #   *_cuda
                #   cuda_*
                return (
                    name.endswith("_cuda")
                    or name.startswith("cuda_")
                    or "_cuda_" in name
                )

        blocker = _BlockCudaModuleImport()
        sys.meta_path.insert(0, blocker)

        try:
            yield
        finally:
            try:
                sys.meta_path.remove(blocker)
            except ValueError:
                pass
            comfy.cli_args.args.cpu = original_args_cpu
            torch.cuda.is_available = original_is_available
            torch.cuda.current_device = original_current_device

    @contextlib.contextmanager
    def _force_triton_during_snapshot(self):
        """Block SageAttention C extensions during snap=True for GPU snapshots.

        With ``enable_gpu_snapshot=True`` we want ComfyUI to initialise with
        GPU so Modal captures the CUDA context, compiled kernels, and any
        warmup model tensors.  However, SageAttention's ``PyInit_*`` in C
        extension .so files calls CUDA driver APIs directly (cudaGetDevice,
        cudaMalloc, …) — these create raw CUDA driver handles that become
        dangling pointers on snapshot restore → SIGSEGV.

        This manager **_only_** blocks C extension imports (via a
        ``sys.meta_path`` finder).  It does **_not_** monkey-patch
        ``torch.cuda.is_available`` or ``comfy.cli_args.args.cpu``, so
        ComfyUI naturally detects the GPU during startup.  SageAttention
        falls back to its Triton path, which uses torch CUDA APIs that
        Modal properly checkpoints.

        On restore, ``_select_sage_runtime_mode()`` detects that the real
        GPU CUDA backend is available and switches to the baked CUDA path
        for subsequent prompt executions.
        """
        import sys

        class _BlockCudaModuleImport:
            def find_spec(self, name, path=None, target=None):
                if _is_cuda_module(name):
                    raise ImportError(
                        f"[comfyapp] blocked CUDA module import "
                        f"{name!r} during snap=True to keep snapshot clean"
                    )
                return None

            def find_module(self, name, path=None):
                if _is_cuda_module(name):
                    return self
                return None

            def load_module(self, name):
                raise ImportError(
                    f"[comfyapp] blocked CUDA module import "
                    f"{name!r} during snap=True to keep snapshot clean"
                )

        def _is_cuda_module(name: str) -> bool:
            return (
                name.endswith("_cuda")
                or name.startswith("cuda_")
                or "_cuda_" in name
            )

        blocker = _BlockCudaModuleImport()
        sys.meta_path.insert(0, blocker)

        # Ensure ComfyUI's CLI layer is initialised with GPU mode so
        # model_management starts in HIGH_VRAM during the snapshot.
        comfy_path = "/root/comfy/ComfyUI"
        if comfy_path not in sys.path:
            sys.path.insert(0, comfy_path)
        import comfy.cli_args
        comfy.cli_args.args.cpu = False

        try:
            yield
        finally:
            try:
                sys.meta_path.remove(blocker)
            except ValueError:
                pass

    def _start_in_process_backend(self):
        """Initialize ComfyUI in-process for snapshot-friendly execution.

        Sets up ComfyUI's execution environment in the current Python process
        instead of launching a subprocess. This allows Modal's memory snapshot
        to capture the initialized state (imported modules, registered nodes,
        etc.) so subsequent container starts skip Python initialization.

        GPU is available during startup — ``enable_gpu_snapshot=True`` in the
        Modal app ensures GPU memory is preserved in the snapshot.
        """
        t0 = time.time()
        _stage = time.time()

        # ── Match comfy launch CWD — ComfyUI modules use relative path
        #    resolution (e.g. ``from utils.install_util import ...``). ──
        comfy_path = "/root/comfy/ComfyUI"
        os.chdir(comfy_path)
        if comfy_path not in sys.path:
            sys.path.insert(0, comfy_path)

        # Line-buffered stdout so container logs are not delayed
        sys.stdout.reconfigure(line_buffering=True)
        self._log_profile("inproc_chdir_cwd", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── Import order matters: ComfyUI's utils/ package (directory) is
        #    shadowed by comfy/utils.py (module file) when comfy is imported
        #    first.  Replicate main.py's order: folder_paths + utils.* BEFORE
        #    any import that touches the comfy package.                       ──
        import folder_paths  # safe — no comfy deps
        import utils.extra_config  # establishes utils as the /utils/ package
        import utils.mime_types  # reinforces utils package before comfy loads

        import asyncio
        import comfy.model_management
        import comfy.model_patcher
        import comfy.utils
        import execution
        import nodes
        import server as comfy_server
        self._log_profile("inproc_imports", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        comfy.model_management.DISABLE_SMART_MEMORY = False
        if hasattr(comfy.model_management, "VRAMState") and hasattr(comfy.model_management.VRAMState, "HIGH_VRAM"):
            comfy.model_management.vram_state = comfy.model_management.VRAMState.HIGH_VRAM
            self._patch_offload_devices_for_high_vram(comfy.model_management)
        self._patch_model_cpu_cache(comfy.utils)
        if PROFILING_ENABLED:
            self._patch_model_clone_profiling(comfy.model_patcher)
            self._patch_model_management_profiling(comfy.model_management)
        self._log_profile("inproc_patch", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── DummyServer: minimal PromptServer that doesn't bind a port ──
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)

        class _DummyServer(comfy_server.PromptServer):
            def __init__(self, loop):
                super().__init__(loop)
                comfy_server.PromptServer.instance = self
                q = execution.PromptQueue(comfy_server.PromptServer.instance)
                self.client_id = "in-process"
                self.prompt_queue = q
                self._send_sync_callback = None

            def send_sync(self, event, data, sid=None):
                if self._send_sync_callback:
                    self._send_sync_callback(event, data, sid)

        dummy = _DummyServer(event_loop)
        self._log_profile("inproc_server_init", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── PromptExecutor for direct workflow execution (must provide
        #    cache_args dict; v0.22+ unconditionally indexes into it) ──
        total_ram_gb = _get_system_ram_gb()
        # Cap at 24 GB: ComfyUI's model cache only needs to hold
        # state_dicts for the active workflow (max ~17 GB for
        # Flux UNet + Qwen-sized text encoders on 32 GB hosts).
        cache_ram_gb = round(max(4.0, min(total_ram_gb * 0.5, 24.0)), 1)
        print(
            f"[comfyapp] total_ram={total_ram_gb}G  "
            f"cache_ram={cache_ram_gb}G"
        )
        self._executor = execution.PromptExecutor(
            dummy,
            cache_args={"lru": 0, "ram": cache_ram_gb, "ram_inactive": 96.0},
        )
        self._dummy_server = dummy
        self._event_loop = event_loop
        self._log_profile("inproc_executor_init", ram_gb=total_ram_gb, cache_gb=cache_ram_gb, duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── Wire up send_sync for execution-progress logging ──
        def _on_sync(event, data, sid):
            if event == "execution_start":
                if PROFILING_ENABLED:
                    self._log_profile("inproc_exec_progress", event="execution_start", prompt_id=data.get("prompt_id","")[:8])
            elif event == "executing":
                node = data.get("node", None)
                now = time.time()
                if node is None:
                    self._finish_profiled_node(now)
                    if PROFILING_ENABLED:
                        self._log_profile("inproc_exec_progress", event="execution_done")
                else:
                    self._finish_profiled_node(now)
                    self._begin_profiled_node(node, now)
            elif event == "progress":
                self._note_progress_event(data)
                if PROFILING_ENABLED:
                    self._log_profile("inproc_exec_progress", event="progress", node=str(data.get("node",""))[:40], step=data.get("step",0), max=data.get("max",0))
            elif event == "execution_error":
                if PROFILING_ENABLED:
                    self._log_profile("inproc_exec_progress", event="execution_error", node=str(data.get("node",""))[:40])
        dummy._send_sync_callback = _on_sync

        # Register built-in + custom nodes (async in ComfyUI v0.22+)
        self._event_loop.run_until_complete(nodes.init_extra_nodes())
        self._apply_sage_attention_policy()
        self._log_profile("inproc_node_init", duration_ms=self._profile_ms(_stage))

        self._in_process_ready = True
        duration = time.time() - t0
        print(f"[comfyapp] in-process backend initialized in {duration:.3f}s")

    def _start_backend(self):
        """Select and start the execution backend."""
        backend = self._select_backend()
        print(f"[comfyapp] selected backend={backend}")
        if backend == "in_process":
            try:
                self._start_in_process_backend()
            except Exception as exc:
                print(f"[comfyapp] in_process backend failed ({exc}), falling back to subprocess")
                self._backend_fallback = True
                self._restart_comfy()
        else:
            self._restart_comfy()
        print(f"[comfyapp] active backend={self._select_backend()}")

    def _submit_and_poll(self, workflow: dict) -> dict:
        """Submit a workflow directly to the local ComfyUI API and wait for history."""
        client_id = f"warmup-{uuid.uuid4()}"
        r = self._http_client.post(
            "/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        r.raise_for_status()
        queued = r.json()
        prompt_id = queued["prompt_id"]
        delay = 0.25
        elapsed = 0.0
        while elapsed < 3600:
            history = self._http_client.get(f"/history/{prompt_id}").json()
            if prompt_id in history:
                return history[prompt_id]
            time.sleep(delay)
            elapsed += delay
        raise TimeoutError(f"Warmup prompt {prompt_id} timed out")

    def _build_warmup_workflow(self, profile: dict) -> dict:
        """Build a warmup workflow from the pinned warmup profile.

        Returns only model-loading nodes (UNETLoader, CLIPLoader) — no
        inference nodes.  Loading the models into ComfyUI's GPU cache is
        the critical part; running a warmup inference step adds ~500ms
        with no measurable benefit for the first real prompt.
        """
        if profile.get("mode") == "checkpoint":
            # Checkpoint path: just load the checkpoint, skip inference
            return {
                "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": profile["checkpoint"]}},
            }
        # Use CLIPLoader (not DualCLIPLoader) to match the real prompt's
        # loader type so the model cache entry is shared.
        clip_name = profile.get("clip1", "")
        clip_type = profile.get("clip_type", "flux")
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": profile["unet"], "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {
                "clip_name": clip_name,
                "type": clip_type,
            }},
        }

    def _preload_warmup_profile(self) -> dict:
        """Preload and warm the pinned or auto-detected model stack.

        Priority: pinned env vars > auto-detected stack from last prompt.

        Uses the active execution backend (in-process or subprocess/HTTP).
        During startup (snap=True) with in-process CUDA is hidden, so this
        method is intentionally skipped by ``startup()`` when
        ``is_in_proc=True`` — it only runs on the ``restore()`` path where
        the GPU is available.
        """
        _t0 = time.time()
        profile = load_warmup_profile()
        t_load_profile = round((time.time() - _t0) * 1000, 1)

        replay_workflow = {}
        t_load_replay = 0.0
        if not profile:
            _t0 = time.time()
            replay_workflow = self._load_last_warmup_workflow()
            t_load_replay = round((time.time() - _t0) * 1000, 1)

        t_load_stack = 0.0
        if not profile and not replay_workflow:
            _t0 = time.time()
            profile = stack_to_profile(self._load_last_model_stack())
            t_load_stack = round((time.time() - _t0) * 1000, 1)

        if not profile and not replay_workflow:
            print(f"[comfyapp] warmup disabled (no profile, no replay, no stack)")
            return {"mode": "none", "status": "disabled"}
        started = time.time()
        try:
            if replay_workflow:
                workflow = replay_workflow
                mode = "workflow"
                t_validate = 0.0
                t_build = 0.0
            else:
                _t0 = time.time()
                self._validate_warmup_profile_files(profile)
                t_validate = round((time.time() - _t0) * 1000, 1)
                _t0 = time.time()
                workflow = self._build_warmup_workflow(profile)
                t_build = round((time.time() - _t0) * 1000, 1)
                mode = profile.get("mode")
            if self._select_backend() == "in_process":
                _t0 = time.time()
                self._execute_in_process(workflow, collect_outputs=False)
                t_exec = round((time.time() - _t0) * 1000, 1)
            else:
                _t0 = time.time()
                self._submit_and_poll(workflow)
                t_exec = round((time.time() - _t0) * 1000, 1)
            duration_ms = round((time.time() - started) * 1000, 1)
            t_overhead = round(duration_ms - t_exec - t_validate - t_build - t_load_profile - t_load_replay - t_load_stack, 1)
            # Extract per-node timing breakdown from stage windows
            node_timing: dict[str, float] = {}
            windows = getattr(self, "_stage_windows", None) or {}
            for stage, fields in windows.items():
                s = fields.get("start")
                e = fields.get("end")
                if s is not None and e is not None:
                    node_timing[f"{stage}_ms"] = round((e - s) * 1000, 1)
            print(f"[comfyapp] warmup mode={mode} total={duration_ms}ms "
                  f"load_profile={t_load_profile}ms "
                  f"load_replay={t_load_replay}ms "
                  f"load_stack={t_load_stack}ms "
                  f"validate={t_validate}ms "
                  f"build={t_build}ms "
                  f"exec={t_exec}ms "
                  f"overhead={t_overhead}ms "
                  f"node_timing={node_timing}")
            return {"mode": mode, "status": "ok", "duration_ms": duration_ms, "node_timing": node_timing}
        except Exception as exc:
            import traceback
            duration_ms = round((time.time() - started) * 1000, 1)
            print(f"[comfyapp] warmup failed after {duration_ms}ms "
                  f"mode={'workflow' if replay_workflow else profile.get('mode')}:\n{traceback.format_exc()}")
            return {
                "mode": "workflow" if replay_workflow else profile.get("mode"),
                "status": "error",
                "duration_ms": duration_ms,
                "error": str(exc)[:500],
            }

    def _warmup_runtime(self) -> dict:
        """Warm up the ComfyUI runtime if enabled.

        For the subprocess backend, submits a model-loading workflow so the
        GPU model cache is populated before the snapshot is taken.  These
        model tensors are then captured in the GPU memory snapshot and are
        immediately available after restore — no volume re-read needed.
        """
        if not ENABLE_WARMUP:
            return {"enabled": False, "profile": WARMUP_PROFILE}
        t0 = time.time()
        node_timing: dict = {}
        try:
            if self._select_backend() == "in_process":
                _ = self._executor
            else:
                # Subprocess: load models into ComfyUI's GPU cache via the
                # HTTP API.  This populates current_loaded_models inside the
                # subprocess so the GPU snapshot captures them.
                wr = self._preload_warmup_profile()
                if isinstance(wr, dict):
                    node_timing = wr.get("node_timing", {})
            duration_s = round(time.time() - t0, 3)
            return {"enabled": True, "profile": WARMUP_PROFILE, "duration_s": duration_s, "status": "ok", **node_timing}
        except Exception as exc:
            duration_s = round(time.time() - t0, 3)
            print(f"[comfyapp] warmup failed after {duration_s:.3f}s: {exc}")
            return {"enabled": True, "profile": WARMUP_PROFILE, "duration_s": duration_s, "status": "error", "error": str(exc)[:200]}

    def _restart_comfy(self):
        _restart_t0 = time.time()
        print("[comfyapp] _restart_comfy starting")
        # If running in-process, switch to subprocess mode
        if getattr(self, "_in_process_ready", False):
            print("[comfyapp] switching from in-process to subprocess backend")
            self._in_process_ready = False
            self._executor = None
            self._dummy_server = None
            self._event_loop = None

        if self._http_client_obj is not None:
            self._http_client_obj.close()
            self._http_client_obj = None
        if getattr(self, "_proc", None) and self._proc.poll() is None:
            print("[comfyapp] terminating existing ComfyUI subprocess")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print("[comfyapp] killing unresponsive ComfyUI subprocess")
                self._proc.kill()
        _kill_ms = round((time.time() - _restart_t0) * 1000, 1)
        self._proc = subprocess.Popen(
            [
                "comfy", "launch", "--", "--listen", "0.0.0.0",
                f"--port={COMFYUI_API_PORT}", "--disable-auto-launch",
                "--gpu-only", "--disable-smart-memory", "--cache-classic",
            ],
        )
        _launch_ms = round((time.time() - _restart_t0) * 1000, 1)
        self._wait_for_comfy()
        _total_ms = round((time.time() - _restart_t0) * 1000, 1)
        print(f"[comfyapp] _restart_comfy done: kill_ms={_kill_ms} launch_ready_ms={_total_ms} wait_ms={_total_ms - _launch_ms}")

    @modal.enter(snap=True)
    def startup(self):
        t0 = time.time()
        _snap_mode = os.environ.get("COMFYMODAL_SNAPSHOT_MODE", "full").strip().lower()
        print(f"[comfyapp] lifecycle=startup snap=True snapshot_mode={_snap_mode}")

        is_in_proc = (self._select_backend() == "in_process")

        stage_started = time.time()
        self._ensure_models_symlink()
        self._log_profile("startup_symlink", duration_ms=self._profile_ms(stage_started))

        stage_started = time.time()
        manager_paths = set_manager_network_mode_offline()
        self._log_profile("manager_network_mode", mode="offline", paths=len(manager_paths), duration_ms=self._profile_ms(stage_started))

        stage_started = time.time()
        vol.reload()
        self._log_profile("volume_reload", duration_ms=self._profile_ms(stage_started))

        stage_started = time.time()
        _, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
        self._log_profile("custom_nodes_sync", duration_ms=self._profile_ms(stage_started), state_count=len(self._custom_nodes_state))

        stage_started = time.time()
        install_summary = self._install_custom_node_requirements()
        self._log_profile("requirements_install", duration_ms=self._profile_ms(stage_started), installed=len(install_summary.get("installed", [])), skipped=len(install_summary.get("skipped", [])))

        stage_started = time.time()
        self._record_runtime_state()
        self._log_profile("runtime_state_record", duration_ms=self._profile_ms(stage_started))

        _need_backend = True
        if _snap_mode == "none":
            _need_backend = False
            print("[comfyapp] snapshot_mode=none: skipping backend init during snap=True")
        elif _snap_mode == "minimal":
            # Minimal snapshot: import backend modules but skip heavy GPU init.
            # ComfyUI will fully init on restore.
            _need_backend = False
            print("[comfyapp] snapshot_mode=minimal: backend init deferred to restore")
        if _need_backend and is_in_proc:
            if ENABLE_GPU_SNAPSHOT:
                stage_started = time.time()
                with self._force_triton_during_snapshot():
                    self._start_backend()
                self._log_profile("backend_start", backend=self._select_backend(), duration_ms=self._profile_ms(stage_started))
            else:
                stage_started = time.time()
                with self._force_cpu_during_snapshot():
                    self._start_backend()
                self._log_profile("backend_start", backend=self._select_backend(), duration_ms=self._profile_ms(stage_started))
        elif _need_backend:
            stage_started = time.time()
            self._start_backend()
            self._log_profile("backend_start", backend=self._select_backend(), duration_ms=self._profile_ms(stage_started))
            # Skip the GPU warmup preload during snap=True — loading ~9GB
            # of Flux/Qwen weights into the subprocess's GPU memory would
            # be captured in the snapshot, costing ~30+ seconds of GPU
            # memory transfer on every restore.  The first prompt after
            # restore pays the model load cost.
            warmup_result = self._warmup_runtime()
            print(f"[comfyapp] warmup={warmup_result}")

        duration = time.time() - t0
        print(f"[comfyapp] startup complete in {duration:.3f}s  "
              f"req_installed={len(install_summary.get('installed', []))}")

    def _warmup_cuda(self):
        """Revitalise CUDA driver context and force GPU clock ramp-up.

        Modal's ``enable_gpu_snapshot`` preserves GPU *memory* across
        restore, but the CUDA driver context can become stale on a new
        container.  The first kernel launch then pays an ~8s penalty
        and the GPU may stay in a low-power state that throttles
        memory-bandwidth-bound ops (VAE decode, text encoding).

        Running a brief warmup here pays the penalty once during
        restore rather than silently degrading prompt execution.
        """
        import torch
        if not torch.cuda.is_available():
            print("[comfyapp] CUDA warmup skipped — no GPU")
            return
        dev = torch.device(torch.cuda.current_device())
        _t0 = time.time()
        # Force CUDA context reconnection (first call is slow if stale)
        torch.cuda.synchronize(dev)
        _ctx_ms = round((time.time() - _t0) * 1000, 1)
        _t0 = time.time()
        # Run a handful of GEMMs to coax GPU Boost out of its low-power state
        a = torch.randn(2048, 2048, device=dev)
        b = torch.randn(2048, 2048, device=dev)
        for _ in range(5):
            a = a @ b
        torch.cuda.synchronize(dev)
        _gemm_ms = round((time.time() - _t0) * 1000, 1)
        # Warm the memory allocator with a moderate allocation
        _t0 = time.time()
        _warm = torch.empty(256, 1024, 1024, dtype=torch.float16, device=dev)
        _warm.zero_()
        torch.cuda.synchronize(dev)
        del _warm
        _alloc_ms = round((time.time() - _t0) * 1000, 1)
        print(f"[comfyapp] CUDA warmup done device={torch.cuda.get_device_name(dev)} "
              f"ctx_sync={_ctx_ms}ms gemm={_gemm_ms}ms alloc={_alloc_ms}ms")

    def _warmup_sage_attention_cuda(self):
        """Run one SageAttention CUDA forward pass to pre-load kernels."""
        try:
            _t0 = time.time()
            backend_name, backend, backend_kwargs = self._preferred_sage_backend()
            if backend is None:
                print("[comfyapp] sage_warmup skipped — no backend")
                return
            import torch
            q = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            k = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            v = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            _ = backend(q, k, v, is_causal=False, attn_mask=None,
                        tensor_layout="NHD", **backend_kwargs)
            torch.cuda.synchronize()
            _dur = round((time.time() - _t0) * 1000, 1)
            print(f"[comfyapp] sage_warmup done backend={backend_name} {_dur}ms")
        except Exception as exc:
            print(f"[comfyapp] sage_warmup failed: {exc}")

    def _warmup_direct(self, profile: dict) -> dict:
        """Direct warmup: load models and prime CLIPTextEncode cache without
        ComfyUI executor overhead.

        Calls UNETLoader, CLIPLoader, and CLIPTextEncode node functions
        directly instead of going through ``_execute_in_process()``.  This
        skips ~800ms of executor dispatch, IS_CHANGED calls, and profiling.

        The loaded models still land in ComfyUI's GPU model cache via
        ``load_models_gpu()`` which the node functions call internally.
        """
        _t0 = time.time()
        _phases: dict[str, float] = {}
        try:
            import nodes

            unet_name = profile.get("unet", "")
            clip_name = profile.get("clip1", "")
            clip_type = profile.get("clip_type", "flux")

            # 1 -- Load UNET via UNETLoader
            _s = time.time()
            unet_cls = nodes.NODE_CLASS_MAPPINGS.get("UNETLoader")
            if unet_cls and unet_name:
                unet_loader = unet_cls()
                unet_loader.load_unet(unet_name=unet_name, weight_dtype="default")
                _phases["direct_unet_load_ms"] = round((time.time() - _s) * 1000, 1)
            else:
                _phases["direct_unet_load_ms"] = 0.0

            # 2 -- Load CLIP via CLIPLoader, cache for real prompt reuse
            _s = time.time()
            clip_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPLoader")
            clip_out = None
            if clip_cls and clip_name:
                clip_loader = clip_cls()
                clip_out = clip_loader.load_clip(clip_name=clip_name, type=clip_type)
                _phases["direct_clip_load_ms"] = round((time.time() - _s) * 1000, 1)
                # Store in CLIP object cache for real prompt reuse
                if clip_out:
                    self._init_clip_cache()
                    try:
                        import folder_paths
                        clip_path = folder_paths.get_full_path("text_encoders", clip_name) or ""
                        if clip_path:
                            _key = self._clip_cache_key(clip_path, clip_type)
                            self._clip_object_cache[_key] = clip_out[0]
                            _phases["direct_clip_cached"] = 1.0
                            print(f"[comfyapp] direct warmup: CLIP cached key={_key} "
                                  f"id={id(clip_out[0])}")
                    except Exception as exc:
                        print(f"[comfyapp] direct warmup: CLIP cache store failed: {exc}")
            else:
                _phases["direct_clip_load_ms"] = 0.0

            # 3 -- Prime CLIPTextEncode cache (optional)
            # Costs ~1000ms for Qwen 8B forward pass but saves ~600ms
            # during inference.  Net savings ~400ms by disabling.
            _wce_enabled, _wce_source = _resolve_wce()
            _s = time.time()
            if _wce_enabled and clip_out and WARMUP_TEXT:
                enc_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                if enc_cls:
                    encoder = enc_cls()
                    encoder.encode(clip=clip_out[0], text=WARMUP_TEXT)
            _phases["direct_clip_encode_ms"] = round((time.time() - _s) * 1000, 1)
            _phases["wce_enabled"] = _wce_enabled
            _phases["wce_source"] = _wce_source
            _phases["direct_total_ms"] = round((time.time() - _t0) * 1000, 1)
            print(f"[comfyapp] direct warmup OK — {_phases}")
            return {"status": "ok", **_phases}
        except Exception as exc:
            import traceback
            _phases["direct_total_ms"] = round((time.time() - _t0) * 1000, 1)
            print(f"[comfyapp] direct warmup FAILED after {_phases['direct_total_ms']}ms: {exc}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(exc)[:200], **_phases}

    def _clip_cache_key(self, clip_path: str, clip_type: str) -> tuple:
        """Deterministic cache key for a CLIP model load request."""
        try:
            resolved = os.path.realpath(clip_path)
        except Exception:
            resolved = clip_path
        return (resolved, clip_type or "stable_diffusion")

    def _init_clip_cache(self):
        """Initialise instance-level CLIP object cache."""
        if not hasattr(self, '_clip_object_cache'):
            self._clip_object_cache: dict[tuple, object] = {}
            self._clip_cache_keys: list[tuple] = []

    def _patch_clip_loader_cache(self):
        """Patch CLIPLoader.load_clip and DualCLIPLoader.load_clip to
        reuse CLIP objects loaded during warmup.

        The warmup ``_warmup_direct()`` stores the loaded CLIP object in
        ``self._clip_object_cache`` keyed by (resolved_path, clip_type).
        When the real prompt's CLIPLoader/DualCLIPLoader asks for the
        same file, the patch returns the cached object instead of
        constructing a new one — eliminating the ~400-600ms clip_load.
        """
        self._init_clip_cache()
        _api = self  # capture ComfyAPI instance for closure access
        try:
            import folder_paths
            import nodes
        except Exception as exc:
            print(f"[comfyapp] clip_loader_cache: imports failed: {exc}")
            return

        for node_name in ("CLIPLoader", "DualCLIPLoader"):
            cls = nodes.NODE_CLASS_MAPPINGS.get(node_name)
            if cls is None:
                print(f"[comfyapp] clip_loader_cache: {node_name} not found")
                continue
            orig_load = getattr(cls, "load_clip", None)
            if orig_load is None:
                continue
            if getattr(orig_load, '_comfy_modal_clip_cached', False):
                continue

            def _make_cached_load(_orig=orig_load, _name=node_name):
                def _cached_load(self_node, **kwargs):
                    # Handle both CLIPLoader (clip_name) and DualCLIPLoader (clip_name1, clip_name2)
                    clip_a = kwargs.get("clip_name") or kwargs.get("clip_name1") or ""
                    clip_b = kwargs.get("clip_name2") or ""
                    clip_type = kwargs.get("type", "stable_diffusion")

                    # Resolve clip paths
                    path_a = ""
                    if clip_a:
                        try:
                            path_a = folder_paths.get_full_path("text_encoders", clip_a) or ""
                        except Exception:
                            path_a = clip_a
                    path_b = ""
                    if clip_b:
                        try:
                            path_b = folder_paths.get_full_path("text_encoders", clip_b) or ""
                        except Exception:
                            path_b = clip_b

                    # Build cache keys
                    keys = []
                    if path_a:
                        keys.append(_api._clip_cache_key(path_a, clip_type))
                    if path_b:
                        keys.append(_api._clip_cache_key(path_b, clip_type))

                    # If warmup cached one file and real prompt loads two of the same,
                    # the second key points to the same file as the first. Deduplicate.
                    _cache = getattr(_api, '_clip_object_cache', {})
                    unique_keys = list(dict.fromkeys(keys))
                    missing = [k for k in unique_keys if k not in _cache]

                    if not missing:
                        # All keys in cache → HIT
                        _api._clip_cache_hits = getattr(_api, '_clip_cache_hits', 0) + 1
                        if _name == "DualCLIPLoader":
                            return (_cache[unique_keys[0]], _cache[unique_keys[-1]])
                        else:
                            return (_cache[unique_keys[0]],)

                    # MISS: load normally, attach metadata for CLIPTextEncode cache
                    _api._clip_cache_misses = getattr(_api, '_clip_cache_misses', 0) + 1
                    result = _orig(self_node, **kwargs)
                    # Attach resolved paths and type to clip for CLIPTextEncode cache key
                    if result:
                        for _clip_obj in result:
                            if _clip_obj is not None:
                                _clip_obj._warmup_model_paths = unique_keys if unique_keys else []
                                _clip_obj._warmup_clip_type = clip_type
                    return result

                _cached_load._comfy_modal_clip_cached = True
                return _cached_load

            setattr(cls, "load_clip", _make_cached_load())
            print(f"[comfyapp] clip_loader_cache: patched {node_name}.load_clip")

    def _patch_model_cache_comparison(self):
        """Patch LoadedModel.__eq__ to match by class+size+device.

        ComfyUI's GPU model cache (``current_loaded_models``) uses Python
        identity to determine if a model is already loaded:
        ``self.model is other.model``.  This means the warmup workflow's
        entries are never reused by the real prompt because each
        ``executor.execute()`` creates fresh ``ModelPatcher`` objects.

        The patch changes the comparison to model class name + model size
        (bytes) + load device.  Models from the same file produce the same
        structure and size, so the warmup's GPU cache entries are found
        by the real prompt — no volume re-read for model weights.

        Also tries model_type fallback when class names differ (handles
        CLIPLoader vs DualCLIPLoader wrapper differences).

        Logs cache hit/miss stats in ``comfy.model_management._gpu_cache_eq_stats``
        which ``restore()`` reads and includes in ``_last_restore_timing``.
        """
        import comfy.model_management
        if getattr(comfy.model_management.LoadedModel, '_comfy_modal_patched', False):
            return
        original_eq = comfy.model_management.LoadedModel.__eq__
        _gpu_stats: dict = {
            "calls": 0, "class_hits": 0, "modeltype_hits": 0,
            "misses": 0, "details": {},
        }
        comfy.model_management._gpu_cache_eq_stats = _gpu_stats

        def _eq(self, other):
            _n1 = _n2 = "?"
            try:
                _n1 = self.model.model.__class__.__name__ if self.model and self.model.model else "?"
                _n2 = other.model.model.__class__.__name__ if other.model and other.model.model else "?"
            except Exception:
                pass
            key = f"{_n1}->{_n2}"
            if self.model is other.model:
                _gpu_stats["calls"] += 1
                _gpu_stats["class_hits"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["hits"] += 1
                _gpu_stats["details"][key]["last"] = "identity"
                return True
            if self.model is None or other.model is None:
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = "none_model"
                return False
            if self.device != other.device:
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = "device_mismatch"
                return False
            try:
                n1 = self.model.model.__class__.__name__
                n2 = other.model.model.__class__.__name__
                sz1 = self.model.model_size()
                sz2 = other.model.model_size()
                if n1 == n2 and sz1 == sz2:
                    _gpu_stats["calls"] += 1
                    _gpu_stats["class_hits"] += 1
                    _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                    _gpu_stats["details"][key]["hits"] += 1
                    _gpu_stats["details"][key]["last"] = "class_match"
                    return True
                # Fallback: match by model_type if class names differ
                # (e.g. CLIPLoader vs DualCLIPLoader wrappers)
                try:
                    t1 = self.model.model.model_type
                    t2 = other.model.model.model_type
                    if t1 == t2 and sz1 == sz2:
                        _gpu_stats["calls"] += 1
                        _gpu_stats["modeltype_hits"] += 1
                        _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                        _gpu_stats["details"][key]["hits"] += 1
                        _gpu_stats["details"][key]["last"] = "modeltype_match"
                        return True
                except Exception:
                    pass
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = f"no_match_{n1}_vs_{n2}_sz{sz1}_vs_{sz2}"
                return False
            except Exception:
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = "exception"
                return original_eq(self, other)

        comfy.model_management.LoadedModel.__eq__ = _eq
        comfy.model_management.LoadedModel._comfy_modal_patched = True

    def _patch_clip_text_encode_cache(self):
        """Cache CLIPTextEncode outputs by text input.

        The same text produces the same embedding every time, but ComfyUI
        re-runs the full Qwen 8B forward pass per ``executor.execute()``
        because its node cache is scoped per-execution.  This patch stores
        embeddings in a module-level cache keyed by text string.

        Called during ``restore()`` before the warmup workflow, which then
        pre-populates the cache by encoding the warmup text.  The real
        prompt's CLIPTextEncode hits the cache → 0ms clip_encode.
        """
        try:
            import nodes
            _clip_node_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
            if _clip_node_cls is None:
                print("[comfyapp] clip_cache: CLIPTextEncode not found")
                return
            _func_name = getattr(_clip_node_cls, "FUNCTION", "encode")
            _orig = getattr(_clip_node_cls, _func_name)
            if getattr(_orig, '_comfy_modal_cached', False):
                return
            _cache: dict[tuple, object] = {}
            _cache_mode = "model_aware"
            def _cached(self_node, clip, text):
                # Build model-aware key: includes text, CLIP model identity,
                # resolved paths, clip_type, and class name for safe reuse.
                _paths = tuple(getattr(clip, '_warmup_model_paths', None) or [])
                _clip_type = getattr(clip, '_warmup_clip_type', '') or ''
                _cls_name = type(clip).__name__
                _key = (text, _paths, _clip_type, _cls_name, id(clip))
                # Fast path: exact clip object match
                if _key in _cache:
                    return _cache[_key]
                # Slightly relaxed key: same text + same model files (different obj)
                _relaxed = (text, _paths, _clip_type, _cls_name)
                if _relaxed in _cache:
                    return _cache[_relaxed]
                # Miss: encode and cache
                result = _orig(self_node, clip, text)
                _cache[_key] = result
                _cache[_relaxed] = result  # also cache relaxed key for future calls
                return result
            _cached._comfy_modal_cached = True
            _cached._cache_mode = _cache_mode
            # Expose cache so background encoding can populate it
            _clip_node_cls._clip_text_cache = _cache
            setattr(_clip_node_cls, _func_name, _cached)
            print(f"[comfyapp] clip_cache: patched {_clip_node_cls.__name__}.{_func_name} "
                  f"mode={_cache_mode}")
        except Exception as exc:
            print(f"[comfyapp] clip_cache: patch failed: {exc}")

    def _restore_in_process_gpu_state(self):
        """Re-enable ComfyUI GPU mode after a CPU-only snapshot import.

        During ``snap=True`` we force ComfyUI's CLI args and import-time
        model-management state into CPU mode so snapshot creation doesn't
        touch CUDA. The in-process backend is then snapshotted with that
        CPU-mode state. On restore we must explicitly flip ComfyUI back to
        GPU/HIGH_VRAM mode before the first real execution, otherwise model
        placement and tensor creation stay on CPU and CUDA-only attention
        paths fail with "Input tensors must be on cuda".
        """
        _t0 = time.time()
        import comfy.cli_args
        import comfy.model_management
        import psutil

        comfy.cli_args.args.cpu = False
        comfy.model_management.cpu_state = comfy.model_management.CPUState.GPU
        comfy.model_management.total_vram = (
            comfy.model_management.get_total_memory(comfy.model_management.get_torch_device())
            / (1024 * 1024)
        )
        comfy.model_management.total_ram = psutil.virtual_memory().total / (1024 * 1024)
        comfy.model_management.DISABLE_SMART_MEMORY = False
        if hasattr(comfy.model_management, "VRAMState") and hasattr(comfy.model_management.VRAMState, "HIGH_VRAM"):
            comfy.model_management.vram_state = comfy.model_management.VRAMState.HIGH_VRAM
        _t1 = time.time()
        print(f"[comfyapp] gpu_state restored vram={comfy.model_management.total_vram:.0f}MB "
              f"ram={comfy.model_management.total_ram:.0f}MB "
              f"vram_state={comfy.model_management.vram_state} "
              f"in {(_t1-_t0)*1000:.1f}ms")

    @modal.enter(snap=False)
    def restore(self):
        """Snapshot restore: reattach the GPU to the pre-initialised backend.

        ``startup()`` initialises the in-process ComfyUI backend under
        ``_force_cpu_during_snapshot()`` so the snapshot already contains
        the fully loaded Python state (modules, registered nodes,
        PromptExecutor, DummyServer) with **zero CUDA driver handles** —
        no SIGSEGV on restore.

        On restore we just need to:

        1. Reconnect the real GPU (``_warmup_cuda``).
        2. Select and apply the SageAttention runtime policy once the
           CUDA context is fresh.
        3. Force eager safetensors reads so model-load I/O happens up
           front instead of during compute.
        4. Optionally rebuild the GPU model cache via the warmup
           profile so the first prompt is fast.

        For the subprocess backend, the subprocess is still running from
        snap=True; we just probe ``/system_stats`` and restart on failure.
        """
        # Ensure warmup profile env vars are set for testing
        if not os.environ.get("COMFYMODAL_WARMUP_UNET"):
            os.environ["COMFYMODAL_WARMUP_UNET"] = "flux-2-klein-9b-fp8.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_CLIP1"):
            os.environ["COMFYMODAL_WARMUP_CLIP1"] = "qwen_3_8b_fp8mixed.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_CLIP2"):
            os.environ["COMFYMODAL_WARMUP_CLIP2"] = "qwen_3_8b_fp8mixed.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_VAE"):
            os.environ["COMFYMODAL_WARMUP_VAE"] = "flux2-vae.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_CLIP_TYPE"):
            # Use "flux2" to match CLIPLoader in flux2 workflows
            os.environ["COMFYMODAL_WARMUP_CLIP_TYPE"] = "flux2"
        if not os.environ.get("COMFYMODAL_PRELOAD_MODE"):
            # Use env var for experiment flexibility, else module default
            pass

        restore_start = time.time()
        print(f"[comfyapp] lifecycle=restore snap=False restore_start_unix={restore_start}")
        __stages: dict[str, float] = {}
        # Clear any stale restore timing from a previous call
        self._last_restore_timing = None

        is_in_proc = (self._select_backend() == "in_process")

        _s = time.time()
        self._ensure_models_symlink()
        __stages["ensure_models_ms"] = self._profile_ms(_s)
        __stages["preload_mode"] = _resolve_preload_mode()
        __stages["preload_mode_source"] = "file" if os.path.isfile(PRELOAD_MODE_PATH) else "env_var"

        # ── Pre-resolve warmup profile + model paths ─────────────────────
        # FUSE stat calls for model file location are I/O-bound and
        # independent of GPU state.  Resolving them early (before the
        # GPU/Sage warmup section below) lets these stat calls overlap
        # with GPU warmup, hiding ~200-600ms of latency.
        _warmup_profile = None
        _warmup_paths: list[str] = []
        if ENABLE_WARMUP:
            _s = time.time()
            _warmup_profile = self._snapshot_preload_profile()
            if _warmup_profile:
                _warmup_paths = self._snapshot_preload_paths(_warmup_profile)
            __stages["early_path_resolve_ms"] = self._profile_ms(_s)
            print(f"[comfyapp] early warmup profile={_warmup_profile.get('mode','none') if _warmup_profile else 'none'} "
                  f"resolved_paths={len(_warmup_paths)} in {__stages['early_path_resolve_ms']}ms")

        if is_in_proc:
            # If backend was skipped during snap=True (snapshot_mode=none/minimal),
            # initialize it now with full GPU access (no force_cpu).
            _backend_inited = getattr(self, "_event_loop", None) is not None
            _backend_deferred = False
            if not _backend_inited:
                _s = time.time()
                print("[comfyapp] deferred backend init on restore (snapshot_mode=none)")
                self._start_backend()
                __stages["deferred_backend_init_ms"] = self._profile_ms(_s)
                _backend_deferred = True
                _backend_inited = True

            if ENABLE_GPU_SNAPSHOT and _backend_inited and not _backend_deferred:
                # GPU snapshot restored — ComfyUI already initialised with GPU
                # (CUDA context, HIGH_VRAM mode, executor, etc. are captured).
                # Skip _restore_in_process_gpu_state() but still recalculate
                # VRAM/RAM in case the restore host differs.
                _s = time.time()
                import comfy.model_management
                import psutil
                comfy.model_management.total_vram = (
                    comfy.model_management.get_total_memory(comfy.model_management.get_torch_device())
                    / (1024 * 1024)
                )
                comfy.model_management.total_ram = psutil.virtual_memory().total / (1024 * 1024)
                __stages["gpu_state_ms"] = self._profile_ms(_s)

                _s = time.time()
                self._warmup_cuda()
                __stages["cuda_warmup_ms"] = self._profile_ms(_s)
                self._log_profile("restore_warmup", mode="cuda_warmup_gpu_snap", duration_ms=__stages["cuda_warmup_ms"])
                import comfy.utils
                comfy.utils.DISABLE_MMAP = True

                _s = time.time()
                mode, reason = self._select_sage_runtime_mode()
                self._apply_sage_attention_policy()
                __stages["sage_runtime_ms"] = self._profile_ms(_s)
                __stages["sage_mode"] = mode
                __stages["sage_reason"] = reason
                self._log_profile(
                    "restore_sage_runtime",
                    mode=mode,
                    reason=reason,
                    duration_ms=__stages["sage_runtime_ms"],
                )
            else:
                if not _backend_deferred:
                    # CPU-only snapshot — the in-process backend was initialised
                    # under force_cpu, so no CUDA state was captured.  Reattach
                    # the GPU, warm CUDA, select Sage runtime.
                    _s = time.time()
                    self._restore_in_process_gpu_state()
                    __stages["gpu_state_ms"] = self._profile_ms(_s)
                else:
                    # Deferred init: backend already started with GPU
                    __stages["gpu_state_ms"] = 0.0
                    __stages["gpu_state_source"] = "deferred"

                _s = time.time()
                self._warmup_cuda()
                __stages["cuda_warmup_ms"] = self._profile_ms(_s)
                self._log_profile("restore_warmup", mode="cuda_warmup", duration_ms=__stages["cuda_warmup_ms"])
                import comfy.utils
                comfy.utils.DISABLE_MMAP = True
                self._patch_model_cache_comparison()
                self._patch_clip_text_encode_cache()
                self._patch_clip_loader_cache()

                # ── CLIP encode cache debug: clear if requested ──────────
                _clip_cache_clear = _resolve_clip_cache_clear()
                __stages["clip_cache_clear_requested"] = 1 if _clip_cache_clear else 0
                if _clip_cache_clear:
                    try:
                        import nodes
                        _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                        if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                            _te_cls._clip_text_cache.clear()
                            __stages["clip_cache_cleared"] = 1
                            print("[comfyapp] clip_encode_cache: cleared by flag")
                    except Exception as exc:
                        print(f"[comfyapp] clip_encode_cache: clear failed: {exc}")
                # Cache size at restore start
                try:
                    import nodes
                    _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                    if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                        __stages["clip_cache_size_at_start"] = len(_te_cls._clip_text_cache)
                except Exception:
                    pass

                _s = time.time()
                mode, reason = self._select_sage_runtime_mode()
                self._apply_sage_attention_policy()
                __stages["sage_runtime_ms"] = self._profile_ms(_s)
                __stages["sage_mode"] = mode
                __stages["sage_reason"] = reason
                self._log_profile(
                    "restore_sage_runtime",
                    mode=mode,
                    reason=reason,
                    duration_ms=__stages["sage_runtime_ms"],
                )

            # Log intermediate restore phases (numeric-only to avoid round() on strings)
            phases = {k: round(v, 1) for k, v in __stages.items()
                      if not k.startswith("warmup_") and isinstance(v, (int, float))}
            print(f"[comfyapp] restore phases (pre-warmup): {phases}")

            # ── Warmup: load models + encode text (for clip cache) ──────
            if ENABLE_WARMUP:
                profile = _warmup_profile
                preload_paths = _warmup_paths
                __stages["warmup_profile_source"] = profile.get("_source", "?") if profile else "none"
                preload_result = {"count": 0, "file_timing_ms": {}}
                _s = time.time()
                if preload_paths:
                    preload_result = self._preload_models_to_cpu(preload_paths)
                __stages["warmup_preload_ms"] = self._profile_ms(_s)
                for fname, d_ms in preload_result.get("file_timing_ms", {}).items():
                    safe_key = f"warmup_{fname.replace('.','_').replace('-','_').lower()}_ms"
                    __stages[safe_key] = d_ms
                self._log_profile(
                    "restore_warmup_preload",
                    mode=profile.get("mode", "none") if profile else "none",
                    files=len(preload_paths),
                    cached=preload_result.get("count", 0),
                    duration_ms=__stages["warmup_preload_ms"],
                )
                warmup_result = {"mode": profile.get("mode", "none") if profile else "none", "status": "ok", "preload_count": preload_result.get("count", 0)}

                # ── Canonical ModelPatcher cache (warmup→prompt reuse) ──
                # Patches comfy.sd.load_diffusion_model so the real prompt
                # receives the same ModelPatcher object as warmup.
                # This makes LoadedModel.__eq__ match naturally, avoiding
                # redundant load_models_gpu work for already-loaded models.
                _mp_cache = _resolve_modelpatcher_cache()
                _mp_cache_dryrun = _resolve_modelpatcher_cache_dryrun()
                _mp_cache_store = {}
                if _mp_cache or _mp_cache_dryrun:
                    try:
                        import comfy.sd as _csd
                        import os as _os
                        _orig_load_diff = _csd.load_diffusion_model
                        def _cached_load_diff(unet_path, model_options={}, disable_dynamic=False):
                            _real = _os.path.realpath(unet_path) if hasattr(_os.path, 'realpath') else unet_path
                            _opts_str = str(sorted(model_options.items())) if model_options else "default"
                            _key = (_real, _opts_str)
                            _hit = _key in _mp_cache_store
                            if _mp_cache_dryrun or _mp_cache:
                                print(f"[comfyapp] modelpatcher_cache: key={_key} hit={_hit} dryrun={_mp_cache_dryrun} active={_mp_cache}")
                            if _mp_cache and _hit:
                                _cached = _mp_cache_store[_key]
                                print(f"[comfyapp] modelpatcher_cache HIT — returning cached ModelPatcher id={id(_cached)}")
                                return _cached
                            _result = _orig_load_diff(unet_path, model_options=model_options, disable_dynamic=disable_dynamic)
                            if not _hit:
                                _mp_cache_store[_key] = _result
                                print(f"[comfyapp] modelpatcher_cache STORE — key={_key} patcher_id={id(_result)} model_id={id(_result.model) if hasattr(_result,'model') else 0}")
                            return _result
                        _csd.load_diffusion_model = _cached_load_diff
                    except Exception as _mp_exc:
                        print(f"[comfyapp] modelpatcher_cache install FAILED: {_mp_exc}")

                # ── Direct warmup (no ComfyUI executor) ──────────────────
                # Calls UNETLoader, CLIPLoader, and CLIPTextEncode node
                # functions directly instead of _execute_in_process().
                # This saves ~800ms of executor dispatch overhead while
                # still loading UNET into GPU cache and priming the
                # CLIPTextEncode text cache.
                if profile and profile.get("mode"):
                    _s = time.time()
                    _dw = self._warmup_direct(profile)
                    __stages["warmup_direct_total_ms"] = _dw.get("direct_total_ms", 0.0)
                    for _k in ("direct_unet_load_ms", "direct_clip_load_ms", "direct_clip_encode_ms"):
                        _v = _dw.get(_k)
                        if _v is not None:
                            __stages[f"warmup_{_k}"] = _v
                    __stages["wce_enabled"] = _dw.get("wce_enabled", False)
                    __stages["wce_source"] = _dw.get("wce_source", "?")
                    if _dw.get("status") != "ok":
                        warmup_result["error"] = _dw.get("error", "direct warmup failed")
                        warmup_result["status"] = "error"
                        print(f"[comfyapp] direct warmup FAILED — executor bypass disabled")
                        # No executor fallback: direct warmup is the only path.
                        # If it fails, models load during inference (acceptable).
                    # Remove cleanup suppression (not needed without executor)
                    try:
                        import comfy.model_management as _mm
                        if hasattr(_mm, '_comfy_modal_suppress_cleanup'):
                            _mm._comfy_modal_suppress_cleanup = False
                    except Exception:
                        pass
        else:
            _s = time.time()
            try:
                self._http_client.get("/system_stats", timeout=5)
            except Exception:
                print("[comfyapp] ComfyUI unresponsive on restore, restarting")
                self._restart_comfy()
            __stages["subprocess_health_ms"] = self._profile_ms(_s)

        # CLIP cache size after warmup
        try:
            import nodes
            _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
            if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                __stages["clip_cache_size_after_warmup"] = len(_te_cls._clip_text_cache)
        except Exception:
            pass

        # Annotate warmup with per-node timing breakdown
        _wr = locals().get("warmup_result") or {}
        warmup_nodes = _wr.get("node_timing", {}) if isinstance(_wr, dict) else {}
        warmup_status = _wr.get("status", "?") if isinstance(_wr, dict) else "?"
        warmup_error = str(_wr.get("error", ""))[:200] if isinstance(_wr, dict) else ""
        # Collect model cache diagnostics
        _cpu_hits = dict(getattr(self, "_cpu_cache_hits", {}))
        _cpu_misses = dict(getattr(self, "_cpu_cache_misses", {}))
        _gpu_stats: dict = {}
        try:
            import comfy.model_management as _mm
            _gpu_stats = dict(getattr(_mm, "_gpu_cache_eq_stats", {}))
        except Exception:
            pass
        # CLIP object cache diagnostics
        _clip_cache = getattr(self, '_clip_object_cache', {})
        _clip_cache_report = {
            "size": len(_clip_cache),
            "keys": [str(k) for k in _clip_cache.keys()],
        }
        _restore_end = time.time()
        self._last_restore_timing = {
            "restore_total_ms": self._profile_ms(restore_start),
            "restore_start_unix_s": restore_start,
            "restore_end_unix_s": _restore_end,
            "warmup_status": warmup_status,
            "warmup_profile": _warmup_profile or {},  # actual profile used during restore
            **__stages,
            **({f"warmup_{k}": v for k, v in warmup_nodes.items()} if warmup_nodes else {}),
            "cpu_cache_hits": _cpu_hits,
            "cpu_cache_misses": _cpu_misses,
            "gpu_cache_eq": _gpu_stats,
            "clip_cache": _clip_cache_report,
        }
        if warmup_error:
            self._last_restore_timing["warmup_error"] = warmup_error
        print(f"[comfyapp] restore sanity check done in {time.time() - restore_start:.3f}s "
              f"perf={self._last_restore_timing}")

    @modal.exit()
    def shutdown(self):
        if self._http_client_obj is not None:
            self._http_client_obj.close()
            self._http_client_obj = None
        if getattr(self, "_proc", None) and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _wait_for_comfy(self):
        for _ in range(120):
            try:
                self._http_client.get("/system_stats")
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError("ComfyUI API failed to start")

    @modal.method()
    def object_info(self):
        if self._select_backend() == "in_process":
            # Return a simplified node registry (class names only) that is
            # JSON-serializable.  NODE_CLASS_MAPPINGS values are class objects
            # and cannot be json.dumps'd directly.
            import nodes
            return {
                "status": "ok",
                "in_process": True,
                "node_count": len(nodes.NODE_CLASS_MAPPINGS),
                "class_types": sorted(nodes.NODE_CLASS_MAPPINGS.keys()),
            }
        r = self._http_client.get("/object_info")
        return r.json()

    @modal.method()
    def refresh_custom_nodes(self, expected_nodes: list[str] | None = None):
        expected_nodes = expected_nodes or []
        last_missing = []
        summary = None
        current_state = ()
        for attempt in range(5):
            summary, current_state = self._sync_custom_nodes_from_volume()
            last_missing = missing_expected_nodes(current_state, expected_nodes)
            if not last_missing:
                self._custom_nodes_state = current_state
                self._restart_comfy()
                return {"status": "ok", **summary}
            if attempt < 4:
                time.sleep(1)
        raise RuntimeError(f"Synced custom nodes not visible in Modal volume yet: {last_missing}")

    @modal.method()
    def run_prompt(
        self,
        workflow: dict,
        input_images: dict | None = None,
        trace: dict | None = None,
    ) -> dict:
        """Submit a workflow for execution.

        NOTE: This method does NOT reload Modal volumes or resync custom
        nodes.  After any model/custom-node mutation, callers must invoke
        ``resync_runtime()`` first so that the container picks up the
        changes before calling ``run_prompt()``.

        The optional ``trace`` parameter is a dict of pre-collected
        timestamps from the local ComfyUI server (browser t0, local t1,
        local t2).  The Modal side merges its own t3..t8 markers into
        the trace and returns the merged dict in the response under
        the ``"trace"`` key.
        """

        # Build a Trace anchored at the earliest known wall-clock time
        # we can find (t0 from the browser).  When no browser t0 is
        # available the anchor falls back to "right now", so all later
        # timestamps are still consistent with each other.
        t0 = coerce_t0_from_browser(trace or {})
        prompt_id_hint = ""
        if isinstance(trace, dict):
            prompt_id_hint = str(trace.get("prompt_id") or "")
        if not prompt_id_hint and isinstance(workflow, dict):
            for node in workflow.values():
                if isinstance(node, dict) and "prompt_id" in node:
                    prompt_id_hint = str(node["prompt_id"])
        server_trace = Trace(prompt_id=prompt_id_hint, t0=t0)
        server_trace.update(trace)
        # t3 = Modal handler entry.  On a cold container this is *after*
        # snapshot restore + CUDA warmup; on a warm container it is just
        # the time the function was dispatched.
        server_trace.mark("t3_modal_entry")

        # ── In-process backend: direct execution, no HTTP ──
        if self._select_backend() == "in_process":
            total_started = time.time()
            _last_graph_validate_ms = getattr(self, "_last_graph_validate_ms", None)
            result = self._execute_in_process(workflow, input_images, trace=server_trace)
            _graph_validate_ms = getattr(self, "_last_graph_validate_ms", None)
            _t8b_t0 = time.time()

            _s = time.time()
            requested_stack = extract_requested_model_stack(workflow)
            if requested_stack and any(requested_stack.values()):
                self._save_last_model_stack(requested_stack)
            _t8b_save_stack_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            _wp = {}
            _rt = getattr(self, "_last_restore_timing", None) or {}
            for _k in ("warmup_status", "warmup_preload_ms", "warmup_direct_total_ms", "warmup_direct_clip_load_ms", "direct_unet_load_ms", "direct_clip_load_ms"):
                _v = _rt.get(_k)
                if _v is not None:
                    _wp[_k] = _v
            print(f"[comfyapp] warmup_profile_during_restore: {_wp}")
            _diagnose_profile = _rt.get("warmup_profile") or load_warmup_profile()
            self._log_warmup_vs_workflow_diagnostics(_diagnose_profile, requested_stack, raw_workflow=workflow)
            _t8b_diag_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            total_ms = round((time.time() - total_started) * 1000, 1)
            server_trace.mark("t9_modal_return")
            _s = time.time()
            print(
                f"[comfyapp.profile] stage=remote_total backend=in_process duration_ms={total_ms} "
                f"output_images={len(result.get('images', []))} "
                f"output_videos={len(result.get('videos', []))}"
            )
            print(server_trace.log_line())
            _t8b_profile_print_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            trace_summary = server_trace.summary()
            self._enrich_trace_with_restore_timing(trace_summary)
            result["trace"] = trace_summary
            _rt2 = getattr(self, "_last_restore_timing", None)
            result["_restore_timing"] = dict(_rt2) if _rt2 else {}
            _t8b_enrich_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            _gpu_stats_raw = {}
            try:
                import comfy.model_management as _mm
                _gpu_stats_raw = dict(getattr(_mm, '_gpu_cache_eq_stats', {}))
            except Exception:
                pass
            result["_cache_diagnostics"] = {
                "cpu_hits": dict(getattr(self, "_cpu_cache_hits", {})),
                "cpu_misses": dict(getattr(self, "_cpu_cache_misses", {})),
                "gpu_eq": _gpu_stats_raw,
                "clip_cache_hits": getattr(self, "_clip_cache_hits", 0),
                "clip_cache_misses": getattr(self, "_clip_cache_misses", 0),
            }
            # Executor profiling data
            import execution as _exec_mod
            _exec_prof_raw = getattr(_exec_mod, '_comfy_modal_exec_prof', None)
            if _exec_prof_raw and _exec_prof_raw.get("nodes"):
                _nodes = _exec_prof_raw.get("nodes", {})
                _total_node_ms = round(sum(n["ms"] for n in _nodes.values()), 2)
                _fcs = _exec_prof_raw.get("_first_call_start")
                _lce = _exec_prof_raw.get("_last_call_end")
                _execute_wall_ms = round((_lce - _fcs) * 1000, 2) if _fcs and _lce else 0.0
                _exec_residual_ms = round(max(0.0, _execute_wall_ms - _total_node_ms), 2)
                _flat = {f"node_{k}": round(v["ms"], 2) for k, v in _nodes.items()}
                _flat["total_node_ms"] = _total_node_ms
                _flat["execute_wall_ms"] = _execute_wall_ms
                _flat["executor_residual_ms"] = _exec_residual_ms
                _flat["node_counts"] = {k: v["count"] for k, v in _nodes.items()}
                result["_exec_profile"] = _flat
                print(f"[comfyapp] exec_profile: nodes={dict(_flat)}")
                # Reset for next prompt (mutate in-place since patched function references this dict)
                _exec_prof_raw.clear()
                _exec_prof_raw["nodes"] = {}
                _exec_prof_raw["_first_call_start"] = None
                _exec_prof_raw["_last_call_end"] = None
                _exec_prof_raw["_call_count"] = 0
            # Sampler profiling data
            import comfy.samplers as _samplers_mod
            _sampler_prof = getattr(_samplers_mod, '_comfy_modal_sampler_prof', None)
            if _sampler_prof and _sampler_prof.get("total_ms"):
                result["_sampler_profile"] = dict(_sampler_prof)
                print(f"[comfyapp] sampler_profile: {_sampler_prof}")
                _sampler_prof.clear()
            # Guider profiling data
            _guider_prof = getattr(_samplers_mod, '_comfy_modal_guider_prof', None)
            if _guider_prof and _guider_prof.get("segments"):
                result["_guider_profile"] = dict(_guider_prof["segments"])
                _seg = _guider_prof["segments"]
                print(f"[comfyapp] guider_profile: {dict(_seg)}")
                _guider_prof["segments"].clear()
            # Deep profiling data
            import comfy as _comfy_mod
            _deep_prof = getattr(_comfy_mod, '_comfy_modal_deep_prof', None)
            if _deep_prof:
                result["_deep_profile"] = dict(_deep_prof)
                _dp_clean = {}
                for k, v in _deep_prof.items():
                    if isinstance(v, dict):
                        _dp_clean[k] = {kk: round(vv, 2) if isinstance(vv, (int, float)) else vv for kk, vv in v.items()}
                    elif isinstance(v, list):
                        _dp_clean[k] = [{kk: round(vv, 2) if isinstance(vv, (int, float)) else vv for kk, vv in c.items()} for c in v]
                    else:
                        _dp_clean[k] = round(v, 2) if isinstance(v, (int, float)) else v
                print(f"[comfyapp] deep_profile: {_dp_clean}")
                _deep_prof.clear()
            print(f"[comfyapp] cache_diagnostics: cpu_hits={result['_cache_diagnostics']['cpu_hits']} "
                  f"cpu_misses={result['_cache_diagnostics']['cpu_misses']} "
                  f"gpu_eq_calls={result['_cache_diagnostics']['gpu_eq'].get('calls', '?')} "
                  f"class_hits={result['_cache_diagnostics']['gpu_eq'].get('class_hits', '?')} "
                  f"misses={result['_cache_diagnostics']['gpu_eq'].get('misses', '?')} "
                  f"clip_hits={result['_cache_diagnostics']['clip_cache_hits']} "
                   f"clip_misses={result['_cache_diagnostics']['clip_cache_misses']}")
            _t8b_diag_print_ms = round((time.time() - _s) * 1000, 1)
            # Return payload logging
            _payload_images = result.get("images", [])
            _payload_videos = result.get("videos", [])
            _payload_image_count = len(_payload_images)
            _payload_video_count = len(_payload_videos)
            _payload_b64_bytes = sum(len(img.get("data", "")) for img in _payload_images)
            _payload_b64_bytes += sum(len(vid.get("data", "")) for vid in _payload_videos)
            _payload_json_approx = _payload_b64_bytes + len(json.dumps(result, separators=(",", ":")))
            print(f"[comfyapp] return_payload: images={_payload_image_count} videos={_payload_video_count} "
                  f"b64_bytes={_payload_b64_bytes} approx_json_bytes={_payload_json_approx}")
            result["_return_payload_info"] = {
                "image_count": _payload_image_count,
                "video_count": _payload_video_count,
                "b64_bytes": _payload_b64_bytes,
                "approx_json_bytes": _payload_json_approx,
            }
            _t8b_total_ms = round((time.time() - _t8b_t0) * 1000, 1)
            _t8b_unknown_ms = round(_t8b_total_ms - _t8b_save_stack_ms - _t8b_diag_ms - _t8b_profile_print_ms - _t8b_enrich_ms - _t8b_diag_print_ms, 1)
            _graph_validate_ms = _graph_validate_ms or 0.0
            print(f"[comfyapp] t8b_breakdown: total={_t8b_total_ms}ms "
                  f"save_stack={_t8b_save_stack_ms}ms "
                  f"diagnostics={_t8b_diag_ms}ms "
                  f"profile_print={_t8b_profile_print_ms}ms "
                  f"enrich={_t8b_enrich_ms}ms "
                  f"diag_print={_t8b_diag_print_ms}ms "
                  f"graph_validate={_graph_validate_ms}ms "
                  f"unknown={_t8b_unknown_ms}ms")
            result["_t8b_breakdown"] = {
                "t8b_total_ms": _t8b_total_ms,
                "t8b_save_stack_ms": _t8b_save_stack_ms,
                "t8b_diagnostics_ms": _t8b_diag_ms,
                "t8b_profile_print_ms": _t8b_profile_print_ms,
                "t8b_enrich_ms": _t8b_enrich_ms,
                "t8b_diag_print_ms": _t8b_diag_print_ms,
                "graph_validate_ms": _graph_validate_ms,
                "t8b_unknown_ms": _t8b_unknown_ms,
            }

            # ── Return mode filtering (after full payload logging) ──────
            _return_mode = _resolve_return_mode()
            result["_return_payload_info"]["return_mode"] = _return_mode
            if _return_mode == "first_image_only" and result.get("images"):
                result["images"] = result["images"][:1]
                _new_b64 = sum(len(img.get("data", "")) for img in result["images"])
                result["_return_payload_info"]["b64_bytes"] = _new_b64
                print(f"[comfyapp] return_mode=first_image_only: kept 1/{_payload_image_count} images, b64={_new_b64}")
            elif _return_mode == "metadata_only":
                for _img in result.get("images", []):
                    _img.pop("data", None)
                for _vid in result.get("videos", []):
                    _vid.pop("data", None)
                result["_return_payload_info"]["b64_bytes"] = 0
                print(f"[comfyapp] return_mode=metadata_only: stripped data from {_payload_image_count} images/{_payload_video_count} videos")
            elif _return_mode == "paths_only":
                import os as _os
                for _img in result.get("images", []):
                    _data = _img.pop("data", "")
                    _img["path"] = _os.path.join("/root/comfy/ComfyUI/output", _img.get("filename", ""))
                for _vid in result.get("videos", []):
                    _data = _vid.pop("data", "")
                    _vid["path"] = _os.path.join("/root/comfy/ComfyUI/output", _vid.get("filename", ""))
                result["_return_payload_info"]["b64_bytes"] = 0
                print(f"[comfyapp] return_mode=paths_only: {_payload_image_count} images, {_payload_video_count} videos")
            # Cache size before real prompt
            try:
                import nodes
                _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                    result["_return_payload_info"]["clip_cache_size_before_prompt"] = len(_te_cls._clip_text_cache)
            except Exception:
                pass
            return result

        # ── Subprocess backend: HTTP-based submission ──
        import base64
        import httpx
        from pathlib import Path

        total_started = time.time()
        input_count = 0
        input_bytes = 0

        if input_images:
            input_started = time.time()
            input_dir = Path("/root/comfy/ComfyUI/input")
            input_dir.mkdir(parents=True, exist_ok=True)
            for filename, b64data in input_images.items():
                dest = input_dir / Path(filename).name
                raw = base64.b64decode(b64data)
                dest.write_bytes(raw)
                input_count += 1
                input_bytes += len(raw)
            input_decode_ms = round((time.time() - input_started) * 1000, 1)
            print(
                f"[comfyapp.profile] stage=input_decode_write duration_ms={input_decode_ms} "
                f"count={input_count} bytes={input_bytes}"
            )

        client_id = str(uuid.uuid4())

        requested_stack = extract_requested_model_stack(workflow)
        warmup_profile = load_warmup_profile()
        warmup_match = warmup_profile_matches_workflow(warmup_profile, requested_stack)
        print(
            f"[comfyapp.profile] stage=warmup_profile_match match={1 if warmup_match else 0} "
            f"requested={requested_stack} profile={warmup_profile}"
        )

        try:
            submit_started = time.time()
            r = self._http_client.post(
                "/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            r.raise_for_status()
            queued = r.json()
            submit_ms = round((time.time() - submit_started) * 1000, 1)
            print(f"[comfyapp.profile] stage=prompt_submit duration_ms={submit_ms}")
        except httpx.HTTPStatusError as e:
            # Read the response body for validation error details
            error_body = ""
            try:
                error_data = e.response.json()
                # Extract meaningful error info from ComfyUI's response
                node_errors = error_data.get("node_errors", {})
                if node_errors:
                    msgs = []
                    for node_id, err_info in node_errors.items():
                        class_type = err_info.get("class_type", f"Node {node_id}")
                        for err in err_info.get("errors", []):
                            msgs.append(f"{class_type}: {err.get('message', 'unknown error')}")
                    if msgs:
                        raise RuntimeError(f"Workflow validation failed: {'; '.join(msgs)}") from e
                # Fallback: use the message field
                msg = error_data.get("message", "") or error_data.get("error", "")
                if msg:
                    raise RuntimeError(f"Workflow validation failed: {msg}") from e
            except (json.JSONDecodeError, RuntimeError):
                if isinstance(sys.exc_info()[1], RuntimeError):
                    raise
            raise RuntimeError(f"ComfyUI rejected the prompt (HTTP {e.response.status_code}): {e.response.text[:500]}") from e

        prompt_id = queued["prompt_id"]
        profile: dict = {}
        result = self._poll_until_done(prompt_id, client_id, profile)

        # Persist the model stack for auto-warmup on next restart
        if requested_stack and any(requested_stack.values()):
            self._save_last_model_stack(requested_stack)

        total_ms = round((time.time() - total_started) * 1000, 1)
        print(
            f"[comfyapp.profile] stage=remote_total backend=subprocess prompt_id={prompt_id[:8]} duration_ms={total_ms} "
            f"output_images={profile.get('output_images', 0)} output_videos={profile.get('output_videos', 0)} "
            f"output_bytes={profile.get('output_bytes', 0)}"
        )
        server_trace.mark("t9_modal_return")
        print(server_trace.log_line())
        trace_summary = server_trace.summary()
        self._enrich_trace_with_restore_timing(trace_summary)
        result["trace"] = trace_summary
        result["_restore_timing"] = dict(getattr(self, "_last_restore_timing", {}))
        # Attach __eq__ hit/miss counters to restore_timing for diagnostics
        if getattr(self, '_comfy_modal_eq', None) is not None:
            c = self._comfy_modal_eq
            result["_restore_timing"]["eq_hits"] = c.get('class_size_hit', 0) + c.get('model_type_hit', 0)
            result["_restore_timing"]["eq_misses"] = c.get('class_size_miss', 0) + c.get('device_miss', 0)
            result["_restore_timing"]["eq_identity"] = c.get('identity_hit', 0)
            if self._comfy_modal_eq_samples:
                result["_restore_timing"]["eq_samples"] = '; '.join(self._comfy_modal_eq_samples[:5])
                self._comfy_modal_eq_samples.clear()
            print(f"[comfyapp] eq: hits={result['_restore_timing']['eq_hits']} misses={result['_restore_timing']['eq_misses']} {dict(c)}")
        return result

    def _enrich_trace_with_restore_timing(self, trace_summary: dict) -> None:
        """Merge per-phase restore timing into the trace summary (mutates in-place)."""
        restore_data = getattr(self, "_last_restore_timing", None)
        if restore_data:
            trace_summary["restore"] = dict(restore_data)

    def _poll_until_done(self, prompt_id: str, client_id: str, profile: dict | None = None) -> dict:
        delay = 0.25
        elapsed = 0.0
        poll_count = 0
        poll_started = time.time()
        while elapsed < 3600:
            poll_count += 1
            r = self._http_client.get(f"/history/{prompt_id}")
            history = r.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                print(f"[comfyapp] prompt {prompt_id} finished in {elapsed:.3f}s")
                poll_ms = round((time.time() - poll_started) * 1000, 1)
                sleep_ms = round(elapsed * 1000, 1)
                active_poll_ms = round(max(poll_ms - sleep_ms, 0.0), 1)
                print(
                    f"[comfyapp.profile] stage=poll prompt_id={prompt_id[:8]} duration_ms={poll_ms} "
                    f"poll_count={poll_count} sleep_ms={sleep_ms} active_poll_ms={active_poll_ms}"
                )
                return self._collect_outputs(outputs, profile)
            time.sleep(delay)
            elapsed += delay
        raise TimeoutError(f"Prompt {prompt_id} timed out")

    def _collect_outputs(self, outputs: dict, profile: dict | None = None) -> dict:
        import base64
        import urllib.parse

        collect_started = time.time()
        images = []
        videos = []
        total_bytes = 0

        for node_id, node_output in outputs.items():
            for img in node_output.get("images", []):
                raw = node_output.get("animated", False)
                if isinstance(raw, bool):
                    is_animated = raw
                else:
                    is_animated = raw[0] if raw else False
                params = urllib.parse.urlencode({
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                })
                r = self._http_client.get(f"/view?{params}")
                total_bytes += len(r.content)
                data = base64.b64encode(r.content).decode()
                entry = {"filename": img["filename"], "data": data, "node_id": node_id}
                if is_animated:
                    videos.append(entry)
                else:
                    images.append(entry)

            for vid in node_output.get("gifs", []):
                params = urllib.parse.urlencode({
                    "filename": vid["filename"],
                    "subfolder": vid.get("subfolder", ""),
                    "type": vid.get("type", "output"),
                })
                r = self._http_client.get(f"/view?{params}")
                total_bytes += len(r.content)
                data = base64.b64encode(r.content).decode()
                videos.append({"filename": vid["filename"], "data": data, "node_id": node_id})

        collect_ms = round((time.time() - collect_started) * 1000, 1)
        print(
            f"[comfyapp.profile] stage=output_collect duration_ms={collect_ms} "
            f"images={len(images)} videos={len(videos)} bytes={total_bytes}"
        )
        if profile is not None:
            profile["output_images"] = len(images)
            profile["output_videos"] = len(videos)
            profile["output_bytes"] = total_bytes
        return {"images": images, "videos": videos}

    def _record_runtime_state(self):
        self._models_state = model_volume_state(MODELS_PATH)
        self._custom_nodes_state = custom_node_volume_state(CUSTOM_NODES_PATH)

    def _runtime_state_payload(self) -> dict:
        current_models = model_volume_state(MODELS_PATH)
        current_nodes = custom_node_volume_state(CUSTOM_NODES_PATH)
        models_changed = current_models != getattr(self, "_models_state", None)
        custom_nodes_changed = current_nodes != getattr(self, "_custom_nodes_state", None)
        stale_reasons = []
        if models_changed:
            stale_reasons.append("models changed")
        if custom_nodes_changed:
            stale_reasons.append("custom nodes changed")
        return {
            "stale": bool(stale_reasons),
            "stale_reasons": stale_reasons,
            "models_changed": models_changed,
            "custom_nodes_changed": custom_nodes_changed,
        }

    @modal.method()
    def resync_runtime(self, scope: str = "all"):
        """Explicit in-container resync: reload volumes, sync custom nodes,
        reinstall changed requirements, and restart ComfyUI in place."""
        if getattr(self, "_resync_in_progress", False):
            return {"status": "conflict", "message": "resync already in progress"}
        self._resync_in_progress = True
        try:
            started = time.time()
            print(f"[comfyapp] resync_runtime scope={scope} starting")

            if scope in {"models", "all"}:
                vol.reload()
            if scope in {"custom_nodes", "all"}:
                custom_nodes_vol.reload()

            summary: dict = {"scope": scope}
            if scope in {"custom_nodes", "all"}:
                node_summary, _ = self._sync_custom_nodes_from_volume()
                summary["custom_nodes"] = node_summary
                summary["requirements"] = self._install_custom_node_requirements()

            self._record_runtime_state()
            self._restart_comfy()

            summary["runtime_state"] = self._runtime_state_payload()
            summary["duration_s"] = round(time.time() - started, 3)
            print(f"[comfyapp] resync_runtime scope={scope} took {summary['duration_s']:.3f}s")
            return {"status": "ok", **summary}
        finally:
            self._resync_in_progress = False

    @modal.method()
    def runtime_state(self) -> dict:
        """Return stale-runtime info by comparing current volume state
        against the last recorded in-memory state."""
        return self._runtime_state_payload()

    @modal.method()
    def health(self):
        return {"status": "ok"}

    @modal.method()
    def list_models(self):
        import os

        vol.reload()

        # Standalone folders shown as their own sections
        solo_folders = ["loras", "vae", "controlnet", "upscale_models",
                        "embeddings", "clip", "text_encoders"]
        result = {}
        for folder in solo_folders:
            folder_path = os.path.join(MODELS_PATH, folder)
            if not os.path.isdir(folder_path):
                result[folder] = []
                continue
            files = []
            for fname in sorted(os.listdir(folder_path)):
                fpath = os.path.join(folder_path, fname)
                if os.path.isfile(fpath):
                    files.append({"name": fname, "size": os.path.getsize(fpath), "folder": folder})
            result[folder] = files
        # Checkpoint-family folders all shown under "checkpoints" in the sidebar,
        # but each file carries its real "folder" so inject/delete uses the right path.
        checkpoint_family = ["checkpoints", "diffusion_models", "unet"]
        result["checkpoints"] = []
        for folder in checkpoint_family:
            folder_path = os.path.join(MODELS_PATH, folder)
            if not os.path.isdir(folder_path):
                continue
            for fname in sorted(os.listdir(folder_path)):
                fpath = os.path.join(folder_path, fname)
                if os.path.isfile(fpath):
                    result["checkpoints"].append({"name": fname, "size": os.path.getsize(fpath), "folder": folder})
        return result

    @modal.method()
    def delete_model(self, folder: str, filename: str):
        import os
        safe_folder = os.path.basename(folder)
        safe_file = os.path.basename(filename)
        target = os.path.join(MODELS_PATH, safe_folder, safe_file)
        if not os.path.isfile(target):
            return {"status": "error", "message": "File not found"}
        os.remove(target)
        vol.commit()
        return {"status": "ok", "deleted": f"{safe_folder}/{safe_file}"}


def _register_gpu_classes():
    for entry in GPU_CATALOG:
        if is_gpu_hidden(entry["value"]):
            continue
        profile = GPU_PROFILES[entry["profile"]]
        # Backward compatibility: the a10g worker keeps the legacy class name "ComfyAPI".
        class_name = entry["class_name"]
        Generated = type(class_name, (_ComfyAPIMixin,), {})
        Generated = modal.concurrent(
            target_inputs=profile["target_inputs"],
            max_inputs=profile["max_inputs"],
        )(Generated)
        Generated = app.cls(
            gpu=entry["modal_gpu"],
            cpu=profile["cpu"],
            memory=profile["memory"],
            timeout=3600,
            min_containers=0,
            # Scale down quickly to avoid holding GPU resources when idle
            scaledown_window=4,
            volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
            enable_memory_snapshot=True,
            # GPU snapshot: when enabled, _force_triton_during_snapshot() blocks
            # SageAttention C extensions (safe) while allowing ComfyUI GPU init.
            # The snapshot captures the CUDA context and compiled kernels.
            **({"experimental_options": {"enable_gpu_snapshot": True}} if ENABLE_GPU_SNAPSHOT else {}),
            secrets=[modal.Secret.from_name("comfyui-warmup-dev")],
        )(Generated)
        globals()[class_name] = Generated


_register_gpu_classes()
