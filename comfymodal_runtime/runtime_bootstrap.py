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
from typing import Any, Callable, Iterator, Sequence

from .contracts import SnapshotExecutionSeed
from .trace import RuntimeTrace

_log = logging.getLogger(__name__)

# ── Sage snapshot identity constants ────────────────────────────────────
COMFYMODAL_SAGE_PATCH_VERSION: str = "comfymodal-sage-v1"
"""Repository-owned sentinel for Sage Python monkeypatch identification.

Set during CPU-snapshot-safe Sage pre-discovery. Verified at restore time
after CUDA init to decide whether full Sage discovery can be skipped.
Stable within this commit of comfyui-modal. Never contains user data,
CUDA handles, tensor objects, or model state.
"""

SNAPSHOT_SAGE_POLICY_VERSION: str = "1"
"""Snapshot-time Sage policy version. Bump when Sage integration changes."""


def _discover_and_patch_sage_cpu_snapshot(
    *,
    custom_node_generation: str = "",
    deployment_combined_hash: str = "",
    baked_cuda_available: bool = False,
) -> dict[str, str]:
    """CPU-snapshot-safe Sage pre-discovery.

    Imports the exact Sage integration, discovers the target function once,
    and installs a Python monkeypatch with a stable COMFYMODAL_SAGE_PATCH_VERSION
    sentinel. No CUDA/GPU/tensor/kernel/inference access.

    Returns a dict with snapshot identity fields:
      module_name, module_file_or_source_identity, target_attribute_path,
      patched_callable_qualname, patch_version, sage_mode, policy_version,
      custom_node_generation, deployment_combined_hash
    """
    result: dict[str, str] = {
        "module_name": "",
        "module_file_or_source_identity": "",
        "target_attribute_path": "",
        "patched_callable_qualname": "",
        "patch_version": COMFYMODAL_SAGE_PATCH_VERSION,
        "sage_mode": "",
        "policy_version": SNAPSHOT_SAGE_POLICY_VERSION,
        "custom_node_generation": custom_node_generation,
        "deployment_combined_hash": deployment_combined_hash,
    }
    try:
        # Discover Sage integration via the known production path:
        # ComfyUI KJNodes model_optimization_nodes.py and api._apply_sage_attention_policy.
        # The _apply_sage_attention_policy method iterates sys.modules looking for
        # model_optimization_nodes.py and calls patch_kjnodes_get_sage_func().
        # We do the same CPU-snapshot-safe discovery here without CUDA/tensor access.
        target = None
        target_mod = None
        target_attr_path = ""
        for mod in list(sys.modules.values()):
            file_name = getattr(mod, "__file__", "") or ""
            if file_name.endswith("model_optimization_nodes.py"):
                target_mod = mod
                target = getattr(mod, "get_sage_func", None)
                if callable(target):
                    target_attr_path = "get_sage_func"
                break

        if target_mod is not None:
            result["module_name"] = getattr(target_mod, "__name__", "")
            source_file = getattr(target_mod, "__file__", "")
            if source_file:
                import hashlib
                result["module_file_or_source_identity"] = hashlib.sha256(
                    source_file.encode("utf-8")
                ).hexdigest()[:16]

        if target is not None:
            integration = sys.modules.get("comfyapp")
            patcher = getattr(integration, "patch_kjnodes_get_sage_func", None)
            if callable(patcher):
                patcher(target_mod, baked_cuda_available=baked_cuda_available)
                target = getattr(target_mod, "get_sage_func", target)
            # Record qualified name
            if hasattr(target, "__qualname__"):
                result["patched_callable_qualname"] = target.__qualname__
            elif hasattr(target, "__name__"):
                result["patched_callable_qualname"] = target.__name__

            # Install the sentinel on the callable
            setattr(target, "_comfymodal_sage_patch_version", COMFYMODAL_SAGE_PATCH_VERSION)
            result["target_attribute_path"] = target_attr_path

        if target_mod is not None:
            # Mark the module with the sentinel too
            setattr(target_mod, "_comfymodal_sage_patch_version", COMFYMODAL_SAGE_PATCH_VERSION)

        if target is not None:
            result["sage_mode"] = "patched_at_snapshot"
        elif target_mod is not None:
            result["sage_mode"] = "module_found_no_target"
        else:
            result["sage_mode"] = "module_not_found"

        print(
            f"[v2.sage_snapshot] action=discover_and_patch "
            f"module={result['module_name']} "
            f"target={result['patched_callable_qualname']} "
            f"mode={result['sage_mode']} "
            f"version={COMFYMODAL_SAGE_PATCH_VERSION}",
            flush=True,
        )
    except Exception as exc:
        result["sage_mode"] = f"error:{str(exc)[:60]}"
    return result


