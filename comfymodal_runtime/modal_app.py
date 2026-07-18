"""Thin Modal application facade for the v2 runtime."""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Mapping

from .contracts import ExecutionPlan
from .runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from .runtime_executor import ExecutionContext, RuntimeExecutor


try:
    import modal as _modal
except Exception:
    _modal = None


APP_NAME = os.environ.get("COMFYMODAL_APP_NAME", "comfyui").strip() or "comfyui"
MODELS_VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")
RUNTIME_STATE_VOLUME_NAME = os.environ.get("COMFYMODAL_RUNTIME_STATE_VOLUME", "comfymodal-runtime-config")
MIN_CONTAINERS = 0
SCALEDOWN_WINDOW = 4


@dataclass(frozen=True)
class ModalRuntimeSpec:
    app_name: str = APP_NAME
    models_volume_name: str = MODELS_VOLUME_NAME
    runtime_state_volume_name: str = RUNTIME_STATE_VOLUME_NAME
    min_containers: int = MIN_CONTAINERS
    scaledown_window: int = SCALEDOWN_WINDOW


def build_modal_resources(*, spec: ModalRuntimeSpec | None = None) -> dict[str, Any]:
    """Build Modal resources lazily; no deployment occurs during import."""
    runtime_spec = spec or ModalRuntimeSpec()
    if _modal is None:
        return {"app": None, "image": None, "models_volume": None, "runtime_state_volume": None, "spec": runtime_spec}
    image = _modal.Image.debian_slim(python_version="3.11")
    models_volume = _modal.Volume.from_name(runtime_spec.models_volume_name, create_if_missing=True)
    runtime_state_volume = _modal.Volume.from_name(runtime_spec.runtime_state_volume_name, create_if_missing=True)
    app = _modal.App(runtime_spec.app_name, image=image)
    return {
        "app": app,
        "image": image,
        "models_volume": models_volume,
        "runtime_state_volume": runtime_state_volume,
        "spec": runtime_spec,
    }


class ModalRuntimeEntrypoint:
    """Remote facade that only parses, delegates, streams, and returns."""

    def __init__(
        self,
        *,
        bootstrap: RuntimeBootstrap | None = None,
        executor: RuntimeExecutor | None = None,
        config: BootstrapConfig | None = None,
        checkpoint_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.bootstrap = bootstrap or RuntimeBootstrap(config)
        self.executor = executor or RuntimeExecutor()
        self.checkpoint_runner = checkpoint_runner

    def startup(self) -> dict[str, Any]:
        state = self.bootstrap.startup(snapshot=True)
        return {"backend": state.backend, "status": "ready"}

    def restore(self) -> dict[str, Any]:
        state = self.bootstrap.restore()
        return {"backend": state.backend, "cuda": dict(state.cuda), "status": "restored"}

    async def run_plan_stream(
        self,
        plan_payload: Mapping[str, Any],
        *,
        request_id: str = "",
        cancelled: Callable[[], bool] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        plan = ExecutionPlan.from_dict(plan_payload)
        context = ExecutionContext(request_id=request_id, cancelled=cancelled)
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


if _modal is not None:
    setattr(ModalRuntimeEntrypoint, "startup", _modal.enter(snap=True)(ModalRuntimeEntrypoint.startup))
    setattr(ModalRuntimeEntrypoint, "restore", _modal.enter(snap=False)(ModalRuntimeEntrypoint.restore))
