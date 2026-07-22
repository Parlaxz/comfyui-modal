"""Explicit execution backend selection and streaming.

Pre-sampler critical-path facility
-----------------------------------
``PreSamplerCache`` — lightweight orchestration/cache component that a runner
attaches to ``context.metadata["pre_sampler_cache"]``.  It caches node inputs,
model patches, futures, and conditioning within a single request, and records
operation timings for critical-path analysis.

``attach_pre_sampler_critical_path(result, plan, cache)`` — postprocessor that
consumes an existing result dict and produces an additive pre-sampler critical
path summary attached to ``result["trace"]`` or ``result`` directly.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping

from .contracts import ExecutionPlan
from .trace import RuntimeTrace


# ── Pre-sampler cache / orchestration component ──────────────────────────

_PRE_SAMPLER_REQUIRED_OPERATIONS = (
    "cache_key_build", "cache_lookup", "input_resolution",
    "model_patch", "conditioning", "future_wait", "lock_wait",
    "node_execution", "unattributed",
)

# Sentinel to distinguish a cached None from a cache miss
_MISS_SENTINEL = object()


@dataclass
class _PublishedResult:
    """Wrapper so we can store None results in the published-models dict."""
    value: Any


class PreSamplerCache:
    """Request-scoped orchestration/cache for pre-sampler critical-path work.

    A runner creates one instance per request and attaches it to
    ``context.metadata["pre_sampler_cache"]``.  All methods are safe to call
    any number of times — redundant work is skipped transparently.

    Timing uses the provided *clock* (default ``time.perf_counter``).
    When *trace* is provided (a ``RuntimeTrace`` instance), operation events
    are emitted through the trace extension points.

    **Cache rules**
      * ``build_cache_key()`` — computes the graph cache key at most once
      * ``resolve_inputs()`` — returns cached prepared inputs when the exact
        (node_id, class_type, input_fingerprint) matches; accepts an optional
        ``builder`` to resolve uncached inputs
      * ``apply_model_patch()`` — applies a patch at most once per
        (published_model_id, patch_identity); returns cached result on hit
      * ``get_future_result()`` — returns a completed future immediately
        without awaiting; awaits only incomplete awaitables
      * ``cache_conditioning()`` — caches by (fingerprint, id(clip));
        distinguishes a cached ``None`` from a miss via sentinel
      * Node execution order, outputs, and sampler parameters are preserved
        (no workflow result caching).
    """

    __slots__ = (
        "_clock", "_lock", "_trace", "_graph_cache_key",
        "_node_input_cache", "_published_models",
        "_conditioning_cache",
        # counters
        "operation_count", "operation_hits", "operation_timing_ms",
        "dominant_spans", "node_class_map", "lock_acquisition_count",
    )

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        trace: RuntimeTrace | None = None,
    ):
        self._clock = clock or time.perf_counter
        self._lock = threading.Lock()
        self._graph_cache_key: str | None = None
        self._node_input_cache: dict[tuple, Any] = {}
        # dict: (published_model_id, patch_identity) -> _PublishedResult
        self._published_models: dict[tuple[str, str], Any] = {}
        self._conditioning_cache: dict[tuple, Any] = {}
        self._trace: RuntimeTrace | None = trace

        # Operation counters
        self.operation_count: dict[str, int] = {
            op: 0 for op in _PRE_SAMPLER_REQUIRED_OPERATIONS
        }
        self.operation_hits: dict[str, int] = {
            op: 0 for op in ("cache_lookup", "model_patch", "conditioning", "future_wait")
        }
        self.operation_timing_ms: dict[str, float] = {
            op: 0.0 for op in _PRE_SAMPLER_REQUIRED_OPERATIONS
        }
        self.dominant_spans: list[dict[str, Any]] = []
        self.node_class_map: dict[str, str] = {}
        self.lock_acquisition_count = 0

    # ── internal helpers ─────────────────────────────────────────────

    def _record_operation(
        self,
        operation: str,
        duration_ms: float,
        *,
        node_id: str = "",
        class_type: str = "",
        cache_hit: bool = False,
        reused: bool = False,
        skipped: bool = False,
        start_node_id: str = "",
        start_node_class_type: str = "",
        end_node_id: str = "",
        end_node_class_type: str = "",
    ) -> None:
        self.operation_count[operation] = self.operation_count.get(operation, 0) + 1
        self.operation_timing_ms[operation] = (
            self.operation_timing_ms.get(operation, 0.0) + duration_ms
        )
        if cache_hit and operation in self.operation_hits:
            self.operation_hits[operation] = self.operation_hits.get(operation, 0) + 1

        # Record dominant span if it has node attribution
        if node_id or start_node_id or end_node_id:
            span: dict[str, Any] = {
                "operation": operation,
                "duration_ms": round(duration_ms, 3),
            }
            if node_id:
                span["node_id"] = node_id
            if class_type:
                span["class_type"] = class_type
            if start_node_id:
                span["start_node_id"] = start_node_id
            if start_node_class_type:
                span["start_node_class_type"] = start_node_class_type
            if end_node_id:
                span["end_node_id"] = end_node_id
            if end_node_class_type:
                span["end_node_class_type"] = end_node_class_type
            if cache_hit:
                span["cache_hit"] = True
            if reused:
                span["reused"] = True
            if skipped:
                span["skipped"] = True
            self.dominant_spans.append(span)

        # Trace integration
        if self._trace is not None:
            meta: dict[str, Any] = {
                "operation": operation,
                "duration_ms": round(duration_ms, 3),
            }
            if node_id or start_node_id:
                if node_id:
                    meta["node_id"] = node_id
                    meta["class_type"] = class_type or ""
                if start_node_id:
                    meta["start_node_id"] = start_node_id
                    meta["start_node_class_type"] = start_node_class_type or ""
                if end_node_id:
                    meta["end_node_id"] = end_node_id
                    meta["end_node_class_type"] = end_node_class_type or ""
            if cache_hit:
                meta["cache_hit"] = True
            if reused:
                meta["reused"] = True
            if skipped:
                meta["skipped"] = True
            self._trace.emit(
                f"pre_sampler_{operation}",
                process="cache",
                phase="pre_sampler",
                metadata=meta,
            )

    def _time_operation(
        self,
        operation: str,
        *,
        node_id: str = "",
        class_type: str = "",
        cache_hit: bool = False,
        reused: bool = False,
        skipped: bool = False,
        start_node_id: str = "",
        start_node_class_type: str = "",
        end_node_id: str = "",
        end_node_class_type: str = "",
    ) -> _TimerContext:
        """Return a context manager that times the operation."""
        return _TimerContext(
            cache=self,
            operation=operation,
            clock=self._clock,
            node_id=node_id,
            class_type=class_type,
            cache_hit=cache_hit,
            reused=reused,
            skipped=skipped,
            start_node_id=start_node_id,
            start_node_class_type=start_node_class_type,
            end_node_id=end_node_id,
            end_node_class_type=end_node_class_type,
        )

    # ── Public API ───────────────────────────────────────────────────

    def build_cache_key(self, plan: ExecutionPlan) -> str:
        """Build and cache the graph cache key once per request.

        Uses ``plan.workflow_hash`` if available (cheap), otherwise
        computes from the workflow dict.  Never deep-copies or content-hashes
        model objects — only scalar/link values are fingerprinted.
        """
        # Fast path: already built — no timer, no count increment
        if self._graph_cache_key is not None:
            return self._graph_cache_key

        with self._time_operation("cache_key_build"):

            # Use existing hash if available
            wf_hash = plan.workflow_hash
            if not wf_hash:
                # Build a lightweight fingerprint from scalar/link values only
                wf = plan.workflow
                parts: list[str] = []
                # Handle both regular dict and MappingProxyType
                if hasattr(wf, "items"):
                    for raw_nid, node in sorted(wf.items(), key=lambda item: str(item[0])):
                        nid = str(raw_nid)
                        if isinstance(node, dict):
                            ct = node.get("class_type", "")
                        elif hasattr(node, "get"):
                            try:
                                ct = node.get("class_type", "")
                            except Exception:
                                ct = ""
                        else:
                            ct = ""
                        parts.append(f"{nid}:{ct}")
                        if isinstance(node, dict):
                            inp = node.get("inputs", {})
                        elif hasattr(node, "get"):
                            try:
                                inp = node.get("inputs", {})
                            except Exception:
                                inp = {}
                        else:
                            inp = {}
                        if isinstance(inp, dict) or hasattr(inp, "items"):
                            try:
                                items = sorted(inp.items(), key=lambda item: str(item[0]))
                            except Exception:
                                items = []
                            for k, v in items:
                                if isinstance(v, (str, int, float, bool)):
                                    parts.append(f"{k}={v}")
                                elif isinstance(v, (list, tuple)):
                                    scalar_items = [
                                        str(x) for x in v
                                        if isinstance(x, (str, int, float, bool))
                                    ]
                                    parts.append(f"{k}=[{','.join(scalar_items)}]")
                wf_hash = str(hash(tuple(parts)))

            self._graph_cache_key = wf_hash
            return self._graph_cache_key

    def resolve_inputs(
        self,
        node_id: str,
        class_type: str,
        inputs: dict[str, Any],
        builder: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Cache and return prepared node inputs.

        Uses a fingerprint of (node_id, class_type, exact input values).
        Scalar/link values (str, int, float, bool) are used directly;
        opaque model objects are distinguished by ``id()`` only.
        Nested scalar/link sequences are fingerprinted element-wise;
        opaque objects within sequences also use ``id()``.

        When *builder* is provided and inputs are not cached, the builder
        is called and its wall time recorded as ``input_resolution``
        (separate non-overlapping leaf from ``cache_lookup``).

        Returns the **same** cached dict when inputs are identical.
        Existing callers without *builder* continue to work unchanged.
        """
        started = self._clock()
        fp = self._fingerprint_inputs(node_id, class_type, inputs)
        cached = self._node_input_cache.get(fp)
        lookup_elapsed = (self._clock() - started) * 1000
        if cached is not None:
            self._record_operation(
                "cache_lookup", lookup_elapsed,
                node_id=node_id, class_type=class_type,
                cache_hit=True,
            )
            return cached

        if builder is not None:
            build_start = self._clock()
            resolved = builder()
            build_elapsed = (self._clock() - build_start) * 1000
            self._node_input_cache[fp] = resolved
            self._record_operation(
                "input_resolution", build_elapsed,
                node_id=node_id, class_type=class_type,
            )
            self._record_operation(
                "cache_lookup", lookup_elapsed,
                node_id=node_id, class_type=class_type,
            )
            return resolved

        self._node_input_cache[fp] = inputs
        self._record_operation(
            "cache_lookup", lookup_elapsed,
            node_id=node_id, class_type=class_type,
        )
        return inputs

    def apply_model_patch(
        self,
        published_model_id: str,
        patch_identity: str,
        patcher: Callable[[], Any],
    ) -> Any:
        """Apply a model patch at most once per identity.

        Uses a double-checked locking pattern: fast-path checks the dict
        without a lock, acquires the lock only on a miss, rechecks under
        lock.  The patcher result is cached and returned on subsequent
        hits.  Lock-wait time is recorded separately from model-patch time
        so they do not overlap.
        """
        key = (published_model_id, patch_identity)
        started = self._clock()

        # Fast path: already published, no lock
        if key in self._published_models:
            elapsed = (self._clock() - started) * 1000
            self._record_operation(
                "model_patch", elapsed,
                cache_hit=True,
                start_node_id=published_model_id,
                end_node_id=patch_identity,
            )
            return self._published_models[key].value

        # Lock on miss
        lock_start = self._clock()
        self.lock_acquisition_count += 1
        with self._lock:
            lock_elapsed = (self._clock() - lock_start) * 1000
            self._record_operation(
                "lock_wait", lock_elapsed,
                start_node_id=published_model_id,
                end_node_id=patch_identity,
            )

            # Double-check under lock
            if key in self._published_models:
                elapsed = (self._clock() - started) * 1000
                self._record_operation(
                    "model_patch", elapsed,
                    cache_hit=True,
                    start_node_id=published_model_id,
                    end_node_id=patch_identity,
                )
                return self._published_models[key].value

            # Measure only the patch execution (lock wait already recorded)
            patch_start = self._clock()
            try:
                result = patcher()
                patch_elapsed = (self._clock() - patch_start) * 1000
                self._published_models[key] = _PublishedResult(result)
                self._record_operation(
                    "model_patch", patch_elapsed,
                    start_node_id=published_model_id,
                    end_node_id=patch_identity,
                )
                return result
            except Exception:
                self._published_models.pop(key, None)
                raise

    async def get_future_result(
        self,
        future: Any,
    ) -> Any:
        """Return a completed future/coroutine result immediately without
        awaiting when possible; await incomplete awaitables once.

        For objects with a ``done()`` method that returns ``True``, the
        result is returned synchronously via ``.result()`` without yielding
        control to the event loop.  Incomplete futures with ``done()``
        returning ``False`` are wrapped via ``asyncio.ensure_future`` and
        awaited.  Incomplete coroutines and other awaitables are awaited
        once (timed).  Plain values are returned immediately (cache hit).
        """
        if hasattr(future, "done") and callable(future.done):
            if future.done():
                # Completed — zero wait, cache hit
                self._record_operation("future_wait", 0.0, cache_hit=True)
                return future.result()
            # Incomplete future — time the await without blocking the event loop.
            started = self._clock()
            if inspect.isawaitable(future):
                result = await asyncio.ensure_future(future)
            elif isinstance(future, concurrent.futures.Future) or hasattr(future, "result"):
                result = await asyncio.to_thread(future.result)
            else:
                result = await asyncio.to_thread(lambda: future)
            elapsed = (self._clock() - started) * 1000
            self._record_operation("future_wait", elapsed)
            return result
        # Coroutine or awaitable
        if inspect.isawaitable(future):
            started = self._clock()
            result = await future
            elapsed = (self._clock() - started) * 1000
            self._record_operation("future_wait", elapsed)
            return result
        # Plain value (not a future/awaitable) — immediate return, cache hit
        self._record_operation("future_wait", 0.0, cache_hit=True)
        return future

    def cache_conditioning(
        self,
        fingerprint: str,
        clip: Any,
        conditioning: Any,
    ) -> Any:
        """Cache conditioning output by (fingerprint, id(clip)).

        When the exact same (fingerprint, clip identity) pair is seen
        again, returns the cached conditioning without recomputing.
        Never deep-copies the clip object — uses ``id(clip)`` only.
        Distinguishes a cached ``None`` result from a cache miss.
        """
        key = (fingerprint, id(clip))
        started = self._clock()
        cached = self._conditioning_cache.get(key, _MISS_SENTINEL)
        if cached is not _MISS_SENTINEL:
            elapsed = (self._clock() - started) * 1000
            self._record_operation("conditioning", elapsed, cache_hit=True)
            return cached
        self._conditioning_cache[key] = conditioning
        elapsed = (self._clock() - started) * 1000
        self._record_operation("conditioning", elapsed)
        return conditioning

    def record_node_execution(
        self,
        node_id: str,
        class_type: str,
        duration_ms: float,
    ) -> None:
        """Record node execution time for critical-path attribution."""
        if class_type:
            self.node_class_map[node_id] = class_type
        self._record_operation(
            "node_execution", duration_ms,
            node_id=node_id,
            class_type=class_type,
        )

    def record_unattributed(self, duration_ms: float) -> None:
        """Record time that cannot be attributed to any specific operation."""
        if duration_ms > 0:
            self._record_operation("unattributed", duration_ms)

    # ── Fingerprinting ───────────────────────────────────────────────

    @staticmethod
    def _fingerprint_value(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)):
            return ("scalar", type(value).__name__, value)
        if value is None:
            return ("none",)
        if isinstance(value, (list, tuple)):
            return ("sequence", tuple(PreSamplerCache._fingerprint_value(item) for item in value))
        if isinstance(value, Mapping):
            items: list[tuple[Any, Any]] = []
            for key, item in value.items():
                key_token = key if isinstance(key, (str, int, float, bool)) else id(key)
                items.append((key_token, PreSamplerCache._fingerprint_value(item)))
            items.sort(key=lambda item: str(item[0]))
            return ("mapping", tuple(items))
        return ("identity", id(value))

    @staticmethod
    def _fingerprint_sequence(seq: list | tuple) -> tuple:
        return tuple(PreSamplerCache._fingerprint_value(item) for item in seq)

    @staticmethod
    def _fingerprint_inputs(
        node_id: str,
        class_type: str,
        inputs: dict[str, Any] | Mapping,
    ) -> tuple:
        """Build a cache key from (node_id, class_type, exact input values).

        Scalars and strings use their literal value.  Opaque model objects
        use ``id()`` — never deep-copy or content-hash them.
        Nested sequences of scalars are fingerprinted element-wise.
        Handles both regular dicts and MappingProxyType.
        """
        parts: list[Any] = [str(node_id), str(class_type)]
        if isinstance(inputs, dict) or hasattr(inputs, "keys"):
            for k in sorted(inputs.keys(), key=str):
                v = inputs[k]
                if isinstance(v, (str, int, float, bool)):
                    parts.append(k)
                    parts.append(v)
                    parts.append(("scalar_type", type(v).__name__))
                elif v is None:
                    parts.append(k)
                    parts.append(("none",))
                elif isinstance(v, (list, tuple, Mapping)):
                    parts.append(k)
                    parts.append(PreSamplerCache._fingerprint_value(v))
                else:
                    # Opaque object — use identity
                    parts.append(k)
                    parts.append(id(v))
        return tuple(parts)

    # ── Summary ──────────────────────────────────────────────────────

    def to_summary_dict(self) -> dict[str, Any]:
        """Export all operation timings and metadata for the postprocessor."""
        data: dict[str, Any] = {}
        for op in _PRE_SAMPLER_REQUIRED_OPERATIONS:
            val = self.operation_timing_ms.get(op, 0.0)
            data[f"{op}_ms"] = round(val, 3)

        measured = sum(
            self.operation_timing_ms.get(op, 0.0)
            for op in _PRE_SAMPLER_REQUIRED_OPERATIONS
            if op != "unattributed"
        )
        if measured > 0:
            data["total_measured_ms"] = round(measured, 3)
        if self.operation_timing_ms.get("unattributed", 0.0) > 0:
            data["unattributed_ms"] = round(self.operation_timing_ms["unattributed"], 3)

        data["operation_counts"] = dict(self.operation_count)
        data["lock_acquisition_count"] = self.lock_acquisition_count
        hits = {k: v for k, v in self.operation_hits.items() if v > 0}
        if hits:
            data["operation_hits"] = hits
        if self.dominant_spans:
            data["dominant_spans"] = list(self.dominant_spans)
        if self.node_class_map:
            data["node_class_map"] = dict(self.node_class_map)
        return data


