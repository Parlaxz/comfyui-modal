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

import copy
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


# ── Reference methods (Phase 8, Lane A) ─────────────────────────────────
# Frozen method ids. Never rename: the Wizard, Mapping records, and the
# ``studio_references`` run companion all key on these exact strings.
REFERENCE_METHOD_IDS: frozenset[str] = frozenset({
    "conditioning_slots",
    "reference_latent_chain",
    "dedicated",
})

REFERENCE_METHOD_LABELS: dict[str, str] = {
    "conditioning_slots": "Conditioning slots",
    "reference_latent_chain": "Reference latent chain",
    "dedicated": "Dedicated reference workflow",
}

# Version-bound reference bindings live on the existing Mapping record (no
# second store, no graph DSL, no model-family identifiers): concrete node
# ids, socket names, output indices, edges, slot order, the reserved I2I
# source socket, and — for Method-2 — the chain boundary.
REFERENCE_BINDING_SOCKET_KINDS: frozenset[str] = frozenset({
    "reference",
    "source",
})


# ── Errors ───────────────────────────────────────────────────────────────


class WorkflowDomainError(RuntimeError):
    """Base error for the workflow domain."""


class WorkflowNotFoundError(WorkflowDomainError):
    pass


class WorkflowVersionNotFoundError(WorkflowDomainError):
    pass


class MappingNotFoundError(WorkflowDomainError):
    pass


class PresetNotFoundError(WorkflowDomainError):
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


