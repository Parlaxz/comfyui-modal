"""Backend adapter for Studio preset execution runtime.

Bridges Studio presets/snapshots into the existing experiment
scheduler/runner pipeline OR a direct single-run path.

Key workflows
-------------
1. **Single run — Direct** (``POST /comfymodal/studio/run`` — one normal run):
   Load preset + snapshot, validate, build a single-cell compilation
   with the snapshot workflow, mapped bindings, and control overrides.
   Execute the cell directly via ``LocalRemoteInvoker.run_cell`` —
   no experiment scheduler, runner, leases, or journal created.
   Returns the completed result synchronously.

2. **Single run — Scheduler** (same endpoint, multi-cell/experiment):
   Same preparation, then schedule via ``REGISTRY.get_or_create_scheduler``
   → ``start()``.  Used when the request is an experiment or the caller
   explicitly requests the scheduler path.

3. **Experiment** (``POST /comfymodal/studio/experiment``):
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
from typing import Any, Callable

try:
    import nodes
except Exception:  # pragma: no cover - runtime-only dependency in some contexts
    nodes = None

from production_workflow import (
    normalize_production_options,
    HASH_SCHEMA_VERSION,
    PRODUCTION_PLAN_SCHEMA_VERSION,
)
from run_prompt_options import (
    build_run_prompt_options,
    ensure_run_prompt_options,
)
from canonical_execution import RunTrace, execute_modal_prompt, prepare_modal_execution
from studio_store import StudioJsonStore, StudioStoreError
from studio_models import (
    _FEATURE_BINDING_KEYS,
    _KNOWN_FEATURE_IDS,
    validate_controls_against_schema,
)
from timing_trace import TRACE_VERSION, coerce_t0_from_browser, merge_remote_trace_into
from warmup_profile import prepare_active_next_profile
from execution_runtime import resolve_execution_mode, MODE_V2

_log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

# Feature IDs whose image/mask input flow is not yet implemented.
# These features are blocked with a run-time reason even when their
# bindings and apiPrompt are present.
_IMAGE_INPUT_FEATURES_UNIMPLEMENTED: set[str] = {"object_remove", "object_replace"}

# Stable error message (no raw exceptions leaked to clients).
_STUDIO_EXECUTION_ERROR_CODE = "STUDIO_EXECUTION_ERROR"
_STABLE_INTERNAL_ERROR = "Internal error processing Studio execution. Retry or inspect the run details."


def _execution_error_response(exc: BaseException, *, operation: str, run_id: str = "") -> dict[str, Any]:
    detail = f"{type(exc).__name__}: {exc}"
    _log.error(
        "Studio execution backend failure",
        extra={
            "error_code": _STUDIO_EXECUTION_ERROR_CODE,
            "operation": operation,
            "run_id": run_id,
            "exception_type": type(exc).__name__,
            "backend_detail": str(exc),
        },
        exc_info=True,
    )
    return {
        "status": "error",
        "message": _STABLE_INTERNAL_ERROR,
        "error_code": _STUDIO_EXECUTION_ERROR_CODE,
        "error": {
            "code": _STUDIO_EXECUTION_ERROR_CODE,
            "operation": operation,
            "run_id": run_id,
            "type": type(exc).__name__,
            "detail": detail,
        },
    }

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


def _derive_output_node_ids(
    snapshot: dict[str, Any] | None,
    caller_output_node_ids: Any = None,
) -> list[str]:
    """Resolve the output binding without inventing a workflow node."""
    candidates = caller_output_node_ids
    if isinstance(candidates, dict):
        candidates = candidates.get("output_node_ids", [])
    if isinstance(candidates, (str, int)) and not isinstance(candidates, bool):
        candidates = [candidates]
    if isinstance(candidates, (list, tuple, set, frozenset)):
        resolved: list[str] = []
        for value in candidates:
            value = str(value).strip()
            if value and value not in resolved:
                resolved.append(value)
        if resolved:
            return resolved

    if not isinstance(snapshot, dict):
        return []
    output_node_id = str(snapshot.get("outputNodeId", "") or "").strip()
    if output_node_id:
        return [output_node_id]
    for binding in (snapshot.get("nodeBindings", {}) or {}).values():
        if not isinstance(binding, dict) or binding.get("kind") != "output":
            continue
        node_id = str(binding.get("nodeId", "") or "").strip()
        if node_id:
            return [node_id]
    return []


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

# Shared canonical alias map used by both scheduler and direct-run paths.
# Maps (top-level_timing_key, raw_deltas_key, timing_source_label).
_CANONICAL_ALIAS_MAP: list[tuple[str, str, str]] = [
    ("clip_load_ms",               "clip_load",        "remote_trace"),
    ("clip_encode_ms",             "clip_encode",      "remote_trace"),
    ("sampling_ms",                "sampler",          "remote_trace"),
    ("vae_decode_ms",              "vae_decode",       "remote_trace"),
    ("image_io_ms",                "image_io",         "remote_trace"),
    ("remote_inference_total_ms",  "inference_total",  "remote_trace"),
    ("remote_validation_ms",       "t3_to_t3b",        "remote_trace"),
    ("graph_overhead_ms",          "graph_overhead",   "remote_trace"),
    ("unet_load_ms",               "unet_load",        "remote_trace"),
    ("vae_load_ms",                "vae_load",         "remote_trace"),
]


def _derive_end_to_end_total_ms(stages: dict[str, Any] | None) -> float | None:
    """Return client-press to materialized-output wall time when observable."""
    if not isinstance(stages, dict):
        return None

    start = stages.get("browser_run_click")
    if start is None:
        start = stages.get("t0_client_press")
    end = stages.get("output_materialized")
    if end is None:
        end = stages.get("t10_local_materialized")

    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return None

    total_ms = round((float(end) - float(start)) * 1000, 2)
    return total_ms if total_ms >= 0 else None


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

        # Compile is NOT performed here for direct single runs — it is
        # delegated to the canonical executor (execute_modal_prompt) so
        # the workflow is compiled exactly once.  The resolved
        # production_options (with output_node_ids) are passed through
        # to the canonical executor via the compilation dict.
        # Production_report remains None (canonical executor will set it).

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
    _mode_resolution = resolve_execution_mode(modal_options=modal_options, extra=trace_ctx)
    studio_meta["execution_mode"] = _mode_resolution["mode"]
    studio_meta["execution_mode_source"] = _mode_resolution["source"]

    _prod_enabled = bool(production_options.get("enabled"))
    _prod_output_ids = production_options.get("output_node_ids", []) if _prod_enabled else []
    # production_plan_used means production is enabled AND output IDs are
    # resolved (even though the actual compile happens in the canonical
    # executor for direct single runs).
    _prod_plan_used = _prod_enabled and bool(_prod_output_ids)

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
                # Pre-set _resolved_workflow to the compiled workflow so
                # _run_checkpoint skips the redundant resolve_and_inject_cell
                # pass (which would deep-copy + re-inject, mutating the hash).
                # For production single-runs the workflow is already fully
                # resolved after controls-apply + compile; re-injection would
                # produce a different canonical hash, failing the guard.
                "_resolved_workflow": production_workflow,  # always the actual workflow (compiled or source)
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
        "execution_mode": _mode_resolution["mode"],
        "execution_mode_source": _mode_resolution["source"],
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
    _mode_resolution = resolve_execution_mode(modal_options=modal_options)
    studio_meta["execution_mode"] = _mode_resolution["mode"]
    studio_meta["execution_mode_source"] = _mode_resolution["source"]

    # ── Production options per checkpoint (no compile — deferred to canonical executor) ──
    # Normalize production options, resolve output_node_ids from each preset's
    # snapshot, but do NOT compile.  The canonical executor compiles each
    # resolved cell exactly once at execution time.
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
        # The canonical executor will compile each cell; we only resolve
        # and store the normalized production_options with output_node_ids.
        if _prod_options.get("enabled"):
            _ck_prod_options = dict(_prod_options)
            _caller_ids = _ck_prod_options.get("output_node_ids", [])
            _snapshot = _profile_to_snapshot.get(pf, {})
            _derived_ids = _derive_output_node_ids(_snapshot, _caller_ids)

            if not _derived_ids:
                return {"error": (
                    f"Production mode is enabled for preset {pf!r} but no output node ID "
                    f"could be derived from its snapshot. The preset snapshot has no "
                    f"outputNodeId and no output binding. Either disable production or "
                    f"bind an output node in the preset wizard."
                )}

            _ck_prod_options["output_node_ids"] = _derived_ids
            # Keep source workflow (do NOT compile here — canonical executor compiles exactly once)
            ck["production_options"] = _ck_prod_options
        else:
            ck["production_options"] = None
        # production_report is None until canonical executor compiles
        ck["production_report"] = None

    for cell in compilation.get("cells", []):
        cell["studio_meta"] = studio_meta
        # Carry the production_options from the checkpoint onto each cell
        _ck_id = cell.get("checkpoint_id", "")
        _match_ck = next(
            (ck for ck in compilation.get("checkpoints", []) if ck.get("id") == _ck_id),
            None,
        )
        if _match_ck:
            cell["production_options"] = _match_ck.get("production_options")
        # production_report is None until canonical executor compiles each cell
        cell["production_report"] = None

    compilation["studio_meta"] = studio_meta
    compilation["production_report"] = None  # experiments have per-cell reports
    compilation["production_options"] = _prod_options if (_prod_options or {}).get("enabled") else None
    # Diagnostic fields — no hashes before execution; downstream receives them from canonical trace
    compilation["execution_surface"] = "studio_experiment"
    compilation["production_default_applied"] = _prod_default_applied
    compilation["production_explicitly_disabled"] = _prod_explicitly_disabled
    compilation["production_plan_used"] = bool(
        _prod_options.get("enabled")
        and any(
            (ck.get("production_options") or {}).get("output_node_ids")
            for ck in compilation.get("checkpoints", [])
        )
    )
    # No fake production_report or hashes before execution — downstream history receives hashes from canonical trace
    return compilation


# ── V2 Playground adapter ───────────────────────────────────────────────────
# Thin compatibility adapter that bridges the existing adapter entrypoints
# to the new PlaygroundService (comfymodal_runtime/playground_service.py).
# The adapter preserves response shapes so callers see no difference.


def _playground_runtime_mode() -> str:
    """Legacy compatibility wrapper. Use execution_runtime.resolve_execution_mode instead."""
    from execution_runtime import resolve_execution_mode
    resolved = resolve_execution_mode()
    return resolved["mode"]


def _record_shadow_plan_comparison(
    context: dict[str, Any],
    feature_id: str,
    controls: dict[str, Any],
    modal_options: dict | None,
) -> None:
    """Build a v2 plan for comparison without publishing or executing it."""
    try:
        from comfymodal_runtime.playground_service import _default_build_execution_plan
        from comfymodal_runtime.contracts import stable_hash

        v2_plan, error = _default_build_execution_plan(
            context["preset"],
            context["snapshot"],
            feature_id,
            controls,
            modal_options=modal_options,
        )
        legacy_workflow = {}
        checkpoints = context.get("compilation", {}).get("checkpoints", [])
        if checkpoints and isinstance(checkpoints[0], dict):
            legacy_workflow = checkpoints[0].get("workflow", {}) or {}
        comparison = {
            "status": "error" if error else "compared",
            "error": error or "",
            "legacy_workflow_hash": stable_hash(legacy_workflow) if legacy_workflow else "",
            "v2_workflow_hash": v2_plan.workflow_hash if v2_plan else "",
            "v2_source_workflow_hash": v2_plan.source_workflow_hash if v2_plan else "",
            "v2_model_stack": dict(v2_plan.model_stack) if v2_plan else {},
            "v2_prefill_bundle": dict(v2_plan.prompt_bundle) if v2_plan else {},
            "v2_output_node_ids": list(v2_plan.output_node_ids) if v2_plan else [],
        }
        context["shadow_plan_comparison"] = comparison
        _log.info("Playground shadow plan comparison: %s", comparison)
    except Exception as exc:
        context["shadow_plan_comparison"] = {
            "status": "error",
            "error": str(exc)[:500],
        }
        _log.warning("Playground shadow plan comparison failed: %s", exc)


async def playground_adapter_direct_run(
    preset_id: str,
    feature_id: str,
    controls: dict[str, Any],
    node_dir: str | os.PathLike,
    *,
    modal_options: dict | None = None,
    gpu: Any = None,
    workspace: dict | None = None,
    trace_ctx: dict | None = None,
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
    studio_output_dir: str | os.PathLike | None = None,
) -> dict[str, Any]:
    """Execute a direct single run via the PlaygroundService.

    Returns a dict with the same shape as
    ``direct_studio_run_completion``.

    This is a **thin adapter** — the actual pipeline lives in
    ``PlaygroundService.execute``.  Tests may call this adapter or
    the service directly with injected fakes.

    Bypasses: matrix compiler, scheduler, leases, journals, worker pool,
    multi-cell machinery.

    *event_sink* is forwarded so progress/status events reach the frontend.
    """
    from comfymodal_runtime.playground_service import (
        _safe_event_sink,
        create_playground_service,
    )

    service = create_playground_service()

    # Try to wire the live profile setter when available
    _profile_setter: Any = None
    try:
        from modal_client import set_active_warmup_profile as _live_setter
        _profile_setter = _live_setter
    except Exception:
        pass

    return await service.execute(
        preset_id=preset_id,
        feature_id=feature_id,
        controls=controls,
        node_dir=node_dir,
        modal_options=modal_options,
        gpu=gpu,
        workspace=workspace,
        trace_ctx=trace_ctx,
        profile_setter=_profile_setter,
        event_sink=event_sink or _safe_event_sink(),
        studio_output_dir=studio_output_dir,
    )


def playground_adapter_sync_run(
    preset_id: str,
    feature_id: str,
    controls: dict[str, Any],
    node_dir: str | os.PathLike,
    *,
    modal_options: dict | None = None,
    gpu: Any = None,
    workspace: dict | None = None,
    trace_ctx: dict | None = None,
    timeout: float = 600.0,
) -> dict[str, Any]:
    """Sync wrapper for ``playground_adapter_direct_run``.

    Spawns a new event loop when called from a running-loop context.
    Matches the sync behaviour of ``handle_studio_run``.
    """
    import asyncio

    async def _run() -> dict[str, Any]:
        return await playground_adapter_direct_run(
            preset_id, feature_id, controls, node_dir,
            modal_options=modal_options,
            gpu=gpu, workspace=workspace, trace_ctx=trace_ctx,
        )

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import threading
        _result_holder: list[dict] = []

        def _run_in_thread() -> None:
            _inner_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_inner_loop)
            try:
                r = _inner_loop.run_until_complete(_run())
                _result_holder.append(r)
            finally:
                _inner_loop.close()

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if not _result_holder:
            return {"status": "error", "message": "Playground run timed out"}
        return _result_holder[0]

    try:
        return asyncio.run(_run())
    except Exception:
        _log.exception("Playground adapter sync run failed for %s", preset_id)
        return {"status": "error", "message": _STABLE_INTERNAL_ERROR}


# ── Run-history single-output save ─────────────────────────────────────────
# Backend implementation for ``POST /comfymodal/run-history/{run_id}/save``.
# Saves ONE known, already-materialized Studio output from a run-history
# record into the configured auto-save folder by reusing the authoritative
# local save pipeline (``output_saver.save_output_image``) and the
# configured folder/format/quality/WebP/sidecar options.  The browser only
# ever selects an ``output_index`` — never a filesystem path — so no
# arbitrary browser filesystem access is possible.

# Recognised image extensions for validating a run output path before reading.
_SAVEABLE_OUTPUT_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})

# Extension → MIME map used when no format conversion is applied.
_EXT_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def _run_extra(run_meta: dict) -> dict:
    """Return the ``extra`` dict of a run-history meta record (safe)."""
    if not isinstance(run_meta, dict):
        return {}
    extra = run_meta.get("extra", {})
    return extra if isinstance(extra, dict) else {}


def resolve_run_output_path(
    run_meta: dict,
    output_index: int,
    asset_resolver_fn: Callable[[str], dict | None] | None = None,
) -> tuple[str, str | None]:
    """Resolve the materialised output path for a run-history record + index.

    Returns ``(path, None)`` on success or ``("", error_message)``.

    Selection precedence (never accepts a browser-supplied path):
      1. ``extra.output_paths`` (list) indexed by *output_index*.
      2. Top-level ``output_path`` when *output_index* is 0.
      3. Legacy ``extra.output_path`` when *output_index* is 0.
      4. Asset registry (experiment-cell records carry asset IDs, not paths):
         - index 0 → ``extra.primary_asset_id``
         - other indexes → ``extra.asset_ids[output_index]``
         Thumbnail assets are re-pointed at their parent original.

    *asset_resolver_fn* maps an asset ID to its registry record (e.g.
    ``REGISTRY.leases().resolve_asset``).  The resolved record's ``path``
    must be a real local file; remote-only ``modal://`` paths are rejected.
    """
    extra = _run_extra(run_meta)
    output_paths = extra.get("output_paths")
    if isinstance(output_paths, (list, tuple)) and output_paths:
        if 0 <= output_index < len(output_paths):
            path = str(output_paths[output_index]).strip()
            if path:
                return path, None
        return "", (
            f"output_index {output_index} is out of range "
            f"(run has {len(output_paths)} output(s))"
        )
    if output_index == 0:
        path = str(run_meta.get("output_path", "") or "").strip()
        if path:
            return path, None
        legacy = str(extra.get("output_path", "") or "").strip()
        if legacy:
            return legacy, None

    # ── Asset-registry fallback (experiment-cell records) ────────────────
    asset_id = ""
    asset_ids = extra.get("asset_ids")
    if isinstance(asset_ids, (list, tuple)) and asset_ids:
        if 0 <= output_index < len(asset_ids):
            asset_id = str(asset_ids[output_index]).strip()
    elif output_index == 0:
        asset_id = str(extra.get("primary_asset_id", "") or "").strip()
    if asset_id:
        if asset_resolver_fn is None:
            return "", (
                f"run has no local output path at index {output_index}; "
                f"asset resolution is unavailable"
            )
        try:
            record = asset_resolver_fn(asset_id)
        except Exception:
            record = None
        # A thumbnail record points at its parent original.
        if isinstance(record, dict) and record.get("variant") == "thumbnail":
            parent_id = str(record.get("parent_asset_id", "") or "")
            if parent_id:
                try:
                    parent = asset_resolver_fn(parent_id)
                except Exception:
                    parent = None
                if isinstance(parent, dict):
                    record = parent
        if isinstance(record, dict):
            path = str(record.get("path", "") or "").strip()
            if path:
                if path.startswith("modal://"):
                    return "", (
                        f"output at index {output_index} has no materialized "
                        f"local path (remote-only asset)"
                    )
                return path, None
        return "", (
            f"output at index {output_index} has no materialized local path"
        )
    return "", f"run has no output at index {output_index}"


def save_run_history_output(
    run_meta: dict,
    *,
    output_index: int = 0,
    output_format: str = "original",
    quality: int = 75,
    webp_lossless_compression: str = "balanced",
    save_folder: str = "",
    save_metadata_sidecar: bool = True,
    comfyui_root: str = "",
    persist_state_fn: Callable[[dict], None] | None = None,
    asset_resolver_fn: Callable[[str], dict | None] | None = None,
) -> dict:
    """Save ONE materialised Studio output from a run-history record.

    Reuses the authoritative automatic local save pipeline
    (``output_saver.save_output_image``) with the configured
    folder/format/quality/WebP/sidecar options.  When a non-``original``
    output format is configured, bytes are first run through the
    authoritative conversion pipeline (``output_converter.convert_image_bytes``)
    — exactly like the normal materialization path.

    **Idempotent retries**: when *run_meta* already records a successful
    save for the same ``output_index`` (``extra.output_saved`` +
    ``extra.output_saved_index``) and the recorded file still exists, no
    new file is written and the previously recorded path is returned.

    *persist_state_fn*, when provided, is called with a state dict after a
    new file is written so the caller can persist per-output saved state
    into the authoritative run meta (which the existing history-index
    upsert then propagates).

    *asset_resolver_fn* maps an asset ID to its registry record and is used
    for experiment-cell records that carry ``asset_ids`` / ``primary_asset_id``
    instead of local paths.

    Returns a structured dict:

    - success: ``{"status": "ok", "saved": True, "already_saved": bool,
      "path", "metadata_path", "output_index", "output_format", "quality",
      "webp_lossless_compression", "mime_type", "file_ext", "byte_count",
      "source_path"}``
    - failure: ``{"status": "error", "message", "reason"}``

    Never fabricates image bytes and never touches the browser filesystem.
    """
    result: dict = {
        "status": "ok",
        "saved": False,
        "already_saved": False,
        "path": "",
        "metadata_path": "",
        "output_index": int(output_index),
        "output_format": output_format,
        "quality": None,
        "webp_lossless_compression": None,
        "mime_type": "",
        "file_ext": "",
        "byte_count": 0,
        "source_path": "",
    }

    if not isinstance(run_meta, dict) or not run_meta.get("run_id"):
        return {
            "status": "error",
            "message": "run metadata is missing run_id",
            "reason": "invalid_run_meta",
        }

    # ── Idempotency gate: a prior successful save wins ─────────────────
    extra = _run_extra(run_meta)
    if (
        extra.get("output_saved") is True
        and extra.get("output_saved_index") == int(output_index)
    ):
        prev_path = str(extra.get("output_saved_path", "") or "")
        if prev_path and os.path.isfile(prev_path):
            return {
                "status": "ok",
                "saved": True,
                "already_saved": True,
                "path": prev_path,
                "metadata_path": str(extra.get("output_saved_metadata_path", "") or ""),
                "output_index": int(output_index),
                "output_format": extra.get("output_saved_format", output_format),
                "quality": extra.get("output_saved_quality"),
                "webp_lossless_compression": extra.get("output_saved_webp_lossless"),
                "mime_type": str(extra.get("output_saved_mime", "") or ""),
                "file_ext": str(extra.get("output_saved_file_ext", "") or ""),
                "byte_count": int(extra.get("output_saved_byte_count", 0) or 0),
                "source_path": str(extra.get("output_saved_source_path", "") or ""),
            }

    # ── Resolve the known Studio output (selected output only) ─────────
    source_path, resolve_error = resolve_run_output_path(
        run_meta, output_index, asset_resolver_fn=asset_resolver_fn
    )
    if resolve_error:
        return {
            "status": "error",
            "message": resolve_error,
            "reason": "output_unresolved",
        }
    if not os.path.isfile(source_path):
        return {
            "status": "error",
            "message": f"output file missing on disk: {source_path}",
            "reason": "output_missing",
        }
    if os.path.splitext(source_path)[1].lower() not in _SAVEABLE_OUTPUT_EXTS:
        return {
            "status": "error",
            "message": f"output is not a saveable image: {source_path}",
            "reason": "unsupported_output_type",
        }

    # ── Read the real bytes (no invented payloads) ─────────────────────
    try:
        with open(source_path, "rb") as f:
            image_bytes = f.read()
    except OSError as exc:
        return {
            "status": "error",
            "message": f"output file unreadable: {exc}",
            "reason": "output_unreadable",
        }
    if not image_bytes:
        return {
            "status": "error",
            "message": "output file is empty",
            "reason": "output_empty",
        }

    # ── Apply the configured conversion when needed ────────────────────
    src_ext = os.path.splitext(source_path)[1].lower() or ".png"
    mime_type = _EXT_TO_MIME.get(src_ext, "image/png")
    file_ext = src_ext
    converted_bytes = image_bytes
    effective_quality: int | None = None
    effective_webp: str | None = None

    if output_format and output_format != "original":
        try:
            from output_converter import convert_image_bytes
            conv = convert_image_bytes(
                image_bytes,
                output_format=output_format,
                quality=int(quality or 75),
                webp_lossless_compression=webp_lossless_compression or "balanced",
            )
        except Exception as exc:
            return {
                "status": "error",
                "message": f"output conversion failed: {exc}",
                "reason": "conversion_failed",
            }
        converted_bytes = conv.get("bytes", image_bytes)
        mime_type = conv.get("mime_type", mime_type)
        file_ext = conv.get("file_ext", file_ext)
        effective_quality = conv.get("quality")
        effective_webp = conv.get("webp_lossless_compression")
    else:
        # Mirror the conversion pipeline's "original" metadata semantics.
        effective_quality = None
        effective_webp = None

    # ── Reuse the authoritative automatic local save pipeline ──────────
    try:
        from output_saver import save_output_image
    except ImportError:
        return {
            "status": "error",
            "message": "output_saver is not available",
            "reason": "saver_unavailable",
        }

    workflow_hash = str(
        run_meta.get("workflow_hash", "")
        or extra.get("workflow_hash", "")
        or ""
    )
    preset_label = str(
        extra.get("preset_label", "")
        or extra.get("studio_preset_id", "")
        or ""
    )
    workflow_name = str(
        run_meta.get("workflow_name", "")
        or preset_label
        or f"run_{run_meta.get('run_id', '')}"
    )
    resolved_controls = extra.get("resolved_controls")
    if not isinstance(resolved_controls, dict):
        resolved_controls = {}
    primary_output = extra.get("primary_output")
    if not isinstance(primary_output, dict):
        primary_output = {}
    seed = resolved_controls.get("seed")
    if seed is None:
        seed = run_meta.get("seed", 0)
    width = resolved_controls.get("width") or primary_output.get("width") or 0
    height = resolved_controls.get("height") or primary_output.get("height") or 0

    extra_meta: dict = {
        "run_id": str(run_meta.get("run_id", "")),
        "kind": str(run_meta.get("kind", "")),
        "output_index": int(output_index),
        "source_path": source_path,
        "saved_via": "run_history_save",
    }
    for key in ("node_id", "output_key", "comparison_side", "source_filename"):
        val = primary_output.get(key) or extra.get(key)
        if val:
            extra_meta[key] = str(val)

    try:
        save_result = save_output_image(
            converted_bytes,
            output_format=output_format,
            file_ext=file_ext,
            mime_type=mime_type,
            quality=effective_quality,
            webp_lossless_compression=effective_webp,
            original_size_bytes=len(image_bytes),
            conversion_time_ms=0,
            save_folder=save_folder,
            save_metadata_sidecar=save_metadata_sidecar,
            workflow_hash=workflow_hash,
            workflow_name=workflow_name,
            seed=str(seed or "0"),
            width=int(width or 0),
            height=int(height or 0),
            index=0,
            comfyui_root=comfyui_root,
            extra_meta=extra_meta,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"save failed: {exc}",
            "reason": "save_exception",
        }

    if not save_result.get("saved"):
        return {
            "status": "error",
            "message": save_result.get("error") or "save failed",
            "reason": "save_failed",
        }

    saved_path = str(save_result.get("path", "") or "")
    saved_metadata_path = str(save_result.get("metadata_path", "") or "")
    saved_byte_count = len(converted_bytes)

    result.update({
        "saved": True,
        "already_saved": False,
        "path": saved_path,
        "metadata_path": saved_metadata_path,
        "output_index": int(output_index),
        "output_format": output_format,
        "quality": effective_quality,
        "webp_lossless_compression": effective_webp,
        "mime_type": mime_type,
        "file_ext": file_ext,
        "byte_count": saved_byte_count,
        "source_path": source_path,
    })

    # ── Persist per-output saved state in the authoritative source meta ─
    # The existing history-index upsert (triggered by the caller's
    # update_run) propagates these fields to the summary index.
    if persist_state_fn is not None:
        from datetime import datetime, timezone
        state = {
            "output_saved": True,
            "output_saved_index": int(output_index),
            "output_saved_path": saved_path,
            "output_saved_metadata_path": saved_metadata_path,
            "output_saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "output_saved_format": output_format,
            "output_saved_quality": effective_quality,
            "output_saved_webp_lossless": effective_webp,
            "output_saved_mime": mime_type,
            "output_saved_file_ext": file_ext,
            "output_saved_byte_count": saved_byte_count,
            "output_saved_source_path": source_path,
        }
        try:
            persist_state_fn(state)
            result["persisted_state"] = True
        except Exception:
            # File is written; a persistence failure means a retry cannot
            # rely on the meta gate.  Surface it as a hard error so the
            # caller can retry without leaving an untracked duplicate file.
            for written_path in (saved_path, saved_metadata_path):
                if written_path:
                    try:
                        os.unlink(written_path)
                    except OSError:
                        pass
            result["status"] = "error"
            result["reason"] = "state_persist_failed"
            result["message"] = (
                "run meta state persistence failed; the output was not "
                "marked saved"
            )
            return result

    return result


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

    from execution_runtime import resolve_execution_mode, MODE_V2
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

    # ── Merge actual_load defaults via shared builder ──────────────────
    _prod_ids = []
    if _effective_modal_options.get("production") and _effective_modal_options["production"].get("enabled"):
        _prod_ids = _effective_modal_options["production"].get("output_node_ids", [])
    _builder_opts = build_run_prompt_options(
        production_output_node_ids=_prod_ids,
        enable_actual_load=True,
    )
    _effective_modal_options = ensure_run_prompt_options(_effective_modal_options, _builder_opts)

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

    # ── Phase 8: choose invoker based on captured execution_mode ──
    _exec_mode_resolved = resolve_execution_mode(
        modal_options=modal_options,
        extra={"execution_mode": compilation.get("execution_mode")},
        modal_settings=None,
    )
    _effective_modal_options["execution_mode"] = _exec_mode_resolved["mode"]
    _effective_modal_options["execution_mode_source"] = _exec_mode_resolved["source"]
    compilation.setdefault("execution_mode", _exec_mode_resolved["mode"])
    compilation.setdefault("execution_mode_source", _exec_mode_resolved["source"])
    _use_v2 = _exec_mode_resolved["mode"] == MODE_V2

    if _use_v2:
        from comfymodal_runtime.v2_experiment_invoker import V2ExperimentInvoker
        invoker = V2ExperimentInvoker(
            experiment_id=exp_id,
            execution_mode=_exec_mode_resolved["mode"],
            execution_mode_source=_exec_mode_resolved["source"],
            modal_options=_effective_modal_options,
            gpu=gpu,
            workspace=workspace,
            stream_event_sink=_progress_sink,
        )
    else:
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
    certificate_candidates: list[dict] = []
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
                _cert_candidate = pl.get("_certificate_candidate")
                if isinstance(_cert_candidate, dict) and _cert_candidate.get("identity"):
                    certificate_candidates.append(copy.deepcopy(_cert_candidate))
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
    timings["_run_type"] = "scheduler"
    timing_sources["_run_type"] = "local_server_observed"

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

    # Prefer the cross-process wall-clock trace for the user-visible total.
    trace_e2e_ms = _derive_end_to_end_total_ms(
        local_timing_summary.get("stages", {})
    )
    if trace_e2e_ms is not None:
        timings["end_to_end_total_ms"] = trace_e2e_ms
        timing_sources["end_to_end_total_ms"] = "local_server_observed"

    # Uses module-level _CANONICAL_ALIAS_MAP (same as direct-run path)
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

    # ── Profile-preparer derived metrics (all five fields) ────────────
    # Numeric fields flow through merged_derived from LocalRemoteInvoker;
    # the string dedup_status sits on the top-level trace dict (not stages).
    for _pk, _pn in (
        ("active_profile_to_gpu_submit_ms", "local_server_observed"),
        ("active_profile_build_ms", "local_server_observed"),
        ("active_profile_remote_call", "local_server_observed"),
        ("active_profile_remote_ms", "local_server_observed"),
    ):
        _pv = merged_derived.get(_pk)
        if _pv is not None:
            timings[_pk] = _pv
            timing_sources[_pk] = _pn
    if timing_payload:
        _trace = timing_payload.get("trace", {}) or {}
        if isinstance(_trace, dict):
            _ds = _trace.get("active_profile_dedup_status")
            if _ds is not None and isinstance(_ds, str):
                timings["active_profile_dedup_status"] = _ds
                timing_sources["active_profile_dedup_status"] = "local_server_observed"

    # 4. Preserve compact raw trace structures (no base64)
    if timing_payload:
        for raw_key in ("trace", "wall_clock_trace", "_wall_clock_summary",
                         "_restore_timing", "scheduler_trace", "waterfall"):
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
    if timing_payload and isinstance(timing_payload.get("waterfall"), dict):
        meta_merge["waterfall"] = copy.deepcopy(timing_payload["waterfall"])

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

    # Validation certificates are persisted only after Studio output
    # materialization and run-history finalization have completed.
    if certificate_candidates:
        try:
            from modal_client import persist_validation_certificate
            from optimizations import _POST_DELIVERY_SINGLETON

            _scheduled_cert_ids: set[str] = set()
            for _cert_candidate in certificate_candidates:
                _cert_identity = str(_cert_candidate.get("identity", ""))
                if not _cert_identity or _cert_identity in _scheduled_cert_ids:
                    continue
                _scheduled_cert_ids.add(_cert_identity)

                def _persist_studio_certificate(candidate=_cert_candidate):
                    return persist_validation_certificate(
                        candidate,
                        workspace=workspace,
                        timeout_s=60.0,
                    )

                _POST_DELIVERY_SINGLETON.submit(
                    task_id=f"studio:{exp_id}:{_cert_identity}",
                    fn=_persist_studio_certificate,
                    timeout_s=60.0,
                )
                print(
                    f"[comfyui-modal.post_delivery] scheduled studio cert "
                    f"experiment_id={exp_id} identity={_cert_identity[:16]}"
                )
        except Exception as _post_cert_exc:
            # Certificate persistence is best-effort and must not change the
            # already-completed Studio result.
            print(
                f"[comfyui-modal.post_delivery] studio cert dispatcher error: "
                f"{_post_cert_exc!r}"
            )

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


# ── Shared preparation (scheduler and direct paths) ──────────────────────


def _prepare_studio_run_context(
    preset_id: str,
    feature_id: str,
    controls: dict[str, Any],
    node_dir: str | os.PathLike,
    trace_ctx: dict | None = None,
    *,
    modal_options: dict | None = None,
    workspace: dict | None = None,
) -> dict[str, Any]:
    """Shared sync preparation for both scheduler and direct-run paths.

    Uses ``import time`` locally for server-side timing markers.

    Loads preset + snapshot, validates, builds the single-run compilation
    (including production compilation), creates the submission-time history
    record (status submitted → running), and returns a context dict with
    everything both paths need.

    Returns ``{"status": "ok", "preset": …, "compilation": …,
    "run_history_id": …, "exp_id": …, "studio_meta": …,
    "profile_preparer": …}`` on success, or ``{"status": "error",
    "message": …}`` on failure.

    Does NOT create an experiment journal, scheduler, or runner.
    """
    import time as _time  # noqa: F401 — used for server-side timing markers
    node_dir = Path(node_dir)
    _log.info("Studio run context prep: preset_id=%s feature_id=%s", preset_id, feature_id)

    # 1. Load
    loaded_preset, loaded_snapshot = load_preset_and_snapshot(preset_id, node_dir)
    if loaded_preset is None:
        _log.warning("Studio run load failed: %s", loaded_snapshot)
        return {"status": "error", "message": loaded_snapshot}
    preset, snapshot = loaded_preset, loaded_snapshot
    _log.info("Studio run preset/snapshot loaded: preset=%s snapshot=%s",
              preset.get("id", ""), snapshot.get("id", ""))

    # 2. Validate
    validation = validate_studio_run(preset, snapshot, feature_id)
    if validation.get("error"):
        _log.warning("Studio run validation failed: %s", validation["error"])
        return {"status": "error", "message": validation["error"]}
    _log.info("Studio run validation passed")

    # 3. Seed studio_route_received BEFORE build_single_run_spec so it
    #    captures when the server started processing (before validate/compile).
    #    The trace_ctx dict was already seeded at route entry if the caller
    #    followed the convention, but set a deterministic fallback here.
    if trace_ctx is not None and "studio_route_received" not in trace_ctx:
        trace_ctx["studio_route_received"] = _time.time()

    # Build single-run compilation (includes validation + production)
    compilation = build_single_run_spec(
        preset, snapshot, feature_id, controls, node_dir,
        trace_ctx=trace_ctx, modal_options=modal_options,
    )
    if isinstance(compilation, dict) and compilation.get("error"):
        _log.warning("Studio run compilation failed: %s", compilation["error"])
        return {"status": "error", "message": compilation["error"]}

    # ── Seed mutable trace with server-side timing markers ──────────────
    # These markers live on the cell's trace dict so they flow into
    # LocalRemoteInvoker.run_cell as _mutable_trace and appear in the
    # merged timing_payload trace after execution.
    _cells = compilation.get("cells", [])
    if _cells:
        _cell_trace = _cells[0].setdefault("trace", {})
        # browser_run_click: alias from browser t0 using shared
        # coerce_t0_from_browser logic (same precedence as normal path).
        # Always set — server-side current time fallback when no browser
        # timestamp exists.
        _t0 = coerce_t0_from_browser(_cell_trace)
        _cell_trace["browser_run_click"] = _t0 if _t0 is not None else _time.time()
        # studio_route_received was set on trace_ctx before build_single_run_spec
        # and is now on _cell_trace already.  Fallback when no trace_ctx was given.
        if "studio_route_received" not in _cell_trace:
            _cell_trace["studio_route_received"] = _time.time()
        # production_compile_complete: captured right after build_single_run_spec
        if compilation.get("production_plan_used"):
            _cell_trace["production_compile_complete"] = _time.time()

    # 4. Create submission-time history record
    try:
        from experiment_service import REGISTRY
        from datetime import datetime, timezone

        exp_id = compilation["experiment_id"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        studio_meta = compilation.get("studio_meta", {})
        requested_controls = dict(controls or {})

        # Compute workflow_hash from the built workflow
        workflow_hash_at_submit = ""
        try:
            ck_list = compilation.get("checkpoints", [])
            if ck_list and isinstance(ck_list[0], dict):
                wf = ck_list[0].get("workflow", {})
                if wf:
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

        # History V2: persist the exact executable workflow at submission
        # time so a future Generate-Original can replay it without relying
        # on current mutable UI state.
        try:
            _ck_list = compilation.get("checkpoints", [])
            if _ck_list and isinstance(_ck_list[0], dict) and isinstance(_ck_list[0].get("workflow"), dict):
                meta_payload["workflow_json"] = copy.deepcopy(_ck_list[0]["workflow"])
        except Exception:
            pass

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

        # Update to "running" right before returning
        REGISTRY.history().update_run(run_history_id, status="running")

    except Exception:
        _log.exception("Studio run history creation failed")
        return {"status": "error", "message": _STABLE_INTERNAL_ERROR}

    # 5. Build profile-preparer closure
    _ws_captured = workspace

    async def _studio_profile_preparer(resolved_workflow, cell) -> dict:
        """Prepare active-next warmup profile using the fully resolved cell workflow.

        Returns the result dict from ``prepare_active_next_profile`` (which includes
        dedup status, timing fields, and remote-call indicators).  On exception,
        returns a non-fatal error result so the caller can still capture it.
        """
        try:
            from experiment_runner import _workflow_sha256
            from modal_client import set_active_warmup_profile as _remote_setter
            from modal_client import check_active_warmup_profile as _remote_checker
            _hash = _workflow_sha256(resolved_workflow) if isinstance(resolved_workflow, dict) else ""
            _cell_report = cell.get("production_report")
            _compilation_prod_opts = compilation.get("production_options") or {}
            _compilation_prod_report = compilation.get("production_report") or {}
            _active_prod_opts: dict | None = None
            _prod_report = _cell_report or _compilation_prod_report
            if _prod_report and _prod_report.get("enabled"):
                _active_prod_opts = dict(_compilation_prod_opts) if _compilation_prod_opts else {}
                _active_prod_opts.setdefault("enabled", True)
                if not _active_prod_opts.get("output_node_ids"):
                    _ids = _prod_report.get("output_node_ids") or _prod_report.get("kept_node_ids") or []
                    if _ids:
                        _active_prod_opts["output_node_ids"] = list(_ids)
                _active_prod_opts.setdefault("source_workflow_hash",
                    _prod_report.get("source_workflow_hash", ""))
                _active_prod_opts.setdefault("compiled_workflow_hash",
                    _prod_report.get("compiled_workflow_hash", ""))
                _active_prod_opts.setdefault("production_plan_hash",
                    _prod_report.get("production_plan_hash", ""))
                _active_prod_opts.setdefault("compiler_version",
                    _prod_report.get("compiler_version", 1))
                _active_prod_opts.setdefault("hash_schema_version",
                    _prod_report.get("hash_schema_version", HASH_SCHEMA_VERSION))
                _active_prod_opts.setdefault("production_plan_schema_version",
                    _prod_report.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION))
            result = await prepare_active_next_profile(
                resolved_workflow,
                _hash,
                production_options=_active_prod_opts,
                workspace=_ws_captured,
                setter=_remote_setter,
                checker=_remote_checker,
            )
            return result
        except Exception:
            _log.warning("Studio profile preparer failed (non-fatal)")
            return {
                "status": "error",
                "active_profile_dedup_status": "error",
                "profile_key": "",
                "remote_call": 0,
                "active_profile_remote_call": 0,
                "active_profile_remote_ms": 0.0,
                "changed": False,
            }

    return {
        "status": "ok",
        "preset": preset,
        "snapshot": snapshot,
        "controls": dict(controls),
        "feature_id": feature_id,
        "compilation": compilation,
        "run_history_id": run_history_id,
        "exp_id": exp_id,
        "studio_meta": studio_meta,
        "profile_preparer": _studio_profile_preparer,
    }


# ── Direct single-run completion helper ────────────────────────────────


async def direct_studio_run_completion(
    ctx: dict[str, Any],
    node_dir: str | os.PathLike,
    *,
    gpu: Any = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
) -> dict[str, Any]:
    """Execute a single Studio run via the canonical ``execute_modal_prompt``.

    Takes the context dict produced by ``_prepare_studio_run_context``
    (which must carry ``status="ok"``).  Calls the shared canonical executor
    directly — no ``LocalRemoteInvoker``, experiment scheduler, runner,
    leases, checkpoints collection, or experiment journal created.

    One deep copy of the compiled workflow is made, one control application
    (already done by ``build_single_run_spec``).  All production compile/
    hash/validation, profile preparation, and modal-args construction are
    delegated to the canonical executor.

    Returns a dict with ``status``, ``output_paths``, ``timings``,
    ``studio_meta``, and ``production_plan_used``.
    """
    from datetime import datetime, timezone
    import time as _time
    import uuid as _uuid

    if ctx.get("status") != "ok":
        return {"status": "error", "message": ctx.get("message", "Preparation failed")}

    node_dir = Path(node_dir)
    preset = ctx["preset"]
    compilation = ctx["compilation"]
    run_history_id = ctx["run_history_id"]
    exp_id = ctx["exp_id"]
    studio_meta = ctx["studio_meta"]

    # Extract the single cell from the compilation
    cells = compilation.get("cells", [])
    checkpoints = compilation.get("checkpoints", [])

    if not cells or not checkpoints:
        return {"status": "error", "message": "Compilation has no cells or checkpoints"}

    cell = cells[0]
    ck = checkpoints[0]

    # The workflow is already deep-copied and controls-applied by
    # build_single_run_spec.  Production compilation is delegated to the
    # canonical executor (execute_modal_prompt) so it occurs exactly once.
    workflow = ck.get("workflow", {})
    if not workflow:
        return {"status": "error", "message": "Compilation checkpoint has no workflow"}

    # Production options (resolved by build_single_run_spec) for the
    # canonical executor to compile.
    _prod_report = compilation.get("production_report")  # None for direct runs (compiled by canonical)
    _prod_opts = compilation.get("production_options")  # Resolved options with output_node_ids

    # Build the RunTrace for instrumentation
    _run_trace = RunTrace(
        run_surface="playground_direct",
    )
    _run_trace.begin("direct_studio_run_completion", reason="playground_single")
    # Record that LocalRemoteInvoker/scheduler/runner/lease/checkpoint
    # are NOT used (optional spans default to called=False).
    _run_trace.count("local_remote_invoker_used", 0)
    _run_trace.count("scheduler_used", 0)
    _run_trace.count("runner_used", 0)

    try:
        # ── Execute via canonical executor ─────────────────────────────
        # execute_modal_prompt handles compile (when production_options
        # is provided), validation, profile prep, run_prompt_options
        # construction, and the run_prompt_stream call.
        _trace_payload = cell.get("trace", {}).copy()
        _trace_payload.setdefault("workflow_hash", "")
        _trace_payload.update({
            "browser_run_click": cell.get("trace", {}).get("browser_run_click", _time.time()),
            "studio_route_received": cell.get("trace", {}).get("studio_route_received", _time.time()),
        })

        # Profile setter/checker for execute_modal_prompt (the canonical executor
        # handles production options enrichment internally)
        from modal_client import set_active_warmup_profile as _ws_setter
        from modal_client import check_active_warmup_profile as _ws_checker

        result = await execute_modal_prompt(
            workflow,
            prompt_id=exp_id,
            client_id="",
            input_images=None,
            modal_options=modal_options,
            production_report=_prod_report,
            production_options=_prod_opts,
            gpu=gpu,
            workspace=workspace,
            trace_payload=_trace_payload,
            profile_setter=_ws_setter,
            profile_checker=_ws_checker,
            run_trace=_run_trace,
        )

        # The direct path receives raw Modal output entries, including
        # base64-encoded image data. Materialize them locally before
        # publishing history/API paths; unlike the scheduler path, this
        # path does not pass through LocalRemoteInvoker's materializer.
        from local_artifacts import get_studio_outputs_dir
        from comfymodal_runtime.result_delivery import materialize_modal_result

        _studio_output_dir = get_studio_outputs_dir()
        _studio_output_dir.mkdir(parents=True, exist_ok=True)
        _materialized = materialize_modal_result(
            result,
            output_dir=str(_studio_output_dir),
            prompt_id=exp_id,
            require_output=True,
            expected_output_node_ids=tuple(
                str(value)
                for value in (
                    (_prod_opts or {}).get("output_node_ids", [])
                    if isinstance(_prod_opts, dict)
                    else ((_prod_report or {}).get("output_node_ids", [])
                          if isinstance(_prod_report, dict) else [])
                )
            ),
        )
        _materialized_paths = [
            Path(path).name for path in _materialized.get("written_files", [])
        ]
        if _materialized_paths:
            result["_local_materialized_output_paths"] = _materialized_paths
            result["_local_primary_output"] = _materialized.get("primary_output")

        if _run_trace is not None:
            _run_trace.begin("post_processing")

        # ── Build timings dict for history ─────────────────────────────
        _result_trace = result.get("trace", {}) if isinstance(result, dict) else {}
        _merged_stages: dict[str, float] = {}
        if isinstance(_result_trace, dict):
            _merged_stages = _result_trace.get("stages", {}) or {}
        _merged_deltas: dict = {}
        _merged_derived: dict = {}
        if isinstance(_result_trace, dict):
            _merged_deltas = _result_trace.get("deltas_ms", {}) or {}
            _merged_derived = _result_trace.get("derived_ms", {}) or {}

        timings: dict[str, Any] = {}
        timing_sources: dict[str, str] = {}
        timings["_run_type"] = "direct"
        timing_sources["_run_type"] = "local_server_observed"

        # Expose marker aliases at top-level timings
        _required_markers = [
            "browser_run_click", "studio_route_received",
            "production_compile_complete",
            "active_profile_write_start", "active_profile_write_end",
            "remote_submit", "first_remote_event",
            "result_received", "output_materialized",
            "active_profile_to_gpu_submit_ms",
        ]
        for _mk in _required_markers:
            _mv = _merged_stages.get(_mk)
            if _mv is not None:
                timings[_mk] = _mv
                timing_sources[_mk] = "local_server_observed"

        # active_profile_dedup_status from trace top level
        _dedup_status = _result_trace.get("active_profile_dedup_status")
        if _dedup_status is not None and isinstance(_dedup_status, str):
            timings["active_profile_dedup_status"] = _dedup_status
            timing_sources["active_profile_dedup_status"] = "local_server_observed"

        # End-to-end total
        _trace_e2e_ms = _derive_end_to_end_total_ms(_merged_stages)
        if _trace_e2e_ms is not None:
            timings["end_to_end_total_ms"] = _trace_e2e_ms
            timing_sources["end_to_end_total_ms"] = "local_server_observed"

        # Stage-based delta timings
        _stage_pairs = [
            ("studio_route_received", "production_compile_complete", "compile_ms"),
            ("active_profile_write_start", "active_profile_write_end", "profile_write_ms"),
            ("remote_submit", "result_received", "remote_execution_ms"),
            ("result_received", "output_materialized", "materialize_ms"),
        ]
        for _start_key, _end_key, _ms_key in _stage_pairs:
            _s = _merged_stages.get(_start_key)
            _e = _merged_stages.get(_end_key)
            if _s is not None and _e is not None:
                _delta = round((_e - _s) * 1000, 2)
                if _delta >= 0:
                    timings[_ms_key] = _delta
                    timing_sources[_ms_key] = "local_server_observed"

        # Preparser numeric fields from merged_derived
        for _pk in ("active_profile_build_ms", "active_profile_remote_call",
                     "active_profile_remote_ms"):
            _pv = _merged_derived.get(_pk)
            if _pv is not None:
                timings[_pk] = _pv
                timing_sources[_pk] = "local_server_observed"

        # Canonical alias map — same keys as scheduler path
        _remote_timings_blk: dict[str, Any] = {}
        for _canon_key, _raw_key, _source in _CANONICAL_ALIAS_MAP:
            _val = _merged_deltas.get(_raw_key)
            if _val is not None:
                timings[_canon_key] = _val
                timing_sources[_canon_key] = _source
                _remote_timings_blk[_raw_key] = _val

        # Restore timing from _restore_timing
        _restore_timing = result.get("_restore_timing", {}) if isinstance(result, dict) else {}
        _restore_total = _restore_timing.get("restore_total_ms")
        if _restore_total is not None:
            timings["restore_total_ms"] = _restore_total
            timing_sources["restore_total_ms"] = "remote_trace"
            timings["remote_restore_ms"] = _restore_total
            timing_sources["remote_restore_ms"] = "remote_trace"

        if _remote_timings_blk:
            timings["remote_timings"] = dict(_remote_timings_blk)
            timing_sources["remote_timings"] = "derived"

        # Preserve the V2 waterfall from the remote result
        _waterfall = result.get("waterfall", {}) if isinstance(result, dict) else {}
        if _waterfall and isinstance(_waterfall, dict):
            timings["waterfall"] = copy.deepcopy(_waterfall)
            timing_sources["waterfall"] = "remote_trace"

        # platform_pre_restore_ms
        _t2_submit = _merged_stages.get("t2_local_modal_submit_start") or _merged_stages.get("t2_local_dispatch")
        _restore_start = _restore_timing.get("restore_start_unix_s")
        if _t2_submit is not None and _restore_start is not None:
            _pre_restore_ms = round((_restore_start - _t2_submit) * 1000, 2)
            if _pre_restore_ms >= 0:
                timings["platform_pre_restore_ms"] = _pre_restore_ms
                timing_sources["platform_pre_restore_ms"] = "cross_process_inferred"

        timings["trace_available"] = bool(result)
        if timing_sources:
            timings["timing_sources"] = timing_sources

        # ── Build meta for history ────────────────────────────────────
        # Determine production_plan_used from run_trace counts
        _rt_summary = _run_trace.emit_remote_summary() if _run_trace else {}
        _rt_counts = _rt_summary.get("counts", {}) if isinstance(_rt_summary, dict) else {}
        _prod_called = _rt_counts.get("production_compile_count", 0) > 0

        meta_merge: dict = {
            "requested_controls": dict(studio_meta.get("studio_controls", {})),
            "studio_preset_id": studio_meta.get("studio_preset_id", ""),
            "studio_snapshot_id": studio_meta.get("studio_snapshot_id", ""),
            "studio_feature_id": studio_meta.get("studio_feature_id", ""),
            "experiment_id": exp_id,
            "preset_label": studio_meta.get("studio_preset_label", ""),
            "production_plan_used": "yes" if _prod_called else "no",
        }

        # Resolved controls from post-application workflow
        try:
            wf = ck.get("workflow", {})
            slots = ck.get("slots", {})
            resolved_controls = _build_resolved_controls(wf, slots)
            _resolved_sanitised = _sanitize_resolved_controls(resolved_controls or {})
            meta_merge["resolved_controls"] = dict(_resolved_sanitised)
            canonical_aliases = _flatten_canonical_aliases(_resolved_sanitised)
            for k, v in canonical_aliases.items():
                if v is not None and k not in meta_merge:
                    meta_merge[k] = v
        except Exception:
            pass

        # Output paths — extract from result
        output_paths: list[str] = []
        if isinstance(result, dict):
            _primary = result.get("primary_output") or result.get("_local_primary_output")
            _materialized_paths = result.get("_local_materialized_output_paths")
            if isinstance(_materialized_paths, list):
                output_paths = [
                    Path(path).name for path in _materialized_paths
                    if isinstance(path, str) and path
                ]
            if not output_paths and isinstance(_primary, dict) and _primary.get("path"):
                output_paths = [Path(_primary["path"]).name]
            if not output_paths and result.get("outputs"):
                for _nid, _nouts in result["outputs"].items():
                    if isinstance(_nouts, dict):
                        for _entries in _nouts.values():
                            if isinstance(_entries, list):
                                for _e in _entries:
                                    if isinstance(_e, dict) and _e.get("filename"):
                                        output_paths.append(_e["filename"])

        if output_paths:
            meta_merge["output_paths"] = list(output_paths)
        meta_merge["output_count"] = len(output_paths)
        if _waterfall and isinstance(_waterfall, dict):
            meta_merge["waterfall"] = copy.deepcopy(_waterfall)

        # ── Finalize history ──────────────────────────────────────────
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            from experiment_service import REGISTRY

            update_kwargs: dict = {
                "status": "completed",
                "completed_at": completed_at,
                "timings": timings,
                "meta": meta_merge,
            }
            if output_paths:
                update_kwargs["output_path"] = output_paths[0]
            REGISTRY.history().update_run(run_history_id, **update_kwargs)
        except Exception:
            _log.warning("Failed to finalize run history for %s", exp_id)

        # ── Certificate persistence (post-delivery) ──────────────────
        if isinstance(result, dict):
            _cert_candidate = result.get("_certificate_candidate")
            if isinstance(_cert_candidate, dict) and _cert_candidate.get("identity"):
                try:
                    from modal_client import persist_validation_certificate
                    from optimizations import _POST_DELIVERY_SINGLETON

                    def _persist_studio_certificate(candidate=_cert_candidate):
                        return persist_validation_certificate(
                            candidate,
                            workspace=workspace,
                            timeout_s=60.0,
                        )

                    _POST_DELIVERY_SINGLETON.submit(
                        task_id=f"studio:{exp_id}:{_cert_candidate['identity'][:16]}",
                        fn=_persist_studio_certificate,
                        timeout_s=60.0,
                    )
                except Exception:
                    pass

        if _run_trace is not None:
            _run_trace.end("post_processing")

        return {
            "status": "ok",
            "runId": run_history_id,
            "experimentId": exp_id,
            "runHistoryId": run_history_id,
            "completed_at": completed_at,
            "output_paths": output_paths,
            "output_path": output_paths[0] if output_paths else "",
            "timings": timings,
            "meta": meta_merge,
            "studio_meta": studio_meta,
            "production_plan_used": _prod_called,
            "direct_run": True,
        }

    except Exception as exc:
        _log.error("Studio direct run failed for %s", exp_id, exc_info=True)
        try:
            from experiment_service import REGISTRY
            from datetime import datetime, timezone
            fail_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            REGISTRY.history().update_run(
                run_history_id,
                status="error",
                completed_at=fail_ts,
                meta={
                    "error": _STABLE_INTERNAL_ERROR,
                    "error_code": _STUDIO_EXECUTION_ERROR_CODE,
                    "_error_detail": str(exc)[:500],
                },
            )
        except Exception:
            pass
        return _execution_error_response(exc, operation="direct_studio_run", run_id=exp_id)
    finally:
        if _run_trace is not None:
            _run_trace.end("direct_studio_run_completion")


# ── Scheduler path (legacy, extracted from original handle_studio_run) ──


def _handle_studio_run_scheduler(
    ctx: dict[str, Any],
    node_dir: str | os.PathLike,
    *,
    gpu: Any = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
) -> dict[str, Any]:
    """Legacy scheduler path for single runs.

    Takes the context from ``_prepare_studio_run_context``, creates an
    experiment via REGISTRY, and fires the scheduler in the background.
    Returns the submission response immediately.

    Behavior and scheduler path unchanged from the original
    ``handle_studio_run`` — only the shared preparation logic has been
    extracted.
    """
    if ctx.get("status") != "ok":
        return {"status": "error", "message": ctx.get("message", "Preparation failed")}

    node_dir = Path(node_dir)
    compilation = ctx["compilation"]
    run_history_id = ctx["run_history_id"]
    exp_id = ctx["exp_id"]
    studio_meta = ctx["studio_meta"]
    preset = ctx["preset"]
    preset_id = preset.get("id", "")
    feature_id = studio_meta.get("studio_feature_id", "")
    profile_preparer = ctx["profile_preparer"]

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        from experiment_service import REGISTRY

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
                                     pp=profile_preparer, g=gpu, mo=modal_options, ws=workspace),
                    exp_id,
                )
            else:
                asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir,
                                             pp=profile_preparer, g=gpu, mo=modal_options, ws=workspace))
        except RuntimeError:
            asyncio.run(_start_and_catch(exp_id, compilation, REGISTRY, node_dir,
                                         pp=profile_preparer, g=gpu, mo=modal_options, ws=workspace))
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
        _log.exception("Studio run scheduler failed for experiment %s", exp_id)
        return {"status": "error", "message": _STABLE_INTERNAL_ERROR}


async def handle_studio_run_async(
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
    direct: bool = True,
) -> dict[str, Any]:
    # T1: local endpoint received — first executable line before any work
    import time as _handle_time
    _t1_wall_ns = int(_handle_time.time() * 1_000_000_000)
    _t1_mono_ns = _handle_time.monotonic_ns()
    # Extract request origin from incoming payload
    _request_origin_info = dict(trace_ctx.get("request_origin", {})) if isinstance(trace_ctx, dict) else {}
    if not _request_origin_info.get("request_id"):
        # Fallback: generate a local request ID when no UI origin provided
        _request_origin_info["request_id"] = str(uuid.uuid4())
        _request_origin_info["trigger_source"] = "local_adapter"
    _request_origin_info["local_receive_wall_ns"] = _t1_wall_ns
    _request_origin_info["local_receive_mono_ns"] = _t1_mono_ns
    # Propagate origin info into the trace_ctx that flows downstream
    if isinstance(trace_ctx, dict):
        trace_ctx["request_origin_info"] = _request_origin_info

    """Async handler for a single Studio run.

    When ``direct=True`` (default), dispatches immediately to the
    PlaygroundService adapter **before** shared-context preparation,
    avoiding duplicate preset loading, compilation, and history creation.

    When ``direct=False``, uses the shared ``_prepare_studio_run_context``
    + experiment scheduler path (legacy scheduler/runner flow).

    Returns a completed result dict on success in direct mode, or a
    submission response dict in scheduler (legacy) mode.
    """
    from execution_runtime import resolve_execution_mode, MODE_V2
    # Phase 8: capture the engine once at submission time.  The captured
    # request option is forwarded through every downstream path.
    _req_settings = {}
    try:
        from __init__ import _load_modal_settings as _ls
        _req_settings = _ls()
    except Exception:
        pass
    resolved = resolve_execution_mode(
        modal_options=modal_options,
        modal_settings=_req_settings,
    )
    mode = resolved["mode"]
    _effective_modal_options = dict(modal_options or {})
    _effective_modal_options["execution_mode"] = mode

    # Forward captured execution_mode through trace_ctx for history/metadata
    if isinstance(trace_ctx, dict):
        trace_ctx["execution_mode"] = mode
        trace_ctx["execution_mode_source"] = resolved["source"]

    if direct and mode == MODE_V2:
        return await playground_adapter_direct_run(
            preset_id, feature_id, controls, node_dir,
            modal_options=_effective_modal_options, gpu=gpu,
            workspace=workspace, trace_ctx=trace_ctx,
        )
    if direct:
        # Legacy is the safe default. Shadow builds and compares the v2 plan,
        # then executes exactly one legacy generation.
        ctx = _prepare_studio_run_context(
            preset_id, feature_id, controls, node_dir,
            trace_ctx=trace_ctx, modal_options=_effective_modal_options, workspace=workspace,
        )
        if ctx.get("status") != "ok":
            return ctx
        if mode == "shadow":
            _record_shadow_plan_comparison(ctx, feature_id, controls, modal_options)
        result = await direct_studio_run_completion(
            ctx,
            node_dir,
            gpu=gpu,
            modal_options=_effective_modal_options,
            workspace=workspace,
        )
        if mode == "shadow":
            result["shadow_plan_comparison"] = ctx.get("shadow_plan_comparison", {})
        return result

    # ── Scheduler (legacy) path — shared context then scheduler ──
    ctx = _prepare_studio_run_context(
        preset_id, feature_id, controls, node_dir,
        trace_ctx=trace_ctx, modal_options=_effective_modal_options, workspace=workspace,
    )
    if ctx.get("status") != "ok":
        return ctx

    return _handle_studio_run_scheduler(
        ctx, node_dir,
        gpu=gpu, modal_options=_effective_modal_options, workspace=workspace,
    )


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
    direct: bool = True,
) -> dict[str, Any]:
    """Sync wrapper for ``handle_studio_run_async``.

    Runs the async handler in a new event loop (thread) when called from
    a context with a running loop.  Falls back to ``asyncio.run()`` when
    no loop is running.

    Prefer calling ``handle_studio_run_async`` directly from async route
    handlers to avoid the thread overhead.
    """
    import asyncio

    async def _run():
        return await handle_studio_run_async(
            preset_id, feature_id, controls, node_dir,
            trace_ctx=trace_ctx,
            profile_preparer=profile_preparer,
            gpu=gpu, modal_options=modal_options,
            workspace=workspace, direct=direct,
        )

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import threading
        _result_holder: list[dict] = []

        def _run_in_thread():
            _inner_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_inner_loop)
            try:
                r = _inner_loop.run_until_complete(_run())
                _result_holder.append(r)
            finally:
                _inner_loop.close()

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        t.join(timeout=600)
        if not _result_holder:
            return _execution_error_response(
                TimeoutError("Studio run worker exceeded the 600 second limit"),
                operation="studio_run_timeout",
                run_id=preset_id,
            )
        return _result_holder[0]

    try:
        return asyncio.run(_run())
    except Exception as exc:
        return _execution_error_response(exc, operation="studio_run", run_id=preset_id)


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

        # History V2: create the durable experiment with fixed-position cells.
        try:
            from history_v2_writer import get_writer as _get_v2_writer
            _v2_writer = _get_v2_writer()
            if _v2_writer is not None:
                _v2_cells = []
                for _i, _cell in enumerate(compilation.get("cells", []) or []):
                    if not isinstance(_cell, dict):
                        continue
                    _v2_cells.append({
                        "cell_key": str(_cell.get("cell_key", "")),
                        "sequence": _cell.get("sequence", _i),
                        "axis_values": dict(_cell.get("axis_values") or {}),
                    })
                _studio_meta = compilation.get("studio_meta", {}) or {}
                _v2_writer.ensure_experiment(
                    exp_id,
                    name=str(experiment_def.get("name", "") or ""),
                    definition={
                        "production": True,
                        "studio": True,
                        "workflow": str(_studio_meta.get("studio_preset_id", "") or ""),
                        "preset": str(_studio_meta.get("studio_preset_label", "") or ""),
                        "feature": str(_studio_meta.get("studio_feature_id", "") or ""),
                    },
                    cells=_v2_cells,
                )
        except Exception:
            _log.warning("History V2 experiment ensure failed for %s", exp_id)

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
