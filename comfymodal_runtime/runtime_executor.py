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

``PreSamplerInstrumentation`` — scoped live-instrumentation that hooks the
native ComfyUI ``execution.PromptExecutor``, ``execution.execute``,
``execution.get_input_data``, and ``comfy.model_management.load_models_gpu`` to
capture wall-clock timings from actual production execution boundaries.
Emits a single ``[v2.pre_sampler_critical_path]`` line per request.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import contextvars
import inspect
import os
import threading
import time

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping

from .contracts import ExecutionPlan, SnapshotExecutionSeed
from .trace import RuntimeTrace


# ── Pre-sampler cache / orchestration component ──────────────────────────

_PRE_SAMPLER_REQUIRED_OPERATIONS = (
    "cache_key_build", "cache_lookup", "input_resolution",
    "model_patch", "conditioning", "future_wait", "lock_wait",
    "node_execution", "unattributed",
)

# Sentinel to distinguish a cached None from a cache miss
_MISS_SENTINEL = object()


# ── SnapshotExecutionSeed identity validation (Step 3 consumer) ───────────
# Pure, deterministic, fail-closed: reuse of snapshot static structure is only
# ever enabled when workflow AND deployment identity positively match.  The
# seed itself contains only structural data (see contracts.SnapshotExecutionSeed);
# the consumer never stores outputs, tensors, request state, caches, random
# state, GPU handles, sampler outputs, or seed-dependent values.

_SEED_DECISION_NO_SEED = "no_seed"
_SEED_DECISION_MATCH = "match"
_SEED_DECISION_MISMATCH = "identity_mismatch"


def seed_identity_decision(
    seed: SnapshotExecutionSeed | Mapping[str, Any] | None,
    *,
    workflow_hash: str = "",
    source_workflow_hash: str = "",
    deployment_combined_hash: str = "",
    custom_node_generation: str = "",
) -> dict[str, Any]:
    """Deterministic, fail-closed identity validation for a snapshot seed.

    ``seed`` may be a ``SnapshotExecutionSeed``, a serializable mapping (v1 or
    v2 payload), or ``None``.  Returns a decision dict:

      status         — ``no_seed`` | ``match`` | ``identity_mismatch``
      reuse_enabled  — bool (True only for ``match``)
      reasons        — list[str] of every failed check (empty on match)
      seed_schema_version — int (0 when no seed)

    Reuse is enabled ONLY when every present identity check positively
    matches:

    * Workflow identity — the request's authoritative workflow hash (either
      ``workflow_hash`` or ``source_workflow_hash``) must equal one of the
      seed's recorded hashes.  A seed with no recorded hash, or a request
      with no hash, is unverifiable and therefore does NOT enable reuse.
    * Deployment identity — when the seed records a deployment hash, the
      request must supply an EQUAL deployment hash.  Missing request hash is
      fail-closed (unverifiable).
    * Custom-node generation — same rule as deployment identity.

    No exception is raised on mismatch; the caller decides how to surface it.
    """
    if seed is None:
        return {
            "status": _SEED_DECISION_NO_SEED,
            "reuse_enabled": False,
            "reasons": [],
            "seed_schema_version": 0,
        }
    if isinstance(seed, Mapping):
        seed = SnapshotExecutionSeed.from_dict(seed)
    if not isinstance(seed, SnapshotExecutionSeed):
        return {
            "status": _SEED_DECISION_MISMATCH,
            "reuse_enabled": False,
            "reasons": ["invalid_seed_type"],
            "seed_schema_version": 0,
        }

    reasons: list[str] = []

    # ── Workflow identity (positive match required for reuse) ──
    request_hashes = {h for h in (str(workflow_hash or ""), str(source_workflow_hash or "")) if h}
    seed_hashes = {
        h for h in (str(seed.workflow_hash or ""), str(seed.source_workflow_hash or "")) if h
    }
    if request_hashes and seed_hashes:
        if not request_hashes & seed_hashes:
            reasons.append("workflow_hash_mismatch")
    elif not seed_hashes:
        reasons.append("seed_workflow_hash_missing")
    elif not request_hashes:
        reasons.append("workflow_hash_unverifiable")

    # ── Deployment identity (fail-closed when unverifiable) ──
    seed_deployment = str(seed.deployment_combined_hash or "")
    if seed_deployment:
        if not deployment_combined_hash:
            reasons.append("deployment_hash_unverifiable")
        elif str(deployment_combined_hash) != seed_deployment:
            reasons.append("deployment_hash_mismatch")

    # ── Custom-node generation (fail-closed when unverifiable) ──
    seed_custom_node = str(seed.custom_node_generation or "")
    if seed_custom_node:
        if not custom_node_generation:
            reasons.append("custom_node_generation_unverifiable")
        elif str(custom_node_generation) != seed_custom_node:
            reasons.append("custom_node_generation_mismatch")

    status = _SEED_DECISION_MATCH if not reasons else _SEED_DECISION_MISMATCH
    return {
        "status": status,
        "reuse_enabled": status == _SEED_DECISION_MATCH,
        "reasons": reasons,
        "seed_schema_version": int(getattr(seed, "schema_version", 0) or 0),
    }


def seed_eligible_static_structure(
    seed: SnapshotExecutionSeed | None,
) -> dict[str, dict[str, Any]]:
    """Extract ONLY eligible loader/static structure from a seed for reuse.

    Returns ``{node_id: static_inputs}`` for nodes whose static inputs are
    recorded in ``static_node_signatures`` and that are NOT sampler nodes.
    Sampler nodes, sampler static inputs, dynamic inputs, and any output /
    conditioning / latent / request / cache / GPU data are NEVER returned.

    Callers MUST gate any actual reuse behind ``seed_identity_decision``
    returning ``reuse_enabled=True``.
    """
    if seed is None:
        return {}
    sampler_ids = set(seed.sampler_node_ids)
    eligible: dict[str, dict[str, Any]] = {}
    for entry in seed.static_node_signatures:
        if not isinstance(entry, Mapping):
            continue
        node_id = str(entry.get("node_id", ""))
        if not node_id or node_id in sampler_ids:
            continue
        static_inputs = entry.get("static_inputs")
        if isinstance(static_inputs, Mapping):
            eligible[node_id] = dict(static_inputs)
    return eligible


def _freeze_static_value(value: Any) -> Any:
    """Normalize a static input value for deterministic equality checks.

    Mapping keys are stringified; lists/tuples are converted to tuples so
    ComfyUI's ``["node", 0]`` link lists compare equal to recorded tuples.
    """
    if isinstance(value, Mapping):
        return tuple(
            sorted(
                (str(k), _freeze_static_value(v)) for k, v in value.items()
            )
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_static_value(v) for v in value)
    return value


def _static_inputs_match(recorded: Mapping[str, Any], supplied: Mapping[str, Any]) -> bool:
    """Exact-key-set + value equality between recorded and supplied static inputs."""
    if set(recorded.keys()) != set(supplied.keys()):
        return False
    for key, expected in recorded.items():
        if key not in supplied:
            return False
        if _freeze_static_value(expected) != _freeze_static_value(supplied[key]):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: executor-cache seed apply seam
# ═══════════════════════════════════════════════════════════════════════════

_SEED_APPLY_BUDGET_MS: float = 25.0


