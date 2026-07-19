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

from .contracts import ExecutionPlan, RestorePlan, _thaw, stable_hash
from .deployment_spec import build_deployment_identity
from .restore_plan import RestorePlanPublisher
from .runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from .runtime_executor import ExecutionContext, RuntimeExecutor
from .runtime_state import CommitCoordinator, ModalMountedStateVolume
from .model_preload import V2LoaderBridge
from .output_delivery import (
    Attempt,
    _measure_json_bytes,
    build_default_chain,
    run_strategy_chain,
)
from .result_delivery import ConversionFailedError, convert_output_items
from .trace import RuntimeTrace, merge_runtime_traces


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

# V1-parity module-level stable identity so instance/snapshot boundaries cannot erase identity.
# Set once at import time, before any Modal instance construction.
_V2_CONTAINER_SESSION_ID: str = uuid.uuid4().hex[:16]
_V2_CONTAINER_IMPORT_UNIX_S: float = time.time()
_v2_container_restore_count: int = 0

V2_SOURCE_MODULES = (
    "comfyapp",
    "canonical_execution",
    "modal_client",
    "run_prompt_options",
    "comfymodal_runtime",
)


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
    """Reuse the working ComfyUI image and add the v2 source manifest."""
    try:
        legacy = importlib.import_module("comfyapp")
        image = getattr(legacy, "image", None)
        if image is None:
            raise RuntimeError("comfyapp.image is unavailable")
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
        trace.container_session_id = self.container_session_id
        trace.set_metadata(**identity)
        trace.set_metadata(container_session_id=self.container_session_id)
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
                "container_session_id": self.container_session_id,
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
        }

    def restore(self) -> dict[str, Any]:
        global _LATEST_LIFECYCLE_TIMING, _v2_container_restore_count
        _restore_perf_start = time.perf_counter()
        identity = _capture_remote_identity()
        self._configure_runtime()
        trace = RuntimeTrace(process="remote")
        trace.container_session_id = self.container_session_id
        trace.set_metadata(**identity)
        trace.set_metadata(container_session_id=self.container_session_id)
        _v2_container_restore_count += 1
        self._restore_count = _v2_container_restore_count
        restore_session_id = uuid.uuid4().hex
        trace.emit(
            "remote_method_entry",
            phase="lifecycle",
            metadata={
                "app_name": APP_NAME,
                "class_name": CLASS_NAME,
                "method_name": "restore",
                "snapshot": "False",
                "restore_session_id": restore_session_id,
                "restore_count": str(self._restore_count),
                "container_session_id": self.container_session_id,
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
            state = self.bootstrap.restore(trace=trace)
        except Exception as exc:
            _lifecycle_error = str(exc)[:200]
            trace.emit("remote_lifecycle_end", phase="restore", metadata={"status": "error", "error": _lifecycle_error})
            self._remember_lifecycle_trace(trace)
            restore_total_ms = round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)
            err_timing: dict[str, Any] = {
                "restore_total_ms": restore_total_ms,
                "restore_session_id": restore_session_id,
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
            preparation = self._preload_bridge.prepare(self._restore_plan, trace=trace)
            trace.emit("preload_submission_end", phase="restore", metadata={
                "preload_scheduled": str(bool(preparation)),
            })
            trace.set_metadata(
                restore_plan_generation=str(self._restore_plan.generation),
                preload_scheduled=bool(preparation),
                preload_diagnostics=self._preload_bridge.diagnostics(),
            )
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
        trace.emit("remote_lifecycle_end", phase="restore", metadata={"status": "restored"})
        self._remember_lifecycle_trace(trace)
        trace = self._lifecycle_trace or trace

        restore_total_ms = round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)
        _restore_timing: dict[str, Any] = {
            "restore_total_ms": restore_total_ms,
            "restore_session_id": restore_session_id,
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

        print(
            f"[v2.lifecycle] method=restore snap=False "
            f"container_session={_V2_CONTAINER_SESSION_ID} "
            f"restore_count={self._restore_count} "
            f"restore_total_ms={restore_total_ms} "
            f"status=restored"
        )

        return {
            "backend": state.backend,
            "cuda": dict(state.cuda),
            "runtime_generation": state.runtime_generation,
            "status": "restored",
            "_restore_timing": _restore_timing,
            "trace": trace.to_dict(),
        }

    async def _run_in_process(self, plan: ExecutionPlan, context: ExecutionContext) -> dict[str, Any]:
        if context.cancelled and context.cancelled():
            raise RuntimeError("execution cancelled before PromptExecutor start")
        self._configure_runtime()
        api = self._load_legacy_runtime()
        trace = context.trace or RuntimeTrace(request_id=context.request_id, process="remote")
        # Attach stable container identity to execution trace
        _cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
        trace.container_session_id = _cid
        trace.emit("graph_execution_start", phase="execution")
        try:
            with self._preload_bridge.request_scope():
                result: dict[str, Any] = await self._execute_v2_prompt_executor(plan, context, api, trace)
            trace.emit("graph_execution_end", phase="execution")
            trace.set_metadata(
                restore_plan_generation=str(self._restore_plan.generation if self._restore_plan else ""),
                execution_backend="in_process",
                preload_diagnostics=self._preload_bridge.diagnostics(),
                container_session_id=_cid,
            )
            result["trace"] = trace.to_dict()
            result["container_session_id"] = _cid
            result["restore_plan_generation"] = str(self._restore_plan.generation if self._restore_plan else "")
            _rt = self._restore_timing or _LATEST_LIFECYCLE_TIMING
            if _rt is not None:
                result["_restore_timing"] = dict(_rt)
            return result
        except Exception as exc:
            trace.emit("graph_execution_end", phase="execution", metadata={"status": "error", "error": str(exc)[:200]})
            raise

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

        preflight = getattr(api, "_preflight_before_prompt_execution", None)
        if callable(preflight) and not getattr(api, "_preflight_already_ran", False):
            trace.emit("preflight_start", phase="execution")
            preflight(workflow)
            trace.emit("preflight_end", phase="execution")

        repair_missing_nodes = getattr(api, "_repair_missing_workflow_nodes", None)
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

        import execution

        trace.emit("prompt_validation_start", phase="execution", metadata={"prompt_id": prompt_id})
        valid, error, outputs_to_execute, node_errors = await execution.validate_prompt(
            prompt_id, workflow, None
        )
        trace.emit(
            "prompt_validation_end",
            phase="execution",
            metadata={
                "valid": bool(valid),
                "output_count": len(outputs_to_execute or []),
                "node_error_count": len(node_errors or {}),
            },
        )
        if not valid:
            detail = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise RuntimeError(f"Workflow validation failed: {detail}")

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

        started = time.time()
        try:
            trace.emit("executor_reset_start", phase="execution")
            executor.reset()
            trace.emit("executor_reset_end", phase="execution")
            trace.emit("prompt_executor_start", phase="execution", metadata={"prompt_id": prompt_id})
            execute_async = getattr(executor, "execute_async", None)
            execute_kwargs = {
                "prompt": workflow,
                "prompt_id": prompt_id,
                "extra_data": {"client_id": prompt_id},
                "execute_outputs": outputs_to_execute,
            }
            if callable(execute_async):
                execute_result = execute_async(**execute_kwargs)
                if inspect.isawaitable(execute_result):
                    await execute_result
            else:
                executor.execute(**execute_kwargs)
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
            return result
        finally:
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
        identity = _capture_remote_identity()
        plan = ExecutionPlan.from_dict(plan_payload)
        context = ExecutionContext(
            request_id=request_id,
            cancelled=cancelled,
            trace=RuntimeTrace(request_id=request_id, process="remote"),
        )
        if context.trace is not None:
            context.trace.set_metadata(**identity)
            # ── Additive common-schema identity keys ──────────────────
            # workflow_hash_prefix: first 16 hex chars for stable short-id.
            _wf_hash_prefix = plan.workflow_hash[:16] if plan.workflow_hash else ""
            _src_wf_hash_prefix = plan.source_workflow_hash[:16] if plan.source_workflow_hash else ""
            # effective_options_hash: stable hash of execution options.
            try:
                _opts_dict = plan.execution_options.to_dict() if hasattr(plan, "execution_options") and plan.execution_options else {}
                _opts_hash = stable_hash(_opts_dict) if _opts_dict else ""
            except Exception:
                _opts_hash = ""
            context.trace.emit(
                "remote_method_entry",
                phase="method",
                metadata={
                    # ── App / class / method ──────────────────────
                    "app_name": APP_NAME,
                    "class_name": CLASS_NAME,
                    "method_name": "run_plan_stream",
                    # ── Workflow identity ─────────────────────────
                    "workflow_hash": plan.workflow_hash,
                    "workflow_hash_prefix": _wf_hash_prefix,
                    "source_workflow_hash": plan.source_workflow_hash,
                    "source_workflow_hash_prefix": _src_wf_hash_prefix,
                    "effective_options_hash": _opts_hash,
                    # ── Remote-observed identity ──────────────────
                    **identity,
                    **_resource_identity(),
                },
            )
        yield {
            "type": "status",
            "phase": "plan_received",
            "request_id": request_id,
            "trace_id": context.trace.trace_id if context.trace else "",
        }
        async for event in self.executor.stream(plan, context=context):
            if event.get("type") == "result" and isinstance(event.get("data"), dict):
                data = dict(event["data"])
                merged = merge_runtime_traces(
                    self._lifecycle_trace,
                    data.get("trace"),
                )
                # Use stable module-level identity — never overwrite a non-empty
                # authoritative container_session_id with an empty placeholder.
                _authoritative_cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
                if _authoritative_cid:
                    merged.container_session_id = _authoritative_cid
                data["trace"] = merged.to_dict()
                _rt = self._restore_timing or _LATEST_LIFECYCLE_TIMING
                if _rt is not None and "_restore_timing" not in data:
                    data["_restore_timing"] = dict(_rt)
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
        async for event in self.run_plan_stream(plan.to_dict()):
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


def _register_remote_entrypoint(resources: Mapping[str, Any], spec: ModalRuntimeSpec) -> Any:
    if _modal is None or resources.get("app") is None:
        return None

    remote_class = type("ModalRuntimeEntrypointV2", (ModalRuntimeEntrypoint,), {})
    setattr(remote_class, "startup", _modal.enter(snap=True)(remote_class.startup))
    setattr(remote_class, "restore", _modal.enter(snap=False)(remote_class.restore))
    setattr(remote_class, "run_plan_stream", _modal.method(is_generator=True)(remote_class.run_plan_stream))
    setattr(remote_class, "run_prompt_stream", _modal.method(is_generator=True)(remote_class.run_prompt_stream))
    setattr(remote_class, "publish_restore_plan", _modal.method()(remote_class.publish_restore_plan))
    setattr(remote_class, "run_checkpoint_stream", _modal.method(is_generator=True)(remote_class.run_checkpoint_stream))
    # Export the raw class. Modal's worker importer resolves this module
    # attribute and reapplies the serialized concurrency/class settings; the
    # result of modal.concurrent() is a PartialFunction and cannot be used as
    # the importer class object.
    globals()["ModalRuntimeEntrypointV2"] = remote_class
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
