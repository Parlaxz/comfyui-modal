"""Studio Workflow platform foundation.

Workflow → immutable Workflow Version → exactly one Mapping, plus
version-scoped Workflow Presets (image-free studio_state v1 snapshots).

* ``models`` — dataclass entities and derived states.
* ``preset_state`` — closed studio_state v1 normalization/validation.
* ``store`` — atomic JSON persistence (versions are write-once immutable;
  exactly one mapping per version; presets cascade with their workflow).
* ``graph`` — pure graph introspection (hashing, node-def metadata, mapping
  candidates).
* ``services`` — ``WorkflowDomainService`` with all domain rules (mapping
  revisions, incomplete states, model compatibility, presets).
"""

from .models import (
    CANONICAL_SEMANTIC_ROLES,
    CONTROL_KINDS,
    ENTRY_KINDS,
    OUTPUT_NODE_CLASSES,
    REFERENCE_BINDING_SOCKET_KINDS,
    REFERENCE_METHOD_IDS,
    REFERENCE_METHOD_LABELS,
    build_studio_references_companion,
    normalize_reference_bindings,
    GraphHashError,
    ImmutableVersionError,
    Mapping,
    MappingAlreadyExistsError,
    MappingEntry,
    MappingNotFoundError,
    PresetNotFoundError,
    VersionState,
    Workflow,
    WorkflowPreset,
    WorkflowDomainError,
    WorkflowNotFoundError,
    WorkflowNotRunnableError,
    WorkflowDomainValidationError,
    WorkflowVersion,
    WorkflowVersionNotFoundError,
    make_mapping_id,
    make_preset_id,
    make_version_id,
    make_workflow_id,
    now_iso,
)
from .preset_state import (
    STUDIO_STATE_SCHEMA_VERSION,
    STUDIO_STATE_SECTIONS,
    compute_mapping_fingerprint,
    normalize_preset_metadata,
    normalize_studio_state,
    validate_studio_state,
)
from .store import WorkflowDomainStore
from .graph import (
    INPUT_BINDING_KINDS,
    derive_mapping_candidates,
    discover_reference_candidates,
    extract_dependency_metadata,
    extract_executable_prompt,
    find_binding_candidates,
    graph_hash_from_capture,
    infer_control_kind,
    is_ui_workflow_format,
    resolve_binding_target,
    subgraph_node_present,
    subgraph_resolve_output,
    ui_graph_has_nested_containers,
    ui_graph_to_api_prompt,
)
from .services import WorkflowDomainService

__all__ = [
    "Workflow",
    "WorkflowVersion",
    "WorkflowPreset",
    "Mapping",
    "MappingEntry",
    "VersionState",
    "STUDIO_STATE_SCHEMA_VERSION",
    "STUDIO_STATE_SECTIONS",
    "normalize_studio_state",
    "validate_studio_state",
    "normalize_preset_metadata",
    "compute_mapping_fingerprint",
    "WorkflowDomainStore",
    "WorkflowDomainService",
    "CANONICAL_SEMANTIC_ROLES",
    "CONTROL_KINDS",
    "ENTRY_KINDS",
    "OUTPUT_NODE_CLASSES",
    "REFERENCE_METHOD_IDS",
    "REFERENCE_METHOD_LABELS",
    "REFERENCE_BINDING_SOCKET_KINDS",
    "normalize_reference_bindings",
    "build_studio_references_companion",
    "discover_reference_candidates",
    "WorkflowDomainError",
    "WorkflowNotFoundError",
    "WorkflowVersionNotFoundError",
    "MappingNotFoundError",
    "PresetNotFoundError",
    "MappingAlreadyExistsError",
    "WorkflowDomainValidationError",
    "ImmutableVersionError",
    "WorkflowNotRunnableError",
    "GraphHashError",
    "INPUT_BINDING_KINDS",
    "make_workflow_id",
    "make_version_id",
    "make_preset_id",
    "make_mapping_id",
    "now_iso",
    "derive_mapping_candidates",
    "extract_dependency_metadata",
    "extract_executable_prompt",
    "find_binding_candidates",
    "graph_hash_from_capture",
    "infer_control_kind",
    "is_ui_workflow_format",
    "resolve_binding_target",
    "subgraph_node_present",
    "subgraph_resolve_output",
    "ui_graph_has_nested_containers",
    "ui_graph_to_api_prompt",
]