def _live_static_inputs(node_class: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Static signature of a live workflow node using the SAME conservative
    classifier as the pure seed builder.  Link edges and fixed loader
    filenames/options are static; seed, prompt text, strengths, dimensions,
    and unknown values are dynamic and never compared."""
    from .execution_seed import _classify_inputs

    static_inputs, _dynamic = _classify_inputs(str(node_class), inputs or {})
    return dict(static_inputs)


def _recorded_static_signatures(seed: SnapshotExecutionSeed) -> dict[str, dict[str, Any]]:
    """Map ``node_id -> {"node_class", "static_inputs", "hash"}`` from the seed."""
    recorded: dict[str, dict[str, Any]] = {}
    for entry in seed.static_node_signatures:
        if not isinstance(entry, Mapping):
            continue
        node_id = str(entry.get("node_id", ""))
        if not node_id:
            continue
        static_inputs = entry.get("static_inputs")
        recorded[node_id] = {
            "node_class": str(entry.get("node_class", "") or ""),
            "static_inputs": dict(static_inputs) if isinstance(static_inputs, Mapping) else {},
        }
    return recorded


async def apply_snapshot_seed_to_executor(
    executor: Any,
    seed: SnapshotExecutionSeed | Mapping[str, Any] | None,
    *,
    workflow: Mapping[str, Any] | None = None,
    workflow_hash: str = "",
    source_workflow_hash: str = "",
    deployment_combined_hash: str = "",
    custom_node_generation: str = "",
    trace: RuntimeTrace | None = None,
    budget_ms: float = _SEED_APPLY_BUDGET_MS,
) -> dict[str, Any]:
    """Verify and (on mismatch) invalidate seeded loader cache entries.

    Called ONLY from the existing ``seeded_set_prompt`` hook after
    ``original_set_prompt`` and after Step 1-2 loader seeding.  Fail-closed:
    any mismatch/error yields an honest fallback marker and execution
    continues unchanged.

    Rules (never violated):
      * Never inserts or replaces loader ``CacheEntry`` values — this seam
        only VERIFIES entries that Step 1-2 loader seeding already inserted
        and DELETES stale ones whose static signature differs.
      * Never touches sampler entries — sampler node ids are excluded by
        construction.
      * Never bypasses ComfyUI cache-key validation — deletions go through
        ``outputs_cache.delete`` using the same data key the cache owns.
      * Never reuses dynamic inputs/outputs — only structural/static
        signatures are compared.

    Emits ``snapshot_graph_seed_validate_start/end`` and
    ``snapshot_graph_seed_apply_start/end`` trace events plus a concise
    ``[v2.seed_apply]`` marker.  Measures only seed validation/application —
    never ``set_prompt`` or Step 1-2 loader seeding.
    """
    started = time.perf_counter()

    # ── Normalize seed (fail-closed on malformed payloads) ──
    normalized: SnapshotExecutionSeed | None = None
    if isinstance(seed, SnapshotExecutionSeed):
        normalized = seed
    elif isinstance(seed, Mapping):
        try:
            normalized = SnapshotExecutionSeed.from_dict(seed)
        except Exception:
            normalized = None

    caches = getattr(executor, "caches", None)
    outputs_cache = getattr(caches, "outputs", None) if caches is not None else None

    def _emit(name: str, **metadata: Any) -> None:
        if trace is not None:
            trace.emit(name, phase="execution", metadata=metadata)

    # ── Validate phase: identity + structural/static signature comparison ──
    _validate_started = time.perf_counter()
    _emit("snapshot_graph_seed_validate_start", budget_ms=budget_ms)
    decision = seed_identity_decision(
        normalized,
        workflow_hash=workflow_hash,
        source_workflow_hash=source_workflow_hash,
        deployment_combined_hash=deployment_combined_hash,
        custom_node_generation=custom_node_generation,
    )
    status = decision.get("status", "no_seed")
    reasons = list(decision.get("reasons", []) or [])
    schema = int(decision.get("seed_schema_version", 0) or 0)

    verified_pre = 0
    stale_candidates: list[str] = []
    observed_missing_in_workflow = 0
    non_loader_static_observed = 0
    sampler_node_count = 0

    if (
        status == "match"
        and normalized is not None
        and isinstance(workflow, Mapping)
        and workflow
    ):
        sampler_node_count = len(tuple(normalized.sampler_node_ids or ()))
        recorded = _recorded_static_signatures(normalized)
        workflow_map = {str(nid): node for nid, node in workflow.items()}
        loader_ids = tuple(str(i) for i in (normalized.loader_node_ids or ()))
        sampler_ids = frozenset(str(i) for i in (normalized.sampler_node_ids or ()))
        for entry in normalized.static_node_signatures:
            if not isinstance(entry, Mapping):
                continue
            node_id = str(entry.get("node_id", ""))
            if not node_id:
                continue
            if node_id in sampler_ids:
                continue  # sampler entries are observational-only and untouched
            rec = recorded.get(node_id)
            if rec is None:
                continue
            if node_id not in loader_ids:
                # Non-loader structure is observational only — never mutated.
                if rec.get("static_inputs"):
                    non_loader_static_observed += 1
                continue
            live_node = workflow_map.get(node_id)
            if not isinstance(live_node, Mapping):
                observed_missing_in_workflow += 1
                continue
            try:
                live_static = _live_static_inputs(
                    str(live_node.get("class_type", "")),
                    live_node.get("inputs", {}),
                )
            except Exception:
                stale_candidates.append(node_id)
                continue
            if _static_inputs_match(rec.get("static_inputs", {}), live_static):
                verified_pre += 1
            else:
                stale_candidates.append(node_id)

    validate_ms = (time.perf_counter() - _validate_started) * 1000.0

    # ── Fallback decision (honest, never silently "seeded") ──
    fallback_reason = "none"
    if status == "no_seed":
        fallback_reason = "no_seed"
    elif status == "identity_mismatch":
        fallback_reason = ",".join(reasons) if reasons else "identity_mismatch"
    elif status == "match" and not isinstance(workflow, Mapping):
        fallback_reason = "workflow_unavailable"
    elif status == "match" and outputs_cache is None:
        fallback_reason = "outputs_cache_unavailable"

    _emit(
        "snapshot_graph_seed_validate_end",
        decision=status,
        schema=schema,
        reasons=",".join(reasons),
        verified_pre=verified_pre,
        stale_candidates=",".join(stale_candidates) if stale_candidates else "",
        observed_missing_in_workflow=observed_missing_in_workflow,
        non_loader_static_observed=non_loader_static_observed,
        sampler_node_count=sampler_node_count,
    )

    # ── Apply phase: invalidate stale loader entries only ──
    _apply_started = time.perf_counter()
    _emit("snapshot_graph_seed_apply_start", decision=status, schema=schema)
    invalidated: list[str] = []
    invalidated_errors: list[str] = []
    if status == "match" and outputs_cache is not None:
        for node_id in stale_candidates:
            delete_fn = getattr(outputs_cache, "delete", None)
            if not callable(delete_fn):
                invalidated_errors.append(node_id)
                continue
            try:
                result = delete_fn(node_id)
                if inspect.isawaitable(result):
                    await result
                invalidated.append(node_id)
            except Exception:
                invalidated_errors.append(node_id)

    apply_ms = (time.perf_counter() - _apply_started) * 1000.0
    total_ms = (time.perf_counter() - started) * 1000.0
    within_budget = total_ms <= float(budget_ms)
    verified = verified_pre
    sampler_untouched = True

    marker = {
        "decision": status,
        "schema": schema,
        "validate_ms": round(validate_ms, 3),
        "apply_ms": round(apply_ms, 3),
        "total_ms": round(total_ms, 3),
        "budget_ms": float(budget_ms),
        "within_budget": within_budget,
        "verified": verified,
        "invalidated": len(invalidated),
        "invalidated_node_ids": ",".join(invalidated) if invalidated else "",
        "invalidated_errors": ",".join(invalidated_errors) if invalidated_errors else "",
        "sampler_untouched": sampler_untouched,
        "fallback_reason": fallback_reason,
    }

    _emit(
        "snapshot_graph_seed_apply_end",
        **marker,
    )
    print(
        f"[v2.seed_apply] decision={status} schema={schema} "
        f"validate_ms={marker['validate_ms']} apply_ms={marker['apply_ms']} "
        f"total_ms={marker['total_ms']} budget_ms={marker['budget_ms']} "
        f"within_budget={1 if within_budget else 0} verified={verified} "
        f"invalidated={len(invalidated)} sampler_untouched={1 if sampler_untouched else 0} "
        f"fallback_reason={fallback_reason}",
        flush=True,
    )
    return marker


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
        # Step 3 seed-consumer state (fail-closed; empty unless validated)
        "_seed_reuse_enabled", "_seed_static_structure",
        "_seed_sampler_node_ids", "_seed_decision",
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

        # Step 3 seed-consumer state — never enabled without identity match.
        self._seed_reuse_enabled: bool = False
        self._seed_static_structure: dict[str, dict[str, Any]] = {}
        self._seed_sampler_node_ids: frozenset[str] = frozenset()
        self._seed_decision: dict[str, Any] | None = None

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

    def consume_snapshot_seed(
        self,
        seed: SnapshotExecutionSeed | Mapping[str, Any] | None,
        *,
        workflow_hash: str = "",
        source_workflow_hash: str = "",
        deployment_combined_hash: str = "",
        custom_node_generation: str = "",
    ) -> dict[str, Any]:
        """Consume a snapshot execution seed at request start, fail-closed.

        Validates workflow AND deployment identity deterministically via
        :func:`seed_identity_decision`.  ONLY on a positive ``match`` is
        eligible loader/static structure retained for ``resolve_inputs``
        reuse.  Sampler node ids are recorded so sampler nodes are NEVER
        reused.  Sampler static inputs, outputs, conditioning, latents,
        request/cache/random state, and GPU handles are never stored.

        When no seed is supplied, the cache keeps its existing behavior
        (no reuse, no state) — fully compatible.

        Returns the decision dict (see ``seed_identity_decision``) and
        records it on ``seed_decision``.
        """
        normalized_seed: SnapshotExecutionSeed | None = None
        if isinstance(seed, Mapping):
            normalized_seed = SnapshotExecutionSeed.from_dict(seed)
        elif isinstance(seed, SnapshotExecutionSeed):
            normalized_seed = seed

        decision = seed_identity_decision(
            normalized_seed,
            workflow_hash=workflow_hash,
            source_workflow_hash=source_workflow_hash,
            deployment_combined_hash=deployment_combined_hash,
            custom_node_generation=custom_node_generation,
        )
        self._seed_decision = decision
        if not decision.get("reuse_enabled", False):
            # Fail-closed: no identity match → no reusable structure.
            self._seed_reuse_enabled = False
            self._seed_static_structure = {}
            self._seed_sampler_node_ids = frozenset()
            return decision

        eligible = seed_eligible_static_structure(normalized_seed)
        self._seed_reuse_enabled = True
        self._seed_static_structure = eligible
        if normalized_seed is None:
            # Unreachable: reuse_enabled=True implies a non-None validated seed.
            self._seed_sampler_node_ids = frozenset()
        else:
            self._seed_sampler_node_ids = frozenset(
                str(i) for i in normalized_seed.sampler_node_ids
            )
        return decision

    @property
    def seed_decision(self) -> dict[str, Any] | None:
        """Last snapshot-seed consumption decision, or ``None`` if never called."""
        if self._seed_decision is None:
            return None
        return dict(self._seed_decision)

    @property
    def seed_reuse_enabled(self) -> bool:
        """True only after a positively validated seed identity match."""
        return bool(self._seed_reuse_enabled)

    def reuse_seed_static_inputs(
        self,
        node_id: str,
        class_type: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return recorded seed static inputs for an eligible node, or ``None``.

        Reuse is gated on BOTH a validated seed match (``seed_reuse_enabled``)
        and the node being non-sampler static structure whose recorded static
        input key set exactly matches *inputs*.  Sampler nodes, nodes without
        a recorded static structure, and nodes with any extra/differing input
        keys return ``None`` (caller falls back to normal resolution).  This
        never serves sampler outputs or seed-dependent data.
        """
        if not self._seed_reuse_enabled:
            return None
        node_id = str(node_id)
        if node_id in self._seed_sampler_node_ids:
            return None
        recorded = self._seed_static_structure.get(node_id)
        if recorded is None:
            return None
        if not _static_inputs_match(recorded, inputs):
            return None
        return dict(recorded)

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

        When a validated snapshot seed is present, eligible non-sampler
        loader/static nodes whose static inputs exactly match are returned
        directly from the recorded seed structure (a ``reused`` cache hit)
        without invoking the builder.

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

        # Step 3 seed reuse: eligible non-sampler static structure only.
        seed_static = self.reuse_seed_static_inputs(node_id, class_type, inputs)
        if seed_static is not None:
            self._node_input_cache[fp] = seed_static
            self._record_operation(
                "cache_lookup", lookup_elapsed,
                node_id=node_id, class_type=class_type,
                cache_hit=True, reused=True,
            )
            return seed_static

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
    # Fix 3: detect authoritative sampling_start event boundary
    _found_sampling_start_ns: int | None = None
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
                # Fix 3: detect authoritative sampling_start event
                if _found_sampling_start_ns is None and ev.get("name") == "sampling_start":
                    _found_sampling_start_ns = ev.get("monotonic_ns")

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

    def _attribution_from_cache(span_name: str, span_duration_ms: float) -> dict[str, Any]:
        """Build attribution sub-fields from cache operation timings.

        Maps milestone span names to the cache operations that would
        logically contribute to each span's wall-clock time.  Values
        come from cache_data since that is the authoritative source
        (cache data takes priority over trace-derived data).
        Returns a dict of attribution fields or empty dict when cache
        data is unavailable.
        """
        if not cache_data:
            return {}
        _attr: dict[str, Any] = {}
        if span_name == "execution_start_to_cached":
            _ckb = cache_data.get("cache_key_build_ms", 0.0)
            _cl = cache_data.get("cache_lookup_ms", 0.0)
            _hash_or_check = _ckb + _cl
            if _hash_or_check > 0:
                _attr["hash_or_cache_check_ms"] = round(_hash_or_check, 3)
        elif span_name == "cached_to_first_node":
            _fw = cache_data.get("future_wait_ms", 0.0)
            _lw = cache_data.get("lock_wait_ms", 0.0)
            _mp = cache_data.get("model_patch_ms", 0.0)
            _ne = cache_data.get("node_execution_ms", 0.0)
            _ir = cache_data.get("input_resolution_ms", 0.0)
            if _fw > 0:
                _attr["future_wait_ms"] = round(_fw, 3)
            if _lw > 0:
                _attr["lock_wait_ms"] = round(_lw, 3)
            if _mp > 0:
                _attr["model_patch_ms"] = round(_mp, 3)
            if _ne > 0:
                _attr["node_execution_ms"] = round(_ne, 3)
            if _ir > 0:
                _attr["input_resolution_ms"] = round(_ir, 3)
        elif span_name in ("first_node_to_clip", "clip_to_sampler_node"):
            _ne = cache_data.get("node_execution_ms", 0.0)
            _co = cache_data.get("conditioning_ms", 0.0)
            if _ne > 0:
                _attr["node_execution_ms"] = round(_ne, 3)
            if _co > 0:
                _attr["conditioning_ms"] = round(_co, 3)
        # Fix 3: sampler_node_to_sampler_start case removed — not derived from
        # progress.  Authoritative sampling_start from the SAMPLER_SAMPLE
        # wrapper is the true end boundary for pre-sampler timing.

        # Common attribution: cache hit, model cache hit, background future
        _hits = cache_data.get("operation_hits", {})
        if _hits.get("cache_lookup", 0) > 0:
            _attr["cache_hit"] = True
        if _hits.get("model_patch", 0) > 0:
            _attr["model_cache_hit"] = True
        _future_hit = _hits.get("future_wait", 0) > 0
        _future_total = cache_data.get("operation_counts", {}).get("future_wait", 0)
        _future_exists = _future_total > 0
        _attr["background_future_exists"] = _future_exists
        _attr["background_future_done"] = _future_hit and _future_exists
        _un = cache_data.get("unattributed_ms", 0.0)
        if _un > 0:
            _attr["unattributed_ms"] = round(_un, 3)

        # Outlier overlap explanation: if the sum of attributed operations
        # is much less (or more) than the milestone wall duration, and
        # background futures exist, the gap is likely overlapping wait.
        _attributed_causes = sum(
            v for k, v in _attr.items()
            if k.endswith("_ms") and isinstance(v, (int, float))
        )
        if _attributed_causes > 0:
            _gap = span_duration_ms - _attributed_causes
            if abs(_gap) > span_duration_ms * 0.2 and _future_exists:
                _attr["overlap_expectation"] = (
                    "background_future_wait_overlaps_independent_work"
                    if _gap > 0
                    else "background_future_wait_inside_milestone"
                )
            elif abs(_gap) > span_duration_ms * 0.2:
                _attr["overlap_expectation"] = "independent_work"
        return _attr

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
        _dur = float(duration_ms)
        start_id = "" if start_node_id in (None, "") else str(start_node_id)
        end_id = "" if end_node_id in (None, "") else str(end_node_id)
        start_class = str(start_class_type or "") or _workflow_class(start_id)
        end_class = str(end_class_type or "") or _workflow_class(end_id)
        span: dict[str, Any] = {
            "span": name,
            "operation": "node_execution",
            "duration_ms": round(_dur, 3),
            "start_node_id": start_id or None,
            "start_node_class_type": start_class or None,
            "end_node_id": end_id or None,
            "end_node_class_type": end_class or None,
            "attribution_status": "exact"
            if start_id and end_id
            else "boundary_node_not_observed",
        }
        # Enrich with cache-derived attribution
        _attribution = _attribution_from_cache(name, _dur)
        if _attribution:
            span["attribution"] = _attribution
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
        # Fix 3: sampler_node_to_sampler_start milestone removed — the
        # authoritative sampling_start from the SAMPLER_SAMPLE wrapper is
        # the true pre-sampler end boundary and is resolved below.

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

    # Fix 3: mark whether authoritative sampling_start was observed
    if _found_sampling_start_ns is not None:
        summary["sampling_start_authoritative"] = True

    # Merge structured report data from live instrumentation
    structured = result.get("pre_sampler_structured_report")
    if isinstance(structured, dict):
        for _field in (
            "per_node_timings", "clip_text_encode_nodes",
            "clip_raw_encode_ms", "clip_raw_encode_calls",
            "load_model_calls", "slowest_pre_sampler_nodes",
        ):
            _val = structured.get(_field)
            if _val is not None:
                summary[_field] = _val
        # Propagate clipped node ids for diagnostics
        _clipped = structured.get("_clipped_node_ids")
        if _clipped:
            summary["_clipped_node_ids"] = list(_clipped)

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


# ═══════════════════════════════════════════════════════════════════════
# Pre-sampler live instrumentation
# ═══════════════════════════════════════════════════════════════════════
# Monkeys the actual ComfyUI execution functions with timed wrappers.
# Scope: per-request via contextvars.  Emits exactly one summary line.

_PRE_SAMPLER_ABSENT_STR: str = "absent"

# Per-request state
_instrumentation_var: contextvars.ContextVar[
    dict[str, Any] | None
] = contextvars.ContextVar("pre_sampler_instrumentation", default=None)

# Bridge for sampler lane lock wait time from modal_app
_lock_wait_bridge: contextvars.ContextVar[float] = contextvars.ContextVar(
    "pre_sampler_lock_wait_bridge", default=0.0
)

# Authoritative sampling_start perf_counter_ns cutoff.
# Set by _build_sampling_wrapper when sampling_start fires;
# consumed by _patched_exec_node to clip node-wall at the boundary.
_sampling_cutoff_perf_ns: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "sampling_cutoff_perf_ns", default=None
)

