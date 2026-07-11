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

# ── Control Schema Helpers ──────────────────────────────────────────────────
# Known ComfyUI sampler names (for enum schema derivation).
_SAMPLER_NAMES: list[str] = [
    "euler", "euler_ancestral", "heun", "heunpp2",
    "dpm_2", "dpm_2_ancestral", "lms", "dpm_fast", "dpm_adaptive",
    "dpmpp_2s_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_3m_sde",
    "dpmpp_sde", "dpmpp_sde_gpu", "dpmpp_2m_sde_gpu", "dpmpp_3m_sde_gpu",
    "ddim", "uni_pc", "uni_pc_bh2",
]

_SCHEDULER_NAMES: list[str] = [
    "normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform",
]

# Mapping from ComfyUI node type → widget_name → schema fragment.
# Used by derive_control_schemas_from_snapshot to produce control schemas.
_NODE_WIDGET_SCHEMAS: dict[str, dict[str, dict]] = {
    "KSampler": {
        "seed": {"kind": "integer", "default": 0, "minimum": 0, "maximum": 2 ** 32 - 1},
        "steps": {"kind": "integer", "default": 20, "minimum": 1, "maximum": 10000},
        "cfg": {"kind": "number", "default": 8.0, "minimum": 0.0, "maximum": 100.0, "step": 0.5, "precision": 1},
        "sampler_name": {"kind": "enum", "options": list(_SAMPLER_NAMES), "default": "euler"},
        "scheduler": {"kind": "enum", "options": list(_SCHEDULER_NAMES), "default": "normal"},
        "denoise": {"kind": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0, "step": 0.01, "precision": 2},
    },
    "KSamplerAdvanced": {
        "seed": {"kind": "integer", "default": 0, "minimum": 0, "maximum": 2 ** 32 - 1},
        "steps": {"kind": "integer", "default": 20, "minimum": 1, "maximum": 10000},
        "cfg": {"kind": "number", "default": 8.0, "minimum": 0.0, "maximum": 100.0, "step": 0.5, "precision": 1},
        "sampler_name": {"kind": "enum", "options": list(_SAMPLER_NAMES), "default": "euler"},
        "scheduler": {"kind": "enum", "options": list(_SCHEDULER_NAMES), "default": "normal"},
        "denoise": {"kind": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0, "step": 0.01, "precision": 2},
    },
    "CLIPTextEncode": {
        "text": {"kind": "multiline", "default": ""},
    },
    "CheckpointLoaderSimple": {
        "ckpt_name": {"kind": "model", "default": ""},
    },
    "VAELoader": {
        "vae_name": {"kind": "model", "default": ""},
    },
    "IntNumber": {
        "value": {"kind": "integer", "default": 0, "minimum": -2 ** 31, "maximum": 2 ** 31 - 1},
    },
    "FloatNumber": {
        "value": {"kind": "number", "default": 0.0},
    },
    "PrimitiveString": {
        "value": {"kind": "string", "default": ""},
    },
    "PrimitiveStringMultiline": {
        "value": {"kind": "multiline", "default": ""},
    },
    "BooleanControl": {
        "value": {"kind": "boolean", "default": False},
    },
}

# Control ID → widget-name aliases for common bindings.
# Key = control ID (binding key), value = widget name in the node.
_CONTROL_WIDGET_ALIASES: dict[str, str] = {
    "sampler": "sampler_name",
    "guidance": "cfg",
    "negative_prompt": "text",
}