class _TimerContext:
    """Context manager used internally by ``PreSamplerCache._time_operation``."""

    __slots__ = (
        "_cache", "_operation", "_clock", "_started",
        "_node_id", "_class_type", "_cache_hit", "_reused", "_skipped",
        "_start_node_id", "_start_node_class_type",
        "_end_node_id", "_end_node_class_type",
    )

    def __init__(
        self,
        cache: PreSamplerCache,
        operation: str,
        clock: Callable[[], float],
        node_id: str = "",
        class_type: str = "",
        cache_hit: bool = False,
        reused: bool = False,
        skipped: bool = False,
        start_node_id: str = "",
        start_node_class_type: str = "",
        end_node_id: str = "",
        end_node_class_type: str = "",
    ):
        self._cache = cache
        self._operation = operation
        self._clock = clock
        self._started = 0.0
        self._node_id = node_id
        self._class_type = class_type
        self._cache_hit = cache_hit
        self._reused = reused
        self._skipped = skipped
        self._start_node_id = start_node_id
        self._start_node_class_type = start_node_class_type
        self._end_node_id = end_node_id
        self._end_node_class_type = end_node_class_type

    def __enter__(self) -> "_TimerContext":
        self._started = self._clock()
        return self

    def __exit__(self, *args: Any) -> None:
        elapsed = (self._clock() - self._started) * 1000
        self._cache._record_operation(
            self._operation, elapsed,
            node_id=self._node_id,
            class_type=self._class_type,
            cache_hit=self._cache_hit,
            reused=self._reused,
            skipped=self._skipped,
            start_node_id=self._start_node_id,
            start_node_class_type=self._start_node_class_type,
            end_node_id=self._end_node_id,
            end_node_class_type=self._end_node_class_type,
        )