# Current node context for nested load_models_gpu attribution.
# Set by _patched_exec_node during node execution; consumed by
# _patched_load_models_gpu and _patched_encode_from_tokens to
# record which node triggered the load/encode operation.
_current_node_context: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "current_node_context", default=None
)

# Set to True while inside CLIP.encode_from_tokens so nested
# load_models_gpu calls can construct an accurate call_path.
_encode_from_tokens_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "encode_from_tokens_active", default=False
)

# Originals saved once by install_hooks()
_ORIGINAL_FUNCTIONS: dict[str, Any] = {}
_hooks_installed: bool = False


def _inst_state() -> dict[str, Any] | None:
    return _instrumentation_var.get()


def _get_class_type(node_id: str, prompt: dict[str, Any]) -> str:
    """Look up class_type from the live prompt dict."""
    node = prompt.get(node_id) or prompt.get(str(node_id))
    if isinstance(node, dict):
        return str(node.get("class_type", ""))
    return ""


def _ns_ms(ns_start: int) -> float:
    """Convert perf_counter ns delta since *ns_start* to ms.

    Uses ``time.perf_counter_ns()`` instead of ``time.monotonic_ns()``
    because ``monotonic_ns`` on Windows can have ~15.6 ms resolution
    (``GetTickCount64``), which makes sub-ms measurements unreliable.
    ``perf_counter_ns`` uses ``QueryPerformanceCounter`` and has
    microsecond-resolution timing on all platforms.
    """
    return round((time.perf_counter_ns() - ns_start) / 1_000_000, 3)


def _fmt_or_absent(v: Any) -> str:
    if v is None:
        return _PRE_SAMPLER_ABSENT_STR
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _model_role_from_patcher(model: Any) -> str:
    """Classify a model's role as CLIP, UNET, VAE, or other.

    Uses strong object evidence in order:
    1. ``model.is_clip`` attribute (set by CLIP.__init__ on ModelPatcher)
    2. Inner ``model.model.forward_module`` shape (VAE autoencoder, UNET diffusion)
    3. ``model.model_type`` attribute (ComfyUI's standard role)
    4. Inner ``model.model`` class name and model_type
    5. Fallback class name heuristics

    ``model_type='Model'`` is classified as ``other`` (not UNET).
    Returns ``"other"`` when none provides a clear signal.  Never raises.
    """
    # 1. Strongest: is_clip attribute (set by CLIP.__init__ on ModelPatcher)
    try:
        if getattr(model, "is_clip", False) is True:
            return "CLIP"
    except Exception:
        pass
    # 2. Check inner model forward_module for VAE/UNET shape
    try:
        inner = getattr(model, "model", None)
        if inner is not None and inner is not model:
            fwd = getattr(inner, "forward_module", None)
            if fwd is not None:
                fwd_name = fwd.__class__.__name__.lower()
                if "autoencoder" in fwd_name or "vae" in fwd_name:
                    return "VAE"
                if "dit" in fwd_name or "diffusion" in fwd_name or "unet" in fwd_name:
                    return "UNET"
    except Exception:
        pass
    # 3. Check model_type on patcher
    try:
        mt = getattr(model, "model_type", None)
        if mt is not None:
            mt_str = str(mt).lower()
            if "clip" in mt_str:
                return "CLIP"
            if mt_str == "model":
                return "other"
            if "unet" in mt_str or "diffusion" in mt_str:
                return "UNET"
            if "vae" in mt_str or "autoencoder" in mt_str:
                return "VAE"
    except Exception:
        pass
    # 4. Check inner model attributes
    try:
        inner = getattr(model, "model", None)
        if inner is not None and inner is not model:
            mt = getattr(inner, "model_type", None)
            if mt is not None:
                mt_str = str(mt).lower()
                if "clip" in mt_str:
                    return "CLIP"
                if "vae" in mt_str or "autoencoder" in mt_str:
                    return "VAE"
                if mt_str == "model":
                    return "other"
                if "unet" in mt_str or "diffusion" in mt_str:
                    return "UNET"
            inner_name = inner.__class__.__name__.lower()
            if "autoencoder" in inner_name or "vae" in inner_name:
                return "VAE"
            if "dit" in inner_name or "diffusion" in inner_name or "unet" in inner_name:
                return "UNET"
    except Exception:
        pass
    # 5. Fallback: class name on patcher itself
    try:
        name = model.__class__.__name__.lower()
        if "clip" in name:
            return "CLIP"
        if "unet" in name or "diffusion" in name:
            return "UNET"
        if "vae" in name:
            return "VAE"
    except Exception:
        pass
    return "other"


# ── CPU-owner attribution infrastructure ──────────────────────────────
# Native thread count reading (/proc first, psutil fallback)
# Per-operation _CpuTimer context manager with peak-thread sampler
# [v2.cpu_owner] line emission and cutoff signaling


def _read_native_thread_count() -> int:
    """Read native thread count from /proc/self/task first; fallback psutil.

    ``/proc/self/task`` is a directory on Linux with one entry per thread.
    On platforms without ``/proc`` (Windows, macOS), falls back to
    ``psutil.Process().num_threads()``.  Returns 0 if both mechanisms fail.
    """
    try:
        task_entries = os.listdir("/proc/self/task")
        if task_entries:
            return len(task_entries)
    except (FileNotFoundError, PermissionError, OSError):
        pass
    try:
        import psutil as _psutil
        return _psutil.Process().num_threads()
    except (ImportError, Exception):
        pass
    return 0


class _PeakThreadSampler:
    """Samples native thread count every 10ms during a timed operation.

    Stores the peak observed count.  The sampler thread is daemon so it
    never blocks process exit.  Always call ``stop()`` in a ``finally``
    block to join the sampler thread.
    """

    __slots__ = ("_peak", "_stop_event", "_thread")

    def __init__(self) -> None:
        self._peak: int = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, initial: int) -> None:
        """Start the sampler with *initial* as the baseline peak."""
        self._peak = initial
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> int:
        """Signal stop and join the sampler thread.  Returns peak."""
        if self._thread is not None and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        return self._peak

    def _sample(self) -> None:
        while not self._stop_event.is_set():
            count = _read_native_thread_count()
            if count > self._peak:
                self._peak = count
            self._stop_event.wait(0.01)


# Active CPU timers registry for cutoff signaling from _build_sampling_wrapper
_active_cpu_timers: list["_CpuTimer"] = []
_active_cpu_timers_lock = threading.Lock()


