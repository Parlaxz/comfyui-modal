import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import modal

DEFAULT_EXECUTION_BACKEND = os.getenv("COMFYMODAL_EXECUTION_BACKEND", "subprocess")
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


def load_warmup_profile() -> dict:
    """Return the configured pinned warmup profile, if any."""
    if WARMUP_CHECKPOINT:
        return {
            "mode": "checkpoint",
            "checkpoint": WARMUP_CHECKPOINT,
        }
    if WARMUP_UNET and WARMUP_CLIP1 and WARMUP_CLIP2 and WARMUP_VAE:
        return {
            "mode": "split",
            "unet": WARMUP_UNET,
            "clip1": WARMUP_CLIP1,
            "clip2": WARMUP_CLIP2,
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


# Bump this version whenever comfyapp.py changes.
# The custom node compares this against the last deployed version
# and re-runs `modal deploy` only when the version changes.
COMFYAPP_VERSION = "2.0.4"

APP_NAME = "comfyui"
VOLUME_NAME = "comfyui-models"
CUSTOM_NODES_VOLUME_NAME = "comfyui-custom-nodes"
COMFYUI_PORT = 8188
COMFYUI_API_PORT = 8189
MODELS_PATH = "/root/models"
CUSTOM_NODES_PATH = "/root/custom_nodes_vol"

SUPPORTED_GPUS = ["a10g", "a100", "t4"]

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
)

download_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("httpx>=0.27.0")
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
    image=modal.Image.debian_slim(python_version="3.11"),
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
    image=modal.Image.debian_slim(python_version="3.11"),
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
    image=modal.Image.debian_slim(python_version="3.11"),
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
    image=modal.Image.debian_slim(python_version="3.11"),
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

    def _sync_custom_nodes_from_volume(self):
        custom_nodes_vol.reload()
        comfy_custom_nodes = "/root/comfy/ComfyUI/custom_nodes"
        summary = sync_custom_nodes_into_comfy(CUSTOM_NODES_PATH, comfy_custom_nodes)
        state = custom_node_volume_state(CUSTOM_NODES_PATH)
        return summary, state

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

    def _select_backend(self) -> str:
        """Return the backend to use, sticky on subprocess fallback."""
        if getattr(self, "_backend_fallback", False):
            return "subprocess"
        return DEFAULT_EXECUTION_BACKEND

    def _start_in_process_backend(self):
        """Start ComfyUI in-process (not yet implemented)."""
        raise NotImplementedError(
            "In-process execution backend is not yet implemented. "
            "Falling back to subprocess backend."
        )

    def _start_backend(self):
        """Select and start the execution backend."""
        backend = self._select_backend()
        print(f"[comfyapp] selected backend={backend}")
        if backend == "in_process":
            try:
                self._start_in_process_backend()
            except NotImplementedError:
                print("[comfyapp] in_process backend unavailable, falling back to subprocess")
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
        """Preload and warm the pinned model stack before snapshot capture."""
        profile = load_warmup_profile()
        if not profile:
            return {"mode": "none", "status": "disabled"}
        started = time.time()
        try:
            workflow = self._build_warmup_workflow(profile)
            self._submit_and_poll(workflow)
            duration_ms = round((time.time() - started) * 1000, 1)
            return {"mode": profile.get("mode"), "status": "ok", "duration_ms": duration_ms}
        except Exception as exc:
            duration_ms = round((time.time() - started) * 1000, 1)
            return {
                "mode": profile.get("mode"),
                "status": "error",
                "duration_ms": duration_ms,
                "error": str(exc)[:200],
            }

    def _warmup_runtime(self) -> dict:
        """Warm up the ComfyUI runtime if enabled."""
        if not ENABLE_WARMUP:
            return {"enabled": False, "profile": WARMUP_PROFILE}
        t0 = time.time()
        try:
            self._http_client.get("/object_info")
            duration_s = round(time.time() - t0, 3)
            return {"enabled": True, "profile": WARMUP_PROFILE, "duration_s": duration_s, "status": "ok"}
        except Exception as exc:
            duration_s = round(time.time() - t0, 3)
            print(f"[comfyapp] warmup failed after {duration_s:.3f}s: {exc}")
            return {"enabled": True, "profile": WARMUP_PROFILE, "duration_s": duration_s, "status": "error", "error": str(exc)[:200]}

    def _restart_comfy(self):
        if self._http_client_obj is not None:
            self._http_client_obj.close()
            self._http_client_obj = None
        if getattr(self, "_proc", None) and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = subprocess.Popen(
            [
                "comfy", "launch", "--", "--listen", "0.0.0.0",
                f"--port={COMFYUI_API_PORT}", "--disable-auto-launch",
                "--gpu-only", "--disable-smart-memory", "--cache-classic",
            ],
        )
        self._wait_for_comfy()

    @modal.enter(snap=True)
    def startup(self):
        t0 = time.time()
        print("[comfyapp] lifecycle=startup snap=True")

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

    @modal.enter(snap=False)
    def restore(self):
        """Snapshot restore: lightweight sanity check only.
        No volume reloads, no custom-node sync, no requirements install
        — the snapshot already captured a ready state.  A quick health
        probe may trigger a restart if the subprocess is dead."""
        restore_start = time.time()
        print("[comfyapp] lifecycle=restore snap=False")
        self._ensure_models_symlink()
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
        import base64
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
        total_ms = round((time.time() - total_started) * 1000, 1)
        print(
            f"[comfyapp.profile] stage=remote_total prompt_id={prompt_id[:8]} duration_ms={total_ms} "
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

            summary["runtime_state"] = self.runtime_state()
            summary["duration_s"] = round(time.time() - started, 3)
            print(f"[comfyapp] resync_runtime scope={scope} took {summary['duration_s']:.3f}s")
            return {"status": "ok", **summary}
        finally:
            self._resync_in_progress = False

    @modal.method()
    def runtime_state(self) -> dict:
        """Return stale-runtime info by comparing current volume state
        against the last recorded in-memory state."""
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


@app.cls(
    gpu="a10g",
    cpu=4,
    memory=16384,
    timeout=3600,
    min_containers=0,
    # Scale down quickly to avoid holding GPU resources when idle
    scaledown_window=4,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(target_inputs=1, max_inputs=1)
class ComfyAPI(_ComfyAPIMixin):
    pass


@app.cls(
    gpu="a100",
    cpu=4,
    memory=32768,
    timeout=3600,
    min_containers=0,
    # Scale down quickly to avoid holding GPU resources when idle
    scaledown_window=4,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(target_inputs=1, max_inputs=1)
class ComfyAPI_A100(_ComfyAPIMixin):
    pass


@app.cls(
    gpu="t4",
    cpu=2,
    memory=8192,
    timeout=3600,
    min_containers=0,
    # Scale down quickly to avoid holding GPU resources when idle
    scaledown_window=4,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(target_inputs=1, max_inputs=1)
class ComfyAPI_T4(_ComfyAPIMixin):
    pass