def _verify_sage_snapshot_identity(
    *,
    snapshot_identity: dict[str, str],
    current_custom_node_generation: str = "",
    current_deployment_combined_hash: str = "",
) -> bool:
    """Verify that the in-memory Sage patch installed at snapshot time is
    still present and intact.  Returns True when the sentinel, version,
    and identity fields all match — meaning full Sage discovery can be
    skipped.  No CUDA/GPU access.
    """
    # Check the patched callable's sentinel
    mod_name = snapshot_identity.get("module_name", "")
    if not mod_name:
        return False
    mod = sys.modules.get(mod_name)
    if mod is None:
        return False
    # Check module-level sentinel
    if getattr(mod, "_comfymodal_sage_patch_version", "") != COMFYMODAL_SAGE_PATCH_VERSION:
        return False
    # Check target callable sentinel
    target_attr_path = snapshot_identity.get("target_attribute_path", "")
    if target_attr_path:
        parts = target_attr_path.split(".")
        obj = mod
        for part in parts:
            obj = getattr(obj, part, None)
            if obj is None:
                return False
        if getattr(obj, "_comfymodal_sage_patch_version", "") != COMFYMODAL_SAGE_PATCH_VERSION:
            return False
    else:
        # Fallback: check any callable on the module with the sentinel
        found = False
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name, None)
            if callable(attr) and getattr(attr, "_comfymodal_sage_patch_version", "") == COMFYMODAL_SAGE_PATCH_VERSION:
                found = True
                break
        if not found:
            return False
    # Check custom-node generation and deployment hash if provided
    if snapshot_identity.get("custom_node_generation") and current_custom_node_generation:
        if snapshot_identity["custom_node_generation"] != current_custom_node_generation:
            return False
    if snapshot_identity.get("deployment_combined_hash") and current_deployment_combined_hash:
        if snapshot_identity["deployment_combined_hash"] != current_deployment_combined_hash:
            return False
    # Check patch version
    if snapshot_identity.get("patch_version") != COMFYMODAL_SAGE_PATCH_VERSION:
        return False
    return True


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
    # Lane B — snapshot Sage identity (frozen at CPU-snapshot time, verified at restore)
    snapshot_sage_identity: dict[str, str] = field(default_factory=dict)
    # Lane B — snapshot custom-node identity (frozen at startup, used at restore)
    snapshot_custom_node_generation: str = ""
    snapshot_custom_node_source: str = ""
    snapshot_custom_node_schema: str = "0"
    deployment_combined_hash: str = ""
    # Lane B — snapshot-memory validation certificate
    snapshot_certificate: dict[str, Any] = field(default_factory=dict)
    snapshot_cert_valid: bool = False
    # Lane B — graph trimming evidence
    graph_removable_node_ids: list[str] = field(default_factory=list)
    graph_trimming_possible: bool = False
    # Lane B — SnapshotExecutionSeed (deterministic immutable cache seed)
    snapshot_execution_seed: SnapshotExecutionSeed | None = None
    snapshot_loader_outputs: dict[str, Any] = field(default_factory=dict)
    snapshot_model_identities: dict[str, str] = field(default_factory=dict)
    snapshot_seed_built: bool = False
    # -- Legacy prescan identity aliases (backward-compatible diagnostics) --
    prescan_runtime_generation: str = ""
    prescan_custom_node_generation: str = ""
    prescan_record_path: str = ""

    def has_prescan_identity(self) -> bool:
        """Backward-compatible diagnostic — checks frozen prescan identity."""
        return bool(self.prescan_custom_node_generation)

    def freeze_prescan_identity(self, *, record_path: str = "") -> None:
        """Backward-compatible diagnostic — freezes current generations
        into legacy prescan identity fields.
        """
        self.prescan_runtime_generation = self.runtime_generation
        self.prescan_custom_node_generation = self.custom_node_generation
        self.prescan_record_path = str(record_path)

    def build_snapshot_execution_seed(
        self,
        *,
        workflow_hash: str = "",
        output_node_ids: Sequence[str] = (),
        loader_node_ids: Sequence[str] = (),
        loader_cache_signatures: Sequence[dict[str, Any]] = (),
        sampler_node_ids: Sequence[str] = (),
        sampler_static_inputs: Sequence[dict[str, Any]] = (),
        custom_node_generation: str = "",
        deployment_combined_hash: str = "",
    ) -> SnapshotExecutionSeed:
        """Build and store a deterministic SnapshotExecutionSeed.

        Contains only identity fields — no outputs, latents, or random state.
        Used to seed the live executor.caches with snapshot-time model objects.
        """
        seed = SnapshotExecutionSeed(
            workflow_hash=str(workflow_hash),
            output_node_ids=tuple(str(i) for i in output_node_ids),
            loader_node_ids=tuple(str(i) for i in loader_node_ids),
            loader_cache_signatures=tuple(dict(item) for item in loader_cache_signatures),
            sampler_node_ids=tuple(str(i) for i in sampler_node_ids),
            sampler_static_inputs=tuple(dict(item) for item in sampler_static_inputs),
            custom_node_generation=str(custom_node_generation),
            deployment_combined_hash=str(deployment_combined_hash),
        )
        self.snapshot_execution_seed = seed
        self.snapshot_seed_built = True
        return seed

    def freeze_custom_node_identity(
        self, *,
        custom_node_generation: str = "",
        generation_source: str = "",
        schema_version: str = "0",
        deployment_combined_hash: str = "",
    ) -> None:
        """Freeze the custom-node identity from observed values at snapshot time."""
        self.snapshot_custom_node_generation = str(custom_node_generation)
        self.snapshot_custom_node_source = str(generation_source)
        self.snapshot_custom_node_schema = str(schema_version)
        self.deployment_combined_hash = str(deployment_combined_hash)

    def has_snapshot_custom_node_identity(self) -> bool:
        """True when a snapshot custom-node generation identity is present."""
        return bool(self.snapshot_custom_node_generation)

    def sage_identity(self) -> dict[str, str]:
        """Return frozen Sage identity for certificate creation."""
        return {
            "sage_mode": self.sage_mode,
            "sage_reason": self.sage_reason,
        }

    def set_snapshot_certificate(self, cert: dict[str, Any]) -> None:
        self.snapshot_certificate = dict(cert)
        # Validate inline - V2 certs use direct identity comparison
        # (cert_identity vs recomputed from identity_components).
        # V1/legacy certs fall back to the generic optimizer validator.
        try:
            sv = cert.get("schema_version")
            if sv == 2:
                # V2 validation: recompute identity from components
                import hashlib
                stored_identity = str(cert.get("cert_identity", "") or cert.get("identity", ""))
                components = cert.get("identity_components", {})
                if isinstance(components, dict) and stored_identity:
                    h = hashlib.sha256()
                    h.update(f"cert_schema={components.get('schema_version', '2')}\n".encode())
                    h.update(f"workflow_hash={components.get('workflow_hash', '')}\n".encode())
                    h.update(f"deployment_hash={components.get('deployment_hash', '')}\n".encode())
                    h.update(f"repair_mode={components.get('repair_mode', '')}\n".encode())
                    h.update(f"custom_nodes_generation={components.get('custom_nodes_generation', '')}\n".encode())
                    computed = h.hexdigest()
                    self.snapshot_cert_valid = (stored_identity == computed)
                else:
                    self.snapshot_cert_valid = False
            else:
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

    async def seed_loader_cache_signatures(
        self,
        executor: Any,
        *,
        loader_node_ids: Sequence[str] = (),
        loader_outputs: dict[str, Any] | None = None,
        workflow_hash: str = "",
        custom_node_generation: str = "",
        deployment_combined_hash: str = "",
        allow_cache: bool = True,
    ) -> dict[str, Any]:
        """Seed immutable loader outputs into executor.caches.outputs.

        Only seeds outputs from loader nodes (CLIPLoader, UNETLoader, VAELoader,
        CheckpointLoader, etc.) — nodes that produce deterministic model objects
        from file names.  Skips samplers, latents, random, prompt-dependent nodes.

        Returns diagnostics mapping node_id -> outcome.
        """
        import hashlib
        results: dict[str, Any] = {}
        if not allow_cache:
            return results
        caches = getattr(executor, "caches", None)
        if caches is None:
            return results
        outputs_cache = getattr(caches, "outputs", None)
        if outputs_cache is None:
            return results

        seed = self.snapshot_execution_seed
        if not seed:
            return results

        if workflow_hash and seed.workflow_hash and workflow_hash != seed.workflow_hash:
            return {str(node_id): "rejected:workflow_hash_mismatch" for node_id in loader_node_ids}
        if custom_node_generation and seed.custom_node_generation != custom_node_generation:
            return {str(node_id): "rejected:custom_node_generation_mismatch" for node_id in loader_node_ids}
        if deployment_combined_hash and seed.deployment_combined_hash != deployment_combined_hash:
            return {str(node_id): "rejected:deployment_hash_mismatch" for node_id in loader_node_ids}
        loader_sigs = {
            str(e.get("node_id", "")): e
            for e in seed.loader_cache_signatures
        }
        loader_outputs = loader_outputs or self.snapshot_loader_outputs
        try:
            from execution import CacheEntry
        except Exception:
            CacheEntry = None
        for node_id in loader_node_ids:
            node_id = str(node_id)
            if node_id not in loader_outputs or loader_outputs[node_id] is None:
                results[node_id] = "rejected:model_identity_missing"
                continue
            entry = loader_sigs.get(node_id)
            if entry is None:
                results[node_id] = "no_signature"
                continue
            expected_signature = entry.get("signature", entry.get("cache_key"))
            cache_key = outputs_cache.cache_key_set.get_data_key(node_id)
            if expected_signature not in (None, "") and str(cache_key) != str(expected_signature):
                results[node_id] = "rejected:loader_signature_mismatch"
                continue
            try:
                cached_entry = (
                    CacheEntry(ui={}, outputs=[loader_outputs[node_id]])
                    if CacheEntry is not None
                    else entry.get("cached_outputs")
                )
                if cached_entry is None:
                    results[node_id] = "rejected:cache_entry_unavailable"
                    continue
                await outputs_cache.set(node_id, cached_entry)
                identity_digest = hashlib.sha256(str(cache_key).encode("utf-8")).hexdigest()[:16]
                results[node_id] = f"seeded:{identity_digest}"
            except Exception as exc:
                results[node_id] = f"error:{str(exc)[:60]}"
        return results

    def prepare_restored_sampler_runtime(
        self,
        executor: Any,
        *,
        dit_model: Any = None,
        static_options: dict[str, Any] | None = None,
        sampler_class: Any = None,
    ) -> dict[str, Any]:
        """Perform deterministic idempotent CacheDiT attachment and
        RES4LYF static option/sampler construction.

        No sample/dummy forward — only identity-safe wiring.
        Returns diagnostics.
        """
        results: dict[str, Any] = {}
        if getattr(executor, "_comfymodal_sampler_runtime_prepared", False):
            return {"ok": True, "already_prepared": True}
        if dit_model is not None:
            try:
                from cache_dit import wrap_diffusion_model
                wrapped = wrap_diffusion_model(dit_model)
                executor._comfymodal_cachedit_model = wrapped
                results["cache_dit_wrapped"] = str(type(wrapped).__name__)
            except Exception as exc:
                results["cache_dit_error"] = str(exc)[:120]
        if static_options:
            try:
                options = dict(static_options)
                executor._res4lyf_static_options = options
                results["res4lyf_static_options"] = list(options.keys())
            except Exception as exc:
                results["res4lyf_options_error"] = str(exc)[:120]
        if sampler_class is not None:
            try:
                sampler = sampler_class()
                executor._res4lyf_sampler = sampler
                results["sampler_constructed"] = str(type(sampler).__name__)
            except Exception as exc:
                results["sampler_construction_error"] = str(exc)[:120]
        results["ok"] = len([k for k in results if "error" in k]) == 0
        if results["ok"]:
            executor._comfymodal_sampler_runtime_prepared = True
        return results


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
        read_current_custom_node_identity: Callable[[], dict[str, str]] | None = None,
        deployment_combined_hash: str = "",
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
        self.read_current_custom_node_identity = read_current_custom_node_identity
        self.state = BootstrapState()
        self._deployment_combined_hash = str(deployment_combined_hash or "")
        self._sage_baked_cuda_available = False
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
                self.state.snapshot_custom_node_source = str(
                    observed.get("custom_nodes_source", "") or ""
                )
            if trace:
                trace.emit("observe_generations_end", phase="startup")

            # ── Lane B: CPU-snapshot Sage pre-discovery ──
            # After all custom-node imports complete, discover and patch the
            # Sage target function with a stable sentinel. No CUDA/GPU access.
            _sage_snap_identity = _discover_and_patch_sage_cpu_snapshot(
                custom_node_generation=self.state.custom_node_generation,
                deployment_combined_hash=getattr(self, '_deployment_combined_hash', ''),
                baked_cuda_available=bool(
                    getattr(self, "_sage_baked_cuda_available", False)
                ),
            )
            self.state.snapshot_sage_identity = _sage_snap_identity
            if trace and _sage_snap_identity.get("sage_mode"):
                trace.emit(
                    "sage_snapshot_identity",
                    phase="startup",
                    metadata={
                        "sage_mode": _sage_snap_identity.get("sage_mode", ""),
                        "patch_version": _sage_snap_identity.get("patch_version", ""),
                        "target": _sage_snap_identity.get("patched_callable_qualname", ""),
                    },
                )

            # Lane B — freeze custom-node identity and persist the atomic versioned record
            _cn_identity_gen = self.state.custom_node_generation
            _cn_identity_src = (
                self.state.snapshot_custom_node_source or "observe_generations"
            )
            self.state.freeze_custom_node_identity(
                custom_node_generation=_cn_identity_gen,
                generation_source=_cn_identity_src,
                schema_version="1",
                deployment_combined_hash=getattr(self, '_deployment_combined_hash', ''),
            )
            # Persist atomic versioned record
            try:
                self._persist_custom_node_identity_record()
                if trace:
                    trace.emit(
                        "custom_node_identity_frozen",
                        phase="startup",
                        metadata={
                            "cn_gen": self.state.snapshot_custom_node_generation,
                            "source": _cn_identity_src,
                            "schema": self.state.snapshot_custom_node_schema,
                            "deployment_hash": self.state.deployment_combined_hash[:16] if self.state.deployment_combined_hash else "",
                        },
                    )
            except Exception as _pexc:
                print(f"[bootstrap] custom_node_identity_persist error: {_pexc}", flush=True)

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

    def _persist_custom_node_identity_record(self) -> None:
        """Persist an atomic versioned custom-node identity record to disk."""
        record_path = getattr(self.config, 'prescan_record_path', '')
        if not record_path:
            return
        import json
        payload = {
            "schema_version": self.state.snapshot_custom_node_schema,
            "custom_node_generation": self.state.snapshot_custom_node_generation,
            "generation_source": self.state.snapshot_custom_node_source,
            "deployment_combined_hash": self.state.deployment_combined_hash,
            "updated_at": time.time(),
        }
        tmp = f"{record_path}.tmp"
        os.makedirs(os.path.dirname(record_path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, record_path)

    def _read_current_custom_node_identity(self) -> dict[str, str]:
        """Authoritative-only read of the current custom-node identity.

        Reads only an O(1) existing runtime API token, a small deployment-
        produced generation record, or the immutable in-memory deployment
        identity.  No directory enumeration, hashing, requirements scan,
        fingerprint, repair, or Volume sync.

        Returns a dict with keys: ``custom_node_generation``, ``generation_source``,
        ``schema_version``, ``deployment_combined_hash``, ``token``.
        When the identity is unavailable, returns ``{"custom_node_generation": ""}``.
        """
        result: dict[str, str] = {
            "custom_node_generation": "",
            "generation_source": "unavailable",
            "schema_version": "0",
            "deployment_combined_hash": "",
            "token": "",
        }
        try:
            # 1) Try the runtime API token (fastest, O(1))
            api_token = getattr(self, '_current_api_token', None)
            if api_token:
                result["token"] = str(api_token)
        except Exception:
            pass
        try:
            # 2) Try the persisted record from deployment
            record_path = getattr(self.config, 'prescan_record_path', '')
            if record_path and os.path.exists(record_path):
                import json
                with open(record_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    gen = data.get("custom_node_generation", "")
                    if gen:
                        result["custom_node_generation"] = str(gen)
                        result["generation_source"] = str(data.get("generation_source", "persisted_record"))
                        result["schema_version"] = str(data.get("schema_version", "0"))
                        result["deployment_combined_hash"] = str(data.get("deployment_combined_hash", ""))
                        return result
        except Exception:
            pass
        # 3) Fallback: in-memory deployment identity from snapshot state
        try:
            if self.state.snapshot_custom_node_generation:
                result["custom_node_generation"] = self.state.snapshot_custom_node_generation
                result["generation_source"] = "snapshot_memory"
                result["schema_version"] = self.state.snapshot_custom_node_schema
                result["deployment_combined_hash"] = self.state.deployment_combined_hash
        except Exception:
            pass
        return result

    def _restore_prescan_identity(self) -> None:
        """Read the persisted prescan record and populate legacy identity fields.

        If a prescan record exists and has a non-empty custom_node_generation,
        sets prescan_custom_node_generation, prescan_runtime_generation, etc.
        on the state for backward-compatible diagnostic use.
        """
        record_path = getattr(self.config, 'prescan_record_path', '')
        if not record_path or not os.path.exists(record_path):
            return
        try:
            import json
            with open(record_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                gen = data.get("custom_node_generation", "") or data.get("generation", "")
                if gen:
                    self.state.prescan_custom_node_generation = str(gen)
                    self.state.prescan_runtime_generation = str(
                        data.get("runtime_generation", "") or data.get("content_hash", "")
                    )
                    self.state.prescan_record_path = record_path
                    print(
                        f"[bootstrap] prescan_identity_restored "
                        f"cn_gen={gen[:24]} source=persisted_record",
                        flush=True,
                    )
        except Exception as exc:
            print(f"[bootstrap] prescan_identity_restore_error: {exc}", flush=True)

    def _build_and_store_snapshot_certificate(self) -> None:
        """Build a snapshot-memory validation certificate from current
        state and store it on the state object.

        Uses V2 cert identity scheme with schema/identity_components for
        exact-match validation. Backward-compatible legacy fields
        (runtime_generation, custom_node_generation, sage_mode, sage_reason,
        unet_identity, clip_identity, clip_type, cert_hash) are retained for
        diagnostic compatibility with the V1 generic optimizer validator.

        After prompt validation in _execute_v2_prompt_executor, outputs_to_execute,
        node_errors, and preflight_ok are populated on the state cert to enable
        snapshot-memory preflight/validation skip on subsequent requests.
        """
        try:
            cn_gen = (self.state.prescan_custom_node_generation
                      or self.state.snapshot_custom_node_generation
                      or self.state.custom_node_generation)
            import hashlib

            # Build complete identity_components first, THEN compute identity
            wf_hash = getattr(self.state, '_last_workflow_hash', '')
            try:
                from .modal_app import _compute_v2_cert_identity
                cert_identity, identity_components = _compute_v2_cert_identity(
                    str(wf_hash),
                    repair_mode="off",
                    custom_nodes_generation=str(cn_gen),
                )
            except Exception:
                identity_components = {
                    "schema_version": "2",
                    "workflow_hash": str(wf_hash),
                    "deployment_hash": str(self.state.deployment_combined_hash),
                    "repair_mode": "off",
                    "custom_nodes_generation": str(cn_gen),
                }
                h = hashlib.sha256()
                h.update("cert_schema=2\n".encode())
                for key in sorted(identity_components):
                    h.update(f"{key}={identity_components[key]}\n".encode())
                cert_identity = h.hexdigest()

            # Build with V2 schema components + legacy diagnostic fields
            now = time.time()
            cert: dict[str, Any] = {
                # V2 primary schema
                "schema_version": 2,
                "identity": cert_identity,
                "identity_components": dict(identity_components),
                "cert_identity": cert_identity,
                # V2 payload fields for snapshot-memory hit eligibility
                "outputs_to_execute": [],
                "node_errors": {},
                "preflight_ok": False,
                # Legacy diagnostic fields (V1 optimizer validator compatible)
                "runtime_generation": self.state.runtime_generation,
                "custom_node_generation": cn_gen,
                "sage_mode": self.state.sage_mode,
                "sage_reason": self.state.sage_reason,
                "unet_identity": self.state.cuda.get("unet_identity", ""),
                "clip_identity": self.state.cuda.get("clip_identity", ""),
                "clip_type": self.state.cuda.get("clip_type", ""),
                "cert_hash": cert_identity[:32] if cert_identity else "",
                "deployment_combined_hash": self.state.deployment_combined_hash,
                "created_at": now,
            }
            self.state.set_snapshot_certificate(cert)
            cert_id_short = cert_identity[:16] if cert_identity else "none"
            print(
                f"[bootstrap] snapshot_cert v2 "
                f"valid={int(self.state.snapshot_cert_valid)} "
                f"identity={cert_id_short}",
                flush=True,
            )
        except Exception as exc:
            print(f"[bootstrap] snapshot_cert_build_error: {exc}", flush=True)

    def restore(self, *, trace: RuntimeTrace | None = None) -> BootstrapState:
        started = time.perf_counter()
        self.state.restore_started_at = time.time()
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
            # After initialize_cuda, read sys.modules and verify the snapshot
            # Sage identity sentinel.  Exact match skips full Sage discovery.
            _skipped_sage = False
            _sage_verify_ok = False
            if self.state.snapshot_sage_identity:
                _sage_current_identity = (
                    self.read_current_custom_node_identity()
                    if self.read_current_custom_node_identity is not None
                    else {}
                )
                _sage_verify_ok = bool(
                    not self.read_current_custom_node_identity
                    or _sage_current_identity.get("custom_node_generation")
                ) and _verify_sage_snapshot_identity(
                    snapshot_identity=self.state.snapshot_sage_identity,
                    current_custom_node_generation=str(
                        _sage_current_identity.get(
                            "custom_node_generation",
                            self.state.snapshot_custom_node_generation,
                        )
                    ),
                    current_deployment_combined_hash=str(
                        _sage_current_identity.get(
                            "deployment_combined_hash",
                            self.state.deployment_combined_hash,
                        )
                    ),
                )
            if _sage_verify_ok:
                _skipped_sage = True
                _check_ms = round((time.perf_counter() - started) * 1000, 3) if started else 0
                print(
                    f"[v2.sage_restore] decision=snapshot_exact_skip "
                    f"discovery_called=0 check_ms={_check_ms}",
                    flush=True,
                )
            else:
                # Log why we fell through
                if not self.state.snapshot_sage_identity:
                    _reason = "no_snapshot_sage_identity"
                else:
                    _reason = "verify_failed"
                print(
                    f"[v2.sage_restore] decision=fallback_full_discovery "
                    f"reason={_reason}",
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

            # Lane B: restore prescan identity from persisted record
            if self.read_current_custom_node_identity is None:
                self._restore_prescan_identity()

            # ── Lane B: custom-node restore fast path (authoritative-only) ──
            # Reads current authoritative-only identity and compares schema,
            # generation, and deployment hash against the snapshot identity.
            # Exact match skips sync_custom_nodes, observe_generations, and
            # fingerprint/hash scans.
            _check_start = time.perf_counter()
            _skipped_cn_sync = False
            _cn_decision = "snapshot_exact_skip"
            _cn_fallback_reason = ""

            _current_source = "unavailable"
            if self.read_current_custom_node_identity and self.sync_custom_nodes:
                current = self.read_current_custom_node_identity()
                _current_gen = current.get("custom_node_generation", "")
                _current_schema = current.get("schema_version", "0")
                _current_dep_hash = current.get("deployment_combined_hash", "")
                _current_source = current.get("generation_source", "unavailable")

                if not _current_gen:
                    _cn_fallback_reason = "missing_current_token"
                    _cn_decision = "fallback_full_sync"
                elif self.state.snapshot_custom_node_schema and _current_schema != self.state.snapshot_custom_node_schema:
                    _cn_fallback_reason = "schema_mismatch"
                    _cn_decision = "fallback_full_sync"
                elif self.state.snapshot_custom_node_generation and _current_gen != self.state.snapshot_custom_node_generation:
                    _cn_fallback_reason = "generation_mismatch"
                    _cn_decision = "fallback_full_sync"
                elif self.state.deployment_combined_hash and _current_dep_hash != self.state.deployment_combined_hash:
                    _cn_fallback_reason = "deployment_hash_mismatch"
                    _cn_decision = "fallback_full_sync"
                elif not self.state.has_snapshot_custom_node_identity():
                    _cn_fallback_reason = "untrusted_source"
                    _cn_decision = "fallback_full_sync"
                else:
                    _skipped_cn_sync = True
            elif self.state.has_prescan_identity() and self.sync_custom_nodes:
                # Fallback: use legacy prescan identity when read_current_custom_node_identity
                # is not provided (backward-compatible path for tests and simpler callers).
                _current_source = "prescan_identity"
                _skipped_cn_sync = True

            _check_ms = round((time.perf_counter() - _check_start) * 1000, 3)

            if _skipped_cn_sync:
                print(
                    f"[v2.custom_node_restore] "
                    f"decision={_cn_decision} "
                    f"callback_called=0 "
                    f"source={_current_source} "
                    f"check_ms={_check_ms}",
                    flush=True,
                )
            else:
                if _cn_fallback_reason:
                    print(
                        f"[v2.custom_node_restore] "
                        f"decision={_cn_decision} "
                        f"callback_called=1 "
                        f"source={_current_source if _current_source else 'unavailable'} "
                        f"check_ms={_check_ms} "
                        f"reason={_cn_fallback_reason}",
                        flush=True,
                    )
                if trace:
                    trace.emit("sync_custom_nodes_start", phase="restore")
                if self.sync_custom_nodes:
                    self.sync_custom_nodes()
                if trace:
                    trace.emit("sync_custom_nodes_end", phase="restore")
            if not _skipped_cn_sync:
                if trace:
                    trace.emit("observe_generations_start", phase="restore")
                if self.observe_generations:
                    observed = self.observe_generations() or {}
                    self.state.runtime_generation = str(observed.get("runtime_state", ""))
                    self.state.custom_node_generation = str(observed.get("custom_nodes", ""))
                if trace:
                    trace.emit("observe_generations_end", phase="restore")
                if self.state.custom_node_generation:
                    self.state.snapshot_custom_node_generation = self.state.custom_node_generation
                    self.state.snapshot_custom_node_source = "observe_generations"
                    try:
                        self._persist_custom_node_identity_record()
                    except Exception as _pexc:
                        print(f"[bootstrap] identity_publish_after_sync error: {_pexc}", flush=True)
            else:
                self.state.custom_node_generation = self.state.snapshot_custom_node_generation

            # Lane B — build snapshot-memory validation certificate
            self._build_and_store_snapshot_certificate()

            # Lane B — build SnapshotExecutionSeed from model identities
            _unet_id = self.state.cuda.get("unet_identity", "")
            _clip_id = self.state.cuda.get("clip_identity", "")
            _loader_sigs: list[dict[str, Any]] = []
            if _unet_id:
                _loader_sigs.append({"node_id": "unet", "signature": _unet_id})
            if _clip_id:
                _loader_sigs.append({"node_id": "clip", "signature": _clip_id})
            self.state.build_snapshot_execution_seed(
                workflow_hash=self.state.snapshot_certificate.get("identity_components", {}).get("workflow_hash", ""),
                custom_node_generation=self.state.snapshot_custom_node_generation,
                deployment_combined_hash=self.state.deployment_combined_hash,
                loader_cache_signatures=_loader_sigs,
            )
            if trace and self.state.snapshot_seed_built:
                trace.emit(
                    "snapshot_execution_seed_built",
                    phase="restore",
                    metadata={
                        "workflow_hash": (
                            self.state.snapshot_execution_seed.workflow_hash[:16]
                            if self.state.snapshot_execution_seed is not None else ""
                        ),
                        "loader_count": len(_loader_sigs),
                        "deployment_hash": self.state.deployment_combined_hash[:16] if self.state.deployment_combined_hash else "",
                    },
                )

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
