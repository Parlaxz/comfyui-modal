import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import modal

from gpu_catalog import GPU_CATALOG, get_supported_gpus, is_gpu_hidden

DEFAULT_EXECUTION_BACKEND = os.getenv("COMFYMODAL_EXECUTION_BACKEND", "in_process")
ENABLE_WARMUP = os.getenv("COMFYMODAL_ENABLE_WARMUP", "0") == "1"
WARMUP_PROFILE = os.getenv("COMFYMODAL_WARMUP_PROFILE", "off")
WARMUP_CHECKPOINT = os.getenv("COMFYMODAL_WARMUP_CHECKPOINT", "").strip()
WARMUP_UNET = os.getenv("COMFYMODAL_WARMUP_UNET", "").strip()
WARMUP_CLIP1 = os.getenv("COMFYMODAL_WARMUP_CLIP1", "").strip()
WARMUP_CLIP2 = os.getenv("COMFYMODAL_WARMUP_CLIP2", "").strip()
WARMUP_VAE = os.getenv("COMFYMODAL_WARMUP_VAE", "").strip()
WARMUP_CLIP_TYPE = os.getenv("COMFYMODAL_WARMUP_CLIP_TYPE", "flux").strip() or "flux"


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
    """Return the configured pinned warmup profile, if any."""
    if WARMUP_CHECKPOINT:
        return {
            "mode": "checkpoint",
            "checkpoint": WARMUP_CHECKPOINT,
        }
    if WARMUP_UNET and WARMUP_CLIP1 and WARMUP_CLIP2 and WARMUP_VAE:
        clip1, clip2 = normalize_flux_clip_pair(WARMUP_CLIP1, WARMUP_CLIP2) if WARMUP_CLIP_TYPE == "flux" else (WARMUP_CLIP1, WARMUP_CLIP2)
        return {
            "mode": "split",
            "unet": WARMUP_UNET,
            "clip1": clip1,
            "clip2": clip2,
            "vae": WARMUP_VAE,
            "clip_type": WARMUP_CLIP_TYPE,
        }
    return {}