class _CpuTimer:
    """Context manager for per-operation CPU-owner attribution.

    Records wall time (``perf_counter_ns``), process CPU time
    (``process_time_ns``), and native thread count.  Starts a
    ``_PeakThreadSampler`` for peak thread tracking.

    On exit, emits exactly one ``[v2.cpu_owner]`` parseable line and
    appends the data dict to ``_cpu_owner_records`` in instrumentation
    state (if active).

    Handles the ``sampling_start`` cutoff:
    * ``signal_cutoff()`` (called from ``_build_sampling_wrapper``)
      freezes intermediate measurements at the cutoff boundary.
    * If the operation started **after** the cutoff, no line is emitted.
    * If the cutoff fires mid-operation, wall/CPU/thread measurements
      are clipped to the signal time rather than the exit time.
    """

    __slots__ = (
        "operation", "role",
        "_wall_start", "_cpu_start", "_threads_start",
        "_peak_sampler", "_lock",
        "_cutoff_ns", "_cutoff_wall", "_cutoff_cpu", "_cutoff_threads",
    )

    def __init__(self, operation: str, role: str) -> None:
        self.operation = operation
        self.role = role
        self._wall_start: int = 0
        self._cpu_start: int = 0
        self._threads_start: int = 0
        self._peak_sampler = _PeakThreadSampler()
        self._lock = threading.Lock()
        self._cutoff_ns: int | None = None
        self._cutoff_wall: int = 0
        self._cutoff_cpu: int = 0
        self._cutoff_threads: int = 0

    def __enter__(self) -> "_CpuTimer":
        self._wall_start = time.perf_counter_ns()
        self._cpu_start = time.process_time_ns()
        self._threads_start = _read_native_thread_count()
        self._peak_sampler.start(self._threads_start)
        with _active_cpu_timers_lock:
            _active_cpu_timers.append(self)
        return self

    def signal_cutoff(self, cutoff_ns: int) -> None:
        """Record intermediate measurements at the sampling_start boundary.

        Called from ``_build_sampling_wrapper`` the instant the first
        ``sampling_start`` event fires.  These measurements replace the
        ``__exit__`` readings so no post-cutoff time leaks in.
        Only the first call has effect (subsequent signals are no-ops).
        """
        with self._lock:
            if self._cutoff_ns is None:
                self._cutoff_ns = cutoff_ns
                self._cutoff_wall = time.perf_counter_ns()
                self._cutoff_cpu = time.process_time_ns()
                self._cutoff_threads = _read_native_thread_count()

    def __exit__(self, *args: Any) -> None:
        # 1. Freeze peak (stop sampler first so no more samples arrive).
        #    Use try/finally so unregister happens even if stop() raises.
        try:
            peak = self._peak_sampler.stop()
        except Exception:
            peak = 0

        # 2. Unregister from active timers (prevents late signal_cutoff).
        #    Always runs, even if stop() raised above.
        with _active_cpu_timers_lock:
            try:
                _active_cpu_timers.remove(self)
            except ValueError:
                pass

        # 3. Read cutoff data under lock
        with self._lock:
            _cutoff = self._cutoff_ns
            if _cutoff is not None:
                wall_end_ns = self._cutoff_wall
                cpu_end_ns = self._cutoff_cpu
                threads_end = self._cutoff_threads
            else:
                wall_end_ns = time.perf_counter_ns()
                cpu_end_ns = time.process_time_ns()
                threads_end = _read_native_thread_count()

        # 4. If operation started after cutoff, emit nothing.
        #    Check both the explicit signal (mid-op cutoff) and the contextvar
        #    (cutoff was set before this operation started — no signal sent).
        if _cutoff is not None and _cutoff <= self._wall_start:
            return
        if _cutoff is None:
            _ctx_cutoff = _sampling_cutoff_perf_ns.get()
            if _ctx_cutoff is not None and _ctx_cutoff <= self._wall_start:
                return

        wall_ms = (wall_end_ns - self._wall_start) / 1_000_000
        if wall_ms <= 0:
            return

        process_cpu_ms = (cpu_end_ns - self._cpu_start) / 1_000_000
        effective_cores = process_cpu_ms / wall_ms if wall_ms > 0 else 0.0

        data: dict[str, Any] = {
            "operation": self.operation,
            "role": self.role,
            "wall_ms": round(wall_ms, 3),
            "process_cpu_ms": round(process_cpu_ms, 3),
            "effective_cores": round(effective_cores, 3),
            "native_threads_start": self._threads_start,
            "native_threads_peak": peak,
            "native_threads_end": threads_end,
        }

        # 5. Store in instrumentation state for structured report
        _state = _instrumentation_var.get()
        if _state is not None:
            _state.setdefault("_cpu_owner_records", []).append(data)

        # 6. Emit parseable line
        _emit_cpu_owner_line(data)


def _emit_cpu_owner_line(data: dict[str, Any]) -> None:
    """Emit exactly one ``[v2.cpu_owner]`` parseable line."""
    parts = ["[v2.cpu_owner]"]
    fields = (
        "operation", "role", "wall_ms", "process_cpu_ms",
        "effective_cores", "native_threads_start",
        "native_threads_peak", "native_threads_end",
    )
    for f in fields:
        parts.append(f"{f}={_fmt_or_absent(data.get(f))}")
    print(" ".join(parts), flush=True)


def _signal_cpu_timers(cutoff_ns: int) -> None:
    """Signal all active CPU timers that sampling_start has fired."""
    with _active_cpu_timers_lock:
        timers = list(_active_cpu_timers)
    for t in timers:
        t.signal_cutoff(cutoff_ns)


def set_lock_wait_ms(ms: float) -> None:
    """Bridge the sampler lane lock wait duration into instrumentation state.

    Called by ``modal_app._execute_v2_prompt_executor`` after acquiring
    the mutation lane for a sampler node.  The value is consumed by
    ``_pop_lock_wait_ms`` during summary aggregation in the patched
    ``execute_async`` wrapper.
    """
    _lock_wait_bridge.set(ms)


def _pop_lock_wait_ms(state: dict[str, Any]) -> None:
    """Consume the bridged lock_wait_ms value into *state*.

    Called once per request in the patched ``execute_async`` finally
    block.  Resets the bridge to 0.0 to prevent cross-request carryover.
    """
    lw = _lock_wait_bridge.get()
    if lw > 0:
        state["lock_wait_ms"] = state.get("lock_wait_ms", 0.0) + lw
        state.setdefault("_lw_count", 0)
        state["_lw_count"] += 1
        _lock_wait_bridge.set(0.0)


def _attach_structured_report(result: dict[str, Any], state: dict[str, Any]) -> None:
    """Attach structured pre-sampler report fields from instrumentation *state*
    onto *result* for consumption by ``attach_pre_sampler_critical_path``.

    Adds the following keys to ``result["pre_sampler_structured_report"]``:

    * ``per_node_timings`` — every pre-sampler node with ``node_id``,
      ``class_type``, ``duration_ms``
    * ``clip_text_encode_nodes`` — complete wall time per CLIPTextEncode node
    * ``clip_raw_encode_ms`` — aggregate underlying ``CLIP.encode_from_tokens``
      wall time
    * ``clip_raw_encode_calls`` — per-call breakdown
    * ``load_model_calls`` — each ``load_models_gpu`` invocation with
      ``duration_ms``, ``model_count``, ``roles`` (CLIP/UNET/VAE/other)
    * ``slowest_pre_sampler_nodes`` — up to five slowest pre-sampler node
      entries (clipped at ``_sampling_cutoff_perf_ns``)
    * ``_clipped_node_ids`` — nodes whose measurement was truncated by the
      sampling-start cutoff
    * ``pre_sampler_total_ms`` — authoritative pre-sampler wall window
      (clipped at sampling_start when available)
    * ``non_overlapping_measured_total`` — ``node_execution_ms + future_wait_ms``
      (excludes nested diagnostics: input_resolution, model_patch,
      lock_wait, conditioning, clip_raw_encode).
      Always satisfies ``non_overlapping_measured_total <= pre_sampler_total_ms``.

    All fields are additive — existing keys on *result* are preserved.
    """
    structured: dict[str, Any] = {}

    node_timings = state.get("_pre_sampler_node_timings", [])
    if node_timings:
        structured["per_node_timings"] = list(node_timings)

    clip_nodes = state.get("_clip_text_encode_nodes", [])
    if clip_nodes:
        structured["clip_text_encode_nodes"] = list(clip_nodes)

    clip_raw_ms = state.get("_clip_raw_encode_ms", 0.0)
    if clip_raw_ms > 0:
        structured["clip_raw_encode_ms"] = round(clip_raw_ms, 3)

    clip_calls = state.get("_clip_raw_encode_calls", [])
    if clip_calls:
        structured["clip_raw_encode_calls"] = list(clip_calls)

    load_calls = state.get("_load_model_calls", [])
    if load_calls:
        structured["load_model_calls"] = list(load_calls)

    if node_timings:
        # Top 5 by duration_ms (pre-sampler only already — already clipped)
        sorted_nodes = sorted(
            node_timings, key=lambda n: n["duration_ms"], reverse=True
        )
        structured["slowest_pre_sampler_nodes"] = sorted_nodes[:5]

    clipped_ids = state.get("_clipped_node_ids", [])
    if clipped_ids:
        structured["_clipped_node_ids"] = list(clipped_ids)

    # Authoritative pre-sampler total and non-overlapping measured total.
    # These invariant fields allow consumers to verify
    # non_overlapping_measured_total <= pre_sampler_total_ms.
    _pre_total = state.get("pre_sampler_total_ms")
    if _pre_total is not None:
        structured["pre_sampler_total_ms"] = round(float(_pre_total), 3)
    _no_total = state.get("non_overlapping_measured_total")
    if _no_total is not None:
        structured["non_overlapping_measured_total"] = round(float(_no_total), 3)

    # CPU-owner attribution records (diagnostic, not part of measured-total)
    cpu_records = state.get("_cpu_owner_records", [])
    if cpu_records:
        structured["cpu_owner_records"] = list(cpu_records)

    # Always set the key so consumers can reliably detect its presence.
    # When empty, it indicates no live instrumentation data was collected.
    result["pre_sampler_structured_report"] = structured


def _emit_pre_sampler_line(state: dict[str, Any]) -> None:
    """Print exactly one [v2.pre_sampler_critical_path] summary line.

    Uses the per-request aggregated state dict.
    """
    parts = ["[v2.pre_sampler_critical_path]"]
    fields = (
        "span", "start_node_id", "start_class_type",
        "end_node_id", "end_class_type",
        "cache_lookup_ms", "pre_sampler_unattributed_ms",
        "input_resolution_ms", "future_wait_ms", "lock_wait_ms",
        "model_patch_ms", "conditioning_ms", "node_execution_ms",
        "unattributed_ms", "background_future_exists",
        "background_future_done", "model_cache_hit",
    )
    for f in fields:
        parts.append(f"{f}={_fmt_or_absent(state.get(f))}")
    print(" ".join(parts), flush=True)


