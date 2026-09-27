"""Pure, runtime-neutral structural seed builder for schema-v2 snapshots.

This module performs graph analysis over a canonical ComfyUI workflow mapping
(``{node_id: {"class_type": ..., "inputs": {...}}}``) and produces a
deterministic ``SnapshotExecutionSeed``.  It has NO ComfyUI or Modal imports
and never touches tensors, model objects, request state, random state, or
mutable caches.

Static vs dynamic classification (narrow, conservative rule set):

STATIC
- ``class_type`` (structural, emitted as ``node_class``).
- Link edges: list/tuple-shaped input values of the form
  ``["<node_id>", <output_index>]`` (or a list of such links).
- Loader nodes (``class_type`` containing ``"Loader"``): non-link inputs are
  treated as fixed filenames/options, EXCEPT the user-controlled LoRA strength
  keys (``strength``/``strength_model``/``strength_clip``) which are dynamic.
- Sampler nodes (``class_type`` containing ``"Sampler"``): only
  ``sampler_name`` and ``scheduler`` (fixed algorithm/scheduler) are static.
- Output routing: the designated ``output_node_ids`` set (structural field).

DYNAMIC (never guessed static)
- Prompt text, seed, width/height, input images/masks, denoise, LoRA strength,
  request-metadata values, and any unknown/non-link value.
- Anything that is not JSON-safe is dynamic.

Unknown inputs default to dynamic by design.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import SnapshotExecutionSeed, stable_hash


# ── Deterministic helpers ──────────────────────────────────────────────────


def _num_key(value: str) -> tuple[int, int | str]:
    """Numeric-aware sort key: ``"2" < "10" < "abc"``."""
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _normalize_node_ids(values: Any) -> tuple[str, ...]:
    """Stringify, deduplicate, and sort node IDs deterministically."""
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(sorted(result, key=_num_key))


def _normalize_workflow(workflow: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Canonicalize a workflow mapping into ``{nid: {"class_type", "inputs"}}``.

    Malformed/non-mapping nodes are dropped; node ids are stringified.
    Consumers always iterate sorted keys, so output is independent of the
    input dict's insertion order.
    """
    canonical: dict[str, dict[str, Any]] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, Mapping):
            continue
        nid = str(node_id).strip()
        if not nid:
            continue
        raw_inputs = node.get("inputs", {})
        inputs: dict[str, Any] = {}
        if isinstance(raw_inputs, Mapping):
            for name, value in raw_inputs.items():
                inputs[str(name)] = value
        canonical[nid] = {
            "class_type": str(node.get("class_type", "")),
            "inputs": inputs,
        }
    return canonical


# Sentinel marking a value that is not JSON-serializable.
_NON_JSON: Any = object()


def _json_safe(value: Any) -> Any:
    """Return a JSON-safe deep copy, or ``_NON_JSON`` for non-serializable data.

    Deterministic for the values it keeps; containers containing a
    non-serializable leaf collapse to ``_NON_JSON``.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe = _json_safe(item)
            if safe is _NON_JSON:
                return _NON_JSON
            result[str(key)] = safe
        return result
    if isinstance(value, (list, tuple)):
        result_list: list[Any] = []
        for item in value:
            safe = _json_safe(item)
            if safe is _NON_JSON:
                return _NON_JSON
            result_list.append(safe)
        return result_list
    return _NON_JSON


def _stable_value(value: Any) -> Any:
    """Deterministic structural representation (type-tags non-JSON leaves)."""
    safe = _json_safe(value)
    if safe is not _NON_JSON:
        return safe
    if isinstance(value, Mapping):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    return {"__non_json__": type(value).__name__}


def _json_safe_lenient(value: Any) -> Any:
    """JSON-safe copy that drops non-serializable leaves instead of collapsing.

    Used for preserved identity metadata (loader/sampler signatures) so that
    string signature fields survive while tensor/object leaves are stripped.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe = _json_safe_lenient(item)
            if safe is not _NON_JSON:
                result[str(key)] = safe
        return result
    if isinstance(value, (list, tuple)):
        result_list: list[Any] = []
        for item in value:
            safe = _json_safe_lenient(item)
            if safe is not _NON_JSON:
                result_list.append(safe)
        return result_list
    return _NON_JSON


