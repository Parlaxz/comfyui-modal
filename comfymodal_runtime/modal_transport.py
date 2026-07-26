"""Typed transport boundary for prompt and checkpoint streams."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Mapping

from .contracts import ExecutionPlan
from .trace import (
    _build_local_submission_breakdown,
    _emit_breakdown_line,
)

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
    """Cache key for Modal function/cls handles.

    Equality is value-based so the same workspace/app/target/
    environment produces the same dict key across call boundaries.
    Invocation-time cloud overrides are excluded — target identity
    is purely workspace + environment + app + class.

    *cloud* (optional) isolates caches across different Modal cloud
    placements (e.g. ``"gcp"`` vs ``"aws"``).  *factory_identity*
    (optional) isolates caches across different ``v2_handle_factory``
    callables so that distinct factory objects never share a cached
    handle.  *gpu* (optional) isolates caches across different GPU
    configurations so that distinct GPU targets never share a cached
    handle.
    """

    workspace: str
    app_name: str
    target: str
    environment: str = ""
    cloud: str = ""
    gpu: str = ""
    factory_identity: object | None = None


class HandleCache:
    def __init__(self) -> None:
        self._values: dict[HandleCacheKey, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: HandleCacheKey) -> Any:
        with self._lock:
            return self._values.get(key)

    def put(self, key: HandleCacheKey, value: Any) -> Any:
        with self._lock:
            self._values[key] = value
        return value

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


_SHARED_HANDLE_CACHE = HandleCache()


class ModalTransport:
    """Pass a canonical plan directly to the registered v2 Modal class."""

    def __init__(
        self,
        *,
        prompt_stream_fn: Callable[..., Any] | None = None,
        checkpoint_stream_fn: Callable[..., Any] | None = None,
        restore_plan_fn: Callable[..., Any] | None = None,
        v2_handle_factory: Callable[..., Any] | None = None,
        handle_cache: HandleCache | None = None,
    ) -> None:
        self.prompt_stream_fn = prompt_stream_fn
        self.checkpoint_stream_fn = checkpoint_stream_fn
        self.restore_plan_fn = restore_plan_fn
        self.v2_handle_factory = v2_handle_factory
        self.handle_cache = handle_cache or _SHARED_HANDLE_CACHE

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

        Only ``COMFYMODAL_V2_ENVIRONMENT`` is honored; ambient
        ``MODAL_ENVIRONMENT`` is never consulted.  Returns ``""`` when unset so
        callers can pass ``None`` to SDK lookups, which uses the default
        deployed environment.
        """
        env = os.environ.get("COMFYMODAL_V2_ENVIRONMENT", "")
        if env:
            return env.strip()
        return ""

    @staticmethod
    def _gpu_cache_key(gpu: Any) -> tuple[str, ...]:
        """Return an ordered immutable tuple of normalized GPU names for
        cache-key identity.  Preserves caller order (not sorted).
        List/tuple entries are lowered and stripped; None/empty falls back
        to env var then default.  A scalar string becomes a single-element tuple."""
        if isinstance(gpu, (list, tuple)):
            _parts = tuple(str(g).strip().lower() for g in gpu if g)
            if _parts:
                return _parts
        _fallback = str(gpu or os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")).strip().lower()
        return (_fallback,)

    @staticmethod
    def _canonicalize_gpu_config(gpu: Any) -> str:
        """Canonicalize GPU configuration to a sorted immutable string for
        SDK/metadata arguments (cache identity uses _gpu_cache_key tuple).
        List/tuple GPUs are sorted and joined with '+'.
        Empty list/tuple or None falls back to env var then default.
        Single strings are stripped, lowered, and returned as-is."""
        if isinstance(gpu, (list, tuple)):
            _canonical = "+".join(sorted(str(g).strip().lower() for g in gpu if g))
            if _canonical:
                return _canonical
        return str(gpu or os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")).strip().lower()

    def _v2_handle(
        self,
        *,
        workspace: dict[str, Any] | None,
        gpu: Any = None,
        runtime_trace: RuntimeTrace | None = None,
    ) -> Any:
        selected_gpu_str = self._canonicalize_gpu_config(gpu)
        app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
        class_name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
        workspace_id = str((workspace or {}).get("id", "default"))
        environment = self._resolve_environment()
        cloud = self._resolve_v2_cloud(gpu)
        key = HandleCacheKey(
            workspace_id,
            app_name,
            class_name,
            environment=environment,
            cloud=cloud,
            gpu=selected_gpu_str,
            factory_identity=self.v2_handle_factory,
        )
        cached = self.handle_cache.get(key)
        if cached is not None:
            if runtime_trace is not None:
                runtime_trace.emit("handle_cache_hit", phase="local", metadata={
                    "app_name": app_name, "class_name": class_name,
                    "gpu": selected_gpu_str,
                })
                runtime_trace.set_metadata(
                    handle_lookup_app_name=app_name,
                    handle_lookup_class_name=class_name,
                    handle_lookup_gpu=selected_gpu_str,
                )
            return cached
        if runtime_trace is not None:
            runtime_trace.emit("handle_cache_miss", phase="local", metadata={
                "app_name": app_name, "class_name": class_name,
                "gpu": selected_gpu_str,
            })
        if self.v2_handle_factory is not None:
            if runtime_trace is not None:
                runtime_trace.emit("handle_factory_resolve", phase="local")
            handle = self.v2_handle_factory(
                workspace=workspace,
                app_name=app_name,
                class_name=class_name,
                gpu=selected_gpu_str,
            )
            if runtime_trace is not None:
                runtime_trace.set_metadata(
                    handle_lookup_app_name=app_name,
                    handle_lookup_class_name=class_name,
                    handle_lookup_gpu=selected_gpu_str,
                )
            return self.handle_cache.put(key, handle)
        if _modal is None:
            raise TransportError("Modal SDK is unavailable for the v2 transport")
        if not workspace or not workspace.get("token_id") or not workspace.get("token_secret"):
            raise TransportError("v2 transport requires an active Modal workspace with credentials")
        _handle_identity = {"app_name": app_name, "class_name": class_name, "gpu": selected_gpu_str}
        try:
            if runtime_trace is not None:
                runtime_trace.emit("client_resolution_start", phase="local", metadata=_handle_identity)
            client = _modal.Client.from_credentials(
                workspace["token_id"], workspace["token_secret"],
            )
            if runtime_trace is not None:
                runtime_trace.emit("client_resolution_end", phase="local")
                runtime_trace.emit("class_lookup_start", phase="local", metadata=_handle_identity)
            print(
                f"[v2.modal_target] app={app_name} class={class_name} "
                f"environment={environment or '(default)'} "
                f"cloud_override=absent with_options_used=0"
            )
            cls_handle = _modal.Cls.from_name(
                app_name, class_name, client=client,
                environment_name=environment or None,
            )
            if runtime_trace is not None:
                runtime_trace.emit("class_lookup_end", phase="local")
            if runtime_trace is not None:
                runtime_trace.emit("instance_construction_start", phase="local")
            handle = cls_handle()
            if runtime_trace is not None:
                runtime_trace.emit("instance_construction_end", phase="local")
                runtime_trace.set_metadata(
                    handle_lookup_app_name=app_name,
                    handle_lookup_class_name=class_name,
                    handle_lookup_gpu=selected_gpu_str,
                )
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
        plan_dict: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        fn = self.prompt_stream_fn
        request_id = str((trace or {}).get("prompt_id", ""))
        _origin_from_meta: dict[str, Any] = {}
        _modal_input_id = ""
        _modal_input_created_at: Any = None
        _modal_input_id_emitted = False
        _generator_start_wall_ns = None
        _generator_start_mono_ns = None
        _generator_end_wall_ns = None
        _generator_end_mono_ns = None
        _submission_boundary_source = None
        try:
            if fn is not None:
                # V1-compatible stream path — measure plan serialization
                if runtime_trace is not None:
                    runtime_trace.emit("plan_serialize_for_transport_start", phase="local")
                if plan_dict is not None:
                    plan_dict_workflow = plan_dict["workflow"]
                    plan_dict_images = plan_dict["input_images"]
                    plan_dict_report = plan_dict["production_report"]
                else:
                    plan_dict = plan.to_dict()
                    plan_dict_workflow = plan_dict["workflow"]
                    plan_dict_images = plan_dict["input_images"]
                    plan_dict_report = plan_dict["production_report"]
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
                # ── V2 transport entry boundary ──
                if runtime_trace is not None:
                    runtime_trace.emit("transport_entry", phase="local")
                    # pre-handle residual brackets the transport_entry→modal_handle_lookup_start gap
                    runtime_trace.emit("pre_handle_residual_start", phase="local")
                    runtime_trace.emit("pre_handle_residual_end", phase="local")
                    runtime_trace.emit("modal_handle_lookup_start", phase="local")
                handle = self._v2_handle(
                    workspace=workspace, gpu=gpu, runtime_trace=runtime_trace,
                )
                if runtime_trace is not None:
                    runtime_trace.emit("modal_handle_lookup_end", phase="local")
                    gpu_str = self._canonicalize_gpu_config(gpu)
                    # handle_lookup_app_name set inside _v2_handle (actual app_name)
                    runtime_trace.set_metadata(
                        handle_lookup_class_name=type(handle).__name__,
                        handle_lookup_gpu=gpu_str,
                    )
                    runtime_trace.emit("modal_payload_serialize_start", phase="local")
                plan_dict = plan_dict if plan_dict is not None else plan.to_dict()
                if isinstance(trace, dict):
                    _trace_meta = trace.get("metadata", {}) or {}
                    if isinstance(_trace_meta, dict):
                        _origin_from_meta = dict(_trace_meta.get("request_origin_info", {}))
                request_id = str(_origin_from_meta.get("request_id") or request_id)
                if _origin_from_meta:
                    plan_dict["__request_origin_info__"] = _origin_from_meta
                if runtime_trace is not None:
                    runtime_trace.emit("payload_measure_size_start", phase="local")
                _payload_size_start_ns = time.monotonic_ns()
                _payload_bytes = len(json.dumps(plan_dict, separators=(",", ":"), default=str).encode("utf-8"))
                _payload_size_end_ns = time.monotonic_ns()
                _payload_size_measurement_ms = round((_payload_size_end_ns - _payload_size_start_ns) / 1_000_000, 3)
                if runtime_trace is not None:
                    runtime_trace.emit("payload_measure_size_end", phase="local")
                _workflow_dict = plan_dict.get("workflow", {})
                _image_dict = plan_dict.get("input_images", {})
                _node_count = sum(
                    1 for v in _workflow_dict.values()
                    if isinstance(v, dict) and isinstance(v.get("class_type"), str)
                )
                _image_count = len(_image_dict)
                if runtime_trace is not None:
                    runtime_trace.emit("modal_payload_serialize_end", phase="local", metadata={
                        "plan_dict_bytes": _payload_bytes,
                        "workflow_hash": plan.workflow_hash,
                    })
                    runtime_trace.set_metadata(
                        modal_payload_serialize_bytes=_payload_bytes,
                        workflow_hash=plan.workflow_hash,
                        payload_bytes=_payload_bytes,
                        workflow_node_count=_node_count,
                        input_image_count=_image_count,
                        payload_size_measurement_ms=_payload_size_measurement_ms,
                    )
                _generator_start_wall_ns = time.time_ns()
                _generator_start_mono_ns = time.monotonic_ns()
                # Inject generator-create-start into origin dict BEFORE the
                # remote_gen.aio call so the remote can read it.  The
                # plan_dict reference is shared mutable, so modifying
                # _origin_from_meta here updates plan_dict.__request_origin_info__.
                if isinstance(_origin_from_meta, dict):
                    _origin_from_meta.setdefault("modal_generator_create_start_wall_ns", _generator_start_wall_ns)
                    _origin_from_meta.setdefault("modal_generator_create_start_mono_ns", _generator_start_mono_ns)
                if runtime_trace is not None:
                    runtime_trace.emit("modal_generator_create_start", phase="local", metadata={
                        "wall_ns": _generator_start_wall_ns,
                        "mono_ns": _generator_start_mono_ns,
                        "request_id": request_id,
                        "payload_bytes": _payload_bytes,
                    })
                # ── Pre-dispatch local submission breakdown ──────────
                # Emit before the actual Modal invocation so the line is
                # observable before the remote call completes.  Forward
                # the breakdown dict to the remote via plan_dict.
                if runtime_trace is not None:
                    _pre_breakdown = _build_local_submission_breakdown(
                        runtime_trace,
                        origin=_origin_from_meta,
                        transport_meta=runtime_trace._metadata,
                        plan_to_dict_count=1,
                    )
                    _emit_breakdown_line("[v2.local_submission_breakdown.pre_dispatch]", _pre_breakdown)
                    # Inject breakdown into plan_dict for remote re-emission.
                    # Ensure the parent origin dict is in plan_dict even when
                    # no prior origin data existed.
                    if isinstance(_origin_from_meta, dict):
                        _origin_from_meta["local_submission_breakdown"] = dict(_pre_breakdown)
                        if "__request_origin_info__" not in plan_dict:
                            plan_dict["__request_origin_info__"] = _origin_from_meta
                try:
                    stream = handle.run_plan_stream.remote_gen.aio(
                        plan_dict, request_id=request_id,
                    )
                except Exception:
                    if runtime_trace is not None:
                        runtime_trace.set_metadata(
                            modal_generator_create_start_wall_ns=_generator_start_wall_ns,
                            modal_generator_create_start_mono_ns=_generator_start_mono_ns,
                        )
                    raise
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
                    # Pre-populate generator-created wall/mono into the
                    # plan_dict origin dict BEFORE the first __anext__ so
                    # the lazy remote_gen payload serialises them.
                    if isinstance(_origin_from_meta, dict):
                        _origin_from_meta.setdefault("modal_generator_created_wall_ns", _generator_end_wall_ns)
                        _origin_from_meta.setdefault("modal_generator_created_mono_ns", _generator_end_mono_ns)
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
                        "modal_first_iteration_start",
                        wall_unix_ns=_submission_wall_ns,
                        monotonic_ns=_submission_mono_ns,
                        phase="local",
                        metadata={
                            "request_id": request_id if fn is None else "",
                        },
                    )
                    runtime_trace.emit_at(
                        "modal_submission_attempt",
                        wall_unix_ns=_submission_wall_ns,
                        monotonic_ns=_submission_mono_ns,
                        phase="local",
                        metadata={
                            "request_id": request_id if fn is None else "",
                        },
                    )
                _submission_boundary_source = "first_iteration_proxy"
                # Pre-populate first-iteration/submission fields into plan_dict
                # origin before the first __anext__ (lazy submission trigger).
                if isinstance(_origin_from_meta, dict):
                    _origin_from_meta.setdefault("modal_first_iteration_start_wall_ns", _submission_wall_ns)
                    _origin_from_meta.setdefault("modal_first_iteration_start_mono_ns", _submission_mono_ns)
                    _origin_from_meta.setdefault("modal_submission_attempt_wall_ns", _submission_wall_ns)
                    _origin_from_meta.setdefault("modal_submission_attempt_mono_ns", _submission_mono_ns)
                    _origin_from_meta.setdefault("modal_submission_boundary_source", _submission_boundary_source)
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
                    runtime_trace.emit("modal_first_remote_event", phase="local", metadata={
                        "event_type": first_event.get("type", "") if isinstance(first_event, dict) else "",
                        "modal_input_id": _modal_input_id if fn is None else "",
                        "wall_ns": _first_event_wall_ns,
                        "mono_ns": _first_event_mono_ns,
                    })
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
                        # Backfill all post-call timing fields into
                        # _origin_from_meta so local consumers (execute_plan)
                        # can read them from either trace metadata or origin.
                        if isinstance(_origin_from_meta, dict):
                            _origin_from_meta.setdefault("modal_generator_created_wall_ns", _generator_end_wall_ns)
                            _origin_from_meta.setdefault("modal_generator_created_mono_ns", _generator_end_mono_ns)
                            _origin_from_meta.setdefault("modal_first_iteration_start_wall_ns", _submission_wall_ns)
                            _origin_from_meta.setdefault("modal_first_iteration_start_mono_ns", _submission_mono_ns)
                            _origin_from_meta.setdefault("modal_submission_attempt_wall_ns", _submission_wall_ns)
                            _origin_from_meta.setdefault("modal_submission_attempt_mono_ns", _submission_mono_ns)
                            _origin_from_meta.setdefault("modal_first_remote_event_wall_ns", _first_event_wall_ns)
                            _origin_from_meta.setdefault("modal_first_remote_event_mono_ns", _first_event_mono_ns)
                            _origin_from_meta.setdefault("modal_submission_boundary_source", _submission_boundary_source)
                        runtime_trace.set_metadata(
                            modal_generator_create_start_wall_ns=_generator_start_wall_ns,
                            modal_generator_create_start_mono_ns=_generator_start_mono_ns,
                            modal_generator_created_wall_ns=_generator_end_wall_ns,
                            modal_generator_created_mono_ns=_generator_end_mono_ns,
                            modal_first_iteration_start_wall_ns=_submission_wall_ns,
                            modal_first_iteration_start_mono_ns=_submission_mono_ns,
                            modal_submission_attempt_wall_ns=_submission_wall_ns,
                            modal_submission_attempt_mono_ns=_submission_mono_ns,
                            modal_first_remote_event_wall_ns=_first_event_wall_ns,
                            modal_first_remote_event_mono_ns=_first_event_mono_ns,
                            modal_first_event_received_wall_ns=_first_event_wall_ns,
                            modal_first_event_received_mono_ns=_first_event_mono_ns,
                            modal_submission_boundary_source=_submission_boundary_source,
                            modal_input_id=_modal_input_id,
                            modal_input_created_at=_modal_input_created_at,
                            local_receive_to_generator_create_ms=(round((_generator_start_mono_ns - _t1_mono) / 1_000_000, 3) if isinstance(_t1_mono, int) else None),
                            generator_create_ms=round((_generator_end_mono_ns - _generator_start_mono_ns) / 1_000_000, 3),
                            generator_create_to_first_iteration_ms=round((_submission_mono_ns - _generator_end_mono_ns) / 1_000_000, 3),
                            first_iteration_to_first_remote_event_ms=round((_first_event_mono_ns - _submission_mono_ns) / 1_000_000, 3),
                            local_receive_to_actual_submission_ms=(round((_submission_mono_ns - _t1_mono) / 1_000_000, 3) if isinstance(_t1_mono, int) else None),
                        )
                if runtime_trace is not None:
                    _final_breakdown = _build_local_submission_breakdown(
                        runtime_trace,
                        origin=_origin_from_meta,
                        transport_meta=runtime_trace._metadata,
                        plan_to_dict_count=1,
                    )
                    runtime_trace.set_metadata(
                        local_submission_breakdown=dict(_final_breakdown),
                        local_submission_breakdown_status="complete",
                    )
                    _emit_breakdown_line(
                        "[v2.local_submission_breakdown]",
                        _final_breakdown,
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
        key = HandleCacheKey(workspace_id, app_name, "publish_restore_plan_remote", environment=environment)
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
