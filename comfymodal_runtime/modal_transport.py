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
    CANCEL_STATE_UNAVAILABLE,
    CancelResult,
    PersistentHandleError,
    PersistentHandleUnavailable,
    RemoteCancellationHandle,
    build_handle_key,
    get_default_handle_client,
    is_stale_handle_error,
)
from .trace import (
    _build_local_submission_breakdown,
    _emit_breakdown_line,
)
from .v2_waterfall import attach_waterfall, graph_result_from_event, is_graph_result

if TYPE_CHECKING:
    from .trace import RuntimeTrace

try:
    import modal as _modal
except Exception:
    _modal = None


class TransportError(RuntimeError):
    pass


# Modal named-Queue partition keys must be non-empty and at most 64 bytes
# (the SDK rejects anything else server-side).  Shared by the transport
# putters and the persistent owner so a bad partition is never delivered.
CONTROL_PARTITION_MAX_BYTES = 64


def validate_control_partition(partition: Any) -> str:
    """Normalize and validate a Modal control-Queue partition key.

    Returns the normalized string, or raises ``ValueError`` when the key is
    empty or exceeds Modal's 64-byte limit.  Callers surface the failure as
    a truthful cancellation-channel error (``unavailable`` verdict) instead
    of delivering to a silently-wrong partition or spinning forever.
    """
    text = str(partition if partition is not None else "")
    if not text:
        raise ValueError("control partition must be non-empty")
    byte_len = len(text.encode("utf-8"))
    if byte_len > CONTROL_PARTITION_MAX_BYTES:
        raise ValueError(
            "control partition exceeds Modal's 64-byte limit "
            f"({byte_len} bytes)"
        )
    return text


# Variant A persistence registry: definitive remote persistence outcome per
# prompt, recorded by the shielded background drain after the caller has
# already broken out of the stream on the result event.
_PERSISTENCE_STATUS_BY_PROMPT: dict[str, dict] = {}


class _PersistenceDrainHandle:
    """Bounded-join handle for one spawned persistence drain task.

    ``shield_task`` is the task callers normally observe (survives request
    cancellation because it shields ``inner_task``); ``inner_task`` is the
    actual drain that teardown may cancel directly.
    """

    __slots__ = ("request_id", "inner_task", "shield_task")

    def __init__(
        self,
        request_id: str,
        inner_task: asyncio.Task,
        shield_task: asyncio.Task,
    ) -> None:
        self.request_id = request_id
        self.inner_task = inner_task
        self.shield_task = shield_task


# Explicit registry of every spawned persistence drain, keyed by request_id.
# Populated by _spawn_persistence_drain, cleared by the shield task's done
# callback, and joined/cancelled by the teardown seams below so no drain task
# is ever left pending at event-loop shutdown.
_PERSISTENCE_DRAIN_HANDLES: dict[str, _PersistenceDrainHandle] = {}


def get_persistence_status(prompt_id: str) -> dict | None:
    """Return a copy of the recorded persistence outcome for *prompt_id*.

    Returns ``None`` when no record exists (e.g. the stream ran to natural
    completion without a deferred commit, or no drain observed the remote's
    terminal ``persistence`` event).
    """
    record = _PERSISTENCE_STATUS_BY_PROMPT.get(str(prompt_id))
    if record is None:
        return None
    return dict(record)


def record_persistence_status(request_id: str, event: Mapping[str, Any]) -> dict | None:
    """Record a remote ``persistence`` event for *request_id*.

    Shared recorder for consumers that observe the terminal persistence
    event outside the shielded drain (e.g. the legacy
    ``modal_client.run_prompt_stream`` path, which consumes the stream to
    natural completion).  Normalizes the event exactly like the drain and
    returns the stored record (or None when the event has no status).
    """
    if not isinstance(event, dict) or event.get("type") != "persistence":
        return None
    status = str(event.get("status", ""))
    if not status:
        return None
    record = {
        "status": status,
        "commit_ms": float(event.get("commit_ms", 0.0) or 0.0),
        "detail": str(event.get("detail", "")),
        "skipped": bool(event.get("skipped", False)),
    }
    _PERSISTENCE_STATUS_BY_PROMPT[str(request_id)] = record
    return record


