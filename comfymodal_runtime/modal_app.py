"""Deployable v2 Modal application and its runtime entrypoint."""

from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
import os
import time
import uuid
from types import MappingProxyType

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, ContextManager, Mapping, cast

from .contracts import DeploymentIdentity, ExecutionPlan, RestorePlan, _thaw, stable_hash
from .deployment_spec import build_deployment_identity
from .restore_plan import RestorePlanPublisher
from .runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from .runtime_executor import ExecutionContext, RuntimeExecutor
from .runtime_state import CommitCoordinator, ModalMountedStateVolume
from .model_preload import (
    V2LoaderBridge,
    RestorePreparation,
    _collect_restore_events_for_summary,
    get_restore_return_marker,
    gpu_not_observed_summary,
    request_execution_trace_scope,
    set_model_load_identity,
    set_restore_return_marker,
    _capture_host_info,
    _DIAGNOSTIC_FLAG as _MP_DIAGNOSTIC_FLAG,
)
from .output_delivery import (
    Attempt,
    _measure_json_bytes,
    build_default_chain,
    run_strategy_chain,
)
from .result_delivery import ConversionFailedError, convert_output_items
from .trace import RuntimeTrace, merge_runtime_traces

_V2_STAGE_MAP: tuple[tuple[str, str, str], ...] = (
    ("unet_load",      "t4b_unet_load_start",      "t4b_unet_load_end"),
    ("clip_load",      "t4_clip_load_start",       "t4_clip_load_end"),
    ("vae_load",       "t4c_vae_load_start",       "t4c_vae_load_end"),
    ("clip_encode",    "t5_text_encode_start",     "t5_text_encode_end"),
    ("sampler",        "t6_sampler_start",          "t6_sampler_end"),
    ("vae_decode",     "t7_vae_decode_start",       "t7_vae_decode_end"),
    ("cachedit",       "t8_cachedit_start",         "t8_cachedit_end"),
    ("noise_inject",   "t8_noise_inject_start",     "t8_noise_inject_end"),
    ("model_sampling", "t4d_model_sampling_start",  "t4d_model_sampling_end"),
    ("model_patch",    "t4e_model_patch_start",     "t4e_model_patch_end"),
    ("sampler_setup",  "t8_sampler_setup_start",    "t8_sampler_setup_end"),
)


try:
    import modal as _modal
except Exception:
    _modal = None


APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow").strip() or "stable-modal-comfy-v2-shadow"
MODELS_VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")
CUSTOM_NODES_VOLUME_NAME = os.environ.get("COMFYMODAL_CUSTOM_NODES_VOLUME", "comfyui-custom-nodes")
RUNTIME_STATE_VOLUME_NAME = os.environ.get("COMFYMODAL_RUNTIME_STATE_VOLUME", "comfymodal-runtime-config")
MODELS_PATH = "/root/models"
CUSTOM_NODES_PATH = "/root/custom_nodes_vol"
RUNTIME_STATE_PATH = "/root/comfymodal_runtime_state"
V2_RESTORE_STATE_FILE = "v2_restore_plan.json"
MIN_CONTAINERS = 0
SCALEDOWN_WINDOW = 4
CLASS_NAME = "ModalRuntimeEntrypoint"
# Process-local fallback for lifecycle timing when Modal separates enter/method instances.
# Both startup() and restore() refresh this; _run_in_process and run_plan_stream
# read it when self._restore_timing is None.
_LATEST_LIFECYCLE_TIMING: dict[str, Any] | None = None
_LATEST_RESTORED_INSTANCE_ID: str = ""
"""Module-level latest restored_instance_id.  Set by restore() after
snapshot restoration; read by background worker and graph-entry paths.
This is distinct from container_session_id: it changes on every restore
cycle while the container session persists across lifecycle."""

# V1-parity module-level stable identity so instance/snapshot boundaries cannot erase identity.
# Set once at import time, before any Modal instance construction.
_V2_CONTAINER_SESSION_ID: str = uuid.uuid4().hex[:16]
_V2_CONTAINER_IMPORT_UNIX_S: float = time.time()
_v2_container_restore_count: int = 0

# All local Python modules that comfyapp.py imports at the top level
# and that must be available in the remote V2 shadow container.
# External ComfyUI modules (nodes, server, folder_paths, torch, ...)
# are provided by the base runtime image — do not list them here.
V2_SOURCE_MODULES = (
    "api_prompt_validator",
    "canonical_execution",
    "comfyapp",
    "comfymodal_runtime",
    "failure_summary",
    "gpu_catalog",
    "modal_client",
    "optimizations",
    "production_workflow",
    "profiler_trace_v4",
    "run_prompt_options",
    "timing_trace",
    "wall_clock_trace_v3",
)

# ── V2 validation certificate (V1-parity persistent validation cache) ──
# Enabled by default.  Set COMFYMODAL_V2_VALIDATION_CERT=0 to disable.
# Certificates are stored on the runtime-state Volume keyed by a stable
# identity that includes workflow struct hash and deployment identity.
_V2_VALIDATION_CERT_ENABLED: bool = (
    os.environ.get("COMFYMODAL_V2_VALIDATION_CERT", "1") == "1"
)
_V2_CERT_SCHEMA_VERSION: int = 2
_V2_CERT_FILENAME_PREFIX: str = "v2_cert_"

# Pre-computed deployment identity hash for certificate identity.
# Populated at module level once during import.
_V2_DEPLOYMENT_COMBINED_HASH: str = ""


def _get_preflight_context(api: Any, module: Any) -> tuple[str, str]:
    """Extract cheap request-time preflight context from the loaded legacy API.

    Calls the authoritative helpers ``api._resolve_requirements_repair_mode()``
    and ``module._current_custom_nodes_generation_id()``.  Returns
    ``(repair_mode, custom_nodes_generation)``.  Either may be empty when
    the helpers are absent or raise — optimisation fails closed.
    """
    repair_mode = ""
    custom_nodes_gen = ""
    try:
        repair_mode = str(api._resolve_requirements_repair_mode() or "")
    except Exception:
        pass
    try:
        custom_nodes_gen = str(module._current_custom_nodes_generation_id() or "")
    except Exception:
        pass
    return repair_mode, custom_nodes_gen


def _compute_v2_cert_identity(
    workflow_hash: str,
    deployment_identity: DeploymentIdentity | None = None,
    repair_mode: str = "",
    custom_nodes_generation: str = "",
) -> tuple[str, dict[str, str]]:
    """Build a deterministic certificate identity from *workflow_hash*,
    the deployment's combined hash, and mutable preflight context.

    Returns ``(identity_hex, components_dict)``.  Identity is a SHA-256 hex
    string.  When *deployment_identity* is absent or empty, only the
    workflow_hash is used (deployment combined hash is empty — less
    discrimination but still safe).
    """
    import hashlib
    dep_hash = ""
    if deployment_identity is not None:
        dep_hash = deployment_identity.combined_hash
    h = hashlib.sha256()
    h.update(f"cert_schema={_V2_CERT_SCHEMA_VERSION}\n".encode())
    h.update(f"workflow_hash={workflow_hash}\n".encode())
    h.update(f"deployment_hash={dep_hash}\n".encode())
    h.update(f"repair_mode={repair_mode}\n".encode())
    h.update(f"custom_nodes_generation={custom_nodes_generation}\n".encode())
    identity = h.hexdigest()
    components = {
        "schema_version": str(_V2_CERT_SCHEMA_VERSION),
        "workflow_hash": workflow_hash,
        "deployment_hash": dep_hash,
        "repair_mode": repair_mode,
        "custom_nodes_generation": custom_nodes_generation,
    }
    return identity, components


def _v2_cert_filename(cert_identity: str) -> str:
    """Return the on-volume filename for a certificate identity."""
    return f"{_V2_CERT_FILENAME_PREFIX}{cert_identity}.json"


def _write_v2_validation_certificate(
    cert_identity: str,
    outputs_to_execute: list[str],
    node_errors: dict[str, Any],
    *,
    components: dict[str, str] | None = None,
    preflight_ok: bool = False,
) -> bool:
    """Write a validation certificate to the runtime-state volume.

    When *preflight_ok* is True the certificate attests that deterministic
    preflight completed successfully for this identity.  Schema v2+ requires
    preflight_ok to be True for the certificate to be eligible as a preflight
    skip.

    Never raises.  Returns True on success, False on any error.
    The certificate is written atomically and committed immediately.
    """
    try:
        import json as _json
        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            return False
        from .runtime_state import ModalMountedStateVolume
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
        filename = _v2_cert_filename(cert_identity)
        payload = {
            "schema_version": _V2_CERT_SCHEMA_VERSION,
            "identity": cert_identity,
            "created_at": time.time(),
            "outputs_to_execute": outputs_to_execute,
            "node_errors": dict(node_errors or {}),
            "preflight_ok": bool(preflight_ok),
        }
        if components:
            payload["identity_components"] = dict(components)
        encoded = _json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        volume.write_bytes(filename, encoded)
        volume.commit()
        print(
            f"[v2.cert] write identity={cert_identity[:16]} status=committed",
            flush=True,
        )
        return True
    except Exception as exc:
        print(
            f"[v2.cert] write identity={cert_identity[:16]} status=error error={str(exc)[:120]}",
            flush=True,
        )
        return False