def _normalize_entries(entries: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """JSON-safe normalization of supplied metadata (order preserved).

    Non-serializable leaves (tensors, model objects, caches) are stripped;
    entries that end up empty are dropped — the seed never stores mutable
    runtime state.
    """
    if not isinstance(entries, (list, tuple, set, frozenset)):
        return ()
    result: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        safe = _json_safe_lenient(entry)
        if safe is _NON_JSON or not isinstance(safe, dict) or not safe:
            continue
        result.append(safe)
    return tuple(result)


# ── Link / node classification ────────────────────────────────────────────


def _extract_links(value: Any) -> list[tuple[str, int]] | None:
    """Extract link edges from a ComfyUI-shaped input value.

    Returns a list of ``(source_node_id, output_index)`` pairs when the value
    is link-shaped (``["<node>", <index>]`` or a list of such links), else
    ``None`` (meaning: not a link — never guessed static).
    """
    if isinstance(value, (list, tuple)) and len(value) == 2:
        first, second = value
        if isinstance(first, (str, int)) and isinstance(second, int):
            return [(str(first), int(second))]
    if isinstance(value, (list, tuple)) and value:
        pairs: list[tuple[str, int]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                return None
            first, second = item
            if not (isinstance(first, (str, int)) and isinstance(second, int)):
                return None
            pairs.append((str(first), int(second)))
        return pairs
    return None


def _is_loader_class(class_type: str) -> bool:
    return "Loader" in class_type


def _is_sampler_class(class_type: str) -> bool:
    return "Sampler" in class_type


# Loader inputs that are user-controlled strengths (never static).
LOADER_DYNAMIC_KEYS: frozenset[str] = frozenset({"strength", "strength_model", "strength_clip"})

# Sampler inputs that encode the fixed algorithm/scheduler.
SAMPLER_STATIC_KEYS: frozenset[str] = frozenset({"sampler_name", "scheduler"})

_PROMPT_ENCODE_CLASSES: frozenset[str] = frozenset({"CLIPTextEncode", "CLIPTextEncodeSDXL"})


def _dynamic_reason(node_class: str, input_name: str) -> str:
    """Human-readable reason for classifying an input as dynamic."""
    if node_class in _PROMPT_ENCODE_CLASSES and input_name == "text":
        return "prompt_text"
    if input_name == "seed":
        return "seed"
    if input_name in ("image", "images"):
        return "input_image"
    if input_name in ("mask", "masks"):
        return "input_mask"
    if input_name == "denoise":
        return "denoise_user_controlled"
    if input_name.startswith("width") or input_name.startswith("height"):
        return "spatial_dimension"
    if "strength" in input_name:
        return "strength_user_controlled"
    if input_name.startswith("request") or "metadata" in input_name:
        return "request_metadata"
    return "unknown_dynamic"


def _classify_inputs(
    node_class: str,
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Classify a node's inputs into static values and dynamic (name, reason).

    Unknown/non-link/non-JSON-safe values are always dynamic.
    """
    is_loader = _is_loader_class(node_class)
    is_sampler = _is_sampler_class(node_class)
    static_inputs: dict[str, Any] = {}
    dynamic: list[tuple[str, str]] = []

    for name in sorted(inputs):
        value = inputs[name]
        links = _extract_links(value)
        if links is not None:
            # Link edges are structural/static.
            static_inputs[name] = [[source, index] for source, index in links]
            continue

        if is_loader:
            if name in LOADER_DYNAMIC_KEYS:
                dynamic.append((name, "lora_strength_user_controlled"))
                continue
            # Fixed loader filenames/options are static (JSON-safe only).
            safe = _json_safe(value)
            if safe is _NON_JSON:
                dynamic.append((name, "non_json_input"))
            else:
                static_inputs[name] = safe
            continue

        if is_sampler:
            # Fixed sampler algorithm/scheduler are static; everything else
            # (seed, steps, cfg, denoise, ...) is dynamic by default.
            if name in SAMPLER_STATIC_KEYS:
                safe = _json_safe(value)
                if safe is _NON_JSON:
                    dynamic.append((name, "non_json_input"))
                else:
                    static_inputs[name] = safe
            else:
                dynamic.append((name, _dynamic_reason(node_class, name)))
            continue

        # Generic / unknown node: non-link inputs are dynamic by default.
        dynamic.append((name, _dynamic_reason(node_class, name)))

    return static_inputs, dynamic


# ── Graph analysis ─────────────────────────────────────────────────────────


def _build_edges(canonical: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    """Map ``target_node_id -> [source_node_id, ...]`` via link-shaped inputs."""
    edges: dict[str, list[str]] = {}
    for node_id, node in canonical.items():
        inputs = node.get("inputs", {})
        if not isinstance(inputs, Mapping):
            continue
        sources: list[str] = []
        for value in inputs.values():
            links = _extract_links(value)
            if links is None:
                continue
            for source, _index in links:
                if source in canonical and source not in sources:
                    sources.append(source)
        if sources:
            edges[node_id] = sorted(sources, key=_num_key)
    return edges


def _compute_reachable(
    canonical: Mapping[str, Mapping[str, Any]],
    output_node_ids: Sequence[str],
) -> tuple[str, ...]:
    """Backward-reachable node set from outputs through link edges (sorted)."""
    edges = _build_edges(canonical)
    frontier = [node_id for node_id in output_node_ids if node_id in canonical]
    seen: set[str] = set(frontier)
    while frontier:
        target = frontier.pop()
        for source in edges.get(target, ()):
            if source not in seen:
                seen.add(source)
                frontier.append(source)
    return tuple(sorted(seen, key=_num_key))


def _compute_execution_order(
    canonical: Mapping[str, Mapping[str, Any]],
    reachable_ids: Sequence[str],
    edges: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    """Deterministic topological order; stable fallback for cycles/malformed."""
    reachable = set(reachable_ids)
    indegree: dict[str, int] = {node_id: 0 for node_id in reachable}
    dependents: dict[str, list[str]] = {}
    for target, sources in edges.items():
        if target not in reachable:
            continue
        for source in sources:
            if source in reachable:
                indegree[target] += 1
                dependents.setdefault(source, []).append(target)

    ready = sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=_num_key)
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for dependent in sorted(dependents.get(node_id, ()), key=_num_key):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort(key=_num_key)

    if len(order) < len(reachable):
        # Cycle (or malformed graph) — append remaining nodes in stable order.
        remaining = sorted(reachable - set(order), key=_num_key)
        order.extend(remaining)
    return tuple(order)


# ── Public builder ─────────────────────────────────────────────────────────


def build_snapshot_execution_seed(
    workflow: Mapping[str, Any],
    *,
    output_node_ids: Sequence[str] = (),
    workflow_hash: str = "",
    source_workflow_hash: str = "",
    custom_node_generation: str = "",
    deployment_combined_hash: str = "",
    loader_cache_signatures: Sequence[Mapping[str, Any]] = (),
    sampler_static_inputs: Sequence[Mapping[str, Any]] = (),
) -> SnapshotExecutionSeed:
    """Build a deterministic schema-v2 ``SnapshotExecutionSeed``.

    ``workflow`` is a canonical mapping ``{node_id: {"class_type", "inputs"}}``.
    Result is independent of the input dict's insertion order and contains no
    outputs, tensors, model objects, request IDs, random state, or caches.
    """
    canonical = _normalize_workflow(workflow)
    computed_hash = str(workflow_hash or stable_hash(_stable_value(canonical)))
    resolved_source_hash = str(source_workflow_hash or computed_hash)

    outputs = _normalize_node_ids(output_node_ids)
    if not outputs:
        outputs = tuple(sorted(canonical, key=_num_key))

    reachable = _compute_reachable(canonical, outputs)
    edges = _build_edges(canonical)
    order = _compute_execution_order(canonical, reachable, edges)

    loader_ids = tuple(
        sorted(
            (node_id for node_id in reachable if _is_loader_class(canonical[node_id]["class_type"])),
            key=_num_key,
        )
    )
    sampler_ids = tuple(
        sorted(
            (node_id for node_id in reachable if _is_sampler_class(canonical[node_id]["class_type"])),
            key=_num_key,
        )
    )

    static_signatures: list[dict[str, Any]] = []
    dynamic_map: list[dict[str, Any]] = []
    for node_id in reachable:
        node = canonical[node_id]
        node_class = node["class_type"]
        static_inputs, dynamic_entries = _classify_inputs(node_class, node.get("inputs", {}))
        static_signatures.append({
            "node_id": node_id,
            "node_class": node_class,
            "static_inputs": static_inputs,
            "hash": stable_hash(static_inputs),
        })
        for name, reason in dynamic_entries:
            dynamic_map.append({"node_id": node_id, "input": name, "reason": reason})

    return SnapshotExecutionSeed(
        schema_version=2,
        workflow_hash=computed_hash,
        source_workflow_hash=resolved_source_hash,
        output_node_ids=outputs,
        reachable_node_ids=reachable,
        execution_order_hint=order,
        loader_node_ids=loader_ids,
        loader_cache_signatures=_normalize_entries(loader_cache_signatures),
        static_node_signatures=tuple(static_signatures),
        dynamic_input_map=tuple(dynamic_map),
        sampler_node_ids=sampler_ids,
        sampler_static_inputs=_normalize_entries(sampler_static_inputs),
        custom_node_generation=str(custom_node_generation or ""),
        deployment_combined_hash=str(deployment_combined_hash or ""),
    )


# ── Seed attestation payloads (Step 3) ────────────────────────────────────
# Deployment-scoped JSON seed payloads built on the publisher side where the
# canonical workflow is available, and hydrated at restore before the first
# request.  The payload wrapper is intentionally small: the schema-v2 seed
# (structural data only) plus source/topology observability.  No outputs,
# tensors, request state, caches, random state, or GPU handles ever appear.

SEED_SOURCE_PUBLISHER_PLAN = "publisher_plan"
SEED_SOURCE_STARTUP_MINIMAL = "startup_minimal"
# Request-derived seed source: built on the CONTAINER side from the request's
# own plan payload (no remote restore-plan publication).  Never used to fake
# ``publisher_plan`` — restore-time and request-time hydration emit it only
# when the seed was genuinely derived from the invocation's workflow.
SEED_SOURCE_INVOCATION_PLAN = "invocation_plan"
SEED_PAYLOAD_FILENAME = "snapshot_seed.json"
SEED_PAYLOAD_SCHEMA_VERSION = 2

# Opt-in env flag for the legacy remote restore-plan publication path.  The
# default (unset / "0") skips the remote ``publish_restore_plan`` RPC entirely;
# the container then derives its seed from the invocation plan and restore-time
# volume reads are skipped so a stale ``snapshot_seed.json`` can never claim
# ``source=publisher_plan``.  Setting the flag to a truthy value restores the
# legacy publisher path for diagnostics.
PUBLISH_RESTORE_PLAN_ENV = "COMFYMODAL_V2_PUBLISH_RESTORE_PLAN"


def publish_restore_plan_enabled() -> bool:
    """True only when the opt-in ``COMFYMODAL_V2_PUBLISH_RESTORE_PLAN`` flag
    is truthy.  Default (unset / "0") disables remote restore publication."""
    return os.environ.get(PUBLISH_RESTORE_PLAN_ENV, "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def build_snapshot_seed_payload(
    workflow: Mapping[str, Any],
    *,
    output_node_ids: Sequence[str] = (),
    workflow_hash: str = "",
    source_workflow_hash: str = "",
    custom_node_generation: str = "",
    deployment_combined_hash: str = "",
) -> dict[str, Any] | None:
    """Build a deployment-scoped schema-v2 seed payload from a canonical
    workflow (publisher side, where ``RestorePlan.workflow`` is available).

    Returns ``None`` when the workflow is empty — no topology is available, so
    callers must fall back honestly to ``minimal_snapshot_seed_payload``.
    """
    if not workflow:
        return None
    seed = build_snapshot_execution_seed(
        workflow,
        output_node_ids=output_node_ids,
        workflow_hash=workflow_hash,
        source_workflow_hash=source_workflow_hash,
        custom_node_generation=custom_node_generation,
        deployment_combined_hash=deployment_combined_hash,
    )
    return {
        "schema_version": SEED_PAYLOAD_SCHEMA_VERSION,
        "seed_source": SEED_SOURCE_PUBLISHER_PLAN,
        "topology_available": True,
        "built_at": time.time(),
        "workflow_hash": seed.workflow_hash,
        "seed": seed.to_dict(),
    }


def build_invocation_seed_payload(
    workflow: Mapping[str, Any],
    *,
    output_node_ids: Sequence[str] = (),
    workflow_hash: str = "",
    source_workflow_hash: str = "",
    custom_node_generation: str = "",
    deployment_combined_hash: str = "",
) -> dict[str, Any] | None:
    """Build a schema-v2 seed payload from the REQUEST's own workflow.

    Mirrors ``build_snapshot_seed_payload`` except the ``seed_source`` is
    ``invocation_plan`` (never ``publisher_plan``): the seed was derived on
    the container side from the invocation plan, not published remotely.
    Returns ``None`` when the workflow is empty — callers fall back honestly
    to ``minimal_snapshot_seed_payload``.
    """
    if not workflow:
        return None
    seed = build_snapshot_execution_seed(
        workflow,
        output_node_ids=output_node_ids,
        workflow_hash=workflow_hash,
        source_workflow_hash=source_workflow_hash,
        custom_node_generation=custom_node_generation,
        deployment_combined_hash=deployment_combined_hash,
    )
    return {
        "schema_version": SEED_PAYLOAD_SCHEMA_VERSION,
        "seed_source": SEED_SOURCE_INVOCATION_PLAN,
        "topology_available": True,
        "built_at": time.time(),
        "workflow_hash": seed.workflow_hash,
        "seed": seed.to_dict(),
    }


def minimal_snapshot_seed_payload(
    *,
    workflow_hash: str = "",
    source_workflow_hash: str = "",
    custom_node_generation: str = "",
    deployment_combined_hash: str = "",
    loader_cache_signatures: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build an honest minimal schema-v2 seed payload for restore when the
    persisted publisher payload is unavailable.

    ``seed_source="startup_minimal"`` and ``topology_available=False``: the
    seed carries only identity/loader-signature fields, never topology or
    static node structure.
    """
    seed = SnapshotExecutionSeed(
        schema_version=2,
        workflow_hash=str(workflow_hash or ""),
        source_workflow_hash=str(source_workflow_hash or workflow_hash or ""),
        custom_node_generation=str(custom_node_generation or ""),
        deployment_combined_hash=str(deployment_combined_hash or ""),
        loader_cache_signatures=tuple(dict(entry) for entry in loader_cache_signatures),
    )
    return {
        "schema_version": SEED_PAYLOAD_SCHEMA_VERSION,
        "seed_source": SEED_SOURCE_STARTUP_MINIMAL,
        "topology_available": False,
        "built_at": time.time(),
        "workflow_hash": seed.workflow_hash,
        "seed": seed.to_dict(),
    }


def snapshot_seed_payload_from_dict(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Validate and normalize a persisted seed payload dict.

    Fail-closed: returns ``None`` when the payload is not a recognized
    schema-v2 seed payload.  Forbidden runtime state in ``seed`` is ignored by
    ``SnapshotExecutionSeed.from_dict`` (never deserialized).
    """
    if not isinstance(value, Mapping):
        return None
    payload = dict(value)
    seed_data = payload.get("seed")
    if not isinstance(seed_data, Mapping):
        return None
    try:
        seed = SnapshotExecutionSeed.from_dict(seed_data)
    except Exception:
        return None
    if int(seed.schema_version) != SEED_PAYLOAD_SCHEMA_VERSION:
        return None
    seed_source = str(payload.get("seed_source", ""))
    if seed_source not in (
        SEED_SOURCE_PUBLISHER_PLAN,
        SEED_SOURCE_STARTUP_MINIMAL,
        SEED_SOURCE_INVOCATION_PLAN,
    ):
        return None
    return {
        "schema_version": SEED_PAYLOAD_SCHEMA_VERSION,
        "seed_source": seed_source,
        "topology_available": bool(
            payload.get("topology_available", seed_source == SEED_SOURCE_PUBLISHER_PLAN)
        ),
        "built_at": payload.get("built_at", 0.0),
        "workflow_hash": seed.workflow_hash,
        "seed": seed.to_dict(),
    }


def snapshot_seed_observability(seed: SnapshotExecutionSeed | Mapping[str, Any] | None) -> dict[str, Any]:
    """Source/topology observability for bootstrap state and the
    ``[v2.seed_build]`` / ``[v2.seed_restore]`` markers.

    Always returns primitive JSON-safe values; never stores outputs, tensors,
    or request state.
    """
    if seed is None:
        return {
            "schema_version": 0,
            "seed_source": "",
            "topology_available": False,
            "workflow_hash": "",
            "loader_node_count": 0,
            "sampler_node_count": 0,
            "reachable_node_count": 0,
            "static_signature_count": 0,
        }
    if isinstance(seed, Mapping):
        try:
            seed = SnapshotExecutionSeed.from_dict(seed)
        except Exception:
            return {
                "schema_version": 0,
                "seed_source": "",
                "topology_available": False,
                "workflow_hash": "",
                "loader_node_count": 0,
                "sampler_node_count": 0,
                "reachable_node_count": 0,
                "static_signature_count": 0,
            }
    return {
        "schema_version": int(getattr(seed, "schema_version", 0) or 0),
        "seed_source": "",
        "topology_available": bool(getattr(seed, "reachable_node_ids", ())),
        "workflow_hash": str(getattr(seed, "workflow_hash", "") or ""),
        "loader_node_count": len(tuple(getattr(seed, "loader_node_ids", ()) or ())),
        "sampler_node_count": len(tuple(getattr(seed, "sampler_node_ids", ()) or ())),
        "reachable_node_count": len(tuple(getattr(seed, "reachable_node_ids", ()) or ())),
        "static_signature_count": len(tuple(getattr(seed, "static_node_signatures", ()) or ())),
    }


def snapshot_seed_state_root() -> str:
    """Local ``.runtime_state/`` directory rooted at the plugin root.

    Same convention as ``restore_plan.get_default_restore_publisher`` — the
    narrow existing-state path used for deployment-scoped seed persistence.
    """
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(plugin_root, ".runtime_state")


def persist_snapshot_seed_payload(
    payload: Mapping[str, Any],
    *,
    root: str | None = None,
    commit: bool = True,
) -> bool:
    """Atomically persist the deployment-scoped seed payload as JSON.

    Uses the same ``MountedStateVolume`` (temp file + atomic rename) as the
    restore-plan state.  Never raises — returns ``False`` on any error.
    """
    try:
        from .runtime_state import MountedStateVolume

        volume = MountedStateVolume(root or snapshot_seed_state_root())
        encoded = json.dumps(
            dict(payload), separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
        volume.write_bytes(SEED_PAYLOAD_FILENAME, encoded)
        if commit:
            volume.commit()
        return True
    except Exception:
        return False


def read_snapshot_seed_payload(root: str | None = None) -> dict[str, Any] | None:
    """Read and validate the persisted seed payload.

    Returns ``None`` when absent or invalid (fail-closed).  Never raises.
    """
    try:
        from .runtime_state import MountedStateVolume

        volume = MountedStateVolume(root or snapshot_seed_state_root())
        if not volume.exists(SEED_PAYLOAD_FILENAME):
            return None
        raw = volume.read_bytes(SEED_PAYLOAD_FILENAME)
        if not raw:
            return None
        payload = json.loads(raw.decode("utf-8"))
        return snapshot_seed_payload_from_dict(payload)
    except Exception:
        return None
