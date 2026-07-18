"""Explicit execution backend selection and streaming."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping

from .contracts import ExecutionPlan
from .trace import RuntimeTrace


@dataclass
class BackendDiagnostics:
    requested: str = "in_process"
    selected: str = ""
    selection_reason: str = ""
    fallback_attempted: bool = False
    fallback_reason: str = ""
    fallback_result: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ExecutionContext:
    request_id: str = ""
    cancelled: Callable[[], bool] | None = None
    progress: Callable[[dict[str, Any]], Any] | None = None
    trace: RuntimeTrace | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeExecutor:
    """Execute a plan once using an explicit backend policy."""

    def __init__(
        self,
        *,
        in_process_runner: Callable[..., Any] | None = None,
        subprocess_runner: Callable[..., Any] | None = None,
        allow_compatibility_fallback: bool = False,
    ) -> None:
        self.in_process_runner = in_process_runner
        self.subprocess_runner = subprocess_runner
        self.allow_compatibility_fallback = allow_compatibility_fallback

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        ctx = context or ExecutionContext()
        diagnostics = self.select_backend(plan.execution_options.requested_backend)
        started = time.perf_counter()
        runner = self._runner_for(diagnostics.selected)
        try:
            if runner is None:
                raise RuntimeError(f"requested execution backend unavailable: {diagnostics.selected}")
            result = runner(plan, ctx)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                result = {"result": result}
            result.setdefault("backend", diagnostics.to_dict())
            return result
        except Exception as exc:
            if (
                diagnostics.selected == "in_process"
                and self.allow_compatibility_fallback
                and self.subprocess_runner is not None
            ):
                diagnostics.fallback_attempted = True
                diagnostics.fallback_reason = f"{type(exc).__name__}: {exc}"
                diagnostics.selected = "subprocess"
                diagnostics.fallback_result = "attempted"
                result = self.subprocess_runner(plan, ctx)
                if inspect.isawaitable(result):
                    result = await result
                if not isinstance(result, dict):
                    result = {"result": result}
                result["backend"] = diagnostics.to_dict()
                return result
            diagnostics.fallback_result = "not_attempted"
            raise
        finally:
            diagnostics.elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)

    async def stream(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        ctx = context or ExecutionContext()
        diagnostics = self.select_backend(plan.execution_options.requested_backend)
        runner = self._runner_for(diagnostics.selected)
        if runner is None:
            yield {"type": "error", "message": f"requested execution backend unavailable: {diagnostics.selected}", "backend": diagnostics.to_dict()}
            return
        started = time.perf_counter()
        try:
            result = runner(plan, ctx)
            if inspect.isawaitable(result):
                result = await result
            if hasattr(result, "__aiter__"):
                async for event in result:
                    if ctx.cancelled and ctx.cancelled():
                        raise asyncio.CancelledError()
                    if isinstance(event, dict):
                        if ctx.progress and event.get("type") in {"progress", "status"}:
                            ctx.progress(event)
                        yield event
                return
            if hasattr(result, "__iter__") and not isinstance(result, (dict, str, bytes)):
                for event in result:
                    if ctx.cancelled and ctx.cancelled():
                        raise asyncio.CancelledError()
                    if isinstance(event, dict):
                        if ctx.progress and event.get("type") in {"progress", "status"}:
                            ctx.progress(event)
                        yield event
                return
            payload = result if isinstance(result, dict) else {"result": result}
            payload.setdefault("backend", diagnostics.to_dict())
            yield {"type": "result", "data": payload}
        except Exception as exc:
            yield {"type": "error", "message": str(exc), "backend": diagnostics.to_dict()}
        finally:
            diagnostics.elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)

    def select_backend(self, requested: str) -> BackendDiagnostics:
        normalized = str(requested or "in_process").strip().lower()
        if normalized in {"safe", "in_process", "production"}:
            if self.in_process_runner is not None:
                return BackendDiagnostics(requested=normalized, selected="in_process", selection_reason="runner_available")
            if normalized == "safe" and self.subprocess_runner is not None:
                return BackendDiagnostics(requested=normalized, selected="subprocess", selection_reason="safe_compatibility_runner")
            return BackendDiagnostics(requested=normalized, selected="in_process", selection_reason="runner_missing")
        if normalized in {"subprocess", "compatibility"}:
            return BackendDiagnostics(requested=normalized, selected="subprocess", selection_reason="explicit_request")
        raise ValueError(f"unsupported execution backend: {requested}")

    def _runner_for(self, selected: str) -> Callable[..., Any] | None:
        return self.in_process_runner if selected == "in_process" else self.subprocess_runner
