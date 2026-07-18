"""Typed transport boundary for prompt and checkpoint streams."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Mapping

from .contracts import ExecutionPlan


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
    """Pass a canonical plan to the existing remote stream seam."""

    def __init__(
        self,
        *,
        prompt_stream_fn: Callable[..., Any] | None = None,
        checkpoint_stream_fn: Callable[..., Any] | None = None,
        restore_plan_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.prompt_stream_fn = prompt_stream_fn
        self.checkpoint_stream_fn = checkpoint_stream_fn
        self.restore_plan_fn = restore_plan_fn
        self.handle_cache = HandleCache()

    async def run_plan_stream(
        self,
        plan: ExecutionPlan,
        *,
        gpu: str | None = None,
        workspace: dict[str, Any] | None = None,
        trace: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        fn = self.prompt_stream_fn
        if fn is None:
            from modal_client import run_prompt_stream
            fn = run_prompt_stream
        try:
            stream = fn(
                workflow=plan.to_dict()["workflow"],
                input_images=plan.to_dict()["input_images"],
                trace=dict(trace or {}),
                production_report=plan.to_dict()["production_report"],
                gpu=gpu,
                modal_options=plan.execution_options.to_legacy_dict(),
                workspace=workspace,
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
        if fn is None:
            from modal_client import run_checkpoint_stream
            fn = run_checkpoint_stream
        stream = fn(*args, **kwargs)
        if hasattr(stream, "__aiter__"):
            async for event in stream:
                yield event
        else:
            result = await stream if inspect.isawaitable(stream) else stream
            if isinstance(result, dict):
                yield {"type": "result", "data": result}

    async def publish_restore_plan(self, payload: Mapping[str, Any], *, workspace: dict[str, Any] | None = None) -> Any:
        fn = self.restore_plan_fn
        if fn is None:
            from modal_client import set_active_warmup_profile
            fn = set_active_warmup_profile
        result = fn(dict(payload), workspace=workspace)
        return await result if inspect.isawaitable(result) else result