def derive_control_schemas_from_snapshot(snapshot: dict) -> dict[str, dict]:
    """Derive control schemas from a snapshot's nodeBindings + apiPromptJson.

    Returns a dict keyed by control ID (binding key), each value being a
    schema dict with fields like ``kind``, ``options``, ``minimum``,
    ``maximum``, ``step``, ``precision``, ``default``, ``nodeId``,
    ``nodeType``, ``widgetName``, and ``schemaResolved``.

    For backward compatibility, missing or unresolvable schemas return a
    stub with ``schemaResolved: False`` so the frontend can fall back to
    its static type definitions.
    """
    schemas: dict[str, dict] = {}
    bindings = snapshot.get("nodeBindings", {}) or {}
    workflow = _get_executable_workflow(snapshot.get("apiPromptJson"))

    for ctrl_id, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        kind = binding.get("kind", "")
        node_id = str(binding.get("nodeId", ""))
        node_type = binding.get("nodeType", "") or ""
        widget_name = binding.get("widgetName") or binding.get("inputName") or ""

        # Skip non-widget bindings (node-kind, output-kind)
        if kind not in ("widget", "input"):
            schemas[ctrl_id] = {
                "field": ctrl_id,
                "kind": "unresolved",
                "schemaResolved": False,
                "nodeId": node_id,
                "nodeType": node_type,
            }
            continue

        # Resolve widget name via aliases
        resolved_widget = _CONTROL_WIDGET_ALIASES.get(ctrl_id, widget_name)

        # Look up the node type in the workflow
        node_data = workflow.get(node_id, {}) if isinstance(workflow, dict) else {}
        actual_type = node_data.get("class_type") or node_type

        schema: dict = {
            "field": ctrl_id,
            "nodeId": node_id,
            "nodeType": actual_type,
            "widgetName": resolved_widget,
        }

        # Look up widget schema from our registry
        widget_schemas = _NODE_WIDGET_SCHEMAS.get(actual_type, {})
        widget_schema = widget_schemas.get(resolved_widget)

        if widget_schema:
            schema.update(widget_schema)
            schema["schemaResolved"] = True
        else:
            # Fall back: infer type from the actual value in the workflow
            actual_value = None
            if isinstance(node_data, dict):
                inputs = node_data.get("inputs", {}) or {}
                actual_value = inputs.get(resolved_widget)
            if actual_value is not None:
                if isinstance(actual_value, bool):
                    schema["kind"] = "boolean"
                elif isinstance(actual_value, int):
                    schema["kind"] = "integer"
                elif isinstance(actual_value, float):
                    schema["kind"] = "number"
                else:
                    schema["kind"] = "string"
                schema["default"] = actual_value
                schema["schemaResolved"] = True
            else:
                schema["kind"] = "unresolved"
                schema["schemaResolved"] = False

        schemas[ctrl_id] = schema

    return schemas


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
) -> tuple[dict | None, str | None]:
    """Load a preset and its referenced snapshot from Studio stores.

    Returns ``(preset_dict, snapshot_dict)`` on success (both dicts).
    Returns ``(None, error_message)`` on failure — no global state needed.
    Thread-safe: each call returns its own error inline.
    """
    node_dir = Path(node_dir)
    presets = _read_store(node_dir / ".studio_presets.json")
    snapshots = _read_store(node_dir / ".studio_snapshots.json")

    preset_index = _build_index(presets)
    snapshot_index = _build_index(snapshots)

    preset = preset_index.get(preset_id)
    if preset is None:
        return None, f"Preset {preset_id!r} not found"

    if preset.get("archived"):
        return None, f"Preset {preset_id!r} is archived"

    snapshot_id = preset.get("snapshotId", "") or ""
    if not snapshot_id:
        return None, f"Preset {preset_id!r} has no snapshot reference"

    snapshot = snapshot_index.get(snapshot_id)
    if snapshot is None:
        return None, f"Snapshot {snapshot_id!r} referenced by preset {preset_id!r} not found"

    if snapshot.get("archived"):
        return None, f"Snapshot {snapshot_id!r} referenced by preset {preset_id!r} is archived"

    return preset, snapshot


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


