"""Direct Studio Playground execution service — v2 bounded lane.

Bypasses experiment machinery: matrix compiler, scheduler, leases, journals,
worker pool, multi-cell. Pure single-run path with injectable dependencies.

Usage::

    service = PlaygroundService()
    result = await service.execute(
        preset_id="preset_abc",
        feature_id="txt2img",
        controls={"prompt": "a cat", "seed": 42},
        node_dir="/path/to/node/root",
    )

Every stage is injected so unit tests can substitute fakes for each step.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Both direct and package-relative import paths are needed depending on
# how the module is loaded (spec_from_file_location in tests vs. runtime).
try:
    from comfymodal_runtime.contracts import (  # noqa: F401
        ExecutionOptions,
        ExecutionPlan,
        normalize_output_intent_options,
    )
except ImportError:
    from contracts import ExecutionOptions, ExecutionPlan, normalize_output_intent_options  # noqa: F401

_log = logging.getLogger(__name__)


# ── Result container ───────────────────────────────────────────────────


@dataclass(frozen=True)
class PlaygroundResult:
    """Frozen result from a playground execution.

    Every field is optional — callers destructure what they need.
    """
    status: str = "ok"
    run_id: str = ""
    experiment_id: str = ""
    run_history_id: str = ""
    completed_at: str = ""
    output_paths: tuple[str, ...] = ()
    timings: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    trace_events: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "runId": self.run_id,
            "experimentId": self.experiment_id,
            "runHistoryId": self.run_history_id,
            "completed_at": self.completed_at,
            "output_paths": list(self.output_paths),
            "output_path": self.output_paths[0] if self.output_paths else "",
            "timings": dict(self.timings),
            "meta": dict(self.meta),
            "direct_run": True,
        }

    @classmethod
    def error(cls, message: str) -> PlaygroundResult:
        return cls(status="error", meta={"message": message})


# ── Helpers ────────────────────────────────────────────────────────────


def _safe_event_sink() -> Callable[[str, dict[str, Any]], None]:
    """Return a safe ``send_sync`` event sink, or no-op if PromptServer
    is unavailable.  Created fresh each call to avoid import-time coupling."""
    try:
        from server import PromptServer
        instance = PromptServer.instance
        if instance is not None:
            def _sink(etype: str, payload: dict) -> None:
                try:
                    instance.send_sync(etype, payload)
                except Exception:
                    pass
            return _sink
    except Exception:
        pass
    return lambda _etype, _payload: None


async def _offload_or_await(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Await an async callable directly, or offload a synchronous callable
    to a thread via ``asyncio.to_thread``.

    Injected test fakes may be sync or async — this helper handles both
    transparently.  Detects ``async def`` functions and class instances
    with ``async def __call__``.
    """
    if asyncio.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    # Handle callable class instances (e.g. FakeMaterializeService with async __call__)
    call_method = getattr(fn, '__call__', None)
    if call_method is not None and asyncio.iscoroutinefunction(call_method):
        return await fn(*args, **kwargs)
    return await asyncio.to_thread(fn, *args, **kwargs)


def _jsonable_workflow(workflow: Any) -> Any:
    """Recursively convert a frozen workflow into plain JSON containers.

    Mapping/mappingproxy → dict, tuple/list sequences → list.  Scalars and
    dict insertion order are preserved, the frozen source is never mutated,
    and unknown objects pass through untouched (never stringified).
    """
    if isinstance(workflow, Mapping):
        return {k: _jsonable_workflow(v) for k, v in workflow.items()}
    if isinstance(workflow, (list, tuple)):
        return [_jsonable_workflow(v) for v in workflow]
    return workflow


# ── Injectable contract protocols ──────────────────────────────────────


async def _default_load_preset(
    preset_id: str,
    node_dir: str | os.PathLike,
) -> tuple[dict | None, dict | None, str | None]:
    """Default loader delegates to ``studio_run_adapter.load_preset_and_snapshot``.
    The sync filesystem call is offloaded via ``_offload_or_await``.
    """
    from studio_run_adapter import load_preset_and_snapshot
    preset, snapshot_or_err = await _offload_or_await(
        load_preset_and_snapshot, preset_id, node_dir,
    )
    if preset is None:
        return None, None, snapshot_or_err  # error message
    if not isinstance(snapshot_or_err, dict):
        return None, None, "Snapshot payload is not a dict"
    return preset, snapshot_or_err, None


