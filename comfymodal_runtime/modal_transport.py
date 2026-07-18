"""Typed transport boundary for prompt and checkpoint streams."""

from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Mapping

from .contracts import ExecutionPlan


try:
    import modal as _modal
except Exception:
    _modal = None


class TransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class HandleCacheKey:
    workspace: str
    app_name: str
    target: str
    gpu: str


class HandleCache:
    def __init__(self) -> None:
        self._values: dict[HandleCacheKey, Any] = {}

    def get(self, key: HandleCacheKey) -> Any:
        return self._values.get(key)

    def put(self, key: HandleCacheKey, value: Any) -> Any:
        self._values[key] = value
        return value

    def clear(self) -> None:
        self._values.clear()


class ModalTransport:
    """Pass a canonical plan directly to the registered v2 Modal class."""

    def __init__(
        self,
        *,
        prompt_stream_fn: Callable[..., Any] | None = None,
        checkpoint_stream_fn: Callable[..., Any] | None = None,
        restore_plan_fn: Callable[..., Any] | None = None,
        v2_handle_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.prompt_stream_fn = prompt_stream_fn
        self.checkpoint_stream_fn = checkpoint_stream_fn
        self.restore_plan_fn = restore_plan_fn
        self.v2_handle_factory = v2_handle_factory
        self.handle_cache = HandleCache()

    def _v2_handle(
        self,
        *,
        workspace: dict[str, Any] | None,
        gpu: str | None,
    ) -> Any:
        selected_gpu = str(gpu or os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")).strip().lower()
        app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
        class_name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
        workspace_id = str((workspace or {}).get("id", "default"))
        key = HandleCacheKey(workspace_id, app_name, class_name, selected_gpu)
        cached = self.handle_cache.get(key)
        if cached is not None:
            return cached
        if self.v2_handle_factory is not None:
            handle = self.v2_handle_factory(
                workspace=workspace,
                app_name=app_name,
                class_name=class_name,
                gpu=selected_gpu,
            )
            return self.handle_cache.put(key, handle)
        if _modal is None:
            raise TransportError("Modal SDK is unavailable for the v2 transport")
        if not workspace or not workspace.get("token_id") or not workspace.get("token_secret"):
            raise TransportError("v2 transport requires an active Modal workspace with credentials")
        try:
            client = _modal.Client.from_credentials(
                workspace["token_id"], workspace["token_secret"],
            )
            cls_handle = _modal.Cls.from_name(app_name, class_name, client=client)
            handle = cls_handle()
        except Exception as exc:
            raise TransportError(f"v2 Modal handle lookup failed: {exc}") from exc
        return self.handle_cache.put(key, handle)

    async def run_plan_stream(
        self,
        plan: ExecutionPlan,
        *,
        gpu: str | None = None,
        workspace: dict[str, Any] | None = None,
        trace: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        fn = self.prompt_stream_fn
        try:
            if fn is not None:
                stream = fn(
                    workflow=plan.to_dict()["workflow"],
                    input_images=plan.to_dict()["input_images"],
                    trace=dict(trace or {}),
                    production_report=plan.to_dict()["production_report"],
                    gpu=gpu,
                    modal_options=plan.execution_options.to_legacy_dict(),
                    workspace=workspace,
                )
            else:
                handle = self._v2_handle(workspace=workspace, gpu=gpu)
                request_id = str((trace or {}).get("prompt_id", ""))
                stream = handle.run_plan_stream.remote_gen.aio(
                    plan.to_dict(), request_id=request_id,
                )
            if hasattr(stream, "__aiter__"):
                async for event in stream:
                    yield event
            else:
                result = await stream if inspect.isawaitable(stream) else stream
                if isinstance(result, dict):
                    yield {"type": "result", "data": result}
        except Exception as exc:
            raise TransportError(str(exc)) from exc

    async def run_checkpoint_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        fn = self.checkpoint_stream_fn
        if fn is not None:
            stream = fn(*args, **kwargs)
        else:
            handle = self._v2_handle(
                workspace=kwargs.pop("workspace", None),
                gpu=kwargs.pop("gpu", None),
            )
            stream = handle.run_checkpoint_stream.remote_gen.aio(*args, **kwargs)
        if hasattr(stream, "__aiter__"):
            async for event in stream:
                yield event
        else:
            result = await stream if inspect.isawaitable(stream) else stream
            if isinstance(result, dict):
                yield {"type": "result", "data": result}

    async def publish_restore_plan(self, payload: Mapping[str, Any], *, workspace: dict[str, Any] | None = None) -> Any:
        fn = self.restore_plan_fn
        if fn is not None:
            result = fn(dict(payload), workspace=workspace)
            return await result if inspect.isawaitable(result) else result
        handle = self._v2_handle(workspace=workspace, gpu=None)
        return await asyncio.to_thread(
            handle.publish_restore_plan.remote,
            dict(payload),
        )
