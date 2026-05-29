import os
import re
from typing import Iterable


ALLOWED_MODEL_FOLDERS = (
    "checkpoints",
    "diffusion_models",
    "unet",
    "loras",
    "vae",
    "controlnet",
    "upscale_models",
    "embeddings",
    "clip",
    "text_encoders",
    "model_patches",
    "clip_vision",
    "style_models",
    "vae_approx",
    "hypernetworks",
    "gligen",
    "photomaker",
    "latent_upscale_models",
    "audio_encoders",
    "frame_interpolation",
)

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def normalize_model_folder(folder: str) -> str:
    if not isinstance(folder, str):
        raise ValueError("folder must be a string")

    normalized = folder.strip().replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("folder required")
    if "/" in normalized or normalized not in ALLOWED_MODEL_FOLDERS:
        raise ValueError(f"unsupported model folder: {folder}")
    return normalized


def normalize_model_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise ValueError("filename must be a string")

    normalized = filename.strip()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("filename required")
    if "/" in normalized or "\\" in normalized:
        raise ValueError(f"unsafe filename: {filename}")
    if _WINDOWS_DRIVE_RE.match(normalized):
        raise ValueError(f"unsafe filename: {filename}")
    if os.path.isabs(normalized):
        raise ValueError(f"unsafe filename: {filename}")
    return normalized


def _local_models_dir(comfyui_root: str) -> str:
    return os.path.join(os.path.abspath(comfyui_root), "models")


def _local_model_path(comfyui_root: str, folder: str, filename: str) -> tuple[str, str, str]:
    safe_folder = normalize_model_folder(folder)
    safe_filename = normalize_model_filename(filename)
    local_dir = os.path.join(_local_models_dir(comfyui_root), safe_folder)
    local_path = os.path.join(local_dir, safe_filename)
    return safe_folder, safe_filename, local_path


def get_local_model_file_info(comfyui_root: str, folder: str, filename: str) -> dict:
    safe_folder, safe_filename, local_path = _local_model_path(comfyui_root, folder, filename)
    exists = os.path.isfile(local_path)
    size = os.path.getsize(local_path) if exists else 0
    return {
        "folder": safe_folder,
        "filename": safe_filename,
        "local_path": local_path,
        "exists": exists,
        "size": size,
        "is_placeholder": exists and size == 0,
        "is_real_file": exists and size > 0,
    }


def create_local_placeholder(comfyui_root: str, folder: str, filename: str) -> dict:
    info = get_local_model_file_info(comfyui_root, folder, filename)
    if info["exists"]:
        return {
            **info,
            "created": False,
            "existed": True,
        }

    os.makedirs(os.path.dirname(info["local_path"]), exist_ok=True)

    created = False
    try:
        with open(info["local_path"], "xb"):
            pass
        created = True
    except FileExistsError:
        created = False

    final_info = get_local_model_file_info(comfyui_root, folder, filename)
    return {
        **final_info,
        "created": created,
        "existed": not created,
    }


def create_local_placeholders(comfyui_root: str, items: Iterable[dict]) -> list[dict]:
    results = []
    for item in items:
        results.append(
            create_local_placeholder(
                comfyui_root,
                item.get("folder", ""),
                item.get("filename", ""),
            )
        )
    return results