def extract_requested_model_stack(workflow: dict) -> dict:
    """Extract a minimal model stack from a workflow for warmup matching."""
    stack = {"checkpoint": [], "unet": [], "clip": [], "vae": []}
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
        elif class_type == "CLIPLoader":
            value = inputs.get("clip_name")
            if isinstance(value, str) and value and value not in stack["clip"]:
                stack["clip"].append(value)
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
    """
    if stack.get("checkpoint"):
        return {"mode": "checkpoint", "checkpoint": stack["checkpoint"][0]}
    if stack.get("unet") and stack.get("clip") and stack.get("vae"):
        clips = stack["clip"]
        clip1, clip2 = normalize_flux_clip_pair(clips[0], clips[-1] if len(clips) > 1 else clips[0])
        return {
            "mode": "split",
            "unet": stack["unet"][0],
            "clip1": clip1,
            "clip2": clip2,
            "vae": stack["vae"][0],
            "clip_type": "flux",
        }
    return {}


# Bump this version whenever comfyapp.py changes.
# The custom node compares this against the last deployed version
# and re-runs `modal deploy` only when the version changes.
COMFYAPP_VERSION = "2.3.0"

APP_NAME = "comfyui"
VOLUME_NAME = "comfyui-models"
CUSTOM_NODES_VOLUME_NAME = "comfyui-custom-nodes"
COMFYUI_PORT = 8188
COMFYUI_API_PORT = 8189
MODELS_PATH = "/root/models"
CUSTOM_NODES_PATH = "/root/custom_nodes_vol"
LAST_MODEL_STACK_PATH = "/root/models/.last_model_stack.json"
LAST_WARMUP_WORKFLOW_PATH = "/root/models/.last_warmup_workflow.json"

SUPPORTED_GPUS = get_supported_gpus()

GPU_PROFILES = {
    "budget": {"cpu": 2, "memory": 8192, "target_inputs": 1, "max_inputs": 1},
    "standard": {"cpu": 4, "memory": 32768, "target_inputs": 1, "max_inputs": 1},
    "high_mem": {"cpu": 4, "memory": 32768, "target_inputs": 1, "max_inputs": 1},
}

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "git",
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxrender1",
        "libxext6",
        "ffmpeg",
    )
    .pip_install("comfy-cli==1.3.7", "httpx>=0.27.0")
    .run_commands(
        "comfy --skip-prompt install --nvidia",
        gpu="a10g",
    )
    .add_local_python_source("gpu_catalog")
)

download_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("httpx>=0.27.0")
    .add_local_python_source("gpu_catalog")
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
    image=modal.Image.debian_slim(python_version="3.11").add_local_python_source("gpu_catalog"),
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
    image=modal.Image.debian_slim(python_version="3.11").add_local_python_source("gpu_catalog"),
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
    image=modal.Image.debian_slim(python_version="3.11").add_local_python_source("gpu_catalog"),
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
    image=modal.Image.debian_slim(python_version="3.11").add_local_python_source("gpu_catalog"),
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
        comfy_models = "/root/comfy/ComfyUI/models"
        if not os.path.islink(comfy_models):
            if os.path.isdir(comfy_models):
                import shutil
                shutil.rmtree(comfy_models)
            os.symlink(MODELS_PATH, comfy_models)

    def _save_last_model_stack(self, stack: dict) -> None:
        """Persist the model stack to the shared volume for auto-warmup."""
        try:
            os.makedirs(os.path.dirname(LAST_MODEL_STACK_PATH), exist_ok=True)
            tmp_path = f"{LAST_MODEL_STACK_PATH}.tmp"
            with open(tmp_path, "w") as f:
                json.dump(stack, f, indent=2, sort_keys=True)
            os.replace(tmp_path, LAST_MODEL_STACK_PATH)
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
        profile = load_warmup_profile()
        source = "env_vars"
        if not profile:
            profile = stack_to_profile(self._load_last_model_stack())
            source = "last_stack"
        if profile:
            print(f"[comfyapp] snapshot_preload_profile source={source} mode={profile.get('mode','?')} data={profile}")
        else:
            print(f"[comfyapp] snapshot_preload_profile source=none — no warmup profile configured")
        return profile

    def _snapshot_preload_paths(self, profile: dict) -> list[str]:
        """Resolve model file paths for snapshot CPU preload.

        Preloads all model files (checkpoint or split) into CPU RAM during
        startup so Modal's memory snapshot captures them.  On restore, the
        cached state dicts are returned by ``_patch_model_cpu_cache``,
        eliminating volume reads during the first prompt execution.
        """
        if not profile:
            print("[comfyapp] snapshot_preload_paths: no profile, nothing to preload")
            return []
        profile_mode = profile.get("mode", "")
        checks: list[tuple[str, str]] = []
        if profile_mode == "checkpoint":
            checks.append(("checkpoint", profile.get("checkpoint", "")))
        elif profile_mode == "split":
            checks.extend([
                ("unet", profile.get("unet", "")),
                ("clip", profile.get("clip1", "")),
                ("clip", profile.get("clip2", "")),
                ("vae", profile.get("vae", "")),
            ])
        paths = []
        seen = set()
        for bucket, filename in checks:
            if not filename:
                print(f"[comfyapp] snapshot_preload_paths: empty filename for bucket={bucket}, skipping")
                continue
            path = self._find_model_file(bucket, filename)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
                print(f"[comfyapp] snapshot_preload_paths: resolved bucket={bucket} name={filename} -> {path}")
            else:
                print(f"[comfyapp] snapshot_preload_paths: NOT FOUND bucket={bucket} name={filename}")
        print(f"[comfyapp] snapshot_preload_paths: resolved {len(paths)} paths: {[os.path.basename(p) for p in paths]}")
        return paths

    def _preload_models_to_cpu(self, file_paths: list[str]) -> dict:
        """Preload model state dicts into CPU RAM for snapshot capture.

        Loaded state dicts are stored in ``_model_cpu_cache``.  Modal's
        memory snapshot captures CPU RAM, so on restore these cached state
        dicts are available immediately without volume reads.  The
        ``_patch_model_cpu_cache`` wrapper returns deep copies of cached
        state dicts when ComfyUI requests a model file.
        """
        if not file_paths:
            return {"count": 0, "cached": []}
        if not hasattr(self, "_model_cpu_cache"):
            self._model_cpu_cache = {}
        _total_start = time.time()
        _total_bytes = 0
        for p in file_paths:
            try:
                _total_bytes += os.path.getsize(p)
            except OSError:
                pass
        print(
            f"[comfyapp] preload_models_to_cpu: files={len(file_paths)} "
            f"total_gb={round(_total_bytes / (1024**3), 2)} starting"
        )
        original_loader = getattr(self, "_original_model_loader", None)
        if original_loader is None:
            raise RuntimeError("Original ComfyUI model loader unavailable for CPU preload")

        cached = []
        for path in file_paths:
            filename = os.path.basename(path)
            if filename in self._model_cpu_cache:
                cached.append(filename)
                continue
            started = time.time()
            try:
                loaded = original_loader(path, return_metadata=True)
                if isinstance(loaded, tuple) and len(loaded) == 2:
                    state_dict, metadata = loaded
                else:
                    state_dict, metadata = loaded, None
                self._model_cpu_cache[filename] = (state_dict, metadata)
                cached.append(filename)
                self._log_profile(
                    "snapshot_preload_model",
                    file=filename,
                    size_mb=round(os.path.getsize(path) / (1024 * 1024), 1),
                    duration_ms=self._profile_ms(started),
                )
            except Exception as exc:
                self._log_profile("snapshot_preload_model_failed", file=filename, error=str(exc)[:200])
        _total_ms = self._profile_ms(_total_start)
        _total_loaded_gb = sum(os.path.getsize(p) for p in file_paths if os.path.isfile(p)) / (1024**3)
        print(
            f"[comfyapp] preload_models_to_cpu: done in {_total_ms}ms "
            f"loaded={len(cached)} files={len(file_paths)} "
            f"loaded_gb={round(_total_loaded_gb, 2)} "
            f"throughput_gbps={round(_total_loaded_gb / max(_total_ms/1000, 0.001), 2)}"
        )
        return {"count": len(cached), "cached": cached}

    def _patch_model_cpu_cache(self, comfy_utils) -> None:
        """Patch ComfyUI model loading to reuse CPU-cached state dicts."""
        if getattr(self, "_model_cpu_cache_patched", False):
            return
        original_load = comfy_utils.load_torch_file
        self._original_model_loader = original_load

        def cached_load(path, *args, **kwargs):
            import copy

            filename = os.path.basename(path)
            cache = getattr(self, "_model_cpu_cache", {})
            if filename in cache:
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

    # ── Backend scaffold (warmup + execution backend selection) ──────────

    def _execute_in_process(self, workflow: dict, input_images: dict | None = None, collect_outputs: bool = True) -> dict:
        """Execute a ComfyUI workflow directly in-process.

        Args:
            workflow: ComfyUI workflow (dict of node-id → node-spec).
            input_images: Optional mapping of filename → base64-encoded data.

        Returns:
            ``{"images": [...], "videos": [...]}`` where each entry contains
            ``filename``, ``data`` (base64), and ``node_id``.
        """
        import base64
        import execution
        from pathlib import Path

        prompt_id = str(uuid.uuid4())

        # ── Write input images to ComfyUI's input directory ──
        stage_started = time.time()
        if input_images:
            inp = Path("/root/comfy/ComfyUI/input")
            inp.mkdir(parents=True, exist_ok=True)
            for fname, b64 in input_images.items():
                (inp / Path(fname).name).write_bytes(base64.b64decode(b64))
        self._log_profile("inproc_input_prepare", prompt_id=prompt_id[:8], count=len(input_images or {}), duration_ms=self._profile_ms(stage_started))

        # ── Validate (async in ComfyUI v0.22+) ──
        stage_started = time.time()
        valid, error, outputs_to_execute, node_errors = self._event_loop.run_until_complete(
            execution.validate_prompt(prompt_id, workflow, None)
        )
        self._log_profile("inproc_validate", prompt_id=prompt_id[:8], valid=1 if valid else 0, outputs=len(outputs_to_execute or []), duration_ms=self._profile_ms(stage_started))
        if not valid:
            parts = [error.get("message", str(error)) if isinstance(error, dict) else str(error)]
            if node_errors:
                for nid, info in node_errors.items():
                    ct = info.get("class_type", f"Node {nid}")
                    for e in info.get("errors", []):
                        parts.append(f"{ct}: {e.get('message', 'unknown error')}")
            raise RuntimeError(f"Workflow validation failed: {'; '.join(parts)}")

        # ── Reset execution-level accumulators ──
        self._exec_model_load_io_ms = 0.0
        self._exec_deepcopy_ms = 0.0
        self._log_profile("inproc_prep_done", prompt_id=prompt_id[:8], duration_ms=self._profile_ms(stage_started))
        _exec_stage = time.time()

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
        if getattr(self._executor, "success", True) is False:
            messages = getattr(self._executor, "status_messages", [])
            error_messages = []
            for event, payload in messages:
                if event == "execution_error" and isinstance(payload, dict):
                    error_messages.append(payload.get("exception_message", str(payload)))
            detail = "; ".join(error_messages) if error_messages else "ComfyUI execution failed"
            raise RuntimeError(detail)

        if not collect_outputs:
            return {"images": [], "videos": []}
        stage_started = time.time()
        result = self._collect_in_process_outputs(prompt_id)
        self._log_profile("inproc_collect", prompt_id=prompt_id[:8], images=len(result.get("images", [])), videos=len(result.get("videos", [])), duration_ms=self._profile_ms(stage_started))
        return result

    def _collect_in_process_outputs(self, prompt_id: str) -> dict:
        """Read generated outputs after an in-process execution.

        Prefers structured metadata from the prompt-queue history (which
        maps node-ids to filenames).  Falls back to scanning the output
        directory if history is not available.
        """
        import base64
        from pathlib import Path

        images: list[dict] = []
        videos: list[dict] = []
        outputs: dict = {}
        out_dir = Path("/root/comfy/ComfyUI/output")

        # ── Try executor history first (direct PromptExecutor execution does
        #    not necessarily populate PromptQueue.history). ──
        try:
            history_result = getattr(self._executor, "history_result", None)
            if isinstance(history_result, dict):
                outputs = history_result.get("outputs", {}) or {}
        except Exception:
            pass

        # ── Try structured queue history as a secondary source ──
        try:
            history = self._dummy_server.prompt_queue.history
            if not outputs and prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
        except Exception:
            pass

        if outputs:
            for node_id, node_out in outputs.items():
                for img in node_out.get("images", []):
                    fp = out_dir / img.get("subfolder", "") / img["filename"]
                    if not fp.is_file():
                        continue
                    _r_start = time.time()
                    raw = fp.read_bytes()
                    _r_ms = round((time.time() - _r_start) * 1000, 1)
                    if _r_ms > 100:
                        print(f"[comfyapp] slow output read: file={img['filename']} size={len(raw)} duration_ms={_r_ms}")
                    animated = bool(node_out.get("animated", False))
                    entry = {"filename": img["filename"], "data": base64.b64encode(raw).decode(), "node_id": node_id}
                    if animated:
                        videos.append(entry)
                    else:
                        images.append(entry)

                for vid in node_out.get("gifs", []):
                    fp = out_dir / vid["filename"]
                    if fp.is_file():
                        _r_start = time.time()
                        raw = fp.read_bytes()
                        _r_ms = round((time.time() - _r_start) * 1000, 1)
                        if _r_ms > 100:
                            print(f"[comfyapp] slow output read: file={vid['filename']} size={len(raw)} duration_ms={_r_ms}")
                        videos.append({"filename": vid["filename"], "data": base64.b64encode(raw).decode(), "node_id": node_id})
        else:
            # ── Fallback: scan for most recent files ──
            print("[comfyapp] output history not found, scanning output directory")
            if out_dir.is_dir():
                for f in sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
                    if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"):
                        images.append({"filename": f.name, "data": base64.b64encode(f.read_bytes()).decode(), "node_id": "0"})

        print(f"[comfyapp] collected {len(images)} images, {len(videos)} videos")
        return {"images": images, "videos": videos}

    def _select_backend(self) -> str:
        """Return the backend to use, sticky on subprocess fallback."""
        if getattr(self, "_backend_fallback", False):
            return "subprocess"
        return DEFAULT_EXECUTION_BACKEND

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
        import comfy.utils
        import execution
        import nodes
        import server as comfy_server
        self._log_profile("inproc_imports", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        self._patch_model_cpu_cache(comfy.utils)
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
                self._log_profile("inproc_exec_progress", event="execution_start", prompt_id=data.get("prompt_id","")[:8])
            elif event == "executing":
                node = data.get("node", None)
                now = time.time()
                if node is None:
                    # Log wall-clock time the PREVIOUS node consumed
                    if hasattr(self, "_perf_last_node") and self._perf_last_node is not None:
                        _pn = self._perf_last_node
                        _ps = (now - self._perf_last_ts) * 1000
                        print(f"[comfyapp.perf] node={_pn} duration_ms={_ps:.1f}")
                        # Also log total sampling time if this was a KSampler node
                    self._log_profile("inproc_exec_progress", event="execution_done")
                else:
                    if hasattr(self, "_perf_last_node") and self._perf_last_node is not None:
                        _pn = self._perf_last_node
                        _ps = (now - self._perf_last_ts) * 1000
                        print(f"[comfyapp.perf] node={_pn} duration_ms={_ps:.1f}")
                    self._perf_last_node = node
                    self._perf_last_ts = now
                    self._log_profile("inproc_exec_progress", event="executing_node", node=str(node)[:40])
            elif event == "progress":
                self._log_profile("inproc_exec_progress", event="progress", node=str(data.get("node",""))[:40], step=data.get("step",0), max=data.get("max",0))
            elif event == "execution_error":
                self._log_profile("inproc_exec_progress", event="execution_error", node=str(data.get("node",""))[:40])
        dummy._send_sync_callback = _on_sync

        # Register built-in + custom nodes (async in ComfyUI v0.22+)
        self._event_loop.run_until_complete(nodes.init_extra_nodes())
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
        """Build a tiny 1-step warmup workflow from the pinned warmup profile."""
        if profile.get("mode") == "checkpoint":
            return {
                "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": profile["checkpoint"]}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "warmup", "clip": ["3", 1]}},
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["3", 1]}},
                "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
                "10": {"class_type": "KSampler", "inputs": {
                    "seed": 1, "steps": 1, "cfg": 1.0,
                    "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                    "model": ["3", 0], "positive": ["6", 0],
                    "negative": ["7", 0], "latent_image": ["5", 0],
                }},
                "8": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 2]}},
                "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "warmup", "images": ["8", 0]}},
            }
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": profile["unet"], "weight_dtype": "default"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {
                "clip_name1": profile["clip1"],
                "clip_name2": profile["clip2"],
                "type": profile.get("clip_type", "flux"),
            }},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": profile["vae"]}},
            "4": {"class_type": "ModelSamplingFlux", "inputs": {
                "model": ["1", 0], "max_shift": 1.15, "base_shift": 0.5, "width": 1024, "height": 1024,
            }},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "warmup", "clip": ["2", 0]}},
            "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "7": {"class_type": "KSampler", "inputs": {
                "seed": 1, "steps": 1, "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                "model": ["4", 0], "positive": ["5", 0],
                "negative": ["5", 0], "latent_image": ["6", 0],
            }},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "warmup", "images": ["8", 0]}},
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
        profile = load_warmup_profile()
        replay_workflow = {}
        if not profile:
            replay_workflow = self._load_last_warmup_workflow()
        if not profile and not replay_workflow:
            profile = stack_to_profile(self._load_last_model_stack())
        if not profile and not replay_workflow:
            return {"mode": "none", "status": "disabled"}
        started = time.time()
        try:
            if replay_workflow:
                workflow = replay_workflow
                mode = "workflow"
            else:
                self._validate_warmup_profile_files(profile)
                workflow = self._build_warmup_workflow(profile)
                mode = profile.get("mode")
            if self._select_backend() == "in_process":
                self._execute_in_process(workflow, collect_outputs=False)
            else:
                self._submit_and_poll(workflow)
            duration_ms = round((time.time() - started) * 1000, 1)
            return {"mode": mode, "status": "ok", "duration_ms": duration_ms}
        except Exception as exc:
            import traceback
            duration_ms = round((time.time() - started) * 1000, 1)
            print(f"[comfyapp] auto-warmup failed after {duration_ms}ms:\n{traceback.format_exc()}")
            return {
                "mode": "workflow" if replay_workflow else profile.get("mode"),
                "status": "error",
                "duration_ms": duration_ms,
                "error": str(exc)[:500],
            }

    def _warmup_runtime(self) -> dict:
        """Warm up the ComfyUI runtime if enabled."""
        if not ENABLE_WARMUP:
            return {"enabled": False, "profile": WARMUP_PROFILE}
        t0 = time.time()
        try:
            if self._select_backend() == "in_process":
                # In-process: just verify the executor loaded successfully
                _ = self._executor
            else:
                self._http_client.get("/object_info")
            duration_s = round(time.time() - t0, 3)
            return {"enabled": True, "profile": WARMUP_PROFILE, "duration_s": duration_s, "status": "ok"}
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
        print("[comfyapp] lifecycle=startup snap=True")

        is_in_proc = (self._select_backend() == "in_process")

        if is_in_proc:
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

            stage_started = time.time()
            self._start_backend()

            self._log_profile("backend_start", backend=self._select_backend(), duration_ms=self._profile_ms(stage_started))

            preload_profile = self._snapshot_preload_profile()
            preload_paths = self._snapshot_preload_paths(preload_profile)
            stage_started = time.time()
            preload_summary = self._preload_models_to_cpu(preload_paths)
            self._log_profile(
                "snapshot_preload_cpu",
                mode=preload_profile.get("mode", "none") if preload_profile else "none",
                requested=len(preload_paths),
                cached=preload_summary.get("count", 0),
                duration_ms=self._profile_ms(stage_started),
            )
        else:
            self._ensure_models_symlink()
            manager_paths = set_manager_network_mode_offline()
            print(
                f"[comfyapp.profile] stage=manager_network_mode mode=offline paths={len(manager_paths)}"
            )
            vol.reload()
            _, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
            install_summary = self._install_custom_node_requirements()
            self._record_runtime_state()
            self._start_backend()

            # Warmup preload always runs during cold start (snap=True) for
            # subprocess — it populates ComfyUI's GPU model cache so that
            # subsequent scale-from-zero restores get instant cache hits.
            # ENABLE_WARMUP only gates the replay on *restore* (see restore()).
            preload_result = self._preload_warmup_profile()
            print(
                f"[comfyapp.profile] stage=warmup_preload mode={preload_result.get('mode', 'none')} "
                f"status={preload_result.get('status', 'unknown')} duration_ms={preload_result.get('duration_ms', 0)}"
            )

            warmup_result = self._warmup_runtime()
            print(f"[comfyapp] warmup={warmup_result}")

        duration = time.time() - t0
        print(f"[comfyapp] startup complete in {duration:.3f}s  "
              f"req_installed={install_summary['installed']}")

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
        # Force CUDA context reconnection (first call is slow if stale)
        torch.cuda.synchronize(dev)
        # Run a handful of GEMMs to coax GPU Boost out of its low-power state
        a = torch.randn(2048, 2048, device=dev)
        b = torch.randn(2048, 2048, device=dev)
        for _ in range(5):
            a = a @ b
        torch.cuda.synchronize(dev)
        # Use print to make it visible in container logs (log_profile may be buffered)
        print(f"[comfyapp] CUDA warmup done device={torch.cuda.get_device_name(dev)}")

    @modal.enter(snap=False)
    def restore(self):
        """Snapshot restore: lightweight sanity check only.

        No volume reloads, no custom-node sync, no requirements install
        — the snapshot already captured a ready state.

        * Subprocess backend:  a quick HTTP health probe may trigger a
          subprocess restart if the old process is dead.
        * In-process backend:  GPU is warmed up so the first prompt
          does not pay a cold-CUDA penalty.
        """
        restore_start = time.time()
        print("[comfyapp] lifecycle=restore snap=False")

        is_in_proc = (self._select_backend() == "in_process")

        self._ensure_models_symlink()

        if is_in_proc:
            _warm_start = time.time()
            self._warmup_cuda()
            self._log_profile("restore_warmup", mode="cuda_warmup", duration_ms=self._profile_ms(_warm_start))
        else:
            try:
                self._http_client.get("/system_stats", timeout=5)
            except Exception:
                print("[comfyapp] ComfyUI unresponsive on restore, restarting")
                self._restart_comfy()

        print(f"[comfyapp] restore sanity check done in {time.time() - restore_start:.3f}s")

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
    def run_prompt(self, workflow: dict, input_images: dict | None = None) -> dict:
        """Submit a workflow for execution.

        NOTE: This method does NOT reload Modal volumes or resync custom
        nodes.  After any model/custom-node mutation, callers must invoke
        ``resync_runtime()`` first so that the container picks up the
        changes before calling ``run_prompt()``.
        """

        # ── In-process backend: direct execution, no HTTP ──
        if self._select_backend() == "in_process":
            total_started = time.time()
            result = self._execute_in_process(workflow, input_images)
            requested_stack = extract_requested_model_stack(workflow)
            if requested_stack and any(requested_stack.values()):
                self._save_last_model_stack(requested_stack)
            total_ms = round((time.time() - total_started) * 1000, 1)
            print(
                f"[comfyapp.profile] stage=remote_total backend=in_process duration_ms={total_ms} "
                f"output_images={len(result.get('images', []))} "
                f"output_videos={len(result.get('videos', []))}"
            )
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
        return result

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
            experimental_options={"enable_gpu_snapshot": True},
        )(Generated)
        globals()[class_name] = Generated


_register_gpu_classes()
