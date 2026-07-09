"""Data models, validation, and feature-status derivation for Studio snapshots and presets.

Exports
-------
* ``_KNOWN_FEATURE_IDS`` — set of recognised compatible-feature identifiers.
* ``_normalize_label`` / ``_sanitize_description`` / ``_validate_feature_ids``
* ``normalize_snapshot_payload`` — enrich a snapshot dict with ``status`` and
  ``featureStatus``.
* ``normalize_preset_payload`` — enrich a preset dict with derived ``status``.
"""

from __future__ import annotations

from typing import Any

# ── Known feature IDs ────────────────────────────────────────────────────

_KNOWN_FEATURE_IDS: set[str] = {"txt2img", "object_remove", "object_replace"}

# Feature-specific requirements for runnability.
# Each entry lists node-bindings keys that MUST be present and truthy.
_FEATURE_BINDING_KEYS: dict[str, list[str]] = {
    "txt2img": ["prompt"],
    "object_remove": ["object_remove_image", "object_remove_mask"],
    "object_replace": ["object_replace_image", "object_replace_mask"],
}

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


# ── Feature-status derivation ────────────────────────────────────────────


def _derive_feature_status(
    feature_id: str,
    node_bindings: dict[str, Any],
    output_node_id: str | None,
    api_prompt_json: Any,
) -> dict[str, str]:
    """Return a ``{"status": …, "reason": …}`` dict for one feature.

    Priority (most restrictive wins):
        needs_bindings > needs_api_prompt > runnable
    """
    bindings = node_bindings if isinstance(node_bindings, dict) else {}
    required_keys = _FEATURE_BINDING_KEYS.get(feature_id, [])

    has_bindings = all(
        bool(bindings.get(k)) for k in required_keys
    )
    has_output_node = bool(output_node_id) if feature_id == "txt2img" else True

    has_api_prompt = bool(api_prompt_json) if feature_id == "txt2img" else True

    if not has_bindings or not has_output_node:
        return {"status": "needs_bindings", "reason": "missing required node bindings"}
    if not has_api_prompt:
        return {"status": "needs_api_prompt", "reason": "missing API prompt configuration"}
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


def normalize_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *payload* enriched with ``status`` and ``featureStatus``.

    The input dict is expected to contain (at least):
        compatibleFeatures, graphJson, apiPromptJson, nodeBindings, outputNodeId

    The enrichment adds:
        featureStatus — ``{feature_id: {"status": …, "reason": …}}`` per feature
        status        — aggregate across all features using the priority rules
    """
    result = dict(payload)
    features = _validate_feature_ids(result.get("compatibleFeatures", []))
    if not features:
        # No recognised features → invalid
        result["featureStatus"] = {}
        result["status"] = "invalid"
        return result

    node_bindings = result.get("nodeBindings", {}) or {}
    output_node_id = result.get("outputNodeId") or ""
    api_prompt_json = result.get("apiPromptJson") or {}

    feature_statuses: dict[str, dict[str, str]] = {}
    for fid in features:
        feature_statuses[fid] = _derive_feature_status(
            fid, node_bindings, output_node_id, api_prompt_json,
        )

    result["featureStatus"] = feature_statuses
    result["status"] = _aggregate_status(feature_statuses)

    # Archive overrides everything
    if result.get("archived"):
        result["status"] = "archived"

    return result


# ── Preset normalisation ─────────────────────────────────────────────────


def normalize_preset_payload(
    payload: dict[str, Any],
    snapshots_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return a copy of *payload* with normalised fields and derived ``status``.

    * If ``snapshotId`` is present and the snapshot is missing from
      ``snapshots_by_id``, status becomes ``"invalid"`` and
      ``disabledReason`` is set to ``"Preset references a missing snapshot"``.
    * If the referenced snapshot is found, the preset inherits the snapshot's
      aggregate ``status`` (runnable only when the snapshot is runnable).
    """
    result = dict(payload)

    # Required fields
    result.setdefault("label", payload.get("name", "Untitled Preset"))
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
            result["disabledReason"] = "Preset references a missing snapshot"
            return result
        # Inherit snapshot status (preset is runnable only when snapshot is)
        snap_status = snapshot.get("status", "runnable")
        result["status"] = snap_status
        # If snapshot is not runnable, mark the preset as derived-invalid
        if snap_status != "runnable":
            result["disabledReason"] = (
                result.get("disabledReason")
                or f"Referenced snapshot is {snap_status}"
            )
    else:
        # No snapshot reference — the preset exists but is unlinked
        result["status"] = "invalid"
        result["disabledReason"] = result.get(
            "disabledReason", "Preset does not reference a snapshot"
        )

    if result.get("archived"):
        result["status"] = "archived"

    return result
