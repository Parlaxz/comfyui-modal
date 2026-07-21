"""Typed transport boundary for prompt and checkpoint streams."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Mapping

from .contracts import ExecutionPlan

if TYPE_CHECKING:
    from .trace import RuntimeTrace

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
    cloud: str = ""
    environment: str = ""


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

    @staticmethod
    def _resolve_v2_cloud(gpu: str) -> str:
        """Resolve the Modal cloud placement for a v2 GPU class lookup.

        Returns the cloud name (e.g. ``"gcp"``) or ``""`` for global scheduling.
        Only an explicit ``COMFYMODAL_V2_CLOUD`` environment value is returned;
        no implicit GPU→cloud pinning is applied.  Callers that require matched
        V1/V2 placement must set the env var on both sides.
        """
        explicit = os.environ.get("COMFYMODAL_V2_CLOUD", "").strip()
        if explicit:
            return explicit
        return ""

    @staticmethod
    def _resolve_environment() -> str:
        """Resolve the Modal environment name.

        ``COMFYMODAL_V2_ENVIRONMENT`` takes precedence over
        ``MODAL_ENVIRONMENT``.  Returns ``""`` when neither is set so callers
        can pass ``None`` to SDK lookups, which uses the default environment.
        """
        env = os.environ.get("COMFYMODAL_V2_ENVIRONMENT", "")
        if env:
            return env.strip()
        env = os.environ.get("MODAL_ENVIRONMENT", "")
        if env:
            return env.strip()
        return ""

    def _v2_handle(
        self,
        *,
        workspace: dict[str, Any] | None,
        gpu: str | None,
        runtime_trace: RuntimeTrace | None = None,
    ) -> Any:
        selected_gpu = str(gpu or os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")).strip().lower()
        app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
        class_name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
        workspace_id = str((workspace or {}).get("id", "default"))
        cloud = self._resolve_v2_cloud(selected_gpu)
        environment = self._resolve_environment()
        key = HandleCacheKey(workspace_id, app_name, class_name, selected_gpu, cloud=cloud, environment=environment)
        cached = self.handle_cache.get(key)
        if cached is not None:
            if runtime_trace is not None:
                runtime_trace.emit("handle_cache_hit", phase="local", metadata={
                    "app_name": app_name, "class_name": class_name,
                    "gpu": selected_gpu, "cloud": cloud,
                })
            return cached
        if runtime_trace is not None:
            runtime_trace.emit("handle_cache_miss", phase="local", metadata={
                "app_name": app_name, "class_name": class_name,
                "gpu": selected_gpu, "cloud": cloud,
            })
        if self.v2_handle_factory is not None:
            if runtime_trace is not None:
                runtime_trace.emit("handle_factory_resolve", phase="local")
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
        _handle_identity = {"app_name": app_name, "class_name": class_name, "gpu": selected_gpu, "cloud": cloud}
        try:
            if runtime_trace is not None:
                runtime_trace.emit("client_resolution_start", phase="local", metadata=_handle_identity)
            client = _modal.Client.from_credentials(
                workspace["token_id"], workspace["token_secret"],
            )
            if runtime_trace is not None:
                runtime_trace.emit("client_resolution_end", phase="local")
                runtime_trace.emit("class_lookup_start", phase="local", metadata=_handle_identity)
            cls_handle = _modal.Cls.from_name(
                app_name, class_name, client=client,
                environment_name=environment or None,
            )
            if runtime_trace is not None:
                runtime_trace.emit("class_lookup_end", phase="local")
            if cloud:
                if runtime_trace is not None:
                    runtime_trace.emit("with_options_start", phase="local", metadata={"cloud": cloud})
                cls_handle = cls_handle.with_options(cloud=cloud)
                if runtime_trace is not None:
                    runtime_trace.emit("with_options_end", phase="local")
            if runtime_trace is not None:
                runtime_trace.emit("instance_construction_start", phase="local")
            handle = cls_handle()
            if runtime_trace is not None:
                runtime_trace.emit("instance_construction_end", phase="local")
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
        runtime_trace: RuntimeTrace | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        fn = self.prompt_stream_fn
        request_id = str((trace or {}).get("prompt_id", ""))
        _origin_from_meta: dict[str, Any] = {}
        _modal_input_id = ""
        _modal_input_created_at: Any = None
        _modal_input_id_emitted = False
        _generator_start_wall_ns = 0
        _generator_start_mono_ns = 0
        _generator_end_wall_ns = 0
        _generator_end_mono_ns = 0
        try:
            if fn is not None:
                # V1-compatible stream path — measure plan serialization
                if runtime_trace is not None:
                    runtime_trace.emit("plan_serialize_for_transport_start", phase="local")
                plan_dict_workflow = plan.to_dict()["workflow"]
                plan_dict_images = plan.to_dict()["input_images"]
                plan_dict_report = plan.to_dict()["production_report"]
                if runtime_trace is not None:
                    rt_plan_dict = {
                        "workflow_bytes": len(str(plan_dict_workflow)),
                        "input_image_count": len(plan_dict_images),
                        "images_base64_byte_estimate": sum(
                            len(v) for v in plan_dict_images.values()
                        ),
                    }
                    runtime_trace.emit("plan_serialize_for_transport_end", phase="local",
                                       metadata=rt_plan_dict)
                stream = fn(
                    workflow=plan_dict_workflow,
                    input_images=plan_dict_images,
                    trace=dict(trace or {}),
                    production_report=plan_dict_report,
                    gpu=gpu,
                    modal_options=plan.execution_options.to_legacy_dict(),
                    workspace=workspace,
                )
            else:
                if runtime_trace is not None:
                    runtime_trace.emit("modal_handle_lookup_start", phase="local")
                handle = self._v2_handle(
                    workspace=workspace, gpu=gpu, runtime_trace=runtime_trace,
                )
                if runtime_trace is not None:
                    runtime_trace.emit("modal_handle_lookup_end", phase="local")
                    runtime_trace.emit("modal_payload_serialize_start", phase="local")
                plan_dict = plan.to_dict()
                if isinstance(trace, dict):
                    _trace_meta = trace.get("metadata", {}) or {}
                    if isinstance(_trace_meta, dict):
                        _origin_from_meta = dict(_trace_meta.get("request_origin_info", {}))
                request_id = str(_origin_from_meta.get("request_id") or request_id)
                if _origin_from_meta:
                    plan_dict["__request_origin_info__"] = _origin_from_meta
                _payload_bytes = len(json.dumps(plan_dict, separators=(",", ":"), default=str).encode("utf-8"))
                if runtime_trace is not None:
                    runtime_trace.emit("modal_payload_serialize_end", phase="local", metadata={
                        "plan_dict_bytes": _payload_bytes,
                        "workflow_hash": plan.workflow_hash,
                    })
                _generator_start_wall_ns = time.time_ns()
                _generator_start_mono_ns = time.monotonic_ns()
                if runtime_trace is not None:
                    runtime_trace.emit("modal_generator_create_start", phase="local", metadata={
                        "wall_ns": _generator_start_wall_ns,
                        "mono_ns": _generator_start_mono_ns,
                        "request_id": request_id,
                        "payload_bytes": _payload_bytes,
                    })
                stream = handle.run_plan_stream.remote_gen.aio(
                    plan_dict, request_id=request_id,
                )
                _generator_end_wall_ns = time.time_ns()
                _generator_end_mono_ns = time.monotonic_ns()
                _modal_input_id = str(getattr(stream, "input_id", "") or "")
                _modal_input_created_at = getattr(stream, "input_created_at", None)
                _modal_input_id_emitted = False
                if runtime_trace is not None:
                    runtime_trace.emit("modal_generator_created", phase="local", metadata={
                        "wall_ns": _generator_end_wall_ns,
                        "mono_ns": _generator_end_mono_ns,
                        "request_id": request_id,
                        "modal_input_id": _modal_input_id,
                        "modal_input_created_at": _modal_input_created_at,
                    })
                    runtime_trace.emit("modal_generator_create_end", phase="local")
                    # Emit modal_input_id_observed at creation boundary when
                    # input_id is already exposed by the SDK immediately after
                    # .remote_gen.aio().
                    if _modal_input_id:
                        runtime_trace.emit("modal_input_id_observed", phase="local", metadata={
                            "modal_input_id": _modal_input_id,
                        })
                        _modal_input_id_emitted = True
            if hasattr(stream, "__aiter__"):
                iterator = stream.__aiter__()
                _submission_wall_ns = time.time_ns()
                _submission_mono_ns = time.monotonic_ns()
                if runtime_trace is not None and fn is None:
                    # Use emit_at so the event wall/monotonic timestamps match
                    # the captured boundary — no normal emit() between capture
                    # and __anext__.
                    runtime_trace.emit_at(
                        "modal_submission_attempt",
                        wall_unix_ns=_submission_wall_ns,
                        monotonic_ns=_submission_mono_ns,
                        phase="local",
                        metadata={
                            "request_id": request_id if fn is None else "",
                        },
                    )
                try:
                    first_event = await iterator.__anext__()
                except StopAsyncIteration:
                    return
                _first_event_wall_ns = time.time_ns()
                _first_event_mono_ns = time.monotonic_ns()
                if fn is None:
                    _modal_input_id = str(
                        getattr(stream, "input_id", "")
                        or getattr(iterator, "input_id", "")
                        or _modal_input_id
                    )
                    _modal_input_created_at = (
                        getattr(stream, "input_created_at", None)
                        or getattr(iterator, "input_created_at", None)
                        or _modal_input_created_at
                    )
                if runtime_trace is not None:
                    runtime_trace.emit("modal_first_event_received", phase="local", metadata={
                        "event_type": first_event.get("type", "") if isinstance(first_event, dict) else "",
                        "modal_input_id": _modal_input_id if fn is None else "",
                        "wall_ns": _first_event_wall_ns,
                        "mono_ns": _first_event_mono_ns,
                    })
                    # Emit modal_input_id_observed after first iteration when
                    # it was not available at creation time.  The flag prevents
                    # a duplicate observation event.
                    if fn is None and _modal_input_id and not _modal_input_id_emitted:
                        runtime_trace.emit("modal_input_id_observed", phase="local", metadata={
                            "modal_input_id": _modal_input_id,
                        })
                    if fn is None:
                        _t1_mono = _origin_from_meta.get("local_receive_mono_ns")
                        runtime_trace.set_metadata(
                            modal_generator_created_wall_ns=_generator_end_wall_ns,
                            modal_generator_created_mono_ns=_generator_end_mono_ns,
                            modal_submission_attempt_wall_ns=_submission_wall_ns,
                            modal_submission_attempt_mono_ns=_submission_mono_ns,
                            modal_first_event_received_wall_ns=_first_event_wall_ns,
                            modal_first_event_received_mono_ns=_first_event_mono_ns,
                            modal_input_id=_modal_input_id,
                            modal_input_created_at=_modal_input_created_at,
                            local_receive_to_generator_create_ms=(round((_generator_start_mono_ns - _t1_mono) / 1_000_000, 3) if isinstance(_t1_mono, int) else None),
                            generator_create_ms=round((_generator_end_mono_ns - _generator_start_mono_ns) / 1_000_000, 3),
                            generator_create_to_first_iteration_ms=round((_submission_mono_ns - _generator_end_mono_ns) / 1_000_000, 3),
                            first_iteration_to_first_remote_event_ms=round((_first_event_mono_ns - _submission_mono_ns) / 1_000_000, 3),
                            local_receive_to_actual_submission_ms=(round((_submission_mono_ns - _t1_mono) / 1_000_000, 3) if isinstance(_t1_mono, int) else None),
                        )
                yield first_event
                async for event in iterator:
                    if runtime_trace is not None and isinstance(event, dict) and event.get("type") == "result":
                        runtime_trace.emit("final_result_received", phase="local")
                    yield event
            else:
                result = await stream if inspect.isawaitable(stream) else stream
                if isinstance(result, dict):
                    if runtime_trace is not None:
                        runtime_trace.emit("non_stream_result_received", phase="local")
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
            ait = stream.__aiter__()
            async for event in ait:
                yield event
        else:
            result = await stream if inspect.isawaitable(stream) else stream
            if isinstance(result, dict):
                yield {"type": "result", "data": result}

    async def publish_restore_plan(
        self,
        payload: Mapping[str, Any],
        *,
        workspace: dict[str, Any] | None = None,
        runtime_trace: RuntimeTrace | None = None,
    ) -> Any:
        fn = self.restore_plan_fn
        if fn is not None:
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_custom_fn", phase="local")
            result = fn(dict(payload), workspace=workspace)
            return await result if inspect.isawaitable(result) else result
        if self.v2_handle_factory is not None:
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_lookup_start", phase="local",
                                   metadata={"method": "v2_handle_factory"})
            handle = self._v2_handle(workspace=workspace, gpu=None)
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_lookup_end", phase="local")
                runtime_trace.emit("restore_publish_call_start", phase="local")
            pub_result = await asyncio.to_thread(handle.publish_restore_plan.remote, dict(payload))
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_call_end", phase="local",
                                   metadata={"generation": str(pub_result)})
            return pub_result
        if _modal is None:
            raise TransportError("Modal SDK is unavailable for the v2 transport")
        if not workspace or not workspace.get("token_id") or not workspace.get("token_secret"):
            raise TransportError("v2 transport requires an active Modal workspace with credentials")
        app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
        workspace_id = str(workspace.get("id", "default"))
        environment = self._resolve_environment()
        key = HandleCacheKey(workspace_id, app_name, "publish_restore_plan_remote", "cpu", environment=environment)
        function = self.handle_cache.get(key)
        if function is None:
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_lookup_start", phase="local",
                                   metadata={"method": "direct_sdk"})
            try:
                def _do_lookup():
                    c = _modal.Client.from_credentials(
                        workspace["token_id"], workspace["token_secret"],
                    )
                    return _modal.Function.from_name(
                        app_name, "publish_restore_plan_remote", client=c,
                        environment_name=environment or None,
                    )
                function = await asyncio.to_thread(_do_lookup)
            except Exception as exc:
                raise TransportError(f"v2 RestorePlan publisher lookup failed: {exc}") from exc
            self.handle_cache.put(key, function)
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_lookup_end", phase="local")
        else:
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_cache_hit", phase="local")
        if runtime_trace is not None:
            runtime_trace.emit("restore_publish_call_start", phase="local",
                               metadata={"payload_bytes": len(str(payload))})
        try:
            pub_result = await asyncio.to_thread(function.remote, dict(payload))
            if runtime_trace is not None:
                runtime_trace.emit("restore_publish_call_end", phase="local",
                                   metadata={"generation": str(pub_result)})
            return pub_result
        except Exception as exc:
            raise TransportError(f"v2 RestorePlan publication failed: {exc}") from exc
