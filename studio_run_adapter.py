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

try:
    import nodes
except Exception:  # pragma: no cover - runtime-only dependency in some contexts
    nodes = None

from production_workflow import (
    normalize_production_options,
    compile_production_workflow,
)
from studio_store import StudioJsonStore, StudioStoreError
from studio_models import (
    _FEATURE_BINDING_KEYS,
    _KNOWN_FEATURE_IDS,
    validate_controls_against_schema,
)
from timing_trace import TRACE_VERSION, merge_remote_trace_into
from warmup_profile import prepare_active_next_profile

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

# Auto-derivation registry for controls that are never explicitly bound.
# Maps control ID → candidate node types + widget name in the workflow.
# Used by _find_node_for_control() to auto-derive schemas, defaults, and slots.
_AUTO_DERIVE_CONTROLS: dict[str, dict] = {
    "sampler":   {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "sampler_name"},
    "scheduler": {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "scheduler"},
    "steps":     {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "steps"},
    "guidance":  {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "cfg"},
    "seed":      {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "seed"},
    "denoise":   {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "denoise"},
}


def _find_node_for_control(workflow: dict, ctrl_id: str) -> dict | None:
    """Find the workflow node + widget for an unbound control via auto-derive registry.

    Returns ``{"node_id", "node_type", "widget_name", "value"}`` or ``None``.
    Scans workflow nodes in insertion order for the first node whose
    class_type matches one of the control's candidate node types.
    """
    spec = _AUTO_DERIVE_CONTROLS.get(ctrl_id)
    if not spec or not isinstance(workflow, dict):
        return None
    widget_name = spec["widget"]
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get("class_type", "")
        inputs = node_data.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if widget_name not in inputs:
            continue
        if class_type not in spec["node_types"] and _derive_widget_schema_from_node_def(class_type, widget_name) is None:
            continue
        return {
            "node_id": str(node_id),
            "node_type": class_type,
            "widget_name": widget_name,
            "value": inputs.get(widget_name),
        }
    return None


def _derive_widget_schema_from_node_def(node_type: str, widget_name: str) -> dict | None:
    """Probe ComfyUI node definitions for widget schema metadata."""
    if not nodes or not node_type or not widget_name:
        return None
    cls = getattr(nodes, "NODE_CLASS_MAPPINGS", {}).get(node_type)
    if cls is None:
        return None
    input_types = getattr(cls, "INPUT_TYPES", None)
    if input_types is None:
        return None
    try:
        spec = input_types()
    except Exception:
        return None
    if not isinstance(spec, dict):
        return None
    for category in ("required", "optional"):
        inputs = spec.get(category, {}) or {}
        entry = inputs.get(widget_name)
        if entry is None or not isinstance(entry, (list, tuple)) or not entry:
            continue
        type_spec = entry[0]
        config = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
        if isinstance(type_spec, (list, tuple)):
            options = list(type_spec)
            return {
                "kind": "enum",
                "options": options,
                "default": config.get("default", options[0] if options else ""),
            }
        if type_spec == "INT":
            return {
                "kind": "integer",
                "default": config.get("default", 0),
                "minimum": config.get("min"),
                "maximum": config.get("max"),
            }
        if type_spec == "FLOAT":
            schema = {
                "kind": "number",
                "default": config.get("default", 0.0),
                "minimum": config.get("min"),
                "maximum": config.get("max"),
            }
            if config.get("step") is not None:
                schema["step"] = config.get("step")
            return schema
        if type_spec == "BOOLEAN":
            return {
                "kind": "boolean",
                "default": config.get("default", False),
            }
        if type_spec == "STRING":
            return {
                "kind": "string",
                "default": config.get("default", ""),
            }
    return None


def derive_control_schemas_from_snapshot(snapshot: dict) -> dict[str, dict]:
    """Derive control schemas from a snapshot's nodeBindings + apiPromptJson.

    Returns a dict keyed by control ID (binding key), each value being a
    schema dict with fields like ``kind``, ``options``, ``minimum``,
    ``maximum``, ``step``, ``precision``, ``default``, ``nodeId``,
    ``nodeType``, ``widgetName``, and ``schemaResolved``.

    **Phase 4**: Snapshots created by the browser preset wizard now carry
    a ``controlSchemas`` dict keyed by control ID.  These were captured
    from the live LiteGraph widget metadata at binding time.  When present
    and non-empty, captured schemas are returned as the primary source —
    the static Python registry is only used as a legacy fallback for old
    snapshots that lack captured schemas.

    For backward compatibility, missing or unresolvable schemas return a
    stub with ``schemaResolved: False`` so the frontend can fall back to
    its static type definitions.
    """
    schemas: dict[str, dict] = {}
    bindings = snapshot.get("nodeBindings", {}) or {}
    workflow = _get_executable_workflow(snapshot.get("apiPromptJson"))

    # ── Phase 4: prefer captured schemas from browser widget metadata ──
    captured = snapshot.get("controlSchemas", {}) or {}
    if captured:
        schemas = copy.deepcopy(captured)
        for ctrl_id, schema in schemas.items():
            if isinstance(schema, dict):
                schema.setdefault("schemaResolved", True)
                schema.setdefault("field", ctrl_id)

    # ── Legacy fallback: derive from static registry ─────────────────────
    if not captured:
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

            if not widget_schema:
                widget_schema = _derive_widget_schema_from_node_def(actual_type, resolved_widget)

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
                    if not _is_connection_spec(actual_value):
                        schema["default"] = actual_value
                    schema["schemaResolved"] = True
                else:
                    schema["kind"] = "unresolved"
                    schema["schemaResolved"] = False

            schemas[ctrl_id] = schema

    # ── Auto-derive schemas for unbound controls ─────────────────────────
    if isinstance(workflow, dict):
        for ctrl_id in _AUTO_DERIVE_CONTROLS:
            existing = schemas.get(ctrl_id)
            if isinstance(existing, dict) and existing.get("schemaResolved"):
                continue
            found = _find_node_for_control(workflow, ctrl_id)
            if found is None:
                continue
            node_type = found["node_type"]
            widget_name = found["widget_name"]
            widget_schema = _NODE_WIDGET_SCHEMAS.get(node_type, {}).get(widget_name)
            if not widget_schema:
                widget_schema = _derive_widget_schema_from_node_def(node_type, widget_name)
            schema: dict = {
                "field": ctrl_id,
                "nodeId": found["node_id"],
                "nodeType": node_type,
                "widgetName": widget_name,
            }
            if widget_schema:
                schema.update(widget_schema)
                if found["value"] is not None and not _is_connection_spec(found["value"]):
                    schema["default"] = found["value"]
                schema["schemaResolved"] = True
            else:
                actual_value = found["value"]
                if isinstance(actual_value, bool):
                    schema["kind"] = "boolean"
                elif isinstance(actual_value, int):
                    schema["kind"] = "integer"
                elif isinstance(actual_value, float):
                    schema["kind"] = "number"
                else:
                    schema["kind"] = "string"
                if not _is_connection_spec(actual_value):
                    schema["default"] = actual_value
                schema["schemaResolved"] = True
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