async def _aclose_iterator(iterator: Any) -> None:
    """Best-effort explicit close of an inner remote async iterator/generator.

    Modal's ``remote_gen.aio()`` returns a real async generator.  If one is
    abandoned (never exhausted, or abandoned on exception/cancellation), its
    eventual garbage-collection schedules a pending ``async_generator_athrow``
    task that can outlive the request and be reported as a leaked task after
    the benchmark process completes.  Closing it here â€” after the final event
    has been yielded, or on exception/cancellation â€” runs the SDK-owned
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


def _spawn_persistence_drain(
    iterator: Any,
    *,
    request_id: str,
    runtime_trace: Any | None,
) -> asyncio.Task:
    """Spawn a shielded background task that drains *iterator* to natural
    completion, recording the remote's final persistence event.

    The drain is tracked in the module registry (``_PERSISTENCE_DRAIN_HANDLES``)
    keyed by *request_id* so a teardown seam can join it with a bounded timeout
    â€” or cancel it cleanly â€” before the event loop shuts down.  It is never a
    fire-and-forget task: result delivery is unaffected, but the trailing
    persistence event is deterministically collected by the join seam.

    The returned task is a shielded wrapper: request cancellation does not kill
    the inner drain (matching the previous semantics), while teardown cancels
    the inner task directly.
    """
    loop = asyncio.get_running_loop()
    request_id = str(request_id)

    inner = loop.create_task(
        _drain_persistence_iterator(
            iterator,
            request_id=request_id,
            runtime_trace=runtime_trace,
        )
    )

    async def _shielded_drain() -> None:
        # asyncio.shield() returns a Future on Python 3.11+, so it cannot be
        # passed directly to create_task; awaiting it inside a coroutine keeps
        # the drain shielded from cancellation while remaining a coroutine.
        await asyncio.shield(inner)

    shield_task = loop.create_task(_shielded_drain())
    _PERSISTENCE_DRAIN_HANDLES[request_id] = _PersistenceDrainHandle(
        request_id, inner, shield_task
    )
    shield_task.add_done_callback(
        lambda _t: _PERSISTENCE_DRAIN_HANDLES.pop(request_id, None)
    )
    return shield_task


async def _cancel_persistence_drain(handle: _PersistenceDrainHandle) -> None:
    """Cancel one drain and await its cancellation cleanly.

    Never leaves the drain pending: the inner task is cancelled and awaited to
    completion (cancelled state is fine â€” it is no longer pending), and the
    shield wrapper resolves once the inner settles.
    """
    if handle.inner_task.done() and handle.shield_task.done():
        return
    handle.inner_task.cancel()
    try:
        await handle.inner_task
    except (asyncio.CancelledError, Exception):
        pass
    try:
        await handle.shield_task
    except (asyncio.CancelledError, Exception):
        pass


async def join_persistence_drain(
    request_id: str,
    timeout: float = 15.0,
) -> dict | None:
    """Join the persistence drain for *request_id* within a bounded *timeout*.

    Awaits the drain to natural completion so the remote trailing persistence
    event is deterministically recorded.  On timeout the drain is cancelled and
    its cancellation awaited cleanly â€” no pending task can survive loop
    shutdown.  Returns the recorded persistence record (or ``None`` when the
    stream completed naturally with no deferred commit).
    """
    request_id = str(request_id)
    handle = _PERSISTENCE_DRAIN_HANDLES.get(request_id)
    if handle is None or handle.shield_task.done():
        return get_persistence_status(request_id)
    try:
        await asyncio.wait_for(asyncio.shield(handle.shield_task), timeout=timeout)
    except asyncio.TimeoutError:
        await _cancel_persistence_drain(handle)
    return get_persistence_status(request_id)


async def join_all_persistence_drains(
    timeout: float = 15.0,
) -> list[dict]:
    """Join every registered persistence drain with a bounded per-drain budget.

    Process/loop teardown seam: guarantees no pending drain task survives loop
    shutdown (no ``Task was destroyed but it is pending`` warnings).  Returns
    the recorded persistence records.
    """
    records: list[dict] = []
    for request_id in list(_PERSISTENCE_DRAIN_HANDLES.keys()):
        record = await join_persistence_drain(request_id, timeout=timeout)
        if record is not None:
            records.append(dict(record))
    return records


async def _drain_persistence_iterator(
    iterator: Any,
    *,
    request_id: str,
    runtime_trace: Any | None,
) -> None:
    """Consume *iterator* to completion; record persistence outcome.

    Never raises.  If the remote yields a ``persistence`` event, record
    its status into the module registry keyed by *request_id* and emit a
    local trace marker.  Always best-effort acloses the iterator at the
    end.
    """
    try:
        async for event in iterator:
            if isinstance(event, dict) and event.get("type") == "persistence":
                record = {
                    "status": str(event.get("status", "")),
                    "commit_ms": float(event.get("commit_ms", 0.0) or 0.0),
                    "detail": str(event.get("detail", "")),
                    "skipped": bool(event.get("skipped", False)),
                }
                _PERSISTENCE_STATUS_BY_PROMPT[str(request_id)] = record
                if runtime_trace is not None:
                    runtime_trace.emit(
                        "deferred_commit_end",
                        phase="local",
                        metadata=dict(record),
                    )
    except Exception:
        # Drain is best-effort observability; never let it propagate.
        pass
    finally:
        # Shield the close so teardown cancellation never skips it: closing the
        # remote iterator deterministically runs SDK-owned cleanup instead of
        # leaving a leaked generator.
        try:
            await asyncio.shield(_aclose_iterator(iterator))
        except (asyncio.CancelledError, Exception):
            pass


def _event_data_input_id(event: Any) -> tuple[str, Any]:
    """Read input-id provenance learned from *yielded event metadata*.

    Modal SDK 1.4.3 does NOT expose ``input_id``/``input_created_at`` on the
    generator object; the only legitimate source is the remote result/status
    event payload.  Returns ``(input_id, input_created_at)`` â€” both empty/
    None when the event carries no identity.
    """
    if not isinstance(event, dict):
        return "", None
    data = event.get("data")
    if not isinstance(data, dict):
        return "", None
    input_id = str(data.get("modal_input_id") or data.get("input_id") or "")
    input_created_at = data.get("modal_input_created_at") or data.get("input_created_at")
    return input_id, input_created_at


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
        control_queue_factory: Callable[..., Any] | None = None,
        workspace: dict[str, Any] | None = None,
    ) -> None:
        self.prompt_stream_fn = prompt_stream_fn
        self.checkpoint_stream_fn = checkpoint_stream_fn
        self.v2_handle_factory = v2_handle_factory
        self.handle_cache = handle_cache or _SHARED_HANDLE_CACHE
        self.persistent_handle_client = persistent_handle_client
        self.workspace = dict(workspace or {})
        # Injected resolver for the cooperative-cancel control Queue (tests /
        # non-Modal environments).  Default: resolve through ``_modal`` with
        # the workspace credentials, lazily and cached.
        self.control_queue_factory = control_queue_factory
        # Request IDs this transport spawned persistence drains for (module
        # registry is keyed by request_id; this tracks the transport-owned set).
        self._drain_request_ids: set[str] = set()
        # Transport-owned cooperative cancellation handles, keyed by request/
        # attempt id.  Registered at stream setup; confirmed only by the remote
        # ``cancelled`` event; released via ``release_cancellation_handle`` /
        # ``close_cancellation_handles``.
        self._cancellation_handles: dict[str, RemoteCancellationHandle] = {}
        # Lazily-resolved control Queue handles, keyed by
        # (workspace id, token id, environment).
        self._control_queue_cache: dict[tuple[str, ...], Any] = {}
        self._control_queue_lock = threading.Lock()

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
        """Whether a persistent-IPC failure is safe to fall back to a direct
        Modal call â€” i.e. the remote method can be guaranteed NOT to have
        executed yet.

        Pre-op failures (owner unreachable, handle resolution/auth failures,
        proxy-internal errors before delivery, stream proxy read errors) fall
        back: no remote side effect happened, so one direct call is exactly
        one remote invocation.

        Post-op failures (``result_unavailable``: result-read timeout, EOF,
        or read failure AFTER the publish op was delivered) do NOT fall back:
        the remote publish may have already executed, and a direct retry
        would trigger ``publish_restore_plan`` a second time.
        """
        if isinstance(exc, PersistentHandleUnavailable):
            return True
        if not isinstance(exc, PersistentHandleError):
            return False
        return str(exc.frame.get("type", "")) in {
            "proxy_read_failed", "proxy_internal", "resolve_failed",
            "auth_failed", "unknown_op",
        }

    @staticmethod
    def _resolve_v2_cloud(gpu: str) -> str:
        """Resolve the Modal cloud placement for a v2 GPU class lookup.

        Returns the cloud name (e.g. ``"gcp"``) or ``""`` for global scheduling.
        Only an explicit ``COMFYMODAL_V2_CLOUD`` environment value is returned;
        no implicit GPUâ†’cloud pinning is applied.  Callers that require matched
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

    # â”€â”€ Cooperative cancellation channel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def _control_queue_name() -> str:
        """Name of the named Modal Queue used for cooperative cancellation."""
        return os.environ.get("COMFYMODAL_V2_CONTROL_QUEUE", "comfymodal-v2-control").strip() or "comfymodal-v2-control"

    async def _resolve_control_queue(self, *, workspace: dict[str, Any] | None) -> Any:
        """Lazily resolve (and cache) the named Modal control Queue for the
        workspace's credentials, FORCING hydration so the handle can be passed
        as a remote-generator argument.

        ``modal.Queue.from_name(...)`` returns a LAZY handle (modal SDK 1.4.3
        defers hydration to first use); passing an unhydrated handle as a kwarg
        to ``remote_gen.aio(...)`` fails argument serialization with
        ``Can't serialize object ... which hasn't been hydrated``.  Returns
        ``None`` when the channel cannot be resolved or hydrated (no Modal SDK,
        no workspace credentials, or a resolution failure) â€” cancellation is
        then truthfully unavailable and the execution path is unaffected.
        Only successful resolutions are cached; queue creation/put never runs
        on the normal execution hot path beyond this handle plumbing.
        """
        cache_key = (
            "control-queue",
            str((workspace or {}).get("id", "default")),
            str((workspace or {}).get("token_id", "") or ""),
            self._resolve_environment(),
        )
        with self._control_queue_lock:
            cached = self._control_queue_cache.get(cache_key)
        if cached is not None:
            return cached
        queue = None
        if self.control_queue_factory is not None:
            try:
                queue = self.control_queue_factory(workspace=workspace)
            except Exception:
                queue = None
        elif _modal is not None:
            token_id = str((workspace or {}).get("token_id", "") or "")
            token_secret = str((workspace or {}).get("token_secret", "") or "")
            if not token_id or not token_secret:
                return None
            try:
                client = _modal.Client.from_credentials(token_id, token_secret)
                queue = _modal.Queue.from_name(
                    self._control_queue_name(), create_if_missing=True, client=client,
                )
                # Force hydration via the async form: modal 1.4.3's instance
                # ``hydrate`` is a SYNC blocking wrapper (returns the Queue),
                # while ``hydrate.aio`` is the awaitable.  An unhydrated lazy
                # handle cannot be passed as a remote-generator argument.
                await queue.hydrate.aio(client=client)
            except Exception:
                # Cancellation plumbing must never break the execution path.
                queue = None
        if queue is not None:
            with self._control_queue_lock:
                self._control_queue_cache[cache_key] = queue
        return queue

    @staticmethod
    def _make_direct_cancel_putter(queue: Any) -> Callable[[Mapping[str, Any]], Any]:
        """Return an async putter that delivers primitive cancel messages to a
        direct Modal Queue handle (put success is NOT confirmation).

        The control channel is a partitioned Modal named Queue: every put
        declares the routing ``partition`` (taken from the message payload) so
        the message lands in the same partition the remote generator polls
        (``get(partition=control_partition)``) â€” never the default partition.
        """

        async def _put(message: Mapping[str, Any]) -> bool:
            partition = validate_control_partition(message.get("partition"))
            await asyncio.to_thread(queue.put, dict(message), partition=partition)
            return True

        return _put

    def _make_persistent_cancel_putter(
        self,
        *,
        request_id: str,
        persistent_key: Mapping[str, Any] | None,
        workspace: dict[str, Any] | None,
    ) -> Callable[[Mapping[str, Any]], Any]:
        """Return an async putter that sends cancellation through the
        persistent client's dedicated ``cancel_attempt`` op (its own loopback
        connection â€” never the busy stream socket)."""
        queue_name = self._control_queue_name()

        async def _put(message: Mapping[str, Any]) -> bool:
            # The partition is taken from the message payload (matching the
            # direct putter) so a cancel never silently re-targets a fallback
            # partition.  Invalid keys surface as a truthful ValueError.
            partition = validate_control_partition(message.get("partition"))
            client = self._persistent_client()
            outcome = await client.cancel_attempt(
                key=dict(persistent_key or {}),
                workspace=dict(workspace or {}),
                control_queue_name=queue_name,
                control_partition=partition,
                reason=str(message.get("reason", "") or ""),
            )
            return bool((outcome or {}).get("delivered"))

        return _put

    def _register_cancel_handle(self, request_id: str, putter: Any) -> RemoteCancellationHandle:
        """Register (or rebind) the transport-owned cancellation handle for
        *request_id*.  The same handle object survives transport retries so a
        scheduler that fetched it earlier keeps a live reference."""
        request_id = str(request_id)
        handle = self._cancellation_handles.get(request_id)
        if handle is None:
            handle = RemoteCancellationHandle(
                request_id=request_id, partition=request_id, putter=putter,
            )
            self._cancellation_handles[request_id] = handle
        else:
            handle._set_putter(putter)
        return handle

    async def _direct_fallback_channel(self, *, workspace: dict[str, Any] | None, request_id: str) -> dict[str, Any]:
        """After falling back to the direct path, (re)resolve the control
        Queue and (re)register the cancellation handle so cancellation keeps
        working across retries.  Returns the kwargs dict for the direct
        ``remote_gen.aio`` call (``{}`` when the channel is unavailable)."""
        queue = await self._resolve_control_queue(workspace=workspace)
        if queue is None:
            self._register_cancel_handle(request_id, None)
            return {}
        self._register_cancel_handle(request_id, self._make_direct_cancel_putter(queue))
        return {"control_queue": queue, "control_partition": request_id}

    def _observe_cancelled_event(self, event: Any, *, request_id: str) -> bool:
        """True only when *event* is the remote cooperative-cancellation
        confirmation (``{'type': 'cancelled', ..., 'confirmed': True}``).

        Confirms the registered handle â€” the ONLY local state that may become
        ``confirmed``.  Unconfirmed/malformed ``cancelled`` frames return
        ``False``: they are treated as ordinary stream events and must NOT
        skip the persistence drain.  A confirmed event is transport-internal
        protocol and is never surfaced as a normal stream event.
        """
        if not isinstance(event, dict) or event.get("type") != "cancelled":
            return False
        if event.get("confirmed") is not True:
            return False
        handle = self._cancellation_handles.get(str(request_id))
        if handle is not None:
            handle._mark_confirmed(reason=str(event.get("reason", "") or ""))
        return True

    def _observe_completion(self, *, request_id: str) -> None:
        """A normal result event was observed for *request_id* â€” the attempt
        finished, so a later cancel reports ``completed_before_cancel``."""
        handle = self._cancellation_handles.get(str(request_id))
        if handle is not None:
            handle._mark_completed()

    def get_cancellation_handle(self, request_id: str) -> RemoteCancellationHandle | None:
        """Narrow D3-binding seam: the transport-owned cooperative cancellation
        handle for a request/attempt id, or ``None`` when no stream registered
        one.  ``cancel(reason)`` on the handle is async and returns a
        ``CancelResult``."""
        return self._cancellation_handles.get(str(request_id))

    async def cancel_attempt(self, request_id: str, reason: str = "") -> CancelResult:
        """Request cooperative cancellation of the attempt identified by
        *request_id*.

        Idempotent: a duplicate request reflects the current verdict without
        re-delivering.  Never fabricates confirmation â€” the verdict is
        ``pending`` until the remote ``cancelled`` event is observed
        (``confirmed``), ``completed_before_cancel`` when the attempt already
        finished, or ``unavailable`` on a channel failure.
        """
        handle = self._cancellation_handles.get(str(request_id))
        if handle is None:
            return CancelResult(
                CANCEL_STATE_UNAVAILABLE,
                reason=str(reason or ""),
                detail="no active transport attempt registered for request_id",
            )
        return await handle.cancel(reason)

    def release_cancellation_handle(self, request_id: str) -> None:
        """Drop the handle for *request_id* (explicit D3/teardown cleanup)."""
        self._cancellation_handles.pop(str(request_id), None)

    async def close_cancellation_handles(self) -> list[CancelResult]:
        """Teardown-only seam: snapshot and drop every registered handle."""
        verdicts: list[CancelResult] = []
        for request_id in list(self._cancellation_handles):
            handle = self._cancellation_handles.pop(request_id, None)
            if handle is not None:
                verdicts.append(handle.snapshot())
        return verdicts

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
        _stream_exhausted = False
        _cancelled_event_seen = False
        if workspace is None:
            workspace = self.workspace
        try:
            if fn is not None:
                # V1-compatible stream path â€” measure plan serialization
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
                # â”€â”€ V2 transport entry boundary â”€â”€
                if runtime_trace is not None:
                    runtime_trace.emit("transport_entry", phase="local")
                    # pre-handle residual brackets the transport_entryâ†’modal_handle_lookup_start gap
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
                        runtime_trace.emit("modal_handle_ready", phase="local", metadata={"mode": "direct"})
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
                # remote request payload (read from os.environ â€” never
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
                # â”€â”€ Pre-dispatch local submission breakdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                # â”€â”€ Cooperative cancellation channel plumbing â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # Lazily resolve (and cache) the named control Queue for the
                # workspace and register a transport-owned cancellation handle
                # for this request/attempt.  Resolution is handle plumbing
                # only â€” the first put happens exclusively on an explicit
                # cancel().  If the channel cannot be resolved, cancellation
                # is truthfully unavailable and the execution path is
                # unaffected.  In persistent mode the OWNER resolves the same
                # named Queue from its client cache; the local transport sends
                # cancellation through its own dedicated loopback channel.
                _persistent_key: dict[str, str] | None = None
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
                    self._register_cancel_handle(
                        request_id,
                        self._make_persistent_cancel_putter(
                            request_id=request_id,
                            persistent_key=_persistent_key,
                            workspace=workspace,
                        ),
                    )
                    _control_kwargs: dict[str, Any] = {}
                else:
                    _control_queue = await self._resolve_control_queue(workspace=workspace)
                    if _control_queue is not None:
                        _control_kwargs = {
                            "control_queue": _control_queue,
                            "control_partition": request_id,
                        }
                        self._register_cancel_handle(
                            request_id, self._make_direct_cancel_putter(_control_queue),
                        )
                    else:
                        _control_kwargs = {}
                        self._register_cancel_handle(request_id, None)
                try:
                    if _persistent_mode:
                        _persistent_client = self._persistent_client()
                        if runtime_trace is not None:
                            runtime_trace.emit("modal_handle_ready", phase="local", metadata={"mode": "persistent_ipc"})
                        stream = await _persistent_client.run_plan_stream(
                            _persistent_key,
                            workspace or {},
                            plan_dict,
                            request_id=request_id,
                            gpu=_gpu_str,
                            control_queue_name=self._control_queue_name(),
                            control_partition=request_id,
                        )
                        _using_persistent_handle = True
                    else:
                        stream = handle.run_plan_stream.remote_gen.aio(
                            plan_dict, request_id=request_id, **_control_kwargs,
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
                        plan_dict,
                        request_id=request_id,
                        **await self._direct_fallback_channel(workspace=workspace, request_id=request_id),
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
                            plan_dict,
                            request_id=request_id,
                            **await self._direct_fallback_channel(workspace=workspace, request_id=request_id),
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
                            plan_dict,
                            request_id=request_id,
                            **await self._direct_fallback_channel(workspace=workspace, request_id=request_id),
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
                    # the captured boundary â€” no normal emit() between capture
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
                        plan_dict,
                        request_id=request_id,
                        **await self._direct_fallback_channel(workspace=workspace, request_id=request_id),
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
                        plan_dict,
                        request_id=request_id,
                        **await self._direct_fallback_channel(workspace=workspace, request_id=request_id),
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
                    # SDK 1.4.3 does not expose input_id on the generator
                    # object; the legitimate source is yielded event metadata.
                    # Generator-attribute reads below are retained only as a
                    # harmless fallback for older SDKs.
                    _evt_input_id, _evt_input_created_at = _event_data_input_id(first_event)
                    _modal_input_id = str(
                        getattr(stream, "input_id", "")
                        or getattr(_iterator, "input_id", "")
                        or _evt_input_id
                        or _modal_input_id
                    )
                    _modal_input_created_at = (
                        getattr(stream, "input_created_at", None)
                        or getattr(_iterator, "input_created_at", None)
                        or _evt_input_created_at
                        or _modal_input_created_at
                    )
                    if _evt_input_id and _modal_input_id_emitted is False:
                        _modal_input_id_emitted = True
                        if runtime_trace is not None:
                            runtime_trace.emit("modal_input_id_observed", phase="local", metadata={
                                "modal_input_id": _modal_input_id,
                            })
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
                if fn is None and self._observe_cancelled_event(first_event, request_id=request_id):
                    # Remote cooperative-cancellation confirmation as the first
                    # event: confirm the handle and never surface the event
                    # (it must not feed the result drain or the caller-visible
                    # stream).  The loop below consumes any trailing frames.
                    _cancelled_event_seen = True
                elif isinstance(first_event, dict) and first_event.get("type") == "result":
                    # Common-path hole: when the FIRST remote event is already
                    # the result, the loop below never runs, so emit the
                    # receipt marker before yielding it.
                    if fn is None:
                        self._observe_completion(request_id=request_id)
                    if runtime_trace is not None:
                        runtime_trace.emit("final_result_received", phase="local")
                    _fe_data = first_event.get("data")
                    if isinstance(_fe_data, dict) and is_graph_result(_fe_data):
                        attach_waterfall(
                            _fe_data,
                            run_label="modal_transport run_prompt_stream",
                            print_render=False,
                        )
                if not _cancelled_event_seen:
                    yield first_event
                async for event in _iterator:
                    if fn is None and self._observe_cancelled_event(event, request_id=request_id):
                        _cancelled_event_seen = True
                        # The cancelled event is transport-internal protocol:
                        # it confirms the handle and is never surfaced as a
                        # normal stream event.
                        continue
                    if isinstance(event, dict):
                        # Input ID learned from yielded event metadata (the
                        # legitimate SDK 1.4.3 source); observe once.
                        _evt_iid, _evt_ica = _event_data_input_id(event)
                        if _evt_iid and not _modal_input_id_emitted:
                            _modal_input_id = _evt_iid
                            if _modal_input_created_at is None:
                                _modal_input_created_at = _evt_ica
                            if runtime_trace is not None:
                                runtime_trace.set_metadata(modal_input_id=_modal_input_id)
                                runtime_trace.emit("modal_input_id_observed", phase="local", metadata={
                                    "modal_input_id": _modal_input_id,
                                })
                            _modal_input_id_emitted = True
                    if isinstance(event, dict) and event.get("type") == "result":
                        if fn is None:
                            self._observe_completion(request_id=request_id)
                        if runtime_trace is not None:
                            runtime_trace.emit("final_result_received", phase="local")
                        _rdata = event.get("data")
                        if isinstance(_rdata, dict) and is_graph_result(_rdata):
                            attach_waterfall(
                                _rdata,
                                run_label="modal_transport run_prompt_stream",
                                print_render=False,
                            )
                    yield event
                _stream_exhausted = True
            else:
                result = await stream if inspect.isawaitable(stream) else stream
                if isinstance(result, dict):
                    if runtime_trace is not None:
                        runtime_trace.emit("non_stream_result_received", phase="local")
                    if is_graph_result(result):
                        attach_waterfall(
                            result,
                            run_label="modal_transport run_prompt_stream",
                        )
                    yield {"type": "result", "data": result}
                    _stream_exhausted = True
        except Exception as exc:
            raise TransportError(str(exc)) from exc
        finally:
            if _iterator is not None and not _stream_exhausted:
                if _cancelled_event_seen:
                    # Cancellation path: bounded cleanup only â€” the normal
                    # result â†’ shielded persistence drain must NOT run for a
                    # cancelled attempt.  Closing the iterator here is local
                    # generator cleanup, never proof of remote stop: the
                    # handle is confirmed solely by the remote ``cancelled``
                    # event.
                    await _aclose_iterator(_iterator)
                else:
                    # Variant A: caller finished early (result received).  Drain the
                    # remaining stream in the background so the remote generator runs
                    # to completion (deferred commit) and its terminal persistence
                    # event is observed.  Shielded: cancellation of this request must
                    # not kill the drain.  The drain is registered so a teardown
                    # seam can join/cancel it with a bounded timeout.
                    self._drain_task = _spawn_persistence_drain(
                        _iterator,
                        request_id=request_id,
                        runtime_trace=runtime_trace,
                    )
                    self._drain_request_ids.add(str(request_id))
            else:
                await _aclose_iterator(_iterator)

    async def close_persistence_drains(self, *, timeout: float = 15.0) -> list[dict]:
        """Bounded-join seam for this transport's spawned persistence drains.

        Awaits each registered drain up to *timeout* so the trailing remote
        persistence event is deterministically collected; any drain that does
        not settle in time is cancelled and awaited cleanly.  Returns the
        recorded persistence records.  Result delivery/critical path is never
        affected â€” this is a teardown-only seam.
        """
        records: list[dict] = []
        for request_id in list(self._drain_request_ids):
            record = await join_persistence_drain(request_id, timeout=timeout)
            if record is not None:
                records.append(dict(record))
        return records

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
                    # Finalize nested cell.completed/cell.failed graph results
                    # and terminal result events; never fabricate stages for
                    # summaries/cells/probes.
                    if isinstance(event, dict):
                        _gres = graph_result_from_event(event)
                        if isinstance(_gres, dict) and is_graph_result(_gres):
                            attach_waterfall(
                                _gres,
                                run_label="modal_transport run_checkpoint_stream",
                            )
                    yield event
            finally:
                await _aclose_iterator(ait)
        else:
            result = await stream if inspect.isawaitable(stream) else stream
            if isinstance(result, dict) and is_graph_result(result):
                attach_waterfall(
                    result,
                    run_label="modal_transport run_checkpoint_stream",
                )
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
        result dict.  The seed payload is passed through unchanged â€” it is
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
