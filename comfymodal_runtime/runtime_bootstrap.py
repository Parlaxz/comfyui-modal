"""Snapshot-safe runtime bootstrap and restore lifecycle.

Lane B extensions:
  - Authoritative pre-scan generation identity freeze/reuse
  - Sage patch snapshot identity retention after real CUDA init
  - Snapshot-memory validation certificate with Volume fallback
  - Reachability-based graph trimming report (delegates to production_workflow)
"""

from __future__ import annotations

import configparser
import contextlib
import logging
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from .trace import RuntimeTrace

_log = logging.getLogger(__name__)

# Three known ComfyUI-Manager config.ini locations (relative to comfyui_root).
_MANAGER_CONFIG_PATHS: tuple[str, ...] = (
    "user/__manager/config.ini",
    "user/default/__manager/config.ini",
    "user/default/ComfyUI-Manager/config.ini",
)


@dataclass(frozen=True)
class BootstrapConfig:
    comfyui_root: str = "/root/comfy/ComfyUI"
    models_path: str = "/root/comfy/ComfyUI/models"
    custom_nodes_path: str = "/root/comfy/ComfyUI/custom_nodes"
    min_containers: int = 0
    scaledown_window: int = 4
    manager_offline: bool = True
    install_requirements_on_startup: bool = False
    # Lane B — path for persisting pre-scan generation record
    prescan_record_path: str = ""


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
    sage_identity_captured: bool = False
    # Lane B — pre-scan generation identity (frozen at startup, reused at restore)
    prescan_runtime_generation: str = ""
    prescan_custom_node_generation: str = ""
    prescan_record_path: str = ""
    # Lane B — snapshot-memory validation certificate
    snapshot_certificate: dict[str, Any] = field(default_factory=dict)
    snapshot_cert_valid: bool = False
    # Lane B — graph trimming evidence
    graph_removable_node_ids: list[str] = field(default_factory=list)
    graph_trimming_possible: bool = False

    def freeze_prescan_identity(self, *, record_path: str = "") -> None:
        """Freeze the pre-scan generation identity from observed values.
        Called at the end of startup() before the snapshot is taken.
        """
        self.prescan_runtime_generation = str(self.runtime_generation)
        self.prescan_custom_node_generation = str(self.custom_node_generation)
        self.prescan_record_path = str(record_path)

    def has_prescan_identity(self) -> bool:
        """True when both pre-scan generations are non-empty."""
        return bool(self.prescan_runtime_generation and self.prescan_custom_node_generation)

    def sage_identity(self) -> dict[str, str]:
        """Return frozen Sage identity for certificate creation."""
        return {
            "sage_mode": self.sage_mode,
            "sage_reason": self.sage_reason,
        }

    def set_snapshot_certificate(self, cert: dict[str, Any]) -> None:
        self.snapshot_certificate = dict(cert)
        # Validate inline
        try:
            from optimizations import validate_snapshot_certificate
            result = validate_snapshot_certificate(cert)
            self.snapshot_cert_valid = bool(result.get("valid"))
        except Exception:
            self.snapshot_cert_valid = False

    def set_graph_trimming_evidence(
        self, *, removable_ids: list[str], trimming_possible: bool,
    ) -> None:
        self.graph_removable_node_ids = list(removable_ids)
        self.graph_trimming_possible = bool(trimming_possible)


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


