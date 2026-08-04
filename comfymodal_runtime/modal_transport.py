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
from .local_handle_client import (
    PersistentHandleError,
    PersistentHandleUnavailable,
    build_handle_key,
    get_default_handle_client,
    is_stale_handle_error,
)
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


async def _aclose_iterator(iterator: Any) -> None:
    """Best-effort explicit close of an inner remote async iterator/generator.

    Modal's ``remote_gen.aio()`` returns a real async generator.  If one is
    abandoned (never exhausted, or abandoned on exception/cancellation), its
    eventual garbage-collection schedules a pending ``async_generator_athrow``
    task that can outlive the request and be reported as a leaked task after
    the benchmark process completes.  Closing it here — after the final event
    has been yielded, or on exception/cancellation — runs the SDK-owned
    cleanup deterministically inside the request scope.

    This is intentionally best-effort and never delays the yielded result:
    it runs in ``finally`` only after the last yield, cleanup errors are
    swallowed so they never mask the result or the original transport error,
    and objects without an ``aclose`` (e.g. test fakes) are skipped untouched.
    """
    close = getattr(iterator, "aclose", None)
    if close is None:
        return
    try:
        await close()
    except Exception:
        # Cleanup is best-effort: never let it mask the result/exception.
        pass


@dataclass(frozen=True)
class HandleCacheKey:
    """Cache key for Modal function/cls handles.

    Equality is value-based so the same workspace/app/target/deployment/
    environment produces the same dict key across call boundaries.

    *cloud* (optional) isolates caches across different Modal cloud
    placements (e.g. ``"gcp"`` vs ``"aws"``).  *token_id* and
    *deployment_identity* isolate credential and deployment generations.
    *factory_identity* (optional) isolates caches across different
    ``v2_handle_factory`` callables so that distinct factory objects never
    share a cached handle.  *gpu* (optional) isolates caches across different
    GPU configurations so that distinct GPU targets never share a cached
    handle.
    """

    workspace: str
    app_name: str
    target: str
    environment: str = ""
    cloud: str = ""
    gpu: str = ""
    token_id: str = ""
    deployment_identity: str = ""
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

    def invalidate(self, key: HandleCacheKey) -> None:
        with self._lock:
            self._values.pop(key, None)

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
        v2_handle_factory: Callable[..., Any] | None = None,
        handle_cache: HandleCache | None = None,
        persistent_handle_client: Any | None = None,
    ) -> None:
        self.prompt_stream_fn = prompt_stream_fn
        self.checkpoint_stream_fn = checkpoint_stream_fn
        self.v2_handle_factory = v2_handle_factory
        self.handle_cache = handle_cache or _SHARED_HANDLE_CACHE
        self.persistent_handle_client = persistent_handle_client

    @staticmethod
    def _persistent_enabled() -> bool:
        return os.environ.get("COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE", "").strip().lower() in {
            "1", "true", "yes", "on",
        }

    @staticmethod
    def _deployment_identity(
        payload: Mapping[str, Any] | None = None,
        snapshot_seed: Mapping[str, Any] | None = None,
    ) -> str:
        metadata = payload.get("request_metadata", {}) if isinstance(payload, Mapping) else {}
        identity = metadata.get("deployment_combined_hash", "") if isinstance(metadata, Mapping) else ""
        if not identity and isinstance(snapshot_seed, Mapping):
            seed = snapshot_seed.get("seed", {})
            if isinstance(seed, Mapping):
                identity = seed.get("deployment_combined_hash", "")
        return str(identity or os.environ.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", ""))

    def _cache_key(
        self,
        *,
        workspace: dict[str, Any] | None,
        app_name: str,
        class_name: str,
        environment: str,
        cloud: str,
        gpu: str,
        deployment_identity: str,
    ) -> HandleCacheKey:
        return HandleCacheKey(
            str((workspace or {}).get("id", "default")),
            app_name,
            class_name,
            environment=environment,
            cloud=cloud,
            gpu=gpu,
            token_id=str((workspace or {}).get("token_id", "")),
            deployment_identity=deployment_identity,
            factory_identity=self.v2_handle_factory,
        )

    def _persistent_key(
        self,
        *,
        workspace: dict[str, Any] | None,
        app_name: str,
        class_name: str,
        environment: str,
        cloud: str,
        gpu: str,
        deployment_identity: str,
    ) -> dict[str, str]:
        return build_handle_key(
            workspace_identity=str((workspace or {}).get("id", "default")),
            token_id=str((workspace or {}).get("token_id", "")),
            app_name=app_name,
            class_name=class_name,
            deployment_identity=deployment_identity,
            environment=environment,
            cloud=cloud,
            gpu=gpu,
        )

    def _persistent_client(self) -> Any:
        return self.persistent_handle_client or get_default_handle_client()

    @staticmethod
    def _fallback_direct(reason: Any) -> None:
        print(
            f"[v2.local_handle] decision=fallback_direct reason={type(reason).__name__}",
            flush=True,
        )

    @staticmethod
    def _persistent_failure_is_local(exc: BaseException) -> bool:
        if isinstance(exc, PersistentHandleUnavailable):
            return True
        if not isinstance(exc, PersistentHandleError):
            return False
        return str(exc.frame.get("type", "")) in {
            "", "proxy_read_failed", "proxy_internal", "resolve_failed",
            "auth_failed", "unknown_op",
        }

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
        deployment_identity: str = "",
        runtime_trace: RuntimeTrace | None = None,
    ) -> Any:
        selected_gpu_str = self._canonicalize_gpu_config(gpu)
        app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
        class_name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
        environment = self._resolve_environment()
        cloud = self._resolve_v2_cloud(gpu)
        key = self._cache_key(
            workspace=workspace,
            app_name=app_name,
            class_name=class_name,
            environment=environment,
            cloud=cloud,
            gpu=selected_gpu_str,
            deployment_identity=deployment_identity,
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
        _iterator: Any = None
        _using_persistent_handle = False
        _persistent_mode = False
        _persistent_client: Any = None
        _direct_retry_done = False
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
                _deployment_identity = self._deployment_identity(plan.request_metadata)
                _app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
                _class_name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
                _gpu_str = self._canonicalize_gpu_config(gpu)
                _persistent_mode = self._persistent_enabled() and self.v2_handle_factory is None
                handle = None
                if not _persistent_mode:
                    handle = self._v2_handle(
                        workspace=workspace,
                        gpu=gpu,
                        deployment_identity=_deployment_identity,
                        runtime_trace=runtime_trace,
                    )
                if runtime_trace is not None:
                    if not _persistent_mode:
                        runtime_trace.emit("modal_handle_lookup_end", phase="local")
                    # Direct lookup sets the actual app name; the persistent
                    # owner uses the same environment-selected target.
                    runtime_trace.set_metadata(
                        handle_lookup_app_name=_app_name,
                        handle_lookup_class_name=(_class_name if _persistent_mode else type(handle).__name__),
                        handle_lookup_gpu=_gpu_str,
                        local_handle_mode=("persistent_ipc" if _persistent_mode else "direct"),
                    )
                    runtime_trace.emit("modal_payload_serialize_start", phase="local")
                plan_dict = plan_dict if plan_dict is not None else plan.to_dict()
                if isinstance(trace, dict):
                    _trace_meta = trace.get("metadata", {}) or {}
                    if isinstance(_trace_meta, dict):
                        _origin_from_meta = dict(_trace_meta.get("request_origin_info", {}))
                request_id = str(_origin_from_meta.get("request_id") or request_id)
                # Propagate the submitting process's V2 env profile into the
                # remote request payload (read from os.environ — never
                # hardcoded).  The remote applies it when the container still
                # runs the deploy default so production/diagnostic semantics
                # match the submitting process.
                if isinstance(_origin_from_meta, dict):
                    _local_env_profile = os.environ.get(
                        "COMFYMODAL_V2_ENV_PROFILE", ""
                    ).strip().lower()
                    if _local_env_profile:
                        _origin_from_meta["env_profile"] = _local_env_profile
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
                    if _persistent_mode:
                        _persistent_client = self._persistent_client()
                        _persistent_key = self._persistent_key(
                            workspace=workspace,
                            app_name=_app_name,
                            class_name=_class_name,
                            environment=self._resolve_environment(),
                            cloud=self._resolve_v2_cloud(gpu),
                            gpu=_gpu_str,
                            deployment_identity=_deployment_identity,
                        )
                        stream = await _persistent_client.run_plan_stream(
                            _persistent_key,
                            workspace or {},
                            plan_dict,
                            request_id=request_id,
                            gpu=_gpu_str,
                        )
                        _using_persistent_handle = True
                    else:
                        stream = handle.run_plan_stream.remote_gen.aio(
                            plan_dict, request_id=request_id,
                        )
                except (PersistentHandleUnavailable, PersistentHandleError) as exc:
                    if not _persistent_mode or not self._persistent_failure_is_local(exc):
                        raise
                    self._fallback_direct(exc)
                    _persistent_mode = False
                    _using_persistent_handle = False
                    handle = self._v2_handle(
                        workspace=workspace,
                        gpu=gpu,
                        deployment_identity=_deployment_identity,
                        runtime_trace=runtime_trace,
                    )
                    stream = handle.run_plan_stream.remote_gen.aio(
                        plan_dict, request_id=request_id,
                    )
                    _generator_end_wall_ns = time.time_ns()
                    _generator_end_mono_ns = time.monotonic_ns()
                except Exception as exc:
                    if _persistent_mode:
                        self._fallback_direct(exc)
                        _persistent_mode = False
                        _using_persistent_handle = False
                        handle = self._v2_handle(
                            workspace=workspace,
                            gpu=gpu,
                            deployment_identity=_deployment_identity,
                            runtime_trace=runtime_trace,
                        )
                        stream = handle.run_plan_stream.remote_gen.aio(
                            plan_dict, request_id=request_id,
                        )
                        _generator_end_wall_ns = time.time_ns()
                        _generator_end_mono_ns = time.monotonic_ns()
                    elif not _direct_retry_done and is_stale_handle_error(exc):
                        self.handle_cache.invalidate(self._cache_key(
                            workspace=workspace,
                            app_name=_app_name,
                            class_name=_class_name,
                            environment=self._resolve_environment(),
                            cloud=self._resolve_v2_cloud(gpu),
                            gpu=_gpu_str,
                            deployment_identity=_deployment_identity,
                        ))
                        _direct_retry_done = True
                        handle = self._v2_handle(
                            workspace=workspace,
                            gpu=gpu,
                            deployment_identity=_deployment_identity,
                            runtime_trace=runtime_trace,
                        )
                        stream = handle.run_plan_stream.remote_gen.aio(
                            plan_dict, request_id=request_id,
                        )
                        _generator_end_wall_ns = time.time_ns()
                        _generator_end_mono_ns = time.monotonic_ns()
                    else:
                        if runtime_trace is not None:
                            runtime_trace.set_metadata(
                                modal_generator_create_start_wall_ns=_generator_start_wall_ns,
                                modal_generator_create_start_mono_ns=_generator_start_mono_ns,
                            )
                        raise
                if runtime_trace is not None:
                    runtime_trace.set_metadata(
                        local_handle_mode=("persistent_ipc" if _using_persistent_handle else "direct"),
                    )
                if _using_persistent_handle and runtime_trace is not None:
                    runtime_trace.emit("modal_handle_lookup_end", phase="local")
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
                _iterator = stream.__aiter__()
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
                    first_event = await _iterator.__anext__()
                except StopAsyncIteration:
                    return
                except PersistentHandleError as exc:
                    if not _using_persistent_handle or not self._persistent_failure_is_local(exc):
                        raise
                    await _aclose_iterator(_iterator)
                    _iterator = None
                    self._fallback_direct(exc)
                    _persistent_mode = False
                    _using_persistent_handle = False
                    handle = self._v2_handle(
                        workspace=workspace,
                        gpu=gpu,
                        deployment_identity=_deployment_identity,
                        runtime_trace=runtime_trace,
                    )
                    stream = handle.run_plan_stream.remote_gen.aio(
                        plan_dict, request_id=request_id,
                    )
                    _generator_end_wall_ns = time.time_ns()
                    _generator_end_mono_ns = time.monotonic_ns()
                    _iterator = stream.__aiter__() if hasattr(stream, "__aiter__") else None
                    if _iterator is None:
                        raise TransportError("direct v2 stream fallback is not asynchronous")
                    first_event = await _iterator.__anext__()
                except Exception as exc:
                    if not is_stale_handle_error(exc) or _direct_retry_done:
                        raise
                    await _aclose_iterator(_iterator)
                    _iterator = None
                    self.handle_cache.invalidate(self._cache_key(
                        workspace=workspace,
                        app_name=_app_name,
                        class_name=_class_name,
                        environment=self._resolve_environment(),
                        cloud=self._resolve_v2_cloud(gpu),
                        gpu=_gpu_str,
                        deployment_identity=_deployment_identity,
                    ))
                    _direct_retry_done = True
                    handle = self._v2_handle(
                        workspace=workspace,
                        gpu=gpu,
                        deployment_identity=_deployment_identity,
                        runtime_trace=runtime_trace,
                    )
                    stream = handle.run_plan_stream.remote_gen.aio(
                        plan_dict, request_id=request_id,
                    )
                    _generator_end_wall_ns = time.time_ns()
                    _generator_end_mono_ns = time.monotonic_ns()
                    _iterator = stream.__aiter__() if hasattr(stream, "__aiter__") else None
                    if _iterator is None:
                        raise TransportError("direct v2 stale retry is not asynchronous")
                    first_event = await _iterator.__anext__()
                _first_event_wall_ns = time.time_ns()
                _first_event_mono_ns = time.monotonic_ns()
                if fn is None:
                    _modal_input_id = str(
                        getattr(stream, "input_id", "")
                        or getattr(_iterator, "input_id", "")
                        or _modal_input_id
                    )
                    _modal_input_created_at = (
                        getattr(stream, "input_created_at", None)
                        or getattr(_iterator, "input_created_at", None)
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
                async for event in _iterator:
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
        finally:
            # Close the inner remote generator after the result is fully
            # yielded, on exception, or on cancellation (finally always runs).
            # Best-effort: never delays/changes the yielded result and never
            # masks the original outcome.
            await _aclose_iterator(_iterator)

    async def run_checkpoint_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        fn = self.checkpoint_stream_fn
        if fn is not None:
            stream = fn(*args, **kwargs)
        else:
            _checkpoint_workspace = kwargs.pop("workspace", None)
            _checkpoint_gpu = kwargs.pop("gpu", None)
            handle = self._v2_handle(
                workspace=_checkpoint_workspace,
                gpu=_checkpoint_gpu,
                deployment_identity=self._deployment_identity(kwargs.get("plan_payload")),
            )
            stream = handle.run_checkpoint_stream.remote_gen.aio(*args, **kwargs)
        if hasattr(stream, "__aiter__"):
            ait = stream.__aiter__()
            try:
                async for event in ait:
                    yield event
            finally:
                await _aclose_iterator(ait)
        else:
            result = await stream if inspect.isawaitable(stream) else stream
            if isinstance(result, dict):
                yield {"type": "result", "data": result}

    async def publish_restore_plan(
        self,
        plan_payload: Mapping[str, Any],
        *,
        workspace: dict[str, Any] | None = None,
        snapshot_seed: Mapping[str, Any] | None = None,
        gpu: str | None = None,
        runtime_trace: RuntimeTrace | None = None,
    ) -> dict[str, Any]:
        """Publish a ``RestorePlan`` dict (and optional schema-v2
        ``snapshot_seed`` payload) through the registered v2 Modal method.

        The remote method writes both atomically to the deployment-scoped
        runtime-state volume (and mirrors the seed to ``snapshot_seed.json``
        for restore-time hydration).  Returns the authoritative publication
        result dict.  The seed payload is passed through unchanged — it is
        never rebuilt or re-validated on the remote side.
        """
        _deployment_identity = self._deployment_identity(
            plan_payload, snapshot_seed,
        )
        _app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
        _class_name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
        _gpu_str = self._canonicalize_gpu_config(gpu)
        if runtime_trace is not None:
            runtime_trace.emit(
                "restore_plan_remote_submit",
                phase="local",
                metadata={
                    "plan_payload_bytes": len(
                        json.dumps(
                            dict(plan_payload or {}),
                            separators=(",", ":"), default=str,
                        ).encode("utf-8")
                    ),
                    "snapshot_seed_present": int(snapshot_seed is not None),
                },
            )
        _persistent_mode = self._persistent_enabled() and self.v2_handle_factory is None
        if _persistent_mode:
            _persistent_key = self._persistent_key(
                workspace=workspace,
                app_name=_app_name,
                class_name=_class_name,
                environment=self._resolve_environment(),
                cloud=self._resolve_v2_cloud(gpu),
                gpu=_gpu_str,
                deployment_identity=_deployment_identity,
            )
            try:
                return await self._persistent_client().publish_restore_plan(
                    _persistent_key,
                    workspace or {},
                    plan_payload,
                    snapshot_seed=snapshot_seed,
                    gpu=_gpu_str,
                )
            except (PersistentHandleUnavailable, PersistentHandleError) as exc:
                if not self._persistent_failure_is_local(exc):
                    raise
                self._fallback_direct(exc)

        _direct_retry_done = False
        while True:
            handle = self._v2_handle(
                workspace=workspace,
                gpu=gpu,
                deployment_identity=_deployment_identity,
                runtime_trace=runtime_trace,
            )
            try:
                publish_fn = handle.publish_restore_plan
                remote = getattr(publish_fn, "remote", None)
                if remote is not None and callable(getattr(remote, "aio", None)):
                    result = remote.aio(plan_payload, snapshot_seed=snapshot_seed)
                    if inspect.isawaitable(result):
                        return await result
                    return result
                if inspect.iscoroutinefunction(publish_fn):
                    result = publish_fn(plan_payload, snapshot_seed=snapshot_seed)
                    if inspect.isawaitable(result):
                        return await result
                    return result
                result = await asyncio.to_thread(
                    publish_fn, plan_payload, snapshot_seed=snapshot_seed,
                )
                if inspect.isawaitable(result):
                    return await result
                return result
            except Exception as exc:
                if not is_stale_handle_error(exc) or _direct_retry_done:
                    raise
                self.handle_cache.invalidate(self._cache_key(
                    workspace=workspace,
                    app_name=_app_name,
                    class_name=_class_name,
                    environment=self._resolve_environment(),
                    cloud=self._resolve_v2_cloud(gpu),
                    gpu=_gpu_str,
                    deployment_identity=_deployment_identity,
                ))
                _direct_retry_done = True
                continue