def install_pre_sampler_hooks() -> None:
    """Patch native ComfyUI execution functions with timed wrappers.

    Safe to call multiple times — originals are stored on first call.
    Each wrapper checks the per-request context variable; when unset
    the original function is called with zero overhead.
    """
    global _hooks_installed
    if _hooks_installed:
        return

    try:
        import execution as _execution
        import comfy.model_management as _mm
    except ImportError:
        # ComfyUI modules not available (e.g. test environment) —
        # skip hook installation.  The contextvar gating ensures
        # no overhead when hooks are absent.
        return

    # Track whether any execution-module hooks were installed
    _installed_execution_hooks = False

    # ── 1. execution.get_input_data ────────────────────────────────────
    _orig_get_input_data = getattr(_execution, "get_input_data", None)
    if _orig_get_input_data is not None:
        _ORIGINAL_FUNCTIONS["get_input_data"] = _orig_get_input_data
        _installed_execution_hooks = True

        def _patched_get_input_data(*args: Any, **kwargs: Any) -> Any:
            state = _instrumentation_var.get()
            if state is None:
                return _orig_get_input_data(*args, **kwargs)
            _t0 = time.perf_counter_ns()
            try:
                return _orig_get_input_data(*args, **kwargs)
            finally:
                _elapsed = _ns_ms(_t0)
                if state is not None:
                    state["input_resolution_ms"] = state.get("input_resolution_ms", 0.0) + _elapsed
                    state.setdefault("_ir_count", 0)
                    state["_ir_count"] += 1

        _execution.get_input_data = _patched_get_input_data

    # ── 2. execution.execute (per-node) ────────────────────────────────
    _orig_exec_node = getattr(_execution, "execute", None)
    if _orig_exec_node is not None:
        _ORIGINAL_FUNCTIONS["execute"] = _orig_exec_node
        _installed_execution_hooks = True

        async def _patched_exec_node(*args: Any, **kwargs: Any) -> Any:
            state = _instrumentation_var.get()
            if state is None:
                return await _orig_exec_node(*args, **kwargs)

            # Extract needed arguments for classification (indices match excution.py signature:
            # server, dynprompt, caches, current_item, extra_data, executed, prompt_id, ...)
            _server = args[0] if len(args) > 0 else kwargs.get("server")
            _dynprompt = args[1] if len(args) > 1 else kwargs.get("dynprompt")
            _current_item = args[3] if len(args) > 3 else kwargs.get("current_item")
            _extra_data = args[4] if len(args) > 4 else kwargs.get("extra_data")
            _prompt_id = args[6] if len(args) > 6 else kwargs.get("prompt_id")

            # Resolve node identity — fall back to state prompt when dynprompt
            # is unavailable (e.g. test or simplified execution paths).
            node_class = ""
            node_id = str(_current_item) if _current_item is not None else ""
            try:
                if _dynprompt is not None:
                    node_info = _dynprompt.get_node(_current_item)
                    if isinstance(node_info, dict):
                        node_class = str(node_info.get("class_type", "") or "")
            except Exception:
                pass
            if not node_class:
                # Fallback: look up class_type from the stored prompt dict
                _prompt = state.get("_prompt", {})
                _entry = _prompt.get(node_id) or _prompt.get(str(_current_item))
                if isinstance(_entry, dict):
                    node_class = str(_entry.get("class_type", "") or "")

            # Classify node type for phase tracking
            _class_lower = node_class.lower()
            _is_clip_text_encode = "cliptextencode" in _class_lower or "textencode" in _class_lower
            _is_sampler = "sampler" in _class_lower or "ksampler" in _class_lower
            _is_model_loader = (
                not _is_clip_text_encode
                and not _is_sampler
                and ("loader" in _class_lower or "checkpoint" in _class_lower)
            )

            # Set current node context for nested load_models_gpu attribution
            _ctx_token = _current_node_context.set((node_id, node_class))
            _encode_ctx_token = _encode_from_tokens_active.set(False)

            # Capture node-entry perf counter before span boundary recording
            _t0 = time.perf_counter_ns()

            # Record span boundaries for dominant intervals
            if "first_node_id" not in state:
                state["first_node_id"] = node_id
                state["first_class_type"] = node_class
                state["first_node_enter_perf_ns"] = _t0
                state["span"] = "node_execution"
            state["last_node_id"] = node_id
            state["last_class_type"] = node_class

            # CPU timer for CLIPTextEncode nodes only (exact operation name)
            _cpu_node_timer: _CpuTimer | None = None
            if _is_clip_text_encode:
                _cpu_node_timer = _CpuTimer("CLIPTextEncode", "CLIP")
                _cpu_node_timer.__enter__()

            try:
                return await _orig_exec_node(*args, **kwargs)
            finally:
                if _cpu_node_timer is not None:
                    _cpu_node_timer.__exit__()
                _elapsed = _ns_ms(_t0)
                _current_node_context.reset(_ctx_token)
                _encode_from_tokens_active.reset(_encode_ctx_token)

                # ── Hard cutoff at authoritative sampling_start ──────────────
                cutoff_ns = _sampling_cutoff_perf_ns.get()
                if cutoff_ns is not None:
                    if cutoff_ns > _t0:
                        # Clip: node contribution stops at sampling_start
                        _clipped_elapsed = round(
                            (cutoff_ns - _t0) / 1_000_000, 3
                        )
                        _clipped = _elapsed - _clipped_elapsed > 0.001
                        _elapsed = _clipped_elapsed
                    else:
                        # Node started after sampling already began — skip
                        _elapsed = 0.0
                        _clipped = False
                else:
                    _clipped = False

                if _elapsed > 0:
                    state["node_execution_ms"] = state.get("node_execution_ms", 0.0) + _elapsed
                    state.setdefault("_ne_count", 0)
                    state["_ne_count"] += 1

                    # Per-node timing list for structured report
                    state.setdefault("_pre_sampler_node_timings", []).append({
                        "node_id": node_id,
                        "class_type": node_class,
                        "duration_ms": round(_elapsed, 3),
                    })

                    # Record as clipped when the measurement was truncated
                    if _clipped:
                        state.setdefault("_clipped_node_ids", []).append(node_id)

                    # Conditioning sub-tracking
                    if _is_clip_text_encode:
                        state["conditioning_ms"] = state.get("conditioning_ms", 0.0) + _elapsed
                        state.setdefault("_clip_text_encode_nodes", []).append({
                            "node_id": node_id,
                            "duration_ms": round(_elapsed, 3),
                        })

                # Sampler node-entry tracking (perf_counter, NOT actual sampler start)
                if _is_sampler and "sampler_node_enter_perf_ns" not in state:
                    state["sampler_node_enter_perf_ns"] = _t0
                    state["sampler_node_id"] = node_id
                    state["sampler_class_type"] = node_class

                # Model loader tracking (first occurrence)
                if _is_model_loader and "model_load_ns" not in state:
                    state["model_load_ns"] = _t0

        _execution.execute = _patched_exec_node

    # ── 3. comfy.model_management.load_models_gpu ──────────────────────
    # Patched with _CpuTimer for CPU-owner attribution, role classification,
    # and hard cutoff support.  Keep in sync with model_preload.py's
    # _make_gpu_loader_wrapper to avoid double-wrapping at the model level.
    _orig_load_models = getattr(_mm, "load_models_gpu", None)
    if _orig_load_models is not None:
        _ORIGINAL_FUNCTIONS["load_models_gpu"] = _orig_load_models

        def _patched_load_models_gpu(*args: Any, **kwargs: Any) -> Any:
            state = _instrumentation_var.get()
            if state is None:
                return _orig_load_models(*args, **kwargs)

            # Read current node context for metadata
            _node_ctx = _current_node_context.get()
            _in_encode = _encode_from_tokens_active.get()
            _load_node_id = _node_ctx[0] if _node_ctx is not None else ""
            _load_node_class = _node_ctx[1] if _node_ctx is not None else ""

            # Build call_path: chain of operations that led to this load
            _call_parts: list[str] = []
            if _load_node_class:
                _call_parts.append(_load_node_class)
            if _in_encode:
                _call_parts.append("CLIP.encode_from_tokens")
            _call_path = "→".join(_call_parts) if _call_parts else ""

            # Extract models for role classification
            _models = args[0] if len(args) > 0 else kwargs.get("models", [])

            # ── Hard cutoff check ──────────────────────────────────────────
            _cutoff_ns = _sampling_cutoff_perf_ns.get()
            _t0 = time.perf_counter_ns()
            if _cutoff_ns is not None and _t0 >= _cutoff_ns:
                # Entirely post-cutoff — skip instrumentation, no record
                return _orig_load_models(*args, **kwargs)

            # Classify roles before timing (deterministic sorted comma-separated)
            _load_roles: list[str] = []
            for _m in _models:
                _load_roles.append(_model_role_from_patcher(_m))
            if not _load_roles:
                _load_roles.append("other")
            _roles_str = ",".join(sorted(_load_roles))

            _cpu_timer_load = _CpuTimer("load_models_gpu", _roles_str)
            _cpu_timer_load.__enter__()
            try:
                return _orig_load_models(*args, **kwargs)
            finally:
                _cpu_timer_load.__exit__()
                _elapsed = _ns_ms(_t0)

                # Clip if cutoff fired mid-operation
                if _cutoff_ns is not None and _cutoff_ns > _t0:
                    _clipped_elapsed = round(
                        (_cutoff_ns - _t0) / 1_000_000, 3
                    )
                    if _elapsed > _clipped_elapsed:
                        _elapsed = _clipped_elapsed

                if state is not None and _elapsed > 0:
                    state["model_patch_ms"] = state.get("model_patch_ms", 0.0) + _elapsed
                    state.setdefault("_mp_count", 0)
                    state["_mp_count"] += 1

                    # Per-call load_models_gpu record with role classification and metadata
                    _load_record: dict[str, Any] = {
                        "duration_ms": round(_elapsed, 3),
                        "model_count": len(_models),
                        "roles": sorted(_load_roles),
                    }
                    if _load_node_id:
                        _load_record["node_id"] = _load_node_id
                    if _load_node_class:
                        _load_record["node_class"] = _load_node_class
                    if _call_path:
                        _load_record["call_path"] = _call_path
                    state.setdefault("_load_model_calls", []).append(_load_record)

        _mm.load_models_gpu = _patched_load_models_gpu

    # ── 4. comfy.sd.CLIP.encode_from_tokens (raw CLIP encode wall time) ─
    try:
        import comfy.sd as _comfy_sd
        _orig_encode_from_tokens = getattr(
            _comfy_sd.CLIP, "encode_from_tokens", None
        )
        if _orig_encode_from_tokens is not None:
            _ORIGINAL_FUNCTIONS["encode_from_tokens"] = _orig_encode_from_tokens
            _installed_execution_hooks = True

            def _patched_encode_from_tokens(*args: Any, **kwargs: Any) -> Any:
                state = _instrumentation_var.get()
                if state is None:
                    return _orig_encode_from_tokens(*args, **kwargs)

                # ── Hard cutoff check ──────────────────────────────────────
                _cutoff_ns = _sampling_cutoff_perf_ns.get()
                _t0 = time.perf_counter_ns()
                if _cutoff_ns is not None and _t0 >= _cutoff_ns:
                    # Entirely post-cutoff — skip instrumentation, no record
                    return _orig_encode_from_tokens(*args, **kwargs)

                _encode_token = _encode_from_tokens_active.set(True)
                _cpu_timer_enc = _CpuTimer("CLIP.encode_from_tokens", "CLIP")
                _cpu_timer_enc.__enter__()
                try:
                    return _orig_encode_from_tokens(*args, **kwargs)
                finally:
                    _cpu_timer_enc.__exit__()
                    _encode_from_tokens_active.reset(_encode_token)
                    _elapsed = _ns_ms(_t0)

                    # Clip if cutoff fired mid-operation
                    if _cutoff_ns is not None and _cutoff_ns > _t0:
                        _clipped_elapsed = round(
                            (_cutoff_ns - _t0) / 1_000_000, 3
                        )
                        if _elapsed > _clipped_elapsed:
                            _elapsed = _clipped_elapsed

                    if state is not None and _elapsed > 0:
                        state["_clip_raw_encode_ms"] = (
                            state.get("_clip_raw_encode_ms", 0.0) + _elapsed
                        )
                        state.setdefault("_clip_raw_encode_count", 0)
                        state["_clip_raw_encode_count"] += 1
                        self_in_args = args[0] if len(args) > 0 else None
                        state.setdefault("_clip_raw_encode_calls", []).append({
                            "duration_ms": round(_elapsed, 3),
                            "clip_id": str(id(self_in_args)),
                        })

            _comfy_sd.CLIP.encode_from_tokens = _patched_encode_from_tokens
    except (ImportError, AttributeError):
        pass

    # ── 5. PromptExecutor.execute_async ────────────────────────────────
    _prompt_executor_cls = getattr(_execution, "PromptExecutor", None)
    _orig_exec_async = getattr(_prompt_executor_cls, "execute_async", None) if _prompt_executor_cls is not None else None
    if _orig_exec_async is not None:
        _ORIGINAL_FUNCTIONS["execute_async"] = _orig_exec_async
        _installed_execution_hooks = True

        async def _patched_exec_async(self, prompt, prompt_id, extra_data={}, execute_outputs=[]):
            state = _instrumentation_var.get()
            if state is None:
                return await _orig_exec_async(
                    self, prompt, prompt_id, extra_data, execute_outputs,
                )

            # Capture the live prompt dict for class_type lookup
            state["_prompt"] = prompt

            # ── Phase: execution_start_to_cached (cache results gather) ────
            # Intercept the cache-results gather that happens inside execute_async.
            # We hook into the section after executor.reset() and before the
            # while-loop that executes nodes.  Since we cannot easily patch the
            # internals of execute_async without a deeper rewrite, we note the
            # start time and let the per-node hooks capture residual work.
            _t_start = time.perf_counter_ns()
            state["_exec_async_start_ns"] = _t_start

            try:
                return await _orig_exec_async(
                    self, prompt, prompt_id, extra_data, execute_outputs,
                )
            finally:
                # Finalize aggregate state after execution completes.
                # Compute local pre-sampler window using authoritative
                # first _sampling_cutoff_perf_ns when present; only fall
                # back to end when no authoritative sampling event exists.
                _t_end = time.perf_counter_ns()
                _cutoff_ns = _sampling_cutoff_perf_ns.get()
                if _cutoff_ns is not None and _cutoff_ns > _t_start:
                    _total_wall_ns = _cutoff_ns - _t_start
                else:
                    _total_wall_ns = _t_end - _t_start
                _total_wall_ms = _total_wall_ns / 1_000_000

                # Consume lock_wait from bridge (set by modal_app send_sync wrapper)
                _pop_lock_wait_ms(state)

                # Determine dominant interval span name based on what was observed
                _has_clip = bool(state.get("conditioning_ms", 0.0) > 0)
                _has_sampler = "sampler_node_id" in state
                _has_loader = "model_load_ns" in state

                if not _has_clip and not _has_sampler:
                    _span_name = "execution_complete"
                elif _has_sampler and _has_clip:
                    _span_name = "full_pre_sampler"
                elif _has_sampler:
                    _span_name = "sampler_path"
                else:
                    _span_name = "conditioning_only"

                state["span"] = _span_name
                state.setdefault("start_node_id", state.get("first_node_id", ""))
                state.setdefault("start_class_type", state.get("first_class_type", ""))
                state.setdefault("end_node_id", state.get("sampler_node_id", state.get("last_node_id", "")))
                state.setdefault("end_class_type", state.get("sampler_class_type", state.get("last_class_type", "")))

                # ── Non-overlap accounting ─────────────────────────────────
                # input_resolution_ms, model_patch_ms, lock_wait_ms,
                # conditioning_ms, clip_raw_encode_ms are nested/subset
                # diagnostics inside node_execution.  They are NOT added to
                # the non-overlapping measured total.  The non-overlapping
                # base is node_execution_ms (sequential node intervals) plus
                # future_wait_ms (truly disjoint outside-node interval).
                _ne = state.get("node_execution_ms", 0.0)
                _fw = state.get("future_wait_ms", 0.0)
                _non_overlap_base = _ne + _fw

                # Enforce invariant: non_overlap_base <= total_wall_ms.
                # Clamp and flag breaches so they can be detected in tests.
                if _non_overlap_base > _total_wall_ms:
                    state["_overlap_breach"] = round(_non_overlap_base - _total_wall_ms, 3)
                    _non_overlap_base = _total_wall_ms

                # pre_sampler_unattributed_ms = residual after non-overlapping base.
                # This represents the wall time gap NOT covered by any node
                # execution or future-wait, bounded by the authoritative
                # pre-sampler window.
                _pre_sampler_unattributed = max(0.0, _total_wall_ms - _non_overlap_base)
                state["pre_sampler_unattributed_ms"] = (
                    state.get("pre_sampler_unattributed_ms", 0.0)
                    + _pre_sampler_unattributed
                )

                # unattributed_ms = residual after also including cache_lookup_ms
                # (partially outside node execution) for full accounting.
                _cl = state.get("cache_lookup_ms", 0.0)
                _all_non_overlap = _non_overlap_base + _cl
                if _all_non_overlap > _total_wall_ms:
                    _all_non_overlap = _total_wall_ms
                _unattr = max(0.0, _total_wall_ms - _all_non_overlap)
                if _unattr > 0.001:
                    state["unattributed_ms"] = state.get("unattributed_ms", 0.0) + _unattr

                # background_future flags
                state.setdefault("background_future_exists", state.get("_model_loaded", False))
                state.setdefault("background_future_done", state.get("_model_loaded", False))
                state.setdefault("model_cache_hit", state.get("_mp_count", 0) == 0)

                # ── Expose authoritative totals for structured report ──────
                # pre_sampler_total_ms = the authoritative pre-sampler window
                # (clipped at sampling_start when available).
                # non_overlapping_measured_total = node_execution_ms + future_wait_ms
                # (excludes nested diagnostics: input_resolution, model_patch,
                #  lock_wait, conditioning, clip_raw_encode).
                # These invariant fields allow consumers to verify
                # measured <= pre_sampler_total.
                state["pre_sampler_total_ms"] = round(_total_wall_ms, 3)
                state["non_overlapping_measured_total"] = round(_non_overlap_base, 3)

                # ── Emit exactly one line ──────────────────────────────────
                _emit_pre_sampler_line(state)

        _execution.PromptExecutor.execute_async = _patched_exec_async

    # ── 5. comfy_execution.caching.HierarchicalCache.get (cache lookup) ─
    try:
        from comfy_execution.caching import HierarchicalCache as _HCache
    except ImportError:
        _HCache = None

    if _HCache is not None:
        _orig_cache_get = _HCache.get
        _ORIGINAL_FUNCTIONS["HierarchicalCache.get"] = _orig_cache_get

        async def _patched_cache_get(self, node_id):
            state = _instrumentation_var.get()
            if state is None:
                return await _orig_cache_get(self, node_id)
            _t0 = time.perf_counter_ns()
            result = await _orig_cache_get(self, node_id)
            _elapsed = _ns_ms(_t0)
            if state is not None:
                state["cache_lookup_ms"] = state.get("cache_lookup_ms", 0.0) + _elapsed
                state.setdefault("_cache_count", 0)
                state["_cache_count"] += 1
                if result is not None:
                    state.setdefault("_cache_hit_count", 0)
                    state["_cache_hit_count"] += 1
                else:
                    state.setdefault("_cache_miss_count", 0)
                    state["_cache_miss_count"] += 1
            return result

        _HCache.get = _patched_cache_get

    # ── 6. execution.resolve_map_node_over_list_results (future wait) ───
    _orig_resolve = getattr(_execution, "resolve_map_node_over_list_results", None)
    if _orig_resolve is not None:
        _ORIGINAL_FUNCTIONS["resolve_map_node_over_list_results"] = _orig_resolve
        _installed_execution_hooks = True

        async def _patched_resolve_results(results):
            state = _instrumentation_var.get()
            if state is None:
                return await _orig_resolve(results)
            # Record whether any futures were actually pending (not done)
            _has_pending = any(
                isinstance(r, asyncio.Task) and not r.done()
                for r in results
            )
            _t0 = time.perf_counter_ns()
            try:
                return await _orig_resolve(results)
            finally:
                _elapsed = _ns_ms(_t0)
                if state is not None:
                    state["future_wait_ms"] = state.get("future_wait_ms", 0.0) + _elapsed
                    state.setdefault("_fw_count", 0)
                    state["_fw_count"] += 1
                    if not _has_pending:
                        # All futures were already done — mark as cache hit
                        # (zero wait, immediate completion)
                        state.setdefault("_fw_immediate_count", 0)
                        state["_fw_immediate_count"] += 1

        _execution.resolve_map_node_over_list_results = _patched_resolve_results

    # Only mark hooks as fully installed when execution-module hooks were
    # actually placed (get_input_data, execute, execute_async, or
    # resolve_map_node_over_list_results).  This prevents a partial fake
    # execution module from permanently blocking real-module hooking.
    if _installed_execution_hooks:
        _hooks_installed = True