def validate_studio_request_controls(
    preset_ids: list[str],
    feature_id: str,
    controls: dict[str, Any],
    axes: dict[str, Any],
    node_dir: str | os.PathLike,
) -> list[dict]:
    """Validate controls against ALL requested presets' snapshot schemas.

    For every *preset_id* in *preset_ids*:
      1. Calls ``load_preset_and_snapshot`` — load failure yields a
         preset-scoped error ``{"presetId": …, "field": …, "message": …}``.
      2. On success, derives the snapshot's control schemas.
      3. Validates *controls* (shared defaults) against those schemas
         with ``strict_unknown_rejection=False``.
      4. Validates EACH axis value from *axes* independently against
         the schemas so heterogeneous schemas catch per-preset incompat
         at every value.

    Every returned error dict carries ``presetId`` set to the preset that
    triggered the error.  A heterogeneous experiment (presets A and B with
    different schemas) must reject a control value that is valid for A but
    invalid for B — no first-valid-preset shortcut.

    Returns a **list of error dicts**.  An empty list means all controls
    are valid for all requested presets.

    Single-run callers pass ``[preset_id], controls, {}``.
    Experiment callers pass all preset IDs, experiment-level defaults,
    and the experiment's axes dict.
    """
    errors: list[dict] = []

    if not preset_ids:
        errors.append({
            "presetId": "",
            "field": "presetIds",
            "message": "At least one presetId is required",
        })
        return errors

    for pid in preset_ids:
        # Step 1: Load preset + snapshot (thread-safe, inline error)
        loaded_preset, loaded_snapshot = load_preset_and_snapshot(pid, node_dir)
        if loaded_preset is None:
            errors.append({
                "presetId": pid,
                "field": "preset",
                "message": loaded_snapshot or f"Preset {pid!r} could not be loaded",
            })
            continue  # Cannot validate controls against a missing preset

        preset = loaded_preset
        snapshot = loaded_snapshot

        # Step 2: Derive schemas from this snapshot
        try:
            schemas = derive_control_schemas_from_snapshot(snapshot)
        except Exception:
            _log.exception("Failed to derive schemas for snapshot %s", snapshot.get("id", "?"))
            errors.append({
                "presetId": pid,
                "field": "schema",
                "message": f"Failed to derive control schemas for preset {pid!r}",
            })
            continue

        # Step 3: Validate shared controls (strict_unknown_rejection=False)
        # Pass all controls in a single call for efficiency.  Each returned
        # error already carries ``field``; we add ``presetId``.
        if controls:
            try:
                ctrl_errors = validate_controls_against_schema(
                    controls, schemas, feature_id,
                    strict_unknown_rejection=False,
                )
            except Exception:
                _log.exception("Control validation error on preset %s", pid)
                # Fail closed: produce a structured error instead of silently
                # passing invalid controls through ([] would be a false green).
                errors.append({
                    "presetId": pid,
                    "field": "control",
                    "message": "Control validation could not be completed",
                })
                ctrl_errors = ()
            for err in ctrl_errors:
                err.setdefault("presetId", pid)
                errors.append(err)

        # Step 4: Validate each axis value independently against schemas.
        # Each value must be validated individually (not flattened into a
        # single dict) because later values would overwrite earlier ones,
        # silently skipping validation of the overwritten keys.
        for axis_id, axis_def in (axes or {}).items():
            if not isinstance(axis_def, dict):
                continue
            values = axis_def.get("values")
            if not isinstance(values, list):
                continue
            for val in values:
                try:
                    axis_errors = validate_controls_against_schema(
                        {axis_id: val}, schemas, feature_id,
                        strict_unknown_rejection=False,
                    )
                except Exception:
                    _log.exception(
                        "Axis validation error for %s on preset %s",
                        axis_id, pid,
                    )
                    # Fail closed: structured error for each axis value.
                    errors.append({
                        "presetId": pid,
                        "field": axis_id,
                        "message": "Control validation could not be completed",
                    })
                    continue
                for err in axis_errors:
                    err.setdefault("presetId", pid)
                    errors.append(err)

    return errors


# ── Defaults extraction ────────────────────────────────────────────────


def get_preset_scalar_defaults(
    preset_id: str, node_dir: str | os.PathLike,
) -> tuple[dict | None, str | None]:
    """Load preset and return merged scalar defaults.

    Merges the preset's own ``defaults`` dict (user-configured) with
    snapshot-derived widget defaults.  Preset keys take priority; snapshot
    defaults fill in any missing keys.  The result includes scalar controls
    such as *steps*, *scheduler*, *width*, *height* when present.

    Returns ``(merged_defaults_dict, None)`` on success or
    ``(None, error_message)`` on failure.
    """
    preset, snapshot_or_err = load_preset_and_snapshot(preset_id, node_dir)
    if preset is None:
        return None, snapshot_or_err  # error message
    if not isinstance(snapshot_or_err, dict):
        return None, "Snapshot payload is not a dict"

    # Start with preset's own defaults (user-configured, top priority)
    merged = dict(preset.get("defaults", {}) or {})

    # Derive snapshot widget defaults for any keys the preset does not have
    snapshot_defaults = extract_defaults_from_snapshot(snapshot_or_err)
    for ctrl_id, val in snapshot_defaults.items():
        if ctrl_id not in merged:
            merged[ctrl_id] = val

    return merged, None


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

    def _resolve_bound_node_value(ctrl_id: str, binding: dict) -> Any:
        node_id = str(binding.get("nodeId", ""))
        if not node_id:
            return None
        node = workflow.get(node_id, {}) if isinstance(workflow, dict) else {}
        if not isinstance(node, dict):
            return None
        inputs = node.get("inputs", {}) or {}
        if not isinstance(inputs, dict):
            return None

        explicit_field = binding.get("widgetName") or binding.get("inputName") or ""
        if explicit_field and explicit_field in inputs:
            return inputs.get(explicit_field)

        aliased_field = _CONTROL_WIDGET_ALIASES.get(ctrl_id, ctrl_id)
        if aliased_field in inputs:
            return inputs.get(aliased_field)

        node_type = node.get("class_type", "")
        widget_schemas = _NODE_WIDGET_SCHEMAS.get(node_type, {})
        text_like_fields = []
        if ctrl_id in ("prompt", "negative_prompt", "instruction", "replacement_prompt"):
            text_like_fields = ["text", "value"]
        for field_name in text_like_fields:
            if field_name in inputs:
                return inputs.get(field_name)
        if len(widget_schemas) == 1:
            only_field = next(iter(widget_schemas.keys()))
            if only_field in inputs:
                return inputs.get(only_field)
        return None

    for ctrl_id, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        kind = binding.get("kind", "")
        if kind == "widget":
            name_key = "widgetName"
        elif kind == "input":
            name_key = "inputName"
        elif kind == "node":
            value = _resolve_bound_node_value(ctrl_id, binding)
            if value is not None:
                defaults[ctrl_id] = value
            continue
        else:
            continue  # skip "node" and "output" kinds
        node_id = binding.get("nodeId", "")
        widget_name = binding.get(name_key, "")
        if not node_id or not widget_name:
            continue
        node = workflow.get(node_id, {})
        inputs = node.get("inputs", {})
        if widget_name in inputs:
            value = inputs[widget_name]
            # Skip ComfyUI internal connection specs (e.g. steps=["937", 0])
            if not _is_connection_spec(value):
                defaults[ctrl_id] = value

    for ctrl_id in _AUTO_DERIVE_CONTROLS:
        if ctrl_id in defaults:
            continue
        found = _find_node_for_control(workflow, ctrl_id)
        if found is not None and found["value"] is not None:
            value = found["value"]
            # Skip ComfyUI internal connection specs (e.g. steps=["937", 0])
            if not _is_connection_spec(value):
                defaults[ctrl_id] = value

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


