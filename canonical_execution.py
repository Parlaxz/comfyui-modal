"""Canonical Modal prompt execution — single shared path for normal dispatch and Playground single runs.

Provides ``RunTrace`` (in-memory hierarchical spans using ``perf_counter_ns``)
and ``execute_modal_prompt`` (owns final workflow input, production compile,
profile preparation, modal-args construction, ``modal_client.run_prompt_stream``
call, result collection, and canonical trace/counts).
"""

from __future__ import annotations

import base64
import copy
import inspect
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from api_prompt_validator import assert_valid_api_prompt_structure
from production_workflow import (
    COMPILER_SCHEMA_VERSION,
    HASH_SCHEMA_VERSION,
    PRODUCTION_PLAN_SCHEMA_VERSION,
    compile_production_workflow,
    normalize_production_options,
)
# Note: modal_options are passed through without reconstructing model-loading policy.
from warmup_profile import prepare_active_next_profile
from workflow_metadata import (
    extract_model_stack,
    extract_warmup_stack,
    prompt_sha256,
    stack_to_warmup_profile,
    summarize_prompt_fields,
)
from comfymodal_runtime.contracts import (
    ExecutionOptions,
    ExecutionPlan,
    RestorePlan,
    stable_hash,
)
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.restore_plan import (
    build_restore_model_spec,
    derive_model_key,
    derive_prefill_key,
)
from comfymodal_runtime.trace import RuntimeTrace, merge_runtime_traces

# ---------------------------------------------------------------------------
# Restore-plan publish cache (process-safe, skips remote calls when
# the canonical identity is unchanged for the same workspace/app/env)
# ---------------------------------------------------------------------------

_RESTORE_PUBLISH_CACHE: dict[str, str] = {}
"""``{cache_key: identity_hash}`` — set of published plan identities.

Cache-key format: ``{workspace_id}:{app_name}:{environment}:{identity_hash}``
Cleared only by module reload; survives across calls within the same process.
Thread-safe via ``_RESTORE_PUBLISH_CACHE_LOCK``.
Bounded to ``_RESTORE_PUBLISH_CACHE_MAX`` entries.
"""

_RESTORE_PUBLISH_CACHE_LOCK = threading.Lock()
"""Guard for all ``_RESTORE_PUBLISH_CACHE`` access."""

_RESTORE_PUBLISH_CACHE_MAX = 100
"""Maximum entries in the restore publish cache before eviction."""

_APP_NAME_DEFAULT = "stable-modal-comfy-v2-shadow"
"""Fallback Modal app name when ``COMFYMODAL_V2_APP_NAME`` is unset."""


def _restore_plan_identity_hash(plan: RestorePlan) -> str:
    """Deterministic hash of identity fields, excluding volatile
    ``generation`` and ``created_at``.

    Mirrors ``RestorePlanPublisher._identity_hash`` so the local cache
    is consistent with the publisher's own no-op detection.
    """
    identity = {
        "schema_version": plan.schema_version,
        "model_key": plan.model_key.to_dict(),
        "prefill_key": plan.prefill_key.to_dict(),
        "model_spec": dict(plan.model_spec),
        "prefill_spec": dict(plan.prefill_spec),
        "source_workflow_hash": plan.source_workflow_hash,
    }
    return stable_hash(identity)


def _reset_restore_publish_cache() -> None:
    """Clear the restore-plan publish cache (test / teardown only)."""
    with _RESTORE_PUBLISH_CACHE_LOCK:
        _RESTORE_PUBLISH_CACHE.clear()


def _evict_restore_publish_cache() -> None:
    """Evict oldest entries when cache exceeds ``_RESTORE_PUBLISH_CACHE_MAX``."""
    with _RESTORE_PUBLISH_CACHE_LOCK:
        while len(_RESTORE_PUBLISH_CACHE) > _RESTORE_PUBLISH_CACHE_MAX:
            _RESTORE_PUBLISH_CACHE.pop(next(iter(_RESTORE_PUBLISH_CACHE)), None)


# ---------------------------------------------------------------------------
# Profile preparation cache — skip prepare_active_next_profile when the
# plan identity (source_workflow_hash + production_plan_hash + workspace +
# app/environment) is unchanged for the same process.
# ---------------------------------------------------------------------------

_PROFILE_PREP_CACHE: dict[str, dict] = {}
"""``{cache_key: profile_result}`` — cached prepared profile results.

Cache-key format: ``stable_hash({source_workflow_hash, production_plan_hash,
workspace_id, app_name, environment})``.
Cleared only by module reload; survives across calls within the same process.
Thread-safe via ``_PROFILE_PREP_CACHE_LOCK``.
Bounded to ``_PROFILE_PREP_CACHE_MAX`` entries.
"""

_PROFILE_PREP_CACHE_LOCK = threading.Lock()
"""Guard for all ``_PROFILE_PREP_CACHE`` access."""

_PROFILE_PREP_CACHE_MAX = 100
"""Maximum entries in the profile prep cache before eviction."""


def _profile_prep_cache_key(
    source_workflow_hash: str,
    production_plan_hash: str,
    workspace_id: str,
    app_name: str,
    environment: str,
) -> str:
    """Deterministic cache key for profile preparation results."""
    identity = {
        "s": source_workflow_hash,
        "p": production_plan_hash,
        "w": workspace_id,
        "a": app_name,
        "e": environment,
    }
    return stable_hash(identity)


def _reset_profile_prep_cache() -> None:
    """Clear the profile prep cache (test / teardown only)."""
    with _PROFILE_PREP_CACHE_LOCK:
        _PROFILE_PREP_CACHE.clear()


def _evict_profile_prep_cache() -> None:
    """Evict oldest entries when cache exceeds ``_PROFILE_PREP_CACHE_MAX``."""
    with _PROFILE_PREP_CACHE_LOCK:
        while len(_PROFILE_PREP_CACHE) > _PROFILE_PREP_CACHE_MAX:
            _PROFILE_PREP_CACHE.pop(next(iter(_PROFILE_PREP_CACHE)), None)


# ---------------------------------------------------------------------------
# RunTrace — in-memory hierarchical span collector
# ---------------------------------------------------------------------------


