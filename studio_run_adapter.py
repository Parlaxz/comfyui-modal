"""Backend adapter for Studio preset execution runtime.

Bridges Studio presets/snapshots into the existing experiment
scheduler/runner pipeline.

Key workflows
-------------
1. **Single run** (``POST /comfymodal/studio/run``):
   Load preset + snapshot, validate, build a single-cell compilation
   with the snapshot workflow, mapped bindings, and control overrides.
   Schedule via ``REGISTRY.get_or_create_scheduler`` → ``start()``.

2. **Experiment** (``POST /comfymodal/studio/experiment``):
   Accepts one or more ``presetIds``, loads each + its snapshot,
   validates, builds a multi-workflow spec from the experiment
   definition (prompts, axes), compiles via ``compile_experiment``,
   enriches each checkpoint with its snapshot workflow/slots, and
   schedules a single unified experiment.

Validation steps
----------------
- Each preset exists and is not archived.
- Each snapshot exists, is not archived, and is runnable.
- Requested feature is in ``compatibleFeatures`` for every preset.
- Feature ``featureStatus[featureId].status`` is ``"runnable"``.
- ``apiPromptJson`` is present and truthy.
- For ``object_remove`` / ``object_replace``: blocked with a clear
  reason since image/mask input flow is not yet implemented.

Binding mapping
---------------
Studio ``nodeBindings`` (wizard format):
    ``{"prompt": {"kind": "widget", "nodeId": "7", "widgetName": "text"}}``

Runner slots format:
    ``{"prompt": {"node_id": "7", "field": "text", "path": ["inputs", "text"]}}``
"""
from __future__ import annotations

import copy
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from studio_store import StudioJsonStore, StudioStoreError
from studio_models import _FEATURE_BINDING_KEYS, _KNOWN_FEATURE_IDS

_log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

# Feature IDs whose image/mask input flow is not yet implemented.
# These features are blocked with a run-time reason even when their
# bindings and apiPrompt are present.
_IMAGE_INPUT_FEATURES_UNIMPLEMENTED: set[str] = {"object_remove", "object_replace"}

# Stable error message (no raw exceptions leaked to clients).
_STABLE_INTERNAL_ERROR = "Internal error processing request"


def _get_executable_workflow(api_prompt_json: Any) -> dict[str, Any]:
    """Return the runnable prompt map from stored apiPromptJson payloads."""
    if not isinstance(api_prompt_json, dict):
        return {}
    output = api_prompt_json.get("output")
    workflow = api_prompt_json.get("workflow")
    if isinstance(output, dict) and isinstance(workflow, dict):
        return output
    return api_prompt_json


def _repair_missing_clip_inputs(workflow: dict[str, Any]) -> None:
    """Inject a CLIP loader link for CLIPTextEncode when one unique loader exists."""
    if not isinstance(workflow, dict):
        return
    clip_loader_ids = [
        str(node_id)
        for node_id, node in workflow.items()
        if isinstance(node, dict)
        and node.get("class_type") in ("CLIPLoader", "DualCLIPLoader")
    ]
    if len(clip_loader_ids) != 1:
        return
    clip_ref = [clip_loader_ids[0], 0]
    for node in workflow.values():
        if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if "clip" not in inputs:
            inputs["clip"] = list(clip_ref)


def _repair_missing_vae_inputs(workflow: dict[str, Any]) -> None:
    """Inject a VAE loader link for VAEDecode when one unique loader exists."""
    if not isinstance(workflow, dict):
        return
    vae_loader_ids = [
        str(node_id)
        for node_id, node in workflow.items()
        if isinstance(node, dict)
        and node.get("class_type") == "VAELoader"
    ]
    if len(vae_loader_ids) != 1:
        return
    vae_ref = [vae_loader_ids[0], 0]
    for node in workflow.values():
        if not isinstance(node, dict) or node.get("class_type") != "VAEDecode":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if "vae" not in inputs:
            inputs["vae"] = list(vae_ref)


# ── Public helpers ─────────────────────────────────────────────────────────


def _make_studio_experiment_id() -> str:
    return f"studio_{uuid.uuid4().hex[:16]}"


# ── Load helpers ───────────────────────────────────────────────────────────