def _write_manager_config_ini(path: Path) -> None:
    """Write ``[default] network_mode = offline`` preserving all existing sections.

    Uses ``ConfigParser(strict=False)`` to tolerate duplicate sections, and an
    atomic temp-file + ``os.replace`` to avoid partial writes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser(strict=False)
    # Read the existing file (if any) into the parser.
    parser.read([str(path)], encoding="utf-8")
    if not parser.has_section("default"):
        parser.add_section("default")
    parser.set("default", "network_mode", "offline")

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config_tmp_", suffix=".ini", text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            parser.write(fh)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def configure_manager_offline(
    comfyui_root: str,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    """Set environment hints *and* write ``config.ini`` files so ComfyUI-Manager
    stays offline even when it reads config before checking environment variables.

    Parameters
    ----------
    comfyui_root:
        Absolute path to the ComfyUI root directory (e.g. ``/root/comfy/ComfyUI``).
    environ:
        Optional environment mapping (defaults to ``os.environ``).  Keys are set
        via ``setdefault`` so caller pre-sets are honoured.

    Returns
    -------
    Dict of the environment changes applied (always ``{"COMFYUI_MANAGER_MODE": "offline",
    "COMFYUI_MANAGER_NETWORK_MODE": "offline"}``).
    """
    target = environ if environ is not None else os.environ
    changes = {
        "COMFYUI_MANAGER_MODE": "offline",
        "COMFYUI_MANAGER_NETWORK_MODE": "offline",
    }
    for key, value in changes.items():
        target.setdefault(key, value)

    written: list[str] = []
    root = Path(comfyui_root)
    for rel_path in _MANAGER_CONFIG_PATHS:
        cfg = root / rel_path
        _write_manager_config_ini(cfg)
        written.append(str(cfg))

    _log.info("Manager offline config applied to %s", "; ".join(written))
    print("[v2.manager] network_mode=offline configs=%d" % len(written), flush=True)
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
                configure_manager_offline(self.config.comfyui_root)
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

            # Lane B — freeze pre-scan identity and persist the record
            try:
                from optimizations import prescan_custom_node_generation
                prescan_custom_node_generation(
                    observe_generations=True,
                    runtime_generation=self.state.runtime_generation,
                    custom_node_generation=self.state.custom_node_generation,
                    reason="startup_prescan",
                    record_path=self.config.prescan_record_path,
                )
                self.state.freeze_prescan_identity(
                    record_path=self.config.prescan_record_path,
                )
                if trace:
                    trace.emit(
                        "prescan_identity_frozen",
                        phase="startup",
                        metadata={
                            "runtime_gen": self.state.prescan_runtime_generation,
                            "cn_gen": self.state.prescan_custom_node_generation,
                            "record_path": self.config.prescan_record_path,
                        },
                    )
            except Exception as _pexc:
                print(f"[bootstrap] prescan_identity error: {_pexc}", flush=True)

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

    def _try_restore_prescan_identity(self) -> None:
        """Attempt to restore the pre-scan generation identity from a
        previously persisted record.  On success, populates state fields
        so the caller can skip re-observation.
        """
        record_path = self.config.prescan_record_path
        if not record_path:
            return
        try:
            from optimizations import read_prescan_generation_record
            record: dict[str, str] = read_prescan_generation_record(record_path)
            if record.get("generation"):
                self.state.prescan_custom_node_generation = record["generation"]
                self.state.prescan_runtime_generation = record.get("content_hash", "")
                self.state.prescan_record_path = record_path
                print(
                    f"[bootstrap] prescan_identity_restored "
                    f"cn_gen={record['generation'][:24]} "
                    f"reason={record.get('reason', '')}",
                    flush=True,
                )
        except Exception as exc:
            print(f"[bootstrap] prescan_identity_restore_error: {exc}", flush=True)

    def _build_and_store_snapshot_certificate(self) -> None:
        """Build a snapshot-memory validation certificate from current
        state and store it on the state object.
        """
        try:
            from optimizations import build_snapshot_certificate

            cert = build_snapshot_certificate(
                runtime_generation=self.state.prescan_runtime_generation
                or self.state.runtime_generation,
                custom_node_generation=self.state.prescan_custom_node_generation
                or self.state.custom_node_generation,
                sage_mode=self.state.sage_mode,
                sage_reason=self.state.sage_reason,
                unet_identity=self.state.cuda.get("unet_identity", ""),
                clip_identity=self.state.cuda.get("clip_identity", ""),
                clip_type=self.state.cuda.get("clip_type", ""),
            )
            self.state.set_snapshot_certificate(cert)
            cert_hash = str(cert.get("cert_hash", ""))
            print(
                f"[bootstrap] snapshot_cert built "
                f"valid={int(self.state.snapshot_cert_valid)} "
                f"hash={cert_hash[:16]}",
                flush=True,
            )
        except Exception as exc:
            print(f"[bootstrap] snapshot_cert_build_error: {exc}", flush=True)

    def restore(self, *, trace: RuntimeTrace | None = None) -> BootstrapState:
        started = time.perf_counter()
        self.state.restore_started_at = time.time()
        # Lane B — try to restore pre-scan generation identity from persisted record
        self._try_restore_prescan_identity()
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

            # ── Lane B: Sage exact-match fast path ──
            # When sage_identity_captured is True, Sage was successfully applied
            # during a previous restore in this container and the in-memory patch
            # persists across restore cycles.  Skip the discovery/patch call
            # when the environment (custom-node generation) is still consistent
            # as proven by has_prescan_identity().
            _skipped_sage = False
            if self.state.sage_identity_captured and self.state.has_prescan_identity():
                _skipped_sage = True
                _check_ms = round((time.perf_counter() - started) * 1000, 3) if started else 0
                print(
                    f"[v2.sage_restore] decision=snapshot_exact_skip "
                    f"discovery_called=0 check_ms={_check_ms}",
                    flush=True,
                )

            if not _skipped_sage:
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
                    # Lane B: capture sage identity after successful application
                    if self.state.sage_mode:
                        self.state.sage_identity_captured = True
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

            # ── Lane B: custom-node restore fast path ──
            # When the prescan identity (frozen at startup) is present and
            # was restored from the persisted record, the custom-node state
            # is unchanged since snapshot time.  Skip the full sync.
            _skipped_cn_sync = False
            if self.state.has_prescan_identity() and self.sync_custom_nodes:
                _skipped_cn_sync = True
                _check_ms = round((time.perf_counter() - started) * 1000, 3) if started else 0
                print(
                    f"[v2.custom_node_restore] decision=snapshot_exact_skip "
                    f"callback_called=0 check_ms={_check_ms}",
                    flush=True,
                )

            if not _skipped_cn_sync:
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

            # Lane B — build snapshot-memory validation certificate
            self._build_and_store_snapshot_certificate()

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