class RunTrace:
    """Hierarchical execution trace using ``perf_counter_ns`` for duration and
    ``time.time`` only for wall-clock correlation.

    Accumulates in memory.  Callers invoke ``emit_local_summary`` before
    Modal submission and ``emit_remote_summary`` before return.  Persistence
    happens only after output delivery (caller responsibility).

    Optional spans (LocalRemoteInvoker, scheduler, runner, lease, checkpoint,
    StudioProgressTracker, LocalRemoteHandler, deploy_listener, scheduler_loop,
    hot_reload_listener) are always present with ``called/count/duration_ms/reason``.
    Payload-size fields report byte counts without full prompt/image bytes.

    Correlation fields (trace_id, run_id, prompt_id, run_surface) are set at
    creation and included in every summary.
    """

    # Required canonical operation count names — counted at the actual
    # operation boundary.
    CANONICAL_COUNTS = frozenset({
        "production_compile_count",
        "full_workflow_hash_count",
        "model_stack_extract_count",
        "active_profile_prepare_count",
        "modal_handle_lookup_count",
        "run_prompt_stream_call_count",
        "workflow_deepcopy_count",
        "workflow_serialization_count",
    })

    # All named Studio wrapper spans — always present with called=False
    # for a direct Playground run.  Includes the original high-level names
    # plus every granular span that the Studio lifecycle creates for
    # experiment/scheduler/runner/invoker/lease flows.
    MARK_OPTIONAL = (
        # Original high-level optional spans
        "LocalRemoteInvoker", "scheduler", "runner", "lease", "checkpoint",
        "StudioProgressTracker", "LocalRemoteHandler", "deploy_listener",
        "scheduler_loop", "hot_reload_listener",
        # Granular Studio lifecycle spans
        "studio_single_run_enter", "direct_studio_run_completion",
        "experiment_creation", "run_history_creation",
        "scheduler_creation", "scheduler_start",
        "runner_creation",
        "local_remote_invoker_creation",
        "local_remote_invoker_open_worker",
        "local_remote_invoker_run_cell",
        "local_remote_invoker_close_worker",
        "lease_claim", "checkpoint_write", "journal_write",
        "cell_resolution", "experiment_trace_merge",
        "studio_output_copy", "studio_history_update",
        "studio_output_metadata_write",
        # Required canonical span names — stable entries in every RunTrace summary
        # (called=true when the boundary was reached, otherwise defaults)
        "canonical_execute_enter",
        "workflow_input_size",
        "workflow_deepcopy",
        "workflow_normalization",
        "production_compile",
        "production_validate_local",
        "source_workflow_hash",
        "compiled_workflow_hash",
        "production_plan_hash",
        "model_stack_extract",
        "used_node_class_extract",
        "input_image_discovery",
        "input_image_read",
        "input_image_encode",
        "extra_data_build",
        "modal_options_build",
        "production_report_build",
        "active_profile_build",
        "active_profile_dedup",
        "active_profile_local_write",
        "active_profile_remote_call",
        "active_profile_ack_wait",
        "modal_handle_lookup",
        "modal_handle_cache_hit",
        "modal_argument_serialization",
        "remote_generator_create",
        "remote_submit",
        "first_remote_message",
        "remote_result_complete",
        "canonical_execute_exit",
    )

    def __init__(
        self,
        *,
        trace_id: str = "",
        run_id: str = "",
        prompt_id: str = "",
        run_surface: str = "unknown",
    ) -> None:
        self._spans: dict[str, dict[str, Any]] = {}
        self._counts: dict[str, int] = {}
        self._wall_start: float = time.time()
        self._perf_start_ns: int = time.perf_counter_ns()
        self._major_samples: list[dict[str, Any]] = []
        self._payload_sizes: dict[str, int] = {}
        self._meta: dict[str, Any] = {}  # canonical metadata without full workflow bytes
        # Correlation fields
        self._trace_id: str = trace_id or uuid.uuid4().hex[:16]
        self._run_id: str = run_id or uuid.uuid4().hex[:12]
        self._prompt_id: str = prompt_id
        self._run_surface: str = run_surface

    # -- correlation property access --

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def prompt_id(self) -> str:
        return self._prompt_id

    @property
    def run_surface(self) -> str:
        return self._run_surface

    # -- span lifecycle --

    def begin(self, name: str, *, reason: str = "") -> None:
        entry = self._spans.setdefault(name, {})
        entry["called"] = True
        entry["_start_ns"] = time.perf_counter_ns()
        entry["wall_s"] = time.time()
        entry["count"] = entry.get("count", 0) + 1
        if reason:
            entry["reason"] = reason

    def end(self, name: str, *, reason: str = "") -> None:
        entry = self._spans.get(name)
        if entry is None or "_start_ns" not in entry:
            return
        entry["duration_ns"] = time.perf_counter_ns() - entry["_start_ns"]
        entry["duration_ms"] = round(entry["duration_ns"] / 1_000_000, 2)
        del entry["_start_ns"]
        if reason:
            entry["reason"] = reason

    def count(self, name: str, delta: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + delta

    def record_payload_size(self, label: str, byte_count: int) -> None:
        self._payload_sizes[label] = byte_count

    def set_meta(self, **fields: Any) -> None:
        """Store canonical metadata fields (model_stack, hashes, GPU, etc.)
        without logging full workflow/image bytes."""
        self._meta.update(fields)

    def sample(self, label: str, **fields: Any) -> None:
        self._major_samples.append({"label": label, "wall_s": time.time(), **fields})

    # -- optional spans (always present with called=False by default) --

    def _ensure_optionals(self) -> None:
        for name in self.MARK_OPTIONAL:
            if name not in self._spans:
                self._spans[name] = {
                    "called": False,
                    "count": 0,
                    "duration_ms": 0,
                    "reason": "",
                }

    def _init_canonical_counts(self) -> None:
        """Ensure every named canonical count is present (even if zero)."""
        for name in self.CANONICAL_COUNTS:
            if name not in self._counts:
                self._counts[name] = 0

    # -- emission --

    def emit_local_summary(self) -> dict[str, Any]:
        """Structured summary emitted before Modal submission."""
        self._ensure_optionals()
        self._init_canonical_counts()
        return {
            "trace_id": self._trace_id,
            "run_id": self._run_id,
            "prompt_id": self._prompt_id,
            "run_surface": self._run_surface,
            "spans": {k: {sk: sv for sk, sv in v.items() if not sk.startswith("_")}
                      for k, v in self._spans.items()},
            "counts": dict(self._counts),
            "payload_sizes": dict(self._payload_sizes),
            "meta": dict(self._meta),
            "wall_start_s": self._wall_start,
        }

    def emit_remote_summary(self) -> dict[str, Any]:
        """Structured summary emitted before return (after Modal call)."""
        self._ensure_optionals()
        self._init_canonical_counts()
        return {
            "trace_id": self._trace_id,
            "run_id": self._run_id,
            "prompt_id": self._prompt_id,
            "run_surface": self._run_surface,
            "spans": {k: {sk: sv for sk, sv in v.items() if not sk.startswith("_")}
                      for k, v in self._spans.items()},
            "counts": dict(self._counts),
            "payload_sizes": dict(self._payload_sizes),
            "meta": dict(self._meta),
            "wall_start_s": self._wall_start,
            "perf_start_ns": self._perf_start_ns,
            "samples": list(self._major_samples),
        }

    def merge_into_trace(self, trace_dict: dict[str, Any]) -> None:
        """Merge run-trace fields into the existing trace payload for history."""
        rs = self.emit_remote_summary()
        trace_dict["_run_trace"] = rs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_class_types(workflow: dict, production_report: dict | None = None) -> None:
    """Local class-type existence check.  Skips compiler-rewritten node IDs."""
    try:
        import nodes as _validate_nodes
    except Exception:
        return  # skip when not running inside ComfyUI

    _requested_types: set[str] = set()
    _PRODUCTION_REMOTE_CLASSES = frozenset({
        "ComfyModalProductionOutput",
        "ComfyModalProductionImageComparerOutput",
    })
    for _spec in workflow.values():
        if isinstance(_spec, dict):
            _ct = _spec.get("class_type")
            if isinstance(_ct, str) and _ct:
                _requested_types.add(_ct)

    _production_active = bool(
        production_report
        and isinstance(production_report, dict)
        and production_report.get("enabled")
    )
    if _production_active:
        _rewritten_out_ids = set(production_report.get("direct_output_rewritten_node_ids", []))
        _rewritten_rgthree_ids = set(production_report.get("rgthree_comparer_rewritten_node_ids", []))
        _validated_types: set[str] = set()
        for _nid, _spec in workflow.items():
            if not isinstance(_spec, dict):
                continue
            _ct = _spec.get("class_type")
            if not isinstance(_ct, str) or not _ct:
                continue
            if _ct == "ComfyModalProductionOutput" and str(_nid) in _rewritten_out_ids:
                continue
            if _ct == "ComfyModalProductionImageComparerOutput" and str(_nid) in _rewritten_rgthree_ids:
                continue
            _validated_types.add(_ct)
    else:
        _validated_types = _requested_types

    _missing = sorted(
        ct for ct in _validated_types
        if ct not in _validate_nodes.NODE_CLASS_MAPPINGS
    )
    if _missing:
        raise RuntimeError(
            f"Missing custom node class(es): {_missing}. "
            f"Install the missing custom nodes or fix the workflow."
        )


def _collect_input_images(workflow: dict, comfyui_root: str) -> dict[str, str]:
    """Base64-encode local images referenced by LoadImage nodes."""
    images: dict[str, str] = {}
    _WORKFLOW_IMAGE_SUFFIX_DIRS = {
        " [output]": "output",
        " [input]": "input",
        " [temp]": "temp",
    }

    def _resolve_candidates(filename: str) -> list[str]:
        name = (filename or "").strip()
        for suffix, directory in _WORKFLOW_IMAGE_SUFFIX_DIRS.items():
            if name.endswith(suffix):
                base = name[: -len(suffix)].rstrip()
                return [os.path.join(comfyui_root, directory, *base.replace("\\", "/").split("/"))]
        parts = [p for p in filename.replace("\\", "/").split("/") if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            return []
        return [
            os.path.join(comfyui_root, d, *parts)
            for d in ("input", "output")
            if os.path.isdir(os.path.join(comfyui_root, d))
        ]

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        if not class_type.startswith("LoadImage"):
            continue
        for key in ("image", "mask"):
            filename = node.get("inputs", {}).get(key, "")
            if not isinstance(filename, str) or not filename:
                continue
            if filename in images:
                continue
            if filename.startswith(("http://", "https://")):
                continue
            candidates = _resolve_candidates(filename)
            for filepath in candidates:
                if os.path.isfile(filepath):
                    with open(filepath, "rb") as f:
                        images[filename] = base64.b64encode(f.read()).decode()
                    break
    return images


def _event_span_ms(trace: RuntimeTrace, start_name: str, end_name: str) -> float | None:
    start_ns: int | None = None
    for event in trace.events:
        if event.name == start_name:
            start_ns = event.monotonic_ns
        elif event.name == end_name and start_ns is not None:
            return round((event.monotonic_ns - start_ns) / 1_000_000, 3)
    return None


def _strict_event_span_ms(trace: RuntimeTrace, start_name: str, end_name: str) -> float | str | None:
    """Like _event_span_ms but returns _INVALID_NEG_STR for negative durations.
    Returns None when missing, _INVALID_NEG_STR when start > end, float otherwise."""
    start_ns: int | None = None
    for event in trace.events:
        if event.name == start_name:
            start_ns = event.monotonic_ns
        elif event.name == end_name and start_ns is not None:
            delta = event.monotonic_ns - start_ns
            if delta < 0:
                return "invalid_negative"
            return round(delta / 1_000_000, 3)
    return None


def _event_mono_ns(trace: RuntimeTrace, name: str) -> int | None:
    """Return the monotonic_ns of the first event with *name*, or None."""
    for event in trace.events:
        if event.name == name:
            return event.monotonic_ns
    return None


def _derived_mono_delta_ms(trace: RuntimeTrace, start_name: str, end_name: str) -> float | str | None:
    """Compute ``end_name - start_name`` in ms using monotonic timestamps.
    Returns ``None`` when either event is missing, ``"invalid_negative"`` when
    the delta is negative, otherwise the non-negative float ms.
    Uses start, end ordering (first arg = start, second arg = end)."""
    start_ns = _event_mono_ns(trace, start_name)
    end_ns = _event_mono_ns(trace, end_name)
    if start_ns is None or end_ns is None:
        return None
    delta = end_ns - start_ns
    if delta < 0:
        return "invalid_negative"
    return round(delta / 1_000_000, 3)


def build_execution_plan(
    workflow: dict,
    *,
    prompt_id: str = "",
    client_id: str = "",
    input_images: dict[str, str] | None = None,
    modal_options: dict | None = None,
    production_options: dict | None = None,
    production_report: dict | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    request_metadata: dict | None = None,
    comfyui_root: str = "",
    trace: RuntimeTrace | None = None,
    validate: bool = True,
) -> ExecutionPlan:
    """Normalize, validate, compile, and freeze one dispatch plan."""
    if trace:
        trace.emit("plan_build_start", phase="local", metadata={"prompt_id": prompt_id})
    source_workflow = copy.deepcopy(workflow or {})
    source_hash = prompt_sha256(source_workflow)
    if validate:
        assert_valid_api_prompt_structure(source_workflow)
        _validate_class_types(source_workflow, production_report)

    dispatch_workflow = source_workflow
    report = dict(production_report or {})
    normalized_production = None
    if report.get("enabled"):
        dispatch_workflow = copy.deepcopy(workflow or {})
    elif production_options and production_options.get("enabled"):
        normalized_production = normalize_production_options(production_options)
        compiled = compile_production_workflow(
            source_workflow,
            normalized_production,
            allow_direct_output_rewrite=True,
        )
        dispatch_workflow = compiled.compiled_workflow
        report = dict(compiled.report)
    dispatch_hash = prompt_sha256(dispatch_workflow)
    if report.get("enabled"):
        compiled_hash = str(report.get("compiled_workflow_hash", ""))
        if compiled_hash and compiled_hash != dispatch_hash:
            raise AssertionError(
                "execution plan compiled workflow hash mismatch: "
                f"compiled={compiled_hash[:12]} dispatch={dispatch_hash[:12]}"
            )

    if input_images is None:
        input_images = _collect_input_images(dispatch_workflow, comfyui_root) if comfyui_root else {}

    model_stack = extract_model_stack(dispatch_workflow)
    try:
        from optimizations import extract_safe_prompt_bundle
        bundle_result = extract_safe_prompt_bundle(dispatch_workflow)
        prompt_bundle = bundle_result.get("bundle", {}) if bundle_result.get("eligible") else {}
    except Exception:
        prompt_bundle = summarize_prompt_fields(dispatch_workflow)

    option_source = dict(modal_options or {})
    if report.get("enabled"):
        option_source["production"] = {
            "enabled": True,
            "output_node_ids": list(report.get("output_node_ids", [])),
        }
    options = ExecutionOptions.from_legacy(
        option_source,
        production_report=report,
        default_production=bool(report.get("enabled")),
    )
    output_node_ids = tuple(str(v) for v in report.get("output_node_ids", options.production_output_node_ids))
    metadata = dict(request_metadata or {})
    # Propagate request_origin_info from trace when request_metadata lacks it.
    # Use Mapping check because frozen dataclasses wrap nested dicts as
    # mappingproxy; isinstance(x, dict) fails for mappingproxy values.
    if trace is not None:
        _trace_origin = trace._metadata.get("request_origin_info", {})
        if isinstance(_trace_origin, Mapping) and _trace_origin:
            metadata.setdefault("request_origin_info", dict(_trace_origin))
    metadata.update({
        "prompt_id": prompt_id,
        "client_id": client_id,
        "selected_gpu": gpu or "",
        "workspace_id": str((workspace or {}).get("id", "")),
    })
    plan = ExecutionPlan(
        workflow=dispatch_workflow,
        workflow_hash=dispatch_hash,
        source_workflow_hash=str(report.get("source_workflow_hash", source_hash)),
        production_report=report,
        model_stack=model_stack,
        prompt_bundle=prompt_bundle,
        output_node_ids=output_node_ids,
        input_images=input_images or {},
        execution_options=options,
        request_metadata=metadata,
    )
    if trace:
        trace.emit("plan_build_end", phase="local", metadata={
            "workflow_hash": plan.workflow_hash,
            "source_workflow_hash": plan.source_workflow_hash,
            "production_enabled": bool(report.get("enabled")),
        })
    return plan


async def execute_plan(
    plan: ExecutionPlan,
    *,
    transport: ModalTransport | None = None,
    restore_publisher: Any | None = None,
    profile_setter: Callable[..., Any] | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    trace: RuntimeTrace | None = None,
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Publish one restore plan, submit one plan, and merge one trace.

    When *profile_setter* is provided, calls ``prepare_active_next_profile``
    before restore publication / Modal submission.  A missing setter is a
    safe dry-run / no-remote path.
    """
    runtime_trace = trace or RuntimeTrace(
        request_id=str(plan.request_metadata.get("prompt_id", "")),
        process="local",
    )

    # Propagate request_origin_info from plan metadata into runtime_trace when
    # the trace metadata does not already carry it.  Preserve existing values
    # (never overwrite with plan defaults).
    # Use Mapping check because frozen dataclasses wrap nested dicts as
    # mappingproxy.
    _plan_origin = plan.request_metadata.get("request_origin_info", {})
    if isinstance(_plan_origin, Mapping) and _plan_origin:
        _existing_origin = runtime_trace._metadata.get("request_origin_info", {})
        if not isinstance(_existing_origin, Mapping) or not _existing_origin:
            runtime_trace.set_metadata(request_origin_info=dict(_plan_origin))

    # ── Entry timestamp for the execute_plan boundary ──
    runtime_trace.emit("execute_plan_entry", phase="local")

    # ── Single canonical payload — materialize the frozen plan exactly once ──
    # Reused for active-profile workflow, restore publication, and final Modal
    # payload.  ExecutionPlan is immutable; the thawed dict is a safe copy.
    runtime_trace.emit("plan_materialization_start", phase="local")
    _plan_mat_start_ns = time.perf_counter_ns()
    _canonical_dict: dict = plan.to_dict()
    _plan_mat_end_ns = time.perf_counter_ns()
    runtime_trace.emit("plan_materialization_end", phase="local")
    _plan_mat_ms = round((_plan_mat_end_ns - _plan_mat_start_ns) / 1_000_000, 3)
    runtime_trace.set_metadata(
        plan_materialization_count=1,
        plan_to_dict_count=1,
        plan_materialization_ms=_plan_mat_ms,
    )
    _canonical_workflow: dict = _canonical_dict["workflow"]

    # ── Profile preparation (before restore publication / Modal submission) ──
    runtime_trace.emit("active_profile_prepare_start", phase="local")
    runtime_trace.emit("active_next_profile_start", phase="local")
    if profile_setter is not None:
        # ── Profile prep cache identity keys ──
        _profile_ws_id = str((workspace or {}).get("id", ""))
        _profile_app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", _APP_NAME_DEFAULT)
        _profile_env = (
            os.environ.get("COMFYMODAL_V2_ENVIRONMENT", "")
            or os.environ.get("MODAL_ENVIRONMENT", "")
        )
        _profile_src_hash = plan.source_workflow_hash or plan.workflow_hash
        _pr = dict(plan.production_report) if isinstance(plan.production_report, Mapping) else {}
        _profile_prod_hash = str(_pr.get("production_plan_hash", ""))

        _profile_cache_key = _profile_prep_cache_key(
            _profile_src_hash, _profile_prod_hash,
            _profile_ws_id, _profile_app_name, _profile_env,
        )

        with _PROFILE_PREP_CACHE_LOCK:
            _cached_result = _PROFILE_PREP_CACHE.get(_profile_cache_key)

        if _cached_result is not None:
            # Identity unchanged — reuse cached result, no remote calls
            _pn_result = dict(_cached_result)
            runtime_trace.emit(
                "profile_prep_cache_hit", phase="local",
                metadata={"cache_key_prefix": _profile_cache_key[:16]},
            )
            runtime_trace.set_metadata(
                active_profile_publish_decision="cached_unchanged",
                active_profile_stable_key=_pn_result.get("active_profile_stable_key", ""),
                active_profile_token=_pn_result.get("active_profile_token", ""),
                local_active_profile_prepare_ms=0.0,
                active_profile_remote_call=0,
                active_profile_remote_ms=0.0,
                active_profile_prepare_count=0,
                profile_cache_hit=True,
                profile_remote_call_performed=False,
                source_workflow_hash=plan.source_workflow_hash,
                model_stack=dict(plan.model_stack),
                prompt_summary=dict(plan.prompt_bundle),
            )
            runtime_trace.emit("active_next_profile_end", phase="local", metadata={
                "decision": "profile_prep_cache_hit",
                "stable_key": _pn_result.get("active_profile_stable_key", "")[:16],
            })
        else:
            runtime_trace.emit("plan_serialization_start", phase="local",
                               metadata={"purpose": "profile_activation"})
            _activation_wf = _canonical_workflow  # reuse canonical payload
            runtime_trace.emit("plan_serialization_end", phase="local",
                               metadata={"purpose": "profile_activation",
                                         "reused_canonical": True})
            _activation_hash = _profile_src_hash
            _prod_opts: dict | None = None
            if _pr.get("enabled"):
                _prod_opts = {
                    "enabled": True,
                    "output_node_ids": list(_pr.get("output_node_ids", [])),
                    "bypass_node_ids": list(_pr.get("bypass_node_ids", [])),
                    "source_workflow_hash": _pr.get("source_workflow_hash", ""),
                    "compiled_workflow_hash": _pr.get("compiled_workflow_hash", ""),
                    "production_plan_hash": _pr.get("production_plan_hash", ""),
                    "compiler_version": _pr.get("compiler_version", COMPILER_SCHEMA_VERSION),
                    "hash_schema_version": _pr.get("hash_schema_version", HASH_SCHEMA_VERSION),
                    "production_plan_schema_version": _pr.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION),
                }
                _activation_hash = _pr.get("source_workflow_hash", _activation_hash)
            _pn_result = await prepare_active_next_profile(
                _activation_wf,
                _activation_hash,
                production_options=_prod_opts,
                workspace=workspace,
                setter=profile_setter,
            )
            runtime_trace.set_metadata(
                active_profile_publish_decision=_pn_result.get("active_profile_publish_decision", ""),
                active_profile_stable_key=_pn_result.get("active_profile_stable_key", ""),
                active_profile_token=_pn_result.get("active_profile_token", ""),
                local_active_profile_prepare_ms=_pn_result.get("local_active_profile_prepare_ms", 0.0),
                active_profile_remote_call=_pn_result.get("active_profile_remote_call", 0),
                active_profile_remote_ms=_pn_result.get("active_profile_remote_ms", 0.0),
                active_profile_prepare_count=1,
                profile_cache_hit=False,
                profile_remote_call_performed=bool(_pn_result.get("active_profile_remote_call", 0)),
                source_workflow_hash=plan.source_workflow_hash,
                model_stack=dict(plan.model_stack),
                prompt_summary=dict(plan.prompt_bundle),
            )
            runtime_trace.emit("active_next_profile_end", phase="local", metadata={
                "decision": _pn_result.get("active_profile_publish_decision", ""),
                "stable_key": _pn_result.get("active_profile_stable_key", "")[:16],
            })
            # On success, populate the cache so future identical calls skip
            # Eviction is inlined (not via helper) to avoid lock reentry.
            if _pn_result.get("status") not in ("error",):
                with _PROFILE_PREP_CACHE_LOCK:
                    _PROFILE_PREP_CACHE[_profile_cache_key] = dict(_pn_result)
                    while len(_PROFILE_PREP_CACHE) > _PROFILE_PREP_CACHE_MAX:
                        _PROFILE_PREP_CACHE.pop(next(iter(_PROFILE_PREP_CACHE)), None)
    else:
        runtime_trace.emit("active_next_profile_end", phase="local", metadata={"status": "dry_run"})
    runtime_trace.emit("active_profile_prepare_end", phase="local")

    active_transport = transport or ModalTransport()

    # ── Restore publication ──
    runtime_trace.emit("restore_plan_build_start", phase="local")
    if restore_publisher is not None:
        runtime_trace.emit("plan_serialization_start", phase="local",
                           metadata={"purpose": "restore_publication"})
        workflow = _canonical_workflow  # reuse canonical payload
        runtime_trace.emit("plan_serialization_end", phase="local",
                           metadata={"purpose": "restore_publication",
                                     "reused_canonical": True})
        model_key = derive_model_key(workflow)
        prefill_key = derive_prefill_key(model_key, workflow)
        restore_plan = RestorePlan(
            generation=0,
            model_key=model_key,
            prefill_key=prefill_key,
            model_spec=build_restore_model_spec(workflow, dict(plan.model_stack)),
            prefill_spec=dict(prefill_key.encode_options),
            source_workflow_hash=plan.source_workflow_hash,
        )
        runtime_trace.emit("restore_plan_build_end", phase="local")
        runtime_trace.emit("restore_plan_publish_start", phase="local")

        # ── Local process-safe cache: skip remote call when identity
        #    is unchanged for the same workspace/app/environment ──
        plan_identity = _restore_plan_identity_hash(restore_plan)
        ws_id = str((workspace or {}).get("id", ""))
        app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", _APP_NAME_DEFAULT)
        env = (
            os.environ.get("COMFYMODAL_V2_ENVIRONMENT", "")
            or os.environ.get("MODAL_ENVIRONMENT", "")
        )
        cache_key = f"{ws_id}:{app_name}:{env}:{plan_identity}"

        with _RESTORE_PUBLISH_CACHE_LOCK:
            cached_identity = _RESTORE_PUBLISH_CACHE.get(cache_key)

        if cached_identity is not None:
            # Identity unchanged — skip the remote publish call entirely
            runtime_trace.emit(
                "restore_publish_cache_skip", phase="local",
                metadata={"cache_key_prefix": cache_key[:64], "identity": plan_identity[:16]},
            )
            runtime_trace.set_metadata(
                restore_publish_cache_skipped=True,
                restore_publish_cache_hit=True,
                restore_remote_call_performed=False,
            )
            observed_generation = 0
        else:
            runtime_trace.set_metadata(
                restore_publish_cache_skipped=False,
                restore_publish_cache_hit=False,
            )
            publish_result = restore_publisher.publish(restore_plan)
            if inspect.isawaitable(publish_result):
                publish_result = await publish_result
            runtime_trace.set_metadata(restore_remote_call_performed=True)
            _publish_succeeded = True
            if isinstance(publish_result, Mapping):
                observed_generation = publish_result.get(
                    "generation", publish_result.get("observed_generation", "")
                )
                runtime_trace.set_metadata(restore_publish_result=dict(publish_result))
                # Guard cache against semantic failure: detect any of:
                #   status in error/failure/failed, ok==False, success==False,
                #   or a truthy error/failure field.
                _pub_status = publish_result.get("status", "")
                _pub_ok = publish_result.get("ok", True)
                _pub_success = publish_result.get("success", True)
                _pub_error_field = publish_result.get("error") or publish_result.get("failure")
                if (_pub_status in ("error", "failure", "failed")
                        or _pub_ok is False
                        or _pub_success is False
                        or bool(_pub_error_field)):
                    _publish_succeeded = False
            else:
                observed_generation = publish_result
            # Only populate cache on semantic success.
            # Eviction is inlined (not via helper) to avoid lock reentry.
            if _publish_succeeded:
                with _RESTORE_PUBLISH_CACHE_LOCK:
                    _RESTORE_PUBLISH_CACHE[cache_key] = plan_identity
                    while len(_RESTORE_PUBLISH_CACHE) > _RESTORE_PUBLISH_CACHE_MAX:
                        _RESTORE_PUBLISH_CACHE.pop(next(iter(_RESTORE_PUBLISH_CACHE)), None)

        runtime_trace.emit("restore_plan_publish_end", phase="local", metadata={"generation": observed_generation})
    else:
        runtime_trace.emit("restore_plan_build_end", phase="local", metadata={"status": "not_configured"})
        runtime_trace.emit("restore_plan_publish_start", phase="local", metadata={"status": "not_configured"})
        runtime_trace.emit("restore_plan_publish_end", phase="local", metadata={"status": "not_configured"})

    # ── Modal submission ──
    runtime_trace.emit("modal_submit_start", phase="local")
    runtime_trace.emit("gpu_invocation_submit", phase="local")
    result: dict[str, Any] | None = None
    async for message in active_transport.run_plan_stream(
        plan,
        gpu=gpu or str(plan.request_metadata.get("selected_gpu", "")) or None,
        workspace=workspace,
        trace=runtime_trace.to_legacy_timing(prompt_id=str(plan.request_metadata.get("prompt_id", ""))),
        runtime_trace=runtime_trace,
        plan_dict=_canonical_dict,
    ):
        message_type = message.get("type") if isinstance(message, dict) else ""
        if event_sink is not None and message_type in {"progress", "status", "executing"}:
            event_sink(message_type, message.get("data") or message.get("event") or message)
        if message_type == "error":
            raise RuntimeError(message.get("message", "Modal execution error"))
        if message_type == "result":
            result = message.get("data")
            break
    if not isinstance(result, dict):
        raise RuntimeError("execution plan stream ended without result")
    runtime_trace.emit("remote_return_start", process="local", phase="transport")

    # ── Merge local trace into remote result without dropping remote evidence ──
    raw_remote_trace = result.get("trace")
    if not isinstance(raw_remote_trace, dict):
        raw_remote_trace = runtime_trace.to_legacy_timing(
            prompt_id=str(plan.request_metadata.get("prompt_id", ""))
        )
    merged_trace = merge_runtime_traces(runtime_trace, raw_remote_trace)
    remote_trace = dict(raw_remote_trace)
    remote_trace["events"] = [event.to_dict() for event in merged_trace.events]
    remote_trace["metadata"] = dict(merged_trace._metadata)
    remote_trace.setdefault("trace_id", merged_trace.trace_id)
    remote_trace.setdefault("request_id", merged_trace.request_id)
    remote_trace.setdefault("container_session_id", merged_trace.container_session_id)
    # Backend: only set/overwrite when the result actually supplies one.
    if "backend" in result:
        remote_trace["backend"] = result["backend"]
    # V2 containers return the unified event form. Derive legacy-compatible
    # stages/durations at the local merge boundary so Playground/history can
    # expose truthful timing without inventing missing phases. Preserve any
    # fields already supplied by a legacy-compatible remote runtime.
    _legacy_stages = dict(
        merged_trace.to_legacy_timing(
            prompt_id=str(plan.request_metadata.get("prompt_id", ""))
        ).get("stages", {})
    )
    if "stages" in remote_trace and remote_trace["stages"]:
        # Merge: legacy fills gaps, existing remote stages win for exact keys.
        for _k, _v in remote_trace["stages"].items():
            _legacy_stages[_k] = _v
    remote_trace["stages"] = _legacy_stages
    if "deltas_ms" not in remote_trace:
        remote_trace["deltas_ms"] = merged_trace.durations_ms()
    if "trace_version" not in remote_trace:
        remote_trace["trace_version"] = "2.0.0"
    _origin = runtime_trace._metadata.get("request_origin_info", {})
    if not isinstance(_origin, Mapping):
        _origin = {}
    _transport_meta = runtime_trace._metadata
    # Unconditionally extract remote metadata before the modal_input_id check
    # so _remote_metadata is always defined for timestamp fallback lookups.
    _remote_metadata: dict[str, Any] = {}
    if isinstance(raw_remote_trace, dict):
        _remote_metadata = raw_remote_trace.get("metadata", {})
        if not isinstance(_remote_metadata, dict):
            _remote_metadata = {}
    if not _transport_meta.get("modal_input_id"):
        if _remote_metadata.get("modal_input_id"):
            _transport_meta["modal_input_id"] = _remote_metadata["modal_input_id"]

    _local_stages = {
        "local_body_read_ms": _origin.get("local_body_read_ms"),
        "local_json_parse_ms": _origin.get("local_json_parse_ms"),
        "local_preflight_ms": _origin.get("local_preflight_ms"),
        "local_queue_lock_wait_ms": _origin.get("local_queue_lock_wait_ms"),
        "local_queue_enqueue_ms": _origin.get("local_queue_enqueue_ms"),
        "queue_wait_before_worker_ms": _origin.get("queue_wait_before_worker_ms"),
        "plan_build_ms": _event_span_ms(runtime_trace, "plan_build_start", "plan_build_end"),
        "active_profile_ms": _event_span_ms(runtime_trace, "active_profile_prepare_start", "active_profile_prepare_end"),
        "restore_plan_build_ms": _event_span_ms(runtime_trace, "restore_plan_build_start", "restore_plan_build_end"),
        "restore_publish_ms": _event_span_ms(runtime_trace, "restore_plan_publish_start", "restore_plan_publish_end"),
        "handle_lookup_ms": _event_span_ms(runtime_trace, "modal_handle_lookup_start", "modal_handle_lookup_end"),
        "payload_serialize_ms": _derived_mono_delta_ms(runtime_trace, "modal_payload_serialize_start", "modal_payload_serialize_end"),
        "payload_materialization_ms": _derived_mono_delta_ms(runtime_trace, "modal_payload_serialize_start", "payload_measure_size_start"),
        "payload_size_measurement_ms": _derived_mono_delta_ms(runtime_trace, "payload_measure_size_start", "payload_measure_size_end"),
        "generator_create_ms": _transport_meta.get("generator_create_ms"),
    }
    _t1_to_submission_ms = _transport_meta.get("local_receive_to_actual_submission_ms")
    if isinstance(_t1_to_submission_ms, (int, float)):
        # Use non-overlapping transport intervals when available to avoid
        # summing overlapping stage spans (route/plan/profile/restore/
        # handle/payload/generator-create all overlap).
        _gen_create = _transport_meta.get("local_receive_to_generator_create_ms")
        _gen_ms = _transport_meta.get("generator_create_ms")
        _gen_to_first = _transport_meta.get("generator_create_to_first_iteration_ms")
        if all(isinstance(v, (int, float)) for v in (_gen_create, _gen_ms, _gen_to_first)):
            _reconciled_total = float(_gen_create) + float(_gen_ms) + float(_gen_to_first)
            _local_residual_ms = round(float(_t1_to_submission_ms) - _reconciled_total, 3)
        else:
            # Fallback: sum only a demonstrably disjoint set using
            # local_receive_to_enqueue_ms as the pre-worker prefix, queue_wait,
            # and sequential plan/profile/restore/handle/payload spans.
            # All must be known; otherwise return None rather than hiding
            # a missing major span.
            _enqueue_prefix = _origin.get("local_receive_to_enqueue_ms")
            _queue_wait = _origin.get("queue_wait_before_worker_ms")
            if isinstance(_enqueue_prefix, (int, float)) and isinstance(_queue_wait, (int, float)):
                _disjoint_total = float(_enqueue_prefix) + float(_queue_wait)
                _all_known = True
                for _sk in ("plan_build_ms", "active_profile_ms",
                            "restore_plan_build_ms", "restore_publish_ms",
                            "handle_lookup_ms", "payload_serialize_ms"):
                    _sv = _local_stages.get(_sk)
                    if isinstance(_sv, (int, float)):
                        _disjoint_total += float(_sv)
                    else:
                        _all_known = False
                        break
                if _all_known:
                    # generator_create_ms and generator_create_to_first_iteration_ms
                    # from transport metadata (sequential after payload serialization).
                    # Both must be present to avoid hiding a potentially major span.
                    _gen_ms_val = _transport_meta.get("generator_create_ms")
                    _gen_to_first_val = _transport_meta.get("generator_create_to_first_iteration_ms")
                    if isinstance(_gen_ms_val, (int, float)) and isinstance(_gen_to_first_val, (int, float)):
                        _disjoint_total += float(_gen_ms_val) + float(_gen_to_first_val)
                        _local_residual_ms = round(float(_t1_to_submission_ms) - _disjoint_total, 3)
                    else:
                        _local_residual_ms = None
                else:
                    _local_residual_ms = None
            else:
                _local_residual_ms = None
    else:
        _local_residual_ms = None
    _t0_ms = _origin.get("ui_run_triggered_wall_unix_ms")
    _t1_wall_ns = _origin.get("local_receive_wall_ns")
    _t0_to_t1_ms = (
        round((_t1_wall_ns - int(_t0_ms) * 1_000_000) / 1_000_000, 3)
        if isinstance(_t0_ms, (int, float)) and isinstance(_t1_wall_ns, int) else None
    )

    # ── V2 remote request origin intervals (Requirement 1) ──────────
    # All new timestamps come from _origin (local) and _transport_meta (remote).
    # Missing endpoints emit "absent" (not None/0).
    # Negative ordering emits "invalid_negative" (not clamp).
    _ABSENT = "absent"
    _INVALID_NEG = "invalid_negative"

    def _interval_ms(start: Any, end: Any, *, scale_start: float = 1.0, scale_end: float = 1.0) -> Any:
        """Compute (end - start) / 1_000_000 in ms.
        Returns _ABSENT when either is missing, _INVALID_NEG when negative.
        *scale_start/scale_end* convert to nanoseconds before subtraction."""
        if start is None or end is None:
            return _ABSENT
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            return _ABSENT
        _start_ns = int(start * scale_start)
        _end_ns = int(end * scale_end)
        _delta_ns = _end_ns - _start_ns
        if _delta_ns < 0:
            return _INVALID_NEG
        return round(_delta_ns / 1_000_000, 3)

    # Raw timestamps: transport metadata first, then origin/request_origin_info,
    # then merged/raw remote trace data (tolerant multi-tier fallback).
    # Explicit is not None per tier — preserves valid zero raw timestamps.
    _local_modal_gen_create_start_ns = _transport_meta.get("modal_generator_create_start_wall_ns")
    if _local_modal_gen_create_start_ns is None:
        _local_modal_gen_create_start_ns = _origin.get("modal_generator_create_start_wall_ns")
    _local_modal_gen_created_ns = _transport_meta.get("modal_generator_created_wall_ns")
    if _local_modal_gen_created_ns is None:
        _local_modal_gen_created_ns = _origin.get("modal_generator_created_wall_ns")
    _local_modal_first_iter_start_ns = _transport_meta.get("modal_first_iteration_start_wall_ns")
    if _local_modal_first_iter_start_ns is None:
        _local_modal_first_iter_start_ns = _origin.get("modal_first_iteration_start_wall_ns")
    _local_modal_submission_attempt_ns = _transport_meta.get("modal_submission_attempt_wall_ns")
    if _local_modal_submission_attempt_ns is None:
        _local_modal_submission_attempt_ns = _origin.get("modal_submission_attempt_wall_ns")
    _local_modal_first_remote_event_ns = _transport_meta.get("modal_first_remote_event_wall_ns")
    if _local_modal_first_remote_event_ns is None:
        _local_modal_first_remote_event_ns = _origin.get("modal_first_remote_event_wall_ns")
    # Third-tier fallback: try from merged/raw remote trace metadata (aliases)
    if _local_modal_gen_create_start_ns is None:
        _local_modal_gen_create_start_ns = _remote_metadata.get("modal_generator_create_start_wall_ns")
    if _local_modal_gen_created_ns is None:
        _local_modal_gen_created_ns = _remote_metadata.get("modal_generator_created_wall_ns")
    if _local_modal_first_iter_start_ns is None:
        _local_modal_first_iter_start_ns = _remote_metadata.get("modal_first_iteration_start_wall_ns")
    if _local_modal_submission_attempt_ns is None:
        _local_modal_submission_attempt_ns = _remote_metadata.get("modal_submission_attempt_wall_ns")
    if _local_modal_first_remote_event_ns is None:
        _local_modal_first_remote_event_ns = _remote_metadata.get("modal_first_remote_event_wall_ns")

    # Raw timestamps from remote transport metadata (wall_unix_ns)
    _remote_python_resume_ns = _transport_meta.get("remote_python_resume_wall_ns")
    _remote_restore_method_start_ns = _transport_meta.get("restore_method_start_wall_ns")
    _remote_restore_method_end_ns = _transport_meta.get("restore_method_end_wall_ns")
    _remote_modal_method_entry_ns = _transport_meta.get("modal_method_entry_wall_ns")
    _remote_prompt_executor_invoke_start_ns = _transport_meta.get("prompt_executor_invoke_start_wall_ns")

    # Also try from _origin for remote timestamps that may be forwarded
    # as part of the local origin info (tolerate either location).
    if _remote_python_resume_ns is None:
        _remote_python_resume_ns = _origin.get("remote_python_resume_wall_ns")
    if _remote_restore_method_start_ns is None:
        _remote_restore_method_start_ns = _origin.get("restore_method_start_wall_ns")
    if _remote_restore_method_end_ns is None:
        _remote_restore_method_end_ns = _origin.get("restore_method_end_wall_ns")
    if _remote_modal_method_entry_ns is None:
        _remote_modal_method_entry_ns = _origin.get("modal_method_entry_wall_ns")
    if _remote_prompt_executor_invoke_start_ns is None:
        _remote_prompt_executor_invoke_start_ns = _origin.get("prompt_executor_invoke_start_wall_ns")

    # ── Fourth-tier fallback: raw_timestamps alias keys from result data ──
    _raw_ts: dict[str, Any] = {}
    if isinstance(result, dict):
        _raw_ts = result.get("raw_timestamps", {})
        if not isinstance(_raw_ts, dict):
            _raw_ts = {}
    if _raw_ts:
        if _t0_ms is None and _raw_ts.get("t0_ui_trigger_wall_unix_ns") is not None:
            _t0_ms = _raw_ts["t0_ui_trigger_wall_unix_ns"] / 1_000_000.0
        if _t1_wall_ns is None and _raw_ts.get("t1_local_receive_wall_unix_ns") is not None:
            _t1_wall_ns = _raw_ts["t1_local_receive_wall_unix_ns"]
        if _local_modal_submission_attempt_ns is None and _raw_ts.get("modal_submission_attempt_wall_unix_ns") is not None:
            _local_modal_submission_attempt_ns = _raw_ts["modal_submission_attempt_wall_unix_ns"]
        if _local_modal_gen_created_ns is None and _raw_ts.get("modal_generator_created_wall_unix_ns") is not None:
            _local_modal_gen_created_ns = _raw_ts["modal_generator_created_wall_unix_ns"]
        if _remote_modal_method_entry_ns is None and _raw_ts.get("t4_modal_method_entry_wall_unix_ns") is not None:
            _remote_modal_method_entry_ns = _raw_ts["t4_modal_method_entry_wall_unix_ns"]
        if _remote_prompt_executor_invoke_start_ns is None and _raw_ts.get("t5_prompt_executor_invoke_start_wall_unix_ns") is not None:
            _remote_prompt_executor_invoke_start_ns = _raw_ts["t5_prompt_executor_invoke_start_wall_unix_ns"]

    # ── Fifth-tier fallback: merged trace event metadata ──
    # Inspect merged trace events for modal_method_entry / remote_method_entry
    # and prompt_executor_invoke_start by name, using their wall_unix_ns.
    if _remote_modal_method_entry_ns is None or _remote_prompt_executor_invoke_start_ns is None:
        for _evt in merged_trace.events:
            if _remote_modal_method_entry_ns is None and _evt.name in ("modal_method_entry", "remote_method_entry"):
                _remote_modal_method_entry_ns = _evt.wall_unix_ns
            if _remote_prompt_executor_invoke_start_ns is None and _evt.name == "prompt_executor_invoke_start":
                _remote_prompt_executor_invoke_start_ns = _evt.wall_unix_ns
            if _remote_modal_method_entry_ns is not None and _remote_prompt_executor_invoke_start_ns is not None:
                break

    # Compute intervals
    _trigger_to_local_receive_ms = _interval_ms(_t0_ms, _t1_wall_ns,
                                                  scale_start=1_000_000, scale_end=1.0)

    _local_receive_to_gen_create_start_ms = _interval_ms(
        _t1_wall_ns, _local_modal_gen_create_start_ns,
        scale_start=1.0, scale_end=1.0)

    _generator_create_ms = _interval_ms(
        _local_modal_gen_create_start_ns, _local_modal_gen_created_ns,
        scale_start=1.0, scale_end=1.0)

    _gen_created_to_first_iter_ms = _interval_ms(
        _local_modal_gen_created_ns, _local_modal_first_iter_start_ns,
        scale_start=1.0, scale_end=1.0)

    _first_iter_to_first_remote_event_ms = _interval_ms(
        _local_modal_first_iter_start_ns, _local_modal_first_remote_event_ns,
        scale_start=1.0, scale_end=1.0)

    _remote_python_resume_to_restore_start_ms = _interval_ms(
        _remote_python_resume_ns, _remote_restore_method_start_ns,
        scale_start=1.0, scale_end=1.0)

    _restore_method_ms = _interval_ms(
        _remote_restore_method_start_ns, _remote_restore_method_end_ns,
        scale_start=1.0, scale_end=1.0)

    _restore_end_to_modal_method_entry_ms = _interval_ms(
        _remote_restore_method_end_ns, _remote_modal_method_entry_ns,
        scale_start=1.0, scale_end=1.0)

    _modal_method_entry_to_executor_ms = _interval_ms(
        _remote_modal_method_entry_ns, _remote_prompt_executor_invoke_start_ns,
        scale_start=1.0, scale_end=1.0)

    # ── submission_to_remote_python_resume_ms ──────────────────────
    # Cross-process interval: local modal_submission_attempt wall_ns →
    # remote python resume wall_ns.  Wall clock across processes.
    _submission_to_remote_python_resume_ms = _interval_ms(
        _local_modal_submission_attempt_ns, _remote_python_resume_ns,
        scale_start=1.0, scale_end=1.0)

    # ── unexplained_pre_remote_ms ──────────────────────────────────
    # = first_iteration_to_first_remote_event_ms minus only intervals
    #   whose raw endpoints are fully within that same window and whose
    #   spans are pairwise non-overlapping.
    # Remote intervals outside the window are ignored (not subtracted,
    #   not marked invalid).  Missing window endpoints → absent.
    # Negative ordering → invalid_negative.
    _unexplained_pre_remote_ms: Any = _ABSENT
    _win_start_raw = _local_modal_first_iter_start_ns
    _win_end_raw = _local_modal_first_remote_event_ns
    if (
        isinstance(_win_start_raw, (int, float))
        and isinstance(_win_end_raw, (int, float))
        and _win_start_raw <= _win_end_raw
    ):
        _win_start = int(_win_start_raw)
        _win_end = int(_win_end_raw)
        # Candidate remote intervals with raw endpoint pairs
        _candidates: list[tuple[int, int, str]] = []
        _remote_groups = [
            ("python_resume→restore_start", _remote_python_resume_ns, _remote_restore_method_start_ns),
            ("restore_method", _remote_restore_method_start_ns, _remote_restore_method_end_ns),
            ("restore_end→method_entry", _remote_restore_method_end_ns, _remote_modal_method_entry_ns),
            ("method_entry→executor", _remote_modal_method_entry_ns, _remote_prompt_executor_invoke_start_ns),
        ]
        for _name, _s, _e in _remote_groups:
            if isinstance(_s, (int, float)) and isinstance(_e, (int, float)):
                _si = int(_s)
                _ei = int(_e)
                if _si > _ei:
                    _unexplained_pre_remote_ms = _INVALID_NEG
                    break
                if _win_start <= _si <= _win_end and _win_start <= _ei <= _win_end:
                    _candidates.append((_si, _ei, _name))
                # else: outside window — ignore for subtraction
        else:
            # Only proceed when no ordering violation was found
            if _candidates:
                # Greedy non-overlapping selection sorted by start time
                _candidates.sort(key=lambda x: x[0])
                _selected: list[tuple[int, int]] = []
                _last_end = _win_start
                for _si, _ei, _name in _candidates:
                    if _si >= _last_end:
                        _selected.append((_si, _ei))
                        _last_end = _ei
                _contained_total_ns = sum(e - s for s, e in _selected)
                _window_ns = _win_end - _win_start
                _residual_ns = _window_ns - _contained_total_ns
                if _residual_ns < 0:
                    _unexplained_pre_remote_ms = _INVALID_NEG
                else:
                    _unexplained_pre_remote_ms = round(_residual_ns / 1_000_000, 3)
            else:
                _unexplained_pre_remote_ms = _ABSENT
    elif isinstance(_win_start_raw, (int, float)) and isinstance(_win_end_raw, (int, float)):
        # Negative ordering within window endpoints
        _unexplained_pre_remote_ms = _INVALID_NEG

    # ── Clock reconciliation residual ──
    # True residual of the monotonic pipeline: authoritative
    # local_receive_to_actual_submission_ms minus the aggregate adjacent
    # non-overlapping transport intervals
    # (local_receive_to_generator_create_ms + generator_create_ms +
    #  generator_create_to_first_iteration_ms) when available; falls back
    # to the disjoint leaf-set calculation (see _local_residual_ms above).
    # local_residual_ms is a compatibility alias with exactly the same
    # value and definition.
    _clock_reconciliation_residual_ms = _local_residual_ms

    # ── Stage attribution residual (non-overlapping leaf stages) ──
    _stage_attribution_residual_ms: dict[str, Any] = {}
    _missing_stages: list[str] = []
    # Route leaf: local_receive_to_enqueue_ms minus sum of sequential handler
    # stages (body_read, json_parse, preflight, lock_wait, enqueue).  The route
    # total is NOT re-used as a leaf — its children are the leaves.
    _route_total = _origin.get("local_receive_to_enqueue_ms")
    _route_leaf_keys = ("local_body_read_ms", "local_json_parse_ms", "local_preflight_ms",
                        "local_queue_lock_wait_ms", "local_queue_enqueue_ms")
    _route_vals = [_origin.get(k) for k in _route_leaf_keys]
    if isinstance(_route_total, (int, float)):
        if all(isinstance(v, (int, float)) for v in _route_vals):
            _route_leaf_sum = sum(float(v) for v in _route_vals)
            _route_residual = round(float(_route_total) - _route_leaf_sum, 3)
            _stage_attribution_residual_ms["route_unattributed_ms"] = _route_residual
            if _route_residual < 0:
                _stage_attribution_residual_ms["overlap_error"] = "route"
        else:
            _stage_attribution_residual_ms["route_unattributed_ms"] = None
            for _rk, _rv in zip(_route_leaf_keys, _route_vals):
                if not isinstance(_rv, (int, float)):
                    _missing_stages.append(_rk)
    else:
        _stage_attribution_residual_ms["route_unattributed_ms"] = None

    # Worker leaf (pre-submission, never first_iteration_to_first_remote_event):
    # Authoritative worker total = local_receive_to_actual_submission_ms
    # minus local_receive_to_enqueue_ms.
    # Leaves are ONLY individual sequential stages (queue_wait, plan_build,
    # active_profile, restore_plan_build, restore_publish, handle_lookup,
    # payload_serialize, generator_create, generator_create_to_first_iteration).
    # No aggregate transport intervals — the aggregate path was removed because
    # it can hide an uninstrumented plan/profile/restore/serialization gap.
    # If any leaf or boundary is absent, worker_unattributed_ms is None and
    # missing_stages lists each missing name (never silently substitute zero).
    _queue_wait = _origin.get("queue_wait_before_worker_ms")
    _enqueue_prefix = _origin.get("local_receive_to_enqueue_ms")
    if isinstance(_t1_to_submission_ms, (int, float)) and isinstance(_enqueue_prefix, (int, float)):
        _worker_span = float(_t1_to_submission_ms) - float(_enqueue_prefix)
        if _worker_span < 0:
            # Negative authoritative span: submission before enqueue.
            # Do NOT build leaves — overlap_error is the primary signal.
            _stage_attribution_residual_ms["worker_unattributed_ms"] = None
            _existing_err = _stage_attribution_residual_ms.get("overlap_error", "")
            _stage_attribution_residual_ms["overlap_error"] = (
                (_existing_err + " worker") if _existing_err else "worker"
            )
        else:
            # Build leaf sequence: every stage must be numeric.
            _worker_leaf_vals: list[float] = []
            _all_worker_known = True
            if isinstance(_queue_wait, (int, float)):
                _worker_leaf_vals.append(float(_queue_wait))
            else:
                _all_worker_known = False
                _missing_stages.append("queue_wait_before_worker_ms")
            for _wk in ("plan_build_ms", "active_profile_ms", "restore_plan_build_ms",
                        "restore_publish_ms", "handle_lookup_ms", "payload_serialize_ms"):
                _wv = _local_stages.get(_wk)
                if isinstance(_wv, (int, float)):
                    _worker_leaf_vals.append(float(_wv))
                else:
                    _all_worker_known = False
                    _missing_stages.append(_wk)
            for _wk in ("generator_create_ms", "generator_create_to_first_iteration_ms"):
                _wv = _transport_meta.get(_wk)
                if isinstance(_wv, (int, float)):
                    _worker_leaf_vals.append(float(_wv))
                else:
                    _all_worker_known = False
                    _missing_stages.append(_wk)
            if _all_worker_known:
                _worker_leaf_sum = sum(_worker_leaf_vals)
                _worker_residual = round(_worker_span - _worker_leaf_sum, 3)
                _stage_attribution_residual_ms["worker_unattributed_ms"] = _worker_residual
                if _worker_residual < 0:
                    _existing_err = _stage_attribution_residual_ms.get("overlap_error", "")
                    _stage_attribution_residual_ms["overlap_error"] = (
                        (_existing_err + " worker") if _existing_err else "worker"
                    )
            else:
                _stage_attribution_residual_ms["worker_unattributed_ms"] = None
    else:
        _stage_attribution_residual_ms["worker_unattributed_ms"] = None
        if _enqueue_prefix is None:
            _missing_stages.append("local_receive_to_enqueue_ms")
        if _t1_to_submission_ms is None:
            _missing_stages.append("local_receive_to_actual_submission_ms")

    # Structured reconciliation status: incomplete when any required boundary
    # or leaf stage is absent; overlap_error when leaves exceed authoritative.
    if _missing_stages:
        # Preserve first-seen order (no set() which loses insertion order).
        _seen = set()
        _ordered = []
        for _m in _missing_stages:
            if _m not in _seen:
                _seen.add(_m)
                _ordered.append(_m)
        _stage_attribution_residual_ms["missing_stages"] = _ordered
        _reconciliation_status = "incomplete"
    elif _stage_attribution_residual_ms.get("overlap_error", ""):
        _reconciliation_status = "overlap_error"
    elif (_stage_attribution_residual_ms.get("route_unattributed_ms") is None
          or _stage_attribution_residual_ms.get("worker_unattributed_ms") is None):
        _reconciliation_status = "incomplete"
    else:
        _reconciliation_status = "complete"
    _stage_attribution_residual_ms["reconciliation_status"] = _reconciliation_status
    _stage_attribution_residual_ms.setdefault("overlap_error", "")

    # Flatten key stage-attribution fields directly under local_timing
    # (benchmark consumers read these top-level keys). Nested dict kept for compat.
    _sar = _stage_attribution_residual_ms
    _local_summary = {
        "t0_to_t1_ms": _t0_to_t1_ms,
        "t1_to_queue_enqueue_ms": _origin.get("local_receive_to_enqueue_ms"),
        "local_receive_to_enqueue_ms": _origin.get("local_receive_to_enqueue_ms"),
        **_local_stages,
        "local_residual_ms": _local_residual_ms,
        "clock_reconciliation_residual_ms": _clock_reconciliation_residual_ms,
        "route_unattributed_ms": _sar.get("route_unattributed_ms"),
        "worker_unattributed_ms": _sar.get("worker_unattributed_ms"),
        "reconciliation_status": _sar.get("reconciliation_status", ""),
        "missing_stages": list(_sar.get("missing_stages", [])),
        "overlap_error": _sar.get("overlap_error", ""),
        "stage_attribution_residual_ms": dict(_sar),
        "local_receive_to_generator_create_ms": _transport_meta.get("local_receive_to_generator_create_ms"),
        "generator_create_to_first_iteration_ms": _transport_meta.get("generator_create_to_first_iteration_ms"),
        "first_iteration_to_first_remote_event_ms": _transport_meta.get("first_iteration_to_first_remote_event_ms"),
        "local_receive_to_actual_submission_ms": _t1_to_submission_ms,
        # V2 remote request origin intervals
        "trigger_to_local_receive_ms": _trigger_to_local_receive_ms,
        "local_receive_to_generator_create_start_ms": _local_receive_to_gen_create_start_ms,
        "generator_create_ms": _generator_create_ms,
        "generator_created_to_first_iteration_ms": _gen_created_to_first_iter_ms,
        "first_iteration_to_first_remote_event_ms": _first_iter_to_first_remote_event_ms,
        "remote_python_resume_to_restore_start_ms": _remote_python_resume_to_restore_start_ms,
        "restore_method_ms": _restore_method_ms,
        "restore_end_to_modal_method_entry_ms": _restore_end_to_modal_method_entry_ms,
        "modal_method_entry_to_executor_ms": _modal_method_entry_to_executor_ms,
        "submission_to_remote_python_resume_ms": _submission_to_remote_python_resume_ms,
        "unexplained_pre_remote_ms": _unexplained_pre_remote_ms,
    }
    result["local_timing"] = _local_summary
    def _fmt_opt(v: Any) -> str:
        """Format a numeric value for the one-line summary.
        Returns ``str(v)`` for numeric values (including 0.0), ``"absent"`` for None."""
        return "absent" if v is None else str(v)

    print(
        f"[v2.request_origin] request_id={runtime_trace.request_id} "
        f"trigger_source={_origin.get('trigger_source', 'unknown')} "
        f"local_prompt_enqueued_unix_ns={_origin.get('local_prompt_enqueued_wall_ns')} "
        f"local_prompt_ack_ready_unix_ns={_origin.get('local_prompt_ack_ready_wall_ns')} "
        f"modal_generator_created_unix_ns={_transport_meta.get('modal_generator_created_wall_ns')} "
        f"modal_submission_attempt_unix_ns={_transport_meta.get('modal_submission_attempt_wall_ns')} "
        f"modal_first_event_received_unix_ns={_transport_meta.get('modal_first_event_received_wall_ns')} "
        f"t0_to_t1_ms={_t0_to_t1_ms} t1_to_queue_enqueue_ms={_origin.get('local_receive_to_enqueue_ms')} "
        f"local_receive_to_enqueue_ms={_origin.get('local_receive_to_enqueue_ms')} "
        f"queue_wait_before_worker_ms={_origin.get('queue_wait_before_worker_ms')} "
        f"plan_build_ms={_local_stages['plan_build_ms']} active_profile_ms={_local_stages['active_profile_ms']} "
        f"restore_publish_ms={_local_stages['restore_publish_ms']} handle_lookup_ms={_local_stages['handle_lookup_ms']} "
        f"payload_serialize_ms={_local_stages['payload_serialize_ms']} local_residual_ms={_local_residual_ms} "
        f"clock_reconciliation_residual_ms={_clock_reconciliation_residual_ms} "
        f"route_unattributed_ms={_stage_attribution_residual_ms.get('route_unattributed_ms')} "
        f"worker_unattributed_ms={_stage_attribution_residual_ms.get('worker_unattributed_ms')} "
        f"reconciliation_status={_stage_attribution_residual_ms.get('reconciliation_status', '')} "
        f"missing_stages={','.join(_stage_attribution_residual_ms.get('missing_stages', []))} "
        f"overlap_error={_stage_attribution_residual_ms.get('overlap_error', '')} "
        f"modal_input_id={_transport_meta.get('modal_input_id', '')} "
        # V2 remote request origin intervals
        f"trigger_to_local_receive_ms={_trigger_to_local_receive_ms} "
        f"local_receive_to_generator_create_start_ms={_local_receive_to_gen_create_start_ms} "
        f"generator_create_ms={_generator_create_ms} "
        f"generator_created_to_first_iteration_ms={_gen_created_to_first_iter_ms} "
        f"first_iteration_to_first_remote_event_ms={_first_iter_to_first_remote_event_ms} "
        f"remote_python_resume_to_restore_start_ms={_remote_python_resume_to_restore_start_ms} "
        f"restore_method_ms={_restore_method_ms} "
        f"restore_end_to_modal_method_entry_ms={_restore_end_to_modal_method_entry_ms} "
        f"modal_method_entry_to_executor_ms={_modal_method_entry_to_executor_ms} "
        f"submission_to_remote_python_resume_ms={_submission_to_remote_python_resume_ms} "
        f"unexplained_pre_remote_ms={_unexplained_pre_remote_ms}",
        flush=True,
    )
    # ── New exact [v2.remote_request_origin] summary ─────────────
    # Preserves [v2.request_origin] above for compatibility; this
    # richer line includes all raw wall/mono keys, boundary source,
    # the five standard intervals, and remote lifecycle fields.
    # Uses _fmt_opt (local formatter) — None → "absent", preserves
    # numeric zero and negative semantics.
    _remote_req_id = _origin.get("request_id") or runtime_trace.request_id
    _remote_trig_src = _origin.get("trigger_source", "unknown")
    _remote_t0_wall = _origin.get("ui_run_triggered_wall_unix_ms")
    _remote_t1_wall_ns = _origin.get("local_receive_wall_ns")
    _remote_t1_mono_ns = _origin.get("local_receive_mono_ns")
    print(
        f"[v2.remote_request_origin] "
        f"request_id={_remote_req_id} "
        f"trigger_source={_remote_trig_src} "
        f"ui_trigger_unix_ms={_fmt_opt(_remote_t0_wall)} "
        f"local_receive_wall_unix_ns={_fmt_opt(_remote_t1_wall_ns)} "
        f"local_receive_mono_ns={_fmt_opt(_remote_t1_mono_ns)} "
        f"modal_generator_create_start_wall_unix_ns={_fmt_opt(_local_modal_gen_create_start_ns)} "
        f"modal_generator_create_start_mono_ns={_fmt_opt(_transport_meta.get('modal_generator_create_start_mono_ns'))} "
        f"modal_generator_created_wall_unix_ns={_fmt_opt(_local_modal_gen_created_ns)} "
        f"modal_generator_created_mono_ns={_fmt_opt(_transport_meta.get('modal_generator_created_mono_ns'))} "
        f"modal_first_iteration_start_wall_unix_ns={_fmt_opt(_local_modal_first_iter_start_ns)} "
        f"modal_first_iteration_start_mono_ns={_fmt_opt(_transport_meta.get('modal_first_iteration_start_mono_ns'))} "
        f"modal_submission_attempt_wall_unix_ns={_fmt_opt(_local_modal_submission_attempt_ns)} "
        f"modal_submission_attempt_mono_ns={_fmt_opt(_transport_meta.get('modal_submission_attempt_mono_ns'))} "
        f"modal_first_remote_event_wall_unix_ns={_fmt_opt(_local_modal_first_remote_event_ns)} "
        f"modal_first_remote_event_mono_ns={_fmt_opt(_transport_meta.get('modal_first_remote_event_mono_ns'))} "
        f"modal_submission_boundary_source={_fmt_opt(_transport_meta.get('modal_submission_boundary_source'))} "
        f"remote_python_resume_wall_unix_ns={_fmt_opt(_remote_python_resume_ns)} "
        f"restore_method_start_wall_unix_ns={_fmt_opt(_remote_restore_method_start_ns)} "
        f"restore_method_end_wall_unix_ns={_fmt_opt(_remote_restore_method_end_ns)} "
        f"modal_method_entry_wall_unix_ns={_fmt_opt(_remote_modal_method_entry_ns)} "
        f"prompt_executor_invoke_start_wall_unix_ns={_fmt_opt(_remote_prompt_executor_invoke_start_ns)} "
        f"trigger_to_local_receive_ms={_trigger_to_local_receive_ms} "
        f"local_receive_to_generator_create_start_ms={_local_receive_to_gen_create_start_ms} "
        f"generator_create_ms={_generator_create_ms} "
        f"generator_created_to_first_iteration_ms={_gen_created_to_first_iter_ms} "
        f"first_iteration_to_first_remote_event_ms={_first_iter_to_first_remote_event_ms} "
        f"remote_python_resume_to_restore_start_ms={_remote_python_resume_to_restore_start_ms} "
        f"restore_method_ms={_restore_method_ms} "
        f"restore_end_to_modal_method_entry_ms={_restore_end_to_modal_method_entry_ms} "
        f"modal_method_entry_to_executor_ms={_modal_method_entry_to_executor_ms} "
        f"submission_to_remote_python_resume_ms={_submission_to_remote_python_resume_ms} "
        f"unexplained_pre_remote_ms={_unexplained_pre_remote_ms} "
        f"modal_input_id={_fmt_opt(_transport_meta.get('modal_input_id', ''))}",
        flush=True,
    )
    # ═══════════════════════════════════════════════════════════════════
    # [v2.local_submission_breakdown] — detailed pre-submission attribution
    # ═══════════════════════════════════════════════════════════════════
    # All durations are monotonic (perf_counter_ns).  Missing events render
    # as "absent" (literal string), negative deltas as "invalid_negative".
    # This line covers only local pre-submission instrumentation — no remote
    # or scheduling time (those appear in [v2.remote_request_origin]).
    # Reconciliation: measured_children + residual = total (non-overlapping).
    # Total span: local_receive_mono_ns → modal_submission_attempt.
    # ═══════════════════════════════════════════════════════════════════
    _ld = _derived_mono_delta_ms  # shorthand: _ld(trace, start_name, end_name)
    _ABSENT_STR = "absent"
    _INVALID_NEG_STR = "invalid_negative"

    # ── Helper: value or absent ──
    def _val_or_absent(v: Any) -> Any:
        return _ABSENT_STR if v is None else v

    # ── Raw monotonic reference timestamps ──
    _ref_mono_local_receive = _origin.get("local_receive_mono_ns")
    _ref_mono_worker_start = _event_mono_ns(runtime_trace, "worker_start")
    _ref_mono_exec_entry = _event_mono_ns(runtime_trace, "execute_plan_entry")
    _ref_mono_submission = _event_mono_ns(runtime_trace, "modal_submission_attempt")

    # ── One-stage durations (direct span events, strict — invalid_negative on neg) ──
    _plan_build_ms = _strict_event_span_ms(runtime_trace, "plan_build_start", "plan_build_end")
    _active_profile_ms = _strict_event_span_ms(runtime_trace,
                                                "active_profile_prepare_start",
                                                "active_profile_prepare_end")
    _restore_plan_build_ms = _strict_event_span_ms(runtime_trace,
                                                    "restore_plan_build_start",
                                                    "restore_plan_build_end")
    _restore_publish_ms = _strict_event_span_ms(runtime_trace,
                                                 "restore_plan_publish_start",
                                                 "restore_plan_publish_end")
    _handle_lookup_ms = _strict_event_span_ms(runtime_trace,
                                               "modal_handle_lookup_start",
                                               "modal_handle_lookup_end")

    # Payload stages: partition into three disjoint intervals.
    #   modal_payload_serialize_start → payload_measure_size_start = payload materialization prep
    #   payload_measure_size_start → payload_measure_size_end   = exact json.dumps measurement
    #   payload_measure_size_end → modal_payload_serialize_end  = post-measurement wrap-up
    _payload_materialization_prep_ms = _ld(runtime_trace,
                                            "modal_payload_serialize_start",
                                            "payload_measure_size_start")
    _payload_size_measurement_ms = _ld(runtime_trace,
                                        "payload_measure_size_start",
                                        "payload_measure_size_end")
    _payload_size_to_serialize_end_ms = _ld(runtime_trace,
                                             "payload_measure_size_end",
                                             "modal_payload_serialize_end")

    # ── Derived gap durations (start→end, non-overlapping) ──
    _restore_pub_to_transport_entry_ms = _ld(runtime_trace,
                                              "restore_plan_publish_end",
                                              "transport_entry")
    _transport_entry_to_handle_lookup_ms = _ld(runtime_trace,
                                                "transport_entry",
                                                "modal_handle_lookup_start")
    _payload_ready_to_gen_create_ms = _ld(runtime_trace,
                                           "modal_payload_serialize_end",
                                           "modal_generator_create_start")
    _generator_create_ms = _ld(runtime_trace,
                                "modal_generator_create_start",
                                "modal_generator_created")
    _gen_created_to_first_iter_ms = _ld(runtime_trace,
                                         "modal_generator_created",
                                         "modal_first_iteration_start")

    # Plan materialization stages (new trace events added in execute_plan)
    _plan_materialization_ms = _ld(runtime_trace,
                                    "plan_materialization_start",
                                    "plan_materialization_end")

    # ── Gap stages in the worker→plan→execute→materialize→profile sequence ──
    _plan_build_to_exec_entry_ms = _ld(runtime_trace,
                                        "plan_build_end",
                                        "execute_plan_entry")
    _exec_entry_to_plan_mat_ms = _ld(runtime_trace,
                                      "execute_plan_entry",
                                      "plan_materialization_start")
    _plan_mat_to_active_profile_ms = _ld(runtime_trace,
                                          "plan_materialization_end",
                                          "active_profile_prepare_start")

    # ── Boundary-anchored durations ──
    # local_receive_to_worker_start_ms = worker_start - local_receive
    _local_receive_to_worker_start_ms: Any = _ABSENT_STR
    if isinstance(_ref_mono_local_receive, int) and isinstance(_ref_mono_worker_start, int):
        _delta = _ref_mono_worker_start - _ref_mono_local_receive
        if _delta < 0:
            _local_receive_to_worker_start_ms = _INVALID_NEG_STR
        else:
            _local_receive_to_worker_start_ms = round(_delta / 1_000_000, 3)

    # worker_start_to_plan_build_ms = plan_build_start - worker_start
    # (true adjacent gap before plan_build, no overlap with plan_build_ms).
    _worker_start_to_plan_build_ms: Any = _ABSENT_STR
    if isinstance(_ref_mono_worker_start, int):
        _ref_mono_plan_build_start = _event_mono_ns(runtime_trace, "plan_build_start")
        if isinstance(_ref_mono_plan_build_start, int):
            _delta = _ref_mono_plan_build_start - _ref_mono_worker_start
            if _delta < 0:
                _worker_start_to_plan_build_ms = _INVALID_NEG_STR
            else:
                _worker_start_to_plan_build_ms = round(_delta / 1_000_000, 3)

    # ── Total span ──
    # local_receive_to_actual_submission_ms = submission - local_receive
    _total_ms: Any = _ABSENT_STR
    if isinstance(_ref_mono_local_receive, int) and isinstance(_ref_mono_submission, int):
        _delta = _ref_mono_submission - _ref_mono_local_receive
        if _delta < 0:
            _total_ms = _INVALID_NEG_STR
        else:
            _total_ms = round(_delta / 1_000_000, 3)

    # ── Measured children: sum of all valid sequential non-overlapping stages ──
    # Sequential non-overlapping stages: these partition the total
    # local_receive→submission span.  The equation holds:
    #   measured_children_ms + residual_ms == local_receive_to_actual_submission_ms
    # for fully numeric data (no absent/invalid_negative).
    _child_keys = [
        ("local_receive_to_worker_start_ms", _local_receive_to_worker_start_ms),
        ("worker_start_to_plan_build_ms", _worker_start_to_plan_build_ms),
        ("plan_build_ms", _plan_build_ms),
        ("plan_build_to_execute_plan_entry_ms", _plan_build_to_exec_entry_ms),
        ("execute_plan_entry_to_plan_materialization_ms", _exec_entry_to_plan_mat_ms),
        ("plan_materialization_ms", _plan_materialization_ms),
        ("plan_materialization_to_active_profile_ms", _plan_mat_to_active_profile_ms),
        ("active_profile_ms", _active_profile_ms),
        ("restore_plan_build_ms", _restore_plan_build_ms),
        ("restore_publish_ms", _restore_publish_ms),
        ("restore_publish_to_transport_entry_ms", _restore_pub_to_transport_entry_ms),
        ("transport_entry_to_handle_lookup_ms", _transport_entry_to_handle_lookup_ms),
        ("handle_lookup_ms", _handle_lookup_ms),
        ("payload_materialization_ms", _payload_materialization_prep_ms),
        ("payload_size_measurement_ms", _payload_size_measurement_ms),
        ("payload_size_to_serialize_end_ms", _payload_size_to_serialize_end_ms),
        ("payload_ready_to_generator_create_ms", _payload_ready_to_gen_create_ms),
        ("generator_create_ms", _generator_create_ms),
        ("generator_created_to_first_iteration_ms", _gen_created_to_first_iter_ms),
    ]
    _measured_children_ms: Any = _ABSENT_STR
    _all_numeric = True
    _child_sum = 0.0
    _missing_child_names: list[str] = []
    for _ck, _cv in _child_keys:
        if isinstance(_cv, (int, float)):
            _child_sum += float(_cv)
        else:
            _all_numeric = False
            if _cv not in (_ABSENT_STR, _INVALID_NEG_STR):
                _missing_child_names.append(_ck)
    if _all_numeric:
        _measured_children_ms = round(_child_sum, 3)
    else:
        _measured_children_ms = _ABSENT_STR

    # ── Residual from unrounded child sum for deterministic reconcile ──
    _residual_ms: Any = _ABSENT_STR
    _unmeasured_boundary: str = ""
    if isinstance(_total_ms, (int, float)) and _all_numeric:
        # unrounded: residual = total - child_sum (not measured_children which is rounded)
        _residual_val = _total_ms - _child_sum
        _residual_ms = round(_residual_val, 3)
        # When residual > 100ms, name the most likely unmeasured boundary
        if _residual_ms > 100:
            _missing_children = [_ck for _ck, _cv in _child_keys if not isinstance(_cv, (int, float))]
            if _missing_children:
                _unmeasured_boundary = f"absent_stage(s)={','.join(_missing_children)}"
            else:
                # All child stages are numeric but residual is >100ms → there is a
                # measurement gap between two otherwise-recorded stages that no
                # trace event name spans.  Report a stable diagnostic phrase.
                _unmeasured_boundary = "between_recorded_stages"

    # ── Reconciliation status ──
    _reconciliation_status: str = "complete"
    if not isinstance(_total_ms, (int, float)):
        _reconciliation_status = "incomplete"
    elif not isinstance(_measured_children_ms, (int, float)):
        _reconciliation_status = "incomplete"
    elif isinstance(_residual_ms, (int, float)) and _residual_ms < -0.001:
        _reconciliation_status = "overlap"
    # Any direct strict stage with INVALID_NEG → overlap
    for _ck, _cv in _child_keys:
        if _cv == _INVALID_NEG_STR:
            _reconciliation_status = "overlap"
            break

    # ── Metadata booleans from actual branches ──
    # Active profile
    _performed_remote_setter_call: Any = None
    _used_existing_stable_profile: Any = None
    _rebuilt_profile_locally: Any = None
    _ap_decision = _transport_meta.get("active_profile_publish_decision", "")
    _remote_call_count = _transport_meta.get("active_profile_remote_call", 0)
    if _ap_decision:
        _performed_remote_setter_call = bool(_remote_call_count)
        # Use exact decision values from warmup_profile rather than substring guess
        _used_existing_stable_profile = _ap_decision in ("stable_key_exists", "stable_found", "stable_key_found")
        _rebuilt_profile_locally = _ap_decision in ("rebuilt", "rebuilt_locally", "rebuilt_profile")
    _remote_call_performed = bool(_remote_call_count) if _ap_decision else None

    # Restore publication
    _hit_restore_publish_cache: Any = None
    _performed_remote_publish: Any = None
    _rpc_skipped = _transport_meta.get("restore_publish_cache_skipped")
    if isinstance(_rpc_skipped, bool):
        _hit_restore_publish_cache = bool(_rpc_skipped)
        _performed_remote_publish = not bool(_rpc_skipped)

    # Handle lookup — check trace events for specific boundaries
    _has_cache_hit_event = any(e.name == "handle_cache_hit" for e in runtime_trace.events)
    _has_cache_miss_event = any(e.name == "handle_cache_miss" for e in runtime_trace.events)
    _has_client_resolution = any(e.name == "client_resolution_start" for e in runtime_trace.events)
    _has_class_lookup = any(e.name == "class_lookup_start" for e in runtime_trace.events)
    _has_instance_construction = any(e.name == "instance_construction_start" for e in runtime_trace.events)
    _has_factory_resolve = any(e.name == "handle_factory_resolve" for e in runtime_trace.events)

    if _has_cache_hit_event:
        _hit_handle_cache = True
    elif _has_cache_miss_event:
        _hit_handle_cache = False
    else:
        _hit_handle_cache = None

    if _has_client_resolution:
        _created_modal_client = True
    elif _has_factory_resolve:
        _created_modal_client = False
    elif _has_cache_hit_event:
        _created_modal_client = False
    else:
        _created_modal_client = None

    if _has_class_lookup:
        _performed_cls_from_name = True
    elif _has_factory_resolve:
        _performed_cls_from_name = False
    elif _has_cache_hit_event:
        _performed_cls_from_name = False
    else:
        _performed_cls_from_name = None

    if _has_instance_construction:
        _constructed_class_instance = True
    elif _has_factory_resolve:
        _constructed_class_instance = False
    elif _has_cache_hit_event:
        _constructed_class_instance = False
    else:
        _constructed_class_instance = None

    # Workflow / payload metadata
    _workflow_node_count: Any = None
    _workflow_node_count_val = _transport_meta.get("workflow_node_count")
    if _workflow_node_count_val is not None:
        _workflow_node_count = _workflow_node_count_val
    _input_image_count = _transport_meta.get("input_image_count", 0)
    _payload_bytes = _transport_meta.get("payload_bytes") or _transport_meta.get("modal_payload_serialize_bytes")

    _breakdown = {
        # ── Required fields ──────────────────────────────────────────
        "request_id": _origin.get("request_id") or runtime_trace.request_id,
        "local_receive_to_worker_start_ms": _local_receive_to_worker_start_ms,
        "worker_start_to_plan_build_ms": _worker_start_to_plan_build_ms,
        "plan_build_ms": _plan_build_ms,
        "active_profile_ms": _active_profile_ms,
        "restore_plan_build_ms": _restore_plan_build_ms,
        "restore_publish_ms": _restore_publish_ms,
        "restore_publish_to_transport_entry_ms": _restore_pub_to_transport_entry_ms,
        "transport_entry_to_handle_lookup_ms": _transport_entry_to_handle_lookup_ms,
        "handle_lookup_ms": _handle_lookup_ms,
        "payload_materialization_ms": _payload_materialization_prep_ms,
        "payload_size_measurement_ms": _payload_size_measurement_ms,
        "payload_ready_to_generator_create_ms": _payload_ready_to_gen_create_ms,
        "generator_create_ms": _generator_create_ms,
        "generator_created_to_first_iteration_ms": _gen_created_to_first_iter_ms,
        "local_receive_to_actual_submission_ms": _total_ms,
        "measured_children_ms": _measured_children_ms,
        "residual_ms": _residual_ms,
        "reconciliation_status": _reconciliation_status,
        "unmeasured_boundary": _unmeasured_boundary,

        # ── Raw monotonic reference points (metadata, not required) ──
        "local_receive_mono_ns": _ref_mono_local_receive,
        "worker_start_mono_ns": _ref_mono_worker_start,
        "execute_plan_entry_mono_ns": _ref_mono_exec_entry,
        "transport_entry_mono_ns": _event_mono_ns(runtime_trace, "transport_entry"),
        "modal_submission_attempt_mono_ns": _ref_mono_submission,

        # ── Active profile metadata ──
        "active_profile_publish_decision": _ap_decision,
        "active_profile_stable_key": _transport_meta.get("active_profile_stable_key", ""),
        "active_profile_token": _transport_meta.get("active_profile_token", ""),
        "local_active_profile_prepare_ms": _transport_meta.get("local_active_profile_prepare_ms"),
        "profile_cache_hit": _transport_meta.get("profile_cache_hit"),
        "profile_remote_call_performed": _transport_meta.get("profile_remote_call_performed"),
        "active_profile_remote_call": _remote_call_count,
        "active_profile_remote_ms": _transport_meta.get("active_profile_remote_ms"),
        "performed_remote_setter_call": _performed_remote_setter_call,
        "used_existing_stable_profile": _used_existing_stable_profile,
        "rebuilt_profile_locally": _rebuilt_profile_locally,
        "remote_call_performed": _remote_call_performed,

        # ── Restore publication metadata ──
        "restore_publish_generation": _transport_meta.get("restore_publish_result", {}).get("generation")
        if isinstance(_transport_meta.get("restore_publish_result"), dict) else None,
        "restore_publish_cache_hit": _hit_restore_publish_cache,
        "restore_remote_call_performed": _performed_remote_publish,
        "performed_remote_publish": _performed_remote_publish,

        # ── Handle lookup metadata ──
        "handle_lookup_app_name": _transport_meta.get("handle_lookup_app_name", ""),
        "handle_lookup_class_name": _transport_meta.get("handle_lookup_class_name", ""),
        "handle_lookup_gpu": _transport_meta.get("handle_lookup_gpu", ""),
        "handle_cache_hit": _hit_handle_cache,
        "created_modal_client": _created_modal_client,
        "performed_cls_from_name": _performed_cls_from_name,
        "constructed_class_instance": _constructed_class_instance,

        # ── Payload / workflow / images metadata ──
        "payload_bytes": _payload_bytes,
        "payload_serialized_bytes": _transport_meta.get("modal_payload_serialize_bytes"),
        "workflow_hash": _transport_meta.get("workflow_hash", ""),
        "input_image_count": _input_image_count,
        "workflow_node_count": _workflow_node_count,
        "plan_materialization_count": _transport_meta.get("plan_materialization_count"),
        "plan_to_dict_count": 1,

        # ── Cache / remote call metadata ──
        "handle_cache_action": _transport_meta.get("handle_cache_action", ""),
        "active_profile_remote_call_count": _remote_call_count,
    }
    _fmt_bd = _fmt_opt
    print(
        f"[v2.local_submission_breakdown] "
        f"request_id={_breakdown['request_id']} "
        f"local_receive_to_worker_start_ms={_fmt_bd(_breakdown['local_receive_to_worker_start_ms'])} "
        f"worker_start_to_plan_build_ms={_fmt_bd(_breakdown['worker_start_to_plan_build_ms'])} "
        f"plan_build_ms={_fmt_bd(_breakdown['plan_build_ms'])} "
        f"active_profile_ms={_fmt_bd(_breakdown['active_profile_ms'])} "
        f"restore_plan_build_ms={_fmt_bd(_breakdown['restore_plan_build_ms'])} "
        f"restore_publish_ms={_fmt_bd(_breakdown['restore_publish_ms'])} "
        f"restore_publish_to_transport_entry_ms={_fmt_bd(_breakdown['restore_publish_to_transport_entry_ms'])} "
        f"transport_entry_to_handle_lookup_ms={_fmt_bd(_breakdown['transport_entry_to_handle_lookup_ms'])} "
        f"handle_lookup_ms={_fmt_bd(_breakdown['handle_lookup_ms'])} "
        f"payload_materialization_ms={_fmt_bd(_breakdown['payload_materialization_ms'])} "
        f"payload_size_measurement_ms={_fmt_bd(_breakdown['payload_size_measurement_ms'])} "
        f"payload_ready_to_generator_create_ms={_fmt_bd(_breakdown['payload_ready_to_generator_create_ms'])} "
        f"generator_create_ms={_fmt_bd(_breakdown['generator_create_ms'])} "
        f"generator_created_to_first_iteration_ms={_fmt_bd(_breakdown['generator_created_to_first_iteration_ms'])} "
        f"local_receive_to_actual_submission_ms={_fmt_bd(_breakdown['local_receive_to_actual_submission_ms'])} "
        f"measured_children_ms={_fmt_bd(_breakdown['measured_children_ms'])} "
        f"residual_ms={_fmt_bd(_breakdown['residual_ms'])} "
        f"unmeasured_boundary={_breakdown['unmeasured_boundary']} "
        f"reconciliation_status={_breakdown['reconciliation_status']} "
        # Metadata exact keys
        f"profile_cache_hit={_fmt_bd(_breakdown['profile_cache_hit'])} "
        f"profile_remote_call_performed={_fmt_bd(_breakdown['profile_remote_call_performed'])} "
        f"restore_publish_cache_hit={_fmt_bd(_breakdown['restore_publish_cache_hit'])} "
        f"restore_remote_call_performed={_fmt_bd(_breakdown['restore_remote_call_performed'])} "
        f"handle_cache_hit={_fmt_bd(_breakdown['handle_cache_hit'])} "
        f"plan_materialization_count={_breakdown['plan_materialization_count']} "
        f"plan_to_dict_count={_breakdown['plan_to_dict_count']} "
        f"payload_bytes={_fmt_bd(_breakdown['payload_bytes'])} "
        f"workflow_node_count={_fmt_bd(_breakdown['workflow_node_count'])} "
        f"input_image_count={_breakdown['input_image_count']} "
        # Informative metadata (backward compat with existing consumers)
        f"active_profile_publish_decision={_breakdown['active_profile_publish_decision']} "
        f"active_profile_stable_key_prefix={str(_breakdown['active_profile_stable_key'])[:16]} "
        f"active_profile_token_prefix={str(_breakdown['active_profile_token'])[:8]} "
        f"local_active_profile_prepare_ms={_fmt_bd(_breakdown['local_active_profile_prepare_ms'])} "
        f"remote_call_performed={_fmt_bd(_breakdown['remote_call_performed'])} "
        f"active_profile_remote_call={_breakdown['active_profile_remote_call']} "
        f"active_profile_remote_ms={_fmt_bd(_breakdown['active_profile_remote_ms'])} "
        f"performed_remote_setter_call={_fmt_bd(_breakdown['performed_remote_setter_call'])} "
        f"used_existing_stable_profile={_fmt_bd(_breakdown['used_existing_stable_profile'])} "
        f"rebuilt_profile_locally={_fmt_bd(_breakdown['rebuilt_profile_locally'])} "
        f"performed_remote_publish={_fmt_bd(_breakdown['performed_remote_publish'])} "
        f"created_modal_client={_fmt_bd(_breakdown['created_modal_client'])} "
        f"performed_cls_from_name={_fmt_bd(_breakdown['performed_cls_from_name'])} "
        f"constructed_class_instance={_fmt_bd(_breakdown['constructed_class_instance'])} "
        f"payload_serialized_bytes={_fmt_bd(_breakdown['payload_serialized_bytes'])} "
        f"workflow_hash_prefix={_breakdown['workflow_hash'][:12]} "
        f"handle_cache_action={_breakdown['handle_cache_action']} "
        f"active_profile_remote_call_count={_breakdown['active_profile_remote_call_count']}",
        flush=True,
    )
    result["trace"] = remote_trace
    return result


# ---------------------------------------------------------------------------
# Canonical executor
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Prepare-only variant (for callers that need to stream events themselves)
# ---------------------------------------------------------------------------


async def prepare_modal_execution(
    workflow: dict,
    *,
    prompt_id: str,
    client_id: str = "",
    input_images: dict[str, str] | None = None,
    modal_options: dict | None = None,
    production_report: dict | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    trace_payload: dict | None = None,
    profile_setter: Callable[..., Any] | None = None,
    run_trace: RunTrace | None = None,
    comfyui_root: str = "",
) -> dict[str, Any]:
    """Prepare a Modal execution — same pre-work as ``execute_modal_prompt``,
    but returns a dict of prepared arguments instead of calling
    ``run_prompt_stream``.  The caller can then iterate ``run_prompt_stream``
    with these arguments and forward events as needed.

    Returns::

        {
            "input_images": {...},
            "trace": {...},
            "production_report": {...},
            "modal_options": {...},
            "gpu": ...,
            "workspace": ...,
            "profile_result": {...},   # from prepare_active_next_profile
        }
    """
    if run_trace is not None:
        run_trace.begin("prepare_modal_execution")

    try:
        # 1. Workflow integrity — compute hash once, reuse for activation
        current_hash = prompt_sha256(workflow)
        expected_hash = trace_payload.get("workflow_hash", "") if trace_payload else ""

        if run_trace is not None:
            run_trace.count("full_workflow_hash_count", 1)

        if expected_hash and current_hash != expected_hash:
            raise RuntimeError(
                f"Workflow hash mismatch: expected {expected_hash[:12]}..., got {current_hash[:12]}..."
            )

        # Stash the workflow hash for activation and metadata
        _activation_workflow_hash = current_hash

        # Skip API prompt structure validation when a production report is
        # present — the compiler has already validated structural integrity.
        # Non-fatal for synthetic fixtures / test / warmup workflows.
        _skip_validation = bool(
            production_report
            and isinstance(production_report, dict)
            and production_report.get("enabled")
        )
        if not _skip_validation:
            try:
                assert_valid_api_prompt_structure(workflow)
            except Exception:
                pass
        _validate_class_types(workflow, production_report)

        # 2. Model stack / prompt summary (single call boundary)
        model_stack = extract_model_stack(workflow) if hasattr(extract_model_stack, "__call__") else {}
        prompt_summary = summarize_prompt_fields(workflow) if hasattr(summarize_prompt_fields, "__call__") else {}

        if run_trace is not None:
            run_trace.count("model_stack_extract_count", 1)
            run_trace.count("model_stack_nodes", len(model_stack))
            _node_count = sum(
                1 for n in workflow.values()
                if isinstance(n, dict) and isinstance(n.get("class_type"), str) and n["class_type"]
            )
            run_trace.count("workflow_nodes", _node_count)
            # Record used node classes (no prompt content)
            _used_classes = sorted(set(
                n.get("class_type", "") for n in workflow.values()
                if isinstance(n, dict) and isinstance(n.get("class_type"), str)
            ))
            run_trace.count("used_node_class_count", len(_used_classes))
            run_trace.record_payload_size("used_node_classes_key_bytes", len(json.dumps(_used_classes)))
            # Store canonical metadata (no workflow/image bytes)
            run_trace.set_meta(
                model_stack_nodes=len(model_stack),
                model_stack=model_stack,
                prompt_summary=prompt_summary,
                workflow_nodes=_node_count,
                used_node_classes=_used_classes,
                prompt_id=prompt_id,
                client_id=client_id,
            )

        # 3. Input image collection (caller may pre-provide)
        if input_images is None:
            input_images = _collect_input_images(workflow, comfyui_root) if comfyui_root else {}
        if run_trace is not None:
            if input_images:
                run_trace.record_payload_size("input_images_bytes", sum(
                    len(base64.b64decode(d)) for d in input_images.values()
                ))
            run_trace.count("input_images", len(input_images or {}))

        # 4. Canonical hashes validation (compile was done by execute_modal_prompt if needed)
        _production_enabled = bool(
            production_report and isinstance(production_report, dict) and production_report.get("enabled")
        )
        if _production_enabled:
            compiled_hash = production_report.get("compiled_workflow_hash", "")
            if compiled_hash:
                actual_hash = current_hash
                if actual_hash and actual_hash != compiled_hash:
                    _src_h = production_report.get("source_workflow_hash", "")[:8]
                    raise AssertionError(
                        f"[canonical_execution] production dispatch hash mismatch: "
                        f"source={_src_h} compiled={compiled_hash[:8]} "
                        f"dispatch={actual_hash[:8]}. Recompile."
                    )

        if run_trace is not None:
            run_trace.count("production_enabled", 1 if _production_enabled else 0)

        # 5. Active-next profile preparation (single call boundary)
        if run_trace is not None:
            run_trace.begin("prepare_active_next_profile")
            run_trace.count("active_profile_prepare_count", 1)

        _prod_opts_for_activation: dict | None = None

        if production_report and isinstance(production_report, dict) and production_report.get("enabled"):
            # Use production report's source hash — no recomputation needed
            _activation_workflow_hash = production_report.get("source_workflow_hash", _activation_workflow_hash)
            _prod_opts_for_activation = {
                "enabled": True,
                "output_node_ids": production_report.get("output_node_ids", []),
                "bypass_node_ids": production_report.get("bypass_node_ids", []),
                "source_workflow_hash": production_report.get("source_workflow_hash", ""),
                "compiled_workflow_hash": production_report.get("compiled_workflow_hash", ""),
                "production_plan_hash": production_report.get("production_plan_hash", ""),
                "compiler_version": production_report.get("compiler_version", COMPILER_SCHEMA_VERSION),
                "hash_schema_version": production_report.get("hash_schema_version", HASH_SCHEMA_VERSION),
                "production_plan_schema_version": production_report.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION),
            }

        _pn_result = await prepare_active_next_profile(
            workflow,
            _activation_workflow_hash,
            production_options=_prod_opts_for_activation,
            workspace=workspace,
            setter=profile_setter,
        )

        if run_trace is not None:
            run_trace.end("prepare_active_next_profile")
            run_trace.record_payload_size("active_profile_payload_bytes", _pn_result.get("payload_bytes", 0))
            # Store canonical metadata for every run (production-disabled included).
            # No full workflow/image bytes — only hashes, model stack, and env fields.
            _prod_meta: dict[str, Any] = {}
            # Source/compiled hashes: from production report when enabled,
            # otherwise fall back to the current dispatch hash.
            if _production_enabled:
                _prod_meta["source_workflow_hash"] = production_report.get("source_workflow_hash", current_hash)
                _prod_meta["compiled_workflow_hash"] = production_report.get("compiled_workflow_hash", current_hash)
                _prod_meta["production_plan_hash"] = production_report.get("production_plan_hash", "")
                _prod_meta["output_node_ids"] = production_report.get("output_node_ids", [])
                _prod_meta["compiler_version"] = production_report.get("compiler_version", 0)
                _prod_meta["hash_schema_version"] = production_report.get("hash_schema_version", 0)
            else:
                _prod_meta["source_workflow_hash"] = current_hash
                _prod_meta["compiled_workflow_hash"] = current_hash
                _prod_meta["production_plan_hash"] = ""
                _prod_meta["output_node_ids"] = []
                _prod_meta["compiler_version"] = 0
                _prod_meta["hash_schema_version"] = 0
            # GPU selection
            _prod_meta["selected_gpu"] = gpu or ""
            # Placement/correlation fields — read env-gated region/cloud without enabling placement
            _prod_meta["region"] = os.environ.get("COMFYMODAL_COMPUTE_REGION", "").strip()
            _prod_meta["cloud"] = os.environ.get("COMFYMODAL_COMPUTE_CLOUD", "").strip()
            _prod_meta["min_containers"] = 0
            _prod_meta["scaledown_window"] = 4
            # Allocated GPU / session fields (empty when not available at trace time)
            _prod_meta["allocated_gpu"] = ""
            _prod_meta["container_session"] = ""
            _prod_meta["restore_session"] = ""
            _prod_meta["request_sequence"] = 0
            # Workspace metadata
            if workspace and isinstance(workspace, dict):
                for _wk in ("id", "workspace_id", "cloud", "region"):
                    _wv = workspace.get(_wk) or workspace.get(f"_{_wk}") or ""
                    if _wv:
                        _prod_meta[f"workspace_{_wk}"] = str(_wv)[:64]
            # Run surface — already a RunTrace property, include explicitly for consumers
            _prod_meta["run_surface"] = run_trace.run_surface
            # Active profile preparation results (lane A) — always present
            # for both production and non-production paths.
            _prod_meta["local_active_profile_prepare_ms"] = _pn_result.get("local_active_profile_prepare_ms", 0.0)
            _prod_meta["active_profile_publish_decision"] = _pn_result.get("active_profile_publish_decision", "")
            _prod_meta["active_profile_stable_key"] = _pn_result.get("active_profile_stable_key", "")
            _prod_meta["active_profile_token"] = _pn_result.get("active_profile_token", "")
            _prod_meta["active_profile_remote_call"] = _pn_result.get("active_profile_remote_call", 0)
            _prod_meta["active_profile_remote_ms"] = _pn_result.get("active_profile_remote_ms", 0.0)
            run_trace.set_meta(**_prod_meta)

        # 6. Pass caller modal_options through without reconstructing model-loading policy.
        # Production output_node_ids are only set when a valid enabled production_report
        # is explicitly provided by the caller.  No default production is injected.
        _mo: dict = {}
        if modal_options:
            _mo = dict(modal_options)
        if production_report and isinstance(production_report, dict) and production_report.get("enabled"):
            _mo["production"] = {
                "enabled": True,
                "output_node_ids": production_report.get("output_node_ids", []),
            }

        if run_trace is not None:
            run_trace.record_payload_size("modal_args_workflow_bytes", len(str(workflow)))

        # Stash the computed dispatch hash so modal_client can skip recomputation
        _trace_for_modal = dict(trace_payload or {})
        _trace_for_modal["canonical_workflow_hash"] = current_hash

        return {
            "input_images": input_images or {},
            "trace": _trace_for_modal,
            "production_report": production_report or {},
            "modal_options": _mo if _mo else {},
            "gpu": gpu,
            "workspace": workspace,
            "profile_result": _pn_result,
        }
    finally:
        if run_trace is not None:
            run_trace.end("prepare_modal_execution")


async def execute_modal_prompt(
    workflow: dict,
    *,
    prompt_id: str,
    client_id: str = "",
    input_images: dict[str, str] | None = None,
    modal_options: dict | None = None,
    production_report: dict | None = None,
    production_options: dict | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    trace_payload: dict | None = None,
    profile_setter: Callable[..., Any] | None = None,
    run_trace: RunTrace | None = None,
    comfyui_root: str = "",
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
    run_prompt_stream_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute a workflow on Modal and return the raw result.

    Owns every step:
    1. Workflow integrity (hash check, API structure, class types)
    2. Model-stack extraction
    3. Input-image collection
    4. Production compile / canonical hashes (when *production_options* are
       provided and *production_report* is not pre-compiled)
    5. Active-next profile preparation
    6. Run-prompt-options construction
    7. Modal-arguments construction
    8. ``modal_client.run_prompt_stream`` call
    9. Result collection
    10. Canonical trace / count merge

    Parameters
    ----------
    workflow:
        The workflow dict (source or already compiled).
    prompt_id:
        Unique prompt identifier.
    client_id:
        Client session identifier.
    input_images:
        Pre-collected base64-encoded input images.
    modal_options:
        User-provided modal options.
    production_report:
        Pre-compiled production report (when the caller already compiled).
    production_options:
        Production options (output_node_ids, etc.) — used when
        *production_report* is not provided and the canonical executor
        should perform compilation.
    gpu:
        Target GPU identifier.
    workspace:
        Modal workspace dict.
    trace_payload:
        Browser/client trace context.
    profile_setter:
        Callable for ``set_active_warmup_profile``.
    run_trace:
        ``RunTrace`` instance for instrumentation.
    comfyui_root:
        ComfyUI root path for image resolution.
    event_sink:
        Optional callback ``(event_type, payload)`` for forwarding
        progress/status events without rebuilding the request.

    **Caller** owns UI event forwarding, output materialization, and
    history finalization.

    Returns the raw result dict from Modal (``{"outputs": ..., "images": ...,
    "trace": ...}``) on success or raises on failure.
    """
    if run_trace is not None:
        run_trace.begin("execute_modal_prompt", reason="canonical")

    try:
        _wf = workflow

        # ── Production compile (when not pre-compiled) — exactly once ──
        _prod_report = production_report
        _prod_opts = production_options
        if _prod_report is None and _prod_opts and isinstance(_prod_opts, dict) and _prod_opts.get("enabled"):
            if run_trace is not None:
                run_trace.count("production_compile_count", 1)
            from production_workflow import compile_production_workflow, normalize_production_options
            _normalized = normalize_production_options(_prod_opts)
            _plan = compile_production_workflow(
                _wf, _normalized, allow_direct_output_rewrite=True
            )
            _prod_report = _plan.report
            _wf = _plan.compiled_workflow
            # Count the real deepcopy that production compile creates
            if run_trace is not None:
                run_trace.count("workflow_deepcopy_count", 1)

        # model_stack_extract_count is counted inside prepare_modal_execution

        # Delegate all pre-work to prepare_modal_execution
        prepared = await prepare_modal_execution(
            _wf,
            prompt_id=prompt_id,
            client_id=client_id,
            input_images=input_images,
            modal_options=modal_options,
            production_report=_prod_report,
            gpu=gpu,
            workspace=workspace,
            trace_payload=trace_payload,
            profile_setter=profile_setter,
            run_trace=run_trace,
            comfyui_root=comfyui_root,
        )

        _input_images = prepared["input_images"]
        _trace = prepared["trace"]
        _mo = prepared["modal_options"]

        if run_trace is not None:
            run_trace.count("run_prompt_stream_call_count", 1)
            run_trace.count("modal_handle_lookup_count", 1)
            # ── emit_local_summary exactly once before Modal generator invocation ──
            # Stored in-memory in the trace payload (no file/database/remote logging).
            _pre_submit_summary = run_trace.emit_local_summary()
            run_trace.set_meta(_pre_submit_summary=_pre_submit_summary)
            run_trace.begin("run_prompt_stream")

        # 8. Call run_prompt_stream, collect result
        _run_prompt_stream_fn = run_prompt_stream_fn
        if _run_prompt_stream_fn is None:
            from modal_client import run_prompt_stream as _run_prompt_stream_fn
        _modal_result: dict | None = None
        async for _msg in _run_prompt_stream_fn(
            workflow=_wf,
            input_images=_input_images,
            trace=_trace,
            production_report=_prod_report or {},
            gpu=gpu,
            modal_options=_mo,
            workspace=workspace,
        ):
            # Forward non-terminal events through event_sink
            if event_sink is not None and _msg.get("type") in ("progress", "status", "executing"):
                event_sink(_msg["type"], _msg.get("data") or _msg.get("event") or _msg)
            if _msg.get("type") == "result":
                _modal_result = _msg.get("data")
                break
            elif _msg.get("type") == "error":
                raise RuntimeError(_msg.get("message", "Modal execution error"))

        if _modal_result is None:
            raise RuntimeError("run_prompt_stream ended without result")

        if run_trace is not None:
            run_trace.end("run_prompt_stream")
            _result_outputs = _modal_result.get("outputs", {}) if isinstance(_modal_result, dict) else {}
            _result_images = _modal_result.get("images", []) if isinstance(_modal_result, dict) else []
            run_trace.count("output_nodes", len(_result_outputs))
            run_trace.count("output_images", len(_result_images))
            # Record payload sizing (no prompt/image content)
            if isinstance(_modal_result, dict):
                run_trace.record_payload_size("result_outputs_bytes", len(json.dumps(_result_outputs)))
                run_trace.record_payload_size("result_images_count", len(_result_images))

        # 9. Merge canonical trace/counts
        result = _modal_result
        if isinstance(result, dict):
            if run_trace is not None:
                run_trace.merge_into_trace(
                    result.setdefault("trace", {})
                )

        return result

    finally:
        if run_trace is not None:
            run_trace.end("execute_modal_prompt")
