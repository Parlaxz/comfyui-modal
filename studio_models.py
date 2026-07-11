"""Data models, validation, and feature-status derivation for Studio snapshots and presets.

Exports
-------
* ``_KNOWN_FEATURE_IDS`` — set of recognised compatible-feature identifiers.
* ``_normalize_label`` / ``_sanitize_description`` / ``_validate_feature_ids``
* ``_validate_feature_ids_strict`` — rejects unknown feature IDs.
* ``normalize_snapshot_payload`` — enrich a snapshot dict with ``status``,
  ``featureStatus``, and ``disabledReason``.
* ``normalize_preset_payload`` — enrich a preset dict with derived ``status``
  and ``disabledReason``.
* ``make_snapshot`` — create a fully-normalised snapshot from an API body.
* ``update_snapshot`` — apply field updates to an existing snapshot.
* ``make_preset`` — create a fully-normalised preset from an API body.
* ``update_preset`` — apply field updates to an existing preset.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# ── Known feature IDs ────────────────────────────────────────────────────

_KNOWN_FEATURE_IDS: set[str] = {"txt2img", "object_remove", "object_replace"}

# Feature-specific requirements for runnability.
# Each entry lists node-bindings keys that MUST be present and truthy.
_FEATURE_BINDING_KEYS: dict[str, list[str]] = {
    "txt2img": ["prompt"],
    "object_remove": ["source_image", "mask", "instruction"],
    "object_replace": ["source_image", "mask", "replacement_prompt"],
}

# Structured binding keys — each binding value is expected to be a dict
# with a "kind" field ("node", "widget", "input", "output") rather than
# a legacy scalar string.  The presence check below treats a truthy dict
# with a valid "kind" the same as truthy.
_WIZARD_BINDING_KINDS: set[str] = {"node", "widget", "input", "output"}

# Status sort-order (lower index = more restrictive / higher priority).
_STATUS_PRIORITY: list[str] = [
    "archived",
    "invalid",
    "needs_bindings",
    "needs_api_prompt",
    "metadata_only",
    "import_only",
    "runnable",
]

# Source types that require a snapshot link.
_SOURCE_TYPES_REQUIRING_SNAPSHOT: set[str] = {"manual", "snapshot"}

# ── Helpers ──────────────────────────────────────────────────────────────


def _normalize_label(s: str) -> str:
    """Strip whitespace and truncate to 200 characters."""
    return (s or "").strip()[:200]


def _sanitize_description(s: str) -> str:
    """Strip whitespace and truncate to 2000 characters."""
    return (s or "").strip()[:2000]


def _validate_feature_ids(features: Any) -> list[str]:
    """Return only the recognised feature IDs from *features*.

    Silently drops unknown or malformed entries.
    """
    if not isinstance(features, list):
        return []
    return [f for f in features if isinstance(f, str) and f in _KNOWN_FEATURE_IDS]


def _validate_feature_ids_strict(features: Any) -> list[str]:
    """Return recognised feature IDs from *features*.

    Raises ``ValueError`` if any entry is unknown or *features* is not a list.
    """
    if not isinstance(features, list):
        raise ValueError("Invalid compatible feature")
    unknown = [
        f
        for f in features
        if not (isinstance(f, str) and f in _KNOWN_FEATURE_IDS)
    ]
    if unknown:
        raise ValueError("Invalid compatible feature")
    return features


def _extract_executable_prompt(api_prompt_json: Any) -> dict[str, Any]:
    if not isinstance(api_prompt_json, dict):
        return {}
    output = api_prompt_json.get("output")
    workflow = api_prompt_json.get("workflow")
    if isinstance(output, dict) and isinstance(workflow, dict):
        return output
    return api_prompt_json


# ── Feature-status derivation ────────────────────────────────────────────


def _derive_feature_status(
    feature_id: str,
    node_bindings: dict[str, Any],
    output_node_id: str | None,
    api_prompt_json: Any,
) -> dict[str, str]:
    """Return a ``{"status": …, "reason": …}`` dict for one feature.

    All runnable features require ``outputNodeId`` and ``apiPromptJson``.
    In addition, ``txt2img`` requires prompt binding, and
    ``object_remove`` / ``object_replace`` require their image/mask bindings.

    Priority (most restrictive wins):
        needs_bindings > needs_api_prompt > runnable
    """
    bindings = node_bindings if isinstance(node_bindings, dict) else {}
    required_keys = _FEATURE_BINDING_KEYS.get(feature_id, [])

    def _binding_truthy(val: object) -> bool:
        """Check truthiness of a binding value.

        Supports both legacy scalar strings and wizard-style structured
        binding dicts (``{"kind": "node", ...}``).
        """
        if isinstance(val, dict):
            return bool(val.get("kind")) and bool(val.get("nodeId"))
        return bool(val)

    has_bindings = all(_binding_truthy(bindings.get(k)) for k in required_keys)
    has_output_node = bool(output_node_id)
    has_api_prompt = bool(api_prompt_json)

    if not has_bindings or not has_output_node:
        return {"status": "needs_bindings", "reason": "missing required node bindings"}
    if not has_api_prompt:
        return {"status": "needs_api_prompt", "reason": "missing API prompt configuration"}

    # Validate that every binding nodeId exists as a key in the executable prompt
    executable_prompt = _extract_executable_prompt(api_prompt_json)
    if executable_prompt:
        for key in required_keys:
            binding = bindings.get(key, {})
            if isinstance(binding, dict):
                node_id = str(binding.get("nodeId", ""))
                if node_id and node_id not in executable_prompt:
                    return {
                        "status": "needs_bindings",
                        "reason": (
                            f"binding '{key}' maps to node {node_id} "
                            f"which does not exist in the workflow"
                        ),
                    }

    return {"status": "runnable", "reason": ""}


def _aggregate_status(feature_statuses: dict[str, dict[str, str]]) -> str:
    """Return the most restrictive status across all feature entries.

    The status list is ordered most-restrictive-first in ``_STATUS_PRIORITY``.
    """
    for candidate in _STATUS_PRIORITY:
        for fs in feature_statuses.values():
            if fs.get("status") == candidate:
                return candidate
    return "runnable"


# ── Snapshot normalisation ───────────────────────────────────────────────


def _derive_snapshot_disabled_reason(
    status: str, feature_statuses: dict[str, dict[str, str]]
) -> str:
    """Derive a human-readable ``disabledReason`` for a snapshot."""
    if status == "invalid":
        return "No compatible features configured"
    if status == "needs_bindings":
        return "Missing required node bindings"
    if status == "needs_api_prompt":
        return "Missing API prompt configuration"
    return ""


def normalize_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *payload* enriched with ``status``, ``featureStatus``,
    and ``disabledReason``.

    The input dict is expected to contain (at least):
        compatibleFeatures, graphJson, apiPromptJson, nodeBindings, outputNodeId

    The enrichment adds:
        featureStatus — ``{feature_id: {"status": …, "reason": …}}`` per feature
        status        — aggregate across all features using the priority rules
        disabledReason — derived from the aggregate status
    """
    result = dict(payload)
    features = _validate_feature_ids(result.get("compatibleFeatures", []))
    if not features:
        # No recognised features → invalid
        result["featureStatus"] = {}
        result["status"] = "invalid"
        result["disabledReason"] = "No compatible features configured"
        return result

    node_bindings = result.get("nodeBindings", {}) or {}
    output_node_id = result.get("outputNodeId") or ""
    api_prompt_json = _extract_executable_prompt(result.get("apiPromptJson") or {})

    feature_statuses: dict[str, dict[str, str]] = {}
    for fid in features:
        feature_statuses[fid] = _derive_feature_status(
            fid, node_bindings, output_node_id, api_prompt_json,
        )

    result["featureStatus"] = feature_statuses
    result["status"] = _aggregate_status(feature_statuses)
    result["disabledReason"] = _derive_snapshot_disabled_reason(
        result["status"], feature_statuses
    )

    # Archive overrides everything
    if result.get("archived"):
        result["status"] = "archived"

    return result


