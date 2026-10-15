"""Domain services for the Workflow platform foundation.

Owns the business rules:

* Workflows are organized (folders/tags/favorites) and identify their latest
  version.
* WorkflowVersions are immutable snapshots; structural change creates a new
  version (deduplicated by canonical graph hash).
* Exactly one Mapping per version; mappings may be edited.
* Incomplete versions are saved but unrunnable, with explicit
  reasons; ``assert_runnable`` guards any future run entry point.
* ``0`` / ``False`` / ``0.0`` / ``""`` are valid values — only ``None`` or
  absent keys count as missing.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Optional

from .graph import (
    INPUT_BINDING_KINDS,
    derive_mapping_candidates,
    discover_reference_candidates,
    extract_dependency_metadata,
    extract_executable_prompt,
    find_binding_candidates,
    graph_hash_from_capture,
    is_ui_workflow_format,
    node_exists,
    resolve_binding_target,
    subgraph_node_present,
    subgraph_resolve_output,
    ui_graph_to_api_prompt,
)
from .models import (
    REFERENCE_METHOD_IDS,
    ImmutableVersionError,
    Mapping,
    MappingAlreadyExistsError,
    MappingEntry,
    PresetNotFoundError,
    VersionState,
    Workflow,
    WorkflowNotFoundError,
    WorkflowNotRunnableError,
    WorkflowDomainValidationError,
    WorkflowPreset,
    WorkflowVersion,
    WorkflowVersionNotFoundError,
    build_studio_references_companion,
    make_mapping_id,
    make_preset_id,
    make_version_id,
    make_workflow_id,
    normalize_reference_bindings,
    now_iso,
)
from .preset_state import (
    compute_mapping_fingerprint,
    normalize_preset_metadata,
    normalize_studio_state,
)
from .store import WorkflowDomainStore

# Fields a client may edit on each entity.
_WORKFLOW_EDITABLE = {
    "name", "description", "folder", "tags", "favorite",
    "source_url", "source_author", "compatible_models",
}

# The wrapper configuration is kept on the Workflow record itself.  These
# names are intentionally boring: they are the durable contract shared by
# autosave, run-context, and portability adapters.
WORKFLOW_CONFIG_FIELDS = frozenset({
    "static_graph",
    "bindings",
    "output_binding",
    "workflow_type",
    "saved_values",
    "layout_profile",
    "allowed_options",
})
WORKFLOW_CONFIG_ALIASES = {
    "graph": "static_graph",
    "type": "workflow_type",
    "output": "output_binding",
    "layout": "layout_profile",
    "field_values": "saved_values",
    "values": "saved_values",
    "allowed_options_filters": "allowed_options",
}
EXPERIMENT_ONLY_FIELDS = frozenset({
    "selected_workflows", "workflow_ids", "axes", "value_pills",
    "experiment_values", "experiment_draft", "run_history", "generated_images",
})


def _normalize_folder_path(value: Any, *, allow_empty: bool = False) -> str:
    if value is None and allow_empty:
        return ""
    if not isinstance(value, str):
        raise WorkflowDomainValidationError("folder path must be a string")
    path = value.strip().strip("/")[:500]
    if not path and not allow_empty:
        raise WorkflowDomainValidationError("folder path is required")
    return path

# Code-owned catalog/profile.  UI code may project these records into blocks,
# but users cannot redefine their type or binding semantics.  The keys are
# product API; graph-specific legacy role names are adapted only at the
# internal Mapping compatibility seam below.
_IMAGE_TYPES = ("t2i", "i2i", "inpaint", "sketch", "outpaint")
_EXACT_BINDING = {"kind": "widget", "exact": True, "cardinality": "one"}
BINDABLE_INPUT_CATALOG: dict[str, dict[str, Any]] = {
    "prompt": {"key": "prompt", "name": "Prompt", "block": "multiline",
               "input_kind": "multiline", "required_for": _IMAGE_TYPES,
               "optional_for": (), "experiment_eligible": True,
               "rules": {"multiline": True}, "binding": _EXACT_BINDING},
    "seed": {"key": "seed", "name": "Seed", "block": "integer",
             "input_kind": "integer", "required_for": _IMAGE_TYPES,
             "optional_for": (), "experiment_eligible": True,
             "rules": {"minimum": None, "allow_negative": True},
             "binding": _EXACT_BINDING},
    "step_count": {"key": "step_count", "name": "Step count", "block": "integer",
                    "input_kind": "integer", "required_for": (),
                    "optional_for": _IMAGE_TYPES, "experiment_eligible": True,
                    "rules": {"minimum": 1, "step": 1, "allow_negative": False},
                    "binding": _EXACT_BINDING},
    "cfg_scale": {"key": "cfg_scale", "name": "CFG scale", "block": "float",
                   "input_kind": "float", "required_for": (),
                   "optional_for": _IMAGE_TYPES, "experiment_eligible": True,
                   "rules": {"minimum": 0, "allow_negative": False},
                   "binding": _EXACT_BINDING},
    "sampler": {"key": "sampler", "name": "Sampler", "block": "dropdown",
                 "input_kind": "dropdown", "required_for": (),
                 "optional_for": _IMAGE_TYPES, "experiment_eligible": True,
                 "rules": {}, "binding": _EXACT_BINDING},
    "width": {"key": "width", "name": "Width", "block": "integer",
               "input_kind": "integer", "required_for": (),
               "optional_for": _IMAGE_TYPES, "experiment_eligible": True,
               "rules": {"minimum": 64, "maximum": 4096, "step": 8,
                         "allow_negative": False}, "binding": _EXACT_BINDING},
    "height": {"key": "height", "name": "Height", "block": "integer",
                "input_kind": "integer", "required_for": (),
                "optional_for": _IMAGE_TYPES, "experiment_eligible": True,
                "rules": {"minimum": 64, "maximum": 4096, "step": 8,
                          "allow_negative": False}, "binding": _EXACT_BINDING},
    "model_unet": {"key": "model_unet", "name": "Model UNET", "block": "model-picker",
                    "input_kind": "model", "required_for": _IMAGE_TYPES,
                    "optional_for": (), "experiment_eligible": True,
                    "rules": {"model_type": "unet"}, "binding": _EXACT_BINDING},
    "vae": {"key": "vae", "name": "VAE", "block": "model-picker",
            "input_kind": "model", "required_for": _IMAGE_TYPES,
            "optional_for": (), "experiment_eligible": True,
            "rules": {"model_type": "vae"}, "binding": _EXACT_BINDING},
    "clip": {"key": "clip", "name": "CLIP", "block": "model-picker",
             "input_kind": "model", "required_for": _IMAGE_TYPES,
             "optional_for": (), "experiment_eligible": True,
             "rules": {"model_type": "clip"}, "binding": _EXACT_BINDING},
    "source_image": {"key": "source_image", "name": "Source Image", "block": "image",
                     "input_kind": "image",
                     "required_for": ("i2i", "inpaint", "sketch", "outpaint"),
                     "optional_for": (), "experiment_eligible": False,
                     "rules": {}, "binding": _EXACT_BINDING},
    "mask": {"key": "mask", "name": "Mask", "block": "image",
             "input_kind": "image", "required_for": ("inpaint",),
             "optional_for": ("i2i", "sketch", "outpaint"), "experiment_eligible": False,
             "rules": {}, "binding": _EXACT_BINDING},
}
T2I_REQUIRED_INPUTS = ("prompt", "seed", "model_unet", "vae", "clip")
T2I_OPTIONAL_INPUTS = ("step_count", "cfg_scale", "sampler", "width", "height")
I2I_REQUIRED_INPUTS = ("prompt", "seed", "model_unet", "vae", "clip", "source_image")
I2I_OPTIONAL_INPUTS = ("step_count", "cfg_scale", "sampler", "width", "height", "mask")
INPAINT_REQUIRED_INPUTS = ("prompt", "seed", "model_unet", "vae", "clip", "source_image", "mask")
INPAINT_OPTIONAL_INPUTS = ("step_count", "cfg_scale", "sampler", "width", "height")
SKETCH_REQUIRED_INPUTS = ("prompt", "seed", "model_unet", "vae", "clip", "source_image")
SKETCH_OPTIONAL_INPUTS = ("step_count", "cfg_scale", "sampler", "width", "height", "mask")
OUTPAINT_REQUIRED_INPUTS = ("prompt", "seed", "model_unet", "vae", "clip", "source_image")
OUTPAINT_OPTIONAL_INPUTS = ("step_count", "cfg_scale", "sampler", "width", "height", "mask")
OUTPUT_BINDING = {"key": "output", "name": "Output", "block": None,
                  "required_for": _IMAGE_TYPES,
                  "binding": {"kind": "output", "exact": True, "cardinality": "one"}}
_ROLE_ALIASES = {
    "positive_prompt": "prompt", "steps": "step_count", "cfg": "cfg_scale",
    "model": "model_unet", "unet": "model_unet",
}
WORKFLOW_TYPE_PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "t2i": {
        "required": T2I_REQUIRED_INPUTS,
        "optional": T2I_OPTIONAL_INPUTS,
    },
    "i2i": {
        "required": I2I_REQUIRED_INPUTS,
        "optional": I2I_OPTIONAL_INPUTS,
    },
    "inpaint": {
        "required": INPAINT_REQUIRED_INPUTS,
        "optional": INPAINT_OPTIONAL_INPUTS,
    },
    "sketch": {
        "required": SKETCH_REQUIRED_INPUTS,
        "optional": SKETCH_OPTIONAL_INPUTS,
    },
    "outpaint": {
        "required": OUTPAINT_REQUIRED_INPUTS,
        "optional": OUTPAINT_OPTIONAL_INPUTS,
    },
}
# Canonical workflow-type spellings for durable storage. Aliases resolve to
# the canonical key wherever workflow types are normalized.
WORKFLOW_TYPE_ALIASES = {
    "txt2img": "t2i",
    "text_to_image": "t2i",
    "img2img": "i2i",
    "image_to_image": "i2i",
    "image_edit": "i2i",
}


def normalize_workflow_type(value: Any) -> str:
    """Resolve a workflow-type string to its canonical spelling."""
    raw = str(value or "").strip().lower()
    if not raw:
        return "t2i"
    return WORKFLOW_TYPE_ALIASES.get(raw, raw)


class WorkflowDomainService:
    def __init__(
        self,
        root: str,
        dependency_provider: Optional[Callable[[dict[str, Any]], list[str]]] = None,
        node_def_provider: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.store = WorkflowDomainStore(root)
        # Optional callable(version_dict) -> list[str] feeding extra reasons
        # into derived version state (e.g. dependency resolution).  Must never
        # raise — any exception is swallowed by derive_version_state.
        self._dependency_provider = dependency_provider
        # Optional callable(class_type) -> (required, optional) node-def
        # pair used for UI-format graph conversion at import time.  Defaults
        # to the lazy ComfyUI registry probe inside ui_graph_to_api_prompt.
        self._node_def_provider = node_def_provider

    # ── value validation helpers ─────────────────────────────────────────

    @staticmethod
    def _validate_value(role: str, value: Any, entry: MappingEntry) -> Optional[str]:
        """Return an error message for an invalid value, or None.

        ``None`` is handled by callers (missing-value logic); 0/False/0.0/""
        are always valid for their kind.
        """
        kind = entry.control_kind
        if kind == "enum":
            # Source Image / Mask reference files by name and the input
            # directory changes on every upload: a captured directory
            # snapshot is never a closed vocabulary (see studio_workflow_run).
            if role in ("source_image", "mask"):
                return None
            if value not in entry.enum_options:
                return (
                    f"invalid value {value!r} for {role!r}, "
                    f"must be one of: {', '.join(str(o) for o in entry.enum_options)}"
                )
            return None
        if kind == "boolean":
            if isinstance(value, bool) or value in (0, 1):
                return None
            return f"invalid value {value!r} for {role!r}, must be a boolean"
        if kind == "integer":
            if isinstance(value, int) and not isinstance(value, bool):
                if entry.minimum is not None and value < entry.minimum:
                    return f"value {value!r} for {role!r} must be >= {entry.minimum}"
                if entry.maximum is not None and value > entry.maximum:
                    return f"value {value!r} for {role!r} must be <= {entry.maximum}"
                return None
            return f"invalid value {value!r} for {role!r}, must be an integer"
        if kind == "number":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if entry.minimum is not None and value < entry.minimum:
                    return f"value {value!r} for {role!r} must be >= {entry.minimum}"
                if entry.maximum is not None and value > entry.maximum:
                    return f"value {value!r} for {role!r} must be <= {entry.maximum}"
                return None
            return f"invalid value {value!r} for {role!r}, must be a number"
        if kind in ("string", "multiline"):
            if isinstance(value, str):
                return None
            return f"invalid value {value!r} for {role!r}, must be a string"
        return None  # file/image/node: accept any non-None value


    @staticmethod
    def _normalize_entries(entries: dict[str, dict[str, Any]]) -> dict[str, MappingEntry]:
        entry_objects: dict[str, MappingEntry] = {}
        for role, raw in entries.items():
            entry = MappingEntry.from_dict(raw)
            entry.semantic_role = role
            entry_objects[role] = entry
        return entry_objects

    @staticmethod
    def normalize_output_node_id(
        output_node_id: Any,
        executable: dict[str, Any],
        ui_graph: Any,
    ) -> str:
        """Normalize a wizard output node id to its executable prompt key.

        Expanded subgraph ids (``"30:8"``) pass through; outer containers
        (``"30"``) and inner-local ids (``"10"``) resolve to their expanded
        key when unambiguous. Returns "" when unresolvable. Never raises.
        """
        try:
            oid = str(output_node_id or "")
            if not oid:
                return ""
            if isinstance(executable, dict) and oid in executable:
                return oid
            resolved = subgraph_resolve_output(executable, ui_graph, oid)
            return str(resolved or "")
        except Exception:
            return ""

    def _validate_entries_against_graph(
        self,
        entries: dict[str, MappingEntry],
        version: dict[str, Any],
    ) -> None:
        """Reject input bindings that cannot resolve against the version's
        graph — fail fast at save time instead of at run-gating time.

        Every entry whose kind binds a node input must name an
        ``input_name`` present in that node's executable ``inputs`` (the
        single location gating and execution read and write). A name that
        exists only as node-def or UI-widget state (e.g. a pure-widget or
        hidden-state value that never reaches the executable prompt) is
        rejected with resolvable alternatives, so an un-runnable mapping
        like ``seed`` → a seed-producer node can never be stored.

        Subgraph workflows expand inner nodes to ``"<outer>:<inner>"`` prompt
        keys while the wizard captures UI ids (outer ``"30"`` or inner-local
        ``"10"``). Resolvable subgraph bindings are normalized in place to
        their expanded executable target so the stored mapping runs
        unchanged downstream.
        """
        executable = version.get("executable_prompt") or {}
        ui_graph = version.get("graph_json")
        problems: list[str] = []
        for role, entry in entries.items():
            if entry.kind == "node_output":
                # Mapping entries bind controls to node inputs/widgets; the
                # workflow output travels separately as output_node_id. An
                # output binding can never receive a control value and fails
                # at run time with "no node/input binding", so reject it
                # here at save time with an actionable message.
                problems.append(
                    f"binding {role!r} must name one concrete node input/widget, "
                    "not a node output; re-bind it to the input field that "
                    "consumes the value"
                )
                continue
            if entry.kind not in INPUT_BINDING_KINDS:
                continue
            node_id = str(entry.node_id or "")
            input_name = str(entry.input_name or "")
            if not node_id or not input_name:
                problems.append(
                    f"binding {role!r} must name one concrete node input/widget"
                )
                continue
            target = resolve_binding_target(
                executable,
                node_id,
                input_name,
                ui_graph=ui_graph,
                node_def_provider=self._node_def_provider,
            )
            if target.get("resolvable"):
                expanded_id = target.get("expanded_node_id")
                expanded_input = target.get("expanded_input_name")
                if expanded_id and expanded_input:
                    entry.node_id = str(expanded_id)
                    entry.input_name = str(expanded_input)
                continue
            if not target.get("node_present"):
                candidates = target.get("subgraph_candidates")
                if isinstance(candidates, list) and candidates:
                    problems.append(
                        f"mapped entry {role!r} node {node_id} is ambiguous "
                        f"across subgraphs (matches {', '.join(candidates)}); "
                        f"bind the outer subgraph widget or re-capture the "
                        f"expanded node id"
                    )
                else:
                    problems.append(
                        f"mapped entry {role!r} node {node_id} not present in graph"
                    )
                continue
            message = (
                f"mapped entry {role!r} input {input_name!r} "
                f"not present on node {node_id}"
            )
            location = target.get("location")
            if location in ("node_def", "ui_widget"):
                message += (
                    " (found only as widget/hidden state, not as an "
                    "executable input; bind the downstream consumer input instead)"
                )
            candidates = find_binding_candidates(
                executable,
                input_name,
                ui_graph=ui_graph,
                node_def_provider=self._node_def_provider,
            )
            executable_hits = [c for c in candidates if c.get("via") == "inputs"]
            if executable_hits:
                hints = ", ".join(
                    f"node {c['node_id']} input {c['input_name']!r}"
                    + (f" (linked to node {c['upstream_node_id']})" if c.get("linked") else "")
                    for c in executable_hits
                )
                message += f"; resolvable bindings for {input_name!r}: {hints}"
            problems.append(message)
        if problems:
            raise WorkflowDomainValidationError("; ".join(problems))

    @staticmethod
    def _normalize_text_generate_node_id(value: Any) -> Optional[str]:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise WorkflowDomainValidationError(
                "text_generate_node_id must be a string or null"
            )
        return value

    @staticmethod
    def _references_output(value: Any, node_id: str, output_index: Optional[int] = None) -> bool:
        """Return whether *value* contains a ComfyUI output connection."""
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                if str(value[0]) == node_id and (
                    output_index is None or value[1] == output_index
                ):
                    return True
            except Exception:
                pass
        if isinstance(value, dict):
            return any(
                WorkflowDomainService._references_output(item, node_id, output_index)
                for item in value.values()
            )
        if isinstance(value, (list, tuple)):
            return any(
                WorkflowDomainService._references_output(item, node_id, output_index)
                for item in value
            )
        return False

    def _validate_text_generate_binding(
        self, node_id: Optional[str], version: dict[str, Any]
    ) -> Optional[str]:
        """Validate the optional bypass target against the stored executable graph."""
        if node_id is None:
            return None
        executable = version.get("executable_prompt") or {}
        node = executable.get(node_id) if isinstance(executable, dict) else None
        if not isinstance(node, dict):
            raise WorkflowDomainValidationError(
                f"text_generate_node_id {node_id!r} is not present in the executable prompt"
            )
        class_type = str(node.get("class_type", ""))
        if class_type not in {"TextGenerate", "TextGenerateLTX2Prompt"}:
            raise WorkflowDomainValidationError(
                "text_generate_node_id must target TextGenerate or TextGenerateLTX2Prompt"
            )
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or "prompt" not in inputs:
            raise WorkflowDomainValidationError(
                f"TextGenerate node {node_id!r} has no executable prompt input"
            )
        declared_outputs = next(
            (node.get(key) for key in ("return_types", "output_types", "outputs")
             if node.get(key) is not None),
            None,
        )
        if declared_outputs is not None:
            first = declared_outputs[0] if isinstance(declared_outputs, (list, tuple)) and declared_outputs else None
            first_type = first.get("type") if isinstance(first, dict) else first
            first_name = first.get("name") if isinstance(first, dict) else None
            if str(first_type or "").upper() not in {"STRING", "STR"} or (
                first_name is not None and str(first_name) != "generated_text"
            ):
                raise WorkflowDomainValidationError(
                    f"TextGenerate node {node_id!r} output slot 0 is not generated text"
                )
        # The two authoritative ComfyUI classes expose generated text at slot 0.
        # A secondary output is safe only when the graph does not consume it;
        # otherwise removing the node would silently change another input.
        for other_id, other in executable.items():
            if isinstance(other, dict) and self._references_output(
                other.get("inputs"), node_id, 1
            ):
                raise WorkflowDomainValidationError(
                    f"TextGenerate node {node_id!r} has a consumed secondary output; "
                    "it cannot be bypassed"
                )
        return node_id

    # ── References (Phase 8, Lane A) ────────────────────────────────────

    def get_reference_candidates(
        self, workflow_version_id: str
    ) -> dict[str, Any]:
        """Structural reference candidates for one version's stored graph.

        Reuses subgraph expansion + target resolution via
        :func:`discover_reference_candidates` over the version's executable
        prompt, installed node schemas, selected output upstream graph, and
        existing prompt/source-image mappings. Never raises.
        """
        version = self.store.get_version(workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        executable = version.get("executable_prompt") or {}
        ui_graph = version.get("graph_json")
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        prompt_bindings: dict[str, Any] = {}
        output_node_id = ""
        try:
            if isinstance(mapping, dict):
                for raw in mapping.get("entries") or []:
                    if not isinstance(raw, dict):
                        continue
                    role = str(raw.get("semantic_role", ""))
                    if role in ("positive_prompt", "prompt", "source_image", "mask"):
                        prompt_bindings[role if role != "positive_prompt" else "prompt"] = {
                            "node_id": str(raw.get("node_id", "")),
                            "input_name": str(raw.get("input_name", "")),
                        }
                output_node_id = str(mapping.get("output_node_id", "") or "")
        except Exception:
            pass
        if not output_node_id:
            try:
                output_node_id = str(version.get("output_node_id", "") or "")
            except Exception:
                output_node_id = ""
        return discover_reference_candidates(
            executable,
            ui_graph=ui_graph,
            node_def_provider=self._node_def_provider,
            output_node_id=output_node_id,
            prompt_bindings=prompt_bindings,
        )

    def _validate_reference_bindings(
        self,
        reference_method: Any,
        reference_bindings: Any,
        version: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Validate version-bound reference bindings against the graph.

        Fail-closed: unknown methods, stale nodes/sockets (including
        subgraph-ambiguous bindings), and Method-2 chains outside the
        evidenced segment are rejected. Returns ``(method, normalized)``.
        """
        method, normalized, problems = normalize_reference_bindings(
            reference_method, reference_bindings
        )
        if problems:
            raise WorkflowDomainValidationError("; ".join(problems))
        if not method:
            return "", {}
        if method not in REFERENCE_METHOD_IDS:
            raise WorkflowDomainValidationError(
                f"unknown reference method {method!r}"
            )
        executable = version.get("executable_prompt") or {}
        ui_graph = version.get("graph_json")
        discovery = discover_reference_candidates(
            executable,
            ui_graph=ui_graph,
            node_def_provider=self._node_def_provider,
            prompt_bindings=None,
        )
        by_id = {
            str(c.get("candidate_id", "")): c
            for c in discovery.get("candidates", [])
            if isinstance(c, dict)
        }
        errors: list[str] = []
        if method == "dedicated":
            target = str(normalized.get("dedicated_target", "") or "")
            if not target:
                raise WorkflowDomainValidationError(
                    "dedicated reference method requires a dedicated target"
                )
            if node_exists(executable, target) or subgraph_node_present(
                executable, ui_graph, target
            ):
                return method, normalized
            # A dedicated target may also be a stored workflow (selected
            # explicitly through the workflow picker); the run path resolves
            # and freezes its version at acceptance. Anything else stays
            # rejected — never a guessed node.
            try:
                stored = self.store.get_workflow(target)
            except Exception:
                stored = None
            if isinstance(stored, dict) and stored:
                return method, normalized
            raise WorkflowDomainValidationError(
                f"dedicated reference target node {target} not present in graph"
            )
        candidate_id = str(normalized.get("candidate_id", "") or "")
        if method == "conditioning_slots":
            slots = normalized.get("slots", [])
            if not isinstance(slots, list) or not slots:
                raise WorkflowDomainValidationError(
                    "conditioning_slots requires at least one reference slot"
                )
            # Multi-candidate confirmation: an explicit candidate pick is
            # required whenever discovery is ambiguous.
            if len(discovery.get("candidates", [])) > 1 and not candidate_id:
                raise WorkflowDomainValidationError(
                    "multiple reference candidates evidenced; "
                    "confirm one conditioning candidate before saving"
                )
            candidate = by_id.get(candidate_id) if candidate_id else None
            if candidate_id and candidate is None:
                raise WorkflowDomainValidationError(
                    f"reference candidate {candidate_id!r} is not evidenced on this version"
                )
            evidenced_slots: dict[tuple[str, str], dict[str, Any]] = {}
            if isinstance(candidate, dict):
                for slot in candidate.get("slots", []) or []:
                    if isinstance(slot, dict) and slot.get("node_id") and slot.get("socket"):
                        evidenced_slots[(str(slot["node_id"]), str(slot["socket"]))] = slot
            for slot in slots:
                nid = str(slot.get("node_id", ""))
                socket = str(slot.get("socket", ""))
                kind = str(slot.get("kind", "reference"))
                if kind == "source":
                    continue
                ev_slot = evidenced_slots.get((nid, socket)) if evidenced_slots else None
                if isinstance(ev_slot, dict):
                    # The candidate already evidenced this slot: a required
                    # slot must be wired, while an optional one may bind an
                    # isolated loader branch at run time (discovery marks it
                    # writable). Trust that evidence instead of re-resolving.
                    if bool(ev_slot.get("required")) and not bool(ev_slot.get("resolvable")):
                        errors.append(
                            f"reference slot socket {socket!r} on node {nid} "
                            "is required but has no resolvable binding path"
                        )
                    continue
                target = resolve_binding_target(
                    executable, nid, socket, ui_graph=ui_graph,
                    node_def_provider=self._node_def_provider,
                )
                if target.get("subgraph_candidates"):
                    errors.append(
                        f"reference slot node {nid} socket {socket!r} is ambiguous "
                        "across subgraphs; bind the outer subgraph widget"
                    )
                elif not target.get("resolvable"):
                    if not target.get("node_present"):
                        errors.append(
                            f"reference slot node {nid} not present in graph"
                        )
                    else:
                        errors.append(
                            f"reference slot socket {socket!r} not present on node {nid}"
                        )
                elif evidenced_slots and (nid, socket) not in evidenced_slots:
                    errors.append(
                        f"reference slot {socket!r} on node {nid} is outside the "
                        f"confirmed candidate {candidate_id!r} slot order"
                    )
            if errors:
                raise WorkflowDomainValidationError("; ".join(errors))
            return method, normalized
        # reference_latent_chain
        chain = normalized.get("chain", {})
        if not isinstance(chain, dict) or not chain:
            raise WorkflowDomainValidationError(
                "reference_latent_chain requires a chain boundary"
            )
        ref_id = str(chain.get("reference_latent_node_id", "") or "")
        if not ref_id:
            raise WorkflowDomainValidationError(
                "reference_latent_chain requires a reference latent node"
            )
        evidenced = None
        for cand in discovery.get("candidates", []) or []:
            if not isinstance(cand, dict):
                continue
            if cand.get("method") != "reference_latent_chain":
                continue
            cand_chain = cand.get("chain", {}) if isinstance(cand.get("chain"), dict) else {}
            if str(cand_chain.get("reference_latent_node_id", "")) == ref_id:
                evidenced = cand
                break
        if evidenced is None:
            raise WorkflowDomainValidationError(
                f"reference latent chain at node {ref_id} is not evidenced; "
                "generic workflow without the chain pattern is incompatible"
            )
        cand_chain = evidenced.get("chain", {})
        for key in ("loader_node_id", "vae_encode_node_id", "reference_latent_node_id"):
            want = str(cand_chain.get(key, "") or "")
            got = str(chain.get(key, "") or "")
            if want and got and want != got:
                errors.append(
                    f"chain boundary {key} {got!r} does not match evidenced {want!r}"
                )
        if errors:
            raise WorkflowDomainValidationError("; ".join(errors))
        return method, normalized

    def build_studio_references(
        self, workflow_version_id: str
    ) -> dict[str, Any]:
        """Top-level ``studio_references`` run companion for one version.

        Explicit method, origin workflow/version, dedicated target where
        applicable, ordered card ids, server image refs (empty until the
        run attaches uploads), and source provenance. No client graph
        patches. Never raises for missing bindings (returns unbound).
        """
        version = self.store.get_version(workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        method = ""
        bindings: dict[str, Any] = {}
        try:
            if isinstance(mapping, dict):
                method = str(mapping.get("reference_method", "") or "")
                raw = mapping.get("reference_bindings")
                if isinstance(raw, dict):
                    bindings = raw
        except Exception:
            pass
        return build_studio_references_companion(
            method=method,
            origin_workflow_id=str(version.get("workflow_id", "") or ""),
            origin_version_id=str(version.get("workflow_version_id", "") or ""),
            bindings=bindings,
        )

    # ── Workflow ─────────────────────────────────────────────────────────

    def create_workflow(
        self,
        name: str,
        *,
        description: str = "",
        folder: str = "",
        tags: Optional[list[str]] = None,
        favorite: bool = False,
        source_url: str = "",
        source_author: str = "",
        compatible_models: Optional[list[str]] = None,
        workflow_type: str = "t2i",
        static_graph: Optional[dict[str, Any]] = None,
        bindings: Optional[dict[str, Any]] = None,
        output_binding: Optional[dict[str, Any]] = None,
        saved_values: Optional[dict[str, Any]] = None,
        layout_profile: Optional[dict[str, Any]] = None,
        allowed_options: Optional[dict[str, Any]] = None,
        require_complete: bool = False,
        **aliases: Any,
    ) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise WorkflowDomainValidationError("workflow name is required")
        for key, value in aliases.items():
            canonical = WORKFLOW_CONFIG_ALIASES.get(key)
            if canonical is None:
                raise WorkflowDomainValidationError(
                    f"field {key!r} is not editable on a workflow"
                )
            if canonical == "static_graph" and static_graph is None:
                static_graph = value
            elif canonical == "workflow_type" and workflow_type == "t2i":
                workflow_type = value
            elif canonical == "saved_values" and saved_values is None:
                saved_values = value
            elif canonical == "layout_profile" and layout_profile is None:
                layout_profile = value
            elif canonical == "allowed_options" and allowed_options is None:
                allowed_options = value
        now = now_iso()
        workflow = Workflow(
            workflow_id=make_workflow_id(),
            name=name.strip()[:200],
            description=(description or "")[:2000],
            folder=_normalize_folder_path(folder, allow_empty=True),
            tags=list(tags or []),
            favorite=bool(favorite),
            source_url=(source_url or "")[:2000],
            source_author=(source_author or "")[:500],
            compatible_models=list(compatible_models or []),
            created_at=now,
            updated_at=now,
        )
        config = self._normalize_workflow_config(
            {
                "workflow_type": workflow_type,
                "static_graph": static_graph if static_graph is not None else {},
                "bindings": bindings if bindings is not None else {},
                "output_binding": output_binding if output_binding is not None else {},
                "saved_values": saved_values if saved_values is not None else {},
                "layout_profile": layout_profile if layout_profile is not None else {},
                "allowed_options": allowed_options if allowed_options is not None else {},
            },
            require_complete=require_complete,
        )
        return self.store.insert_workflow(workflow, config)

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        return workflow

    def list_workflows(self) -> list[dict[str, Any]]:
        return self.store.list_workflows()

    def delete_workflow(self, workflow_id: str) -> None:
        """Delete a Workflow and all of its dependent records."""
        if self.store.get_workflow(workflow_id) is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        self.store.delete_workflow(workflow_id)

    def update_workflow(self, workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
        raw = self.store.get_workflow(workflow_id)
        if raw is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        if not isinstance(body, dict):
            raise WorkflowDomainValidationError("workflow update must be an object")
        if "require_complete" in body:
            raise WorkflowDomainValidationError("require_complete is not a saved field")
        normalized_config = self._workflow_config_updates(raw, body)
        metadata = {key: value for key, value in body.items()
                    if key not in WORKFLOW_CONFIG_FIELDS and key not in WORKFLOW_CONFIG_ALIASES}
        workflow = Workflow.from_dict(raw)
        for key in metadata:
            if key not in _WORKFLOW_EDITABLE:
                raise WorkflowDomainValidationError(
                    f"field {key!r} is not editable on a workflow"
                )
        if "name" in metadata:
            if not isinstance(metadata["name"], str) or not metadata["name"].strip():
                raise WorkflowDomainValidationError("workflow name is required")
            workflow.name = metadata["name"].strip()[:200]
        if "description" in metadata:
            workflow.description = (metadata["description"] or "")[:2000]
        if "folder" in metadata:
            workflow.folder = _normalize_folder_path(metadata["folder"], allow_empty=True)
        if "tags" in metadata:
            if not isinstance(metadata["tags"], list):
                raise WorkflowDomainValidationError("tags must be a list of strings")
            workflow.tags = [t for t in metadata["tags"] if isinstance(t, str)]
        if "favorite" in metadata:
            workflow.favorite = bool(metadata["favorite"])
        if "source_url" in metadata:
            workflow.source_url = (metadata["source_url"] or "")[:2000]
        if "source_author" in metadata:
            workflow.source_author = (metadata["source_author"] or "")[:500]
        if "compatible_models" in metadata:
            if not isinstance(metadata["compatible_models"], list):
                raise WorkflowDomainValidationError(
                    "compatible_models must be a list of strings"
                )
            workflow.compatible_models = [
                m for m in metadata["compatible_models"] if isinstance(m, str)
            ]
        workflow.updated_at = now_iso()
        if normalized_config:
            # Keep the compatibility dataclass and wrapper fields in one
            # atomic read-modify-write operation.
            fields = workflow.to_dict()
            fields.update(normalized_config)
            return self.store.update_workflow_fields(workflow_id, fields)
        return self.store.update_workflow(workflow)

    @staticmethod
    def _normalize_binding_map(bindings: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(bindings, dict):
            raise WorkflowDomainValidationError("bindings must be an object")
        normalized: dict[str, dict[str, Any]] = {}
        targets: set[tuple[str, str, str]] = set()
        for role, raw in bindings.items():
            if not isinstance(role, str) or not role.strip():
                raise WorkflowDomainValidationError("binding roles must be non-empty strings")
            canonical_role = _ROLE_ALIASES.get(role, role)
            if canonical_role not in BINDABLE_INPUT_CATALOG:
                raise WorkflowDomainValidationError(
                    f"binding {role!r} is not a supported bindable input"
                )
            if not isinstance(raw, dict):
                raise WorkflowDomainValidationError(f"binding {role!r} must be an object")
            item = copy.deepcopy(raw)
            node_id = str(item.get("node_id") or item.get("nodeId") or "")
            input_name = str(
                item.get("input_name")
                or item.get("inputName")
                or item.get("widget_name")
                or item.get("widget")
                or ""
            )
            output_name = str(item.get("output_name") or item.get("outputName") or "")
            if not node_id or (not input_name and not output_name):
                raise WorkflowDomainValidationError(
                    f"binding {role!r} must name one concrete node input/widget or output"
                )
            target = (node_id, input_name, output_name)
            if target in targets:
                raise WorkflowDomainValidationError(
                    f"binding {role!r} duplicates node/widget binding {target!r}"
                )
            targets.add(target)
            item["node_id"] = node_id
            if input_name:
                item["input_name"] = input_name
            if canonical_role in normalized:
                raise WorkflowDomainValidationError(
                    f"binding {role!r} duplicates role {canonical_role!r}"
                )
            normalized[canonical_role] = item
        return normalized

    @classmethod
    def _normalize_workflow_config(
        cls, fields: dict[str, Any], *, require_complete: bool = False
    ) -> dict[str, Any]:
        workflow_type = fields.get("workflow_type", "t2i")
        if not isinstance(workflow_type, str) or not workflow_type.strip():
            raise WorkflowDomainValidationError("workflow_type must be a non-empty string")
        workflow_type = normalize_workflow_type(workflow_type)
        graph = fields.get("static_graph", {})
        if not isinstance(graph, dict):
            raise WorkflowDomainValidationError("static_graph must be an object")
        bindings = cls._normalize_binding_map(fields.get("bindings", {}))
        output = fields.get("output_binding", {})
        if not isinstance(output, dict):
            raise WorkflowDomainValidationError("output_binding must be an object")
        output = copy.deepcopy(output)
        if output:
            output["node_id"] = str(
                output.get("node_id")
                or output.get("nodeId")
                or output.get("output_node_id")
                or ""
            )
            if not output["node_id"]:
                raise WorkflowDomainValidationError("output_binding must name a concrete node")
        values = fields.get("saved_values", {})
        if not isinstance(values, dict):
            raise WorkflowDomainValidationError("saved_values must be an object")
        values = copy.deepcopy(values)
        allowed = fields.get("allowed_options", {})
        if not isinstance(allowed, dict):
            raise WorkflowDomainValidationError("allowed_options must be an object")
        allowed = copy.deepcopy(allowed)
        for role, options in allowed.items():
            if not isinstance(options, list):
                raise WorkflowDomainValidationError(
                    f"allowed_options[{role!r}] must be a list"
                )
            if role in values and values[role] is not None and values[role] not in options:
                raise WorkflowDomainValidationError(
                    f"saved value for {role!r} is outside its allowed options"
                )
        layout = fields.get("layout_profile", {})
        if not isinstance(layout, dict):
            raise WorkflowDomainValidationError("layout_profile must be an object")
        result = {
            "static_graph": copy.deepcopy(graph),
            "bindings": bindings,
            "output_binding": output,
            "workflow_type": workflow_type,
            "saved_values": values,
            "layout_profile": copy.deepcopy(layout),
            "allowed_options": allowed,
        }
        if require_complete:
            profile = WORKFLOW_TYPE_PROFILES.get(workflow_type, {})
            missing = []
            for role in profile.get("required", ()):
                if role in bindings:
                    continue
                # ``model`` is the legacy graph semantic role; the wrapper
                # catalog names the same required component Model UNET.
                if role == "model" and ({"model_unet", "unet"} & bindings.keys()):
                    continue
                missing.append(role)
            if output.get("node_id") == "":
                missing.append("output")
            if missing:
                raise WorkflowDomainValidationError(
                    "workflow is missing required bindings: " + ", ".join(missing)
                )
        return result

    def _workflow_config_updates(
        self, raw: dict[str, Any], body: dict[str, Any]
    ) -> dict[str, Any]:
        forbidden = EXPERIMENT_ONLY_FIELDS.intersection(body)
        if forbidden:
            raise WorkflowDomainValidationError(
                "experiment-only fields are not durable Workflow config: "
                + ", ".join(sorted(forbidden))
            )
        supplied: dict[str, Any] = {}
        for key, value in body.items():
            canonical = WORKFLOW_CONFIG_ALIASES.get(key, key)
            if canonical in WORKFLOW_CONFIG_FIELDS:
                supplied[canonical] = value
        if not supplied:
            return {}
        merged = {field: copy.deepcopy(raw.get(field, default)) for field, default in (
            ("workflow_type", "t2i"), ("static_graph", {}), ("bindings", {}),
            ("output_binding", {}), ("saved_values", {}), ("layout_profile", {}),
            ("allowed_options", {}),
        )}
        merged.update(supplied)
        return self._normalize_workflow_config(
            merged, require_complete=bool(body.get("require_complete", False))
        )

    def autosave_workflow(
        self, workflow_id: str, body: dict[str, Any], *, require_complete: bool = False
    ) -> dict[str, Any]:
        """Durably save normal Workflow content/layout; never experiment state."""
        if not isinstance(body, dict):
            raise WorkflowDomainValidationError("workflow autosave must be an object")
        raw = self.store.get_workflow(workflow_id)
        if raw is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        fields = self._workflow_config_updates(raw, body)
        if not fields:
            raise WorkflowDomainValidationError("autosave requires Workflow config fields")
        if require_complete:
            fields = self._normalize_workflow_config(fields, require_complete=True)
        fields["updated_at"] = now_iso()
        return self.store.update_workflow_fields(workflow_id, fields)

    def save_workflow_config(
        self, workflow_id: str, config: dict[str, Any], *, require_complete: bool = False
    ) -> dict[str, Any]:
        """Named API alias for callers that do not model autosave as a route."""
        return self.autosave_workflow(
            workflow_id, config, require_complete=require_complete
        )

    def validate_workflow_config(self, workflow_id: str, *, require_complete: bool = False) -> dict[str, Any]:
        raw = self.get_workflow(workflow_id)
        config = self._normalize_workflow_config(
            {field: raw.get(field, default) for field, default in (
                ("workflow_type", "t2i"), ("static_graph", {}), ("bindings", {}),
                ("output_binding", {}), ("saved_values", {}), ("layout_profile", {}),
                ("allowed_options", {}),
            )},
            require_complete=require_complete,
        )
        return {"valid": True, "complete": bool(require_complete), "config": config}

    def get_workflow_config(self, workflow_id: str) -> dict[str, Any]:
        """Return only the durable wrapper configuration for one Workflow."""
        raw = self.get_workflow(workflow_id)
        defaults = {
            "workflow_type": "t2i", "static_graph": {}, "bindings": {},
            "output_binding": {}, "saved_values": {}, "layout_profile": {},
            "allowed_options": {},
        }
        return {
            field: copy.deepcopy(raw.get(field, default))
            for field, default in defaults.items()
        }

    def list_folders(self) -> list[str]:
        folders: set[str] = set()
        for record in self.store.list_folders():
            folder = record.get("path", "")
            if not isinstance(folder, str) or not folder:
                continue
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                folders.add("/".join(parts[:i]))
        for wf in self.store.list_workflows():
            folder = wf.get("folder", "")
            if not isinstance(folder, str) or not folder:
                continue
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                folders.add("/".join(parts[:i]))
        return sorted(folders)

    def create_folder(self, path: Any) -> list[str]:
        normalized = _normalize_folder_path(path)
        self.store.insert_folder(normalized)
        return self.list_folders()

    def list_tags(self) -> list[str]:
        tags: set[str] = set()
        for wf in self.store.list_workflows():
            tags.update(wf.get("tags") or [])
        return sorted(tags)

    # ── Workflow Version (immutable) ─────────────────────────────────────

    def create_version_from_capture(
        self, workflow_id: str, capture: dict[str, Any]
    ) -> dict[str, Any]:
        raw_workflow = self.store.get_workflow(workflow_id)
        if raw_workflow is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        capture = dict(capture or {})
        # File/canvas imports arrive as UI-format graphs (nodes list) with no
        # API prompt. Derive the executable prompt server-side (registry
        # probe) so candidates, dependency metadata, runnable state, and
        # future runs all see the same graph downstream consumers expect.
        graph_json = capture.get("graph_json") or {}
        if not capture.get("api_prompt_json") and is_ui_workflow_format(graph_json):
            derived = ui_graph_to_api_prompt(
                graph_json, node_def_provider=self._node_def_provider
            )
            if derived:
                capture["api_prompt_json"] = derived
        graph_hash = graph_hash_from_capture(capture)

        # Accidental duplicate capture: reuse the LATEST version with the
        # same graph hash (idempotent re-capture of an unchanged graph).
        existing = [
            v for v in self.store.list_versions_for_workflow(workflow_id)
            if v.get("graph_hash") == graph_hash
        ]
        if existing:
            existing.sort(
                key=lambda v: int(v.get("version_number", 0)), reverse=True
            )
            return self._enrich_version(existing[0])

        versions = self.store.list_versions_for_workflow(workflow_id)
        version_number = max(
            (int(v.get("version_number", 0)) for v in versions), default=0
        ) + 1

        executable = extract_executable_prompt(
            (capture or {}).get("api_prompt_json") or {}
        )
        version = WorkflowVersion(
            workflow_version_id=make_version_id(),
            workflow_id=workflow_id,
            version_number=version_number,
            graph_json=dict((capture or {}).get("graph_json") or {}),
            api_prompt_json=dict((capture or {}).get("api_prompt_json") or {}),
            executable_prompt=executable,
            graph_hash=graph_hash,
            created_at=now_iso(),
            dependency_metadata=extract_dependency_metadata(capture or {}),
            compatible_models=list(raw_workflow.get("compatible_models") or []),
        )
        stored = self.store.insert_version(version)

        workflow = Workflow.from_dict(raw_workflow)
        workflow.latest_version_id = stored["workflow_version_id"]
        workflow.updated_at = now_iso()
        updated = workflow.to_dict()
        updated.update({
            # Keep the first imported/captured graph on the user-facing
            # Workflow.  Later immutable compatibility revisions do not
            # silently replace the wrapper's static graph.
            "static_graph": copy.deepcopy(
                raw_workflow.get("static_graph")
                or (capture or {}).get("graph_json")
                or executable
                or {}
            ),
        })
        self.store.update_workflow_fields(workflow_id, updated)

        return self._enrich_version(stored)

    def create_mapping_revision(
        self,
        workflow_version_id: str,
        *,
        entries: dict[str, dict[str, Any]],
        output_node_id: str = "",
        text_generate_node_id: Optional[str] = None,
        reference_method: str = "",
        reference_bindings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Change a Mapping by creating a NEW immutable Workflow Version.

        The new Version copies the exact graph (graph JSON / API prompt /
        executable prompt / graph hash) from the source Version — identical
        graph bytes are allowed across Versions because the Mapping differs.
        Graph-hash dedupe never applies here: the revision is intentional.

        The old Version and its Mapping remain untouched.
        """
        source = self.store.get_version(workflow_version_id)
        if source is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        raw_workflow = self.store.get_workflow(str(source.get("workflow_id", "")))
        if raw_workflow is None:
            raise WorkflowNotFoundError(
                f"workflow {source.get('workflow_id', '')!r} not found"
            )
        now = now_iso()
        normalized = self._normalize_entries(entries)
        self._validate_entries_against_graph(normalized, source)
        text_generate_node_id = self._validate_text_generate_binding(
            self._normalize_text_generate_node_id(text_generate_node_id), source
        )
        ref_method, ref_bindings = self._validate_reference_bindings(
            reference_method, reference_bindings, source
        )
        output_node_id = self.normalize_output_node_id(
            output_node_id,
            source.get("executable_prompt") or {},
            source.get("graph_json"),
        ) or str(output_node_id or "")
        versions = self.store.list_versions_for_workflow(
            str(source.get("workflow_id", ""))
        )
        version_number = max(
            (int(v.get("version_number", 0)) for v in versions), default=0
        ) + 1

        revision = WorkflowVersion(
            workflow_version_id=make_version_id(),
            workflow_id=str(source.get("workflow_id", "")),
            version_number=version_number,
            graph_json=dict(source.get("graph_json") or {}),
            api_prompt_json=dict(source.get("api_prompt_json") or {}),
            executable_prompt=dict(source.get("executable_prompt") or {}),
            graph_hash=str(source.get("graph_hash", "")),
            created_at=now,
            dependency_metadata=dict(source.get("dependency_metadata") or {}),
            compatible_models=list(raw_workflow.get("compatible_models") or []),
        )
        stored = self.store.insert_version(revision)

        mapping = Mapping(
            mapping_id=make_mapping_id(),
            workflow_version_id=stored["workflow_version_id"],
            created_at=now,
            updated_at=now,
            output_node_id=str(output_node_id or ""),
            text_generate_node_id=text_generate_node_id,
            entries=normalized,
            reference_method=ref_method,
            reference_bindings=ref_bindings,
        )
        self.store.insert_mapping(mapping)

        workflow = Workflow.from_dict(raw_workflow)
        workflow.latest_version_id = stored["workflow_version_id"]
        workflow.updated_at = now
        self.store.update_workflow_fields(
            workflow.workflow_id,
            {
                **workflow.to_dict(),
                "bindings": {
                    _ROLE_ALIASES.get(role, role): {
                        **entry.to_dict(),
                        "semantic_role": _ROLE_ALIASES.get(role, role),
                    }
                    for role, entry in mapping.entries.items()
                    if _ROLE_ALIASES.get(role, role) in BINDABLE_INPUT_CATALOG
                },
                "output_binding": {
                    "node_id": mapping.output_node_id,
                    "output_name": "",
                } if mapping.output_node_id else {},
            },
        )

        return self._enrich_version(stored)

    def get_version(self, workflow_version_id: str) -> dict[str, Any]:
        version = self.store.get_version(workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        return self._enrich_version(version)

    def list_versions(self, workflow_id: str) -> list[dict[str, Any]]:
        versions = self.store.list_versions_for_workflow(workflow_id)
        versions.sort(key=lambda v: int(v.get("version_number", 0)))
        return [self._enrich_version(v) for v in versions]

    def derive_version_state_for_records(
        self,
        workflow_version_id: str,
        version: dict[str, Any] | None,
        mapping: dict[str, Any] | None,
        workflow_row: dict[str, Any] | None = None,
    ) -> VersionState:
        if version is None:
            return VersionState(
                status="incomplete",
                reasons=[f"workflow version {workflow_version_id!r} not found"],
                runnable=False,
            )
        reasons: list[str] = []
        executable = version.get("executable_prompt") or {}
        if not executable:
            reasons.append("no executable prompt")
        if mapping is None:
            reasons.append("missing mapping")
        else:
            entries_raw = mapping.get("entries") or []
            ui_graph = version.get("graph_json")
            for raw_entry in entries_raw:
                if not isinstance(raw_entry, dict):
                    continue
                role = raw_entry.get("semantic_role", "")
                node_id = str(raw_entry.get("node_id", ""))
                kind = raw_entry.get("kind", "node_input")
                if kind in INPUT_BINDING_KINDS:
                    input_name = str(raw_entry.get("input_name", ""))
                    if node_id and input_name:
                        target = resolve_binding_target(
                            executable,
                            node_id,
                            input_name,
                            ui_graph=ui_graph,
                            node_def_provider=self._node_def_provider,
                        )
                        if target.get("resolvable"):
                            continue
                        if not target.get("node_present") and not subgraph_node_present(
                            executable, ui_graph, node_id
                        ):
                            reasons.append(
                                f"mapped entry {role!r} node {node_id} not present in graph"
                            )
                            continue
                        reasons.append(
                            f"mapped entry {role!r} input {input_name!r} "
                            f"not present on node {node_id}"
                        )
                        continue
                if node_id and not node_exists(executable, node_id):
                    if subgraph_node_present(executable, ui_graph, node_id):
                        continue
                    reasons.append(
                        f"mapped entry {role!r} node {node_id} not present in graph"
                    )
                    continue
            output_node_id = str(mapping.get("output_node_id", ""))
            output_ok = bool(
                output_node_id
                and (
                    node_exists(executable, output_node_id)
                    or subgraph_resolve_output(
                        executable, version.get("graph_json"), output_node_id
                    )
                )
            )
            if not output_ok:
                reasons.append("no output node")
            # Reference bindings are version-bound: revalidate the stored
            # method/bindings against the current executable graph on every
            # read (version change, regeneration, submission gate). Stale
            # nodes/sockets or an unevidenced chain block runnable state.
            try:
                ref_method = str((mapping.get("reference_method", "") or ""))
                ref_bindings = mapping.get("reference_bindings")
                if ref_method:
                    try:
                        self._validate_reference_bindings(
                            ref_method, ref_bindings, version
                        )
                    except WorkflowDomainValidationError as ref_exc:
                        reasons.append(f"stale reference bindings: {ref_exc}")
                    except Exception:
                        reasons.append("stale reference bindings")
            except Exception:
                pass
            # Profile completeness: a version missing a required Tool Input
            # for its workflow type cannot run. Without this, an image tool
            # version saved without its Source Image binding reports ready and
            # fails opaquely at submit/run time instead.
            try:
                # Graph-era spellings canonicalize exactly like the binding
                # map does, so legacy-mapped workflows keep their status.
                mapped_roles = {
                    _ROLE_ALIASES.get(str(raw_entry.get("semantic_role", "")),
                                      str(raw_entry.get("semantic_role", "")))
                    for raw_entry in entries_raw
                    if isinstance(raw_entry, dict) and raw_entry.get("semantic_role")
                }
                raw_type = str(
                    version.get("workflow_type", "")
                    or (workflow_row or {}).get("workflow_type", "")
                    or ""
                ).strip().lower()
                if raw_type:
                    canonical_type = normalize_workflow_type(raw_type)
                    profile = WORKFLOW_TYPE_PROFILES.get(canonical_type, {})
                    # Only image Tool Inputs are enforced here (Source Image,
                    # Mask): model roles have long-standing triple-mapping and
                    # dependency-provider semantics that completeness must not
                    # renegotiate. An image tool saved without its image
                    # binding would otherwise report ready and fail opaquely
                    # at submit/run time.
                    for role in profile.get("required", ()):
                        if BINDABLE_INPUT_CATALOG.get(role, {}).get("input_kind") != "image":
                            continue
                        if role not in mapped_roles:
                            reasons.append(
                                f"missing required binding {role!r} for workflow type {canonical_type!r}"
                            )
            except Exception:
                pass
        if self._dependency_provider is not None:
            try:
                extra = self._dependency_provider(version)
                if isinstance(extra, list):
                    reasons.extend(str(r) for r in extra if r)
            except Exception:
                pass
        state = VersionState()
        if not reasons:
            state.status = "ready"
            state.runnable = True
        else:
            state.status = "incomplete"
            state.reasons = reasons
            state.runnable = False
        return state

    def derive_version_state(self, workflow_version_id: str) -> VersionState:
        snap = self.store.snapshot_all()
        version = self.store.find_in(
            snap.get("versions", []), "workflow_version_id", workflow_version_id
        )
        mapping = None
        workflow_row = None
        if version is not None:
            mapping = self.store.find_in(
                snap.get("mappings", []),
                "workflow_version_id",
                workflow_version_id,
            )
            workflow_row = self.store.find_in(
                snap.get("workflows", []),
                "workflow_id",
                str(version.get("workflow_id", "")),
            )
        return self.derive_version_state_for_records(
            workflow_version_id, version, mapping, workflow_row
        )

    def assert_runnable(self, workflow_version_id: str) -> None:
        state = self.derive_version_state(workflow_version_id)
        if not state.runnable:
            raise WorkflowNotRunnableError(
                f"workflow version {workflow_version_id!r} is not runnable: "
                + "; ".join(state.reasons)
            )

    # ── Mapping (exactly one immutable Mapping per version) ──────────────

    def set_mapping(
        self,
        workflow_version_id: str,
        *,
        entries: dict[str, dict[str, Any]],
        output_node_id: str = "",
        text_generate_node_id: Optional[str] = None,
        reference_method: str = "",
        reference_bindings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Attach the (single, immutable) Mapping to a Workflow Version.

        A Version without a Mapping receives one; a Version that already
        has a Mapping rejects any further set_mapping call. To change a
        Mapping, create a new Workflow Version via
        ``create_mapping_revision`` — the old Version and Mapping never
        change meaning.
        """
        version = self.store.get_version(workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        if self.store.get_mapping_for_version(workflow_version_id) is not None:
            raise MappingAlreadyExistsError(
                f"workflow version {workflow_version_id!r} already has an "
                "immutable mapping; use create_mapping_revision() to create "
                "a new version with a changed mapping"
            )
        now = now_iso()
        normalized = self._normalize_entries(entries)
        self._validate_entries_against_graph(normalized, version)
        text_generate_node_id = self._validate_text_generate_binding(
            self._normalize_text_generate_node_id(text_generate_node_id), version
        )
        ref_method, ref_bindings = self._validate_reference_bindings(
            reference_method, reference_bindings, version
        )
        output_node_id = self.normalize_output_node_id(
            output_node_id,
            version.get("executable_prompt") or {},
            version.get("graph_json"),
        ) or str(output_node_id or "")
        mapping = Mapping(
            mapping_id=make_mapping_id(),
            workflow_version_id=workflow_version_id,
            created_at=now,
            updated_at=now,
            output_node_id=str(output_node_id or ""),
            text_generate_node_id=text_generate_node_id,
            entries=normalized,
            reference_method=ref_method,
            reference_bindings=ref_bindings,
        )
        stored = self.store.insert_mapping(mapping)
        raw_workflow = self.store.get_workflow(str(version.get("workflow_id", "")))
        if raw_workflow is not None:
            self.store.update_workflow_fields(
                str(version.get("workflow_id", "")),
                {
                    "bindings": {
                        _ROLE_ALIASES.get(role, role): {
                            **entry.to_dict(),
                            "semantic_role": _ROLE_ALIASES.get(role, role),
                        }
                        for role, entry in mapping.entries.items()
                        if _ROLE_ALIASES.get(role, role) in BINDABLE_INPUT_CATALOG
                    },
                    "output_binding": {
                        "node_id": mapping.output_node_id,
                        "output_name": "",
                    } if mapping.output_node_id else {},
                    "updated_at": now_iso(),
                },
            )
        return stored

    def get_mapping(self, workflow_version_id: str) -> Optional[dict[str, Any]]:
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        if mapping is None:
            return None
        return self._enrich_mapping(mapping)

    def get_mapping_entries(self, workflow_version_id: str) -> dict[str, dict[str, Any]]:
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        if mapping is None:
            return {}
        return {
            raw.get("semantic_role", ""): raw
            for raw in mapping.get("entries") or []
            if isinstance(raw, dict) and raw.get("semantic_role")
        }

    def _enrich_mapping(self, mapping: dict[str, Any]) -> dict[str, Any]:
        version_id = mapping.get("workflow_version_id", "")
        enriched = dict(mapping)
        # Records written before TextGenerate bypass support are unbound.
        enriched.setdefault("text_generate_node_id", None)
        # Records written before reference support carry no bindings.
        enriched.setdefault("reference_method", "")
        enriched.setdefault("reference_bindings", {})
        enriched["version_state"] = self.derive_version_state(version_id).to_dict()
        return enriched

    # ── enrichment ───────────────────────────────────────────────────────

    def _enrich_version(self, version: dict[str, Any]) -> dict[str, Any]:
        version_id = version.get("workflow_version_id", "")
        mapping = self.store.get_mapping_for_version(version_id)
        enriched = dict(version)
        enriched["state"] = self.derive_version_state(version_id).to_dict()
        enriched["mapping_id"] = mapping.get("mapping_id") if mapping else None
        enriched["mapping"] = self._enrich_mapping(mapping) if mapping else None
        return enriched

    # ── Workflow Presets (version-scoped, Phase 12) ──────────────────────

    def _require_preset_version(self, workflow_version_id: str) -> dict[str, Any]:
        version = self.store.get_version(workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        return version

    def _preset_mapping_roles(self, workflow_version_id: str) -> dict[str, dict]:
        """Mapped semantic roles for one version (canonical spellings)."""
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        if mapping is None:
            raise WorkflowDomainValidationError(
                f"workflow version {workflow_version_id!r} has no mapping; "
                "attach a mapping before creating presets"
            )
        roles: dict[str, dict] = {}
        for raw in mapping.get("entries") or []:
            if isinstance(raw, dict) and raw.get("semantic_role"):
                roles[str(raw["semantic_role"])] = raw
        return roles

    def _validate_preset_controls(
        self,
        studio_state: dict[str, Any],
        roles: dict[str, dict],
        *,
        target_version_id: str,
    ) -> None:
        """Fail closed when a preset control is not bound on the version."""
        canonical_roles = {_ROLE_ALIASES.get(r, r) for r in roles}
        for key in (studio_state.get("core") or {}).get("controls") or {}:
            if _ROLE_ALIASES.get(key, key) not in canonical_roles:
                raise WorkflowDomainValidationError(
                    f"studio_state.core.controls[{key!r}] is not a mapped role "
                    f"on workflow version {target_version_id!r} (stale binding)"
                )

    def _build_preset_record(
        self,
        *,
        preset_id: str,
        workflow_version_id: str,
        name: Any,
        description: Any,
        tags: Any,
        studio_state: Any,
        created_at: str,
        updated_at: str,
    ) -> WorkflowPreset:
        """Validate everything BEFORE any write; returns an unsaved record."""
        self._require_preset_version(workflow_version_id)
        clean_name, clean_description, clean_tags = normalize_preset_metadata(
            name, description, tags
        )
        normalized_state = normalize_studio_state(studio_state)
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        roles = self._preset_mapping_roles(workflow_version_id)
        self._validate_preset_controls(
            normalized_state, roles, target_version_id=workflow_version_id
        )
        return WorkflowPreset(
            preset_id=preset_id,
            workflow_version_id=workflow_version_id,
            name=clean_name,
            description=clean_description,
            tags=clean_tags,
            studio_state=normalized_state,
            mapping_fingerprint=compute_mapping_fingerprint(mapping),
            created_at=created_at,
            updated_at=updated_at,
        )

    def list_presets(self, workflow_version_id: str) -> list[dict[str, Any]]:
        self._require_preset_version(workflow_version_id)
        presets = self.store.list_presets_for_version(workflow_version_id)
        presets.sort(key=lambda p: (str(p.get("created_at", "")),
                                    str(p.get("preset_id", ""))))
        return presets

    def get_preset(self, preset_id: str) -> dict[str, Any]:
        preset = self.store.get_preset(preset_id)
        if preset is None:
            raise PresetNotFoundError(f"preset {preset_id!r} not found")
        return preset

    def create_preset(
        self,
        workflow_version_id: str,
        *,
        name: Any,
        description: Any = "",
        tags: Any = None,
        studio_state: Any,
    ) -> dict[str, Any]:
        now = now_iso()
        record = self._build_preset_record(
            preset_id=make_preset_id(),
            workflow_version_id=workflow_version_id,
            name=name,
            description="" if description is None else description,
            tags=[] if tags is None else tags,
            studio_state=studio_state,
            created_at=now,
            updated_at=now,
        )
        return self.store.insert_preset(record)

    def update_preset(self, preset_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Whole-state replace (no merge): ``studio_state`` is replaced in
        full and revalidated; version binding is immutable here."""
        stored = self.store.get_preset(preset_id)
        if stored is None:
            raise PresetNotFoundError(f"preset {preset_id!r} not found")
        if not isinstance(body, dict):
            raise WorkflowDomainValidationError("preset update must be an object")
        if ("workflow_version_id" in body
                and body["workflow_version_id"] != stored.get("workflow_version_id")):
            raise WorkflowDomainValidationError(
                "preset workflow_version_id is immutable; "
                "use copy-to-version to move a preset forward"
            )
        if "preset_id" in body and body["preset_id"] != preset_id:
            raise WorkflowDomainValidationError("preset preset_id is immutable")
        if "mapping_fingerprint" in body:
            raise WorkflowDomainValidationError(
                "preset mapping_fingerprint is server-computed and not editable"
            )
        name = body.get("name", stored.get("name", ""))
        description = body.get("description", stored.get("description", ""))
        tags = body.get("tags", stored.get("tags", []))
        if "studio_state" in body:
            studio_state = body["studio_state"]
        else:
            # No merge with history: callers resubmit the full state they
            # intend to keep; without one there is nothing to update.
            studio_state = stored.get("studio_state")
        record = self._build_preset_record(
            preset_id=preset_id,
            workflow_version_id=str(stored.get("workflow_version_id", "")),
            name=name,
            description="" if description is None else description,
            tags=[] if tags is None else tags,
            studio_state=copy.deepcopy(studio_state),
            created_at=str(stored.get("created_at", "")),
            updated_at=now_iso(),
        )
        return self.store.update_preset(record)

    def delete_preset(self, preset_id: str) -> None:
        if not self.store.delete_preset(preset_id):
            raise PresetNotFoundError(f"preset {preset_id!r} not found")

    def duplicate_preset(
        self, preset_id: str, *, name: Any = None
    ) -> dict[str, Any]:
        """Duplicate on the SAME version: new id and timestamps, same state."""
        stored = self.store.get_preset(preset_id)
        if stored is None:
            raise PresetNotFoundError(f"preset {preset_id!r} not found")
        now = now_iso()
        record = self._build_preset_record(
            preset_id=make_preset_id(),
            workflow_version_id=str(stored.get("workflow_version_id", "")),
            name=stored.get("name", "") if name is None else name,
            description=stored.get("description", ""),
            tags=list(stored.get("tags", [])),
            studio_state=copy.deepcopy(stored.get("studio_state")),
            created_at=now,
            updated_at=now,
        )
        return self.store.insert_preset(record)

    def copy_preset_to_version(
        self, preset_id: str, target_version_id: str
    ) -> dict[str, Any]:
        """Copy forward onto another version with target revalidation.

        The carried ``studio_state`` is revalidated against the TARGET
        version's mapping; controls bound to roles the target does not map
        fail closed as stale bindings and nothing is written.
        """
        stored = self.store.get_preset(preset_id)
        if stored is None:
            raise PresetNotFoundError(f"preset {preset_id!r} not found")
        self._require_preset_version(target_version_id)
        now = now_iso()
        record = self._build_preset_record(
            preset_id=make_preset_id(),
            workflow_version_id=target_version_id,
            name=stored.get("name", ""),
            description=stored.get("description", ""),
            tags=list(stored.get("tags", [])),
            studio_state=copy.deepcopy(stored.get("studio_state")),
            created_at=now,
            updated_at=now,
        )
        return self.store.insert_preset(record)