def uninstall_pre_sampler_hooks() -> None:
    """Restore all original ComfyUI execution functions.

    Safe to call multiple times — no-op when hooks are not installed.
    """
    global _hooks_installed
    if not _hooks_installed:
        return

    import execution as _execution
    import comfy.model_management as _mm

    _orig_get_data = _ORIGINAL_FUNCTIONS.get("get_input_data")
    if _orig_get_data is not None:
        _execution.get_input_data = _orig_get_data

    _orig_exec = _ORIGINAL_FUNCTIONS.get("execute")
    if _orig_exec is not None:
        _execution.execute = _orig_exec

    _orig_load = _ORIGINAL_FUNCTIONS.get("load_models_gpu")
    if _orig_load is not None:
        _mm.load_models_gpu = _orig_load

    _orig_exec_async = _ORIGINAL_FUNCTIONS.get("execute_async")
    if _orig_exec_async is not None:
        _execution.PromptExecutor.execute_async = _orig_exec_async

    # Restore new hooks (5, 6)
    _orig_cache_get = _ORIGINAL_FUNCTIONS.get("HierarchicalCache.get")
    if _orig_cache_get is not None:
        from comfy_execution.caching import HierarchicalCache as _HCache
        _HCache.get = _orig_cache_get

    _orig_resolve = _ORIGINAL_FUNCTIONS.get("resolve_map_node_over_list_results")
    if _orig_resolve is not None:
        _execution.resolve_map_node_over_list_results = _orig_resolve

    # Restore encode_from_tokens hook
    _orig_encode = _ORIGINAL_FUNCTIONS.get("encode_from_tokens")
    if _orig_encode is not None:
        try:
            import comfy.sd as _comfy_sd
            _comfy_sd.CLIP.encode_from_tokens = _orig_encode
        except (ImportError, AttributeError):
            pass

    _ORIGINAL_FUNCTIONS.clear()
    _hooks_installed = False


@contextlib.contextmanager
def pre_sampler_instrumentation_scope(state_override: dict[str, Any] | None = None):
    """Context manager that installs hooks and sets per-request state.

    Usage::

        with pre_sampler_instrumentation_scope():
            result = await executor.execute(plan, context=ctx)
    """
    state = state_override if state_override is not None else {}
    token = _instrumentation_var.set(state)
    # Reset sampling cutoff contextvar to prevent cross-request leakage
    _cutoff_token = _sampling_cutoff_perf_ns.set(None)
    install_pre_sampler_hooks()
    try:
        yield state
    finally:
        _sampling_cutoff_perf_ns.reset(_cutoff_token)
        _instrumentation_var.reset(token)


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

    def _consume_seed_for_request(
        self,
        ctx: ExecutionContext,
        plan: ExecutionPlan,
        cache: PreSamplerCache | None,
    ) -> None:
        """Consume a snapshot execution seed at request start, fail-closed.

        Reads ``ctx.metadata["snapshot_execution_seed"]`` (a
        ``SnapshotExecutionSeed`` or serializable mapping).  When absent,
        existing behavior is fully preserved (no decision recorded, no reuse).

        When present, validates workflow AND deployment identity against the
        plan before enabling any loader/static reuse, then records the
        decision on ``ctx.metadata["snapshot_seed_decision"]``.  Deployment /
        custom-node identity is sourced from ``ctx.metadata`` first, then
        ``plan.request_metadata``, so existing callers that place those
        values in either location work unchanged.
        """
        seed = ctx.metadata.get("snapshot_execution_seed")
        if seed is None:
            return
        if cache is None:
            return
        request_meta = plan.request_metadata or {}
        deployment_hash = str(
            ctx.metadata.get("deployment_combined_hash", "")
            or (request_meta.get("deployment_combined_hash", "") if hasattr(request_meta, "get") else "")
        )
        custom_node_generation = str(
            ctx.metadata.get("custom_node_generation", "")
            or (request_meta.get("custom_node_generation", "") if hasattr(request_meta, "get") else "")
        )
        decision = cache.consume_snapshot_seed(
            seed,
            workflow_hash=plan.workflow_hash,
            source_workflow_hash=plan.source_workflow_hash,
            deployment_combined_hash=deployment_hash,
            custom_node_generation=custom_node_generation,
        )
        ctx.metadata["snapshot_seed_decision"] = decision
        if ctx.trace is not None:
            ctx.trace.emit(
                "snapshot_seed_consumed",
                phase="execution",
                metadata={
                    "status": decision.get("status", ""),
                    "reuse_enabled": 1 if decision.get("reuse_enabled") else 0,
                    "reasons": ",".join(decision.get("reasons", []) or []),
                    "seed_schema_version": decision.get("seed_schema_version", 0),
                },
            )

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext | None = None,
        enable_pre_sampler_instrumentation: bool = False,
    ) -> dict[str, Any]:
        ctx = context or ExecutionContext()
        cache: PreSamplerCache | None = ctx.metadata.get("pre_sampler_cache")
        if cache is not None:
            cache.build_cache_key(plan)
        # Step 3: consume snapshot seed at request start (fail-closed, no-op
        # when no seed is supplied).
        self._consume_seed_for_request(ctx, plan, cache)
        diagnostics = self.select_backend(plan.execution_options.requested_backend)
        started = time.perf_counter()
        runner = self._runner_for(diagnostics.selected)
        try:
            if runner is None:
                raise RuntimeError(f"requested execution backend unavailable: {diagnostics.selected}")

            # ── Pre-sampler live instrumentation scope ─────────────
            async def _run_with_instrumentation() -> dict[str, Any]:
                _inst_state: dict[str, Any] = {}
                with pre_sampler_instrumentation_scope(_inst_state):
                    result = runner(plan, ctx)
                    if inspect.isawaitable(result):
                        result = await result
                    # Capture structured report data from instrumentation state
                    _attach_structured_report(result, _inst_state)
                    return result  # type: ignore[return-value]

            if enable_pre_sampler_instrumentation:
                result = await _run_with_instrumentation()
            else:
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
        # Step 3: consume snapshot seed at request start (fail-closed, no-op
        # when no seed is supplied).
        self._consume_seed_for_request(ctx, plan, cache)
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


