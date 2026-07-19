"""Snapshot-safe runtime bootstrap and restore lifecycle."""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from .trace import RuntimeTrace


@dataclass(frozen=True)
class BootstrapConfig:
    comfyui_root: str = "/root/comfy/ComfyUI"
    models_path: str = "/root/comfy/ComfyUI/models"
    custom_nodes_path: str = "/root/comfy/ComfyUI/custom_nodes"
    min_containers: int = 0
    scaledown_window: int = 4
    manager_offline: bool = True
    install_requirements_on_startup: bool = False


@dataclass
class BootstrapState:
    startup_started_at: float = 0.0
    startup_completed_at: float = 0.0
    restore_started_at: float = 0.0
    restore_completed_at: float = 0.0
    backend: str = ""
    cuda: dict[str, Any] = field(default_factory=dict)
    runtime_generation: str = ""
    custom_node_generation: str = ""
    errors: list[str] = field(default_factory=list)
    # Phase 3 — per-stage durations (ms) from trace events
    stage_durations: dict[str, float] = field(default_factory=dict)
    # Phase 0 — identity/environment metadata captured at lifecycle entry
    modal_task_id: str = ""
    modal_image_id: str = ""
    modal_cloud_provider: str = ""
    modal_region: str = ""
    # SageAttention policy observability
    sage_mode: str = ""
    sage_reason: str = ""


def ensure_models_symlink(models_path: str, comfyui_root: str) -> str:
    """Ensure ComfyUI resolves its model directory without copying models."""
    source = Path(models_path)
    destination = Path(comfyui_root) / "models"
    if destination.is_symlink():
        if destination.resolve() != source.resolve():
            destination.unlink()
    elif destination.exists():
        if destination.resolve() == source.resolve():
            return str(destination)
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source, target_is_directory=True)
    return str(destination)


def configure_manager_offline(environ: dict[str, str] | None = None) -> dict[str, str]:
    target = environ if environ is not None else os.environ
    changes = {
        "COMFYUI_MANAGER_MODE": "offline",
        "COMFYUI_MANAGER_NETWORK_MODE": "offline",
    }
    for key, value in changes.items():
        target.setdefault(key, value)
    return changes


@contextlib.contextmanager
def cpu_snapshot_environment() -> Iterator[None]:
    """Hide CUDA only while snapshot-time imports execute."""
    previous = os.environ.get("CUDA_VISIBLE_DEVICES")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = previous


