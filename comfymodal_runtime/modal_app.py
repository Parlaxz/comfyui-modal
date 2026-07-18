"""Deployable v2 Modal application and its runtime entrypoint."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping

from .contracts import ExecutionPlan, RestorePlan
from .deployment_spec import build_deployment_identity
from .restore_plan import RestorePlanPublisher
from .runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from .runtime_executor import ExecutionContext, RuntimeExecutor
from .runtime_state import CommitCoordinator, ModalMountedStateVolume
from .trace import RuntimeTrace


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
RUNTIME_STATE_PATH = "/root/comfymodal_runtime"
V2_RESTORE_STATE_FILE = "v2_restore_plan.json"
MIN_CONTAINERS = 0
SCALEDOWN_WINDOW = 4
V2_SOURCE_MODULES = (
    "comfyapp",
    "canonical_execution",
    "modal_client",
    "run_prompt_options",
    "comfymodal_runtime",
)


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

        def start_backend() -> str:
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
            start_backend=start_backend,
            restore_gpu_state=restore_gpu_state,
            initialize_cuda=initialize_cuda,
            apply_sage_policy=apply_sage_policy,
            observe_generations=observe_generations,
        )
        self._runtime_configured = True

    def startup(self) -> dict[str, Any]:
        self._configure_runtime()
        trace = RuntimeTrace(process="remote")
        state = self.bootstrap.startup(snapshot=True, trace=trace)
        return {"backend": state.backend, "status": "ready", "trace": trace.to_dict()}

    def restore(self) -> dict[str, Any]:
        self._configure_runtime()
        trace = RuntimeTrace(process="remote")
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
        state = self.bootstrap.restore(trace=trace)
        return {
            "backend": state.backend,
            "cuda": dict(state.cuda),
            "runtime_generation": state.runtime_generation,
            "status": "restored",
            "trace": trace.to_dict(),
        }

    def _run_in_process(self, plan: ExecutionPlan, context: ExecutionContext) -> dict[str, Any]:
        if context.cancelled and context.cancelled():
            raise RuntimeError("execution cancelled before PromptExecutor start")
        self._configure_runtime()
        api = self._load_legacy_runtime()
        trace = context.trace or RuntimeTrace(request_id=context.request_id, process="remote")
        trace.emit("graph_execution_start", phase="execution")
        legacy_trace = None
        try:
            trace_factory = getattr(self._legacy_module, "Trace", None)
            legacy_trace = trace_factory(prompt_id=context.request_id) if trace_factory else None
            result = api._execute_in_process(
                dict(plan.workflow),
                input_images=dict(plan.input_images),
                collect_outputs=True,
                trace=legacy_trace,
                modal_options=plan.execution_options.to_legacy_dict(),
                production_report=dict(plan.production_report),
            )
            if not isinstance(result, dict):
                result = {"result": result}
            trace.emit("graph_execution_end", phase="execution")
            trace.set_metadata(
                restore_plan_generation=str(self._restore_plan.generation if self._restore_plan else ""),
                execution_backend="in_process",
            )
            result["trace"] = trace.to_dict()
            if legacy_trace is not None:
                result["legacy_trace"] = legacy_trace.summary()
            result["restore_plan_generation"] = str(self._restore_plan.generation if self._restore_plan else "")
            return result
        except Exception as exc:
            trace.emit("graph_execution_end", phase="execution", metadata={"status": "error", "error": str(exc)[:200]})
            raise

    async def run_plan_stream(
        self,
        plan_payload: Mapping[str, Any],
        *,
        request_id: str = "",
        cancelled: Callable[[], bool] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        plan = ExecutionPlan.from_dict(plan_payload)
        context = ExecutionContext(
            request_id=request_id,
            cancelled=cancelled,
            trace=RuntimeTrace(request_id=request_id, process="remote"),
        )
        yield {"type": "status", "phase": "plan_received", "request_id": request_id}
        async for event in self.executor.stream(plan, context=context):
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
        plan = RestorePlan.from_dict(plan_payload)
        result = await asyncio.to_thread(_publish_restore_plan_impl, plan)
        authoritative = self._get_remote_restore_publisher().read_current_plan()
        self._restore_plan = authoritative or plan
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
    remote_class = _modal.concurrent(
        target_inputs=spec.target_inputs,
        max_inputs=spec.max_inputs,
    )(remote_class)
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
    authoritative = publisher.read_current_plan()
    if authoritative is None:
        raise RuntimeError("published RestorePlan could not be read back from runtime-state Volume")
    result.update({
        "status": "published" if result.get("changed") else "unchanged",
        "generation": authoritative.generation,
        "canonical_hash": authoritative.canonical_hash,
        "runtime_state_volume": RUNTIME_STATE_VOLUME_NAME,
        "state_path": V2_RESTORE_STATE_FILE,
        "models_volume_write_count": 0,
        "models_volume_commit_count": 0,
    })
    return result


def publish_restore_plan_remote(plan_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Publish before GPU class lookup so the next snap=False sees the plan."""
    return _publish_restore_plan_impl(RestorePlan.from_dict(plan_payload))


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