# ═══════════════════════════════════════════════════════════════════════
# Critical-path postprocessor
# ═══════════════════════════════════════════════════════════════════════

_PRE_SAMPLER_REQUIRED_FIELDS = (
    "cache_key_build_ms", "cache_lookup_ms", "input_resolution_ms",
    "model_patch_ms", "conditioning_ms", "future_wait_ms",
    "lock_wait_ms", "node_execution_ms", "unattributed_ms",
)


def attach_pre_sampler_critical_path(
    result: dict[str, Any],
    plan: ExecutionPlan,
    cache: PreSamplerCache | None = None,
) -> dict[str, Any]:
    """Attach an additive pre-sampler critical-path summary to *result*.

    Consumes the existing ``result["trace"]`` if present (as a dict from
    ``RuntimeTrace`` or legacy-ish events) plus ``plan.workflow`` for
    node-to-class-type mapping, and produces a ``"pre_sampler_critical_path"``
    key on the result (or inside ``result["trace"]`` if it is a dict).

    Trace events with ``pre_sampler_*`` operation metadata are also consumed:
    their operation durations are aggregated and merged with cache data
    (cache data takes priority when both exist).

    Summary structure::

        result["pre_sampler_critical_path"] = {
            "cache_key_build_ms": …,
            "cache_lookup_ms": …,
            "input_resolution_ms": …,
            "model_patch_ms": …,
            "conditioning_ms": …,
            "future_wait_ms": …,
            "lock_wait_ms": …,
            "node_execution_ms": …,
            "unattributed_ms": …,
            "total_measured_ms": …,
            "total_wall_ms": …,
            "residual_ms": …,
            "operation_counts": {…},
            "operation_hits": {…},
            "dominant_spans": [{…}, …],
            "node_class_map": {…},
        }

    Existing trace fields are preserved.  Unknown work goes to
    ``unattributed_ms`` — never invented savings.
    """
    # Collect data from cache if available
    cache_data: dict[str, Any] = {}
    if cache is not None:
        cache_data = cache.to_summary_dict()

    # Consume pre_sampler_* operation metadata from trace events
    trace_data = result.get("trace")
    trace_derived_ops: dict[str, float] = {}
    trace_derived_counts: dict[str, int] = {}
    trace_derived_hits: dict[str, int] = {}
    trace_derived_spans: list[dict] = []
    pre_sampler_stage_metadata: dict[str, Any] = {}
    if isinstance(trace_data, dict):
        events = trace_data.get("events", [])
        if isinstance(events, list):
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                if ev.get("name") == "pre_sampler_stages":
                    stage_meta = ev.get("metadata") or {}
                    if isinstance(stage_meta, dict):
                        pre_sampler_stage_metadata.update(stage_meta)
                meta = ev.get("metadata") or {}
                if not isinstance(meta, dict):
                    continue
                op = meta.get("operation", "")
                if not op:
                    continue
                dur = meta.get("duration_ms", 0)
                if isinstance(dur, (int, float)):
                    trace_derived_ops[op] = trace_derived_ops.get(op, 0.0) + dur
                    trace_derived_counts[op] = trace_derived_counts.get(op, 0) + 1
                    if meta.get("cache_hit"):
                        trace_derived_hits[op] = trace_derived_hits.get(op, 0) + 1
                    # Build dominant span from event metadata
                    span: dict[str, Any] = {
                        "operation": op,
                        "duration_ms": round(float(dur), 3),
                    }
                    for attr in (
                        "node_id", "class_type",
                        "start_node_id", "start_node_class_type",
                        "end_node_id", "end_node_class_type",
                        "cache_hit", "reused", "skipped",
                    ):
                        val = meta.get(attr)
                        if val is not None and val != "":
                            span[attr] = val
                    if span.get("node_id") or span.get("start_node_id") or span.get("end_node_id"):
                        trace_derived_spans.append(span)

        # Also check for pre_sampler_stages / milestone metadata
        stages = trace_data.get("stages", {})
        if isinstance(stages, dict):
            for stage_name, stage_val in stages.items():
                if not isinstance(stage_val, dict):
                    continue
                op = stage_val.get("operation", "")
                if op:
                    dur = stage_val.get("duration_ms", 0)
                    if isinstance(dur, (int, float)):
                        trace_derived_ops[op] = trace_derived_ops.get(op, 0.0) + dur
                        trace_derived_counts[op] = trace_derived_counts.get(op, 0) + 1

    def _workflow_class(node_id: Any) -> str:
        if node_id in (None, ""):
            return ""
        node_key = str(node_id)
        workflow = plan.workflow
        try:
            node = workflow.get(node_key, {}) if hasattr(workflow, "get") else {}
            if hasattr(node, "get"):
                return str(node.get("class_type", "") or "")
        except Exception:
            pass
        return ""

    def _append_milestone_span(
        name: str,
        duration_ms: Any,
        start_node_id: Any,
        end_node_id: Any,
        start_class_type: Any = "",
        end_class_type: Any = "",
    ) -> None:
        if not isinstance(duration_ms, (int, float)):
            return
        start_id = "" if start_node_id in (None, "") else str(start_node_id)
        end_id = "" if end_node_id in (None, "") else str(end_node_id)
        start_class = str(start_class_type or "") or _workflow_class(start_id)
        end_class = str(end_class_type or "") or _workflow_class(end_id)
        span: dict[str, Any] = {
            "span": name,
            "operation": "node_execution",
            "duration_ms": round(float(duration_ms), 3),
            "start_node_id": start_id or None,
            "start_node_class_type": start_class or None,
            "end_node_id": end_id or None,
            "end_node_class_type": end_class or None,
            "attribution_status": "exact"
            if start_id and end_id
            else "boundary_node_not_observed",
        }
        trace_derived_spans.append(span)

    if pre_sampler_stage_metadata:
        _append_milestone_span(
            "execution_start_to_cached",
            pre_sampler_stage_metadata.get("execution_start_to_cached_ms"),
            pre_sampler_stage_metadata.get("first_output_node_id")
            or pre_sampler_stage_metadata.get("first_executing_node_id"),
            pre_sampler_stage_metadata.get("cached_node_id"),
            pre_sampler_stage_metadata.get("first_output_class_type")
            or pre_sampler_stage_metadata.get("first_executing_node_class"),
            pre_sampler_stage_metadata.get("cached_node_class_type"),
        )
        _append_milestone_span(
            "cached_to_first_node",
            pre_sampler_stage_metadata.get("cached_to_first_node_ms"),
            pre_sampler_stage_metadata.get("cached_node_id"),
            pre_sampler_stage_metadata.get("first_executing_node_id"),
            pre_sampler_stage_metadata.get("cached_node_class_type"),
            pre_sampler_stage_metadata.get("first_executing_node_class"),
        )
        _append_milestone_span(
            "first_node_to_clip",
            pre_sampler_stage_metadata.get("first_node_to_clip_ms"),
            pre_sampler_stage_metadata.get("first_executing_node_id"),
            pre_sampler_stage_metadata.get("first_clip_encode_node_id"),
            pre_sampler_stage_metadata.get("first_executing_node_class"),
            pre_sampler_stage_metadata.get("first_clip_encode_node_class"),
        )
        _append_milestone_span(
            "clip_to_sampler_node",
            pre_sampler_stage_metadata.get("clip_to_sampler_node_ms"),
            pre_sampler_stage_metadata.get("first_clip_encode_node_id"),
            pre_sampler_stage_metadata.get("first_sampler_node_id"),
            pre_sampler_stage_metadata.get("first_clip_encode_node_class"),
            pre_sampler_stage_metadata.get("first_sampler_node_class"),
        )
        _append_milestone_span(
            "sampler_node_to_sampler_start",
            pre_sampler_stage_metadata.get("sampler_node_to_sampler_start_ms"),
            pre_sampler_stage_metadata.get("first_sampler_node_id"),
            pre_sampler_stage_metadata.get("sampler_stage_node_id"),
            pre_sampler_stage_metadata.get("first_sampler_node_class"),
            pre_sampler_stage_metadata.get("sampler_stage_node_class"),
        )

    # Try to derive total wall time from trace events or stages
    total_wall_ms: float | None = None
    if isinstance(trace_data, dict):
        stages = trace_data.get("stages", {})
        if isinstance(stages, dict) and stages:
            timestamps = [v for v in stages.values() if isinstance(v, (int, float))]
            if len(timestamps) >= 2:
                total_wall_ms = round(
                    (max(timestamps) - min(timestamps)) * 1000, 3
                )
        # Also check for events with wall_unix_ns
        events = trace_data.get("events", [])
        if isinstance(events, list) and len(events) >= 2:
            timestamps = [
                e.get("wall_unix_ns", 0) for e in events
                if isinstance(e, dict) and e.get("wall_unix_ns")
            ]
            if len(timestamps) >= 2:
                derived = (max(timestamps) - min(timestamps)) / 1_000_000
                if total_wall_ms is None or derived > total_wall_ms:
                    total_wall_ms = round(derived, 3)
    pre_sampler_total_ms = pre_sampler_stage_metadata.get("pre_sampler_total_ms")
    if isinstance(pre_sampler_total_ms, (int, float)):
        total_wall_ms = round(float(pre_sampler_total_ms), 3)

    # Build the summary dict
    summary: dict[str, Any] = {}

    # Required operation timing fields — cache data takes priority
    for field in _PRE_SAMPLER_REQUIRED_FIELDS:
        # First try cache data, then trace-derived data
        val = cache_data.get(field)
        if val is None:
            # Derive from trace-derived ops: field "cache_key_build_ms" → op "cache_key_build"
            op_name = field[:-3]  # strip "_ms"
            if op_name in trace_derived_ops:
                val = round(trace_derived_ops[op_name], 3)
        summary[field] = round(float(val or 0.0), 3)

    # Measured total (sum of all non-unattributed operations)
    measured = sum(
        summary.get(f, 0.0) for f in _PRE_SAMPLER_REQUIRED_FIELDS
        if f != "unattributed_ms"
    )
    unattributed = summary.get("unattributed_ms", 0.0)

    summary["total_measured_ms"] = round(measured, 3)

    if total_wall_ms is not None:
        summary["total_wall_ms"] = round(total_wall_ms, 3)
        # Residual = wall - measured - unattributed
        total_known = measured + unattributed
        # Never clamp away an overlap/error — report reconciliation status
        residual = total_wall_ms - total_known
        if residual != 0 or unattributed > 0:
            summary["residual_ms"] = round(residual, 3)
        if residual < 0:
            summary["reconciliation_status"] = "measured_exceeds_wall"
    elif unattributed > 0:
        summary["residual_ms"] = round(unattributed, 3)

    # Operation counts — merge cache + trace-derived
    counts = dict(cache_data.get("operation_counts", {}))
    for op_name, count in trace_derived_counts.items():
        counts[op_name] = max(counts.get(op_name, 0), count)
    if counts:
        summary["operation_counts"] = counts

    hits = dict(cache_data.get("operation_hits", {}))
    for op_name, count in trace_derived_hits.items():
        if count > 0:
            hits[op_name] = max(hits.get(op_name, 0), count)
    if hits:
        summary["operation_hits"] = hits

    # Dominant spans — cache spans first, then trace-derived (no duplicates)
    seen_spans: set[str] = set()
    all_spans: list[dict] = []
    for span in cache_data.get("dominant_spans", []):
        span_key = str(span)
        if span_key not in seen_spans:
            seen_spans.add(span_key)
            all_spans.append(span)
    for span in trace_derived_spans:
        span_key = str(span)
        if span_key not in seen_spans:
            seen_spans.add(span_key)
            all_spans.append(span)
    if all_spans:
        summary["dominant_spans"] = all_spans

    # Node class map from cache + workflow fallback + trace-derived
    node_map: dict[str, str] = {}
    cache_map = cache_data.get("node_class_map")
    if isinstance(cache_map, dict):
        node_map.update(cache_map)

    # Fall back to workflow for any missing nodes
    wf = plan.workflow
    if isinstance(wf, dict) or hasattr(wf, "items"):
        try:
            items = wf.items() if hasattr(wf, "items") else {}
        except Exception:
            items = {}
        for nid, node in items:
            if nid in node_map:
                continue
            ct = ""
            if isinstance(node, dict):
                ct = node.get("class_type", "")
            elif hasattr(node, "get"):
                try:
                    ct = node.get("class_type", "")
                except Exception:
                    ct = ""
            if ct:
                node_map[str(nid)] = str(ct)
    if node_map:
        summary["node_class_map"] = node_map

    if isinstance(pre_sampler_total_ms, (int, float)):
        summary["pre_sampler_total_ms"] = round(float(pre_sampler_total_ms), 3)

    # Attach to result
    if summary:
        if isinstance(trace_data, dict):
            trace_data["pre_sampler_critical_path"] = summary
            result["trace"] = trace_data
        else:
            result["pre_sampler_critical_path"] = summary

    return result


