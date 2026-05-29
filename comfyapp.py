import hashlib
import os
import subprocess
import sys
import time
import json
import uuid
from pathlib import Path

import modal


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
    .pip_install("comfy-cli==1.3.7")
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

    def _restart_comfy(self):
        if getattr(self, "_proc", None) and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = subprocess.Popen(
            ["comfy", "launch", "--", "--listen", "0.0.0.0", f"--port={COMFYUI_API_PORT}", "--disable-auto-launch"],
        )
        self._wait_for_comfy()

    @modal.enter(snap=True)
    def startup(self):
        import shutil

        t0 = time.time()

        # Symlink models from volume into ComfyUI
        comfy_models = "/root/comfy/ComfyUI/models"
        if os.path.isdir(comfy_models):
            shutil.rmtree(comfy_models)
        os.symlink(MODELS_PATH, comfy_models)

        vol.reload()
        _, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
        install_summary = self._install_custom_node_requirements()
        self._record_runtime_state()
        self._restart_comfy()

        duration = time.time() - t0
        print(f"[comfyapp] startup complete in {duration:.3f}s  "
              f"req_installed={install_summary['installed']}")

    @modal.enter(snap=False)
    def restore(self):
        """Snapshot restore: lightweight sanity check only.
        No volume reloads, no custom-node sync, no requirements install,
        no forced restart — the snapshot already captured a ready state."""
        restore_start = time.time()
        import shutil
        # Tiny local sanity: ensure the symlink still exists
        comfy_models = "/root/comfy/ComfyUI/models"
        if not os.path.islink(comfy_models):
            if os.path.isdir(comfy_models):
                shutil.rmtree(comfy_models)
            os.symlink(MODELS_PATH, comfy_models)
        print(f"[comfyapp] restore sanity check done in {time.time() - restore_start:.3f}s")

    @modal.exit()
    def shutdown(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _wait_for_comfy(self):
        import urllib.request
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{COMFYUI_API_PORT}/system_stats")
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError("ComfyUI API failed to start")

    @modal.method()
    def object_info(self):
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{COMFYUI_API_PORT}/object_info") as r:
            return json.loads(r.read())

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
        import urllib.request
        import urllib.error
        import base64
        from pathlib import Path

        if input_images:
            input_dir = Path("/root/comfy/ComfyUI/input")
            input_dir.mkdir(parents=True, exist_ok=True)
            for filename, b64data in input_images.items():
                dest = input_dir / Path(filename).name
                dest.write_bytes(base64.b64decode(b64data))

        client_id = str(uuid.uuid4())
        payload = json.dumps({"prompt": workflow, "client_id": client_id}).encode()

        req = urllib.request.Request(
            f"http://127.0.0.1:{COMFYUI_API_PORT}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as r:
                queued = json.loads(r.read())
        except urllib.error.HTTPError as e:
            # Read the response body for validation error details
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
                error_data = json.loads(error_body)
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
            raise RuntimeError(f"ComfyUI rejected the prompt (HTTP {e.code}): {error_body[:500]}") from e

        prompt_id = queued["prompt_id"]
        return self._poll_until_done(prompt_id, client_id)

    def _poll_until_done(self, prompt_id: str, client_id: str) -> dict:
        import urllib.request
        delay = 0.5
        elapsed = 0.0
        while elapsed < 3600:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{COMFYUI_API_PORT}/history/{prompt_id}"
            ) as r:
                history = json.loads(r.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                print(f"[comfyapp] prompt {prompt_id} finished in {elapsed:.3f}s")
                return self._collect_outputs(outputs)
            time.sleep(delay)
            elapsed += delay
            delay = min(delay * 1.5, 5.0)
        raise TimeoutError(f"Prompt {prompt_id} timed out")

    def _collect_outputs(self, outputs: dict) -> dict:
        import urllib.request
        import base64

        images = []
        videos = []

        for node_id, node_output in outputs.items():
            for img in node_output.get("images", []):
                animated = node_output.get("animated", (False,))
                is_animated = animated[0] if animated else False
                url = (
                    f"http://127.0.0.1:{COMFYUI_API_PORT}/view"
                    f"?filename={img['filename']}&subfolder={img.get('subfolder','')}&type={img.get('type','output')}"
                )
                with urllib.request.urlopen(url) as r:
                    data = base64.b64encode(r.read()).decode()
                entry = {"filename": img["filename"], "data": data, "node_id": node_id}
                if is_animated:
                    videos.append(entry)
                else:
                    images.append(entry)

            for vid in node_output.get("gifs", []):
                url = (
                    f"http://127.0.0.1:{COMFYUI_API_PORT}/view"
                    f"?filename={vid['filename']}&subfolder={vid.get('subfolder','')}&type={vid.get('type','output')}"
                )
                with urllib.request.urlopen(url) as r:
                    data = base64.b64encode(r.read()).decode()
                videos.append({"filename": vid["filename"], "data": data, "node_id": node_id})

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
@modal.concurrent(max_inputs=4)
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
@modal.concurrent(max_inputs=4)
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
@modal.concurrent(max_inputs=4)
class ComfyAPI_T4(_ComfyAPIMixin):
    pass