async def _default_validate(
    preset: dict[str, Any],
    snapshot: dict[str, Any],
    feature_id: str,
) -> str | None:
    """Return an error message or None on success.  Offloaded to thread."""
    from studio_run_adapter import validate_studio_run
    result = await _offload_or_await(
        validate_studio_run, preset, snapshot, feature_id,
    )
    return result.get("error") or None


def _default_build_execution_plan(
    preset: dict[str, Any],
    snapshot: dict[str, Any],
    feature_id: str,
    controls: dict[str, Any],
    *,
    modal_options: dict[str, Any] | None = None,
) -> tuple[ExecutionPlan | None, str | None]:
    """Build a frozen ExecutionPlan from Studio preset/snapshot.

    Returns ``(ExecutionPlan, None)`` on success or
    ``(None, error_message)`` on failure.

    Steps:
    1. Validate controls + snapshot schemas
    2. Deep-copy executable workflow
    3. Repair missing CLIP/VAE inputs
    4. Map nodeBindings → runner slots
    5. Apply control overrides
    6. Resolve production options
    7. Build and return ExecutionPlan
    """
    from studio_run_adapter import (
        _AUTO_DERIVE_CONTROLS,
        _CONTROL_WIDGET_ALIASES,
        _apply_controls_to_workflow,
        _augment_slots_with_auto_derive,
        _derive_output_node_ids,
        _get_executable_workflow,
        _repair_missing_clip_inputs,
        _repair_missing_vae_inputs,
        derive_control_schemas_from_snapshot,
        map_studio_bindings_to_slots,
    )
    from studio_models import validate_controls_against_schema
    from production_workflow import normalize_production_options
    from workflow_metadata import extract_model_stack, prompt_sha256

    effective_modal_options = normalize_output_intent_options(modal_options)
    output_mode = str(effective_modal_options.get("output_mode", "original"))

    # ── 0. Validate controls against snapshot schemas ──
    schemas = derive_control_schemas_from_snapshot(snapshot)
    control_errors = validate_controls_against_schema(controls, schemas, feature_id)
    if control_errors:
        return None, "; ".join(
            f"{e['field']}: {e['message']}" for e in control_errors
        )

    # ── 1. Deep-copy executable workflow ──
    workflow = copy.deepcopy(
        _get_executable_workflow(snapshot.get("apiPromptJson"))
    ) or {}

    # ── 2. Repair legacy missing inputs ──
    _repair_missing_clip_inputs(workflow)
    _repair_missing_vae_inputs(workflow)

    # ── 3. Map bindings to slots ──
    node_bindings = copy.deepcopy(snapshot.get("nodeBindings", {})) or {}
    slots = map_studio_bindings_to_slots(node_bindings)
    slots = _augment_slots_with_auto_derive(slots, workflow)

    # ── 4. Validate slot node IDs exist in the workflow ──
    missing = [
        f"'{sk}' maps to node {sv.get('node_id', '')}"
        for sk, sv in slots.items()
        if sv.get("node_id", "") and sv["node_id"] not in workflow
    ]
    if missing:
        return None, (
            f"Snapshot has node bindings that reference nodes not found in "
            f"the workflow: {', '.join(missing)}. "
            f"Re-bind these slots in the preset wizard."
        )

    # ── 5. Apply control overrides ──
    _apply_controls_to_workflow(workflow, slots, controls)

    # ── 6. Build prompt bundle (custom, from controls) ──
    custom_prompt_bundle: dict[str, Any] = {
        "prompt": controls.get("prompt", ""),
        "negative_prompt": controls.get("negative_prompt", ""),
    }
    for ck, cv in controls.items():
        if ck not in ("prompt", "negative_prompt", "seed", "steps",
                      "guidance", "cfg", "sampler", "scheduler", "denoise"):
            custom_prompt_bundle[ck] = cv

    # ── 7. Studio request metadata ──
    studio_meta = {
        "studio_preset_id": preset.get("id", ""),
        "studio_snapshot_id": snapshot.get("id", ""),
        "studio_feature_id": feature_id,
        "studio_preset_label": preset.get("label", ""),
        "studio_controls": copy.deepcopy(controls or {}),
        "output_mode": output_mode,
        "variant": output_mode,
    }

    # ── 8. Resolve production options and compile when normalized production
    #    is enabled (defaults to enabled for None/{} per normalize_production_options
    #    contract).  Explicit production.enabled=False stays raw.
    _production_options = normalize_production_options(effective_modal_options)
    _production_enabled = _production_options.get("enabled", False)

    output_node_ids = _derive_output_node_ids(
        snapshot,
        _production_options.get("output_node_ids", []),
    )

    if _production_enabled:
        from canonical_execution import build_execution_plan as canonical_build_plan

        production_options = _production_options
        # Derive output_node_ids from caller, snapshot output binding, or nodeBindings
        derived_output_ids = list(output_node_ids)
        if not derived_output_ids:
            return None, (
                "Production is enabled but no output node ID could be derived. "
                "Provide outputNodeId in the snapshot, an output nodeBinding, "
                "or production.output_node_ids in modal_options."
            )

        production_options["output_node_ids"] = derived_output_ids

        # Route through canonical build_execution_plan which compiles the workflow
        # and produces a coherent production report with correct hashes.
        # Pass validate=False since the snapshot workflow may not be a strict
        # API prompt (it may carry graphJson, metadata, etc.).
        plan = canonical_build_plan(
            workflow,
            prompt_id=str(uuid.uuid4().hex[:12]),
            modal_options=effective_modal_options,
            production_options=production_options,
            gpu="",
            request_metadata=studio_meta,
            validate=False,
        )
        # Override request_metadata and prompt_bundle with Studio-specific values.
        plan = ExecutionPlan(
            schema_version=plan.schema_version,
            workflow=plan.workflow,
            workflow_hash=plan.workflow_hash,
            source_workflow_hash=plan.source_workflow_hash,
            production_report=plan.production_report,
            model_stack=plan.model_stack,
            prompt_bundle=custom_prompt_bundle,
            output_node_ids=plan.output_node_ids,
            input_images=plan.input_images,
            execution_options=plan.execution_options,
            request_metadata=studio_meta,
        )
    else:
        # Non-production: build plan directly without compilation.
        # Use the normalized production state for execution_options.
        exec_options = ExecutionOptions(
            production_enabled=_production_options.get("enabled", False),
            output_mode=output_mode,
            output_conversion_options=effective_modal_options.get(
                "output_conversion_options", {}
            ),
        )
        model_stack = extract_model_stack(workflow) if hasattr(extract_model_stack, "__call__") else {}
        plan = ExecutionPlan(
            workflow=workflow,
            workflow_hash=prompt_sha256(workflow),
            model_stack=model_stack,
            prompt_bundle=custom_prompt_bundle,
            output_node_ids=tuple(output_node_ids),
            execution_options=exec_options,
            request_metadata=studio_meta,
        )
    return plan, None


async def _default_execute_plan(
    plan: ExecutionPlan,
    *,
    gpu: Any = None,
    workspace: dict[str, Any] | None = None,
    trace_payload: dict[str, Any] | None = None,
    profile_setter: Callable[..., Any] | None = None,
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
    run_prompt_stream_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute a frozen ExecutionPlan via ``execute_plan``.

    Returns the raw Modal result dict.  Bypasses experiment_runner,
    scheduler, leases, journals, and worker pool.

    * Creates a ``RuntimeTrace`` seeded with *trace_payload* metadata.
    * Uses the shared default restore publisher.
    * If *run_prompt_stream_fn* is supplied (tests/compatibility), injects
      it via ``ModalTransport(prompt_stream_fn=...)``.
    * Delegates profile preparation, restore publication, and Modal
      submission to the canonical v2 executor.
    """
    from canonical_execution import execute_plan
    from comfymodal_runtime.modal_transport import ModalTransport
    from comfymodal_runtime.trace import RuntimeTrace

    _request_id = str(uuid.uuid4().hex[:16])
    if trace_payload:
        _request_id = str(trace_payload.get("prompt_id", _request_id))
    elif plan.workflow_hash:
        _request_id = plan.workflow_hash[:16]
    runtime_trace = RuntimeTrace(
        request_id=_request_id,
        process="local",
    )
    if trace_payload:
        runtime_trace.set_metadata(**trace_payload)

    transport = ModalTransport(prompt_stream_fn=run_prompt_stream_fn) if run_prompt_stream_fn else ModalTransport()
    return await execute_plan(
        plan,
        transport=transport,
        profile_setter=None,
        gpu=gpu,
        workspace=workspace,
        trace=runtime_trace,
        event_sink=event_sink,
    )


async def _default_save_history(
    plan: ExecutionPlan,
    result: dict[str, Any],
    run_history_id: str,
    status: str = "completed",
    completed_at: str = "",
    materialized_paths: list[str] | None = None,
) -> None:
    """Default history writer: records then updates via REGISTRY.

    Only uses ``REGISTRY.history().record_run()`` / ``.update_run()``
    which are pure history storage — no experiment machinery, scheduler,
    leases, journals, or worker pool is created.
    """
    try:
        from experiment_service import REGISTRY
        from datetime import datetime, timezone

        if not completed_at:
            completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        timings: dict[str, Any] = {}
        timings["_run_type"] = "playground_direct"
        if isinstance(result, dict):
            ts = result.get("trace", {}) or {}
            if isinstance(ts, dict):
                stages = ts.get("stages", {}) or {}
                for mk in ("browser_run_click", "studio_route_received",
                           "production_compile_complete", "remote_submit",
                           "first_remote_event", "result_received",
                           "output_materialized"):
                    mv = stages.get(mk)
                    if mv is not None:
                        timings[mk] = mv

                deltas = ts.get("deltas_ms", {}) or {}
                for ck, rk in (("clip_load_ms", "clip_load"),
                               ("clip_encode_ms", "clip_encode"),
                               ("sampling_ms", "sampler"),
                               ("vae_decode_ms", "vae_decode"),
                               ("image_io_ms", "image_io"),
                               ("remote_inference_total_ms", "inference_total")):
                    rv = deltas.get(rk)
                    if rv is not None:
                        timings[ck] = rv

                # v2 profile timings from derived_ms / metadata
                _raw_derived = ts.get("derived_ms")
                _derived = _raw_derived if isinstance(_raw_derived, dict) else {}
                _raw_meta = ts.get("metadata")
                _meta = _raw_meta if isinstance(_raw_meta, dict) else {}
                _v2_build = _derived.get("active_profile_build_ms")
                if _v2_build is not None:
                    timings["active_profile_build_ms"] = _v2_build
                elif isinstance(_meta.get("local_active_profile_prepare_ms"), (int, float)):
                    timings["active_profile_build_ms"] = max(0.0, float(_meta["local_active_profile_prepare_ms"]))
                _v2_call = _derived.get("active_profile_remote_call")
                if _v2_call is not None:
                    timings["active_profile_remote_call"] = _v2_call
                elif _meta.get("active_profile_prepare_count"):
                    timings["active_profile_remote_call"] = int(_meta["active_profile_prepare_count"])
                _v2_remote_ms = _derived.get("active_profile_remote_ms")
                if _v2_remote_ms is not None:
                    timings["active_profile_remote_ms"] = _v2_remote_ms
                elif isinstance(_meta.get("active_profile_remote_ms"), (int, float)):
                    timings["active_profile_remote_ms"] = max(0.0, float(_meta["active_profile_remote_ms"]))

                restore = result.get("_restore_timing", {}) or {}
                rt = restore.get("restore_total_ms")
                if rt is not None:
                    timings["restore_total_ms"] = rt

                if isinstance(result.get("trace"), dict):
                    timings["trace"] = copy.deepcopy(result["trace"])

        # Build meta — from plan request_metadata enriched with controls/ids
        meta: dict[str, Any] = {
            "playground_run": True,
        }
        meta.update(dict(plan.request_metadata))
        meta["requested_controls"] = dict(plan.prompt_bundle)
        meta["experiment_id"] = run_history_id
        meta["workflow_hash"] = plan.workflow_hash

        try:
            serialized_plan = plan.to_dict()
            if isinstance(serialized_plan, dict):
                request_metadata = serialized_plan.get("request_metadata") or {}
                controls = request_metadata.get("studio_controls")
                meta["workflow_json"] = serialized_plan.get("workflow") or {}
                meta["request_json"] = {
                    "controls": controls if isinstance(controls, dict) else {},
                    "prompt_bundle": serialized_plan.get("prompt_bundle") or {},
                    "model_stack": serialized_plan.get("model_stack") or {},
                    "execution_options": serialized_plan.get("execution_options") or {},
                    "request_metadata": request_metadata,
                }
                meta["execution_plan_json"] = serialized_plan
                meta["deployment_identity_json"] = (
                    serialized_plan.get("deployment_identity") or {}
                )
                meta["model_stack"] = serialized_plan.get("model_stack") or {}
        except Exception:
            _log.warning("Failed to serialize plan for history run %s", run_history_id)

        primary_asset_id = ""
        if isinstance(result, dict):
            primary_asset_id = str(result.get("primary_asset_id", "") or "")
        if primary_asset_id:
            meta["primary_asset_id"] = primary_asset_id

        # Extract output paths from result — prefer pre-materialized paths
        # when available (passed by the PlaygroundService after materialization).
        output_paths: list[str] = list(materialized_paths) if materialized_paths else []
        if not output_paths and isinstance(result, dict):
            primary = result.get("primary_output") or result.get("_local_primary_output")
            if (
                isinstance(primary, dict)
                and primary.get("path")
                and not primary_asset_id
                and Path(str(primary["path"])).is_file()
            ):
                output_paths = [Path(str(primary["path"])).name]
        if output_paths:
            meta["output_paths"] = list(output_paths)

        # Extract first output basename for top-level output_path — the
        # frontend normalizer (studio-run-normalizer.js) resolves history
        # images from run.output_path, not meta.output_paths.
        top_level_output_path: str = output_paths[0] if output_paths else ""

        # Record a run in history, then update with timings/meta
        record = REGISTRY.history().record_run(
            kind="playground_run",
            prompt_id=run_history_id,
            status=status,
            started_at=completed_at,
            meta=meta,
        )
        actual_run_id = record.get("run_id", run_history_id) if record else run_history_id

        update_kwargs: dict[str, Any] = {
            "status": status,
            "completed_at": completed_at,
            "timings": timings if timings else None,
            "meta": meta,
        }
        if top_level_output_path:
            update_kwargs["output_path"] = top_level_output_path
        if primary_asset_id:
            update_kwargs["primary_asset_id"] = primary_asset_id
        REGISTRY.history().update_run(actual_run_id, **update_kwargs)
    except Exception:
        _log.warning("Failed to save history for run %s", run_history_id)


def _sync_materialize(
    result: dict[str, Any],
    experiment_id: str,
    studio_output_dir: str | os.PathLike | None = None,
    require_output: bool = False,
    expected_output_node_ids: tuple[str, ...] | list[str] | None = None,
    workspace: dict[str, Any] | None = None,
    gpu: Any = None,
) -> list[str]:
    """Synchronous materialization body — offloaded to thread by
    ``_default_materialize``.

    Does NOT import or use: ``experiment_runner``, ``LocalRemoteInvoker``,
    scheduler, leases, journals, or worker pool.
    """
    if not isinstance(result, dict) or not result.get("outputs"):
        return []
    if studio_output_dir is None:
        from local_artifacts import get_studio_outputs_dir
        out_dir = str(get_studio_outputs_dir())
    else:
        out_dir = str(Path(studio_output_dir))
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # Delegate to result_delivery.materialize_modal_result for actual
    # file writes.  This is a standalone function — no experiment
    # machinery imported.
    from comfymodal_runtime.result_delivery import materialize_modal_result
    mat = materialize_modal_result(
        result,
        output_dir=out_dir,
        prompt_id=experiment_id,
        require_output=require_output,
        expected_output_node_ids=expected_output_node_ids,
    )
    paths = [str(Path(p).name) for p in mat.get("written_files", [])]
    primary = mat.get("primary_output") if isinstance(mat, dict) else None
    if not paths and isinstance(primary, dict):
        result["primary_asset_id"] = primary.get("asset_id", "")
        result["_local_primary_output"] = primary
    descriptors = result.get("asset_descriptors", []) if isinstance(result, dict) else []
    workspace_id = str((workspace or {}).get("id", ""))
    result_mode = str((result or {}).get("output_mode", "original") or "original")
    result_variant = str((result or {}).get("variant", result_mode) or result_mode)
    if isinstance(descriptors, list) and workspace_id:
        try:
            from experiment_service import REGISTRY
            leases = REGISTRY.leases()
            for descriptor in descriptors:
                if not isinstance(descriptor, dict):
                    continue
                asset_id = str(descriptor.get("asset_id", "") or "")
                backend_path = str(descriptor.get("backend_path") or descriptor.get("path") or "")
                if not asset_id or not backend_path:
                    continue
                leases.register_asset(
                    asset_id=asset_id,
                    experiment_id="",
                    cell_key=experiment_id,
                    variant=str(
                        descriptor.get("variant")
                        or descriptor.get("output_mode")
                        or result_variant
                    ),
                    path=f"modal://{workspace_id}|{str(gpu or '')}|{backend_path}",
                    mime_type=str(descriptor.get("mime_type") or "application/octet-stream"),
                    byte_size=int(descriptor.get("byte_count", 0) or 0),
                    content_hash=asset_id,
                    node_id=str(descriptor.get("node_id", "")),
                    output_key=str(descriptor.get("output_key", "")),
                    output_index=int(descriptor.get("output_index", 0) or 0),
                    comparison_side=str(descriptor.get("comparison_side", "")),
                    width=int(descriptor.get("width", 0) or 0),
                    height=int(descriptor.get("height", 0) or 0),
                )
        except Exception:
            _log.warning("Failed to register Playground output assets")
    return paths


async def _default_materialize(
    result: dict[str, Any],
    experiment_id: str,
    cell_key: str = "",
    studio_output_dir: str | os.PathLike | None = None,
    require_output: bool = False,
    expected_output_node_ids: tuple[str, ...] | list[str] | None = None,
    workspace: dict[str, Any] | None = None,
    gpu: Any = None,
) -> list[str]:
    """Save output images to disk and return URL-safe filenames.

    Offloads the synchronous filesystem work to a thread via
    ``asyncio.to_thread`` so the event loop is not blocked by
    ``materialize_modal_result`` or directory creation.

    Standalone materializer — delegates to
    ``result_delivery.materialize_modal_result`` for the actual file
    writes and returns a list of relative filenames matching the shape
    produced by the adapter for response compatibility.

    Does NOT import or use: ``experiment_runner``, ``LocalRemoteInvoker``,
    scheduler, leases, journals, or worker pool.
    """
    return await asyncio.to_thread(
        _sync_materialize,
        result,
        experiment_id,
        studio_output_dir,
        require_output,
        expected_output_node_ids,
        workspace,
        gpu,
    )


# ── PlaygroundService ──────────────────────────────────────────────────


class PlaygroundService:
    """Direct single-run Playground service with injectable dependencies.

    Default production implementations delegate to the existing
    ``studio_run_adapter`` / ``canonical_execution`` modules.  Unit tests
    inject fakes for every stage.

    Usage::

        svc = PlaygroundService()
        result = await svc.execute(
            preset_id="preset_abc",
            feature_id="txt2img",
            controls={"prompt": "a cat"},
            node_dir="/path/to/node/root",
        )

    The full pipeline is:

        load preset/snapshot
            → validate runnability
            → build frozen ExecutionPlan
            → execute (injected)
            → materialize outputs
            → save history
            → return PlaygroundResult
    """

    def __init__(
        self,
        *,
        load_preset_fn: Callable[..., Any] | None = None,
        validate_fn: Callable[..., Any] | None = None,
        build_plan_fn: Callable[..., Any] | None = None,
        execute_plan_fn: Callable[..., Any] | None = None,
        materialize_fn: Callable[..., Any] | None = None,
        save_history_fn: Callable[..., Any] | None = None,
        plan_observer_fn: Callable[[ExecutionPlan], Any] | None = None,
    ) -> None:
        self._load_preset = load_preset_fn or _default_load_preset
        self._validate = validate_fn or _default_validate
        self._build_plan = build_plan_fn or _default_build_execution_plan
        self._execute_plan = execute_plan_fn or _default_execute_plan
        self._materialize = materialize_fn or _default_materialize
        self._save_history = save_history_fn or _default_save_history
        self._plan_observer = plan_observer_fn

    # ── Public entrypoint ──────────────────────────────────────────────

    async def execute(
        self,
        preset_id: str,
        feature_id: str,
        controls: dict[str, Any],
        node_dir: str | os.PathLike,
        *,
        modal_options: dict[str, Any] | None = None,
        gpu: Any = None,
        workspace: dict[str, Any] | None = None,
        trace_ctx: dict[str, Any] | None = None,
        profile_setter: Callable[..., Any] | None = None,
        event_sink: Callable[[str, dict[str, Any]], None] | None = None,
        run_prompt_stream_fn: Callable[..., Any] | None = None,
        studio_output_dir: str | os.PathLike | None = None,
    ) -> dict[str, Any]:
        """Execute a single playground run.

        Returns a dict with the same shape as
        ``direct_studio_run_completion`` for adapter compatibility:
        ``status``, ``runId``, ``experimentId``, ``output_paths``,
        ``timings``, ``meta``, ``production_plan_used``, ``direct_run``.
        On error returns ``{"status": "error", "message": ...}``.

        *event_sink* is forwarded through execution so progress/status
        events reach the frontend via ``PromptServer.send_sync``.
        """
        from datetime import datetime, timezone

        # Build the event sink early — safe no-op when PromptServer absent
        _event_sink = event_sink

        # ── Stage 1: Load preset + snapshot ───────────────────────────
        preset, snapshot, load_err = await _offload_or_await(
            self._load_preset, preset_id, node_dir,
        )
        if preset is None or snapshot is None:
            _log.warning("Playground load failed: %s", load_err)
            return {"status": "error", "message": load_err or "Preset or snapshot not found"}

        # ── Stage 2: Validate runnability ─────────────────────────────
        validate_err = await _offload_or_await(
            self._validate, preset, snapshot, feature_id,
        )
        if validate_err:
            _log.warning("Playground validation failed: %s", validate_err)
            return {"status": "error", "message": validate_err}

        # ── Stage 3: Build frozen ExecutionPlan ───────────────────────
        plan, build_err = await _offload_or_await(
            self._build_plan,
            preset, snapshot, feature_id, controls,
            modal_options=modal_options,
        )
        if plan is None:
            _log.warning("Playground plan build failed: %s", build_err)
            return {"status": "error", "message": build_err or "Plan build failed"}

        # ── Safe check: plan must have a workflow ─────────────────────
        if not plan.workflow:
            return {"status": "error", "message": "ExecutionPlan has no workflow"}

        if self._plan_observer is not None:
            try:
                self._plan_observer(plan)
            except Exception as exc:
                _log.warning("Playground plan observer failed: %s", exc)

        # ── Stage 4: Execute ─────────────────────────────────────────
        exp_id = preset.get("id", preset_id) + "_" + uuid.uuid4().hex[:8]
        trace_payload = dict(trace_ctx or {})
        trace_payload.setdefault("workflow_hash", plan.workflow_hash)
        trace_payload.setdefault("prompt_id", exp_id)

        try:
            result = await self._execute_plan(
                plan,
                gpu=gpu,
                workspace=workspace,
                trace_payload=trace_payload,
                profile_setter=profile_setter,
                event_sink=_event_sink,
                run_prompt_stream_fn=run_prompt_stream_fn,
            )
        except Exception as exc:
            _log.error("Playground execution failed: %s", exc)
            return {"status": "error", "message": str(exc)[:500]}

        # ── Stage 5: Materialize outputs ─────────────────────────────
        output_paths: list[str] = []
        requires_output = bool(plan.execution_options.production_enabled)
        output_required = requires_output or bool(plan.output_node_ids)
        has_remote_output = bool(
            isinstance(result, dict)
            and (
                result.get("outputs")
                or result.get("images")
                or result.get("videos")
                or result.get("primary_output")
            )
        )
        if output_required and not has_remote_output:
            return {"status": "error", "message": "v2 execution returned no output"}
        try:
            if has_remote_output:
                output_paths = await _offload_or_await(
                    self._materialize,
                    result,
                    experiment_id=exp_id,
                    cell_key="playground",
                    studio_output_dir=studio_output_dir,
                    require_output=output_required,
                    expected_output_node_ids=tuple(plan.output_node_ids),
                    workspace=workspace,
                    gpu=gpu,
                )
        except Exception as exc:
            if output_required:
                _log.error("Playground output materialization failed: %s", exc)
                return {"status": "error", "message": str(exc)[:500]}
            _log.warning("Playground output materialization failed (non-fatal)")

        if output_required and not output_paths and not (isinstance(result, dict) and result.get("primary_asset_id")):
            return {"status": "error", "message": "v2 output materialization produced no files"}

        # ── Stage 6: Build timings ────────────────────────────────────
        timings: dict[str, Any] = {}
        timings["_run_type"] = "playground_direct"
        if isinstance(result, dict):
            ts = result.get("trace", {}) or {}
            if isinstance(ts, dict):
                stages = ts.get("stages", {}) or {}
                for mk in ("browser_run_click", "studio_route_received",
                           "production_compile_complete", "remote_submit",
                           "first_remote_event", "result_received",
                           "output_materialized"):
                    mv = stages.get(mk)
                    if mv is not None:
                        timings[mk] = mv

                deltas = ts.get("deltas_ms", {}) or {}
                for ck, rk in (("clip_load_ms", "clip_load"),
                               ("clip_encode_ms", "clip_encode"),
                               ("sampling_ms", "sampler"),
                               ("vae_decode_ms", "vae_decode"),
                               ("image_io_ms", "image_io"),
                               ("remote_inference_total_ms", "inference_total")):
                    rv = deltas.get(rk)
                    if rv is not None:
                        timings[ck] = rv

                # End-to-end from stages
                start = stages.get("browser_run_click")
                end = stages.get("output_materialized")
                if start is not None and end is not None:
                    e2e = round((end - start) * 1000, 2)
                    if e2e >= 0:
                        timings["end_to_end_total_ms"] = e2e

                # v2 profile timings: derived_ms first, then metadata fallback
                _raw_derived = ts.get("derived_ms")
                _derived = _raw_derived if isinstance(_raw_derived, dict) else {}
                _raw_meta = ts.get("metadata")
                _meta = _raw_meta if isinstance(_raw_meta, dict) else {}
                _v2_build = _derived.get("active_profile_build_ms")
                if _v2_build is not None:
                    timings["active_profile_build_ms"] = _v2_build
                elif isinstance(_meta.get("local_active_profile_prepare_ms"), (int, float)):
                    timings["active_profile_build_ms"] = max(0.0, float(_meta["local_active_profile_prepare_ms"]))

                _v2_call = _derived.get("active_profile_remote_call")
                if _v2_call is not None:
                    timings["active_profile_remote_call"] = _v2_call
                elif _meta.get("active_profile_prepare_count"):
                    timings["active_profile_remote_call"] = int(_meta["active_profile_prepare_count"])

                _v2_remote_ms = _derived.get("active_profile_remote_ms")
                if _v2_remote_ms is not None:
                    timings["active_profile_remote_ms"] = _v2_remote_ms
                elif isinstance(_meta.get("active_profile_remote_ms"), (int, float)):
                    timings["active_profile_remote_ms"] = max(0.0, float(_meta["active_profile_remote_ms"]))

            restore = result.get("_restore_timing", {}) or {}
            rt = restore.get("restore_total_ms")
            if rt is not None:
                timings["restore_total_ms"] = rt
                timings["remote_restore_ms"] = rt

            if isinstance(result.get("trace"), dict):
                timings["trace"] = copy.deepcopy(result["trace"])

        timings["trace_available"] = bool(result)
        timings["timing_sources"] = {
            k: "local_server_observed"
            for k in timings
            if k not in ("_run_type", "timing_sources")
        }

        # ── Stage 7: Build meta ───────────────────────────────────────
        meta: dict[str, Any] = dict(plan.request_metadata)
        meta["requested_controls"] = dict(plan.prompt_bundle)
        meta["experiment_id"] = exp_id
        meta["workflow_hash"] = plan.workflow_hash
        # History V2: persist the exact executable workflow at completion so a
        # future Generate-Original can replay it without mutable UI state.
        try:
            if isinstance(plan.workflow, dict):
                meta["workflow_json"] = _jsonable_workflow(plan.workflow)
            elif hasattr(plan.workflow, "items"):
                meta["workflow_json"] = _jsonable_workflow(plan.workflow)
        except Exception:
            pass
        meta["output_count"] = len(output_paths)
        meta["production_plan_used"] = "yes" if plan.execution_options.production_enabled else "no"
        if isinstance(result, dict) and result.get("primary_asset_id"):
            meta["primary_asset_id"] = result["primary_asset_id"]
        if output_paths:
            meta["output_paths"] = list(output_paths)

        # ── Stage 8: Save history (fully delegated to injectable) ─────
        run_history_id = f"play_{uuid.uuid4().hex[:16]}"
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            await self._save_history(
                plan, result, run_history_id,
                status="completed", completed_at=completed_at,
                materialized_paths=output_paths if output_paths else None,
            )
        except Exception:
            _log.warning("Playground history save failed (non-fatal)")

        # ── Stage 9: Return result ────────────────────────────────────
        return {
            "status": "ok",
            "runId": run_history_id,
            "experimentId": exp_id,
            "runHistoryId": run_history_id,
            "completed_at": completed_at,
            "output_paths": output_paths,
            "output_path": output_paths[0] if output_paths else "",
            "primary_asset_id": meta.get("primary_asset_id", ""),
            "timings": timings,
            "trace": copy.deepcopy(result.get("trace", {})) if isinstance(result, dict) else {},
            "meta": meta,
            "direct_run": True,
            "production_plan_used": meta["production_plan_used"],
        }


# ── Convenience factory ────────────────────────────────────────────────


def create_playground_service() -> PlaygroundService:
    """Create a PlaygroundService with default (live) dependencies."""
    return PlaygroundService()