# ═══════════════════════════════════════════════════════════════════════
# SAMPLER_SAMPLE production wrapper — always-on sampling timing
# ═══════════════════════════════════════════════════════════════════════
# Lives here (not in modal_app.py) to avoid circular import with model_preload.

# In-flight dedup set for the SAMPLER_SAMPLE wrapper.  Keys are
# ``(request_id, str(id(executor)))`` and are REMOVED when the invocation
# completes (the wrapper's ``finally``).  The set therefore only ever holds
# currently-in-flight sampler invocations: it cannot grow without bound, and a
# later sampler whose executor happens to reuse a freed ``id()`` is never
# suppressed.  Sequential invocations of the same executor each emit their own
# start/end pair (one pair per actual sampler invocation).
_sampler_wrapper_dedup: set[tuple[str, str]] = set()
_sampler_wrapper_dedup_lock = threading.RLock()


def _build_sampling_wrapper() -> Callable:
    """Build a production SAMPLER_SAMPLE wrapper that emits sampling_start
    and sampling_end events to the active request RuntimeTrace.

    The wrapper reads ``_ACTIVE_REQUEST_TRACE`` from model_preload's ContextVar,
    emits ``sampling_start`` immediately before the inner executor, emits
    ``sampling_end`` in a ``finally`` block immediately after, computes duration
    via ``time.monotonic_ns()``, and reads step count from the sigma argument.

    Also emits authoritative ``[v2.sampler_boundary]`` one-lines and the
    ``first_sampler_step`` trace event (via a callback wrapper) so the one-shot
    stall watchdog can observe the first completed sampler step.  The first
    sampler identity (guider patcher / diffusion model) is captured and the
    retained-UNET object identity is verified against the bridge.

    This is also where the one-shot sampler-stall watchdog is PRODUCTION-armed
    (at the actual sampling_start boundary): its 5s first-UNET-forward and 15s
    first-step deadlines are measured from sampling start, NOT from
    PromptExecutor start (model loading / CLIP encode before the sampler must
    not count toward them).  The watchdog is canceled by the request owner
    (modal_app's finally) on normal/error completion.

    Deduplication is per ``(request_id, id(executor))`` and is in-flight-only:
    the key is removed in the wrapper's ``finally`` when the invocation
    completes, so the set never grows without bound and never suppresses a
    later sampler from ``id(executor)`` reuse.  Each actual sampler
    invocation emits exactly one start/end pair; the one-shot stall watchdog
    stays single per request (arming is idempotent per request_id).

    Does NOT copy ``CFGGuider.inner_sample`` or any other sampler internals.
    Preserves all model options, wrapper chains, and per-step callbacks.
    """
    from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE

    def _sampler_node_context(guider: Any) -> tuple[str, str]:
        """Resolve the authoritative sampler node context ``(node_id, node_class)``.

        Preferred source: a COMPLETE guider-owned pair — ``_node_id`` /
        ``_class_type`` (or the non-underscore ``node_id`` / ``class_type``),
        set by custom sampler nodes.  Fallback: a COMPLETE
        ``_current_node_context`` ContextVar pair set by ``_patched_exec_node``,
        so a stock ComfyUI guider still reports the exact sampler node — e.g.
        node id ``1242`` / ``ClownsharKSampler_Beta`` when present — at the
        watchdog arm, sampling_start, first_unet_forward, first_sampler_step,
        and sampling_end markers.

        A partial pair from one source is NEVER combined with a field from the
        other source: that would fabricate a mixed identity (e.g. one guider
        field plus one ContextVar field).  If neither source yields a complete
        pair, both blank values are returned.
        """
        guider_node_id = str(getattr(guider, "_node_id", getattr(guider, "node_id", "")) or "")
        guider_node_class = str(getattr(guider, "_class_type", getattr(guider, "class_type", "")) or "")
        if guider_node_id and guider_node_class:
            return guider_node_id, guider_node_class
        try:
            _ctx = _current_node_context.get()
        except Exception:
            _ctx = None
        if _ctx is not None:
            ctx_node_id, ctx_node_class = _ctx
            ctx_node_id = str(ctx_node_id or "")
            ctx_node_class = str(ctx_node_class or "")
            if ctx_node_id and ctx_node_class:
                return ctx_node_id, ctx_node_class
        # No complete pair from either source: never mix one guider field with
        # one ContextVar field.  Report both blank rather than a mixed identity.
        return "", ""

    def _sampler_boundary_meta(
        trace: Any,
        guider: Any,
        *,
        steps: int,
        include_memory: bool = True,
    ) -> dict[str, Any]:
        """Collect sampler/node/patcher/diffusion-model identity metadata."""
        from comfymodal_runtime.unet_forward_probe import resolve_diffusion_model
        meta: dict[str, Any] = {
            "request_id": str(trace.request_id) if trace is not None else "",
        }
        try:
            from comfymodal_runtime.model_preload import _LATEST_RESTORED_INSTANCE_ID
            meta["restored_instance_id"] = _LATEST_RESTORED_INSTANCE_ID or ""
        except Exception:
            pass
        meta["node_id"], meta["node_class"] = _sampler_node_context(guider)
        meta["steps"] = steps
        patcher = getattr(guider, "model_patcher", None)
        if patcher is None:
            patcher = getattr(guider, "model", None)
        patcher_id = str(id(patcher)) if patcher is not None else ""
        meta["patcher_object_id"] = patcher_id
        dm_obj_id = ""
        dm_device = ""
        dm_current_device = ""
        if patcher is not None:
            try:
                _p, dm = resolve_diffusion_model(patcher)
                if dm is not None:
                    dm_obj_id = str(id(dm))
                    try:
                        dm_device = str(getattr(dm, "device", ""))
                    except Exception:
                        pass
                    try:
                        dm_current_device = str(getattr(dm, "current_device", ""))
                    except Exception:
                        pass
            except Exception:
                pass
        meta["diffusion_model_object_id"] = dm_obj_id
        meta["diffusion_model_device"] = dm_device
        meta["diffusion_model_current_device"] = dm_current_device
        if include_memory:
            try:
                import torch as _torch_mem
                if _torch_mem.cuda.is_available():
                    meta["gpu_allocated_bytes"] = int(_torch_mem.cuda.memory_allocated())
                    meta["gpu_reserved_bytes"] = int(_torch_mem.cuda.memory_reserved())
            except Exception:
                pass
        return meta

    def _sampler_boundary_line(event: str, meta: dict[str, Any]) -> None:
        print(
            f"[v2.sampler_boundary] event={event} "
            + " ".join(f"{k}={v if v not in (None, '') else 'absent'}" for k, v in meta.items()),
            flush=True,
        )

    def _wrapper(executor: Any, *args: Any, **kwargs: Any) -> Any:
        trace = _ACTIVE_REQUEST_TRACE.get()
        if trace is None:
            return executor(*args, **kwargs)

        # Dedup is in-flight-only: the key is removed in the finally below
        # when this invocation completes, so the set cannot grow without bound
        # and a later sampler whose executor reuses a freed id() is never
        # suppressed.  Each actual sampler invocation emits its own pair.
        dedup_key = (trace.request_id, str(id(executor)))
        with _sampler_wrapper_dedup_lock:
            if dedup_key in _sampler_wrapper_dedup:
                return executor(*args, **kwargs)
            _sampler_wrapper_dedup.add(dedup_key)

        # Extract step count from sigma argument (torch tensor length).
        sigmas = kwargs.get("sigmas") if "sigmas" in kwargs else (
            args[1] if len(args) > 1 else None
        )
        steps = int(len(sigmas)) - 1 if sigmas is not None and hasattr(sigmas, "__len__") else 0

        # Get node metadata from sampler (first arg is CFGGuider self).
        # Authoritative node context: guider attributes first, then the active
        # _current_node_context ContextVar (node id 1242 / ClownsharKSampler_Beta
        # when present) so the watchdog arm, sampling_start, first_unet_forward,
        # first_sampler_step and sampling_end all carry the exact sampler node.
        sampler_self = args[0] if args else None
        node_id, node_class = _sampler_node_context(sampler_self)

        start_meta = _sampler_boundary_meta(trace, sampler_self, steps=steps)

        # ── Snapshot/bridge context ──
        # The bridge-served UNET (published retained snapshot object, or its
        # CacheDiT-patched replacement) is compared against the sampler
        # patcher.  A not-yet-done bridge UNET future means no published
        # retained object yet — both the identity check and the fail-closed
        # residency enforcement are skipped for that call.
        _patch = getattr(sampler_self, "model_patcher", None)
        if _patch is None:
            _patch = getattr(sampler_self, "model", None)
        _bridge = None
        _served = None
        _bridge_future_done = False
        try:
            from comfymodal_runtime.model_preload import current_v2_loader_bridge
            _bridge = current_v2_loader_bridge()
            if _bridge is not None and _bridge._preparation is not None and _bridge._preparation.unet_future is not None:
                _uf = _bridge._preparation.unet_future
                _bridge_future_done = bool(_uf.done())
                if _bridge_future_done:
                    try:
                        _served = _uf.result()
                    except Exception:
                        _served = None
        except Exception:
            _bridge = None

        # ── Retained-UNET logical identity: sampler vs bridge ──
        # The sampler must run the exact retained logical UNET.  Identity is
        # the resolved diffusion-model object, so ComfyUI's dynamic
        # ModelPatcher delegates and CacheDiT wrapper/re-attach (which wrap
        # the SAME diffusion model) are accepted.  A different resolved
        # diffusion object (or a missing one on either side) fails closed
        # before the sampler runs.
        if _bridge_future_done and _served is not None and _patch is not None:
            try:
                from comfymodal_runtime.model_preload import verify_retained_unet_identity
                verify_retained_unet_identity(
                    stage_a="bridge",
                    unet_a=_served,
                    stage_b="sampler",
                    unet_b=_patch,
                    request_id=str(trace.request_id),
                )
            except RuntimeError:
                # Fail-closed before the sampler runs: release the in-flight
                # dedup key so a later sampler (or a later request reusing
                # this executor id) is never suppressed by a stale key.
                with _sampler_wrapper_dedup_lock:
                    _sampler_wrapper_dedup.discard(dedup_key)
                raise
            except Exception:
                # Unrelated bridge/verification errors (non-snapshot paths)
                # must never break the sampler.
                pass

        # ── Prove GPU activation with post-load evidence (no tensor contents) ──
        # Enforcement (raise on CPU-resident) is gated to the PRODUCTION
        # CPU-snapshot path AND the exact retained snapshot/bridge model being
        # sampled (logical diffusion-model identity match).  Normal
        # non-snapshot, CPU-only, dynamic/offload, meta/unknown, and bypass
        # paths report diagnostic status instead of raising.
        _enforce_residency = False
        try:
            from comfymodal_runtime.model_preload import is_production_cpu_snapshot_request
            from comfymodal_runtime.unet_forward_probe import resolve_diffusion_model
            if (
                is_production_cpu_snapshot_request(str(trace.request_id))
                and _served is not None
                and _patch is not None
            ):
                _dm_served = resolve_diffusion_model(_served)[1]
                _dm_patch = resolve_diffusion_model(_patch)[1]
                if (
                    _dm_served is not None
                    and _dm_patch is not None
                    and id(_dm_served) == id(_dm_patch)
                ):
                    _enforce_residency = True
        except Exception:
            _enforce_residency = False
        try:
            from comfymodal_runtime.cpu_snapshot_models import verify_unet_gpu_residency
            verify_unet_gpu_residency(
                _patch,
                request_id=str(trace.request_id),
                context="sampler_wrapper_before_sample",
                enforce=_enforce_residency,
            )
        except Exception as _residency_exc:
            if "CPU-resident" in str(_residency_exc):
                # Fail-closed before the sampler runs: release the in-flight
                # dedup key (see identity-mismatch path above).
                with _sampler_wrapper_dedup_lock:
                    _sampler_wrapper_dedup.discard(dedup_key)
                raise
            pass

        # ── Arm the one-shot sampler-stall watchdog at the sampling_start
        # boundary ──
        # Production arming moved here (from modal_app's PromptExecutor start)
        # so the exact deadlines are measured from actual sampling start:
        #   - 5s  waiting for the first UNET forward
        #   - 15s waiting for the first completed sampler step (NOT 5s + 15s)
        # Modal loading / CLIP encode before the sampler no longer count
        # against these deadlines.  Non-destructive; idempotent per request
        # (a second sampler in the same request does not re-arm).  Canceled by
        # the request owner (modal_app finally) on normal/error completion.
        try:
            from comfymodal_runtime.model_preload import start_sampler_stall_watchdog
            start_sampler_stall_watchdog(
                request_id=str(trace.request_id),
                restored_instance_id=start_meta.get("restored_instance_id", ""),
                sampler_node_id=node_id,
                sampler_class=node_class,
                patcher_object_id=start_meta.get("patcher_object_id", ""),
                diffusion_model_object_id=start_meta.get("diffusion_model_object_id", ""),
                # unet_object_id is the retained UNET *patcher* object being
                # sampled (the bridge-served snapshot object or its CacheDiT
                # replacement) — the same logical identity the identity chain
                # records.  The resolved diffusion model id is reported
                # separately as diffusion_model_object_id.
                unet_object_id=start_meta.get("patcher_object_id", ""),
            )
        except Exception:
            pass

        # ── Enrich the one-shot stall watchdog with sampler identity ──
        try:
            from comfymodal_runtime.model_preload import update_sampler_stall_watchdog_identity
            update_sampler_stall_watchdog_identity(
                str(trace.request_id),
                sampler_node_id=node_id,
                sampler_class=node_class,
                patcher_object_id=start_meta.get("patcher_object_id", ""),
                diffusion_model_object_id=start_meta.get("diffusion_model_object_id", ""),
            )
        except Exception:
            pass

        t0 = time.monotonic_ns()
        _sv_before = None
        try:
            from comfymodal_runtime.variance_diagnostics import (
                capture_metric_snapshot,
                variance_diagnostics_enabled,
            )
            if variance_diagnostics_enabled():
                _sv_before = capture_metric_snapshot()
        except Exception:
            pass
        try:
            from comfymodal_runtime.model_preload import (
                acquire_sampler_mutation_lane_at_sampling_start,
            )
            acquire_sampler_mutation_lane_at_sampling_start()
        except Exception:
            pass
        trace.emit("sampling_start", phase="execution", metadata={
            "node_id": node_id,
            "node_class": node_class,
            "steps": steps,
            "patcher_object_id": start_meta.get("patcher_object_id", ""),
            "diffusion_model_object_id": start_meta.get("diffusion_model_object_id", ""),
            "diffusion_model_device": start_meta.get("diffusion_model_device", ""),
        })
        _sampler_boundary_line("sampling_start", start_meta)
        # ── V2 VAE CPU page prefetch (sampling_start hook) ──────────────
        # CPU-only, bounded readiness work submitted through the bridge's
        # coordinator pool (never the mutation lane).  Disabled mode is a
        # silent no-op; an enabled-mode failure is surfaced with a
        # diagnostic line instead of being swallowed.
        try:
            from comfymodal_runtime.model_preload import (
                current_v2_loader_bridge,
                vae_prefetch_mode,
            )
            _vae_prefetch_bridge = current_v2_loader_bridge()
            if _vae_prefetch_bridge is not None:
                _prefetch_mode = vae_prefetch_mode()
                _prefetch_scheduled = _vae_prefetch_bridge.schedule_vae_cpu_prefetch(
                    trace=trace,
                    request_id=str(trace.request_id),
                )
                if not _prefetch_scheduled and _prefetch_mode != "off":
                    print(
                        f"[v2.vae_prefetch] event=schedule_failed "
                        f"request_id={str(trace.request_id)} mode={_prefetch_mode}",
                        flush=True,
                    )
        except Exception:
            print(
                f"[v2.vae_prefetch] event=schedule_exception "
                f"request_id={str(trace.request_id)}",
                flush=True,
            )
        # Set the authoritative pre-sampler hard cutoff: every node-wall
        # measurement is clipped at this perf_counter_ns timestamp so that
        # no sampler/VAE/output wall time leaks into pre-sampler metrics.
        # Idempotent: only the first caller sets the cutoff; subsequent
        # sampler invocations within the same request do NOT overwrite it.
        _cutoff_ns = time.perf_counter_ns()
        if _sampling_cutoff_perf_ns.get() is None:
            _sampling_cutoff_perf_ns.set(_cutoff_ns)
            # Signal all active CPU-owner timers to freeze measurements at cutoff
            _signal_cpu_timers(_cutoff_ns)

        # ── First completed sampler step: wrap the per-step callback ──
        # SAMPLER_SAMPLE args: (guider, sigmas, extra_args, callback, noise,
        # latent_image, denoise_mask, disable_pbar).  The callback fires once
        # per completed step.  The first invocation emits first_sampler_step.
        _first_step_fired = False

        def _step_callback(*cb_args: Any, **cb_kwargs: Any) -> Any:
            nonlocal _first_step_fired
            if not _first_step_fired:
                _first_step_fired = True
                try:
                    trace.emit("first_sampler_step", phase="execution", metadata={
                        "node_id": node_id,
                        "node_class": node_class,
                        "steps": steps,
                        "patcher_object_id": start_meta.get("patcher_object_id", ""),
                        "diffusion_model_object_id": start_meta.get("diffusion_model_object_id", ""),
                    })
                    _sampler_boundary_line("first_sampler_step", dict(start_meta))
                    from comfymodal_runtime.model_preload import mark_first_sampler_step
                    mark_first_sampler_step(str(trace.request_id))
                except Exception:
                    pass
            if _orig_callback is not None:
                return _orig_callback(*cb_args, **cb_kwargs)
            return None

        _orig_callback = kwargs.get("callback") if "callback" in kwargs else (
            args[3] if len(args) > 3 else None
        )
        # Only wrap real callables; preserve None fast path.
        if callable(_orig_callback):
            if "callback" in kwargs:
                kwargs = dict(kwargs)
                kwargs["callback"] = _step_callback
            else:
                args = args[:3] + (_step_callback,) + args[4:]

        try:
            return executor(*args, **kwargs)
        finally:
            # Request-scoped cleanup: drop the in-flight dedup key so the set
            # never grows and a later invocation (including one whose executor
            # reuses this id) is never suppressed.
            with _sampler_wrapper_dedup_lock:
                _sampler_wrapper_dedup.discard(dedup_key)
            duration_ms = round((time.monotonic_ns() - t0) / 1_000_000, 3)
            trace.emit("sampling_end", phase="execution", metadata={
                "node_id": node_id,
                "node_class": node_class,
                "duration_ms": duration_ms,
                "steps": steps,
                "source": "sampler_sample_wrapper",
                "patcher_object_id": start_meta.get("patcher_object_id", ""),
                "diffusion_model_object_id": start_meta.get("diffusion_model_object_id", ""),
            })
            _end_meta = dict(start_meta)
            _end_meta["duration_ms"] = duration_ms
            _sampler_boundary_line("sampling_end", _end_meta)
            # ── Sampler wait-on-activation variance (diagnostic-only) ──
            # Emits a dedicated event separating the sampler wait on
            # activation from sampling duration, using the existing
            # join/activation demand boundaries.  Gated by
            # COMFYMODAL_V2_VARIANCE_DIAGNOSTICS; no semantic change.
            if _sv_before is not None:
                try:
                    from comfymodal_runtime.variance_diagnostics import (
                        capture_metric_snapshot,
                        emit_sampler_variance,
                    )
                    emit_sampler_variance(
                        trace,
                        node_id=node_id,
                        node_class=node_class,
                        steps=steps,
                        before=_sv_before,
                        after=capture_metric_snapshot(),
                        sampling_duration_ms=duration_ms,
                    )
                except Exception:
                    pass
            # ── V2 VAE early activation (sampling_end mode) ─────────────
            # The authoritative sampling_end trace event and
            # [v2.sampler_boundary] line are emitted FIRST above; then the
            # existing sampler mutation-lane ownership is released, the
            # concise [v2.vae_early_activation] event=scheduled line is
            # emitted, and the VAE activation future is submitted exactly
            # once through the existing coordinator pool (see
            # model_preload.schedule_vae_early_activation_at_sampling_end).
            # Hooked from this real SAMPLER_SAMPLE boundary — never from
            # progress/milestones.  Any failure falls back silently to the
            # unchanged late path (the graph VAEDecode/loader handles it).
            try:
                from comfymodal_runtime.model_preload import (
                    current_v2_loader_bridge,
                    release_sampler_mutation_lane_at_sampling_end,
                    schedule_vae_early_activation_at_sampling_end,
                )
                release_sampler_mutation_lane_at_sampling_end(
                    trace=trace,
                    request_id=str(trace.request_id),
                )
                _vae_bridge = current_v2_loader_bridge()
                if _vae_bridge is not None:
                    schedule_vae_early_activation_at_sampling_end(
                        _vae_bridge,
                        trace=trace,
                        request_id=str(trace.request_id),
                        sampler_node_id=node_id,
                        sampler_node_class=node_class,
                        duration_ms=duration_ms,
                    )
            except Exception:
                pass

    return _wrapper


