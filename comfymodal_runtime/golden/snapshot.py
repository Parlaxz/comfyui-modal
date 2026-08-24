"""Golden snapshot composition: static metadata only, asserted quiescent.

The Golden snapshot is small and deterministic.  It contains
snapshot-resident static metadata (topology, manifests, safetensors
headers, tensor maps, QD range plans, skeletons/meta, identities) and
NEVER model weight values for CLIP/UNET/VAE — those are re-materialized
through the Golden QD4 loader after restore.

Capture-time contract: no active readers, no unresolved CUDA events, no
request state, no persistence queue, no speculative future, no temporary
owner, no pinned transfer buffers depending on stale runtime state.
Violations raise ``QuiescenceViolationError`` listing every violation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from .contracts import (
    GoldenError,
    ImmutableStateAbsentError,
    ModelRole,
    QuiescenceViolationError,
    RoleManifest,
)

__all__ = [
    "REQUIRED_STATIC_ENTRIES",
    "FORBIDDEN_SNAPSHOT_ENTRIES",
    "QuiescenceReport",
    "assert_quiescent",
    "SnapshotAccounting",
    "validate_exclusions",
    "build_snapshot_manifest",
    "immutable_metadata_present",
]

REQUIRED_STATIC_ENTRIES: Tuple[str, ...] = (
    "imports_modules_registry",
    "custom_node_registry",
    "workflow_topology_reachability",
    "execution_plan_static_facts",
    "tokenizer_config",
    "model_manifests",
    "safetensors_headers",
    "tensor_maps",
    "qd_range_plans",
    "clip_skeleton_meta",
    "unet_skeleton_meta",
    "vae_skeleton_meta",
    "model_identities",
)

FORBIDDEN_SNAPSHOT_ENTRIES: Tuple[str, ...] = (
    "clip_weight_values",
    "unet_weight_values",
    "vae_weight_values",
    "active_source_readers",
    "unresolved_cuda_events",
    "request_state",
    "persistence_queue",
    "speculative_future",
    "temporary_owner",
    "stale_pinned_transfer_buffers",
)


@dataclass(frozen=True)
class QuiescenceReport:
    quiescent: bool
    violations: Tuple[str, ...]


def assert_quiescent(
    *,
    loaders_active: bool = False,
    unresolved_cuda_events: int = 0,
    request_state_present: bool = False,
    persistence_queue_present: bool = False,
    speculative_future_present: bool = False,
    temporary_owner_present: bool = False,
    live_pinned_buffer_count: int = 0,
) -> QuiescenceReport:
    """Assert full worker/event/state quiescence immediately before capture."""
    violations = []
    if loaders_active:
        violations.append("active_source_readers present at capture")
    if unresolved_cuda_events:
        violations.append(f"unresolved_cuda_events={unresolved_cuda_events}")
    if request_state_present:
        violations.append("request_state present at capture")
    if persistence_queue_present:
        violations.append("persistence_queue present at capture")
    if speculative_future_present:
        violations.append("speculative_future present at capture")
    if temporary_owner_present:
        violations.append("temporary_owner present at capture")
    if live_pinned_buffer_count:
        violations.append(f"live_pinned_transfer_buffers={live_pinned_buffer_count}")
    report = QuiescenceReport(quiescent=not violations, violations=tuple(violations))
    if violations:
        raise QuiescenceViolationError("; ".join(violations))
    return report


@dataclass
class SnapshotAccounting:
    value_bytes_by_role: Dict[ModelRole, int] = field(
        default_factory=lambda: {role: 0 for role in ModelRole}
    )
    unique_storage_bytes: int = 0
    unique_storage_count: int = 0
    meta_params: int = 0
    known_strong_roots: list = field(default_factory=list)
    rss_bytes: int = 0
    cgroup_memory_bytes: Optional[int] = None


def validate_exclusions(
    accounting: SnapshotAccounting,
    excluded_roles: Tuple[ModelRole, ...] = (ModelRole.CLIP, ModelRole.UNET, ModelRole.VAE),
) -> None:
    """Weight-value exclusion is the default architectural goal; enforce it."""
    offenders = {
        role.value: accounting.value_bytes_by_role.get(role, 0)
        for role in excluded_roles
        if accounting.value_bytes_by_role.get(role, 0) > 0
    }
    if offenders:
        raise GoldenError(f"snapshot contains weight values for excluded roles: {offenders}")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(f"not serializable: {type(obj)!r}")


def build_snapshot_manifest(
    model_manifests: Mapping[ModelRole, RoleManifest],
    extra_static: Optional[Mapping[str, Any]] = None,
) -> dict:
    """Deterministic snapshot manifest of static metadata only."""
    manifests_out: Dict[str, Any] = {}
    for role in sorted(ModelRole, key=lambda r: r.value):
        manifest = model_manifests.get(role)
        if manifest is None:
            manifests_out[role.value] = None
            continue
        manifests_out[role.value] = {
            "identity_hash": manifest.identity_hash,
            "file_sha256": manifest.file_sha256,
            "model_path": manifest.model_path,
            "destination_kind": manifest.destination_kind.value,
            "layout": _json_default(manifest.layout),
            "qd_range_plan": {
                "block_bytes": manifest.qd_range_plan.block_bytes,
                "data_start": manifest.qd_range_plan.data_start,
                "data_end": manifest.qd_range_plan.data_end,
                "n_blocks": manifest.qd_range_plan.n_blocks,
            },
            "meta_params_count": manifest.meta_params_count,
        }

    doc: Dict[str, Any] = {}
    for entry in REQUIRED_STATIC_ENTRIES:
        if entry == "model_manifests":
            doc[entry] = manifests_out
        elif extra_static and entry in extra_static:
            doc[entry] = extra_static[entry]
        else:
            doc[entry] = "absent_at_build"
    doc["forbidden_absent"] = {name: True for name in FORBIDDEN_SNAPSHOT_ENTRIES}
    doc["manifest_sha256"] = hashlib.sha256(_canonical_json(doc).encode("utf-8")).hexdigest()
    return doc


def immutable_metadata_present(required: Mapping[str, bool]) -> None:
    """Runtime guard: absent immutable state is DEGRADED/FAILED, never silent rebuild."""
    missing = sorted(name for name, present in required.items() if not present)
    if missing:
        raise ImmutableStateAbsentError(f"required immutable snapshot-resident metadata absent: {missing}")