# ── Preset normalisation ─────────────────────────────────────────────────


def _derive_preset_disabled_reason(
    status: str,
    snapshot_id: str,
    snapshot_status: str | None,
) -> str:
    """Derive a human-readable ``disabledReason`` for a preset."""
    if status == "invalid":
        if snapshot_id and snapshot_status is None:
            return "Preset references a missing snapshot"
        return "Preset does not reference a snapshot"
    if status == "import_only":
        return "Import preset without snapshot linkage"
    if status == "metadata_only":
        return "Legacy preset without snapshot linkage"
    if snapshot_status and snapshot_status != "runnable":
        return f"Referenced snapshot is {snapshot_status}"
    return ""


def normalize_preset_payload(
    payload: dict[str, Any],
    snapshots_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return a copy of *payload* with normalised fields and derived ``status``
    and ``disabledReason``.

    * If ``snapshotId`` is present and the snapshot is missing from
      ``snapshots_by_id``, status becomes ``"invalid"`` and
      ``disabledReason`` is set to ``"Preset references a missing snapshot"``.
    * If the referenced snapshot is found, the preset inherits the snapshot's
      aggregate ``status`` (runnable only when the snapshot is runnable).
    * If ``snapshotId`` is empty and ``sourceType`` is ``"import"``, status
      becomes ``"import_only"``. For ``"legacy"`` it becomes ``"metadata_only"``.
      For other source types, status becomes ``"invalid"``.
    """
    result = dict(payload)

    # Required fields
    result.setdefault("label", result.get("name", "Untitled Preset"))
    result.setdefault("description", "")
    result.setdefault("snapshotId", "")
    result.setdefault("compatibleFeatures", [])
    result.setdefault("defaults", {})
    result.setdefault("sourceType", "manual")
    result.setdefault("sourceId", "")
    result.setdefault("archived", False)

    # Derive status from the referenced snapshot
    snapshot_id = result.get("snapshotId", "") or ""
    if snapshot_id:
        snapshot = snapshots_by_id.get(snapshot_id)
        if snapshot is None:
            result["status"] = "invalid"
            result["disabledReason"] = _derive_preset_disabled_reason(
                "invalid", snapshot_id, None
            )
            return result
        # Inherit snapshot status (preset is runnable only when snapshot is)
        snap_status = snapshot.get("status", "runnable")
        result["status"] = snap_status
        result["disabledReason"] = _derive_preset_disabled_reason(
            snap_status, snapshot_id, snap_status
        )
    else:
        # No snapshot reference — check source type semantics
        source_type = result.get("sourceType", "manual")
        if source_type == "import":
            result["status"] = "import_only"
            result["disabledReason"] = _derive_preset_disabled_reason(
                "import_only", "", None
            )
        elif source_type == "legacy":
            result["status"] = "metadata_only"
            result["disabledReason"] = _derive_preset_disabled_reason(
                "metadata_only", "", None
            )
        else:
            result["status"] = "invalid"
            result["disabledReason"] = _derive_preset_disabled_reason(
                "invalid", "", None
            )

    if result.get("archived"):
        result["status"] = "archived"

    return result


# ── Canonical helpers for route use ──────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_snapshot_id() -> str:
    return f"snap_{uuid.uuid4().hex[:16]}"


def _make_preset_id() -> str:
    return f"preset_{uuid.uuid4().hex[:16]}"


def make_snapshot(body: dict[str, Any]) -> dict[str, Any]:
    """Create a fully-normalised snapshot dict from a raw API body.

    Returns a complete snapshot dictionary with generated ``id``,
    normalised fields, derived ``status``, ``featureStatus``, and
    ``disabledReason``.  Client-provided ``disabledReason`` is ignored —
    it is always derived server-side.

    Raises ``ValueError`` if ``compatibleFeatures`` contains unknown IDs.
    """
    features = _validate_feature_ids_strict(body.get("compatibleFeatures", []))
    now = _now_iso()
    entry: dict[str, Any] = {
        "id": _make_snapshot_id(),
        "name": _normalize_label(body.get("name", "Untitled Snapshot")),
        "description": _sanitize_description(body.get("description", "")),
        "createdAt": now,
        "updatedAt": now,
        "compatibleFeatures": features,
        "graphJson": body.get("graphJson"),
        "apiPromptJson": body.get("apiPromptJson"),
        "nodeBindings": body.get("nodeBindings", {}),
        "outputNodeId": body.get("outputNodeId", ""),
        "modelSummary": body.get("modelSummary", ""),
        "source": _normalize_label(body.get("source", "manual")),
        "archived": False,
    }
    enriched = normalize_snapshot_payload(entry)
    entry["status"] = enriched["status"]
    entry["featureStatus"] = enriched["featureStatus"]
    entry["disabledReason"] = enriched.get("disabledReason", "")
    return entry


def update_snapshot(
    snapshot: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    """Apply field updates to an existing snapshot and re-derive status.

    Mutates *snapshot* in place and returns it.  Fields not present in
    *body* are left unchanged.  Client-provided ``disabledReason`` is
    ignored — it is always derived server-side.

    Raises ``ValueError`` if ``compatibleFeatures`` contains unknown IDs.
    """
    if "name" in body and isinstance(body["name"], str):
        snapshot["name"] = _normalize_label(body["name"])
    if "description" in body and isinstance(body["description"], str):
        snapshot["description"] = _sanitize_description(body["description"])
    if "compatibleFeatures" in body:
        snapshot["compatibleFeatures"] = _validate_feature_ids_strict(
            body["compatibleFeatures"]
        )
    if "graphJson" in body:
        snapshot["graphJson"] = body["graphJson"]
    if "apiPromptJson" in body:
        snapshot["apiPromptJson"] = body["apiPromptJson"]
    if "nodeBindings" in body and isinstance(body["nodeBindings"], dict):
        snapshot["nodeBindings"] = body["nodeBindings"]
    if "outputNodeId" in body and isinstance(body["outputNodeId"], str):
        snapshot["outputNodeId"] = body["outputNodeId"]
    if "modelSummary" in body and isinstance(body["modelSummary"], str):
        snapshot["modelSummary"] = body["modelSummary"].strip()
    if "archived" in body:
        snapshot["archived"] = bool(body["archived"])

    snapshot["updatedAt"] = _now_iso()
    enriched = normalize_snapshot_payload(snapshot)
    snapshot["status"] = enriched["status"]
    snapshot["featureStatus"] = enriched["featureStatus"]
    snapshot["disabledReason"] = enriched.get("disabledReason", "")
    return snapshot


def make_preset(
    body: dict[str, Any],
    snapshots_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Create a fully-normalised preset dict from a raw API body.

    Returns a complete preset dictionary with generated ``id``,
    normalised fields, and derived ``status`` and ``disabledReason``.
    Client-provided ``disabledReason`` is ignored — it is always derived
    server-side.

    Raises ``ValueError`` if ``compatibleFeatures`` contains unknown IDs.
    """
    features = _validate_feature_ids_strict(body.get("compatibleFeatures", []))
    now = _now_iso()
    entry: dict[str, Any] = {
        "id": _make_preset_id(),
        "label": _normalize_label(
            body.get("label", body.get("name", "Untitled Preset"))
        ),
        "description": _sanitize_description(body.get("description", "")),
        "snapshotId": body.get("snapshotId", ""),
        "compatibleFeatures": features,
        "defaults": body.get("defaults", {}),
        "sourceType": body.get("sourceType", "manual"),
        "sourceId": body.get("sourceId", ""),
        "archived": False,
        "createdAt": now,
        "updatedAt": now,
    }
    normalized = normalize_preset_payload(entry, snapshots_by_id)
    entry["status"] = normalized["status"]
    entry["disabledReason"] = normalized.get("disabledReason", "")
    return entry


def update_preset(
    preset: dict[str, Any],
    body: dict[str, Any],
    snapshots_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Apply field updates to an existing preset and re-derive status.

    Mutates *preset* in place and returns it.  Fields not present in
    *body* are left unchanged.  Client-provided ``disabledReason`` is
    ignored — it is always derived server-side.

    Raises ``ValueError`` if ``compatibleFeatures`` contains unknown IDs.
    """
    if "label" in body and isinstance(body["label"], str):
        preset["label"] = _normalize_label(body["label"])
    if "description" in body and isinstance(body["description"], str):
        preset["description"] = _sanitize_description(body["description"])
    if "snapshotId" in body and isinstance(body["snapshotId"], str):
        preset["snapshotId"] = body["snapshotId"]
    if "compatibleFeatures" in body:
        preset["compatibleFeatures"] = _validate_feature_ids_strict(
            body["compatibleFeatures"]
        )
    if "defaults" in body and isinstance(body["defaults"], dict):
        preset["defaults"] = body["defaults"]
    if "sourceType" in body and isinstance(body["sourceType"], str):
        preset["sourceType"] = body["sourceType"]
    if "sourceId" in body and isinstance(body["sourceId"], str):
        preset["sourceId"] = body["sourceId"]
    if "archived" in body:
        preset["archived"] = bool(body["archived"])

    preset["updatedAt"] = _now_iso()
    normalized = normalize_preset_payload(preset, snapshots_by_id)
    preset["status"] = normalized["status"]
    preset["disabledReason"] = normalized.get("disabledReason", "")
    return preset


# ── Control validation ────────────────────────────────────────────────────


def validate_controls_against_schema(
    controls: dict[str, Any],
    schemas: dict[str, dict],
    feature_id: str,
    strict_unknown_rejection: bool = False,
) -> list[dict[str, str]]:
    """Validate submitted control values against control schemas.

    Parameters
    ----------
    controls : dict
        The submitted control values (control_id → value).
    schemas : dict
        Control schemas keyed by control_id, derived from the snapshot graph.
    feature_id : str
        Feature identifier for context (currently unused, reserved).
    strict_unknown_rejection : bool, optional
        If True, control fields that do not appear in *schemas* are rejected
        as unknown.  Default False preserves backward compatibility for
        legacy/extra fields.

    Returns a list of error dicts (``{"field": …, "message": …}``).
    An empty list means all controls are valid.
    """
    errors: list[dict[str, str]] = []

    for field, value in controls.items():
        schema = schemas.get(field)
        if schema is None:
            if strict_unknown_rejection:
                errors.append({
                    "field": field,
                    "message": f"Unknown control field {field!r} not in control schemas",
                })
            continue  # unknown field, skip validation unless strict mode

        kind = schema.get("kind", "unknown")
        resolved = schema.get("schemaResolved", False)

        if not resolved or kind == "unresolved":
            continue  # can't validate unresolved schemas

        if kind == "enum":
            options = schema.get("options", [])
            if value is None:
                errors.append({
                    "field": field,
                    "message": f"Value for {field!r} must not be null. "
                              f"Must be one of: {', '.join(str(o) for o in options)}",
                })
            elif value not in options:
                errors.append({
                    "field": field,
                    "message": f"Invalid value {value!r} for {field!r}. "
                              f"Must be one of: {', '.join(str(o) for o in options)}",
                })

        elif kind == "integer":
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append({
                    "field": field,
                    "message": f"Value for {field!r} must be an integer, got {type(value).__name__}",
                })
                continue
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append({
                    "field": field,
                    "message": f"Value for {field!r} must be >= {minimum}, got {value}",
                })
            if maximum is not None and value > maximum:
                errors.append({
                    "field": field,
                    "message": f"Value for {field!r} must be <= {maximum}, got {value}",
                })

        elif kind == "number":
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append({
                    "field": field,
                    "message": f"Value for {field!r} must be a number, got {type(value).__name__}",
                })
                continue
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append({
                    "field": field,
                    "message": f"Value for {field!r} must be >= {minimum}, got {value}",
                })
            if maximum is not None and value > maximum:
                errors.append({
                    "field": field,
                    "message": f"Value for {field!r} must be <= {maximum}, got {value}",
                })

        elif kind == "boolean":
            if value is not None and not isinstance(value, bool):
                # Accept 0/1 for backward compatibility
                if value not in (0, 1):
                    errors.append({
                        "field": field,
                        "message": f"Value for {field!r} must be a boolean, got {type(value).__name__}",
                    })

    return errors