def make_preset_id() -> str:
    return f"wp_{uuid.uuid4().hex[:16]}"


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
    text_generate_node_id: Optional[str] = None
    entries: dict[str, MappingEntry] = field(default_factory=dict)
    # Phase 8 reference bindings: version-bound, concrete only (node ids,
    # socket names, output indices, edges, slot order, reserved source
    # socket, Method-2 chain boundary). Empty/"" means unbound.
    reference_method: str = ""
    reference_bindings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "workflow_version_id": self.workflow_version_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output_node_id": self.output_node_id,
            "text_generate_node_id": self.text_generate_node_id,
            "entries": [e.to_dict() for e in self.entries.values()],
            "reference_method": self.reference_method,
            "reference_bindings": dict(self.reference_bindings or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Mapping":
        entries: dict[str, MappingEntry] = {}
        for raw in data.get("entries") or []:
            if isinstance(raw, dict):
                entry = MappingEntry.from_dict(raw)
                if entry.semantic_role:
                    entries[entry.semantic_role] = entry
        method = str(data.get("reference_method", "") or "")
        if method not in REFERENCE_METHOD_IDS:
            method = "" if method else method
        bindings = data.get("reference_bindings")
        return cls(
            mapping_id=str(data.get("mapping_id", "")),
            workflow_version_id=str(data.get("workflow_version_id", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            output_node_id=str(data.get("output_node_id", "")),
            text_generate_node_id=(
                None
                if data.get("text_generate_node_id") in (None, "")
                else str(data.get("text_generate_node_id"))
            ),
            entries=entries,
            reference_method=method,
            reference_bindings=(
                dict(bindings) if isinstance(bindings, dict) else {}
            ),
        )


# ── Reference binding helpers ────────────────────────────────────────────


def normalize_reference_bindings(
    method: Any, bindings: Any
) -> tuple[str, dict[str, Any], list[str]]:
    """Normalize a reference method + bindings pair without graph access.

    Returns ``(method, normalized, problems)``. Never raises. Structural
    only: method must be a frozen id; bindings must be a dict carrying only
    concrete addressing (node ids, socket names, output indices, edges,
    slot order, reserved source socket, chain boundary). Unknown keys are
    dropped; malformed shapes are reported, never coerced into evidence.
    """
    problems: list[str] = []
    name = str(method or "")
    if name and name not in REFERENCE_METHOD_IDS:
        return "", {}, [f"unknown reference method {name!r}"]
    if not name:
        return "", {}, []
    if not isinstance(bindings, dict):
        return name, {}, [f"reference bindings for {name!r} must be an object"]
    normalized: dict[str, Any] = {}
    try:
        candidate_id = bindings.get("candidate_id", bindings.get("candidateId", ""))
        if candidate_id is not None and str(candidate_id) != "":
            normalized["candidate_id"] = str(candidate_id)
        slots = bindings.get("slots", bindings.get("slot_order", []))
        if isinstance(slots, dict):
            slots = list(slots.values())
        norm_slots: list[dict[str, Any]] = []
        if isinstance(slots, (list, tuple)):
            for raw in slots:
                if not isinstance(raw, dict):
                    continue
                node_id = str(raw.get("node_id", raw.get("nodeId", "")) or "")
                socket = str(raw.get("socket", raw.get("socket_name", raw.get("input_name", ""))) or "")
                if not node_id or not socket:
                    continue
                entry: dict[str, Any] = {"node_id": node_id, "socket": socket}
                kind = str(raw.get("kind", raw.get("role", "reference")) or "reference")
                entry["kind"] = kind if kind in REFERENCE_BINDING_SOCKET_KINDS else "reference"
                try:
                    entry["order"] = int(raw.get("order", len(norm_slots)))
                except (TypeError, ValueError):
                    entry["order"] = len(norm_slots)
                out_idx = raw.get("output_index", raw.get("outputIndex"))
                if out_idx is not None:
                    try:
                        entry["output_index"] = int(out_idx)
                    except (TypeError, ValueError):
                        pass
                edge = raw.get("edge", raw.get("edge_id"))
                if edge is not None and str(edge) != "":
                    entry["edge"] = str(edge)
                norm_slots.append(entry)
        norm_slots.sort(key=lambda s: (int(s.get("order", 0)), s.get("node_id", ""), s.get("socket", "")))
        # Re-number densely so order is always 0..n-1 in slot order.
        for idx, entry in enumerate(norm_slots):
            entry["order"] = idx
        normalized["slots"] = norm_slots
        reserved = bindings.get("reserved_source_socket", bindings.get("reservedSourceSocket"))
        if isinstance(reserved, dict):
            rid = str(reserved.get("node_id", reserved.get("nodeId", "")) or "")
            rsock = str(reserved.get("socket", reserved.get("socket_name", reserved.get("input_name", ""))) or "")
            if rid and rsock:
                normalized["reserved_source_socket"] = {"node_id": rid, "socket": rsock}
        elif reserved is not None and not isinstance(reserved, dict):
            problems.append("reserved source socket must be an object")
        chain = bindings.get("chain", bindings.get("chain_boundary", bindings.get("chainBoundary")))
        if isinstance(chain, dict):
            norm_chain: dict[str, Any] = {}
            for key in ("loader_node_id", "vae_encode_node_id", "reference_latent_node_id",
                        "consumer_node_id", "vae_node_id"):
                val = chain.get(key)
                if val is not None and str(val) != "":
                    norm_chain[key] = str(val)
            for key in ("loader_socket", "vae_socket", "latent_socket", "conditioning_socket"):
                val = chain.get(key)
                if val is not None and str(val) != "":
                    norm_chain[key] = str(val)
            edges = chain.get("edges")
            if isinstance(edges, list):
                norm_chain["edges"] = [str(e) for e in edges if str(e) != ""]
            order = chain.get("order")
            if isinstance(order, list):
                norm_chain["order"] = [str(o) for o in order if str(o) != ""]
            if norm_chain:
                normalized["chain"] = norm_chain
        dedicated = bindings.get("dedicated_target", bindings.get("dedicatedTarget"))
        if dedicated is not None and str(dedicated) != "":
            normalized["dedicated_target"] = str(dedicated)
        cards = bindings.get("card_ids", bindings.get("cardIds"))
        if isinstance(cards, list):
            normalized["card_ids"] = [str(c) for c in cards if str(c) != ""]
    except Exception:
        problems.append("reference bindings are malformed")
    return name, normalized, problems


def build_studio_references_companion(
    *,
    method: str,
    origin_workflow_id: str,
    origin_version_id: str,
    bindings: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the top-level ``studio_references`` run companion.

    Explicit method, origin workflow/version, dedicated target where
    applicable, ordered card ids, server image refs (empty until the run
    attaches uploads), and source provenance. Never carries client graph
    patches — only addressing the server resolves against the version's
    stored graph. Never raises.
    """
    cards: list[str] = []
    dedicated_target = ""
    try:
        src = bindings if isinstance(bindings, dict) else {}
        raw_cards = src.get("card_ids", [])
        if isinstance(raw_cards, list) and [c for c in raw_cards if str(c) != ""]:
            cards = [str(c) for c in raw_cards if str(c) != ""]
        else:
            slots = src.get("slots", [])
            if isinstance(slots, list):
                cards = [
                    f"{s.get('node_id')}:{s.get('socket')}"
                    for s in slots
                    if isinstance(s, dict) and s.get("node_id") and s.get("socket")
                ]
        dedicated_target = str(src.get("dedicated_target", "") or "")
    except Exception:
        pass
    return {
        "method": str(method or ""),
        "origin_workflow_id": str(origin_workflow_id or ""),
        "origin_version_id": str(origin_version_id or ""),
        "dedicated_target": dedicated_target,
        "card_ids": list(cards),
        "images": [],
        "provenance": {"source": "mapping"},
    }


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


# ── Workflow presets (Phase 12) ────────────────────────────────────────────


@dataclass
class WorkflowPreset:
    """Version-scoped, image-free UI intent snapshot for one WorkflowVersion.

    Bound to exactly one ``workflow_version_id`` (no ``workflow_id`` field —
    the version already owns that edge) and carrying a closed
    ``studio_state`` v1 dict.  There is no default-preset concept: presets
    are peers and only move forward via explicit copy-to-version.
    ``mapping_fingerprint`` is server-computed at write time.
    """

    preset_id: str
    workflow_version_id: str
    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    studio_state: dict[str, Any] = field(default_factory=dict)
    mapping_fingerprint: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "workflow_version_id": self.workflow_version_id,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "studio_state": copy.deepcopy(self.studio_state),
            "mapping_fingerprint": self.mapping_fingerprint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowPreset":
        tags = data.get("tags")
        state = data.get("studio_state")
        return cls(
            preset_id=str(data.get("preset_id", "")),
            workflow_version_id=str(data.get("workflow_version_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            tags=[t for t in tags if isinstance(t, str)]
            if isinstance(tags, list) else [],
            studio_state=copy.deepcopy(state)
            if isinstance(state, dict) else {},
            mapping_fingerprint=str(data.get("mapping_fingerprint", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )
