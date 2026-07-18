"""Measured two-lane UNET/CLIP restore preparation."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import RLock
from collections.abc import Mapping
from typing import Any, Callable, Iterator

from .contracts import ModelRestoreKey, PrefillKey
from .trace import RuntimeTrace


@dataclass
class PreparationDiagnostics:
    unet_started_at: float = 0.0
    unet_completed_at: float = 0.0
    clip_started_at: float = 0.0
    clip_completed_at: float = 0.0
    prefill_started_at: float = 0.0
    prefill_completed_at: float = 0.0
    unet_demanded_at: float = 0.0
    clip_demanded_at: float = 0.0
    prefill_demanded_at: float = 0.0
    unet_wait_ms: float = 0.0
    clip_wait_ms: float = 0.0
    prefill_wait_ms: float = 0.0
    unet_work_completed_before_demand_ms: float = 0.0
    clip_work_completed_before_demand_ms: float = 0.0
    prefill_work_completed_before_demand_ms: float = 0.0
    unet_actual_graph_wait_ms: float = 0.0
    clip_actual_graph_wait_ms: float = 0.0
    prefill_actual_graph_wait_ms: float = 0.0
    useful_overlap_ms: float = 0.0
    unused_speculation: bool = False
    unet_error: str = ""
    clip_error: str = ""
    prefill_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        for key in (
            "unet_wait_ms",
            "clip_wait_ms",
            "prefill_wait_ms",
            "unet_work_completed_before_demand_ms",
            "clip_work_completed_before_demand_ms",
            "prefill_work_completed_before_demand_ms",
            "unet_actual_graph_wait_ms",
            "clip_actual_graph_wait_ms",
            "prefill_actual_graph_wait_ms",
            "useful_overlap_ms",
        ):
            data[key] = round(float(data[key]), 3)
        return data


@dataclass
class RestorePreparation:
    model_key: ModelRestoreKey
    prefill_key: PrefillKey
    unet_future: Future[Any] | None = None
    clip_future: Future[Any] | None = None
    prefill_future: Future[Any] | None = None
    diagnostics: PreparationDiagnostics = field(default_factory=PreparationDiagnostics)


class ModelPreloadCoordinator:
    """Direct coordinator for restore-time UNET and CLIP work."""

    def __init__(
        self,
        *,
        unet_loader: Callable[[ModelRestoreKey], Any] | None = None,
        clip_loader: Callable[[ModelRestoreKey], Any] | None = None,
        prefill_loader: Callable[[PrefillKey, Any], Any] | None = None,
        max_workers: int = 2,
    ) -> None:
        self.unet_loader = unet_loader
        self.clip_loader = clip_loader
        self.prefill_loader = prefill_loader
        self._max_workers = max(1, min(int(max_workers), 2))
        # Do not create worker threads during Modal's snap=True startup. The
        # pool is intentionally created only when snap=False schedules a real
        # restore, so no thread objects cross the memory snapshot boundary.
        self._pool: ThreadPoolExecutor | None = None
        self._pool_lock = RLock()
        self._active: RestorePreparation | None = None

    def prepare(
        self,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        *,
        exact_prefill: bool = True,
        prepare_unet: bool = True,
        prepare_clip: bool = True,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        preparation = RestorePreparation(model_key=model_key, prefill_key=prefill_key)
        self._active = preparation

        unet_loader = self.unet_loader
        clip_loader = self.clip_loader
        if prepare_unet and unet_loader is not None:
            preparation.unet_future = self._submit("unet", lambda: unet_loader(model_key), preparation, trace)
        if prepare_clip and clip_loader is not None:
            preparation.clip_future = self._submit("clip", lambda: clip_loader(model_key), preparation, trace)
        prefill_loader = self.prefill_loader
        if exact_prefill and prefill_loader is not None and prefill_key.prompt_bundle_hash:
            def prefill() -> Any:
                clip = self.wait_clip(preparation, trace=trace, demand_source="prefill")
                return prefill_loader(prefill_key, clip)
            preparation.prefill_future = self._submit("prefill", prefill, preparation, trace)
        else:
            preparation.diagnostics.unused_speculation = bool(exact_prefill and self.prefill_loader is None)
        return preparation

    def wait_unet(self, preparation: RestorePreparation | None = None, *, trace: RuntimeTrace | None = None) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "unet", prep.unet_future, trace)

    def wait_clip(
        self,
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
        demand_source: str = "graph",
    ) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "clip", prep.clip_future, trace, demand_source=demand_source)

    def wait_prefill(self, preparation: RestorePreparation | None = None, *, trace: RuntimeTrace | None = None) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "prefill", prep.prefill_future, trace, demand_source="graph")

    def diagnostics(self, preparation: RestorePreparation | None = None) -> dict[str, Any]:
        return (preparation or self._require_active()).diagnostics.to_dict()

    def close(self) -> None:
        with self._pool_lock:
            pool = self._pool
            self._pool = None
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=False)

    def _ensure_pool(self) -> ThreadPoolExecutor:
        with self._pool_lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="comfymodal-restore",
                )
            return self._pool

    def _submit(self, name: str, callback: Callable[[], Any], preparation: RestorePreparation, trace: RuntimeTrace | None) -> Future[Any]:
        def run() -> Any:
            started = time.time()
            setattr(preparation.diagnostics, f"{name}_started_at", started)
            if trace:
                trace.emit(f"{name}_prepare_start", phase="restore")
            try:
                result = callback()
                setattr(preparation.diagnostics, f"{name}_completed_at", time.time())
                if trace:
                    trace.emit(f"{name}_prepare_end", phase="restore")
                return result
            except Exception as exc:
                setattr(preparation.diagnostics, f"{name}_error", str(exc))
                setattr(preparation.diagnostics, f"{name}_completed_at", time.time())
                if trace:
                    trace.emit(f"{name}_prepare_end", phase="restore", metadata={"error": str(exc)[:200]})
                raise
        return self._ensure_pool().submit(run)

    def _wait(
        self,
        preparation: RestorePreparation,
        name: str,
        future: Future[Any] | None,
        trace: RuntimeTrace | None,
        *,
        demand_source: str = "graph",
    ) -> Any:
        demanded = time.time()
        if demand_source == "graph":
            setattr(preparation.diagnostics, f"{name}_demanded_at", demanded)
        if future is None:
            return None
        wait_started = time.time()
        if trace:
            trace.emit(
                f"{name}_wait_start",
                phase="execution" if demand_source == "graph" else "restore",
                metadata={"demand_source": demand_source},
            )
        result = future.result()
        completed = getattr(preparation.diagnostics, f"{name}_completed_at")
        wait_ms = max(0.0, (time.time() - wait_started) * 1000.0)
        completed_before_demand_ms = max(0.0, (demanded - completed) * 1000.0)
        setattr(preparation.diagnostics, f"{name}_wait_ms", wait_ms)
        if demand_source == "graph":
            setattr(preparation.diagnostics, f"{name}_actual_graph_wait_ms", wait_ms)
            setattr(
                preparation.diagnostics,
                f"{name}_work_completed_before_demand_ms",
                completed_before_demand_ms,
            )
        if trace:
            trace.emit(
                f"{name}_wait_end",
                phase="execution" if demand_source == "graph" else "restore",
                metadata={
                    "demand_source": demand_source,
                    "wait_ms": round(wait_ms, 3),
                    "completed_before_demand_ms": round(completed_before_demand_ms, 3),
                },
            )
        if name == "unet":
            clip_start = preparation.diagnostics.clip_started_at
            if clip_start and preparation.diagnostics.unet_completed_at:
                preparation.diagnostics.useful_overlap_ms = max(0.0, (preparation.diagnostics.unet_completed_at - clip_start) * 1000.0)
        return result

    def _require_active(self) -> RestorePreparation:
        if self._active is None:
            raise RuntimeError("no active restore preparation")
        return self._active


_ACTIVE_V2_LOADER_BRIDGE: ContextVar["V2LoaderBridge | None"] = ContextVar(
    "comfymodal_active_v2_loader_bridge",
    default=None,
)
_LOADER_MISS = object()


def current_v2_loader_bridge() -> "V2LoaderBridge | None":
    """Return the bridge active for the current graph-execution context."""
    return _ACTIVE_V2_LOADER_BRIDGE.get()


class V2LoaderBridge:
    """Connect restore preparation to ComfyUI's real loader node methods.

    The bridge wraps the already-loaded node classes instead of replacing
    ComfyUI's loader implementation. A matching prepared result is returned;
    every mismatch, missing plan, or failed future falls through to the
    original loader. The context variable isolates v2 from legacy requests.
    """

    _NODE_METHODS = {
        "UNETLoader": "load_unet",
        "CLIPLoader": "load_clip",
        "DualCLIPLoader": "load_clip",
        "CLIPTextEncode": "encode",
    }

    def __init__(self, *, max_workers: int = 2) -> None:
        self.coordinator = ModelPreloadCoordinator(
            unet_loader=self._load_unet,
            clip_loader=self._load_clip,
            prefill_loader=self._prefill,
            max_workers=max_workers,
        )
        self._nodes: Any | None = None
        self._original_methods: dict[str, Callable[..., Any]] = {}
        self._node_classes: dict[str, Any] = {}
        self._model_key: ModelRestoreKey | None = None
        self._prefill_key: PrefillKey | None = None
        self._model_spec: Mapping[str, Any] = {}
        self._preparation: RestorePreparation | None = None
        self._trace: RuntimeTrace | None = None
        self._prefill_results: dict[tuple[int, str], Any] = {}
        self._prefill_lock = RLock()

    def install(self, nodes_module: Any | None = None) -> bool:
        """Install wrappers on the live ComfyUI node classes once."""
        if nodes_module is None:
            import nodes as nodes_module  # type: ignore[no-redef]
        mappings = getattr(nodes_module, "NODE_CLASS_MAPPINGS", {})
        if not isinstance(mappings, Mapping):
            return False
        self._nodes = nodes_module
        installed = False
        for class_name, method_name in self._NODE_METHODS.items():
            node_class = mappings.get(class_name)
            method = getattr(node_class, method_name, None) if node_class else None
            if not callable(method):
                continue
            key = f"{class_name}.{method_name}"
            self._node_classes[class_name] = node_class
            if getattr(method, "_comfy_modal_v2_loader_bridge", False):
                original = getattr(method, "_comfy_modal_v2_original", None)
                if callable(original):
                    self._original_methods[key] = original
                continue
            self._original_methods[key] = method
            wrapper = self._make_wrapper(class_name, method_name, method)
            setattr(wrapper, "_comfy_modal_v2_loader_bridge", True)
            setattr(wrapper, "_comfy_modal_v2_original", method)
            setattr(node_class, method_name, wrapper)
            installed = True
        return installed or bool(self._original_methods)

    def prepare(
        self,
        plan: Any,
        *,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation | None:
        """Start actual restore-time UNET/CLIP work for one RestorePlan."""
        self._model_key = plan.model_key
        self._prefill_key = plan.prefill_key
        self._model_spec = plan.model_spec if isinstance(plan.model_spec, Mapping) else {}
        self._trace = trace
        with self._prefill_lock:
            self._prefill_results.clear()
        self._preparation = None
        if not self._model_key or not (
            self._model_key.unet_identity or self._model_key.clip_identity
        ):
            if trace:
                trace.emit("preload_schedule_end", phase="restore", metadata={"status": "no_model_key"})
            return None
        self.install(self._nodes)
        prepare_unet = bool(self._model_key.unet_identity and self._request_list("unet"))
        prepare_clip = bool(self._model_key.clip_identity and self._request_list("clip"))
        exact_prefill = bool(
            self._prefill_key
            and self._prefill_key.prompt_bundle_hash
            and isinstance(self._prefill_key.encode_options, Mapping)
            and self._prefill_key.encode_options.get("eligible", True)
            and prepare_clip
        )
        if trace:
            trace.emit(
                "preload_schedule_start",
                phase="restore",
                metadata={
                    "unet_identity": self._model_key.unet_identity,
                    "clip_identity": self._model_key.clip_identity,
                    "exact_prefill": exact_prefill,
                },
            )
        self._preparation = self.coordinator.prepare(
            self._model_key,
            self._prefill_key or PrefillKey(model_key=self._model_key),
            exact_prefill=exact_prefill,
            prepare_unet=prepare_unet,
            prepare_clip=prepare_clip,
            trace=trace,
        )
        if trace:
            trace.emit(
                "preload_schedule_end",
                phase="restore",
                metadata={
                    "status": "started",
                    "unet_future": bool(self._preparation.unet_future),
                    "clip_future": bool(self._preparation.clip_future),
                    "prefill_future": bool(self._preparation.prefill_future),
                },
            )
        return self._preparation

    @contextmanager
    def request_scope(self) -> Iterator[None]:
        """Make this bridge visible only while the v2 graph is executing."""
        token = _ACTIVE_V2_LOADER_BRIDGE.set(self)
        try:
            yield
        finally:
            _ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def diagnostics(self) -> dict[str, Any]:
        if self._preparation is None:
            return {}
        return self.coordinator.diagnostics(self._preparation)

    def clear(self) -> None:
        """Disable consumption when a restore has no authoritative plan."""
        self._model_key = None
        self._prefill_key = None
        self._model_spec = {}
        self._preparation = None
        self._trace = None
        with self._prefill_lock:
            self._prefill_results.clear()

    def _make_wrapper(self, class_name: str, method_name: str, original: Callable[..., Any]) -> Callable[..., Any]:
        if class_name == "UNETLoader":
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_unet(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        elif class_name in {"CLIPLoader", "DualCLIPLoader"}:
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_clip(class_name, args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        else:
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_prefill(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        return wrapped

    def _request_list(self, bucket: str) -> list[dict[str, Any]]:
        loaders = self._model_spec.get("loaders", self._model_spec)
        values = loaders.get(bucket, []) if isinstance(loaders, Mapping) else []
        return [dict(value) for value in values if isinstance(value, Mapping)]

    def _find_request(self, bucket: str, identity: str) -> dict[str, Any] | None:
        for request in self._request_list(bucket):
            values = (
                request.get("unet_name"),
                request.get("clip_name"),
                request.get("clip_name1"),
            )
            if identity and identity in {str(value) for value in values if value}:
                return request
            if bucket == "clip" and request.get("clip_name1") and request.get("clip_name2"):
                if identity == f"{request['clip_name1']}||{request['clip_name2']}":
                    return request
        return None

    def _load_unet(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("unet", model_key.unet_identity)
        if request is None:
            raise RuntimeError(f"v2 UNET loader request is absent for {model_key.unet_identity!r}")
        kwargs = {
            "unet_name": request.get("unet_name", model_key.unet_identity),
            "weight_dtype": request.get("weight_dtype", "default"),
        }
        result = self._invoke_original("UNETLoader", kwargs)
        return result[0] if isinstance(result, (tuple, list)) and result else result

    def _load_clip(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("clip", model_key.clip_identity)
        if request is None:
            raise RuntimeError(f"v2 CLIP loader request is absent for {model_key.clip_identity!r}")
        class_name = str(request.get("loader_class", "CLIPLoader"))
        kwargs = dict(request)
        kwargs.pop("node_id", None)
        kwargs.pop("loader_class", None)
        kwargs.setdefault("type", model_key.clip_type or "stable_diffusion")
        kwargs.setdefault("device", "default")
        result = self._invoke_original(class_name, kwargs)
        return result[0] if isinstance(result, (tuple, list)) and result else result

    def _prefill(self, prefill_key: PrefillKey, clip: Any) -> dict[tuple[int, str], Any]:
        options = prefill_key.encode_options
        entries = options.get("encodes", []) if isinstance(options, Mapping) else []
        results: dict[tuple[int, str], Any] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            text = str(entry.get("text", ""))
            if not text:
                continue
            result = self._invoke_original(
                "CLIPTextEncode",
                {"clip": clip, "text": text},
            )
            results[(id(clip), text)] = result
        return results

    def _consume_unet(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        key = self._model_key
        preparation = self._preparation
        unet_name = kwargs.get("unet_name", args[0] if args else "")
        if key is None or preparation is None or str(unet_name) != key.unet_identity:
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_unet_demand", phase="execution", metadata={"unet_name": str(unet_name)})
            self._trace.emit("graph_unet_wait_start", phase="execution")
        try:
            result = self.coordinator.wait_unet(preparation)
        except Exception as exc:
            if self._trace:
                self._trace.emit("graph_unet_wait_end", phase="execution", metadata={"status": "error"})
                self._trace.emit("graph_unet_consumed", phase="execution", metadata={"status": "fallback", "error": str(exc)[:200]})
            return _LOADER_MISS
        if result is None:
            if self._trace:
                self._trace.emit("graph_unet_wait_end", phase="execution", metadata={"status": "unavailable"})
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_unet_wait_end", phase="execution", metadata={"status": "ok"})
            self._trace.emit("graph_unet_consumed", phase="execution", metadata={"status": "prepared"})
        return (result,)

    def _consume_clip(self, class_name: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        key = self._model_key
        preparation = self._preparation
        if class_name == "DualCLIPLoader":
            clip_a = kwargs.get("clip_name1", args[0] if args else "")
            clip_b = kwargs.get("clip_name2", args[1] if len(args) > 1 else "")
            identity = f"{clip_a}||{clip_b}"
        else:
            identity = str(kwargs.get("clip_name", args[0] if args else ""))
        if key is None or preparation is None or identity != key.clip_identity:
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_clip_demand", phase="execution", metadata={"clip_identity": identity})
            self._trace.emit("graph_clip_wait_start", phase="execution")
        try:
            result = self.coordinator.wait_clip(preparation)
        except Exception as exc:
            if self._trace:
                self._trace.emit("graph_clip_wait_end", phase="execution", metadata={"status": "error"})
                self._trace.emit("graph_clip_consumed", phase="execution", metadata={"status": "fallback", "error": str(exc)[:200]})
            return _LOADER_MISS
        if result is None:
            if self._trace:
                self._trace.emit("graph_clip_wait_end", phase="execution", metadata={"status": "unavailable"})
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_clip_wait_end", phase="execution", metadata={"status": "ok"})
            self._trace.emit("graph_clip_consumed", phase="execution", metadata={"status": "prepared"})
        return (result,)

    def _consume_prefill(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        preparation = self._preparation
        if preparation is None or self._prefill_key is None or not self._prefill_key.prompt_bundle_hash:
            return _LOADER_MISS
        clip = kwargs.get("clip", args[0] if args else None)
        text = str(kwargs.get("text", args[1] if len(args) > 1 else ""))
        if clip is None or not text:
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_prefill_demand", phase="execution", metadata={"text_length": len(text)})
            self._trace.emit("graph_prefill_wait_start", phase="execution")
        try:
            cache_key = (id(clip), text)
            with self._prefill_lock:
                result = self._prefill_results.get(cache_key, _LOADER_MISS)
            if result is _LOADER_MISS:
                # Never hold the cache lock while waiting for the restore
                # future. This keeps parallel CLIPTextEncode nodes from
                # deadlocking and makes the blocking interval measurable.
                values = self.coordinator.wait_prefill(preparation)
                with self._prefill_lock:
                    if isinstance(values, Mapping):
                        self._prefill_results.update(values)
                    result = self._prefill_results.get(cache_key, _LOADER_MISS)
        except Exception as exc:
            if self._trace:
                self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "error"})
                self._trace.emit("graph_prefill_consumed", phase="execution", metadata={"status": "fallback", "error": str(exc)[:200]})
            return _LOADER_MISS
        if result is _LOADER_MISS:
            if self._trace:
                self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "unavailable"})
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "ok"})
            self._trace.emit("graph_prefill_consumed", phase="execution", metadata={"status": "prepared"})
        return result

    def _invoke_original(self, class_name: str, kwargs: Mapping[str, Any]) -> Any:
        method_name = self._NODE_METHODS[class_name]
        method = self._original_methods.get(f"{class_name}.{method_name}")
        node_class = self._node_classes.get(class_name)
        if not callable(method) or node_class is None:
            raise RuntimeError(f"original ComfyUI loader is unavailable: {class_name}.{method_name}")
        return method(node_class(), **dict(kwargs))
