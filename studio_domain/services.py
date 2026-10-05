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
    derive_mapping_candidates,
    extract_dependency_metadata,
    extract_executable_prompt,
    graph_hash_from_capture,
    input_exists,
    is_ui_workflow_format,
    node_exists,
    ui_graph_to_api_prompt,
)
from .models import (
    ImmutableVersionError,
    Mapping,
    MappingAlreadyExistsError,
    MappingEntry,
    VersionState,
    Workflow,
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
_EXACT_BINDING = {"kind": "widget", "exact": True, "cardinality": "one"}
BINDABLE_INPUT_CATALOG: dict[str, dict[str, Any]] = {
    "prompt": {"key": "prompt", "name": "Prompt", "block": "multiline",
               "input_kind": "multiline", "required_for": ("t2i",),
               "optional_for": (), "experiment_eligible": True,
               "rules": {"multiline": True}, "binding": _EXACT_BINDING},
    "seed": {"key": "seed", "name": "Seed", "block": "integer",
             "input_kind": "integer", "required_for": ("t2i",),
             "optional_for": (), "experiment_eligible": True,
             "rules": {"minimum": None, "allow_negative": True},
             "binding": _EXACT_BINDING},
    "step_count": {"key": "step_count", "name": "Step count", "block": "integer",
                    "input_kind": "integer", "required_for": (),
                    "optional_for": ("t2i",), "experiment_eligible": True,
                    "rules": {"minimum": 1, "step": 1, "allow_negative": False},
                    "binding": _EXACT_BINDING},
    "cfg_scale": {"key": "cfg_scale", "name": "CFG scale", "block": "float",
                   "input_kind": "float", "required_for": (),
                   "optional_for": ("t2i",), "experiment_eligible": True,
                   "rules": {"minimum": 0, "allow_negative": False},
                   "binding": _EXACT_BINDING},
    "sampler": {"key": "sampler", "name": "Sampler", "block": "dropdown",
                "input_kind": "dropdown", "required_for": (),
                "optional_for": ("t2i",), "experiment_eligible": True,
                "rules": {}, "binding": _EXACT_BINDING},
    "model_unet": {"key": "model_unet", "name": "Model UNET", "block": "model-picker",
                    "input_kind": "model", "required_for": ("t2i",),
                    "optional_for": (), "experiment_eligible": True,
                    "rules": {"model_type": "unet"}, "binding": _EXACT_BINDING},
    "vae": {"key": "vae", "name": "VAE", "block": "model-picker",
            "input_kind": "model", "required_for": ("t2i",),
            "optional_for": (), "experiment_eligible": True,
            "rules": {"model_type": "vae"}, "binding": _EXACT_BINDING},
    "clip": {"key": "clip", "name": "CLIP", "block": "model-picker",
             "input_kind": "model", "required_for": ("t2i",),
             "optional_for": (), "experiment_eligible": True,
             "rules": {"model_type": "clip"}, "binding": _EXACT_BINDING},
}
T2I_REQUIRED_INPUTS = ("prompt", "seed", "model_unet", "vae", "clip")
T2I_OPTIONAL_INPUTS = ("step_count", "cfg_scale", "sampler")
OUTPUT_BINDING = {"key": "output", "name": "Output", "block": None,
                  "required_for": ("t2i",),
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
}


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
        workflow_type = workflow_type.strip()
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
            entries=self._normalize_entries(entries),
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

    def derive_version_state(self, workflow_version_id: str) -> VersionState:
        version = self.store.get_version(workflow_version_id)
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
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        if mapping is None:
            reasons.append("missing mapping")
        else:
            entries_raw = mapping.get("entries") or []
            for raw_entry in entries_raw:
                if not isinstance(raw_entry, dict):
                    continue
                role = raw_entry.get("semantic_role", "")
                node_id = str(raw_entry.get("node_id", ""))
                kind = raw_entry.get("kind", "node_input")
                if node_id and not node_exists(executable, node_id):
                    reasons.append(
                        f"mapped entry {role!r} node {node_id} not present in graph"
                    )
                    continue
                if kind in ("node_input", "widget"):
                    input_name = str(raw_entry.get("input_name", ""))
                    if node_id and input_name and not input_exists(
                        executable, node_id, input_name
                    ):
                        reasons.append(
                            f"mapped entry {role!r} input {input_name!r} "
                            f"not present on node {node_id}"
                        )
            output_node_id = str(mapping.get("output_node_id", ""))
            if not output_node_id or not node_exists(executable, output_node_id):
                reasons.append("no output node")
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
        mapping = Mapping(
            mapping_id=make_mapping_id(),
            workflow_version_id=workflow_version_id,
            created_at=now,
            updated_at=now,
            output_node_id=str(output_node_id or ""),
            entries=self._normalize_entries(entries),
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