# ── Async helper ─────────────────────────────────────────────────────────

async def await_result(future: Awaitable[Any]) -> Any:
    """Await a single awaitable and return its result."""
    return await future


# ── Backend diagnostics (unchanged below) ────────────────────────────────

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

    def __post_init__(self) -> None:
        """Auto-create a request-scoped PreSamplerCache unless caller supplied one."""
        if "pre_sampler_cache" not in self.metadata:
            self.metadata["pre_sampler_cache"] = PreSamplerCache(trace=self.trace)


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
        cache: PreSamplerCache | None = ctx.metadata.get("pre_sampler_cache")
        if cache is not None:
            cache.build_cache_key(plan)
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
            # Attach pre-sampler critical path summary to result
            if cache is not None:
                attach_pre_sampler_critical_path(result, plan, cache)
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
        cache: PreSamplerCache | None = ctx.metadata.get("pre_sampler_cache")
        if cache is not None:
            cache.build_cache_key(plan)
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
                        # Attach critical path to result events before yielding
                        if cache is not None and event.get("type") == "result":
                            attach_pre_sampler_critical_path(event, plan, cache)
                        yield event
                return
            if hasattr(result, "__iter__") and not isinstance(result, (dict, str, bytes)):
                for event in result:
                    if ctx.cancelled and ctx.cancelled():
                        raise asyncio.CancelledError()
                    if isinstance(event, dict):
                        if ctx.progress and event.get("type") in {"progress", "status"}:
                            ctx.progress(event)
                        # Attach critical path to result events before yielding
                        if cache is not None and event.get("type") == "result":
                            attach_pre_sampler_critical_path(event, plan, cache)
                        yield event
                return
            payload = result if isinstance(result, dict) else {"result": result}
            payload.setdefault("backend", diagnostics.to_dict())
            if cache is not None:
                attach_pre_sampler_critical_path(payload, plan, cache)
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