def _read_store(path: Path) -> list[dict[str, Any]]:
    """Read a StudioJsonStore, returning [] on missing file."""
    store = StudioJsonStore(path)
    try:
        return store.read()
    except (StudioStoreError, OSError):
        return []


def _build_index(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {e.get("id", ""): e for e in entries if e.get("id")}


# ── Public API: load and validate ──────────────────────────────────────────


def load_preset_and_snapshot(
    preset_id: str, node_dir: str | os.PathLike,
):
    """Load a preset and its referenced snapshot from Studio stores.

    Returns ``(preset, snapshot)`` on success (two-element tuple).

    Returns ``None`` on failure — use :func:`get_load_error` to retrieve
    the most recent error message.
    """
    global _last_load_error
    node_dir = Path(node_dir)
    presets = _read_store(node_dir / ".studio_presets.json")
    snapshots = _read_store(node_dir / ".studio_snapshots.json")

    preset_index = _build_index(presets)
    snapshot_index = _build_index(snapshots)

    preset = preset_index.get(preset_id)
    if preset is None:
        _last_load_error = f"Preset {preset_id!r} not found"
        return None

    if preset.get("archived"):
        _last_load_error = f"Preset {preset_id!r} is archived"
        return None

    snapshot_id = preset.get("snapshotId", "") or ""
    if not snapshot_id:
        _last_load_error = f"Preset {preset_id!r} has no snapshot reference"
        return None

    snapshot = snapshot_index.get(snapshot_id)
    if snapshot is None:
        _last_load_error = f"Snapshot {snapshot_id!r} referenced by preset {preset_id!r} not found"
        return None

    if snapshot.get("archived"):
        _last_load_error = f"Snapshot {snapshot_id!r} referenced by preset {preset_id!r} is archived"
        return None

    return preset, snapshot


_last_load_error: str = ""


def get_load_error() -> str:
    """Return the most recent error message from :func:`load_preset_and_snapshot`."""
    global _last_load_error
    return _last_load_error


def load_presets_and_snapshots(
    preset_ids: list[str], node_dir: str | os.PathLike,
):
    """Load multiple presets and their referenced snapshots.

    Returns ``[(preset, snapshot), ...]`` on success (list of tuples).

    Returns ``None`` on failure — use :func:`get_load_error` to retrieve
    the most recent error message.
    """
    for pid in preset_ids:
        loaded = load_preset_and_snapshot(pid, node_dir)
        if loaded is None:
            return None
    # All loaded — re-read and build full list
    result = []
    for pid in preset_ids:
        loaded = load_preset_and_snapshot(pid, node_dir)
        if loaded is not None:
            result.append(loaded)
    return result


def validate_studio_run(
    preset: dict[str, Any],
    snapshot: dict[str, Any],
    feature_id: str,
) -> dict[str, Any]:
    """Validate runnability for a Studio preset execution.

    Returns ``{"error": "reason"}`` on failure, or ``{}`` (empty dict
    with no ``"error"`` key) on success.

    Checks:
    1. Preset status is ``"runnable"``
    2. Snapshot status is not archived / disabled
    3. Feature is in ``compatibleFeatures``
    4. Snapshot ``featureStatus[featureId].status`` is ``"runnable"``
    5. ``apiPromptJson`` is present and truthy
    6. Object features require image/mask input (blocked)
    """
    errors: list[str] = []

    # Preset-level check
    preset_status = preset.get("status", "")
    if preset_status != "runnable":
        reason = preset.get("disabledReason", "") or preset_status
        errors.append(f"Preset is not runnable: {reason}")

    # Archived snapshot
    if snapshot.get("archived"):
        errors.append("Snapshot is archived")

    # Feature compatibility
    compatible = preset.get("compatibleFeatures", []) or []
    if feature_id not in compatible:
        errors.append(
            f"Feature {feature_id!r} is not in preset compatibleFeatures"
        )

    # Feature-level status
    feature_statuses = snapshot.get("featureStatus", {}) or {}
    fs = feature_statuses.get(feature_id, {})
    if fs.get("status") != "runnable":
        reason = fs.get("reason", "") or fs.get("status", "unknown")
        errors.append(f"Feature {feature_id!r} is not runnable: {reason}")

    # apiPromptJson
    api_prompt = snapshot.get("apiPromptJson")
    if not api_prompt:
        errors.append("Snapshot has no apiPromptJson")

    # Object features with image/mask input are blocked
    if feature_id in _IMAGE_INPUT_FEATURES_UNIMPLEMENTED:
        errors.append(
            f"Feature {feature_id!r} requires image/mask input which is "
            f"not yet implemented in the Studio runtime"
        )

    if errors:
        return {"error": "; ".join(errors)}
    return {}


# ── Defaults extraction ────────────────────────────────────────────────


def extract_defaults_from_snapshot(snapshot: dict) -> dict:
    """Extract flat {controlId: value} from snapshot nodeBindings + apiPromptJson.

    Walks nodeBindings to find the workflow path for each bound control,
    reads the widget/input value from the apiPromptJson workflow, and returns
    a flat dict of {control_id: value}. Handles kind="widget" (uses widgetName)
    and kind="input" (uses inputName). Skips kind="node"/"output" bindings.
    Missing keys are handled gracefully via .get() chains.
    """
    workflow = _get_executable_workflow(snapshot.get("apiPromptJson"))
    bindings = snapshot.get("nodeBindings", {}) or {}
    defaults = {}
    for ctrl_id, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        kind = binding.get("kind", "")
        if kind == "widget":
            name_key = "widgetName"
        elif kind == "input":
            name_key = "inputName"
        else:
            continue  # skip "node" and "output" kinds
        node_id = binding.get("nodeId", "")
        widget_name = binding.get(name_key, "")
        if not node_id or not widget_name:
            continue
        node = workflow.get(node_id, {})
        inputs = node.get("inputs", {})
        if widget_name in inputs:
            defaults[ctrl_id] = inputs[widget_name]
    return defaults


# ── Binding mapping ────────────────────────────────────────────────────────


def _map_binding_to_slot(
    binding_key: str,
    binding_val: Any,
) -> dict[str, Any] | None:
    """Map a single Studio wizard-format binding to a runner slot dict.

    Wizard format: ``{"kind": "widget", "nodeId": "7", "widgetName": "text"}``
    Runner slot: ``{"node_id": "7", "field": "text", "path": ["inputs", "text"]}``
    """
    if not isinstance(binding_val, dict):
        return None

    kind = binding_val.get("kind", "")
    node_id = str(binding_val.get("nodeId", ""))
    if not node_id:
        return None

    if kind == "widget":
        widget_name = binding_val.get("widgetName", "")
        return {
            "node_id": node_id,
            "field": widget_name,
            "path": ["inputs", widget_name],
        }
    elif kind == "node":
        field = (
            binding_val.get("widgetName")
            or binding_val.get("inputName")
            or "value"
        )
        return {
            "node_id": node_id,
            "field": field,
            "path": ["inputs", field],
        }
    elif kind == "output":
        return {
            "node_id": node_id,
            "field": "images",
            "path": ["outputs", "images"],
        }
    elif kind == "input":
        return {
            "node_id": node_id,
            "field": binding_key,
            "path": ["inputs", binding_key],
        }
    return None


def map_studio_bindings_to_slots(
    node_bindings: dict[str, Any],
) -> dict[str, Any]:
    """Map Studio ``nodeBindings`` to runner slot format.

    Returns a dict with keys matching the binding keys and values
    in the runner slot format (``node_id``, ``field``, ``path``).
    Unmappable bindings are silently dropped.
    """
    if not isinstance(node_bindings, dict):
        return {}
    slots: dict[str, Any] = {}
    for key, val in node_bindings.items():
        slot = _map_binding_to_slot(key, val)
        if slot is not None:
            slots[key] = slot
    return slots


# ── Control application ────────────────────────────────────────────────────


def _apply_controls_to_workflow(
    workflow: dict[str, Any],
    slots: dict[str, Any],
    controls: dict[str, Any],
) -> None:
    """Apply control overrides to a deep-copied workflow in place.

    Each control key is looked up in *slots*; if found, the slot's
    path is used to set the value in the workflow.  Unrecognized
    control keys are silently ignored.
    """
    for key, value in controls.items():
        slot = slots.get(key)
        if not isinstance(slot, dict):
            slot = slots.get(key.lower())
        if not isinstance(slot, dict):
            continue
        node_id = slot.get("node_id", "")
        path = slot.get("path", [])
        if not node_id or not path:
            continue
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            continue
        target = node
        for segment in path[:-1]:
            if isinstance(target, dict) and segment in target:
                target = target[segment]
            else:
                break
        else:
            if isinstance(target, dict) and path[-1] in target:
                target[path[-1]] = value


# ── History metadata ───────────────────────────────────────────────────────


def _build_studio_history_meta(
    preset_id: str,
    snapshot_id: str,
    feature_id: str,
    controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build metadata dict for run history, carrying Studio info."""
    return {
        "studio_preset_id": preset_id,
        "studio_snapshot_id": snapshot_id,
        "studio_feature_id": feature_id,
        "studio_controls": dict(controls or {}),
    }


def _build_studio_experiment_meta(
    preset_ids: list[str],
    snapshot_ids: list[str],
    feature_id: str,
) -> dict[str, Any]:
    """Build metadata dict for experiment definition, carrying Studio info."""
    return {
        "studio_preset_ids": preset_ids,
        "studio_snapshot_ids": snapshot_ids,
        "studio_feature_id": feature_id,
    }


# ── Spec / compilation building ────────────────────────────────────────────


def build_single_run_spec(
    preset: dict[str, Any],
    snapshot: dict[str, Any],
    feature_id: str,
    controls: dict[str, Any],
    node_dir: str | os.PathLike,
) -> dict[str, Any]:
    """Build a compilation-like spec for a single Studio run.

    Returns a dict with experiment_id, checkpoints, cells, and studio_meta.
    May return ``{"error": "reason"}`` if validation fails.

    Steps:
    1. Validate the run first.
    2. Deep-copy snapshot ``apiPromptJson`` as the workflow.
    3. Map ``nodeBindings`` to runner slot format.
    4. Apply control overrides to the deep-copied workflow.
    5. Build a single-cell compilation.
    6. Attach studio metadata for history.
    """
    # Validate first — ensures build helpers never bypass validation
    validation = validate_studio_run(preset, snapshot, feature_id)
    if validation.get("error"):
        return validation

    exp_id = _make_studio_experiment_id()

    # Deep copy so stored data is never mutated
    workflow = copy.deepcopy(_get_executable_workflow(snapshot.get("apiPromptJson"))) or {}
    _repair_missing_clip_inputs(workflow)
    _repair_missing_vae_inputs(workflow)
    node_bindings = copy.deepcopy(snapshot.get("nodeBindings", {})) or {}

    # Map bindings to slots
    slots = map_studio_bindings_to_slots(node_bindings)

    # Validate all mapped slot node IDs exist in the workflow
    missing = []
    for sk, sv in slots.items():
        nid = sv.get("node_id", "")
        if nid and nid not in workflow:
            missing.append(f"'{sk}' maps to node {nid}")
    if missing:
        return {"error": (
            f"Snapshot has node bindings that reference nodes not found in "
            f"the workflow: {', '.join(missing)}. "
            f"Re-bind these slots in the preset wizard."
        )}

    # Apply control overrides to the deep-copied workflow
    _apply_controls_to_workflow(workflow, slots, controls)

    # Build axis_values from controls (for history)
    axis_values: dict[str, Any] = {}
    for ck, cv in controls.items():
        if ck in ("prompt", "negative_prompt"):
            continue  # These are handled separately
        axis_values[ck] = cv

    checkpoint_id = f"ck_{uuid.uuid4().hex[:8]}"
    cell_key = f"studio_cell_{uuid.uuid4().hex[:8]}"

    studio_meta = _build_studio_history_meta(
        preset_id=preset.get("id", ""),
        snapshot_id=snapshot.get("id", ""),
        feature_id=feature_id,
        controls=controls,
    )

    compilation: dict[str, Any] = {
        "experiment_id": exp_id,
        "revision": 1,
        "checkpoints": [
            {
                "id": checkpoint_id,
                "profile_id": "",
                "loader_target_group_id": "g_default",
                "triple": {"unet": "", "clip": "", "vae": ""},
                "lora_selection_ids": [],
                "cell_count": 1,
                "workflow": workflow,
                "slots": slots,
                "loader_target_groups": [],
                "lora_slots": [],
                "studio_meta": studio_meta,
            }
        ],
        "cells": [
            {
                "cell_key": cell_key,
                "sequence": 0,
                "checkpoint_id": checkpoint_id,
                "profile_id": "",
                "loader_target_group_id": "g_default",
                "triple": {"unet": "", "clip": "", "vae": ""},
                "lora_selection_id": "",
                "lora_signature": [],
                "prompt_id": "studio_prompt",
                "prompt": controls.get("prompt", ""),
                "negative_prompt": controls.get("negative_prompt", ""),
                "image_id": "",
                "axis_values": axis_values,
                "workflow_hash": "",
                "studio_meta": studio_meta,
            }
        ],
        "duplicate_count": 0,
        "warnings": [],
        "studio_meta": studio_meta,
    }

    return compilation


def build_experiment_spec(
    preset_snapshot_pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    feature_id: str,
    experiment_def: dict[str, Any],
    node_dir: str | os.PathLike,
) -> dict[str, Any]:
    """Build a spec for a Studio experiment with matrix expansion.

    Accepts one or more ``(preset, snapshot)`` pairs.  Each preset
    contributes its snapshot workflow as a separate compiler workflow
    entry.  All workflows share the same experiment definition
    (prompts, axes) and are compiled into a single unified experiment.

    Constructs a compiler-compatible spec from the snapshot workflows
    and the experiment definition.  Then compiles it via
    ``compile_experiment`` and enriches checkpoints with snapshot
    workflow/slots.

    Returns a compilation dict on success, or ``{"error": "reason"}``
    on failure.
    """
    if not preset_snapshot_pairs:
        return {"error": "At least one preset is required"}

    node_dir = Path(node_dir)

    # Validate every preset/snapshot first
    for preset, snapshot in preset_snapshot_pairs:
        validation = validate_studio_run(preset, snapshot, feature_id)
        if validation.get("error"):
            return validation

    # Build the compiler spec with one workflow per preset
    spec_workflows: list[dict[str, Any]] = []
    all_preset_ids: list[str] = []
    all_snapshot_ids: list[str] = []

    for idx, (preset, snapshot) in enumerate(preset_snapshot_pairs):
        pid = preset.get("id", "")
        sid = snapshot.get("id", "")
        all_preset_ids.append(pid)
        all_snapshot_ids.append(sid)

        spec_workflows.append({
            "profile_id": f"studio_{pid}_{idx}",
            "loader_target_group_id": "g_default",
            "main_triple": {"id": "main", "unet": "", "clip": "", "vae": ""},
            "subprofile_triples": [],
            "selected_triple_ids": ["main"],
            "lora_slots": [],
        })

    # Build prompts list from experiment_def (avoid double-counting)
    prompts = experiment_def.get("prompts", [])
    spec_prompts = []
    prompt_texts_seen: set[str] = set()
    for p in prompts:
        if not isinstance(p, dict) or not p.get("enabled", True):
            continue
        text = p.get("text", "")
        # Deduplicate by text to avoid prompt double-counting
        if text and text in prompt_texts_seen:
            continue
        if text:
            prompt_texts_seen.add(text)
        spec_prompts.append({
            "id": p.get("id", str(uuid.uuid4().hex[:8])),
            "label": text[:60] if text else "",
            "text": text,
            "negative": p.get("negative", ""),
            "enabled": True,
        })

    axes = experiment_def.get("axes", {}) or {}

    spec: dict[str, Any] = {
        "experiment_id": _make_studio_experiment_id(),
        "revision": 1,
        "name": experiment_def.get("name", f"Studio {feature_id}"),
        "workflows": spec_workflows,
        "prompts": {"items": spec_prompts, "shared_negative": ""},
        "images": {"mode": "cartesian", "items": []},
        "loras": {"selections": [
            {"id": "L_no_lora", "label": "No LoRA", "loras": [], "enabled": True},
        ]},
        "axes": axes,
    }

    # Compile via matrix compiler
    try:
        from matrix_compiler import compile_experiment as _compile
        compilation = _compile(spec)
    except Exception:
        _log.exception("Experiment compilation failed")
        return {"error": "Experiment compilation failed: invalid spec or empty definition"}

    # Build workflow/slot lookup per profile_id
    workflow_map: dict[str, dict] = {}
    slots_map: dict[str, dict] = {}
    for idx, (preset, snapshot) in enumerate(preset_snapshot_pairs):
        profile_id = f"studio_{preset.get('id', '')}_{idx}"
        workflow_map[profile_id] = copy.deepcopy(
            _get_executable_workflow(snapshot.get("apiPromptJson"))
        ) or {}
        _repair_missing_clip_inputs(workflow_map[profile_id])
        _repair_missing_vae_inputs(workflow_map[profile_id])
        slots_map[profile_id] = map_studio_bindings_to_slots(
            copy.deepcopy(snapshot.get("nodeBindings", {})) or {}
        )

    studio_meta = _build_studio_experiment_meta(
        preset_ids=all_preset_ids,
        snapshot_ids=all_snapshot_ids,
        feature_id=feature_id,
    )

    for ck in compilation.get("checkpoints", []):
        pf = ck.get("profile_id", "")
        ck["workflow"] = workflow_map.get(pf, {})
        ck["slots"] = slots_map.get(pf, {})
        ck["loader_target_groups"] = []
        ck["lora_slots"] = []
        ck["studio_meta"] = studio_meta

        # Validate all mapped slot node IDs exist in this checkpoint's workflow
        wf = ck["workflow"]
        ck_slots = ck["slots"]
        missing = []
        for sk, sv in ck_slots.items():
            nid = sv.get("node_id", "")
            if nid and nid not in wf:
                missing.append(f"'{sk}' maps to node {nid}")
        if missing:
            return {"error": (
                f"Preset snapshot has node bindings that reference nodes not "
                f"found in the workflow: {', '.join(missing)}. "
                f"Re-bind these slots in the preset wizard."
            )}

    for cell in compilation.get("cells", []):
        cell["studio_meta"] = studio_meta

    compilation["studio_meta"] = studio_meta
    return compilation


# ── Async scheduler helpers ────────────────────────────────────────────────


async def _schedule_and_start(
    exp_id: str,
    compilation: dict[str, Any],
    REGISTRY: Any,
    node_dir: str | os.PathLike = "",
) -> dict[str, Any]:
    """Create scheduler and start execution. Returns the run result."""
    from experiment_runner import LocalRemoteInvoker
    from modal_client import run_prompt_stream

    invoker = LocalRemoteInvoker(
        run_prompt_stream,
        experiment_id=exp_id,
        node_dir=str(node_dir) if node_dir else "",
    )
    sched = await REGISTRY.get_or_create_scheduler(
        exp_id,
        compilation=compilation,
        invoker=invoker,
        max_containers=1,
    )
    result = await sched.start()
    # Record run history after successful completion
    if result and result.get("completed", 0) > 0:
        try:
            from experiment_service import REGISTRY as _REGISTRY
            _REGISTRY.history().record_run(
                kind="studio_run",
                prompt_id=exp_id,
                status="completed",
                meta=compilation.get("studio_meta", {}),
            )
        except Exception:
            _log.warning("Failed to record run history for experiment %s", exp_id)
    return result


def _fire_and_forget(coro, exp_id: str) -> None:
    """Fire a coroutine as a background task with error logging."""
    import asyncio

    task = asyncio.ensure_future(coro)

    def _log_error(fut):
        try:
            exc = fut.exception()
            if exc is not None:
                _log.error(
                    "Async scheduler start failed for experiment %s: %s",
                    exp_id, exc,
                )
        except asyncio.CancelledError:
            _log.warning("Scheduler start cancelled for experiment %s", exp_id)
        except Exception as e:
            _log.error("Unexpected error in scheduler callback for %s: %s", exp_id, e)

    task.add_done_callback(_log_error)


def _create_experiment(
    exp_id: str,
    compilation: dict[str, Any],
    definition: dict[str, Any],
    REGISTRY: Any,
) -> None:
    """Write experiment definition and creation event to the store."""
    store = REGISTRY.store(exp_id)
    store.write_definition(definition)
    store.append_event({
        "type": "experiment.created",
        "payload": {
            "experiment_id": exp_id,
            "name": definition.get("name", ""),
            "compilation": compilation,
            "studio_meta": compilation.get("studio_meta", {}),
        },
    })


# ── Route helpers ──────────────────────────────────────────────────────────


def _persist_experiment_error(exp_id: str, error_message: str) -> None:
    """Persist an error event to the experiment store so polling can see it."""
    try:
        from experiment_service import REGISTRY
        store = REGISTRY.store(exp_id)
        store.append_event({
            "type": "experiment.error",
            "payload": {
                "experiment_id": exp_id,
                "error": error_message,
                "stage": "scheduler",
            },
        })
    except Exception:
        _log.warning("Failed to persist error event for experiment %s", exp_id)


def handle_studio_run(
    preset_id: str,
    feature_id: str,
    controls: dict[str, Any],
    node_dir: str | os.PathLike,
) -> dict[str, Any]:
    """Handle a single Studio run request.

    Called from the route handler. Performs validation, builds the
    compilation, creates an experiment via REGISTRY, and schedules
    the runner.

    Returns a response dict with ``status``, ``runId``, ``experimentId``
    on success, or ``status`` + ``message`` on error.  No raw exception
    strings are exposed in the message.
    """
    node_dir = Path(node_dir)
    _log.info("Studio run received: preset_id=%s feature_id=%s", preset_id, feature_id)

    # 1. Load
    loaded = load_preset_and_snapshot(preset_id, node_dir)
    if loaded is None:
        _log.warning("Studio run load failed: %s", get_load_error())
        return {"status": "error", "message": get_load_error()}
    preset, snapshot = loaded
    _log.info("Studio run preset/snapshot loaded: preset=%s snapshot=%s",
              preset.get("id", ""), snapshot.get("id", ""))

    # 2. Validate
    validation = validate_studio_run(preset, snapshot, feature_id)
    if validation.get("error"):
        _log.warning("Studio run validation failed: %s", validation["error"])
        return {"status": "error", "message": validation["error"]}
    _log.info("Studio run validation passed")

    # 3. Build single-run compilation (includes validation)
    compilation = build_single_run_spec(preset, snapshot, feature_id, controls, node_dir)
    if isinstance(compilation, dict) and compilation.get("error"):
        _log.warning("Studio run compilation failed: %s", compilation["error"])
        return {"status": "error", "message": compilation["error"]}

    # 4. Create experiment via REGISTRY and start scheduler
    try:
        from experiment_service import REGISTRY

        exp_id = compilation["experiment_id"]
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        definition = {
            "experiment_id": exp_id,
            "revision": 1,
            "name": f"Studio Run: {preset.get('label', preset_id)} [{feature_id}]",
            "notes": "",
            "created_at": now,
            "updated_at": now,
            "studio_meta": compilation.get("studio_meta", {}),
        }
        _create_experiment(exp_id, compilation, definition, REGISTRY)
        _log.info("Studio experiment created: %s", exp_id)

        # Start scheduler in background — report truthful submission status
        import asyncio

        async def _start_and_catch(exp_id, compilation, REGISTRY, nd):
            """Start scheduler and persist error events on failure."""
            try:
                _log.info("Scheduler start called for experiment %s", exp_id)
                result = await _schedule_and_start(exp_id, compilation, REGISTRY, node_dir=nd)
                _log.info("Scheduler start completed for experiment %s: %s", exp_id, result)
                return result
            except Exception as exc:
                error_msg = str(exc)[:200]
                _log.error("Scheduler start failed for experiment %s: %s", exp_id, error_msg)
                _persist_experiment_error(exp_id, error_msg)
                raise

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                _fire_and_forget(
                    _start_and_catch(exp_id, compilation, REGISTRY, node_dir),
                    exp_id,
                )
            else:
                asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir))
        except RuntimeError:
            asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir))
        except Exception:
            _log.exception("Unexpected error starting scheduler for %s", exp_id)
            _persist_experiment_error(exp_id, _STABLE_INTERNAL_ERROR)

        return {
            "status": "ok",
            "runId": exp_id,
            "experimentId": exp_id,
            "message": "Studio run submitted; check experiment status for completion",
            "studio_meta": compilation.get("studio_meta", {}),
        }
    except Exception:
        _log.exception("Studio run failed for experiment %s", compilation.get("experiment_id", "unknown"))
        return {"status": "error", "message": _STABLE_INTERNAL_ERROR}


def handle_studio_experiment(
    preset_ids: list[str],
    feature_id: str,
    experiment_def: dict[str, Any],
    node_dir: str | os.PathLike,
) -> dict[str, Any]:
    """Handle a Studio experiment request supporting multiple presets.

    Accepts a list of ``preset_ids`` and creates ONE unified experiment
    across all selected presets.  Returns ``status``, ``experimentId``,
    ``cellCount`` on success, or ``status`` + ``message`` on error.
    No raw exception strings are exposed.
    """
    node_dir = Path(node_dir)
    _log.info("Studio experiment received: presets=%s feature=%s", preset_ids, feature_id)

    if not preset_ids:
        _log.warning("Studio experiment rejected: no preset IDs")
        return {"status": "error", "message": "At least one presetId is required"}

    # 1. Load all presets + snapshots
    pairs: list[tuple[dict, dict]] = []
    for pid in preset_ids:
        loaded = load_preset_and_snapshot(pid, node_dir)
        if loaded is None:
            _log.warning("Studio experiment load failed for preset %s: %s", pid, get_load_error())
            return {"status": "error", "message": get_load_error()}
        pairs.append(loaded)
    _log.info("Studio experiment loaded %d preset/snapshot pairs", len(pairs))

    # 2. Build unified experiment spec (includes validation of all pairs)
    compilation = build_experiment_spec(pairs, feature_id, experiment_def, node_dir)
    if isinstance(compilation, dict) and compilation.get("error"):
        _log.warning("Studio experiment spec build failed: %s", compilation["error"])
        return {"status": "error", "message": compilation["error"]}
    _log.info("Studio experiment spec built successfully")

    # 3. Create unified experiment via REGISTRY
    try:
        from experiment_service import REGISTRY

        exp_id = compilation["experiment_id"]
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        definition = {
            "experiment_id": exp_id,
            "revision": 1,
            "name": experiment_def.get("name", f"Studio Experiment: {feature_id}"),
            "notes": "",
            "created_at": now,
            "updated_at": now,
            "studio_meta": compilation.get("studio_meta", {}),
        }
        _create_experiment(exp_id, compilation, definition, REGISTRY)
        _log.info("Studio experiment created: %s", exp_id)

        # Start scheduler
        import asyncio

        async def _start_and_catch(exp_id, compilation, REGISTRY, nd):
            """Start scheduler and persist error events on failure."""
            try:
                _log.info("Scheduler start called for experiment %s", exp_id)
                result = await _schedule_and_start(exp_id, compilation, REGISTRY, node_dir=nd)
                _log.info("Scheduler start completed for experiment %s: %s", exp_id, result)
                return result
            except Exception as exc:
                error_msg = str(exc)[:200]
                _log.error("Scheduler start failed for experiment %s: %s", exp_id, error_msg)
                _persist_experiment_error(exp_id, error_msg)
                raise

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                _fire_and_forget(
                    _start_and_catch(exp_id, compilation, REGISTRY, node_dir),
                    exp_id,
                )
            else:
                asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir))
        except RuntimeError:
            asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir))
        except Exception:
            _log.exception("Unexpected error starting scheduler for %s", exp_id)
            _persist_experiment_error(exp_id, _STABLE_INTERNAL_ERROR)

        cell_count = len(compilation.get("cells", []))

        return {
            "status": "ok",
            "experimentId": exp_id,
            "cellCount": cell_count,
            "message": f"Studio experiment submitted with {cell_count} cell(s) across {len(preset_ids)} preset(s)",
            "studio_meta": compilation.get("studio_meta", {}),
        }
    except Exception:
        _log.exception("Studio experiment failed for %s", preset_ids)
        return {"status": "error", "message": _STABLE_INTERNAL_ERROR}
