"""Studio Workflow platform foundation.

Workflow → immutable Workflow Version → exactly one Mapping.

* ``models`` — dataclass entities and derived states.
* ``store`` — atomic JSON persistence (versions are write-once immutable;
  exactly one mapping per version).
* ``graph`` — pure graph introspection (hashing, node-def metadata, mapping
  candidates).
* ``services`` — ``WorkflowDomainService`` with all domain rules (mapping
  revisions, incomplete states, model compatibility).
"""

from .models import (
    CANONICAL_SEMANTIC_ROLES,
    CONTROL_KINDS,
    ENTRY_KINDS,
    OUTPUT_NODE_CLASSES,
    GraphHashError,
    ImmutableVersionError,
    Mapping,
    MappingAlreadyExistsError,
    MappingEntry,
    MappingNotFoundError,
    VersionState,
    Workflow,
    WorkflowDomainError,
    WorkflowNotFoundError,
    WorkflowNotRunnableError,
    WorkflowDomainValidationError,
    WorkflowVersion,
    WorkflowVersionNotFoundError,
    make_mapping_id,
    make_version_id,
    make_workflow_id,
    now_iso,
)
from .store import WorkflowDomainStore
from .graph import (
    derive_mapping_candidates,
    extract_dependency_metadata,
    extract_executable_prompt,
    graph_hash_from_capture,
    infer_control_kind,
    is_ui_workflow_format,
    ui_graph_to_api_prompt,
)
from .services import WorkflowDomainService

__all__ = [
    "Workflow",
    "WorkflowVersion",
    "Mapping",
    "MappingEntry",
    "VersionState",
    "WorkflowDomainStore",
    "WorkflowDomainService",
    "CANONICAL_SEMANTIC_ROLES",
    "CONTROL_KINDS",
    "ENTRY_KINDS",
    "OUTPUT_NODE_CLASSES",
    "WorkflowDomainError",
    "WorkflowNotFoundError",
    "WorkflowVersionNotFoundError",
    "MappingNotFoundError",
    "MappingAlreadyExistsError",
    "WorkflowDomainValidationError",
    "ImmutableVersionError",
    "WorkflowNotRunnableError",
    "GraphHashError",
    "make_workflow_id",
    "make_version_id",
    "make_mapping_id",
    "now_iso",
    "derive_mapping_candidates",
    "extract_dependency_metadata",
    "extract_executable_prompt",
    "graph_hash_from_capture",
    "infer_control_kind",
    "is_ui_workflow_format",
    "ui_graph_to_api_prompt",
]