class RuntimeBootstrap:
    """Coordinates exactly one CPU-snapshot and one post-restore lifecycle."""

    def __init__(
        self,
        config: BootstrapConfig | None = None,
        *,
        reload_models: Callable[[], Any] | None = None,
        reload_runtime_state: Callable[[], Any] | None = None,
        sync_custom_nodes: Callable[[], Any] | None = None,
        install_requirements: Callable[[], Any] | None = None,
        start_backend: Callable[[], Any] | None = None,
        restore_gpu_state: Callable[[], Any] | None = None,
        initialize_cuda: Callable[[], Any] | None = None,
        apply_sage_policy: Callable[[], Any] | None = None,
        observe_generations: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self.config = config or BootstrapConfig()
        self.reload_models = reload_models
        self.reload_runtime_state = reload_runtime_state
        self.sync_custom_nodes = sync_custom_nodes
        self.install_requirements = install_requirements
        self.start_backend = start_backend
        self.restore_gpu_state = restore_gpu_state
        self.initialize_cuda = initialize_cuda
        self.apply_sage_policy = apply_sage_policy
        self.observe_generations = observe_generations
        self.state = BootstrapState()
        self._backend_started = False

    def startup(self, *, snapshot: bool = True, trace: RuntimeTrace | None = None) -> BootstrapState:
        started = time.time()
        self.state.startup_started_at = started
        # Phase 0/3 — capture identity/environment metadata at lifecycle entry
        if trace:
            self.state.modal_task_id = os.environ.get("MODAL_TASK_ID", "")
            self.state.modal_image_id = os.environ.get("MODAL_IMAGE_ID", "")
            self.state.modal_cloud_provider = os.environ.get("MODAL_CLOUD_PROVIDER", "")
            self.state.modal_region = os.environ.get("MODAL_REGION", "")
            trace.emit(
                "snapshot_restore_start",
                phase="startup",
                metadata={
                    "modal_task_id": self.state.modal_task_id,
                    "modal_image_id": self.state.modal_image_id,
                    "modal_cloud_provider": self.state.modal_cloud_provider,
                    "modal_region": self.state.modal_region,
                    "snapshot_enabled": str(snapshot),
                },
            )
        try:
            if trace:
                trace.emit("models_symlink_start", phase="startup")
            ensure_models_symlink(self.config.models_path, self.config.comfyui_root)
            if trace:
                trace.emit("models_symlink_end", phase="startup")

            if trace:
                trace.emit("manager_offline_start", phase="startup")
            if self.config.manager_offline:
                configure_manager_offline()
            if trace:
                trace.emit("manager_offline_end", phase="startup")

            if trace:
                trace.emit("reload_models_start", phase="startup")
            if self.reload_models:
                self.reload_models()
            if trace:
                trace.emit("reload_models_end", phase="startup")

            if trace:
                trace.emit("reload_runtime_state_start", phase="startup")
            if self.reload_runtime_state:
                self.reload_runtime_state()
            if trace:
                trace.emit("reload_runtime_state_end", phase="startup")

            if trace:
                trace.emit("sync_custom_nodes_start", phase="startup")
            if self.sync_custom_nodes:
                self.sync_custom_nodes()
            if trace:
                trace.emit("sync_custom_nodes_end", phase="startup")

            if trace:
                trace.emit("install_requirements_start", phase="startup")
            if self.config.install_requirements_on_startup and self.install_requirements:
                self.install_requirements()
            if trace:
                trace.emit("install_requirements_end", phase="startup")

            if trace:
                trace.emit("comfyui_path_setup_start", phase="startup")
            self._import_comfyui_path()
            if trace:
                trace.emit("comfyui_path_setup_end", phase="startup")

            if trace:
                trace.emit("backend_startup_start", phase="startup")
            if self.start_backend and not self._backend_started:
                backend = self.start_backend()
                self.state.backend = str(backend or "in_process")
                self._backend_started = True
            if trace:
                trace.emit("backend_startup_end", phase="startup")

            if trace:
                trace.emit("observe_generations_start", phase="startup")
            if self.observe_generations:
                observed = self.observe_generations() or {}
                self.state.runtime_generation = str(observed.get("runtime_state", ""))
                self.state.custom_node_generation = str(observed.get("custom_nodes", ""))
            if trace:
                trace.emit("observe_generations_end", phase="startup")

            self.state.startup_completed_at = time.time()
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="startup",
                    metadata={"status": "ok"},
                )
                durations = trace.durations_ms()
                self.state.stage_durations.update(durations)
            return self.state
        except Exception as exc:
            self.state.errors.append(str(exc))
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="startup",
                    metadata={"status": "error", "error": str(exc)[:200]},
                )
            raise

    def restore(self, *, trace: RuntimeTrace | None = None) -> BootstrapState:
        started = time.time()
        self.state.restore_started_at = started
        # Phase 0/3 — capture identity/environment metadata at lifecycle entry
        if trace:
            self.state.modal_task_id = os.environ.get("MODAL_TASK_ID", "")
            self.state.modal_image_id = os.environ.get("MODAL_IMAGE_ID", "")
            self.state.modal_cloud_provider = os.environ.get("MODAL_CLOUD_PROVIDER", "")
            self.state.modal_region = os.environ.get("MODAL_REGION", "")
            trace.emit(
                "snapshot_restore_start",
                phase="restore",
                metadata={
                    "modal_task_id": self.state.modal_task_id,
                    "modal_image_id": self.state.modal_image_id,
                    "modal_cloud_provider": self.state.modal_cloud_provider,
                    "modal_region": self.state.modal_region,
                },
            )
        try:
            if trace:
                trace.emit("restore_gpu_state_start", phase="restore")
            if self.restore_gpu_state:
                self.restore_gpu_state()
            if trace:
                trace.emit("restore_gpu_state_end", phase="restore")

            if trace:
                trace.emit("cuda_init_start", phase="restore")
            if self.initialize_cuda:
                cuda_result = self.initialize_cuda()
                if isinstance(cuda_result, dict):
                    self.state.cuda = dict(cuda_result)
            if trace:
                trace.emit(
                    "cuda_init_end",
                    phase="restore",
                    metadata={
                        "device": str(self.state.cuda.get("device", "")),
                        "cuda_available": str(self.state.cuda.get("cuda_available", "")),
                    },
                )

            if trace:
                trace.emit("sage_policy_start", phase="restore")
            if self.apply_sage_policy:
                sage_result = self.apply_sage_policy()
                if isinstance(sage_result, bool):
                    self.state.sage_mode = "baked_cuda" if sage_result else "triton_fallback"
                    self.state.sage_reason = "patched" if sage_result else "not-patched-or-not-found"
                elif isinstance(sage_result, dict):
                    self.state.sage_mode = str(sage_result.get("mode", ""))
                    self.state.sage_reason = str(sage_result.get("reason", ""))
            if trace:
                trace.emit(
                    "sage_policy_end",
                    phase="restore",
                    metadata={
                        "sage_mode": self.state.sage_mode,
                        "sage_reason": self.state.sage_reason,
                    },
                )

            if trace:
                trace.emit("reload_runtime_state_start", phase="restore")
            if self.reload_runtime_state:
                self.reload_runtime_state()
            if trace:
                trace.emit("reload_runtime_state_end", phase="restore")

            if trace:
                trace.emit("reload_models_start", phase="restore")
            if self.reload_models:
                self.reload_models()
            if trace:
                trace.emit("reload_models_end", phase="restore")

            if trace:
                trace.emit("sync_custom_nodes_start", phase="restore")
            if self.sync_custom_nodes:
                self.sync_custom_nodes()
            if trace:
                trace.emit("sync_custom_nodes_end", phase="restore")

            if trace:
                trace.emit("observe_generations_start", phase="restore")
            if self.observe_generations:
                observed = self.observe_generations() or {}
                self.state.runtime_generation = str(observed.get("runtime_state", ""))
                self.state.custom_node_generation = str(observed.get("custom_nodes", ""))
            if trace:
                trace.emit("observe_generations_end", phase="restore")

            self.state.restore_completed_at = time.time()
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="restore",
                    metadata={"status": "ok"},
                )
                durations = trace.durations_ms()
                self.state.stage_durations.update(durations)
            return self.state
        except Exception as exc:
            self.state.errors.append(str(exc))
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="restore",
                    metadata={"status": "error", "error": str(exc)[:200]},
                )
            raise

    def _import_comfyui_path(self) -> None:
        root = self.config.comfyui_root
        if root and root not in sys.path and Path(root).exists():
            sys.path.insert(0, root)
