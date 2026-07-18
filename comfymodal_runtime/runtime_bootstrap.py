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
        if trace:
            trace.emit("snapshot_restore_start", phase="startup")
        try:
            ensure_models_symlink(self.config.models_path, self.config.comfyui_root)
            if self.config.manager_offline:
                configure_manager_offline()
            if self.reload_models:
                self.reload_models()
            if self.reload_runtime_state:
                self.reload_runtime_state()
            if self.sync_custom_nodes:
                self.sync_custom_nodes()
            self._import_comfyui_path()
            if self.start_backend and not self._backend_started:
                context = cpu_snapshot_environment() if snapshot else contextlib.nullcontext()
                with context:
                    backend = self.start_backend()
                self.state.backend = str(backend or "in_process")
                self._backend_started = True
            if self.observe_generations:
                observed = self.observe_generations() or {}
                self.state.runtime_generation = str(observed.get("runtime_state", ""))
                self.state.custom_node_generation = str(observed.get("custom_nodes", ""))
            self.state.startup_completed_at = time.time()
            if trace:
                trace.emit("snapshot_restore_end", phase="startup", metadata={"status": "ok"})
            return self.state
        except Exception as exc:
            self.state.errors.append(str(exc))
            if trace:
                trace.emit("snapshot_restore_end", phase="startup", metadata={"status": "error", "error": str(exc)[:200]})
            raise

    def restore(self, *, trace: RuntimeTrace | None = None) -> BootstrapState:
        started = time.time()
        self.state.restore_started_at = started
        if trace:
            trace.emit("snapshot_restore_start", phase="restore")
        try:
            if self.restore_gpu_state:
                self.restore_gpu_state()
            if trace:
                trace.emit("gpu_init_start", phase="restore")
            if self.initialize_cuda:
                cuda_result = self.initialize_cuda()
                if isinstance(cuda_result, dict):
                    self.state.cuda = dict(cuda_result)
            if trace:
                trace.emit("gpu_init_end", phase="restore", metadata=dict(self.state.cuda))
            if self.apply_sage_policy:
                self.apply_sage_policy()
            if self.reload_runtime_state:
                self.reload_runtime_state()
            if self.reload_models:
                self.reload_models()
            if self.sync_custom_nodes:
                self.sync_custom_nodes()
            if self.observe_generations:
                observed = self.observe_generations() or {}
                self.state.runtime_generation = str(observed.get("runtime_state", ""))
                self.state.custom_node_generation = str(observed.get("custom_nodes", ""))
            self.state.restore_completed_at = time.time()
            if trace:
                trace.emit("snapshot_restore_end", phase="restore", metadata={"status": "ok"})
            return self.state
        except Exception as exc:
            self.state.errors.append(str(exc))
            if trace:
                trace.emit("snapshot_restore_end", phase="restore", metadata={"status": "error", "error": str(exc)[:200]})
            raise

    def _import_comfyui_path(self) -> None:
        root = self.config.comfyui_root
        if root and root not in sys.path and Path(root).exists():
            sys.path.insert(0, root)
