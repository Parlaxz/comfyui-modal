"""Persistent domain model for the Studio Workflow platform.

Entities
--------
* ``Workflow`` — logical workflow identity (name, folder, tags, favorite,
  source metadata, compatible models, latest version).
* ``WorkflowVersion`` — immutable snapshot of the exact graph. Frozen once
  created; never mutated by the store or services.
* ``Mapping`` — exactly one per WorkflowVersion. Maps Studio semantic roles
  to graph nodes/inputs/outputs plus graph-derived metadata.
* ``MappingEntry`` — one mapped semantic role.

``VersionState`` is DERIVED at read time from stored data — it is never
persisted on the immutable version record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ── Canonical semantic roles (extension-friendly: unknown roles allowed) ──

CANONICAL_SEMANTIC_ROLES: frozenset[str] = frozenset({
    "positive_prompt",
    "negative_prompt",
    "seed",
    "steps",
    "cfg",
    "sampler",
    "scheduler",
    "model",
    "denoise",
    "width",
    "height",
    "source_image",
    "mask",
    "output",
})

# Mapping-entry kinds and control kinds
ENTRY_KINDS: frozenset[str] = frozenset({"node_input", "node_output", "widget", "node"})
CONTROL_KINDS: frozenset[str] = frozenset({
    "enum", "boolean", "integer", "number", "string", "multiline", "file", "image", "node",
})

# Output-capable node classes used for automatic output-node detection.
OUTPUT_NODE_CLASSES: tuple[str, ...] = (
    "SaveImage",
    "PreviewImage",
    "SaveImageWithMetaData",
)


# ── Errors ───────────────────────────────────────────────────────────────


class WorkflowDomainError(RuntimeError):
    """Base error for the workflow domain."""


class WorkflowNotFoundError(WorkflowDomainError):
    pass


class WorkflowVersionNotFoundError(WorkflowDomainError):
    pass


class MappingNotFoundError(WorkflowDomainError):
    pass


class MappingAlreadyExistsError(WorkflowDomainError):
    """A Workflow Version already has its (immutable) Mapping."""


class WorkflowDomainValidationError(WorkflowDomainError):
    pass


class ImmutableVersionError(WorkflowDomainError):
    pass


class WorkflowNotRunnableError(WorkflowDomainError):
    pass


class GraphHashError(WorkflowDomainError):
    pass


# ── Helpers ──────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_workflow_id() -> str:
    return f"wf_{uuid.uuid4().hex[:16]}"


def make_version_id() -> str:
    return f"wv_{uuid.uuid4().hex[:16]}"


def make_mapping_id() -> str:
    return f"wm_{uuid.uuid4().hex[:16]}"


def _sanitize_str(value: Any, max_len: int = 2000, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    return value.strip()[:max_len]


def _sanitize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item not in out:
            out.append(item)
    return out


# ── Entities ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorkflowVersion:
    """Immutable snapshot of one exact graph.

    Instances are frozen; the store offers no update/delete path for
    version records, so once persisted a version never changes.
    """

    workflow_version_id: str
    workflow_id: str
    version_number: int
    graph_json: dict
    api_prompt_json: dict
    executable_prompt: dict
    graph_hash: str
    created_at: str
    dependency_metadata: dict = field(default_factory=dict)
    compatible_models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_version_id": self.workflow_version_id,
            "workflow_id": self.workflow_id,
            "version_number": self.version_number,
            "graph_json": self.graph_json,
            "api_prompt_json": self.api_prompt_json,
            "executable_prompt": self.executable_prompt,
            "graph_hash": self.graph_hash,
            "created_at": self.created_at,
            "dependency_metadata": self.dependency_metadata,
            "compatible_models": list(self.compatible_models),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowVersion":
        compat = data.get("compatible_models")
        return cls(
            workflow_version_id=str(data.get("workflow_version_id", "")),
            workflow_id=str(data.get("workflow_id", "")),
            version_number=int(data.get("version_number", 0)),
            graph_json=dict(data.get("graph_json") or {}),
            api_prompt_json=dict(data.get("api_prompt_json") or {}),
            executable_prompt=dict(data.get("executable_prompt") or {}),
            graph_hash=str(data.get("graph_hash", "")),
            created_at=str(data.get("created_at", "")),
            dependency_metadata=dict(data.get("dependency_metadata") or {}),
            compatible_models=(
                [m for m in compat if isinstance(m, str)] if isinstance(compat, list) else []
            ),
        )


@dataclass
class Workflow:
    workflow_id: str
    name: str = ""
    description: str = ""
    folder: str = ""
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    source_url: str = ""
    source_author: str = ""
    compatible_models: list[str] = field(default_factory=list)
    latest_version_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "folder": self.folder,
            "tags": list(self.tags),
            "favorite": self.favorite,
            "source_url": self.source_url,
            "source_author": self.source_author,
            "compatible_models": list(self.compatible_models),
            "latest_version_id": self.latest_version_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        return cls(
            workflow_id=str(data.get("workflow_id", "")),
            name=_sanitize_str(data.get("name", ""), 200, "Untitled Workflow"),
            description=_sanitize_str(data.get("description", ""), 2000),
            folder=_sanitize_str(data.get("folder", ""), 500),
            tags=_sanitize_str_list(data.get("tags")),
            favorite=bool(data.get("favorite", False)),
            source_url=_sanitize_str(data.get("source_url", ""), 2000),
            source_author=_sanitize_str(data.get("source_author", ""), 500),
            compatible_models=_sanitize_str_list(data.get("compatible_models")),
            latest_version_id=_sanitize_str(data.get("latest_version_id", ""), 100),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass
class MappingEntry:
    semantic_role: str
    node_id: str
    input_name: str = ""
    output_name: str = ""
    kind: str = "node_input"
    data_type: str = ""
    enum_options: list = field(default_factory=list)
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    required: bool = False
    multiline: bool = False
    control_kind: str = "string"
    display_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_role": self.semantic_role,
            "node_id": self.node_id,
            "input_name": self.input_name,
            "output_name": self.output_name,
            "kind": self.kind,
            "data_type": self.data_type,
            "enum_options": list(self.enum_options),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "required": self.required,
            "multiline": self.multiline,
            "control_kind": self.control_kind,
            "display_name": self.display_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MappingEntry":
        kind = str(data.get("kind", "node_input"))
        if kind not in ENTRY_KINDS:
            kind = "node_input"
        control_kind = str(data.get("control_kind", "string"))
        if control_kind not in CONTROL_KINDS:
            control_kind = "string"
        enum_options = data.get("enum_options") or []
        if not isinstance(enum_options, list):
            enum_options = [enum_options]

        def _opt_num(value: Any) -> Optional[float]:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return cls(
            semantic_role=str(data.get("semantic_role", "")),
            node_id=str(data.get("node_id", "")),
            input_name=str(data.get("input_name", "")),
            output_name=str(data.get("output_name", "")),
            kind=kind,
            data_type=str(data.get("data_type", "")),
            enum_options=list(enum_options),
            minimum=_opt_num(data.get("minimum")),
            maximum=_opt_num(data.get("maximum")),
            step=_opt_num(data.get("step")),
            required=bool(data.get("required", False)),
            multiline=bool(data.get("multiline", False)),
            control_kind=control_kind,
            display_name=str(data.get("display_name", "")),
        )


@dataclass
class Mapping:
    """Exactly one Mapping exists per WorkflowVersion (store-enforced)."""

    mapping_id: str
    workflow_version_id: str
    created_at: str = ""
    updated_at: str = ""
    output_node_id: str = ""
    entries: dict[str, MappingEntry] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "workflow_version_id": self.workflow_version_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output_node_id": self.output_node_id,
            "entries": [e.to_dict() for e in self.entries.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Mapping":
        entries: dict[str, MappingEntry] = {}
        for raw in data.get("entries") or []:
            if isinstance(raw, dict):
                entry = MappingEntry.from_dict(raw)
                if entry.semantic_role:
                    entries[entry.semantic_role] = entry
        return cls(
            mapping_id=str(data.get("mapping_id", "")),
            workflow_version_id=str(data.get("workflow_version_id", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            output_node_id=str(data.get("output_node_id", "")),
            entries=entries,
        )


# ── Derived states ───────────────────────────────────────────────────────


@dataclass
class VersionState:
    status: str = "incomplete"  # "ready" | "incomplete"
    reasons: list[str] = field(default_factory=list)
    runnable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "runnable": self.runnable,
        }