def _augment_slots_with_auto_derive(
    slots: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    """Add slot mappings for controls derivable from workflow nodes."""
    if not isinstance(slots, dict):
        slots = {}
    if not isinstance(workflow, dict):
        return slots
    for ctrl_id in _AUTO_DERIVE_CONTROLS:
        if ctrl_id in slots:
            continue
        found = _find_node_for_control(workflow, ctrl_id)
        if found is None:
            continue
        slots[ctrl_id] = {
            "node_id": found["node_id"],
            "field": found["widget_name"],
            "path": ["inputs", found["widget_name"]],
        }
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


def _is_connection_spec(value: Any) -> bool:
    """Return True if *value* looks like a ComfyUI internal node connection spec.

    Connection specs are lists/tuples of length ≥ 2 where the first element
    is a node identifier (string or int) and the second is an output slot
    index (int).  Example: ``["1178", 0]`` or ``[9, 0]``.

    These are internal wiring artefacts produced by ``_build_resolved_controls``
    when a slot maps to a linked node output rather than a widget value.
    They must be filtered out before persistence so that frontend/history
    metadata only contains user-facing control values.
    """
    if not isinstance(value, (list, tuple)):
        return False
    if len(value) < 2:
        return False
    # Second element being an int is the strongest signal of a (node_id, slot) pair.
    if not isinstance(value[1], int):
        return False
    # First element must be a node id (string or int).
    if isinstance(value[0], (str, int)):
        return True
    return False


def _sanitize_resolved_controls(
    controls: dict[str, Any],
) -> dict[str, Any]:
    """Remove internal connection-spec values from a resolved_controls dict.

    Returns a new dict with only user-facing scalar values preserved.
    The original dict is not mutated.
    """
    if not isinstance(controls, dict):
        return {}
    return {
        k: v for k, v in controls.items()
        if not _is_connection_spec(v)
    }


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
    experiment_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build metadata dict for experiment definition, carrying Studio info.

    Includes the full experiment source definition (prompts, axes, defaults,
    shared_negative, name) in ``experiment_definition`` so that stored
    metadata retains everything needed for frontend reconstruction and
    history display.
    """
    meta: dict[str, Any] = {
        "studio_preset_ids": preset_ids,
        "studio_snapshot_ids": snapshot_ids,
        "studio_feature_id": feature_id,
    }
    if experiment_source:
        # Store the full experiment definition for later retrieval.
        # Only include non-empty fields to keep metadata compact.
        _src = {}
        if experiment_source.get("prompts"):
            _src["prompts"] = experiment_source["prompts"]
        if experiment_source.get("axes"):
            _src["axes"] = experiment_source["axes"]
        if experiment_source.get("shared_negative"):
            _src["shared_negative"] = experiment_source["shared_negative"]
        if experiment_source.get("defaults"):
            _src["defaults"] = experiment_source["defaults"]
        if experiment_source.get("name"):
            _src["name"] = experiment_source["name"]
        if _src:
            meta["experiment_definition"] = _src
    return meta


# ── Spec / compilation building ────────────────────────────────────────────


def build_single_run_spec(
    preset: dict[str, Any],
    snapshot: dict[str, Any],
    feature_id: str,
    controls: dict[str, Any],
    node_dir: str | os.PathLike,
    trace_ctx: dict | None = None,
    *,
    modal_options: dict | None = None,
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

    If *trace_ctx* is provided (a dict with browser timestamps such as
    ``t0_perf_ms`` / ``t0_client_press``), it is stored in each cell's
    ``"trace"`` key so that ``LocalRemoteInvoker.run_cell`` can forward it
    to ``run_prompt_stream`` and add local observation stages.
    """
    # Validate first — ensures build helpers never bypass validation
    validation = validate_studio_run(preset, snapshot, feature_id)
    if validation.get("error"):
        return validation

    # ── Task 2: Control coercion before _apply_controls_to_workflow ─────
    # 1. Required text control must not be whitespace-only
    _val = controls.get("prompt")
    if isinstance(_val, str) and _val.strip() == "":
        return {"error": "prompt: Value must not be empty or whitespace-only"}
    # 2. Validate scalar controls against snapshot schemas
    _schemas = derive_control_schemas_from_snapshot(snapshot)
    _control_errors = validate_controls_against_schema(controls, _schemas, feature_id)
    if _control_errors:
        return {"error": "; ".join(
            f"{e['field']}: {e['message']}" for e in _control_errors
        )}

    exp_id = _make_studio_experiment_id()

    # Deep copy so stored data is never mutated
    workflow = copy.deepcopy(_get_executable_workflow(snapshot.get("apiPromptJson"))) or {}
    _repair_missing_clip_inputs(workflow)
    _repair_missing_vae_inputs(workflow)
    node_bindings = copy.deepcopy(snapshot.get("nodeBindings", {})) or {}

    # Map bindings to slots
    slots = map_studio_bindings_to_slots(node_bindings)
    slots = _augment_slots_with_auto_derive(slots, workflow)

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

    # ── Production workflow compilation ──────────────────────────────────
    # Normalize production options.  The normalizer never validates
    # output_node_ids — that is the surface's responsibility.
    production_options = normalize_production_options(modal_options)
    _prod_explicitly_disabled = bool(
        isinstance(modal_options, dict)
        and isinstance(modal_options.get("production"), dict)
        and modal_options["production"].get("enabled") is False
    )
    _prod_default_applied = bool(
        not modal_options
        or "production" not in (modal_options or {})
    )

    production_report = None
    production_workflow = workflow
    _prod_output_source = "none"

    if production_options.get("enabled"):
        # ── Derive output_node_ids from the snapshot ──────────────────────
        # Snapshot carries outputNodeId (a single node ID string).
        # Caller-provided output_node_ids in modal_options take precedence.
        _caller_output_ids = production_options.get("output_node_ids", [])
        _snapshot_output = snapshot.get("outputNodeId", "") or ""
        _derived_output_ids = []

        if _caller_output_ids:
            _derived_output_ids = list(_caller_output_ids)
            _prod_output_source = "caller"
        elif _snapshot_output:
            _derived_output_ids = [str(_snapshot_output).strip()]
            _prod_output_source = "preset_binding"
        else:
            # Check nodeBindings for kind=="output" binding
            for _bk, _bv in (snapshot.get("nodeBindings", {}) or {}).items():
                if isinstance(_bv, dict) and _bv.get("kind") == "output":
                    _nid = str(_bv.get("nodeId", "")).strip()
                    if _nid:
                        _derived_output_ids = [_nid]
                        _prod_output_source = "preset_binding"
                        break

        if not _derived_output_ids:
            return {"error": (
                "Production mode is enabled but no output node ID could be derived. "
                "The preset snapshot has no outputNodeId and no output binding. "
                "Either disable production or bind an output node in the preset wizard."
            )}

        production_options["output_node_ids"] = _derived_output_ids

        # ── Compile ───────────────────────────────────────────────────────
        # Compile whenever production is enabled (including default-applied
        # when modal_options is omitted).  The only skip is explicit
        # enabled=False checked above.  No existence pre-check — let
        # compile_production_workflow's precise ValueError propagate.
        try:
            plan = compile_production_workflow(
                workflow, production_options, allow_direct_output_rewrite=True
            )
            production_workflow = plan.compiled_workflow
            production_report = plan.report
        except Exception:
            raise

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

    _prod_enabled = bool(production_options.get("enabled"))
    _prod_output_ids = production_options.get("output_node_ids", []) if _prod_enabled else []
    _prod_plan_used = bool(production_report and production_report.get("enabled"))

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
                "workflow": production_workflow,
                "slots": slots,
                "loader_target_groups": [],
                "lora_slots": [],
                "studio_meta": studio_meta,
                "production_report": production_report,
                "production_options": production_options if _prod_enabled else None,
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
                "trace": dict(trace_ctx) if trace_ctx else {},
                "production_report": production_report,
            }
        ],
        "duplicate_count": 0,
        "warnings": [],
        "studio_meta": studio_meta,
        "production_report": production_report,
        "production_options": production_options if _prod_enabled else None,
        # Diagnostic fields — hash values sourced from compiler report
        "execution_surface": "studio_single",
        "production_default_applied": _prod_default_applied,
        "production_explicitly_disabled": _prod_explicitly_disabled,
        "production_output_source": _prod_output_source,
        "production_output_ids": _prod_output_ids,
        "production_plan_used": _prod_plan_used,
        "production_output_count": len(_prod_output_ids),
        "production_source_hash": (production_report or {}).get("source_workflow_hash", ""),
        "production_plan_hash": (production_report or {}).get("production_plan_hash", ""),
        "production_compiled_hash": (production_report or {}).get("compiled_workflow_hash", ""),
        "runner_workflow_hash": (production_report or {}).get("runner_workflow_hash", ""),
    }

    return compilation