def _read_and_validate_cert_payload(
    volume: Any,
    cert_identity: str,
    *,
    expected_components: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Read and validate a certificate payload from an already-reloaded *volume*.

    Shared helper used by both sync (``_read_v2_validation_certificate``) and
    async (``_read_v2_validation_certificate_async``) read paths.  Never raises.
    Returns ``{"outputs_to_execute": [...], "node_errors": {...}}`` on hit, or
    ``None`` on miss/mismatch/error.
    """
    try:
        import json as _json
        filename = _v2_cert_filename(cert_identity)
        if not volume.exists(filename):
            return None
        raw = volume.read_bytes(filename)
        if not raw:
            return None
        payload = _json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None

        # Schema version must match
        if payload.get("schema_version") != _V2_CERT_SCHEMA_VERSION:
            return None

        # Schema v2+: preflight_ok must be True for the cert to be eligible
        # as a preflight-skip token.  Old v1 payloads (no preflight_ok key)
        # fail this check naturally.
        if payload.get("preflight_ok") is not True:
            return None

        # Identity must match the requested cert_hash
        stored_identity = payload.get("identity", "")
        if stored_identity and stored_identity != cert_identity:
            return None

        # Verify identity components if provided
        if expected_components and isinstance(expected_components, dict):
            stored_components = payload.get("identity_components", {})
            if not isinstance(stored_components, dict):
                return None
            for key, expected_val in expected_components.items():
                stored_val = stored_components.get(key)
                if stored_val is None or str(stored_val) != str(expected_val):
                    print(
                        f"[v2.cert] hit=0 identity={cert_identity[:16]} "
                        f"reason={key}_changed "
                        f"stored={str(stored_val)[:32]!r} "
                        f"expected={str(expected_val)[:32]!r}",
                        flush=True,
                    )
                    return None

        # outputs_to_execute must be a non-empty list
        outputs = payload.get("outputs_to_execute")
        if not isinstance(outputs, list) or len(outputs) == 0:
            return None

        # Verify output IDs are unique strings
        seen: set[str] = set()
        for oid in outputs:
            if not isinstance(oid, str) or oid in seen:
                return None
            seen.add(oid)

        # node_errors must be dict of dicts
        errors = payload.get("node_errors", {})
        if not isinstance(errors, dict):
            errors = {}

        print(
            f"[v2.cert] hit=1 identity={cert_identity[:16]} "
            f"outputs={len(outputs)} errors={len(errors)}",
            flush=True,
        )
        return {"outputs_to_execute": outputs, "node_errors": errors}
    except Exception as exc:
        print(
            f"[v2.cert] read identity={cert_identity[:16]} "
            f"status=error error={str(exc)[:120]}",
            flush=True,
        )
        return None


def _read_v2_validation_certificate(
    cert_identity: str,
    *,
    expected_components: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Read and validate a certificate from the runtime-state volume.

    Synchronous variant — creates a ``ModalMountedStateVolume``, calls
    ``volume.reload()`` synchronously, then delegates to
    ``_read_and_validate_cert_payload()``.

    Never raises.  Returns the cached ``(outputs_to_execute, node_errors)``
    dict on hit, or None on miss/mismatch/error.

    When *expected_components* is provided, each stored identity component
    is verified against its expected value.  A mismatch logs the changed
    component and returns None.
    """
    try:
        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            return None
        from .runtime_state import ModalMountedStateVolume
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
        volume.reload()
        return _read_and_validate_cert_payload(
            volume, cert_identity, expected_components=expected_components,
        )
    except Exception as exc:
        print(
            f"[v2.cert] read identity={cert_identity[:16]} "
            f"status=error error={str(exc)[:120]}",
            flush=True,
        )
        return None


async def _read_v2_validation_certificate_async(
    cert_identity: str,
    *,
    expected_components: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Async variant — uses ``volume.reload_async()`` to avoid Modal's
    "synchronous reload in async context" warning, then delegates to
    ``_read_and_validate_cert_payload()``.

    Prefer this over the sync variant when calling from an async context
    (e.g. ``_execute_v2_prompt_executor``).
    """
    try:
        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            return None
        from .runtime_state import ModalMountedStateVolume
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
        await volume.reload_async()
        return _read_and_validate_cert_payload(
            volume, cert_identity, expected_components=expected_components,
        )
    except Exception as exc:
        print(
            f"[v2.cert] read identity={cert_identity[:16]} "
            f"status=error error={str(exc)[:120]}",
            flush=True,
        )
        return None


def _capture_remote_identity() -> dict[str, Any]:
    """Capture Modal identity and environment metadata at remote entry.

    Gathers ``modal.current_input_id()`` (safe fallback on failure), Modal
    runtime env vars, and current runtime mode.  Never raises — all access
    is wrapped in try/except.
    """
    identity: dict[str, Any] = {}
    try:
        if _modal is not None:
            input_id = _modal.current_input_id()
            if input_id:
                identity["modal_input_id"] = str(input_id)
    except Exception:
        pass
    for env_key, meta_key in (
        ("MODAL_TASK_ID", "container_task_id"),
        ("MODAL_IMAGE_ID", "image_id"),
        ("MODAL_CLOUD_PROVIDER", "cloud"),
        ("MODAL_REGION", "region"),
    ):
        value = os.environ.get(env_key, "")
        if value:
            identity[meta_key] = value
    runtime_mode = os.environ.get("COMFYMODAL_RUNTIME", "").strip()
    if runtime_mode:
        identity["runtime_mode"] = runtime_mode
    return identity


def _resource_identity(spec: ModalRuntimeSpec | None = None) -> dict[str, Any]:
    """Resource, volume, and snapshot configuration for invocation metadata.

    Returns the additive common-schema identity keys used across V1 and V2
    remote resource metadata.  All values are remote-observed or null/empty
    — never client-generated IDs or raw workflow/image/credential data.
    """
    actual = spec or _MODAL_RESOURCES.get("spec", ModalRuntimeSpec())
    return {
        # ── App / class identity (from remote-observed values) ────────
        "app_name": actual.app_name,
        "class_name": CLASS_NAME,
        # ── Resource allocation ───────────────────────────────────────
        "gpu": actual.gpu,
        "cpu": actual.cpu,
        "memory_mb": actual.memory,
        "target_inputs": actual.target_inputs,
        "max_inputs": actual.max_inputs,
        # ── Snapshot flags ────────────────────────────────────────────
        "snapshot_enabled": str(actual.enable_memory_snapshot),
        "gpu_snapshot_enabled": str(
            os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"
        ),
        # ── Volume names and mount paths ──────────────────────────────
        "models_volume": actual.models_volume_name,
        "runtime_state_volume": actual.runtime_state_volume_name,
        "custom_nodes_volume": actual.custom_nodes_volume_name,
        "volume_mount_paths": {
            actual.models_volume_name: actual.models_path,
            actual.custom_nodes_volume_name: actual.custom_nodes_path,
            actual.runtime_state_volume_name: actual.runtime_state_path,
        },
    }


@dataclass(frozen=True)
class ModalRuntimeSpec:
    app_name: str = APP_NAME
    models_volume_name: str = MODELS_VOLUME_NAME
    custom_nodes_volume_name: str = CUSTOM_NODES_VOLUME_NAME
    runtime_state_volume_name: str = RUNTIME_STATE_VOLUME_NAME
    models_path: str = MODELS_PATH
    custom_nodes_path: str = CUSTOM_NODES_PATH
    runtime_state_path: str = RUNTIME_STATE_PATH
    gpu: str = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
    cpu: int = 4
    memory: int = 32768
    timeout: int = 3600
    target_inputs: int = 1
    max_inputs: int = 1
    min_containers: int = MIN_CONTAINERS
    scaledown_window: int = SCALEDOWN_WINDOW
    enable_memory_snapshot: bool = True


def _local_custom_nodes_root() -> Path:
    explicit = os.environ.get("COMFYMODAL_LOCAL_CUSTOM_NODES", "").strip()
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[1]


def _reference_image() -> Any:
    """Build the V2 shadow deployment image from the production base.

    Modal requires that all build steps (``.pip_install``, ``.run_commands``,
    ``.env()``, ``.add_local_dir``) precede any ``.add_local_python_source()``
    calls.  The production base (``_image_base``) already satisfies this, so
    we start from it, inject the V2-only environment variable, then add the
    V2 source modules — preserving Modal's ordering constraint and keeping
    deep diagnostics off the legacy production image.
    """
    try:
        legacy = importlib.import_module("comfyapp")
        # Use _image_base (pre-local-sources) so .env() is legal here.
        # comfyapp.image already has add_local_python_source applied and
        # cannot be further modified with build-step commands.
        base = getattr(legacy, "_image_base", None)
        if base is None:
            # Fallback: attempt the fully-built image (risks build-order
            # rejection, but avoids hard crash when _image_base is absent)
            base = getattr(legacy, "image", None)
            if base is None:
                raise RuntimeError("comfyapp._image_base and .image are unavailable")
        image = base.env({"COMFYMODAL_V2_DEEP_MODEL_DIAG": "1"})
        for module_name in V2_SOURCE_MODULES:
            image = image.add_local_python_source(module_name)
        return image
    except Exception as exc:
        raise RuntimeError("unable to build v2 image from the working ComfyUI image") from exc


def build_modal_resources(*, spec: ModalRuntimeSpec | None = None) -> dict[str, Any]:
    """Build the actual v2 app, image, Volumes, and source identity."""
    runtime_spec = spec or ModalRuntimeSpec()
    runtime_root = Path(__file__).resolve().parent
    custom_root = _local_custom_nodes_root()
    identity = build_deployment_identity(runtime_root, custom_node_paths=[custom_root])
    if _modal is None:
        return {
            "app": None,
            "image": None,
            "models_volume": None,
            "custom_nodes_volume": None,
            "runtime_state_volume": None,
            "source_identity": identity,
            "spec": runtime_spec,
        }

    image = _reference_image()
    models_volume = _modal.Volume.from_name(runtime_spec.models_volume_name, create_if_missing=True)
    custom_nodes_volume = _modal.Volume.from_name(runtime_spec.custom_nodes_volume_name, create_if_missing=True)
    runtime_state_volume = _modal.Volume.from_name(runtime_spec.runtime_state_volume_name, create_if_missing=True)
    app = _modal.App(runtime_spec.app_name, image=image)
    return {
        "app": app,
        "image": image,
        "models_volume": models_volume,
        "custom_nodes_volume": custom_nodes_volume,
        "runtime_state_volume": runtime_state_volume,
        "source_identity": identity,
        "spec": runtime_spec,
    }


class ModalRuntimeEntrypoint:
    """Real v2 runtime facade backed by the existing ComfyUI executor."""

    def __init__(
        self,
        *,
        bootstrap: RuntimeBootstrap | None = None,
        executor: RuntimeExecutor | None = None,
        config: BootstrapConfig | None = None,
        checkpoint_runner: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._bootstrap_injected = bootstrap is not None
        self.bootstrap = bootstrap or RuntimeBootstrap(config)
        self._executor_injected = executor is not None
        self.executor = executor or RuntimeExecutor(in_process_runner=self._run_in_process)
        self.checkpoint_runner = checkpoint_runner
        self._legacy_module: Any | None = None
        self._legacy_api: Any | None = None
        self._runtime_configured = False
        self._restore_plan: RestorePlan | None = None
        self._restore_publisher: RestorePlanPublisher | None = None
        self._preload_bridge = V2LoaderBridge()
        self._lifecycle_trace: RuntimeTrace | None = None
        # Stable module-level identity so snapshot boundaries cannot erase identity.
        self.container_session_id: str = _V2_CONTAINER_SESSION_ID
        self._restore_count: int = 0
        self._restore_timing: dict[str, Any] | None = None

    def _remember_lifecycle_trace(self, trace: RuntimeTrace) -> None:
        if self._lifecycle_trace is None:
            self._lifecycle_trace = trace
        elif self._lifecycle_trace is not trace:
            self._lifecycle_trace.extend(trace.events)

    def _get_remote_restore_publisher(self) -> RestorePlanPublisher:
        if self._restore_publisher is not None:
            return self._restore_publisher
        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            raise RuntimeError("v2 runtime-state Modal Volume is not mounted")
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
        coordinator = CommitCoordinator(volume, state_path=V2_RESTORE_STATE_FILE)
        self._restore_publisher = RestorePlanPublisher(coordinator)
        return self._restore_publisher

    def _join_legacy_background_threads(self, api: Any, *, join_timeout: float = 30.0) -> int:
        """Join remaining alive threads in the legacy API's ``_actual_load_futures``.

        Returns the number of threads joined.  Uses a bounded per-thread
        timeout.  If the graph already consumed the future (thread is dead),
        the join returns immediately.  Never raises — errors are swallowed so
        existing error behaviour is preserved.
        """
        joined = 0
        if api is None:
            return 0
        try:
            futures = getattr(api, "_actual_load_futures", None)
            if not isinstance(futures, dict):
                return 0
            for key, thread in list(futures.items()):
                if thread is not None and getattr(thread, "is_alive", lambda: False)():
                    try:
                        thread.join(timeout=join_timeout)
                        joined += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return joined

    @staticmethod
    def _check_unet_deferral_eligible(api: Any, plan: Any) -> bool:
        """Return True when the optimized V2 UNET-deferral handoff is eligible.

        Checks that the plan has a UNET identity and the legacy API exposes
        the two helper methods needed by the handoff.  Never raises.
        """
        try:
            if plan is None:
                return False
            model_key = getattr(plan, "model_key", None)
            if model_key is None or not getattr(model_key, "unet_identity", ""):
                return False
            if not callable(getattr(api, '_patch_unet_loader_cache', None)):
                return False
            if not callable(getattr(api, '_start_production_restore_unet', None)):
                return False
            return True
        except Exception:
            return False

    def _load_legacy_runtime(self) -> Any:
        if self._legacy_api is not None:
            return self._legacy_api
        module = self._legacy_module or importlib.import_module("comfyapp")
        gpu_value = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000").strip().lower()
        class_name = "ComfyAPI"
        try:
            catalog = importlib.import_module("gpu_catalog")
            class_name = catalog.GPU_BY_VALUE.get(gpu_value, {}).get("class_name", class_name)
        except Exception:
            pass
        api_class = getattr(module, class_name, None) or getattr(module, "ComfyAPI", None)
        if api_class is None:
            raise RuntimeError(f"ComfyUI GPU runtime class is unavailable: {class_name}")
        self._legacy_module = module
        self._legacy_api = api_class()
        return self._legacy_api

    def _configure_runtime(self) -> None:
        if self._runtime_configured or self._bootstrap_injected:
            return
        api = self._load_legacy_runtime()
        module = self._legacy_module

        def reload_models() -> None:
            volume = getattr(module, "vol", None)
            if volume is not None:
                volume.reload()

        def reload_runtime_state() -> None:
            volume = getattr(module, "runtime_config_vol", None)
            if volume is not None:
                volume.reload()

        def sync_custom_nodes() -> Any:
            return api._sync_custom_nodes_from_volume()

        def install_requirements() -> Any:
            return api._install_custom_node_requirements()

        def start_backend() -> str:
            snapshot_context = getattr(api, "_force_cpu_during_snapshot", None)
            if callable(snapshot_context):
                with cast(ContextManager[Any], snapshot_context()):
                    api._start_in_process_backend()
            else:
                api._start_in_process_backend()
            return "in_process"

        def restore_gpu_state() -> Any:
            return api._restore_in_process_gpu_state()

        def initialize_cuda() -> dict[str, Any]:
            value = api._initialize_cuda_context()
            if isinstance(value, tuple) and len(value) == 2:
                return {"device": str(value[0]), "diagnostics": value[1]}
            return {"result": value}

        def apply_sage_policy() -> Any:
            return api._apply_sage_attention_policy()

        def observe_generations() -> dict[str, str]:
            return {
                "runtime_state": str(getattr(api, "_runtime_generation_seen", "") or ""),
                "custom_nodes": str(getattr(api, "_custom_nodes_generation_seen", "") or ""),
            }

        config = self._config or BootstrapConfig(
            comfyui_root="/root/comfy/ComfyUI",
            models_path=MODELS_PATH,
            custom_nodes_path=CUSTOM_NODES_PATH,
            min_containers=MIN_CONTAINERS,
            scaledown_window=SCALEDOWN_WINDOW,
        )
        self.bootstrap = RuntimeBootstrap(
            config,
            reload_models=reload_models,
            reload_runtime_state=reload_runtime_state,
            sync_custom_nodes=sync_custom_nodes,
            install_requirements=install_requirements,
            start_backend=start_backend,
            restore_gpu_state=restore_gpu_state,
            initialize_cuda=initialize_cuda,
            apply_sage_policy=apply_sage_policy,
            observe_generations=observe_generations,
        )
        self._runtime_configured = True

    def startup(self) -> dict[str, Any]:
        global _LATEST_LIFECYCLE_TIMING
        _startup_perf = time.perf_counter()
        identity = _capture_remote_identity()
        self._configure_runtime()
        trace = RuntimeTrace(process="remote")
        trace.container_session_id = self.container_session_id or _V2_CONTAINER_SESSION_ID
        trace.set_metadata(**identity)
        trace.set_metadata(container_session_id=self.container_session_id or _V2_CONTAINER_SESSION_ID)
        startup_session_id = uuid.uuid4().hex
        trace.emit(
            "remote_method_entry",
            phase="lifecycle",
            metadata={
                "app_name": APP_NAME,
                "class_name": CLASS_NAME,
                "method_name": "startup",
                "snapshot": "True",
                "lifecycle_session_id": startup_session_id,
                "lifecycle_count": "1",
                "container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
                **identity,
                **_resource_identity(),
            },
        )
        trace.emit(
            "gpu_invocation_submit",
            phase="lifecycle",
            metadata=_resource_identity(),
        )
        trace.emit("remote_lifecycle_start", phase="lifecycle", metadata={"snapshot": "True"})
        _lifecycle_error: str | None = None
        try:
            state = self.bootstrap.startup(snapshot=True, trace=trace)
        except Exception as exc:
            _lifecycle_error = str(exc)[:200]
            trace.emit("remote_lifecycle_end", phase="lifecycle", metadata={"status": "error", "error": _lifecycle_error})
            self._remember_lifecycle_trace(trace)
            startup_total_ms = round((time.perf_counter() - _startup_perf) * 1000.0, 3)
            err_timing: dict[str, Any] = {
                "restore_total_ms": startup_total_ms,
                "restore_session_id": startup_session_id,
                "container_session_id": self.container_session_id,
                "restore_count": 1,
                "lifecycle_status": "error",
                "lifecycle_error": _lifecycle_error,
                "lifecycle_method": "startup",
            }
            self._restore_timing = err_timing
            _LATEST_LIFECYCLE_TIMING = err_timing
            raise
        trace.emit("remote_lifecycle_end", phase="lifecycle", metadata={"status": "ready"})
        self._remember_lifecycle_trace(trace)

        startup_total_ms = round((time.perf_counter() - _startup_perf) * 1000.0, 3)
        _restore_timing: dict[str, Any] = {
            "restore_total_ms": startup_total_ms,
            "restore_session_id": startup_session_id,
            "container_session_id": self.container_session_id,
            "restore_count": 1,
            "lifecycle_status": "ok",
            "lifecycle_method": "startup",
        }
        if state.stage_durations:
            for _stage, _dur_ms in state.stage_durations.items():
                if _dur_ms is not None and _dur_ms > 0:
                    _restore_timing[f"{_stage}_ms"] = round(float(_dur_ms), 3)
        self._restore_timing = _restore_timing
        _LATEST_LIFECYCLE_TIMING = _restore_timing

        print(
            f"[v2.lifecycle] method=startup snap=True "
            f"container_session={_V2_CONTAINER_SESSION_ID} "
            f"restore_total_ms={startup_total_ms} "
            f"status=ready"
        )

        return {
            "backend": state.backend,
            "status": "ready",
            "trace": trace.to_dict(),
            "_restore_timing": _restore_timing,
            "phase_durations_ms": trace.export_phase_durations(),
        }

    def restore(self) -> dict[str, Any]:
        global _LATEST_LIFECYCLE_TIMING, _LATEST_RESTORED_INSTANCE_ID, _v2_container_restore_count
        _restore_perf_start = time.perf_counter()
        identity = _capture_remote_identity()
        self._configure_runtime()
        trace = RuntimeTrace(process="remote")
        trace.container_session_id = self.container_session_id or _V2_CONTAINER_SESSION_ID
        trace.set_metadata(**identity)
        trace.set_metadata(container_session_id=self.container_session_id or _V2_CONTAINER_SESSION_ID)
        _v2_container_restore_count += 1
        self._restore_count = _v2_container_restore_count
        restore_session_id = uuid.uuid4().hex
        # ── V2 restore correlation identity ──────────────────────────
        restored_instance_id = uuid.uuid4().hex
        self._restored_instance_id = restored_instance_id
        _LATEST_RESTORED_INSTANCE_ID = restored_instance_id
        set_model_load_identity(restored_instance_id, restore_session_id)
        # Legacy identity: rename old container_session_id internally
        legacy_container_session_id = self.container_session_id or _V2_CONTAINER_SESSION_ID
        trace.set_metadata(
            trace_id=trace.trace_id,
            restored_instance_id=restored_instance_id,
            restore_session_id=restore_session_id,
            legacy_container_session_id=legacy_container_session_id,
            **_resource_identity(),
        )
        trace.emit(
            "remote_method_entry",
            phase="lifecycle",
            metadata={
                "app_name": APP_NAME,
                "class_name": CLASS_NAME,
                "method_name": "restore",
                "snapshot": "False",
                "restore_session_id": restore_session_id,
                "restored_instance_id": restored_instance_id,
                "legacy_container_session_id": legacy_container_session_id,
                "restore_count": str(self._restore_count),
                "container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
                **identity,
                **_resource_identity(),
            },
        )
        trace.emit(
            "gpu_invocation_submit",
            phase="restore",
            metadata=_resource_identity(),
        )
        trace.emit("remote_lifecycle_start", phase="restore", metadata={"snapshot": "False"})
        trace.emit("restore_plan_read_start", phase="restore")
        try:
            self._restore_plan = self._get_remote_restore_publisher().read_current_plan()
            trace.emit(
                "restore_plan_read_end",
                phase="restore",
                metadata={
                    "status": "found" if self._restore_plan else "absent",
                    "generation": str(self._restore_plan.generation if self._restore_plan else ""),
                },
            )
        except Exception as exc:
            trace.emit(
                "restore_plan_read_end",
                phase="restore",
                metadata={"status": "error", "error": str(exc)[:200]},
            )
        _lifecycle_error: str | None = None
        try:
            trace.emit("v2_bootstrap_restore_start", phase="restore")
            state = self.bootstrap.restore(trace=trace)
            trace.emit("v2_bootstrap_restore_end", phase="restore")
        except Exception as exc:
            _lifecycle_error = str(exc)[:200]
            trace.emit("v2_bootstrap_restore_end", phase="restore", metadata={"status": "error", "error": _lifecycle_error})
            trace.emit("remote_lifecycle_end", phase="restore", metadata={"status": "error", "error": _lifecycle_error})
            self._remember_lifecycle_trace(trace)
            restore_total_ms = round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)
            err_timing: dict[str, Any] = {
                "restore_total_ms": restore_total_ms,
                "restore_session_id": restore_session_id,
                "restored_instance_id": restored_instance_id,
                "container_session_id": self.container_session_id,
                "restore_count": self._restore_count,
                "lifecycle_status": "error",
                "lifecycle_error": _lifecycle_error,
                "lifecycle_method": "restore",
            }
            self._restore_timing = err_timing
            _LATEST_LIFECYCLE_TIMING = err_timing
            raise
        if self._restore_plan is not None:
            trace.emit("preload_submission_start", phase="restore", metadata={
                "restore_plan_generation": str(self._restore_plan.generation),
            })
            preparation: RestorePreparation | None = None
            # ── Bounded V2 latency: check if we can defer UNET+VAE to
            #    original graph loaders and prepare only CLIP through the
            #    V2 bridge.  On any failure (missing helper, exception,
            #    non-submitted background future) we fail closed to the
            #    existing full V2 preload path. ──
            _optimized_ok = False
            _unet_deferred_meta: dict[str, Any] = {}
            _defer_api = self._load_legacy_runtime() if self._restore_plan else None
            if self._check_unet_deferral_eligible(_defer_api, self._restore_plan):
                trace.emit("defer_trial_start", phase="restore", metadata={
                    "unet_identity_hash": stable_hash(self._restore_plan.model_key.unet_identity) if self._restore_plan else "",
                })
                try:
                    # ── v2 UNET cache patch ────────────────────────
                    trace.emit("v2_unet_cache_patch_start", phase="restore")
                    _defer_api._patch_unet_loader_cache()
                    trace.emit("v2_unet_cache_patch_end", phase="restore")

                    # ── v2 CLIP prepare submit ─────────────────────
                    trace.emit("v2_clip_prepare_submit_start", phase="restore")
                    # Prepare only CLIP through V2; UNET and VAE are
                    # deferred to the original (patched) graph loaders.
                    preparation = self._preload_bridge.prepare(
                        self._restore_plan, trace=trace,
                        prepare_unet=False, prepare_vae=False,
                    )
                    trace.emit("v2_clip_prepare_submit_end", phase="restore")

                    # ── v2 CLIP worker wait ────────────────────────
                    trace.emit("v2_clip_worker_wait_start", phase="restore")
                    self._preload_bridge.close_workers()
                    trace.emit("v2_clip_worker_wait_end", phase="restore")
                    trace.emit("v2_clip_ready", phase="restore")

                    # ── v2 UNET spec extract ───────────────────────
                    trace.emit("v2_unet_spec_extract_start", phase="restore")
                    unet_name = self._restore_plan.model_key.unet_identity
                    weight_dtype = "default"
                    try:
                        unet_specs = self._restore_plan.model_spec.get("loaders", {}).get("unet", [])
                        if unet_specs and isinstance(unet_specs, list) and len(unet_specs) > 0:
                            weight_dtype = str(unet_specs[0].get("weight_dtype", "default"))
                    except Exception:
                        pass
                    trace.emit("v2_unet_spec_extract_end", phase="restore",
                               metadata={"unet_name": unet_name, "weight_dtype": weight_dtype})

                    # ── v2 background UNET submit ──────────────────
                    trace.emit("v2_background_unet_submit_start", phase="restore")

                    # Build diagnostic scope factory for the background worker.
                    # Use a shared mutable dict so _start_production_restore_unet
                    # populates canonical_key, diagnostic_id, resolved_path before
                    # the worker thread starts, and the factory reads the live values.
                    _bg_diag_ctx: dict[str, Any] = {
                        "canonical_key": "",
                        "diagnostic_id": "",
                        "resolved_path": "",
                        "restored_instance_id": restored_instance_id,
                        "restore_session_id": restore_session_id,
                        "weight_dtype": weight_dtype,
                        "submitted_at_unix": time.time(),
                    }
                    _bg_unet_trace_ref = None
                    try:
                        from comfymodal_runtime.model_preload import external_model_lane_scope
                        _factory_tid = trace.trace_id

                        def _bg_unet_diag_scope_factory():
                            """Create external_model_lane_scope for the bg UNET worker.
                            Reads live values from the shared mutable _bg_diag_ctx
                            dict, which _start_production_restore_unet populated."""
                            _ck = str(_bg_diag_ctx.get("canonical_key", ""))
                            _did = str(_bg_diag_ctx.get("diagnostic_id", ""))
                            _rp = str(_bg_diag_ctx.get("resolved_path", ""))
                            _bt = RuntimeTrace(
                                process="remote_background_unet",
                                trace_id=_factory_tid,
                            )
                            _bt.set_metadata(
                                restored_instance_id=str(_bg_diag_ctx.get("restored_instance_id", "")),
                                restore_session_id=str(_bg_diag_ctx.get("restore_session_id", "")),
                                canonical_key=_ck,
                                diagnostic_id=_did,
                                resolved_path=_rp,
                                weight_dtype=str(_bg_diag_ctx.get("weight_dtype", "")),
                            )
                            return external_model_lane_scope(
                                _bt, lane="UNET", phase="restore", expected_read_count=1,
                            )

                        _defer_result = _defer_api._start_production_restore_unet(
                            {"unet": unet_name, "weight_dtype": weight_dtype},
                            restore_start=time.time(),
                            restore_stages={},
                            diagnostic_scope_factory=_bg_unet_diag_scope_factory,
                            diagnostic_context=_bg_diag_ctx,
                            diagnostic_sink=None,
                        )
                        # Update shared context with values returned by the method
                        _defer_key = str(_defer_result.get("canonical_key", ""))
                        _defer_did = str(_defer_result.get("diagnostic_id", ""))
                        if _defer_key:
                            _bg_diag_ctx["canonical_key"] = _defer_key
                        if _defer_did:
                            _bg_diag_ctx["diagnostic_id"] = _defer_did
                        _bg_unet_trace_ref = None
                    except Exception:
                        _defer_result = _defer_api._start_production_restore_unet(
                            {"unet": unet_name, "weight_dtype": weight_dtype},
                            restore_start=time.time(),
                            restore_stages={},
                        )

                    trace.emit("v2_background_unet_submit_end", phase="restore",
                               metadata={"submitted": _defer_result.get("submitted", False),
                                         "canonical_key": _defer_result.get("canonical_key", ""),
                                         "diagnostic_id": _defer_result.get("diagnostic_id", "")})

                    # NOTE: bg_unet IO/stages summaries are NOT emitted here.
                    # They are emitted inside external_model_lane_scope's finally
                    # block after the worker completes (model_preload.py).
                    if _defer_result.get("submitted"):
                        _optimized_ok = True
                        _unet_deferred_meta = {
                            "decision": str(_defer_result.get("decision", "unknown")),
                            "submitted": True,
                            "unet_identity": unet_name,
                        }
                        trace.emit("defer_trial_result", phase="restore", metadata={
                            "submitted": True,
                            "decision": str(_defer_result.get("decision", "unknown"))[:120],
                        })
                    else:
                        trace.emit("defer_trial_result", phase="restore", metadata={
                            "submitted": False,
                            "reason": "not_submitted",
                        })
                except Exception as _defer_exc:
                    trace.emit("defer_trial_result", phase="restore", metadata={
                        "submitted": False,
                        "reason": str(_defer_exc)[:200],
                    })
            if not _optimized_ok:
                # Check whether an existing clip-only preparation can be
                # extended with UNET+VAE rather than cleared+reprepared.
                _existing = self._preload_bridge._preparation
                _can_extend = False
                if _existing is not None and _existing.clip_future is not None:
                    try:
                        _existing.clip_future.result()  # non-blocking; already waited
                        _can_extend = True
                    except Exception:
                        _can_extend = False
                if _can_extend:
                    preparation = self._preload_bridge.extend_preparation(
                        prepare_unet=True, prepare_vae=True, trace=trace,
                    )
                    self._preload_bridge.close_workers()
                    trace.emit(
                        "preload_fallback_mode", phase="restore",
                        metadata={"mode": "extended_existing_preparation"},
                    )
                else:
                    # Fail closed: clear any partially-prepared bridge state
                    # and use the full V2 preload path.
                    _reason = "no_useful_existing_preparation"
                    if _existing is not None and _existing.clip_future is not None:
                        _reason = "clip_future_failed"
                    self._preload_bridge.clear()
                    preparation = self._preload_bridge.prepare(self._restore_plan, trace=trace)
                    self._preload_bridge.close_workers()
                    trace.emit(
                        "preload_fallback_mode", phase="restore",
                        metadata={"mode": "full_reprepare", "reason": _reason},
                    )
            # Shared tail: trace metadata common to both paths.
            trace.emit("preload_submission_end", phase="restore", metadata={
                "preload_scheduled": str(bool(preparation)),
                "unet_deferred": _optimized_ok,
            })
            trace.set_metadata(
                restore_plan_generation=str(self._restore_plan.generation),
                preload_scheduled=bool(preparation),
                preload_diagnostics=self._preload_bridge.diagnostics(),
            )
            if _optimized_ok:
                trace.emit("unet_deferred", phase="restore", metadata=_unet_deferred_meta)
        else:
            self._preload_bridge.clear()
        trace.emit(
            "restore_completion_evidence",
            phase="restore",
            metadata={
                "preload_submitted": str(self._restore_plan is not None),
                "restore_plan_generation": str(
                    self._restore_plan.generation if self._restore_plan else ""
                ),
            },
        )
        # ── v2 restore finalize ──────────────────────────────────────
        trace.emit("v2_restore_finalize_start", phase="restore")

        trace.emit("remote_lifecycle_end", phase="restore", metadata={"status": "restored"})
        self._remember_lifecycle_trace(trace)
        trace = self._lifecycle_trace or trace

        restore_total_ms = round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)
        _restore_timing: dict[str, Any] = {
            "restore_total_ms": restore_total_ms,
            "restore_session_id": restore_session_id,
            "restored_instance_id": restored_instance_id,
            "legacy_container_session_id": legacy_container_session_id,
            "container_session_id": self.container_session_id,
            "restore_count": self._restore_count,
            "lifecycle_status": "ok",
            "lifecycle_method": "restore",
        }
        # Include available stage timings from bootstrap state (only when present)
        if state.stage_durations:
            for _stage, _dur_ms in state.stage_durations.items():
                if _dur_ms is not None and _dur_ms > 0:
                    _restore_timing[f"{_stage}_ms"] = round(float(_dur_ms), 3)
        self._restore_timing = _restore_timing
        _LATEST_LIFECYCLE_TIMING = _restore_timing

        trace.emit("v2_restore_finalize_end", phase="restore")
        _restore_result = {
            "backend": state.backend,
            "cuda": dict(state.cuda),
            "runtime_generation": state.runtime_generation,
            "status": "restored",
            "_restore_timing": _restore_timing,
            "restored_instance_id": restored_instance_id,
            "restore_session_id": restore_session_id,
            "container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
            "trace": trace.to_dict(),
            "phase_durations_ms": trace.export_phase_durations(),
        }

        # ── Emit compact restore-breakdown summary ──────────────────
        _brk, _clip = _collect_restore_events_for_summary(trace)
        print(
            f"[v2.restore_breakdown] "
            f"bootstrap_ms={_brk.get('bootstrap_ms')} "
            f"unet_cache_patch_ms={_brk.get('unet_cache_patch_ms')} "
            f"clip_prepare_submit_ms={_brk.get('clip_prepare_submit_ms')} "
            f"clip_worker_wait_ms={_brk.get('clip_worker_wait_ms')} "
            f"unet_spec_extract_ms={_brk.get('unet_spec_extract_ms')} "
            f"bg_unet_submit_ms={_brk.get('bg_unet_submit_ms')} "
            f"restore_finalize_ms={_brk.get('restore_finalize_ms')}",
            flush=True,
        )
        print(
            f"[v2.clip_stages] "
            f"worker_queue_ms={_clip.get('worker_queue_ms')} "
            f"load_torch_file_ms={_clip.get('load_torch_file_ms')} "
            f"read_to_ready_ms={_clip.get('read_to_ready_ms')} "
            f"post_read_cpu_prepare_ms={_clip.get('post_read_cpu_prepare_ms')} "
            f"gpu_wait_ms={_clip.get('gpu_wait_ms')} "
            f"gpu_commit_ms={_clip.get('gpu_commit_ms')} "
            f"read_end_to_ready_ms={_clip.get('read_end_to_ready_ms')} "
            f"worker_total_ms={_clip.get('worker_total_ms')} "
            f"worker_close_wait_ms={_clip.get('worker_close_wait_ms')} "
            f"restore_finalization_ms={_clip.get('restore_finalization_ms')}",
            flush=True,
        )

        # ── Emit restoration identity line ──────────────────────────
        print(
            f"[v2.restoration_identity] "
            f"restored_instance_id={restored_instance_id} "
            f"restore_session_id={restore_session_id} "
            f"container_session_id={self.container_session_id or _V2_CONTAINER_SESSION_ID} "
            f"modal_task_id={identity.get('container_task_id', '')} "
            f"modal_image_id={identity.get('image_id', '')} "
            f"modal_cloud={identity.get('cloud', '')} "
            f"modal_region={identity.get('region', '')} "
            f"pid={os.getpid()} "
            f"hostname={_capture_host_info().get('hostname', '')} "
            f"restore_total_ms={restore_total_ms} ",
            flush=True,
        )

        print(
            f"[v2.lifecycle] method=restore snap=False "
            f"container_session={_V2_CONTAINER_SESSION_ID} "
            f"restore_count={self._restore_count} "
            f"restore_total_ms={restore_total_ms} "
            f"status=restored"
        )

        trace.emit("v2_restore_return", phase="restore")
        _restore_result["trace"] = trace.to_dict()
        set_restore_return_marker(
            restored_instance_id=restored_instance_id,
            restore_session_id=restore_session_id,
            legacy_container_session_id=legacy_container_session_id,
            modal_task_id=identity.get("container_task_id", ""),
            pid=os.getpid(),
        )
        return _restore_result

    async def _run_in_process(self, plan: ExecutionPlan, context: ExecutionContext) -> dict[str, Any]:
        if context.cancelled and context.cancelled():
            raise RuntimeError("execution cancelled before PromptExecutor start")
        trace = context.trace or RuntimeTrace(request_id=context.request_id, process="remote")
        trace.emit("runtime_config_start", phase="execution")
        self._configure_runtime()
        trace.emit("runtime_config_end", phase="execution")
        trace.emit("legacy_runtime_load_start", phase="execution")
        api = self._load_legacy_runtime()
        trace.emit("legacy_runtime_load_end", phase="execution")
        # Attach stable container identity to execution trace
        _cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
        trace.container_session_id = _cid
        trace.emit("graph_execution_start", phase="execution")
        # Stash the execution trace on the legacy API so the patched UNET
        # loader (_cached_unet_load) can emit V2 cache-hit events even
        # when current_v2_loader_bridge() returns None.
        try:
            api._v2_graph_trace = trace
        except Exception:
            pass
        # ── Execution-phase CLIP exact-prefill single-flight ────────
        # Schedule prefill immediately after graph start so it runs
        # concurrently with execution setup.  The callback waits for both
        # UNET and CLIP preparation futures before encoding, preventing
        # GPU model-load/encode overlap.  Idempotent and thread-safe.
        self._preload_bridge.schedule_execution_prefill(trace=trace)
        try:
            with request_execution_trace_scope(trace):
                with self._preload_bridge.request_scope():
                    result: dict[str, Any] = await self._execute_v2_prompt_executor(plan, context, api, trace)
                _gpu_summary = gpu_not_observed_summary()
                trace.set_metadata(gpu_observation_summary=_gpu_summary)
                # ── Build GPU observation classification from helper + trace events ──
                _gpu_wrapper_installed = _gpu_summary.get("wrapper_status") == "installed"
                _gpu_wrapper_calls = _gpu_summary.get("count", 0)
                _gpu_graph_load_obs = any(e.name == "graph_gpu_load_start" for e in trace.events)
                _gpu_sampler_setup_obs = (
                    any(e.name in ("sampler_lane_wait_start", "sampler_lane_wait_end") for e in trace.events)
                    or any(
                        e.name == "graph_gpu_load_start"
                        and e.metadata.get("caller_classification") == "sampler_setup"
                        for e in trace.events
                    )
                )
                _gpu_obs_classification = {
                    "wrapper_installed": _gpu_wrapper_installed,
                    "wrapper_calls_observed": _gpu_wrapper_calls > 0,
                    "graph_gpu_load_observed": _gpu_graph_load_obs,
                    "sampler_setup_observed": _gpu_sampler_setup_obs,
                }
                trace.set_metadata(gpu_observation_classification=_gpu_obs_classification)
            trace.emit("graph_execution_end", phase="execution")
            # Drain late worker events (read/cpu/gpu/ready) from bridge
            # preparation into the execution trace so they are not lost.
            self._preload_bridge.drain_worker_events(trace)
            self._preload_bridge.close_workers()
            # Ensure any remaining legacy API background loader threads
            # for this request are terminal before result delivery.
            # MUST happen before the _BG_UNET_DIAG_STORE drain so
            # a workflow that never demands UNET still has its
            # background worker finish and store events first.
            self._join_legacy_background_threads(api)
            # Drain available background UNET diagnostics into trace
            try:
                from comfymodal_runtime.model_preload import _BG_UNET_DIAG_STORE, _BG_UNET_DIAG_LOCK
                with _BG_UNET_DIAG_LOCK:
                    for _ck in list(_BG_UNET_DIAG_STORE.keys()):
                        _bg_events = _BG_UNET_DIAG_STORE.pop(_ck, [])
                        if _bg_events:
                            trace.extend(_bg_events)
            except Exception:
                pass
            trace.set_metadata(
                restore_plan_generation=str(self._restore_plan.generation if self._restore_plan else ""),
                execution_backend="in_process",
                preload_diagnostics=self._preload_bridge.diagnostics(),
                container_session_id=_cid,
            )
            _gpu_locations: list[str] = []
            for _gpu_event in trace.events:
                if _gpu_event.name == "graph_gpu_load_start":
                    _classification = str(_gpu_event.metadata.get("caller_classification", "graph_model_loading"))
                    if _classification not in _gpu_locations:
                        _gpu_locations.append(_classification)
                elif _gpu_event.name == "gpu_commit_start":
                    _lane_name = str(_gpu_event.metadata.get("lane", ""))
                    _lane_location = {
                        "UNET": "background_unet_preparation",
                        "CLIP": "restore_clip_preparation",
                        "VAE": "restore_vae_preparation",
                    }.get(_lane_name)
                    if _lane_location and _lane_location not in _gpu_locations:
                        _gpu_locations.append(_lane_location)
            if not _gpu_locations:
                _gpu_locations = ["not_observed"]
            trace.set_metadata(gpu_loading_observed=_gpu_locations)
            result["gpu_loading_observed"] = _gpu_locations
            result["trace"] = trace.to_dict()
            if "_stage_timings" in result:
                result["trace"]["stages"] = result.pop("_stage_timings")
            result["container_session_id"] = _cid
            result["restore_plan_generation"] = str(self._restore_plan.generation if self._restore_plan else "")
            _rt = self._restore_timing or _LATEST_LIFECYCLE_TIMING
            if _rt is not None:
                result["_restore_timing"] = dict(_rt)
            result["phase_durations_ms"] = trace.export_phase_durations()
            return result
        except Exception as exc:
            trace.emit("graph_execution_end", phase="execution", metadata={"status": "error", "error": str(exc)[:200]})
            # Capture GPU observation summary/classification on exception path too.
            # Safe after request_execution_trace_scope exit — reads from module-level state.
            try:
                _gpu_summary = gpu_not_observed_summary()
                trace.set_metadata(gpu_observation_summary=_gpu_summary)
                _gpu_wrapper_installed = _gpu_summary.get("wrapper_status") == "installed"
                _gpu_wrapper_calls = _gpu_summary.get("count", 0)
                _gpu_graph_load_obs = any(e.name == "graph_gpu_load_start" for e in trace.events)
                _gpu_sampler_setup_obs = (
                    any(e.name in ("sampler_lane_wait_start", "sampler_lane_wait_end") for e in trace.events)
                    or any(
                        e.name == "graph_gpu_load_start"
                        and e.metadata.get("caller_classification") == "sampler_setup"
                        for e in trace.events
                    )
                )
                _gpu_obs_classification = {
                    "wrapper_installed": _gpu_wrapper_installed,
                    "wrapper_calls_observed": _gpu_wrapper_calls > 0,
                    "graph_gpu_load_observed": _gpu_graph_load_obs,
                    "sampler_setup_observed": _gpu_sampler_setup_obs,
                }
                trace.set_metadata(gpu_observation_classification=_gpu_obs_classification)
            except Exception:
                pass
            # Ensure any remaining legacy API background loader threads
            # are terminal before draining diagnostics (same ordering as
            # success path: join first, then drain).
            self._preload_bridge.close_workers()
            self._join_legacy_background_threads(api)
            # Drain bg diagnostics on exception path too
            try:
                from comfymodal_runtime.model_preload import _BG_UNET_DIAG_STORE, _BG_UNET_DIAG_LOCK
                with _BG_UNET_DIAG_LOCK:
                    for _ck in list(_BG_UNET_DIAG_STORE.keys()):
                        _bg_events = _BG_UNET_DIAG_STORE.pop(_ck, [])
                        if _bg_events:
                            trace.extend(_bg_events)
            except Exception:
                pass
            raise

    @staticmethod
    def _interval_from_trace(trace: Any, start_name: str, end_name: str) -> float | None:
        """Compute ms interval from the first start_name event to the first
        end_name event in the trace.  Returns None if either event is missing
        or end is before start (wrapping).  Does not raise."""
        start_ns: int | None = None
        end_ns: int | None = None
        for ev in trace.events:
            if ev.name == start_name and start_ns is None:
                start_ns = ev.monotonic_ns
            if ev.name == end_name and end_ns is None:
                end_ns = ev.monotonic_ns
            if start_ns is not None and end_ns is not None:
                break
        if start_ns is not None and end_ns is not None and end_ns >= start_ns:
            return round((end_ns - start_ns) / 1_000_000, 3)
        return None

    @staticmethod
    def _fmt_or_absent(v: float | int | None) -> str:
        """Format a numeric interval for the one-line summary.
        Returns ``str(v)`` for numeric values (including ``0.0``), ``"absent"`` for None."""
        if v is None:
            return "absent"
        return str(v)

    async def _execute_v2_prompt_executor(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        api: Any,
        trace: RuntimeTrace,
    ) -> dict[str, Any]:
        """Run the live ComfyUI PromptExecutor without the legacy wrapper.

        The v2 boundary owns request identity, validation, production
        authorization, output collection, and result packaging. ComfyUI still
        owns its actual PromptExecutor and node execution semantics.
        """
        if context.cancelled and context.cancelled():
            raise RuntimeError("execution cancelled before PromptExecutor start")

        workflow = _thaw(plan.workflow)
        _res4lyf_reported = int(plan.production_report.get("res4lyf_options_injected_count", 0) or 0)
        _res4lyf_injected_ids = [
            str(node_id)
            for node_id, node in workflow.items()
            if isinstance(node, Mapping)
            and node.get("class_type") == "ClownOptions_ExtraOptions_Beta"
            and "disable_dummy_sampler_init" in str((node.get("inputs") or {}).get("extra_options", ""))
        ]
        print(
            f"[v2.exec] res4lyf_dummy_init_disabled={int(bool(_res4lyf_injected_ids))} "
            f"reported_injected={_res4lyf_reported} actual_injected={len(_res4lyf_injected_ids)}",
            flush=True,
        )
        trace.emit(
            "res4lyf_dummy_init_transform",
            phase="execution",
            metadata={
                "reported_injected": _res4lyf_reported,
                "actual_injected": len(_res4lyf_injected_ids),
                "disabled": bool(_res4lyf_injected_ids),
            },
        )
        prompt_id = str(context.request_id or f"v2-{id(workflow):x}")
        module = self._legacy_module
        executor = getattr(api, "_executor", None)
        if executor is None:
            raise RuntimeError("v2 PromptExecutor runtime is not initialized")

        wait_for_preload = getattr(api, "_wait_for_restore_preload_before_request", None)
        if callable(wait_for_preload):
            trace.emit("legacy_preload_check_start", phase="execution")
            wait_for_preload(workflow)
            trace.emit("legacy_preload_check_end", phase="execution")

        materialize_inputs = getattr(module, "_materialize_input_images", None)
        if plan.input_images and callable(materialize_inputs):
            trace.emit("input_materialization_start", phase="execution")
            materialize_inputs(dict(plan.input_images))
            trace.emit("input_materialization_end", phase="execution")

        # ── Preflight context and certificate-gated preflight fast path ──
        # Phase 2: resolve the exact certificate before expensive preflight.
        # On exact identity/component hit + preflight_ok, skip preflight.
        # Missing-node repair always runs outside the certified skip.
        _v2_cert_hit = False
        _v2_cert_preflight_skip = False
        _v2_preflight_ran = False
        _v2_cert_identity = ""
        _v2_cert_components: dict[str, str] = {}
        _v2_schedule_cert_write = False
        _v2_dep_identity: DeploymentIdentity | None = globals().get("_MODAL_RESOURCES", {}).get("source_identity")
        _v2_repair_mode: str = ""
        _v2_custom_nodes_gen: str = ""

        # Pre-initialize outputs_to_execute/node_errors so they are always
        # defined before the execution/output section regardless of cert path.
        outputs_to_execute: list[str] = []
        node_errors: dict[str, Any] = {}

        # Obtain preflight context from the loaded legacy API
        _preflight_fn = getattr(api, "_preflight_before_prompt_execution", None)
        if callable(_preflight_fn) and not getattr(api, "_preflight_already_ran", False):
            _v2_repair_mode, _v2_custom_nodes_gen = _get_preflight_context(api, module)

            # Try cert lookup before preflight — only eligible when the
            # deployment identity, repair mode, and custom-nodes generation
            # are all complete and recognised.
            if _V2_VALIDATION_CERT_ENABLED:
                _cert_wf_hash = plan.workflow_hash or plan.source_workflow_hash or ""
                if _cert_wf_hash:
                    _v2_dep_hash = _v2_dep_identity.combined_hash if _v2_dep_identity else ""

                    # Cert read eligibility: nonempty deployment combined
                    # hash, recognised repair mode, and nonempty custom-nodes
                    # generation.  Incomplete context means preflight+validate
                    # must run and no certificate will be written.
                    _cert_eligible = (
                        bool(_v2_dep_hash)
                        and _v2_repair_mode in ("off", "fail_fast", "dev")
                        and bool(_v2_custom_nodes_gen)
                    )
                    if _cert_eligible:
                        _v2_cert_identity, _v2_cert_components = _compute_v2_cert_identity(
                            _cert_wf_hash,
                            deployment_identity=_v2_dep_identity,
                            repair_mode=_v2_repair_mode,
                            custom_nodes_generation=_v2_custom_nodes_gen,
                        )
                        trace.emit(
                            "certificate_reload_start",
                            phase="execution",
                            metadata={"cert_identity": _v2_cert_identity[:16]},
                        )
                        _cert_result = await _read_v2_validation_certificate_async(
                            _v2_cert_identity,
                            expected_components=_v2_cert_components,
                        )
                        trace.emit(
                            "certificate_read_outcome",
                            phase="execution",
                            metadata={
                                "cert_identity": _v2_cert_identity[:16],
                                "hit": _cert_result is not None,
                                "preflight_skip": _cert_result is not None,
                            },
                        )
                        trace.emit(
                            "certificate_reload_end",
                            phase="execution",
                            metadata={
                                "cert_identity": _v2_cert_identity[:16],
                                "hit": _cert_result is not None,
                            },
                        )
                        if _cert_result is not None:
                            outputs_to_execute = _cert_result["outputs_to_execute"]
                            node_errors = _cert_result.get("node_errors", {})
                            _v2_cert_hit = True
                            _v2_cert_preflight_skip = True
                            print(
                                f"[v2.cert] hit=1 preflight_skip=1 identity={_v2_cert_identity[:16]} "
                                f"outputs={len(outputs_to_execute)}",
                                flush=True,
                            )

        # ── Preflight (skip on exact certificate hit) ──────────────────
        if callable(_preflight_fn) and not getattr(api, "_preflight_already_ran", False):
            if _v2_cert_preflight_skip:
                trace.emit(
                    "preflight_certificate_skip",
                    phase="execution",
                    metadata={
                        "cert_identity": _v2_cert_identity[:16] if _v2_cert_identity else "",
                        "cert_hit": True,
                    },
                )
            else:
                _v2_preflight_ran = True
                trace.emit("preflight_start", phase="execution")
                _preflight_fn(workflow)
                trace.emit("preflight_end", phase="execution")

        repair_missing_nodes = getattr(api, "_repair_missing_workflow_nodes", None)
        repair_summary: Any = None
        if callable(repair_missing_nodes):
            trace.emit("missing_node_repair_start", phase="execution")
            repair_summary = repair_missing_nodes(workflow)
            trace.emit(
                "missing_node_repair_end",
                phase="execution",
                metadata={
                    "missing_before": list(repair_summary.get("missing_before", [])) if isinstance(repair_summary, Mapping) else [],
                    "missing_after": list(repair_summary.get("missing_after", [])) if isinstance(repair_summary, Mapping) else [],
                    "blocked": bool(repair_summary.get("blocked_by_mode", False)) if isinstance(repair_summary, Mapping) else False,
                },
            )
            if (
                isinstance(repair_summary, Mapping)
                and repair_summary.get("blocked_by_mode")
                and repair_summary.get("missing_before")
            ):
                raise RuntimeError(
                    "Workflow references missing custom node class(es): "
                    f"{repair_summary['missing_before']}. Runtime repair is disabled."
                )

            # Oracle Gate 2: if a cert skip occurred but the repair reports
            # nodes that were missing before repair, the cached validation
            # result may be stale because repair changed node availability.
            # Invalidate the cached cert result and fall through to full
            # preflight+validate below.
            if (
                _v2_cert_preflight_skip
                and isinstance(repair_summary, Mapping)
                and repair_summary.get("missing_before")
            ):
                print(
                    f"[v2.cert] invalidating cached result after missing-node repair "
                    f"missing_before={repair_summary['missing_before']}",
                    flush=True,
                )
                _v2_cert_hit = False
                _v2_cert_preflight_skip = False
                outputs_to_execute = []
                node_errors = {}
                # Re-run preflight now since the inline preflight block
                # already executed (and skipped).  Validate will also run
                # because _v2_cert_preflight_skip is now False.
                _v2_preflight_ran = True
                if callable(_preflight_fn):
                    trace.emit("preflight_start", phase="execution")
                    _preflight_fn(workflow)
                    trace.emit("preflight_end", phase="execution")

        import execution

        # ── Prompt validation ─────────────────────────────────────────
        # When preflight was skipped via certificate hit, outputs_to_execute
        # and node_errors are already populated from the stored certificate.
        # When preflight ran, we run validate_prompt and schedule a new cert
        # write (with preflight_ok=True) after successful execution.
        valid: bool = False
        error: dict[str, Any] | str = {}
        if not _v2_cert_preflight_skip:
            outputs_to_execute = []
            node_errors = {}
        trace.emit(
            "prompt_validation_start",
            phase="execution",
            metadata={
                "prompt_id": prompt_id,
                "cert_hit": _v2_cert_hit,
                "preflight_skip": _v2_cert_preflight_skip,
            },
        )
        if not _v2_cert_preflight_skip:
            valid, error, outputs_to_execute, node_errors = await execution.validate_prompt(
                prompt_id, workflow, None
            )
            # Schedule certificate write only when the same eligibility
            # conditions that would allow a read are met — incomplete or
            # unknown context never produces a certificate.
            _cert_write_eligible = (
                bool(_v2_dep_identity.combined_hash if _v2_dep_identity else "")
                and _v2_repair_mode in ("off", "fail_fast", "dev")
                and bool(_v2_custom_nodes_gen)
            )
            if valid and outputs_to_execute and _cert_write_eligible:
                if not _v2_cert_identity:
                    _cert_wf_hash = plan.workflow_hash or plan.source_workflow_hash or ""
                    if _cert_wf_hash and _V2_VALIDATION_CERT_ENABLED:
                        _v2_cert_identity, _v2_cert_components = _compute_v2_cert_identity(
                            _cert_wf_hash,
                            deployment_identity=_v2_dep_identity,
                            repair_mode=_v2_repair_mode,
                            custom_nodes_generation=_v2_custom_nodes_gen,
                        )
                if _v2_cert_identity:
                    _v2_schedule_cert_write = True
        else:
            valid = True
            error = {}
        trace.emit(
            "prompt_validation_end",
            phase="execution",
            metadata={
                "valid": bool(valid),
                "output_count": len(outputs_to_execute or []),
                "node_error_count": len(node_errors or {}),
                "cert_hit": _v2_cert_hit,
                "preflight_skip": _v2_cert_preflight_skip,
                "preflight_ran": _v2_preflight_ran,
                "cert_identity": _v2_cert_identity[:16] if _v2_cert_identity else "",
            },
        )
        if not valid:
            detail = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise RuntimeError(f"Workflow validation failed: {detail}")

        # ── Pregraph setup: V2-owned work between prompt validation and
        # PromptExecutor call (production registry, _begin_profile, etc.).
        trace.emit("pregraph_setup_start", phase="execution", metadata={
            "prompt_id": prompt_id,
        })
        _pregraph_error: str | None = None
        try:
            legacy_options = plan.execution_options.to_legacy_dict()
            production_report = dict(plan.production_report)
            production = legacy_options.get("production", {})
            production_enabled = bool(
                (production.get("enabled") if isinstance(production, Mapping) else False)
                or production_report.get("enabled")
            )
            authorized_node_ids: list[str] = []
            if production_report:
                for key in (
                    "direct_output_rewritten_node_ids",
                    "rgthree_comparer_rewritten_node_ids",
                ):
                    authorized_node_ids.extend(str(value) for value in production_report.get(key, []) or [])
            authorized_node_ids = list(dict.fromkeys(authorized_node_ids))
            register_request = getattr(module, "_register_production_request", None)
            cleanup_request = getattr(module, "_cleanup_production_request", None)
            cleanup_registry = getattr(module, "_cleanup_production_registry", None)
            pop_outputs = getattr(module, "_pop_production_outputs", None)
            if production_enabled and not callable(pop_outputs):
                raise RuntimeError("v2 production output registry is unavailable")

            if production_enabled and callable(register_request):
                trace.emit(
                    "production_registry_setup_start",
                    phase="execution",
                    metadata={"production_enabled": True, "authorized_node_count": len(authorized_node_ids)},
                )
                register_request(
                    prompt_id,
                    {
                        "enabled": True,
                        "prompt_id": prompt_id,
                        "output_format": legacy_options.get("output_format", "original"),
                        "quality": legacy_options.get("quality", 75),
                        "webp_lossless_compression": legacy_options.get(
                            "webp_lossless_compression", "balanced"
                        ),
                        "return_comparison_a": legacy_options.get("return_comparison_a", False),
                        "metadata_mode": production.get("metadata_mode", "none") if isinstance(production, Mapping) else "none",
                        "authorized_node_ids": authorized_node_ids,
                    },
                )
                trace.emit("production_registry_setup_end", phase="execution")

            _begin_profile = getattr(api, "_begin_prompt_profile", None)
            if callable(_begin_profile):
                _begin_profile(workflow, prompt_id, outputs_to_execute)
        except Exception as _pg_exc:
            _pregraph_error = str(_pg_exc)[:200]

        _lane = getattr(self._preload_bridge.coordinator, "mutation_lane", None)
        _lane_acquired = [False]
        started = time.time()
        try:
            trace.emit("executor_reset_start", phase="execution")
            executor.reset()
            trace.emit("executor_reset_end", phase="execution")
            # End pregraph span here — before prompt_executor_invoke_start, after
            # all V2-owned setup including executor.reset().
            trace.emit("pregraph_setup_end", phase="execution", metadata={
                "status": "error" if _pregraph_error else "ok",
                "error": _pregraph_error or "",
            })
            if _pregraph_error:
                raise RuntimeError(_pregraph_error)
            execute_async = getattr(executor, "execute_async", None)
            execute_kwargs = {
                "prompt": workflow,
                "prompt_id": prompt_id,
                "extra_data": {"client_id": prompt_id},
                "execute_outputs": outputs_to_execute,
            }
            # ── Build node-ID → class_type map ──────────────────
            _node_class_map: dict[str, str] = {}
            if isinstance(workflow, dict):
                for _nid, _node in workflow.items():
                    if isinstance(_node, dict):
                        _ct = _node.get("class_type", "")
                        if _ct:
                            _node_class_map[str(_nid)] = str(_ct)
            _first_node_id = str(outputs_to_execute[0]) if outputs_to_execute else ""
            _first_class_type = _node_class_map.get(_first_node_id, "")
            _has_clip_loader = any(ct.startswith("CLIP") for ct in _node_class_map.values())
            _has_text_encode = any("TextEncode" in ct or "CLIPTextEncode" in ct for ct in _node_class_map.values())
            _has_sampler = any("Sampler" in ct or "KSampler" in ct for ct in _node_class_map.values())
            _sampler_node_ids = [
                nid for nid, ct in _node_class_map.items()
                if "Sampler" in ct or "KSampler" in ct
            ]
            # ── PromptExecutor internal milestone interception ──
            # Request-local: wraps executor.add_message (3-arg shape:
            # event, data: dict, broadcast: bool) to capture
            # execution_start and execution_cached timestamps (first
            # occurrences only via setdefault).  Wraps
            # executor.server.send_sync (3-arg shape: event, data: dict,
            # client_id) to capture the first executing node and to
            # classify first model-loader, CLIP/text-encode, and
            # sampler-related nodes.  Both wrappers are restored in
            # the finally block and always delegate with original args.
            _orig_add_message = getattr(executor, "add_message", None)
            _server = getattr(executor, "server", None)
            _orig_send_sync = getattr(_server, "send_sync", None) if _server is not None else None
            _milestones: dict[str, Any] = {}
            _milestone_wrapper_ok = False
            _send_sync_wrapper_ok = False

            if callable(_orig_add_message) and not getattr(_orig_add_message, "_comfy_modal_milestone", False):
                def _milestone_wrapper(*args: Any, **kwargs: Any) -> Any:
                    # Real shape: add_message(event, data: dict, broadcast: bool)
                    event = args[0] if args else kwargs.get("event", "")
                    if event in ("execution_start", "execution_cached"):
                        _milestones.setdefault(event, time.monotonic_ns())
                    return _orig_add_message(*args, **kwargs)
                setattr(_milestone_wrapper, "_comfy_modal_milestone", True)
                executor.add_message = _milestone_wrapper
                _milestone_wrapper_ok = True

            if callable(_orig_send_sync) and not getattr(_orig_send_sync, "_comfy_modal_send_sync", False):
                def _send_sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    # Real shape: send_sync(event, data: dict, client_id)
                    event = args[0] if args else kwargs.get("event", "")
                    if event == "executing":
                        _event_ns = time.monotonic_ns()
                        _milestones.setdefault(event, _event_ns)
                        _data = args[1] if len(args) > 1 else kwargs.get("data", {})
                        if isinstance(_data, dict):
                            _node = _data.get("node")
                            if _node:
                                _node_str = str(_node)
                                _class_node = _node_class_map.get(str(_node), "")
                                # First executing node
                                if "first_executing_node" not in _milestones:
                                    _milestones["first_executing_node"] = _node_str
                                    _milestones["first_executing_node_class"] = _class_node
                                    _milestones["first_executing_node_ns"] = _event_ns
                                # First model-loader node: *Loader, Checkpoint, UNETLoader,
                                # VAELoader, CLIPLoader/DualCLIPLoader/LoraLoader; exclude CLIPTextEncode
                                _class_lower = _class_node.lower()
                                if ("first_loader_node" not in _milestones
                                        and "textencode" not in _class_lower
                                        and (_class_lower.endswith("loader")
                                             or "checkpointloader" in _class_lower
                                             or "model_loader" in _class_lower)):
                                    _milestones["first_loader_node"] = _node_str
                                    _milestones["first_loader_node_class"] = _class_node
                                    _milestones["first_loader_node_ns"] = _event_ns
                                # First CLIP/text-encode node
                                if ("first_clip_encode_node" not in _milestones
                                        and ("CLIPTextEncode" in _class_node or "TextEncode" in _class_node
                                             or "CLIP" in _class_node)):
                                    _milestones["first_clip_encode_node"] = _node_str
                                    _milestones["first_clip_encode_node_class"] = _class_node
                                    _milestones["first_clip_encode_node_ns"] = _event_ns
                                # First sampler-related node
                                if ("first_sampler_node" not in _milestones
                                        and ("Sampler" in _class_node or "KSampler" in _class_node)):
                                    _milestones["first_sampler_node"] = _node_str
                                    _milestones["first_sampler_node_class"] = _class_node
                                    _milestones["first_sampler_node_ns"] = _event_ns
                                    # Acquire mutation lane: blocks until previous
                                    # GPU commit finishes, preventing overlap
                                    # between model GPU commits and sampling.
                                    if _lane is not None and not _lane_acquired[0]:
                                        _blocking_owner = _lane.owner or ""
                                        _lane_wait_start_ns = time.monotonic_ns()
                                        trace.emit("sampler_lane_wait_start", phase="execution", metadata={
                                            "sampler_node_id": _node_str,
                                            "sampler_node_class": _class_node,
                                            "blocking_owner": _blocking_owner,
                                        })
                                        _lane.acquire("sampler")
                                        _milestones["_lane_acquired_mono_ns"] = time.monotonic_ns()
                                        _lane_wait_ms = round((_milestones["_lane_acquired_mono_ns"] - _lane_wait_start_ns) / 1_000_000, 3)
                                        trace.emit("sampler_lane_wait_end", phase="execution", metadata={
                                            "sampler_node_id": _node_str,
                                            "sampler_node_class": _class_node,
                                            "wait_ms": _lane_wait_ms,
                                            "blocking_owner": _blocking_owner,
                                        })
                                        _lane_acquired[0] = True
                    elif event in ("sampler_start", "sampling_start", "sampler_stage_start", "progress") and "first_sampler_node" in _milestones:
                        if "first_sampler_stage_ns" not in _milestones:
                            _milestones["first_sampler_stage_ns"] = time.monotonic_ns()
                            _milestones["first_sampler_stage_event"] = event
                    return _orig_send_sync(*args, **kwargs)
                setattr(_send_sync_wrapper, "_comfy_modal_send_sync", True)
                _server.send_sync = _send_sync_wrapper
                _send_sync_wrapper_ok = True

            if not _milestone_wrapper_ok and not _send_sync_wrapper_ok:
                trace.emit("prompt_executor_internal_milestones_unavailable", phase="execution",
                           metadata={"reason": "add_message_and_send_sync_unavailable"})
            elif not _milestone_wrapper_ok:
                trace.emit("prompt_executor_internal_milestones_unavailable", phase="execution",
                           metadata={"reason": "add_message_unavailable"})
            elif not _send_sync_wrapper_ok:
                trace.emit("prompt_executor_internal_milestones_unavailable", phase="execution",
                           metadata={"reason": "send_sync_unavailable"})

            # T5: immediately before prompt executor invocation
            _t5_wall_ns = int(time.time() * 1_000_000_000)
            _t5_mono_ns = time.monotonic_ns()
            _execute_call_ns = _t5_mono_ns  # preserve for milestone calculations
            trace.emit("prompt_executor_invoke_start", phase="execution", metadata={
                "prompt_id": prompt_id,
                "request_id": str(context.trace.request_id if context.trace else ""),
                "t5_wall_ns": _t5_wall_ns,
                "t5_mono_ns": _t5_mono_ns,
                "first_node_id": _first_node_id,
                "first_class_type": _first_class_type,
                "has_clip_loader": _has_clip_loader,
                "has_text_encode": _has_text_encode,
                "has_sampler": _has_sampler,
                "sampler_node_count": len(_sampler_node_ids),
                "total_nodes": len(_node_class_map),
            })
            try:
                if callable(execute_async):
                    execute_result = execute_async(**execute_kwargs)
                    if inspect.isawaitable(execute_result):
                        await execute_result
                else:
                    executor.execute(**execute_kwargs)
            finally:
                try:
                    # Restore original add_message
                    if _milestone_wrapper_ok and _orig_add_message is not None:
                        executor.add_message = _orig_add_message
                    # Restore original send_sync
                    if _send_sync_wrapper_ok and _orig_send_sync is not None and _server is not None:
                        _server.send_sync = _orig_send_sync
                finally:
                    # Always emit invoke_end — even if restore/release raises
                    _invoke_elapsed_ms = round((time.monotonic_ns() - _execute_call_ns) / 1_000_000, 3)
                    trace.emit("prompt_executor_invoke_end", phase="execution", metadata={
                        "invoke_elapsed_ms": _invoke_elapsed_ms,
                    })

            # ── Compute derived milestone intervals ──────────────────────
            _exec_st_ns = _milestones.get("execution_start") if _milestones else None
            _cached_ns = _milestones.get("execution_cached") if _milestones else None
            _first_ns = _milestones.get("executing") if _milestones else None
            _first_exec_node_id = _milestones.get("first_executing_node", "") if _milestones else ""
            _first_exec_node_class = _milestones.get("first_executing_node_class", "") if _milestones else ""
            _first_loader_node_id = _milestones.get("first_loader_node", "") if _milestones else ""
            _first_clip_encode_node_id = _milestones.get("first_clip_encode_node", "") if _milestones else ""
            _first_sampler_node_id = _milestones.get("first_sampler_node", "") if _milestones else ""
            # Extract monotonic_ns timestamps for node classifications (A)
            _first_exec_node_ns = _milestones.get("first_executing_node_ns") if _milestones else None
            _first_loader_node_ns = _milestones.get("first_loader_node_ns") if _milestones else None
            _first_clip_ns = _milestones.get("first_clip_encode_node_ns") if _milestones else None
            _first_sampler_ns = _milestones.get("first_sampler_node_ns") if _milestones else None
            _first_sampler_stage_ns = _milestones.get("first_sampler_stage_ns") if _milestones else None
            _first_sampler_stage_event = _milestones.get("first_sampler_stage_event", "") if _milestones else ""
            _exec_st_val = round((_exec_st_ns - _execute_call_ns) / 1_000_000, 3) if _exec_st_ns else None
            _exec_to_cache = round((_cached_ns - _exec_st_ns) / 1_000_000, 3) if _exec_st_ns and _cached_ns else None
            _cache_to_node = round((_first_ns - _cached_ns) / 1_000_000, 3) if _cached_ns and _first_ns else None
            _call_to_cached = round((_cached_ns - _execute_call_ns) / 1_000_000, 3) if _cached_ns else None
            _call_to_first_node = round((_first_ns - _execute_call_ns) / 1_000_000, 3) if _first_ns else None
            # ── Node-to-node sub-intervals (B) ──
            _first_node_to_clip_ms: float | None = None
            _clip_to_sampler_node_ms: float | None = None
            _sampler_node_to_sampler_start_ms: float | None = None
            if _first_exec_node_ns is not None and _first_clip_ns is not None:
                _first_node_to_clip_ms = round((_first_clip_ns - _first_exec_node_ns) / 1_000_000, 3)
            if _first_clip_ns is not None and _first_sampler_ns is not None:
                _clip_to_sampler_node_ms = round((_first_sampler_ns - _first_clip_ns) / 1_000_000, 3)
            if _first_sampler_ns is not None and _first_sampler_stage_ns is not None:
                _sampler_node_to_sampler_start_ms = round((_first_sampler_stage_ns - _first_sampler_ns) / 1_000_000, 3)
            if _milestones:
                trace.emit("prompt_executor_milestones", phase="execution", metadata={
                    "executor_call_to_execution_start_ms": _exec_st_val,
                    "execution_start_to_cached_ms": _exec_to_cache,
                    "cached_to_first_node_ms": _cache_to_node,
                    "executor_call_to_cached_ms": _call_to_cached,
                    "executor_call_to_first_node_ms": _call_to_first_node,
                    "first_executing_node_id": _first_exec_node_id,
                    "first_executing_node_class": _first_exec_node_class,
                    # Loader/CLIP/sampler node classification (B)
                    "first_loader_node_id": _first_loader_node_id,
                    "first_clip_encode_node_id": _first_clip_encode_node_id,
                    "first_sampler_node_id": _first_sampler_node_id,
                    "first_sampler_stage_event": _first_sampler_stage_event,
                    # Node-to-node intervals (B)
                    "first_node_to_clip_ms": _first_node_to_clip_ms,
                    "clip_to_sampler_node_ms": _clip_to_sampler_node_ms,
                    "sampler_node_to_sampler_start_ms": _sampler_node_to_sampler_start_ms,
                    # Raw monotonic-ns timestamps
                    "first_executing_node_monotonic_ns": _first_exec_node_ns,
                    "first_loader_node_monotonic_ns": _first_loader_node_ns,
                    "first_clip_encode_node_monotonic_ns": _first_clip_ns,
                    "first_sampler_node_monotonic_ns": _first_sampler_ns,
                    "first_sampler_stage_monotonic_ns": _first_sampler_stage_ns,
                })

            # ── Classify sampler stage from first executing node ──
            _sampler_stage_status: str = "awaiting_classification"
            if _first_exec_node_class:
                if "Sampler" in _first_exec_node_class or "KSampler" in _first_exec_node_class:
                    _sampler_stage_status = "sampler_active"
                elif "CLIPTextEncode" in _first_exec_node_class or "TextEncode" in _first_exec_node_class:
                    _sampler_stage_status = "text_encoding"
                elif "CLIP" in _first_exec_node_class:
                    _sampler_stage_status = "clip_loading"
                elif "VAE" in _first_exec_node_class:
                    _sampler_stage_status = "vae_loading"
                elif "UNET" in _first_exec_node_class or "UNet" in _first_exec_node_class:
                    _sampler_stage_status = "unet_loading"
                elif "Load" in _first_exec_node_class:
                    _sampler_stage_status = f"loading:{_first_exec_node_class}"
                else:
                    _sampler_stage_status = f"other:{_first_exec_node_class}"

            # ── Compute setup intervals from existing trace events ───────
            _cert_ms = self._interval_from_trace(trace, "certificate_reload_start", "certificate_reload_end")
            _preflight_ms = self._interval_from_trace(trace, "preflight_start", "preflight_end")
            _validation_ms = self._interval_from_trace(trace, "prompt_validation_start", "prompt_validation_end")
            _pregraph_ms = self._interval_from_trace(trace, "pregraph_setup_start", "pregraph_setup_end")
            _exec_reset_ms = self._interval_from_trace(trace, "executor_reset_start", "executor_reset_end")
            _sampler_lane_ms = self._interval_from_trace(trace, "sampler_lane_wait_start", "sampler_lane_wait_end")
            _graph_setup_ms = self._interval_from_trace(trace, "graph_execution_start", "prompt_executor_invoke_start")
            _met_start_ms = self._interval_from_trace(trace, "remote_method_entry", "graph_execution_start")
            # Additional setup interval fields (C)
            _runtime_config_ms = self._interval_from_trace(trace, "runtime_config_start", "runtime_config_end")
            _method_entry_to_runtime_ms = self._interval_from_trace(trace, "remote_method_entry", "runtime_config_end")
            _legacy_runtime_ms = self._interval_from_trace(trace, "legacy_runtime_load_start", "legacy_runtime_load_end")
            _preload_check_ms = self._interval_from_trace(trace, "legacy_preload_check_start", "legacy_preload_check_end")
            _repair_ms = self._interval_from_trace(trace, "missing_node_repair_start", "missing_node_repair_end")
            _production_registry_ms = self._interval_from_trace(trace, "production_registry_setup_start", "production_registry_setup_end")
            # Residual before invoke: gap between pregraph_setup_end (or last measured) and invoke_start
            _pregraph_end_event_ns: int | None = None
            for ev in reversed(trace.events):
                if ev.name == "pregraph_setup_end":
                    _pregraph_end_event_ns = ev.monotonic_ns
                    break
            if _pregraph_end_event_ns and _execute_call_ns > _pregraph_end_event_ns:
                _residual_before_invoke = round((_execute_call_ns - _pregraph_end_event_ns) / 1_000_000, 3)
            else:
                _residual_before_invoke = None

            # ── Measured children sum (leaf-level, non-overlapping) (C) ──
            # pregraph_setup_ms includes executor_reset_ms; decompose into
            # pregraph_without_reset + exec_reset (non-overlapping leaves).
            _pregraph_without_reset_ms = (_pregraph_ms - _exec_reset_ms) if _pregraph_ms is not None and _exec_reset_ms is not None else None
            _leaf_setup = [
                _cert_ms, _preflight_ms, _repair_ms, _validation_ms,
                _pregraph_without_reset_ms, _exec_reset_ms,
            ]
            # Include sampler_lane_wait_ms only when lane was acquired
            # (avoids including lane wait in both sampler_lane and residual).
            if _lane_acquired[0]:
                _leaf_setup.append(_sampler_lane_ms)
            _leaf_setup_ms = sum(v for v in _leaf_setup if v is not None)
            # Sampler node → lane acquired → actual stage decompose
            # the single sampler_node_to_sampler_start_ms into two
            # non-overlapping sub-intervals for the leaf sum.
            _lane_acquired_ns = _milestones.get("_lane_acquired_mono_ns") if _milestones else None
            _sampler_node_to_lane_acquired_ms: float | None = None
            _lane_acquired_to_actual_stage_ms: float | None = None
            if _first_sampler_ns is not None and _lane_acquired_ns is not None:
                _sampler_node_to_lane_acquired_ms = round((_lane_acquired_ns - _first_sampler_ns) / 1_000_000, 3)
            if _lane_acquired_ns is not None and _first_sampler_stage_ns is not None:
                _lane_acquired_to_actual_stage_ms = round((_first_sampler_stage_ns - _lane_acquired_ns) / 1_000_000, 3)
            _leaf_milestone = [
                _exec_st_val, _exec_to_cache, _cache_to_node,
                _first_node_to_clip_ms, _clip_to_sampler_node_ms,
                _sampler_node_to_lane_acquired_ms, _lane_acquired_to_actual_stage_ms,
            ]
            _leaf_milestone_ms = sum(v for v in _leaf_milestone if v is not None)
            _total_children_val = _leaf_setup_ms + _leaf_milestone_ms
            _measured_children_ms = round(_total_children_val, 3) if _total_children_val > 0 else None

            # ── Build named interval map for overlap diagnostics ──
            _overlap_interval_map: dict[str, float | None] = {
                "certificate_ms": _cert_ms,
                "preflight_ms": _preflight_ms,
                "repair_ms": _repair_ms,
                "validation_ms": _validation_ms,
                "pregraph_without_reset_ms": _pregraph_without_reset_ms,
                "executor_reset_ms": _exec_reset_ms,
                "sampler_lane_wait_ms": _sampler_lane_ms if _lane_acquired[0] else None,
                "invoke_to_execution_start_ms": _exec_st_val,
                "execution_start_to_cached_ms": _exec_to_cache,
                "cached_to_first_node_ms": _cache_to_node,
                "first_node_to_clip_ms": _first_node_to_clip_ms,
                "clip_to_sampler_node_ms": _clip_to_sampler_node_ms,
                "sampler_node_to_lane_acquired_ms": _sampler_node_to_lane_acquired_ms,
                "lane_acquired_to_actual_stage_ms": _lane_acquired_to_actual_stage_ms,
            }
            _overlapping_intervals: list[str] = [
                name for name, val in _overlap_interval_map.items() if val is not None
            ]

            # ── pre_sampler_total_ms from remote_method_entry to first_sampler_stage_ns (C) ──
            _remote_method_entry_ns = None
            for ev in trace.events:
                if ev.name == "remote_method_entry":
                    _remote_method_entry_ns = ev.monotonic_ns
                    break
            if _remote_method_entry_ns is not None and _first_sampler_stage_ns is not None:
                _pre_sampler_total_ms = round((_first_sampler_stage_ns - _remote_method_entry_ns) / 1_000_000, 3)
            else:
                _pre_sampler_total_ms = None
            if _pre_sampler_total_ms is not None:
                if _measured_children_ms is not None and _measured_children_ms > _pre_sampler_total_ms:
                    _reconciliation_status = "overlap_error"
                    _residual_ms = round(_pre_sampler_total_ms - _measured_children_ms, 3)
                else:
                    _reconciliation_status = "ok"
                    _residual_ms = round(_pre_sampler_total_ms - (_measured_children_ms or 0.0), 3)
            else:
                _reconciliation_status = "absent_total"
                _residual_ms = None

            # ── Gather identity metadata for pre_sampler_stages event and print (D) ──
            _ps_prompt_id = prompt_id
            _ps_identity = _capture_remote_identity()
            _ps_modal_input_id = _ps_identity.get("modal_input_id", "absent")
            _ps_modal_task_id = _ps_identity.get("container_task_id", "absent")
            _ps_host_info = _capture_host_info()
            _ps_pid = _ps_host_info.get("pid", os.getpid())
            _ps_hostname = _ps_host_info.get("hostname", "absent")
            _ps_boot_id = _ps_host_info.get("boot_id", "absent")
            _ps_restored_id_actual = getattr(self, "_restored_instance_id", "")
            _ps_restore_session = (self._restore_timing or {}).get("restore_session_id", "") or "absent"
            _ps_restored_instance_id = _ps_restored_id_actual or "absent"
            _ps_cid = self.container_session_id or _V2_CONTAINER_SESSION_ID or "absent"

            # Always emit pre_sampler_stages — even when milestones absent (C/D)
            trace.emit("pre_sampler_stages", phase="execution", metadata={
                # Setup intervals from trace events
                "method_entry_to_graph_start_ms": _met_start_ms,
                "graph_setup_ms": _graph_setup_ms,
                "certificate_ms": _cert_ms,
                "preflight_ms": _preflight_ms,
                "validation_ms": _validation_ms,
                "runtime_configuration_ms": _runtime_config_ms,
                "method_entry_to_runtime_configuration_ms": _method_entry_to_runtime_ms,
                "legacy_runtime_resolution_ms": _legacy_runtime_ms,
                "preload_check_ms": _preload_check_ms,
                "missing_node_repair_ms": _repair_ms,
                "production_registry_setup_ms": _production_registry_ms,
                "production_registry_profile_setup_ms": _production_registry_ms,
                "pregraph_setup_ms": _pregraph_ms,
                "executor_reset_ms": _exec_reset_ms,
                "sampler_lane_wait_ms": _sampler_lane_ms,
                "residual_before_invoke_ms": _residual_before_invoke,
                # Internal milestone intervals (from wrapper captures)
                "invoke_to_execution_start_ms": _exec_st_val,
                "execution_start_to_cached_ms": _exec_to_cache,
                "cached_to_first_node_ms": _cache_to_node,
                "first_node_to_clip_ms": _first_node_to_clip_ms,
                "clip_to_sampler_node_ms": _clip_to_sampler_node_ms,
                "sampler_node_to_lane_acquired_ms": _sampler_node_to_lane_acquired_ms,
                "lane_acquired_to_actual_stage_ms": _lane_acquired_to_actual_stage_ms,
                "sampler_node_to_sampler_start_ms": _sampler_node_to_sampler_start_ms,
                # Totals and reconciliation (C)
                "pre_sampler_total_ms": _pre_sampler_total_ms,
                "measured_children_ms": _measured_children_ms,
                "residual_ms": _residual_ms,
                "reconciliation_status": _reconciliation_status,
                "overlapping_intervals": _overlapping_intervals,
                "lane_acquired": _lane_acquired[0],
                # Node classification (B)
                "total_nodes": len(_node_class_map),
                "first_output_node_id": _first_node_id,
                "first_output_class_type": _first_class_type,
                "first_executing_node_id": _first_exec_node_id,
                "first_executing_node_class": _first_exec_node_class,
                "first_loader_node_id": _first_loader_node_id,
                "first_loader_node_class": _milestones.get("first_loader_node_class", "") if _milestones else "",
                "first_clip_encode_node_id": _first_clip_encode_node_id,
                "first_clip_encode_node_class": _milestones.get("first_clip_encode_node_class", "") if _milestones else "",
                "first_sampler_node_id": _first_sampler_node_id,
                "first_sampler_node_class": _milestones.get("first_sampler_node_class", "") if _milestones else "",
                "first_sampler_stage_event": _first_sampler_stage_event,
                # Raw monotonic-ns timestamps
                "first_executing_node_monotonic_ns": _first_exec_node_ns,
                "first_loader_node_monotonic_ns": _first_loader_node_ns,
                "first_clip_encode_node_monotonic_ns": _first_clip_ns,
                "first_sampler_node_monotonic_ns": _first_sampler_ns,
                "first_sampler_stage_monotonic_ns": _first_sampler_stage_ns,
                "sampler_stage_status": _sampler_stage_status,
                "has_clip_loader": _has_clip_loader,
                "has_text_encode": _has_text_encode,
                "has_sampler": _has_sampler,
                "sampler_node_ids": ",".join(_sampler_node_ids) if _sampler_node_ids else "",
                "sampler_node_count": len(_sampler_node_ids),
                # Wrapper availability
                "add_message_available": _milestone_wrapper_ok,
                "send_sync_available": _send_sync_wrapper_ok,
                # Identity metadata (D)
                "request_id": _ps_prompt_id,
                "modal_input_id": _ps_modal_input_id,
                "modal_task_id": _ps_modal_task_id,
                "container_task_id": _ps_modal_task_id,
                "pid": _ps_pid,
                "boot_id": _ps_boot_id,
                "hostname": _ps_hostname,
                "restored_instance_id": _ps_restored_instance_id,
                "restore_session_id": _ps_restore_session,
                "container_session_id": _ps_cid,
            })
            # ── One-line [v2.pre_sampler_stages] summary (always emitted) ───
            print(
                f"[v2.pre_sampler_stages] "
                f"request_id={_ps_prompt_id} "
                f"restored_instance_id={_ps_restored_instance_id} "
                f"restore_session_id={_ps_restore_session} "
                f"container_session_id={_ps_cid} "
                f"modal_input_id={_ps_modal_input_id} "
                f"modal_task_id={_ps_modal_task_id} "
                f"pid={_ps_pid} "
                f"boot_id={_ps_boot_id} "
                f"hostname={_ps_hostname} "
                f"total_nodes={len(_node_class_map)} "
                f"first_output_node={_first_node_id}:{_first_class_type} "
                f"first_executing_node={_first_exec_node_id}:{_first_exec_node_class} "
                f"sampler_stage_status={_sampler_stage_status} "
                f"method_entry_to_graph_start_ms={self._fmt_or_absent(_met_start_ms)} "
                f"graph_setup_ms={self._fmt_or_absent(_graph_setup_ms)} "
                f"certificate_ms={self._fmt_or_absent(_cert_ms)} "
                f"preflight_ms={self._fmt_or_absent(_preflight_ms)} "
                f"validation_ms={self._fmt_or_absent(_validation_ms)} "
                f"missing_node_repair_ms={self._fmt_or_absent(_repair_ms)} "
                f"production_registry_setup_ms={self._fmt_or_absent(_production_registry_ms)} "
                f"production_registry_profile_setup_ms={self._fmt_or_absent(_production_registry_ms)} "
                f"pregraph_setup_ms={self._fmt_or_absent(_pregraph_ms)} "
                f"executor_reset_ms={self._fmt_or_absent(_exec_reset_ms)} "
                f"sampler_lane_wait_ms={self._fmt_or_absent(_sampler_lane_ms)} "
                f"residual_before_invoke_ms={self._fmt_or_absent(_residual_before_invoke)} "
                f"method_entry_to_runtime_configuration_ms={self._fmt_or_absent(_method_entry_to_runtime_ms)} "
                f"call_to_exec_start_ms={self._fmt_or_absent(_exec_st_val)} "
                f"exec_start_to_cached_ms={self._fmt_or_absent(_exec_to_cache)} "
                f"cached_to_first_executing_ms={self._fmt_or_absent(_cache_to_node)} "
                f"call_to_cached_ms={self._fmt_or_absent(_call_to_cached)} "
                f"call_to_first_node_ms={self._fmt_or_absent(_call_to_first_node)} "
                f"first_node_to_clip_ms={self._fmt_or_absent(_first_node_to_clip_ms)} "
                f"clip_to_sampler_node_ms={self._fmt_or_absent(_clip_to_sampler_node_ms)} "
                f"sampler_node_to_sampler_start_ms={self._fmt_or_absent(_sampler_node_to_sampler_start_ms)} "
                f"sampler_node_to_lane_acquired_ms={self._fmt_or_absent(_sampler_node_to_lane_acquired_ms)} "
                f"lane_acquired_to_actual_stage_ms={self._fmt_or_absent(_lane_acquired_to_actual_stage_ms)} "
                f"pre_sampler_total_ms={self._fmt_or_absent(_pre_sampler_total_ms)} "
                f"measured_children_ms={self._fmt_or_absent(_measured_children_ms)} "
                f"residual_ms={self._fmt_or_absent(_residual_ms)} "
                f"reconciliation_status={_reconciliation_status} "
                f"add_message={_milestone_wrapper_ok} "
                f"send_sync={_send_sync_wrapper_ok} "
                f"has_sampler={_has_sampler} "
                f"sampler_count={len(_sampler_node_ids)} "
                f"lane_acquired={_lane_acquired[0]}",
                flush=True,
            )
            trace.emit(
                "prompt_executor_end",
                phase="execution",
                metadata={"elapsed_ms": round((time.time() - started) * 1000.0, 3)},
            )
            if context.cancelled and context.cancelled():
                raise RuntimeError("execution cancelled after PromptExecutor completion")
            if getattr(executor, "success", True) is False:
                raise RuntimeError(self._executor_error_message(executor))

            trace.emit("output_collect_start", phase="output")
            registry = pop_outputs(prompt_id) if production_enabled and callable(pop_outputs) else {}
            if not isinstance(registry, Mapping):
                registry = {}
            history_result = getattr(executor, "history_result", None)
            history = {prompt_id: history_result} if isinstance(history_result, dict) else {}
            output_dir = Path("/root/comfy/ComfyUI/output")
            trace.emit(
                "output_chain_start",
                phase="output",
                metadata={"prompt_id": prompt_id},
            )
            chain = build_default_chain(
                registry=registry,
                history=history,
                materials_dir=str(output_dir) if output_dir.is_dir() else "",
            )
            attempts = run_strategy_chain(
                chain,
                prompt_id=prompt_id,
                output_node_ids=tuple(plan.output_node_ids),
                materials_dir=str(output_dir) if output_dir.is_dir() else "",
                request_start_boundary=started,
            )
            trace.emit(
                "output_chain_end",
                phase="output",
                metadata={
                    "prompt_id": prompt_id,
                    "attempts": len(attempts),
                    "successful": sum(1 for a in attempts if a.success),
                },
            )
            selected_index = next(
                (index for index, attempt in enumerate(attempts) if attempt.success),
                None,
            )
            selected = attempts[selected_index] if selected_index is not None else None
            if selected is None:
                if production_enabled:
                    raise RuntimeError("v2 production execution produced no materializable output")
                selected = Attempt(strategy="none", success=False, error="no output")
            output_format = str(legacy_options.get("output_format", "original") or "original")
            if selected.success and selected.strategy != "direct_output_sink" and output_format != "original":
                trace.emit(
                    "output_conversion_start",
                    phase="output",
                    metadata={
                        "format": output_format,
                        "items": len(selected.items),
                    },
                )
                try:
                    converted = convert_output_items(
                        list(selected.items),
                        output_format=output_format,
                        quality=int(legacy_options.get("quality", 75) or 75),
                        webp_lossless_compression=str(
                            legacy_options.get("webp_lossless_compression", "balanced")
                        ),
                    )
                except ConversionFailedError as exc:
                    # The registry path is already encoded by the production
                    # node. For history/filesystem compatibility, retain the
                    # original bytes when a requested conversion cannot run.
                    selected = Attempt(
                        strategy=selected.strategy,
                        success=selected.success,
                        items=selected.items,
                        total_items=selected.total_items,
                        total_raw_bytes=selected.total_raw_bytes,
                        total_base64_bytes=selected.total_base64_bytes,
                        total_json_result_bytes=selected.total_json_result_bytes,
                        total_conversion_time_ms=selected.total_conversion_time_ms,
                        error=str(exc),
                        metrics={**dict(selected.metrics), "conversion_fallback": True},
                    )
                else:
                    selected = Attempt(
                        strategy=selected.strategy,
                        success=bool(converted.items),
                        items=tuple(converted.items),
                        total_items=len(converted.items),
                        total_raw_bytes=converted.total_raw_bytes,
                        total_base64_bytes=converted.total_base64_bytes,
                        total_json_result_bytes=converted.total_json_result_bytes,
                        total_conversion_time_ms=converted.total_conversion_time_ms,
                        error="" if converted.items else "output conversion produced no items",
                        metrics={**dict(selected.metrics), "converted": True},
                    )
                if selected_index is not None:
                    attempts[selected_index] = selected
                _conv_ok = selected.success and selected.strategy != "direct_output_sink" and output_format != "original"
                trace.emit(
                    "output_conversion_end",
                    phase="output",
                    metadata={
                        "format": output_format,
                        "success": _conv_ok,
                        "error": selected.error if not _conv_ok else "",
                        "conversion_time_ms": round(getattr(selected, "total_conversion_time_ms", 0), 3),
                        "fallback": bool(
                            selected.metrics.get("conversion_fallback")
                        ) if hasattr(selected, "metrics") and isinstance(selected.metrics, Mapping) else False,
                    },
                )
            result = self._attempt_to_result(selected)
            result["output_attempts"] = [
                {
                    "strategy": attempt.strategy,
                    "success": attempt.success,
                    "total_items": attempt.total_items,
                    "total_raw_bytes": attempt.total_raw_bytes,
                    "total_base64_bytes": attempt.total_base64_bytes,
                    "error": attempt.error,
                    "metrics": dict(attempt.metrics),
                }
                for attempt in attempts
            ]
            result["_registry_used"] = bool(attempts and attempts[0].success)
            result["_registry_entries"] = attempts[0].total_items if attempts else 0

            # ── Phase 6: measure serialized result payload size ────────
            payload_bytes = _measure_json_bytes(result)
            selected = dataclasses.replace(
                selected,
                serialized_result_bytes=payload_bytes,
                metrics=MappingProxyType({**dict(selected.metrics), "serialized_result_bytes": payload_bytes}),
            )
            if selected_index is not None:
                result["output_attempts"][selected_index]["metrics"]["serialized_result_bytes"] = payload_bytes

            trace.emit(
                "output_collect_end",
                phase="output",
                metadata={
                    "strategy": selected.strategy,
                    "items": selected.total_items,
                    "raw_bytes": selected.total_raw_bytes,
                    "serialized_result_bytes": payload_bytes,
                },
            )

            _stage_windows = getattr(api, "_stage_windows", None)
            if _stage_windows:
                _stages: dict[str, float] = {}
                for _stage, _sk, _ek in _V2_STAGE_MAP:
                    _fields = _stage_windows.get(_stage, {})
                    _s = _fields.get("start")
                    _e = _fields.get("end")
                    if _s is not None:
                        _stages[_sk] = _s
                    if _e is not None:
                        _stages[_ek] = _e
                if _stages:
                    result["_stage_timings"] = _stages

            # ── Write validation certificate after successful execution ──
            # Schema v2 certs include preflight_ok=True to attest that
            # deterministic preflight completed successfully for this identity.
            # Only write when preflight actually ran (not on cert skip).
            if _v2_schedule_cert_write and _v2_preflight_ran:
                _write_v2_validation_certificate(
                    _v2_cert_identity,
                    outputs_to_execute,
                    node_errors,
                    components=_v2_cert_components,
                    preflight_ok=True,
                )

            return result
        finally:
            # Release sampler lane if acquired during execution.
            # Must happen before production cleanup to ensure GPU
            # commit lane is free before any post-execution work.
            if _lane is not None and _lane_acquired[0]:
                _lane.release("sampler")
            if production_enabled:
                trace.emit("production_cleanup_start", phase="output")
            if production_enabled and callable(cleanup_request):
                cleanup_request(prompt_id)
            if production_enabled and callable(cleanup_registry):
                cleanup_registry(prompt_id)
            if production_enabled:
                trace.emit("production_cleanup_end", phase="output")

    @staticmethod
    def _executor_error_message(executor: Any) -> str:
        messages = getattr(executor, "status_messages", [])
        errors = [
            payload.get("exception_message", str(payload))
            for event, payload in messages
            if event == "execution_error" and isinstance(payload, dict)
        ]
        return "; ".join(errors) or "ComfyUI PromptExecutor failed"

    @staticmethod
    def _attempt_to_result(attempt: Attempt) -> dict[str, Any]:
        outputs: dict[str, dict[str, list[dict[str, Any]]]] = {}
        images: list[dict[str, Any]] = []
        videos: list[dict[str, Any]] = []
        for item in attempt.items:
            output_key = item.output_key or ("gifs" if item.animated else "images")
            data = item.base64_data or base64.b64encode(item.raw_bytes).decode("ascii")
            entry = {
                "filename": item.filename,
                "data": data,
                "node_id": item.node_id,
                "output_key": output_key,
                "comparison_side": item.comparison_side,
                "mime_type": item.mime_type,
                "file_ext": item.file_ext,
                "width": item.width,
                "height": item.height,
                "output_index": item.output_index,
                "format": item.format,
            }
            outputs.setdefault(item.node_id, {}).setdefault(output_key, []).append(entry)
            if item.animated or output_key in {"gifs", "videos"}:
                videos.append(entry)
            else:
                images.append(entry)
        return {"images": images, "videos": videos, "outputs": outputs}

    async def run_plan_stream(
        self,
        plan_payload: Mapping[str, Any],
        *,
        request_id: str = "",
        cancelled: Callable[[], bool] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        # ── TRUE METHOD FIRST LINE (before any identity or trace exists) ──
        _method_first_line_ns = time.monotonic_ns()
        _method_first_line_wall_ns = int(time.time() * 1_000_000_000)
        _method_first_line_pid = os.getpid()
        _method_restore_marker = get_restore_return_marker()
        _entry_host = _capture_host_info()

        identity = _capture_remote_identity()
        _identity_capture_end_ns = time.monotonic_ns()

        # ── Extract request origin info before deserialization ─────
        _request_origin_info: dict[str, Any] = {}
        _safe_payload = dict(plan_payload) if isinstance(plan_payload, Mapping) else plan_payload
        if isinstance(_safe_payload, dict):
            _request_origin_info = dict(_safe_payload.pop("__request_origin_info__", {}) or {})
        _t4_request_id = str(_request_origin_info.get("request_id", request_id or ""))

        plan = ExecutionPlan.from_dict(_safe_payload if isinstance(_safe_payload, dict) else plan_payload)
        _deserialize_end_ns = time.monotonic_ns()

        # ── Compute method entry gap before any trace output ─────────
        _method_entry_gap_results: dict[str, Any] = {}
        try:
            # Durations are valid only when all process identities match.
            _marker_restored_id = (_method_restore_marker or {}).get("restored_instance_id", "")
            _marker_restore_session_id = (_method_restore_marker or {}).get("restore_session_id", "")
            _marker_task_id = (_method_restore_marker or {}).get("modal_task_id", "")
            _marker_pid = (_method_restore_marker or {}).get("pid", 0)
            _marker_boot_id = (_method_restore_marker or {}).get("boot_id", "")
            _marker_hostname = (_method_restore_marker or {}).get("hostname", "")
            _current_rid = self._restored_instance_id if hasattr(self, "_restored_instance_id") else ""
            _current_restore_session_id = (self._restore_timing or {}).get("restore_session_id", "")
            _current_task_id = identity.get("container_task_id", "")
            _current_host = _entry_host
            _identity_matches = {
                "restored_instance_id": bool(_current_rid and _current_rid == _marker_restored_id),
                "restore_session_id": bool(_current_restore_session_id and _current_restore_session_id == _marker_restore_session_id),
                "modal_task_id": bool(_current_task_id and _current_task_id == _marker_task_id),
                "pid": bool(_method_first_line_pid == _marker_pid),
                "boot_id": bool(_marker_boot_id and _marker_boot_id == _current_host.get("boot_id", "")),
                "hostname": bool(_marker_hostname and _marker_hostname == _current_host.get("hostname", "")),
            }
            _same_process = all(
                _identity_matches[key]
                for key in ("restored_instance_id", "modal_task_id", "pid", "boot_id")
            )
            _method_entry_gap_results["identity_matches"] = _identity_matches
            _method_entry_gap_results["identity_mismatch_reasons"] = [
                key for key, matched in _identity_matches.items() if not matched
            ]
            if _same_process and _method_restore_marker is not None:
                _restore_return_ns = _method_restore_marker.get("monotonic_ns", 0)
                if _restore_return_ns and _method_first_line_ns >= _restore_return_ns:
                    _method_entry_gap_results["restore_return_to_method_first_line_ms"] = round(
                        (_method_first_line_ns - _restore_return_ns) / 1_000_000, 3
                    )
                _method_entry_gap_results["same_process"] = True
                _method_entry_gap_results["cross_process_duration_unavailable"] = False
            else:
                _method_entry_gap_results["same_process"] = False
                _method_entry_gap_results["cross_process_duration_unavailable"] = True
        except Exception as exc:
            _method_entry_gap_results["same_process"] = False
            _method_entry_gap_results["cross_process_duration_unavailable"] = True
            _method_entry_gap_results["identity_mismatch_reasons"] = [f"identity_check_error:{type(exc).__name__}"]

        # ── Continue with normal setup ──────────────────────────────
        # Use a local event buffer until trace exists
        _pre_trace_events: list[dict[str, Any]] = [
            {"name": "run_plan_method_first_line", "phase": "method",
             "wall_unix_ns": _method_first_line_wall_ns,
             "monotonic_ns": _method_first_line_ns,
             "metadata": {"pid": _method_first_line_pid, **_entry_host}}
        ]

        context = ExecutionContext(
            request_id=_t4_request_id or request_id,
            cancelled=cancelled,
            trace=RuntimeTrace(request_id=_t4_request_id or request_id, process="remote"),
        )
        context.trace.set_metadata(
            **identity,
            trace_id=context.trace.trace_id,
            restored_instance_id=getattr(self, "_restored_instance_id", ""),
            restore_session_id=(self._restore_timing or {}).get("restore_session_id", ""),
            legacy_container_session_id=self.container_session_id or _V2_CONTAINER_SESSION_ID,
            request_origin_info=_request_origin_info,
            **_entry_host,
            **_resource_identity(),
        )

        if isinstance(_request_origin_info, dict):
            _origin_events = (
                ("ui_or_test_run_triggered", _request_origin_info.get("ui_run_triggered_wall_unix_ms"), "t0"),
                ("local_run_request_received", _request_origin_info.get("local_receive_wall_ns"), "t1"),
            )
            for _name, _timestamp, _boundary in _origin_events:
                if isinstance(_timestamp, (int, float)) and _timestamp > 0:
                    _wall_ns = int(_timestamp * (1_000_000 if _boundary == "t0" else 1))
                    context.trace.emit_at(
                        _name,
                        wall_unix_ns=_wall_ns,
                        process="local",
                        phase="request_origin",
                        metadata={
                            "request_id": _t4_request_id or request_id,
                            "trigger_source": _request_origin_info.get("trigger_source", ""),
                            "benchmark_run_index": _request_origin_info.get("benchmark_run_index"),
                        },
                    )

        # Now merge pre-trace events into the real trace
        for _pt_event in _pre_trace_events:
            context.trace.emit_at(
                _pt_event["name"],
                wall_unix_ns=_pt_event["wall_unix_ns"],
                monotonic_ns=_pt_event["monotonic_ns"],
                phase=_pt_event["phase"],
                metadata={**_pt_event.get("metadata", {}),
                          "deferred": True},
            )

        # ── Emit identity capture/deserialize/trace-setup spans ─────
        context.trace.emit(
            "run_plan_identity_capture_start",
            phase="method",
            metadata={"pid": _method_first_line_pid},
        )
        context.trace.emit(
            "run_plan_identity_capture_end",
            phase="method",
            metadata={
                "capture_ms": round((_identity_capture_end_ns - _method_first_line_ns) / 1_000_000, 3),
            },
        )
        context.trace.emit("run_plan_deserialize_start", phase="method")
        context.trace.emit(
            "run_plan_deserialize_end",
            phase="method",
            metadata={
                "deserialize_ms": round((_deserialize_end_ns - _identity_capture_end_ns) / 1_000_000, 3),
            },
        )

        # ── Emit method entry gap summary ───────────────────────────
        _first_line_to_now_ms = round((time.monotonic_ns() - _method_first_line_ns) / 1_000_000, 3)
        context.trace.emit(
            "run_plan_method_entry_gap",
            phase="method",
            metadata={
                **_method_entry_gap_results,
                "method_first_line_to_running_log_ms": _first_line_to_now_ms,
            },
        )

        print(
            f"[v2.method_entry_gap] "
            f"restore_to_method_ms={_method_entry_gap_results.get('restore_return_to_method_first_line_ms')} "
            f"first_line_to_running_log_ms={_first_line_to_now_ms} "
            f"same_process={_method_entry_gap_results.get('same_process')} "
            f"identity_mismatch_reasons={','.join(_method_entry_gap_results.get('identity_mismatch_reasons', [])) or 'none'}",
            flush=True,
        )

        # ── Normal trace setup ──────────────────────────────────────
        if context.trace is not None:
            _auth_cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
            context.trace.container_session_id = _auth_cid
            context.trace.set_metadata(
                **identity,
                trace_id=context.trace.trace_id,
                restored_instance_id=getattr(self, "_restored_instance_id", ""),
                restore_session_id=(self._restore_timing or {}).get("restore_session_id", ""),
                legacy_container_session_id=_auth_cid,
                request_origin_info=_request_origin_info,
                **_resource_identity(),
            )
            _wf_hash_prefix = plan.workflow_hash[:16] if plan.workflow_hash else ""
            _src_wf_hash_prefix = plan.source_workflow_hash[:16] if plan.source_workflow_hash else ""
            try:
                _opts_dict = plan.execution_options.to_dict() if hasattr(plan, "execution_options") and plan.execution_options else {}
                _opts_hash = stable_hash(_opts_dict) if _opts_dict else ""
            except Exception:
                _opts_hash = ""

            # ── Emit trace-setup span (remote_method_entry at original first-line time) ──
            context.trace.emit("run_plan_trace_setup_start", phase="method")
            context.trace.emit_at(
                "remote_method_entry",
                wall_unix_ns=_method_first_line_wall_ns,
                monotonic_ns=_method_first_line_ns,
                phase="method",
                metadata={
                    "app_name": APP_NAME,
                    "class_name": CLASS_NAME,
                    "method_name": "run_plan_stream",
                    "workflow_hash": plan.workflow_hash,
                    "workflow_hash_prefix": _wf_hash_prefix,
                    "source_workflow_hash": plan.source_workflow_hash,
                    "source_workflow_hash_prefix": _src_wf_hash_prefix,
                    "effective_options_hash": _opts_hash,
                    # ── Correlation identity ──────────────────────
                    "restored_instance_id": getattr(self, "_restored_instance_id", ""),
                    "restore_session_id": (self._restore_timing or {}).get("restore_session_id", ""),
                    "legacy_container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
                    # ── Request origin identity ───────────────────
                    "request_id": _t4_request_id,
                    "trigger_source": _request_origin_info.get("trigger_source", ""),
                    # ── Remote-observed identity ──────────────────
                    **identity,
                    **_resource_identity(),
                },
            )
            context.trace.emit(
                "container_entry",
                phase="execution",
                metadata={
                    "container_session_id": _auth_cid,
                    "workflow_hash": plan.workflow_hash,
                },
            )
            context.trace.emit("run_plan_trace_setup_end", phase="method")

        # ── First status yield ──────────────────────────────────────
        context.trace.emit("run_plan_first_status_yield", phase="method")
        yield {
            "type": "status",
            "phase": "plan_received",
            "request_id": request_id,
            "trace_id": context.trace.trace_id if context.trace else "",
        }
        async for event in self.executor.stream(plan, context=context):
            if event.get("type") == "result" and isinstance(event.get("data"), dict):
                data = dict(event["data"])
                _exec_trace = data.get("trace", {})
                _exec_stages = _exec_trace.get("stages") if isinstance(_exec_trace, Mapping) else None

                # ── Drain available background UNET diagnostics ────
                _bg_trace_events: list[dict[str, Any]] = []
                try:
                    from comfymodal_runtime.model_preload import _BG_UNET_DIAG_STORE, _BG_UNET_DIAG_LOCK
                    with _BG_UNET_DIAG_LOCK:
                        for _canonical_key in list(_BG_UNET_DIAG_STORE.keys()):
                            _bg_trace_events.extend(_BG_UNET_DIAG_STORE.pop(_canonical_key, []))
                except Exception:
                    pass

                merged = merge_runtime_traces(
                    self._lifecycle_trace,
                    _exec_trace,
                )
                _authoritative_cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
                if _authoritative_cid:
                    merged.container_session_id = _authoritative_cid
                # Merge background UNET diagnostic events into the result trace
                if _bg_trace_events:
                    merged.extend(_bg_trace_events)
                # ── Event identity enrichment ────────────────────────
                # Backfill missing request_id, restore IDs, task/input/pid/tid
                # on lifecycle and background events now that the authoritative
                # request_id is known.  Updates BOTH event.request_id (top-level
                # serialized field) and event.metadata identity keys.
                # Does NOT overwrite nonempty values.
                _enrich_identity = {
                    "request_id": _t4_request_id,
                    "restored_instance_id": getattr(self, "_restored_instance_id", ""),
                    "restore_session_id": (self._restore_timing or {}).get("restore_session_id", ""),
                    "modal_task_id": identity.get("container_task_id", ""),
                }
                _enrich_identity = {k: v for k, v in _enrich_identity.items() if v}
                if _enrich_identity:
                    for _evt in merged.events:
                        # Update top-level request_id if empty
                        if _t4_request_id and not _evt.request_id:
                            object.__setattr__(_evt, "request_id", _t4_request_id)
                        # Update metadata identity keys if missing
                        if hasattr(_evt, "metadata") and isinstance(_evt.metadata, dict):
                            for _ek, _ev in _enrich_identity.items():
                                if _ek not in _evt.metadata or not _evt.metadata.get(_ek):
                                    _evt.metadata[_ek] = _ev
                # Ensure merged.request_id is set to authoritative value
                if _t4_request_id:
                    merged.request_id = _t4_request_id
                # Merge legacy stages from events with node-stage windows.
                # Node-stage windows win for exact keys; legacy stages fill
                # gaps (e.g. container_entry -> t3_modal_entry).
                _legacy_stages = merged.to_legacy_timing().get("stages", {})
                if _exec_stages:
                    _legacy_stages.update(_exec_stages)
                data["trace"] = merged.to_dict()
                data["trace"]["stages"] = _legacy_stages
                data["phase_durations_ms"] = merged.export_phase_durations()
                _rt = self._restore_timing or _LATEST_LIFECYCLE_TIMING
                if _rt is not None and "_restore_timing" not in data:
                    data["_restore_timing"] = dict(_rt)
                # ── Request-origin summary (T0–T5) ──────────────────
                # Gather raw wall timestamps from origin info + local captures
                _t4_wall = _method_first_line_wall_ns
                _t4_request = _t4_request_id
                _trig_src = _request_origin_info.get("trigger_source", "unknown")
                _t0_wall = _request_origin_info.get("ui_run_triggered_wall_unix_ms", None)
                if _t0_wall is not None:
                    _t0_wall_ns = int(_t0_wall * 1_000_000)  # convert ms→ns
                else:
                    _t0_wall_ns = None
                _t1_wall_ns = _request_origin_info.get("local_receive_wall_ns", None)
                _t2_wall_ns = _request_origin_info.get("modal_submission_attempt_wall_ns", None)
                _t3_wall_ns = _request_origin_info.get("modal_generator_created_wall_ns", None)
                # Extract authoritative T5 from remote V2 prompt_executor_invoke_start event.
                # Filter for process=remote to ignore legacy/duplicate traces.
                # Iterate until a remote event with non-empty t5_wall_ns is found;
                # do NOT break on the first remote event missing the raw timestamp.
                _t5_wall_ns = None
                if isinstance(_exec_trace, dict):
                    _exec_events = _exec_trace.get("events", [])
                    if isinstance(_exec_events, list):
                        for _evt in _exec_events:
                            if isinstance(_evt, dict) and _evt.get("name") == "prompt_executor_invoke_start":
                                _evt_proc = _evt.get("process", "") or ""
                                if _evt_proc == "remote":
                                    _evt_meta = _evt.get("metadata", {}) or {}
                                    _t5_raw = _evt_meta.get("t5_wall_ns")
                                    if _t5_raw:
                                        _t5_wall_ns = int(_t5_raw)
                                        break

                # Compute all eight intervals with clock-scope metadata.
                # Cross-process intervals MUST use wall; same-process may use mono.
                # T0(browser)→T1(server): cross-process → wall
                _t0_t1_ms = round((_t1_wall_ns - _t0_wall_ns) / 1_000_000, 3) if _t0_wall_ns and _t1_wall_ns else None
                _t0_t1_scope = "wall_cross_process" if _t0_wall_ns and _t1_wall_ns else None
                # T1(server)→T2(server): same-process → mono preferred
                _t1_t2_ms = None
                _t1_t2_scope = None
                _t1_mono = _request_origin_info.get("local_receive_mono_ns", None)
                _t2_mono = _request_origin_info.get("modal_submission_attempt_mono_ns", None)
                if _t1_mono and _t2_mono:
                    _t1_t2_ms = round((_t2_mono - _t1_mono) / 1_000_000, 3)
                    _t1_t2_scope = "mono_same_process"
                elif _t1_wall_ns and _t2_wall_ns:
                    _t1_t2_ms = round((_t2_wall_ns - _t1_wall_ns) / 1_000_000, 3)
                    _t1_t2_scope = "wall_fallback"
                # T2(server)→T3(server): same-process → mono
                _t2_t3_ms = None
                _t2_t3_scope = None
                if _t2_mono and _request_origin_info.get("modal_generator_created_mono_ns"):
                    _t2_t3_ms = round((_request_origin_info["modal_generator_created_mono_ns"] - _t2_mono) / 1_000_000, 3)
                    _t2_t3_scope = "mono_same_process"
                elif _t2_wall_ns and _t3_wall_ns:
                    _t2_t3_ms = round((_t3_wall_ns - _t2_wall_ns) / 1_000_000, 3)
                    _t2_t3_scope = "wall_fallback"
                # T2(server)→T4(remote): cross-process → wall
                _t2_t4_ms = round((_t4_wall - _t2_wall_ns) / 1_000_000, 3) if _t2_wall_ns and _t4_wall else None
                _t2_t4_scope = "wall_cross_process" if _t2_wall_ns and _t4_wall else None
                # T3(server)→T4(remote): cross-process → wall
                _t3_t4_ms = round((_t4_wall - _t3_wall_ns) / 1_000_000, 3) if _t3_wall_ns and _t4_wall else None
                _t3_t4_scope = "wall_cross_process" if _t3_wall_ns and _t4_wall else None
                # T4(remote)→T5(remote): same-process → mono
                _t4_t5_ms = None
                _t4_t5_scope = None
                _t5_mono_from_trace = None
                if isinstance(_exec_trace, dict):
                    _exec_events = _exec_trace.get("events", [])
                    if isinstance(_exec_events, list):
                        for _evt in _exec_events:
                            if isinstance(_evt, dict) and _evt.get("name") == "prompt_executor_invoke_start":
                                _evt_proc = _evt.get("process", "") or ""
                                if _evt_proc == "remote":
                                    _evt_meta = _evt.get("metadata", {}) or {}
                                    _t5_mono_candidate = _evt_meta.get("t5_mono_ns")
                                    if _t5_mono_candidate:
                                        _t5_mono_from_trace = _t5_mono_candidate
                                        break
                if _method_first_line_ns and _t5_mono_from_trace:
                    _t4_t5_ms = round((_t5_mono_from_trace - _method_first_line_ns) / 1_000_000, 3)
                    _t4_t5_scope = "mono_same_process"
                elif _t4_wall and _t5_wall_ns:
                    _t4_t5_ms = round((_t5_wall_ns - _t4_wall) / 1_000_000, 3)
                    _t4_t5_scope = "wall_fallback"
                # T0(browser)→T4(remote): cross-process → wall
                _t0_t4_ms = round((_t4_wall - _t0_wall_ns) / 1_000_000, 3) if _t0_wall_ns and _t4_wall else None
                _t0_t4_scope = "wall_cross_process" if _t0_wall_ns and _t4_wall else None
                # T0(browser)→T5(remote): cross-process → wall
                _t0_t5_ms = round((_t5_wall_ns - _t0_wall_ns) / 1_000_000, 3) if _t0_wall_ns and _t5_wall_ns else None
                _t0_t5_scope = "wall_cross_process" if _t0_wall_ns and _t5_wall_ns else None

                # Embed raw timestamps + intervals + clock scope in result data
                data["request_id"] = _t4_request
                data["trigger_source"] = _trig_src
                data["raw_timestamps"] = {
                    "t0_ui_trigger_wall_unix_ns": _t0_wall_ns,
                    "t1_local_receive_wall_unix_ns": _t1_wall_ns,
                    "modal_submission_attempt_wall_unix_ns": _t2_wall_ns,
                    "modal_generator_created_wall_unix_ns": _t3_wall_ns,
                    "t4_modal_method_entry_wall_unix_ns": _t4_wall,
                    "t5_prompt_executor_invoke_start_wall_unix_ns": _t5_wall_ns,
                }
                data["intervals_ms"] = {
                    "run_trigger_to_local_receive_ms": _t0_t1_ms,
                    "local_receive_to_actual_submission_ms": _t1_t2_ms,
                    "generator_create_ms": _t2_t3_ms,
                    "actual_submission_to_method_entry_ms": _t2_t4_ms,
                    "generator_created_to_entry_ms": _t3_t4_ms,
                    "method_entry_to_prompt_executor_ms": _t4_t5_ms,
                    "run_trigger_to_modal_entry_ms": _t0_t4_ms,
                    "run_trigger_to_prompt_executor_ms": _t0_t5_ms,
                }
                data["clock_scopes"] = {
                    "run_trigger_to_local_receive": _t0_t1_scope,
                    "local_receive_to_actual_submission": _t1_t2_scope,
                    "generator_create": _t2_t3_scope,
                    "actual_submission_to_method_entry": _t2_t4_scope,
                    "generator_created_to_entry": _t3_t4_scope,
                    "method_entry_to_prompt_executor": _t4_t5_scope,
                    "run_trigger_to_modal_entry": _t0_t4_scope,
                    "run_trigger_to_prompt_executor": _t0_t5_scope,
                }

                _modal_input_id = identity.get("modal_input_id", "")
                _modal_task_id = identity.get("container_task_id", "")

                # ── Exact one-line [v2.request_origin] summary ──────
                _trig_to_dispatch = _t0_t1_ms  # same as run_trigger_to_local_receive
                _dispatch_to_entry = _t2_t4_ms
                _entry_to_exec = _t4_t5_ms       # same as method_entry_to_prompt_executor
                _trig_to_exec = _t0_t5_ms        # same as run_trigger_to_prompt_executor
                print(
                    f"[v2.remote_request_origin] "
                    f"request_id={_t4_request} "
                    f"trigger_source={_trig_src} "
                    f"ui_trigger_unix_ms={self._fmt_or_absent(_t0_wall)} "
                    f"local_receive_unix_ns={self._fmt_or_absent(_t1_wall_ns)} "
                    f"modal_submission_attempt_unix_ns={self._fmt_or_absent(_t2_wall_ns)} "
                    f"modal_generator_created_unix_ns={self._fmt_or_absent(_t3_wall_ns)} "
                    f"modal_method_entry_unix_ns={_t4_wall} "
                    f"prompt_executor_invoke_start_unix_ns={self._fmt_or_absent(_t5_wall_ns)} "
                    f"trigger_to_dispatch_ms={_trig_to_dispatch} "
                    f"dispatch_to_modal_entry_ms={_dispatch_to_entry} "
                    f"modal_entry_to_executor_ms={_entry_to_exec} "
                    f"trigger_to_executor_ms={_trig_to_exec} "
                    f"modal_input_id={_modal_input_id} "
                    f"modal_task_id={_modal_task_id}",
                    flush=True,
                )
                event = {**event, "data": data}
            yield event

    async def run_prompt_stream(
        self,
        workflow: dict,
        input_images: dict | None = None,
        trace: dict | None = None,
        modal_options: dict | None = None,
        production_report: dict | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        from .contracts import ExecutionOptions

        plan = ExecutionPlan(
            workflow=workflow,
            input_images=input_images or {},
            production_report=production_report or {},
            execution_options=ExecutionOptions.from_legacy(
                modal_options,
                production_report=production_report or {},
                default_production=bool((production_report or {}).get("enabled")),
            ),
            request_metadata={"trace": dict(trace or {})},
        )
        plan_dict = plan.to_dict()
        # Propagate request_origin_info from the trace dict so it reaches
        # run_plan_stream on the v2 benchmark/legacy path.
        if isinstance(trace, dict):
            _roi = trace.get("request_origin_info", None)
            if _roi and isinstance(_roi, dict):
                plan_dict["__request_origin_info__"] = dict(_roi)
        async for event in self.run_plan_stream(plan_dict):
            yield event

    async def publish_restore_plan(self, plan_payload: Mapping[str, Any]) -> dict[str, Any]:
        identity = _capture_remote_identity()
        plan = RestorePlan.from_dict(plan_payload)
        result = await asyncio.to_thread(_publish_restore_plan_impl, plan)
        authoritative = self._get_remote_restore_publisher().read_current_plan()
        self._restore_plan = authoritative or plan
        result.setdefault("identity", {}).update(identity)
        return result

    async def run_checkpoint_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        if self.checkpoint_runner is None:
            yield {"type": "error", "message": "checkpoint compatibility runner is not configured"}
            return
        result = self.checkpoint_runner(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        if hasattr(result, "__aiter__"):
            async for event in result:
                yield event
        elif isinstance(result, dict):
            yield {"type": "result", "data": result}


def _build_decorated_v2_class() -> type:
    """Build a ``ModalRuntimeEntrypointV2`` subclass with all Modal lifecycle
    and method decorators applied, but WITHOUT ``modal.concurrent()`` or
    ``app.cls()`` binding (which requires resources).

    This must be called BEFORE ``build_modal_resources()`` so the decorated
    class (with finalized ``enter``/``method`` registrations) is exported
    to ``globals()`` regardless of resource availability.  Modal's worker
    importer needs the decorated raw class at module level; replacing it
    with a plain ``ModalRuntimeEntrypoint`` would cause ``KeyError`` on
    ``run_plan_stream`` in the container IO manager.

    When ``_modal`` is unavailable, returns ``None`` and the caller should
    export a plain compatibility alias instead.
    """
    if _modal is None:
        return None
    cls = type("ModalRuntimeEntrypointV2", (ModalRuntimeEntrypoint,), {})
    setattr(cls, "startup", _modal.enter(snap=True)(cls.startup))
    setattr(cls, "restore", _modal.enter(snap=False)(cls.restore))
    setattr(cls, "run_plan_stream", _modal.method(is_generator=True)(cls.run_plan_stream))
    setattr(cls, "run_prompt_stream", _modal.method(is_generator=True)(cls.run_prompt_stream))
    setattr(cls, "publish_restore_plan", _modal.method()(cls.publish_restore_plan))
    setattr(cls, "run_checkpoint_stream", _modal.method(is_generator=True)(cls.run_checkpoint_stream))
    return cls


def _register_remote_entrypoint(resources: Mapping[str, Any], spec: ModalRuntimeSpec) -> Any:
    if _modal is None or resources.get("app") is None:
        return None

    # The raw decorated class was already exported by the module tail.
    # Reuse it for concurrent + app binding; do NOT re-create it (that
    # would register duplicate Modal functions).
    remote_class = globals().get("ModalRuntimeEntrypointV2")
    if remote_class is None or remote_class is ModalRuntimeEntrypoint:
        # Guard: if the decorated class somehow wasn't set (e.g. _modal was
        # unavailable when _build_decorated_v2_class was called but became
        # available now), build it fresh.
        remote_class = _build_decorated_v2_class()
        if remote_class is not None:
            globals()["ModalRuntimeEntrypointV2"] = remote_class
    if remote_class is None:
        return None

    remote_class = _modal.concurrent(
        target_inputs=spec.target_inputs,
        max_inputs=spec.max_inputs,
    )(remote_class)
    _enable_gpu_snapshot = os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"
    return resources["app"].cls(
        gpu=spec.gpu,
        cpu=spec.cpu,
        memory=spec.memory,
        timeout=spec.timeout,
        min_containers=spec.min_containers,
        scaledown_window=spec.scaledown_window,
        volumes={
            spec.models_path: resources["models_volume"],
            spec.custom_nodes_path: resources["custom_nodes_volume"],
            spec.runtime_state_path: resources["runtime_state_volume"],
        },
        enable_memory_snapshot=spec.enable_memory_snapshot,
        **({"experimental_options": {"enable_gpu_snapshot": True}} if _enable_gpu_snapshot else {}),
    )(remote_class)


def _publish_restore_plan_impl(plan: RestorePlan) -> dict[str, Any]:
    resources = globals().get("_MODAL_RESOURCES", {})
    modal_volume = resources.get("runtime_state_volume")
    if modal_volume is None:
        # The volume is mounted via the function's ``volumes={...}``
        # declaration, but the module-level ``_MODAL_RESOURCES`` fallback
        # may not carry the live handle.  Resolve the named Volume from
        # inside the remote function as a remote-safe fallback.
        try:
            import modal as _modal_fallback
            modal_volume = _modal_fallback.Volume.from_name(
                RUNTIME_STATE_VOLUME_NAME, create_if_missing=False,
            )
        except Exception:
            modal_volume = None
    if modal_volume is None:
        raise RuntimeError("v2 runtime-state Modal Volume is not mounted")
    volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
    coordinator = CommitCoordinator(volume, state_path=V2_RESTORE_STATE_FILE)
    publisher = RestorePlanPublisher(coordinator)
    result = publisher.publish_with_metrics(plan)
    readback_started = time.perf_counter()
    authoritative = publisher.read_current_plan()
    readback_ms = round((time.perf_counter() - readback_started) * 1000.0, 3)
    if authoritative is None:
        raise RuntimeError("published RestorePlan could not be read back from runtime-state Volume")
    # ── Add publish_readback event to publication trace ────────────
    pub_trace = result.get("trace", {})
    if isinstance(pub_trace, dict) and "events" in pub_trace:
        pub_trace["events"].append({
            "name": "publish_readback",
            "phase": "publish",
            "wall_unix_ns": int(time.time() * 1_000_000_000),
            "monotonic_ns": time.monotonic_ns(),
            "process": "publisher",
            "metadata": {"readback_ms": readback_ms},
        })
    result.update({
        "status": "published" if result.get("changed") else "unchanged",
        "generation": authoritative.generation,
        "canonical_hash": authoritative.canonical_hash,
        "runtime_state_volume": RUNTIME_STATE_VOLUME_NAME,
        "state_path": V2_RESTORE_STATE_FILE,
        "readback_ms": readback_ms,
        "models_volume_write_count": 0,
        "models_volume_commit_count": 0,
    })
    return result


def publish_restore_plan_remote(plan_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Publish before GPU class lookup so the next snap=False sees the plan."""
    identity = _capture_remote_identity()
    result = _publish_restore_plan_impl(RestorePlan.from_dict(plan_payload))
    result.setdefault("identity", {}).update(identity)
    return result


# ── ModalRuntimeEntrypointV2: decorated class exported BEFORE resource
#    construction so Modal's finalized function registry (enter/method)
#    is always populated.  Resource-independent: only depends on _modal
#    being importable.  When _modal is unavailable, export a plain
#    compatibility alias (no decorated methods, but prevents crash-loop
#    on missing attribute).
_v2_decorated_class = _build_decorated_v2_class()
globals()["ModalRuntimeEntrypointV2"] = (
    _v2_decorated_class if _v2_decorated_class is not None else ModalRuntimeEntrypoint
)

try:
    _MODAL_RESOURCES = build_modal_resources()
except Exception:
    _MODAL_RESOURCES = {
        "app": None,
        "image": None,
        "models_volume": None,
        "custom_nodes_volume": None,
        "runtime_state_volume": None,
        "source_identity": None,
        "spec": ModalRuntimeSpec(),
    }
# Modal CLI discovers the application through a module-level ``app`` object.
# Keep the resource construction above as the single source of truth while
# exposing the registered shadow app for ``modal deploy -m``.
app = _MODAL_RESOURCES.get("app")
ModalRuntimeEntrypointRemote = _register_remote_entrypoint(
    _MODAL_RESOURCES,
    _MODAL_RESOURCES["spec"],
)
if _modal is not None and _MODAL_RESOURCES.get("app") is not None:
    publish_restore_plan_remote = _MODAL_RESOURCES["app"].function(
        image=_MODAL_RESOURCES["image"],
        cpu=2,
        memory=4096,
        timeout=300,
        min_containers=MIN_CONTAINERS,
        max_containers=1,
        scaledown_window=SCALEDOWN_WINDOW,
        volumes={
            _MODAL_RESOURCES["spec"].runtime_state_path: _MODAL_RESOURCES["runtime_state_volume"],
        },
    )(publish_restore_plan_remote)