def _build_resolved_controls(
    workflow: dict[str, Any],
    slots: dict[str, Any],
) -> dict[str, Any]:
    """Read back actual control values from the workflow after application.

    Iterates ALL bound slots generically — not a hardcoded shortlist — so
    arbitrary bindings (mask_blur, lora_strength, source_image, expansion,
    etc.) are captured.  Preserves falsy values (0, 0.0, "", False).
    Only keys that have a corresponding slot mapping are included.

    For each slot, the function follows the slot's ``path`` into the
    workflow node and returns the terminal value.
    """
    resolved: dict[str, Any] = {}
    for key, slot in slots.items():
        if not isinstance(slot, dict):
            continue
        nid = slot.get("node_id", "")
        path = slot.get("path", [])
        if not nid or not path:
            continue
        node = workflow.get(nid, {})
        target = node
        for segment in path:
            if isinstance(target, dict):
                target = target.get(segment)
            else:
                target = None
                break
        if target is not None:
            resolved[key] = target
    return resolved


_CANONICAL_ALIAS_KEYS = frozenset({
    "prompt", "negative_prompt", "seed", "steps", "guidance", "cfg",
    "sampler", "scheduler", "denoise", "width", "height",
})


def _flatten_canonical_aliases(
    resolved_controls: dict[str, Any],
    event_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy key values from *resolved_controls* into flat aliases.

    Also copies any arbitrary keys (lora_name, lora_strength, source_image,
    mask_blur, expansion, image_identity, etc.) so the frontend normalizer
    does not need to dig into ``resolved_controls``.

    When the same key appears in *event_payload* (from the remote cell
    completion event), the event value takes precedence since it represents
    the actual executed value.

    Falsy values (0, 0.0, "", False) are preserved — only truly missing
    keys (``None``) are skipped.
    """
    aliases: dict[str, Any] = {}
    seen: set[str] = set()

    # 1. Known canonical keys from resolved_controls
    for key in _CANONICAL_ALIAS_KEYS:
        val = resolved_controls.get(key)
        if val is not None:
            aliases[key] = val
            seen.add(key)

    # 2. Arbitrary keys from resolved_controls (LoRA, image, mask, etc.)
    for key, val in resolved_controls.items():
        if val is not None and key not in seen:
            aliases[key] = val
            seen.add(key)

    # 3. Event payload overrides (actual executed values from remote)
    if event_payload:
        for key in _CANONICAL_ALIAS_KEYS:
            val = event_payload.get(key)
            if val is not None:
                aliases[key] = val

    return aliases


def _build_studio_history_meta(
    preset_id: str,
    snapshot_id: str,
    feature_id: str,
    controls: dict[str, Any] | None = None,
    preset_label: str = "",
) -> dict[str, Any]:
    """Build metadata dict for run history, carrying Studio info.

    Includes ``studio_preset_label`` so that finalization and the frontend
    normalizer can surface the human-readable preset name instead of the
    raw preset id.
    """
    return {
        "studio_preset_id": preset_id,
        "studio_snapshot_id": snapshot_id,
        "studio_feature_id": feature_id,
        "studio_controls": dict(controls or {}),
        "studio_preset_label": preset_label,
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
        preset_label=preset.get("label", ""),
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
    """Create scheduler and start execution. Returns the run result.

    Finalizes the submission-time history record (created by
    ``handle_studio_run``) with the actual output paths, timings,
    resolved controls, and terminal status.

    Timing semantics
    ----------------
    ``submitted_at`` — set when ``handle_studio_run`` created the record.
    ``queue_ms``     — wall-clock from submission to ``sched.start()``.
    ``generation_ms`` — wall-clock duration of ``sched.start()``.
    ``total_ms``     — ``queue_ms + generation_ms``.
    ``remote_timings`` — any timing breakdown from the remote side, kept
                         separate from the local wall-clock measurements.
    ``completed_at`` — set after ``sched.start()`` returns or fails.
    """
    from datetime import datetime, timezone

    # Capture the pre-start timestamp for queue_ms computation
    generation_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    generation_start_dt = datetime.fromisoformat(generation_start.replace("Z", "+00:00"))

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

    try:
        result = await sched.start()
    except Exception as exc:
        # Finalize the submission record as failed — preserve elapsed timings and failure evidence
        run_history_id = compilation.get("run_history_id", "")
        if run_history_id:
            fail_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                # Compute known timings even on failure
                fail_timings: dict[str, Any] = {}
                fail_meta: dict[str, Any] = {
                    "error": _STABLE_INTERNAL_ERROR,
                    "_error_detail": str(exc)[:500],
                    "failure_stage": "scheduler_execution",
                }
                sub_meta = REGISTRY.history().get_run(run_history_id)
                if sub_meta:
                    sub_started = sub_meta.get("started_at") or ""
                    if sub_started:
                        try:
                            sub_dt = datetime.fromisoformat(sub_started.replace("Z", "+00:00"))
                            now_dt = datetime.fromisoformat(fail_ts.replace("Z", "+00:00"))
                            elapsed_ms = int((now_dt - sub_dt).total_seconds() * 1000)
                            fail_timings["queue_ms"] = max(0, elapsed_ms)
                            fail_timings["end_to_end_total_ms"] = max(0, elapsed_ms)
                        except Exception:
                            pass
                REGISTRY.history().update_run(
                    run_history_id,
                    status="error",
                    completed_at=fail_ts,
                    timings=fail_timings if fail_timings else None,
                    meta=fail_meta,
                )
            except Exception:
                _log.warning("Failed to update run history for %s on failure", exp_id)
        # Persist the stable error, not raw exception text
        try:
            _persist_experiment_error(exp_id, _STABLE_INTERNAL_ERROR[:200])
        except Exception:
            pass
        raise

    # ── Capture post-execution timestamps ─────────────────────────────────
    completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))

    # Compute wall-clock timing relative to the submission record's started_at
    run_history_id = compilation.get("run_history_id", "")
    submission_started_at: str | None = None
    if run_history_id:
        try:
            meta = REGISTRY.history().get_run(run_history_id)
            if meta:
                submission_started_at = meta.get("started_at") or None
        except Exception:
            pass

    timings: dict[str, Any] = {}
    if submission_started_at:
        try:
            sub_dt = datetime.fromisoformat(submission_started_at.replace("Z", "+00:00"))
            queue_ms = int((generation_start_dt - sub_dt).total_seconds() * 1000)
            generation_ms = int((completed_dt - generation_start_dt).total_seconds() * 1000)
            timings = {
                "queue_ms": max(0, queue_ms),
                "generation_ms": max(0, generation_ms),
                "total_ms": max(0, queue_ms + generation_ms),
            }
        except Exception:
            pass

    # Preserve any remote-side timing breakdown separately
    if isinstance(result, dict):
        remote_breakdown = {}
        for k in list(result.keys()):
            if k.endswith("_ms") or k in ("sampling_ms", "queue_remote_ms",
                                          "inference_ms", "restore_total_ms"):
                remote_breakdown[k] = result[k]
        if remote_breakdown:
            timings["remote_timings"] = remote_breakdown

    # ── Inspect experiment journal for the LATEST visible cell.completed ──
    output_paths: list[str] = []
    primary_asset_id = ""
    attempt_id = ""
    cell_key = ""
    checkpoint_id = ""
    resolved_meta: dict = {}
    has_cell_completed = False

    try:
        store = REGISTRY.store(exp_id)
        # Iterate all events; only the LAST cell.completed is used
        for ev in store.read_events():
            if ev.get("type") == "cell.completed":
                has_cell_completed = True
                pl = ev.get("payload", {}) or {}
                paths = pl.get("output_paths", [])
                if paths:
                    output_paths = paths
                primary_asset_id = pl.get("primary_asset_id", primary_asset_id)
                attempt_id = pl.get("attempt_id", attempt_id)
                cell_key = pl.get("cell_key", cell_key)
                checkpoint_id = pl.get("checkpoint_id", checkpoint_id)
                resolved_meta["workflow_hash"] = pl.get("workflow_hash", resolved_meta.get("workflow_hash", ""))
    except Exception:
        _log.warning("Failed to read journal events for %s", exp_id)

    # Derive resolved_controls from the post-application workflow
    resolved_controls: dict = {}
    try:
        if compilation.get("checkpoints"):
            ck = compilation["checkpoints"][0]
            wf = ck.get("workflow", {})
            slots = ck.get("slots", {})
            resolved_controls = _build_resolved_controls(wf, slots)
    except Exception:
        _log.warning("Failed to derive resolved_controls for %s", exp_id)

    # Determine terminal status
    terminal_status = "completed"
    if result:
        completed = result.get("completed", 0)
        failed = result.get("failed", 0)
        if failed > 0 and completed == 0:
            terminal_status = "failed"
        elif failed > 0:
            terminal_status = "completed_with_failures"
        # If no cell.completed event was seen, execution didn't actually produce output
        if not has_cell_completed:
            terminal_status = "failed"

    # Build canonical flattened metadata for the frontend normalizer.
    # Everything lives at the top level or in extra — NOT hidden inside nested dicts.
    studio_meta = compilation.get("studio_meta", {}) or {}
    meta_merge: dict = {}
    meta_merge["requested_controls"] = dict(studio_meta.get("studio_controls", {}))
    meta_merge["resolved_controls"] = dict(resolved_controls or {})
    meta_merge["studio_preset_id"] = studio_meta.get("studio_preset_id", "")
    meta_merge["studio_snapshot_id"] = studio_meta.get("studio_snapshot_id", "")
    meta_merge["studio_feature_id"] = studio_meta.get("studio_feature_id", "")
    meta_merge["experiment_id"] = exp_id
    meta_merge["attempt_id"] = attempt_id or ""
    meta_merge["cell_key"] = cell_key or ""
    meta_merge["checkpoint_id"] = checkpoint_id or ""
    meta_merge["preset_label"] = studio_meta.get("studio_preset_label", "")

    # Include submitted_at from the submission record's started_at
    if submission_started_at:
        meta_merge["submitted_at"] = submission_started_at

    # Flatten canonical aliases from resolved_controls + event payload
    # so frontend/history see prompt, seed, steps, etc. at top level.
    canonical_aliases = _flatten_canonical_aliases(
        resolved_controls or {},
        resolved_meta if has_cell_completed else None,
    )
    for k, v in canonical_aliases.items():
        if v is not None and k not in meta_merge:
            meta_merge[k] = v

    if has_cell_completed and output_paths:
        meta_merge["output_paths"] = list(output_paths)
    if primary_asset_id:
        meta_merge["primary_asset_id"] = primary_asset_id
    if resolved_meta.get("workflow_hash"):
        meta_merge["workflow_hash"] = resolved_meta["workflow_hash"]

    # Finalize the submission record — only set output_path if truly completed
    if run_history_id:
        try:
            output_path_val = output_paths[0] if (has_cell_completed and output_paths) else ""
            update_kwargs: dict = {
                "status": terminal_status,
                "completed_at": completed_at,
                "timings": timings,
                "meta": meta_merge,
            }
            if output_path_val:
                update_kwargs["output_path"] = output_path_val
            if primary_asset_id and has_cell_completed:
                update_kwargs["primary_asset_id"] = primary_asset_id
            if resolved_meta.get("workflow_hash"):
                update_kwargs["workflow_hash"] = resolved_meta["workflow_hash"]
            REGISTRY.history().update_run(run_history_id, **update_kwargs)  # type: ignore[arg-type]
        except Exception:
            _log.warning("Failed to finalize run history for %s", exp_id)
    else:
        # Fallback: no submission record — create one (legacy path)
        try:
            REGISTRY.history().record_run(
                kind="studio_run",
                prompt_id=exp_id,
                status=terminal_status,
                started_at=completed_at,
                meta=compilation.get("studio_meta", {}),
            )
        except Exception:
            _log.warning("Failed to record fallback run history for %s", exp_id)

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

    # 1. Load (returns (preset, snapshot) or (None, error) — thread-safe, no global state)
    loaded_preset, loaded_snapshot = load_preset_and_snapshot(preset_id, node_dir)
    if loaded_preset is None:
        _log.warning("Studio run load failed: %s", loaded_snapshot)
        return {"status": "error", "message": loaded_snapshot}
    _log.info("Studio run preset/snapshot loaded: preset=%s snapshot=%s",
              loaded_preset.get("id", ""), loaded_snapshot.get("id", ""))
    preset, snapshot = loaded_preset, loaded_snapshot

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

    # 4. Create submission-time history record
    try:
        from experiment_service import REGISTRY

        exp_id = compilation["experiment_id"]
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build requested_controls from the controls dict + studio meta
        requested_controls = dict(controls or {})
        studio_meta = compilation.get("studio_meta", {})

        # Compute workflow_hash from the built workflow if possible
        workflow_hash_at_submit = ""
        try:
            ck_list = compilation.get("checkpoints", [])
            if ck_list and isinstance(ck_list[0], dict):
                wf = ck_list[0].get("workflow", {})
                if wf:
                    # Import inline to avoid circular dependency at module level
                    from experiment_runner import _workflow_sha256
                    workflow_hash_at_submit = _workflow_sha256(wf)
        except Exception:
            pass

        meta_payload: dict = {
            "requested_controls": requested_controls,
            "studio_preset_id": studio_meta.get("studio_preset_id", preset_id),
            "studio_snapshot_id": studio_meta.get("studio_snapshot_id", ""),
            "studio_feature_id": studio_meta.get("studio_feature_id", feature_id),
            "experiment_id": exp_id,
            "preset_label": preset.get("label", preset_id),
            "submitted_at": now,
        }
        if workflow_hash_at_submit:
            meta_payload["workflow_hash"] = workflow_hash_at_submit

        # Create the submission history record
        submission_record = REGISTRY.history().record_run(
            kind="studio_run",
            prompt_id=exp_id,
            status="submitted",
            started_at=now,
            meta=meta_payload,
        )
        run_history_id = submission_record.get("run_id", "")
        compilation["run_history_id"] = run_history_id

        # Flow run_history_id through all compilation metadata layers
        for ck in compilation.get("checkpoints", []):
            ck.setdefault("studio_meta", {})["run_history_id"] = run_history_id
        for cell in compilation.get("cells", []):
            cell.setdefault("studio_meta", {})["run_history_id"] = run_history_id
        compilation.setdefault("studio_meta", {})["run_history_id"] = run_history_id

        _log.info("Studio run history record created: %s (status=submitted)", run_history_id)

        # Update the submission record to "running" right before scheduling
        REGISTRY.history().update_run(
            run_history_id,
            status="running",
        )

        # 5. Create experiment via REGISTRY and start scheduler
        definition = {
            "experiment_id": exp_id,
            "revision": 1,
            "name": f"Studio Run: {preset.get('label', preset_id)} [{feature_id}]",
            "notes": "",
            "created_at": now_iso,
            "updated_at": now_iso,
            "studio_meta": studio_meta,
            "run_history_id": run_history_id,
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
                error_detail = str(exc)[:300]
                fail_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _log.error("Scheduler start failed for experiment %s: %s", exp_id, error_detail)
                # Finalize the submission record as failed with stable message
                if run_history_id:
                    try:
                        REGISTRY.history().update_run(
                            run_history_id,
                            status="error",
                            completed_at=fail_ts,
                            meta={
                                "error": _STABLE_INTERNAL_ERROR,
                                "_error_detail": error_detail,
                            },
                        )
                    except Exception:
                        pass
                _persist_experiment_error(exp_id, _STABLE_INTERNAL_ERROR[:200])
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
            "runHistoryId": run_history_id,
            "message": "Studio run submitted; check experiment status for completion",
            "studio_meta": studio_meta,
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

    # 1. Load all presets + snapshots (thread-safe, no global state)
    pairs: list[tuple[dict, dict]] = []
    for pid in preset_ids:
        loaded_preset, loaded_snapshot = load_preset_and_snapshot(pid, node_dir)
        if loaded_preset is None:
            _log.warning("Studio experiment load failed for preset %s: %s", pid, loaded_snapshot)
            return {"status": "error", "message": loaded_snapshot}
        pairs.append((loaded_preset, loaded_snapshot))
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