def build_experiment_spec(
    preset_snapshot_pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    feature_id: str,
    experiment_def: dict[str, Any],
    node_dir: str | os.PathLike,
    *,
    modal_options: dict | None = None,
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

    _preset_to_profile: dict[str, str] = {}
    for idx, (preset, snapshot) in enumerate(preset_snapshot_pairs):
        pid = preset.get("id", "")
        sid = snapshot.get("id", "")
        all_preset_ids.append(pid)
        all_snapshot_ids.append(sid)
        _profile_id = f"studio_{pid}_{idx}"
        _preset_to_profile[pid] = _profile_id

        spec_workflows.append({
            "profile_id": _profile_id,
            "loader_target_group_id": "g_default",
            "main_triple": {"id": "main", "unet": "", "clip": "", "vae": ""},
            "subprofile_triples": [],
            "selected_triple_ids": ["main"],
            "lora_slots": [],
        })

    # ── Build workflow/slot lookup early (for axis validation) ─────────
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
        slots_map[profile_id] = _augment_slots_with_auto_derive(
            slots_map[profile_id], workflow_map[profile_id]
        )

    # Collect all slot keys across all presets (union)
    all_slot_keys: set[str] = set()
    for slots in slots_map.values():
        all_slot_keys.update(slots.keys())

    # Build per-preset slot key sets for individual validation
    preset_slot_keys: dict[str, set[str]] = {}
    for pf_id, slots in slots_map.items():
        preset_slot_keys[pf_id] = set(slots.keys())

    # ── Parse axes (copy to avoid mutating experiment_def) ────────────
    raw_axes = copy.deepcopy(experiment_def.get("axes", {})) or {}

    # Detect nested compiler format vs flat Studio format
    has_nested_format = (
        isinstance(raw_axes, dict)
        and ("shared" in raw_axes or "per_workflow" in raw_axes)
    )

    if has_nested_format:
        shared_source = raw_axes.get("shared", {}) or {}
        per_workflow_source = raw_axes.get("per_workflow", {}) or {}
    else:
        shared_source = raw_axes
        per_workflow_source = {}

    # Extract special axes handled at the adapter level.
    # Check BOTH the flat raw_axes level AND the nested shared_source level
    # so that mixed-format payloads (prompt at flat level + shared at nested)
    # are handled robustly and prompt axis values are never lost.
    prompt_axis_values: list | None = None
    negative_prompt_axis_values: list | None = None

    # 1. Check flat level (applies to pure flat AND mixed-format payloads)
    if "prompt" in raw_axes:
        p_axis = raw_axes.pop("prompt", {})
        if isinstance(p_axis, dict):
            prompt_axis_values = p_axis.get("values", [])

    if "negative_prompt" in raw_axes:
        np_axis = raw_axes.pop("negative_prompt", {})
        if isinstance(np_axis, dict):
            negative_prompt_axis_values = np_axis.get("values", [])

    # 2. Fallback: check nested shared level (pure nested format)
    if prompt_axis_values is None and has_nested_format:
        p_axis = shared_source.pop("prompt", {})
        if isinstance(p_axis, dict):
            prompt_axis_values = p_axis.get("values", [])

    if negative_prompt_axis_values is None and has_nested_format:
        np_axis = shared_source.pop("negative_prompt", {})
        if isinstance(np_axis, dict):
            negative_prompt_axis_values = np_axis.get("values", [])

    # ── Build prompt items ─────────────────────────────────────────────
    spec_prompts: list[dict[str, Any]] = []

    if prompt_axis_values:
        # Prompt axis overrides the base prompt list
        for i, text in enumerate(prompt_axis_values):
            text_str = str(text) if text is not None else ""
            spec_prompts.append({
                "id": f"prompt_axis_{i}",
                "label": text_str[:60],
                "text": text_str,
                "negative": None,
                "enabled": True,
            })
    else:
        # Use base prompts from experiment_def
        prompts = experiment_def.get("prompts", [])
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
                "negative": p.get("negative", None),  # None = not set
                "enabled": True,
            })

    # Cartesian-expand negative_prompt axis with prompts
    if negative_prompt_axis_values:
        expanded: list[dict[str, Any]] = []
        for p in spec_prompts:
            for np_text in negative_prompt_axis_values:
                np_str = str(np_text) if np_text is not None else None
                new_p = copy.deepcopy(p)
                new_p["negative"] = np_str
                new_p["id"] = f"{p['id']}_neg_{len(expanded)}"
                expanded.append(new_p)
        spec_prompts = expanded

    # Validate prompt/negative_prompt slots when their axes inject values
    if prompt_axis_values and "prompt" not in all_slot_keys:
        return {"error": (
            f"Prompt axis requires a prompt slot, but no selected preset "
            f"has a prompt binding. Re-bind the prompt slot in the preset wizard."
        )}
    if negative_prompt_axis_values and "negative_prompt" not in all_slot_keys:
        return {"error": (
            f"Negative prompt axis requires a negative_prompt slot, but no "
            f"selected preset has a negative_prompt binding. "
            f"Re-bind the negative prompt slot in the preset wizard."
        )}

    # ── Convert remaining shared_source axes to compiler format ────────
    # Auto-derivable axes that do not need explicit slot bindings
    _AUTO_SLOT_AXES = frozenset({
        "seed", "steps", "guidance", "sampler", "scheduler", "denoise",
    })
    # Axes that are compiler-internal (not passed as extra axes)
    _SPECIAL_COMPILER_AXES = frozenset({
        "resolution", "lora_model_strengths", "lora_clip_strengths",
        "shared", "per_workflow",
    })

    compiler_axes: dict[str, Any] = {"shared": {}}
    for ctrl_id, axis_def in shared_source.items():
        if not isinstance(axis_def, dict):
            continue
        # Skip special axes already handled
        if ctrl_id in _SPECIAL_COMPILER_AXES:
            continue
        # Validate: every non-auto-derivable axis must have a slot binding
        # in EVERY selected preset (not just the union).
        if ctrl_id not in _AUTO_SLOT_AXES and ctrl_id not in all_slot_keys:
            return {"error": (
                f"Configured axis {ctrl_id!r} is not bound to any slot in "
                f"the selected preset(s). This axis must be bound in the "
                f"preset wizard before it can be used as an experiment axis."
            )}
        if ctrl_id not in _AUTO_SLOT_AXES and ctrl_id in all_slot_keys:
            # Slot exists in at least one preset — now verify EVERY preset
            missing_presets = [
                pf_id for pf_id, psk in preset_slot_keys.items()
                if ctrl_id not in psk
            ]
            if missing_presets:
                return {"error": (
                    f"Configured axis {ctrl_id!r} is bound in some selected "
                    f"presets but is missing from the following preset(s): "
                    f"{', '.join(missing_presets)}. "
                    f"Bind this slot in every preset wizard before using it "
                    f"as an experiment axis."
                )}
        # Handle both flat format {values: [...]} and compiler format {mode: "list", values: [...]}
        if "mode" in axis_def:
            compiler_axes["shared"][ctrl_id] = dict(axis_def)
        else:
            values_list = axis_def.get("values")
            if isinstance(values_list, list) and len(values_list) > 0:
                compiler_axes["shared"][ctrl_id] = {"mode": "list", "values": values_list}

    # ── Validate per_workflow axes against profile-specific slots ─────
    if per_workflow_source:
        for pw_key, pw_axes in per_workflow_source.items():
            if not isinstance(pw_axes, dict):
                continue
            pw_profile = _preset_to_profile.get(pw_key, pw_key)
            pw_slot_keys = preset_slot_keys.get(pw_profile, set())
            for axis_id, axis_def in pw_axes.items():
                if not isinstance(axis_def, dict):
                    continue
                if axis_id in _AUTO_SLOT_AXES:
                    continue
                if axis_id not in pw_slot_keys:
                    return {"error": (
                        f"Configured per_workflow axis {axis_id!r} for "
                        f"preset {pw_key!r} is not bound to any slot in "
                        f"that preset's snapshot. This axis must be bound "
                        f"in the preset wizard before it can be used as "
                        f"a per-workflow axis."
                    )}
        # Propagate per_workflow axes into compiler axes (translate keys
        # from user-facing preset IDs to spec profile_ids).
        _translated_pw: dict[str, dict] = {}
        for pw_key, pw_axes in per_workflow_source.items():
            if not isinstance(pw_axes, dict):
                continue
            pw_profile = _preset_to_profile.get(pw_key, pw_key)
            _translated_pw[pw_profile] = dict(pw_axes)
        compiler_axes["per_workflow"] = _translated_pw

    axes = compiler_axes

    # Preserve the original experiment definition in metadata for history
    # and frontend reconstruction.  Include the full prompts list, axes,
    # and shared_negative so that the stored metadata is self-describing.
    _experiment_source = {
        "prompts": experiment_def.get("prompts", []),
        "axes": experiment_def.get("axes", {}),
        "shared_negative": experiment_def.get("shared_negative"),
        "defaults": experiment_def.get("defaults", {}),
        "name": experiment_def.get("name", ""),
    }

    spec: dict[str, Any] = {
        "experiment_id": _make_studio_experiment_id(),
        "revision": 1,
        "name": experiment_def.get("name", f"Studio {feature_id}"),
        "workflows": spec_workflows,
        # shared_negative defaults to None (not "") so that
        # _build_prompt_image_pairs correctly distinguishes "no shared
        # negative" from "explicit empty string" in _resolve_negative.
        "prompts": {"items": spec_prompts, "shared_negative": experiment_def.get("shared_negative")},
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

    studio_meta = _build_studio_experiment_meta(
        preset_ids=all_preset_ids,
        snapshot_ids=all_snapshot_ids,
        feature_id=feature_id,
        experiment_source=_experiment_source,
    )

    # ── Production compilation per checkpoint ────────────────────────────
    # Normalize production options, then compile each checkpoint's workflow
    # independently so each cell carries its own production_report.
    _prod_options = normalize_production_options(modal_options)
    _prod_explicitly_disabled = bool(
        isinstance(modal_options, dict)
        and isinstance(modal_options.get("production"), dict)
        and modal_options["production"].get("enabled") is False
    )
    _prod_default_applied = bool(
        not modal_options
        or "production" not in (modal_options or {})
    )

    # Build a lookup: profile_id -> snapshot (for outputNodeId derivation)
    _profile_to_snapshot: dict[str, dict] = {}
    for idx, (preset, snapshot) in enumerate(preset_snapshot_pairs):
        pid = preset.get("id", "")
        _profile_id = f"studio_{pid}_{idx}"
        _profile_to_snapshot[_profile_id] = snapshot

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

        # ── Derive output_node_ids from this preset's snapshot ──────────
        _ck_prod_report = None
        _ck_prod_options = None
        if _prod_options.get("enabled"):
            _ck_prod_options = dict(_prod_options)
            _caller_ids = _ck_prod_options.get("output_node_ids", [])
            _snapshot = _profile_to_snapshot.get(pf, {})
            _snap_output = (_snapshot.get("outputNodeId") or "") if isinstance(_snapshot, dict) else ""
            _derived_ids = []

            if _caller_ids:
                _derived_ids = list(_caller_ids)
            elif _snap_output:
                _derived_ids = [str(_snap_output).strip()]
            else:
                # Check nodeBindings for kind=="output"
                for _bk, _bv in (_snapshot.get("nodeBindings", {}) or {}).items():
                    if isinstance(_bv, dict) and _bv.get("kind") == "output":
                        _nid = str(_bv.get("nodeId", "")).strip()
                        if _nid:
                            _derived_ids = [_nid]
                            break

            if not _derived_ids:
                return {"error": (
                    f"Production mode is enabled for preset {pf!r} but no output node ID "
                    f"could be derived from its snapshot. The preset snapshot has no "
                    f"outputNodeId and no output binding. Either disable production or "
                    f"bind an output node in the preset wizard."
                )}

            _ck_prod_options["output_node_ids"] = _derived_ids
            # Compile whenever production is enabled (including default-applied
            # when modal_options is omitted).  The only skip is explicit
            # enabled=False checked before the derivation loop.
            # No existence pre-check — let compile_production_workflow's
            # precise ValueError propagate.
            try:
                _ck_plan = compile_production_workflow(
                    wf, _ck_prod_options, allow_direct_output_rewrite=True
                )
                ck["workflow"] = _ck_plan.compiled_workflow
                _ck_prod_report = _ck_plan.report
            except Exception:
                raise
        ck["production_report"] = _ck_prod_report
        if _ck_prod_options:
            ck["production_options"] = _ck_prod_options

    for cell in compilation.get("cells", []):
        cell["studio_meta"] = studio_meta
        # Carry the production_report from the checkpoint onto each cell
        _ck_id = cell.get("checkpoint_id", "")
        _match_ck = next(
            (ck for ck in compilation.get("checkpoints", []) if ck.get("id") == _ck_id),
            None,
        )
        if _match_ck:
            cell["production_report"] = _match_ck.get("production_report")
            cell["production_options"] = _match_ck.get("production_options")

    compilation["studio_meta"] = studio_meta
    compilation["production_report"] = None  # experiments have per-cell reports
    compilation["production_options"] = _prod_options if (_prod_options or {}).get("enabled") else None
    # Diagnostic fields — per-checkpoint hashes sourced from each report
    compilation["execution_surface"] = "studio_experiment"
    compilation["production_default_applied"] = _prod_default_applied
    compilation["production_explicitly_disabled"] = _prod_explicitly_disabled
    compilation["production_plan_used"] = bool(
        any(
            (ck.get("production_report") or {}).get("enabled")
            for ck in compilation.get("checkpoints", [])
        )
    )
    # Reference hashes from the first compiled checkpoint's report (if any).
    # Each checkpoint carries its own full report for per-cell matching.
    _first_compiled_ck = next(
        (ck for ck in compilation.get("checkpoints", []) if ck.get("production_report")),
        None,
    )
    _first_report = (_first_compiled_ck or {}).get("production_report") or {}
    compilation["production_source_hash"] = _first_report.get("source_workflow_hash", "")
    compilation["production_plan_hash"] = _first_report.get("production_plan_hash", "")
    compilation["production_compiled_hash"] = _first_report.get("compiled_workflow_hash", "")
    compilation["runner_workflow_hash"] = _first_report.get("runner_workflow_hash", "")
    return compilation


# ── Async scheduler helpers ────────────────────────────────────────────────


async def _schedule_and_start(
    exp_id: str,
    compilation: dict[str, Any],
    REGISTRY: Any,
    node_dir: str | os.PathLike = "",
    *,
    profile_preparer: Any = None,
    gpu: Any = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
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
    from local_artifacts import get_studio_outputs_dir
    from modal_client import run_prompt_stream

    # ── Merge compilation's effective production options into modal_options ──
    # The production_report carries output_node_ids, schema, rewrite state, etc.
    # that the compiled workflow depends on.  Forward these as a production key
    # inside modal_options so LocalRemoteInvoker.run_cell can merge them into
    # the remote call (and comfyapp's compiled-workflow hash check passes).
    _effective_modal_options = dict(modal_options) if modal_options else {}
    _prod_report = compilation.get("production_report")
    if _prod_report and _prod_report.get("enabled"):
        _prod_options = dict(compilation.get("production_options", {}))
        # Derive output_node_ids from the report if the normalizer left them empty
        if not _prod_options.get("output_node_ids") and _prod_report.get("output_node_ids"):
            _prod_options["output_node_ids"] = list(_prod_report["output_node_ids"])
        if not _prod_options.get("output_node_ids") and _prod_report.get("kept_node_ids"):
            # Fallback: use kept_node_ids as output binding (all compiled nodes)
            _prod_options["output_node_ids"] = list(_prod_report["kept_node_ids"])
        _effective_modal_options["production"] = _prod_options

    # ── Build a stream_event_sink that broadcasts nonterminal progress ────
    # as experiment.worker.progress via PromptServer.send_sync (no-op safe
    # when PromptServer is unavailable / outside ComfyUI).
    # Import PromptServer dynamically to avoid import cycles.
    async def _progress_sink(detail: dict) -> None:
        """Broadcast a progress detail payload as experiment.worker.progress.

        The *detail* dict is the normalised detail from
        ``_desired_map_stream_message`` (type, phase, message, node, step,
        max, experiment_id, checkpoint_id, cell_key, attempt_id, sequence).
        It is sent directly as the ``experiment.worker.progress`` WS event
        detail so the frontend receives exactly the fields it needs.
        """
        try:
            from server import PromptServer
            server = PromptServer.instance
            if server is not None:
                server.send_sync("experiment.worker.progress", dict(detail))
        except Exception:
            pass

    invoker = LocalRemoteInvoker(
        run_prompt_stream,
        experiment_id=exp_id,
        node_dir=str(node_dir) if node_dir else "",
        stream_event_sink=_progress_sink,
        profile_preparer=profile_preparer,
        gpu=gpu,
        modal_options=_effective_modal_options,
        workspace=workspace,
        production_report=_prod_report,
        studio_output_dir=str(get_studio_outputs_dir()),
    )
    sched = await REGISTRY.get_or_create_scheduler(
        exp_id,
        compilation=compilation,
        invoker=invoker,
        max_containers=1,
    )

    # Apply a stop requested before the background scheduler was registered.
    consume_pending_stop = getattr(REGISTRY, "consume_pending_stop", None)
    if callable(consume_pending_stop) and consume_pending_stop(exp_id):
        await sched.stop_now()

    try:
        result = await sched.start()
    except Exception as exc:
        # Finalize the submission record as failed — preserve elapsed
        # timings without fabricating queue_ms or aliases.
        run_history_id = compilation.get("run_history_id", "")
        if run_history_id:
            fail_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            try:
                fail_timings: dict[str, Any] = {}
                fail_timing_sources: dict[str, str] = {}
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
                            fail_dt = datetime.fromisoformat(fail_ts.replace("Z", "+00:00"))
                            # end_to_end_total_ms from submission to failure
                            e2e_ms = int((fail_dt - sub_dt).total_seconds() * 1000)
                            if e2e_ms >= 0:
                                fail_timings["end_to_end_total_ms"] = e2e_ms
                                fail_timing_sources["end_to_end_total_ms"] = "local_server_observed"
                            # scheduler_execution_ms from generation_start to failure
                            sched_ms = int((fail_dt - generation_start_dt).total_seconds() * 1000)
                            if sched_ms >= 0:
                                fail_timings["scheduler_execution_ms"] = sched_ms
                                fail_timing_sources["scheduler_execution_ms"] = "local_server_observed"
                        except Exception:
                            pass
                    # If no submission time, still try scheduler duration
                    else:
                        try:
                            fail_dt = datetime.fromisoformat(fail_ts.replace("Z", "+00:00"))
                            sched_ms = int((fail_dt - generation_start_dt).total_seconds() * 1000)
                            if sched_ms >= 0:
                                fail_timings["scheduler_execution_ms"] = sched_ms
                                fail_timing_sources["scheduler_execution_ms"] = "local_server_observed"
                        except Exception:
                            pass
                # No queue_ms, studio_queue_ms, generation_ms, or remote aliases
                # — those are meaningful only for successful runs with a trace.
                if fail_timing_sources:
                    fail_timings["timing_sources"] = fail_timing_sources
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

    # ── Inspect experiment journal for timing_payload and output metadata ──
    output_paths: list[str] = []
    primary_asset_id = ""
    attempt_id = ""
    cell_key = ""
    checkpoint_id = ""
    resolved_meta: dict = {}
    has_cell_completed = False
    has_cell_failed = False
    timing_payload: dict | None = None

    try:
        store = REGISTRY.store(exp_id)
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
                # Capture timing_payload from the latest cell.completed
                tp = pl.get("timing_payload")
                if tp:
                    timing_payload = tp
            elif ev.get("type") == "cell.failed":
                has_cell_failed = True
                pl = ev.get("payload", {}) or {}
                # Capture timing_payload from cell.failed if not already obtained
                tp = pl.get("timing_payload")
                if tp and timing_payload is None:
                    timing_payload = tp
    except Exception:
        _log.warning("Failed to read journal events for %s", exp_id)

    # ── Build timing dict ──────────────────────────────────────────────────
    timings: dict[str, Any] = {}
    timing_sources: dict[str, str] = {}

    # 1. Local wall-clock observations (exact values, no faked floor)
    if submission_started_at and completed_at:
        try:
            sub_dt = datetime.fromisoformat(submission_started_at.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            pre_dt = generation_start_dt
            queue_ms = int((pre_dt - sub_dt).total_seconds() * 1000)
            scheduler_wall_ms = int((end_dt - pre_dt).total_seconds() * 1000)
            end_to_end_ms = int((end_dt - sub_dt).total_seconds() * 1000)
        except Exception:
            queue_ms = 0
            scheduler_wall_ms = 0
            end_to_end_ms = 0

        # New-run queue time: use studio_queue_ms (legacy queue_ms remains
        # readable for backward compatibility, but we write the new key).
        if has_cell_completed:
            timings["studio_queue_ms"] = max(0, queue_ms)
            timing_sources["studio_queue_ms"] = "local_server_observed"

        # NO generation_ms or total_ms — legacy names not written
        timings["scheduler_execution_ms"] = max(0, scheduler_wall_ms)
        timings["end_to_end_total_ms"] = max(0, end_to_end_ms)
        timing_sources["scheduler_execution_ms"] = "local_server_observed"
        timing_sources["end_to_end_total_ms"] = "local_server_observed"

    # 2. Create a minimal local Studio timing summary and merge remote trace
    #    into it using the shared merger (same deterministic rules as the
    #    normal graph path).
    local_timing_summary: dict[str, Any] = {
        "stages": {},
        "deltas_ms": {},
        "derived_ms": {},
        "trace_version": TRACE_VERSION,
    }
    if timing_payload:
        remote_trace = timing_payload.get("trace", {}) or {}
        merge_remote_trace_into(local_timing_summary, remote_trace)

    # 3. Canonical alias map — translate merged trace deltas to top-level
    #    canonical keys with _ms suffix for the frontend normalizer.
    #
    #    Each entry: (canonical_key, source_location, timing_source_label)
    merged_deltas = local_timing_summary.get("deltas_ms", {}) or {}
    merged_derived = local_timing_summary.get("derived_ms", {}) or {}

    _CANONICAL_ALIAS_MAP: list[tuple[str, str, str]] = [
        # (canonical_key,              raw_deltas_key,     source)
        ("clip_load_ms",               "clip_load",        "remote_trace"),
        ("clip_encode_ms",             "clip_encode",      "remote_trace"),
        ("sampling_ms",                "sampler",          "remote_trace"),
        ("vae_decode_ms",              "vae_decode",       "remote_trace"),
        ("image_io_ms",                "image_io",         "remote_trace"),
        ("remote_inference_total_ms",  "inference_total",  "remote_trace"),
        # Extended: validation, graph overhead, individual model loads
        # These only appear when the remote trace provides them —
        # conditional on merged_deltas.get(raw_key) returning a value.
        ("remote_validation_ms",       "t3_to_t3b",       "remote_trace"),
        ("graph_overhead_ms",          "graph_overhead",   "remote_trace"),
        ("unet_load_ms",               "unet_load",        "remote_trace"),
        ("vae_load_ms",                "vae_load",         "remote_trace"),
    ]
    remote_timings: dict[str, Any] = {}
    for canonical_key, raw_key, source in _CANONICAL_ALIAS_MAP:
        val = merged_deltas.get(raw_key)
        if val is not None:
            timings[canonical_key] = val
            timing_sources[canonical_key] = source
            remote_timings[raw_key] = val

    # Restore timing from _restore_timing block — map to top-level keys
    # only (NOT inside remote_timings) so consumers never sum restore
    # into execution metrics like inference_total.
    if timing_payload:
        restore = timing_payload.get("_restore_timing", {}) or {}
        restore_total = restore.get("restore_total_ms")
        if restore_total is not None:
            timings["restore_total_ms"] = restore_total
            timing_sources["restore_total_ms"] = "remote_trace"
            timings["remote_restore_ms"] = restore_total
            timing_sources["remote_restore_ms"] = "remote_trace"

    # Preserve raw remote_timings block for diagnostic access.
    if remote_timings:
        timings["remote_timings"] = dict(remote_timings)
        timing_sources["remote_timings"] = "derived"

    # Local materialization wall time from merged derived_ms
    _local_mat_ms = merged_derived.get("local_output_materialization_ms")
    if _local_mat_ms is not None:
        timings["local_output_materialization_ms"] = _local_mat_ms
        timing_sources["local_output_materialization_ms"] = "derived"

    # 4. Preserve compact raw trace structures (no base64)
    if timing_payload:
        for raw_key in ("trace", "wall_clock_trace", "_wall_clock_summary",
                         "_restore_timing", "scheduler_trace"):
            val = timing_payload.get(raw_key)
            if val is not None:
                timings[raw_key] = copy.deepcopy(val)
                timing_sources[raw_key] = "remote_trace"

    # ── platform_pre_restore_ms: cross-process inferred window ─────────
    # Derived from local t2_submit timestamp + remote restore_start_unix_s.
    # Only present when BOTH timestamps exist.  Never fabricated.
    _local_trace_dict = local_timing_summary.get("stages", {}) or {}
    _t2_submit = _local_trace_dict.get("t2_local_modal_submit_start") or _local_trace_dict.get("t2_local_dispatch")
    if timing_payload:
        _restore_block = timing_payload.get("_restore_timing", {}) or {}
        _restore_start = _restore_block.get("restore_start_unix_s")
        if _t2_submit is not None and _restore_start is not None:
            _pre_restore_ms = round((_restore_start - _t2_submit) * 1000, 2)
            if _pre_restore_ms >= 0:
                timings["platform_pre_restore_ms"] = _pre_restore_ms
                timing_sources["platform_pre_restore_ms"] = "cross_process_inferred"

    # 5. trace_available flag
    timings["trace_available"] = bool(timing_payload)

    # 6. Attach timing_sources metadata
    if timing_sources:
        timings["timing_sources"] = timing_sources

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
    # Sanitise resolved_controls: remove internal connection-spec values
    # (e.g. ``output: ["1178", 0]``) that are wiring artefacts, not user
    # controls.  Use the sanitised copy for persistence and flattening.
    _resolved_sanitised = _sanitize_resolved_controls(resolved_controls or {})
    meta_merge["resolved_controls"] = dict(_resolved_sanitised)
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
    # Uses the sanitised copy (connection specs already removed).
    canonical_aliases = _flatten_canonical_aliases(
        _resolved_sanitised,
        resolved_meta if has_cell_completed else None,
    )

    # Fallback to requested_controls for canonical keys that resolved
    # controls cannot provide (e.g. when auto-derive produces no slot
    # for seed/steps/guidance/sampler/scheduler/denoise).
    if meta_merge.get("requested_controls"):
        for ck in _CANONICAL_ALIAS_KEYS:
            if ck not in canonical_aliases or canonical_aliases.get(ck) is None:
                fv = meta_merge["requested_controls"].get(ck)
                if fv is not None:
                    canonical_aliases[ck] = fv

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
    trace_ctx: dict | None = None,
    *,
    profile_preparer: Any = None,
    gpu: Any = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
) -> dict[str, Any]:
    """Handle a single Studio run request.

    Called from the route handler. Performs validation, builds the
    compilation, creates an experiment via REGISTRY, and schedules
    the runner.

    *trace_ctx* is an optional dict carrying browser-side timestamps
    (``t0_perf_ms`` / ``t0_client_press``, captured by the Studio UI).
    It is propagated to each cell's ``"trace"`` key so that
    ``LocalRemoteInvoker.run_cell`` can forward it to the remote Modal
    function and add local observation stages.

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

    # 3. Build single-run compilation (includes validation + production)
    # Pass trace_ctx so each cell carries browser timestamps and the trace
    # flows through to LocalRemoteInvoker.run_cell -> run_prompt_stream.
    compilation = build_single_run_spec(
        preset, snapshot, feature_id, controls, node_dir,
        trace_ctx=trace_ctx, modal_options=modal_options,
    )
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

        # ── Build shared profile-preparer closure for the Studio path ──
        # Uses the same warmup_profile.prepare_active_next_profile that
        # __init__._execute_job calls, but with a setter sourced from
        # modal_client.  The workflow hash is computed from the ACTUAL
        # resolved_workflow (passed to the closure by run_cell), NOT
        # from the pre-compilation workflow, so that post-resolution
        # mutations are captured.
        _ws_captured = workspace

        async def _studio_profile_preparer(resolved_workflow, cell):
            """Prepare active-next warmup profile using the fully resolved
            cell workflow.  Hashes the actual resolved_workflow passed by
            LocalRemoteInvoker.run_cell.

            Forwards production options from the compilation data so that
            omitted production (default-enabled) is reflected in the
            activation payload.
            """
            try:
                from experiment_runner import _workflow_sha256
                from modal_client import set_active_warmup_profile as _remote_setter
                _hash = _workflow_sha256(resolved_workflow) if isinstance(resolved_workflow, dict) else ""
                # Derive production options from the compilation data.
                # The compilation carries production_options when production
                # is enabled; prefer the cell-level production_report when
                # available, then fall back to the compilation-level one.
                _cell_report = cell.get("production_report")
                _compilation_prod_opts = compilation.get("production_options") or {}
                _compilation_prod_report = compilation.get("production_report") or {}
                _active_prod_opts: dict | None = None
                _prod_report = _cell_report or _compilation_prod_report
                if _prod_report and _prod_report.get("enabled"):
                    _active_prod_opts = dict(_compilation_prod_opts) if _compilation_prod_opts else {}
                    _active_prod_opts.setdefault("enabled", True)
                    # Forward output_node_ids from the report if not present
                    if not _active_prod_opts.get("output_node_ids"):
                        _ids = _prod_report.get("output_node_ids") or _prod_report.get("kept_node_ids") or []
                        if _ids:
                            _active_prod_opts["output_node_ids"] = list(_ids)
                await prepare_active_next_profile(
                    resolved_workflow,
                    _hash,
                    production_options=_active_prod_opts,
                    workspace=_ws_captured,
                    setter=_remote_setter,
                )
            except Exception:
                _log.warning("Studio profile preparer failed (non-fatal)")

        # Start scheduler in background — report truthful submission status
        import asyncio

        async def _start_and_catch(exp_id, compilation, REGISTRY, nd,
                                    pp=None, g=None, mo=None, ws=None):
            """Start scheduler and persist error events on failure."""
            try:
                _log.info("Scheduler start called for experiment %s", exp_id)
                result = await _schedule_and_start(
                    exp_id, compilation, REGISTRY, node_dir=nd,
                    profile_preparer=pp, gpu=g, modal_options=mo, workspace=ws,
                )
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
                    _start_and_catch(exp_id, compilation, REGISTRY, node_dir,
                                     pp=_studio_profile_preparer, g=gpu, mo=modal_options, ws=workspace),
                    exp_id,
                )
            else:
                asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir,
                                             pp=_studio_profile_preparer, g=gpu, mo=modal_options, ws=workspace))
        except RuntimeError:
            asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir,
                                         pp=_studio_profile_preparer, g=gpu, mo=modal_options, ws=workspace))
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
    *,
    modal_options: dict | None = None,
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
    compilation = build_experiment_spec(pairs, feature_id, experiment_def, node_dir, modal_options=modal_options)
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

        async def _start_and_catch(exp_id, compilation, REGISTRY, nd, mo=None):
            """Start scheduler and persist error events on failure."""
            try:
                _log.info("Scheduler start called for experiment %s", exp_id)
                result = await _schedule_and_start(exp_id, compilation, REGISTRY, node_dir=nd, modal_options=mo)
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
                    _start_and_catch(exp_id, compilation, REGISTRY, node_dir, mo=modal_options),
                    exp_id,
                )
            else:
                asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir, mo=modal_options))
        except RuntimeError:
            asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir, mo=modal_options))
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