# Pre-built SAMPLER_SAMPLE wrapper singleton.
_COMFYMODAL_V2_SAMPLING_WRAPPER: Callable = _build_sampling_wrapper()


def ensure_sampling_timing_wrapper(model_patcher: Any) -> bool:
    """Install authoritative ``SAMPLER_SAMPLE`` timing wrapper on *model_patcher*.

    Uses ``WrappersMP.SAMPLER_SAMPLE`` key ``comfymodal_v2_sampling_timing``
    with ``_COMFYMODAL_V2_SAMPLING_WRAPPER`` (defined above).
    Idempotent — checks whether the keyed wrapper already exists.

    Returns ``True`` on success, ``False`` on any failure (prints exception
    type name only — no traceback captured).
    """
    try:
        if not hasattr(model_patcher, "model_options"):
            return False
        import comfy.patcher_extension as _pe

        # Idempotent guard
        existing = _pe.get_wrappers_with_key(
            _pe.WrappersMP.SAMPLER_SAMPLE,
            "comfymodal_v2_sampling_timing",
            model_patcher.model_options,
            is_model_options=True,
        )
        if existing:
            return True

        _pe.add_wrapper_with_key(
            _pe.WrappersMP.SAMPLER_SAMPLE,
            "comfymodal_v2_sampling_timing",
            _COMFYMODAL_V2_SAMPLING_WRAPPER,
            model_patcher.model_options,
            is_model_options=True,
        )
        return True
    except Exception as _exc:
        print(
            f"[comfymodal] ensure_sampling_timing_wrapper failed: "
            f"{type(_exc).__name__}",
            flush=True,
        )
        return False
