"""Domain services for the Workflow platform foundation.

Owns the business rules:

* Workflows are organized (folders/tags/favorites) and identify a default
  preset and their latest version.
* WorkflowVersions are immutable snapshots; structural change creates a new
  version (deduplicated by canonical graph hash).
* Exactly one Mapping per version; mappings may be edited.
* Presets are tied to the version they were created for; they may be copied
  forward to newer versions without mutating the originals.
* Incomplete versions/presets are saved but unrunnable, with explicit
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
    node_exists,
)
from .models import (
    ImmutableVersionError,
    Mapping,
    MappingAlreadyExistsError,
    MappingEntry,
    PresetCopyError,
    PresetState,
    VersionState,
    Workflow,
    WorkflowNotFoundError,
    WorkflowNotRunnableError,
    WorkflowPreset,
    WorkflowPresetNotFoundError,
    WorkflowPresetValidationError,
    WorkflowVersion,
    WorkflowVersionNotFoundError,
    make_mapping_id,
    make_preset_id,
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
_PRESET_EDITABLE = {
    "name", "description", "values", "model_choices", "lora_values",
    "exposed_controls", "recommended_values", "favorite", "tags",
}


class WorkflowDomainService:
    def __init__(
        self,
        root: str,
        dependency_provider: Optional[Callable[[dict[str, Any]], list[str]]] = None,
    ) -> None:
        self.store = WorkflowDomainStore(root)
        # Optional callable(version_dict) -> list[str] feeding extra reasons
        # into derived version state (e.g. dependency resolution).  Must never
        # raise — any exception is swallowed by derive_version_state.
        self._dependency_provider = dependency_provider

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

    def _validate_preset_values(
        self,
        values: dict[str, Any],
        mapping: Mapping,
        *,
        missing_required: list[str],
        strict: bool,
    ) -> list[str]:
        """Validate preset values against the mapping. Returns reason list.

        Unknown controls raise only when *strict*; missing required values
        are recorded into *missing_required*.
        """
        reasons: list[str] = []
        entries = mapping.entries
        for role, value in values.items():
            entry = entries.get(role)
            if entry is None:
                if strict:
                    raise WorkflowPresetValidationError(
                        f"unknown control {role!r}: not present in the mapping"
                    )
                continue
            if value is None:
                if entry.required and role not in missing_required:
                    missing_required.append(role)
                continue
            error = self._validate_value(role, value, entry)
            if error:
                reasons.append(error)
        for role, entry in entries.items():
            if entry.required and role not in values:
                if role not in missing_required:
                    missing_required.append(role)
        return reasons

    def _validate_model_choices(
        self,
        model_choices: dict[str, Any],
        mapping: Mapping,
        compatible_models: list[str],
        *,
        as_reason: bool = False,
    ) -> list[str]:
        """Validate model choices against the mapping + the VERSION's frozen
        compatible-model contract.

        With ``as_reason`` (copy-forward path) mismatches become reasons
        instead of raised errors.
        """
        reasons: list[str] = []
        for role, model_name in model_choices.items():
            entry = mapping.entries.get(role)
            if entry is None:
                msg = f"unknown control {role!r}: not present in the mapping"
                if as_reason:
                    reasons.append(msg)
                else:
                    raise WorkflowPresetValidationError(msg)
                continue
            if compatible_models and model_name not in compatible_models:
                msg = (
                    f"model {model_name!r} for {role!r} is not declared "
                    f"compatible for this workflow version"
                )
                if as_reason:
                    reasons.append(msg)
                else:
                    raise WorkflowPresetValidationError(msg)
        return reasons

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
    ) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise WorkflowPresetValidationError("workflow name is required")
        now = now_iso()
        workflow = Workflow(
            workflow_id=make_workflow_id(),
            name=name.strip()[:200],
            description=(description or "")[:2000],
            folder=(folder or "").strip("/")[:500],
            tags=list(tags or []),
            favorite=bool(favorite),
            source_url=(source_url or "")[:2000],
            source_author=(source_author or "")[:500],
            compatible_models=list(compatible_models or []),
            created_at=now,
            updated_at=now,
        )
        return self.store.insert_workflow(workflow)

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        return workflow

    def list_workflows(self) -> list[dict[str, Any]]:
        return self.store.list_workflows()

    def update_workflow(self, workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
        raw = self.store.get_workflow(workflow_id)
        if raw is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        workflow = Workflow.from_dict(raw)
        for key in body:
            if key not in _WORKFLOW_EDITABLE:
                raise WorkflowPresetValidationError(
                    f"field {key!r} is not editable on a workflow"
                )
        if "name" in body:
            if not isinstance(body["name"], str) or not body["name"].strip():
                raise WorkflowPresetValidationError("workflow name is required")
            workflow.name = body["name"].strip()[:200]
        if "description" in body:
            workflow.description = (body["description"] or "")[:2000]
        if "folder" in body:
            workflow.folder = (body["folder"] or "").strip("/")[:500]
        if "tags" in body:
            if not isinstance(body["tags"], list):
                raise WorkflowPresetValidationError("tags must be a list of strings")
            workflow.tags = [t for t in body["tags"] if isinstance(t, str)]
        if "favorite" in body:
            workflow.favorite = bool(body["favorite"])
        if "source_url" in body:
            workflow.source_url = (body["source_url"] or "")[:2000]
        if "source_author" in body:
            workflow.source_author = (body["source_author"] or "")[:500]
        if "compatible_models" in body:
            if not isinstance(body["compatible_models"], list):
                raise WorkflowPresetValidationError(
                    "compatible_models must be a list of strings"
                )
            workflow.compatible_models = [
                m for m in body["compatible_models"] if isinstance(m, str)
            ]
        workflow.updated_at = now_iso()
        return self.store.update_workflow(workflow)

    def list_folders(self) -> list[str]:
        folders: set[str] = set()
        for wf in self.store.list_workflows():
            folder = wf.get("folder", "")
            if not folder:
                continue
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                folders.add("/".join(parts[:i]))
        return sorted(folders)

    def list_tags(self) -> list[str]:
        tags: set[str] = set()
        for wf in self.store.list_workflows():
            tags.update(wf.get("tags") or [])
        for preset in self.store.list_presets():
            tags.update(preset.get("tags") or [])
        return sorted(tags)

    def set_default_preset(self, workflow_id: str, preset_id: str) -> dict[str, Any]:
        raw = self.store.get_workflow(workflow_id)
        if raw is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        preset = self.store.get_preset(preset_id)
        if preset is None:
            raise WorkflowPresetNotFoundError(f"preset {preset_id!r} not found")
        if preset.get("workflow_id") != workflow_id:
            raise WorkflowPresetValidationError(
                f"preset {preset_id!r} does not belong to workflow {workflow_id!r}"
            )
        workflow = Workflow.from_dict(raw)
        workflow.default_preset_id = preset_id
        workflow.updated_at = now_iso()
        return self.store.update_workflow(workflow)

    def clear_default_preset(self, workflow_id: str) -> dict[str, Any]:
        raw = self.store.get_workflow(workflow_id)
        if raw is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        workflow = Workflow.from_dict(raw)
        workflow.default_preset_id = ""
        workflow.updated_at = now_iso()
        return self.store.update_workflow(workflow)

    def get_default_preset(self, workflow_id: str) -> Optional[dict[str, Any]]:
        raw = self.store.get_workflow(workflow_id)
        if raw is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
        default_id = raw.get("default_preset_id", "")
        if not default_id:
            return None
        preset = self.store.get_preset(default_id)
        if preset is None:
            return None
        return self._enrich_preset(preset, raw)

    # ── Workflow Version (immutable) ─────────────────────────────────────

    def create_version_from_capture(
        self, workflow_id: str, capture: dict[str, Any]
    ) -> dict[str, Any]:
        raw_workflow = self.store.get_workflow(workflow_id)
        if raw_workflow is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id!r} not found")
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
        self.store.update_workflow(workflow)

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

        The old Version, its Mapping, and its Presets remain untouched.
        Presets can be copied forward explicitly via
        ``copy_preset_to_version``.
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
        self.store.update_workflow(workflow)

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
        return self.store.insert_mapping(mapping)

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

    # ── Preset ───────────────────────────────────────────────────────────

    def create_preset(
        self,
        workflow_version_id: str,
        name: str,
        *,
        values: Optional[dict[str, Any]] = None,
        model_choices: Optional[dict[str, Any]] = None,
        lora_values: Optional[dict[str, Any]] = None,
        exposed_controls: Optional[list[str]] = None,
        recommended_values: Optional[dict[str, Any]] = None,
        favorite: bool = False,
        tags: Optional[list[str]] = None,
        description: str = "",
        strict: bool = True,
    ) -> dict[str, Any]:
        version = self.store.get_version(workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        if not isinstance(name, str) or not name.strip():
            raise WorkflowPresetValidationError("preset name is required")
        mapping = self.store.get_mapping_for_version(workflow_version_id)
        if mapping is None:
            raise WorkflowPresetValidationError(
                f"workflow version {workflow_version_id!r} has no mapping"
            )
        mapping_obj = Mapping.from_dict(mapping)
        version_compat = list(version.get("compatible_models") or [])
        workflow = self.store.get_workflow(str(version.get("workflow_id", "")))

        values = values or {}
        model_choices = model_choices or {}
        missing_required: list[str] = []
        reasons = self._validate_preset_values(
            values, mapping_obj, missing_required=missing_required, strict=strict
        )
        reasons += self._validate_model_choices(
            model_choices, mapping_obj, version_compat, as_reason=False
        )

        now = now_iso()
        preset = WorkflowPreset(
            preset_id=make_preset_id(),
            workflow_version_id=workflow_version_id,
            workflow_id=str(version.get("workflow_id", "")),
            name=name.strip()[:200],
            description=(description or "")[:2000],
            values=dict(values),
            model_choices=dict(model_choices),
            lora_values=dict(lora_values or {}),
            exposed_controls=list(exposed_controls or []),
            recommended_values=dict(recommended_values or {}),
            favorite=bool(favorite),
            tags=list(tags or []),
            created_at=now,
            updated_at=now,
        )
        if reasons or missing_required:
            preset_state = PresetState(
                status="incomplete",
                reasons=reasons
                + [f"missing value for required control {r!r}" for r in missing_required],
                runnable=False,
            )
        else:
            preset_state = self.derive_preset_state(preset, version, mapping)
        stored = self.store.insert_preset(preset)
        enriched = self._enrich_preset(stored, workflow)
        enriched["state"] = preset_state.to_dict()
        return enriched

    def update_preset(self, preset_id: str, body: dict[str, Any]) -> dict[str, Any]:
        raw = self.store.get_preset(preset_id)
        if raw is None:
            raise WorkflowPresetNotFoundError(f"preset {preset_id!r} not found")
        for key in body:
            if key not in _PRESET_EDITABLE:
                raise WorkflowPresetValidationError(
                    f"field {key!r} is not editable on a preset "
                    "(workflow_version_id/workflow_id/preset_id are immutable)"
                )
        version = self.store.get_version(str(raw.get("workflow_version_id", "")))
        mapping = self.store.get_mapping_for_version(str(raw.get("workflow_version_id", "")))
        if version is None or mapping is None:
            raise WorkflowPresetValidationError(
                f"preset {preset_id!r} references a missing version/mapping"
            )
        mapping_obj = Mapping.from_dict(mapping)
        version_compat = list(version.get("compatible_models") or [])
        workflow_raw = self.store.get_workflow(str(raw.get("workflow_id", "")))

        preset = WorkflowPreset.from_dict(raw)
        if "name" in body:
            if not isinstance(body["name"], str) or not body["name"].strip():
                raise WorkflowPresetValidationError("preset name is required")
            preset.name = body["name"].strip()[:200]
        if "description" in body:
            preset.description = (body["description"] or "")[:2000]
        if "values" in body:
            if not isinstance(body["values"], dict):
                raise WorkflowPresetValidationError("values must be an object")
            preset.values = dict(body["values"])
        if "model_choices" in body:
            if not isinstance(body["model_choices"], dict):
                raise WorkflowPresetValidationError("model_choices must be an object")
            preset.model_choices = dict(body["model_choices"])
        if "lora_values" in body:
            if not isinstance(body["lora_values"], dict):
                raise WorkflowPresetValidationError("lora_values must be an object")
            preset.lora_values = dict(body["lora_values"])
        if "exposed_controls" in body:
            if not isinstance(body["exposed_controls"], list):
                raise WorkflowPresetValidationError(
                    "exposed_controls must be a list"
                )
            preset.exposed_controls = [
                c for c in body["exposed_controls"] if isinstance(c, str)
            ]
        if "recommended_values" in body:
            if not isinstance(body["recommended_values"], dict):
                raise WorkflowPresetValidationError(
                    "recommended_values must be an object"
                )
            preset.recommended_values = dict(body["recommended_values"])
        if "favorite" in body:
            preset.favorite = bool(body["favorite"])
        if "tags" in body:
            if not isinstance(body["tags"], list):
                raise WorkflowPresetValidationError("tags must be a list of strings")
            preset.tags = [t for t in body["tags"] if isinstance(t, str)]
        preset.updated_at = now_iso()

        # Re-validate against the version's mapping: unknown controls and
        # incompatible models raise; invalid/missing values are saved and
        # surface through the derived (incomplete) state.
        missing_required: list[str] = []
        self._validate_preset_values(
            preset.values, mapping_obj, missing_required=missing_required, strict=True
        )
        self._validate_model_choices(
            preset.model_choices, mapping_obj, version_compat, as_reason=False
        )

        stored = self.store.update_preset(preset)
        return self._enrich_preset(stored, workflow_raw)

    def duplicate_preset(self, preset_id: str, *, name: str = "") -> dict[str, Any]:
        """Duplicate a Preset on the SAME Version (re-validated on create)."""
        raw = self.store.get_preset(preset_id)
        if raw is None:
            raise WorkflowPresetNotFoundError(f"preset {preset_id!r} not found")
        version = self.store.get_version(str(raw.get("workflow_version_id", "")))
        if version is None:
            raise WorkflowPresetValidationError(
                f"preset {preset_id!r} references a missing version"
            )
        if self.store.get_mapping_for_version(
            str(raw.get("workflow_version_id", ""))
        ) is None:
            raise WorkflowPresetValidationError(
                f"preset {preset_id!r} references a version without a mapping"
            )
        return self.create_preset(
            str(raw.get("workflow_version_id", "")),
            name or f"{raw.get('name', 'Untitled Preset')} (Copy)",
            description=str(raw.get("description", "")),
            values=dict(raw.get("values") or {}),
            model_choices=dict(raw.get("model_choices") or {}),
            lora_values=dict(raw.get("lora_values") or {}),
            exposed_controls=list(raw.get("exposed_controls") or []),
            recommended_values=dict(raw.get("recommended_values") or {}),
            favorite=bool(raw.get("favorite", False)),
            tags=list(raw.get("tags") or []),
        )

    def get_preset(self, preset_id: str) -> dict[str, Any]:
        raw = self.store.get_preset(preset_id)
        if raw is None:
            raise WorkflowPresetNotFoundError(f"preset {preset_id!r} not found")
        workflow = self.store.get_workflow(str(raw.get("workflow_id", "")))
        return self._enrich_preset(raw, workflow)

    def delete_preset(self, preset_id: str) -> None:
        raw = self.store.get_preset(preset_id)
        if raw is None:
            raise WorkflowPresetNotFoundError(f"preset {preset_id!r} not found")
        self.store.delete_preset(preset_id)
        workflow = self.store.get_workflow(str(raw.get("workflow_id", "")))
        if workflow and workflow.get("default_preset_id") == preset_id:
            wf_obj = Workflow.from_dict(workflow)
            wf_obj.default_preset_id = ""
            wf_obj.updated_at = now_iso()
            self.store.update_workflow(wf_obj)

    def list_presets(self, workflow_version_id: str) -> list[dict[str, Any]]:
        version = self.store.get_version(workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {workflow_version_id!r} not found"
            )
        workflow = self.store.get_workflow(str(version.get("workflow_id", "")))
        presets = [
            p for p in self.store.list_presets()
            if p.get("workflow_version_id") == workflow_version_id
        ]
        return [self._enrich_preset(p, workflow) for p in presets]

    def list_presets_for_workflow(self, workflow_id: str) -> list[dict[str, Any]]:
        versions = self.store.list_versions_for_workflow(workflow_id)
        versions.sort(key=lambda v: int(v.get("version_number", 0)), reverse=True)
        workflow = self.store.get_workflow(workflow_id)
        presets = [
            p for p in self.store.list_presets()
            if p.get("workflow_id") == workflow_id
        ]
        version_rank = {v["workflow_version_id"]: i for i, v in enumerate(versions)}
        presets.sort(key=lambda p: version_rank.get(p.get("workflow_version_id", ""), 10**9))
        return [self._enrich_preset(p, workflow) for p in presets]

    def derive_preset_state(
        self,
        preset: WorkflowPreset | dict[str, Any],
        version: Optional[dict[str, Any]] = None,
        mapping: Optional[dict[str, Any]] = None,
        compatible_models: Optional[list[str]] = None,
    ) -> PresetState:
        """Derive the preset state from stored data (never persisted).

        Model compatibility is validated against the VERSION's frozen
        compatibility contract, never the mutable logical-Workflow list.
        """
        preset = preset if isinstance(preset, WorkflowPreset) else WorkflowPreset.from_dict(preset)
        reasons: list[str] = []
        if preset.dropped_controls:
            reasons.append(
                "mapped controls no longer present in this version: "
                + ", ".join(preset.dropped_controls)
            )
        if version is None:
            version = self.store.get_version(preset.workflow_version_id)
        if version is None:
            reasons.append("workflow version not found")
        if compatible_models is None:
            compatible_models = list((version or {}).get("compatible_models") or [])
        if mapping is None:
            mapping = self.store.get_mapping_for_version(preset.workflow_version_id)
        version_state = self.derive_version_state(preset.workflow_version_id)
        if version_state.reasons:
            reasons.append("workflow version is incomplete: " + "; ".join(version_state.reasons))

        if mapping is not None:
            mapping_obj = Mapping.from_dict(mapping)
            missing: list[str] = []
            for role, entry in mapping_obj.entries.items():
                if entry.required and (preset.values.get(role) is None):
                    missing.append(role)
            reasons += [f"missing value for required control {r!r}" for r in missing]
            for role, value in preset.values.items():
                entry = mapping_obj.entries.get(role)
                if entry is None or value is None:
                    continue
                error = self._validate_value(role, value, entry)
                if error:
                    reasons.append(error)
            reasons += self._validate_model_choices(
                preset.model_choices, mapping_obj, compatible_models, as_reason=True
            )
        else:
            reasons.append("workflow version has no mapping")

        state = PresetState()
        if not reasons:
            state.status = "ready"
            state.runnable = version_state.runnable
        else:
            state.status = "incomplete"
            state.reasons = reasons
            state.runnable = False
        return state

    # ── copy-forward ─────────────────────────────────────────────────────

    def _prepare_copy(
        self,
        source: dict[str, Any],
        target_version: dict[str, Any],
    ) -> tuple[WorkflowPreset, list[str]]:
        """Compute the copied preset + dropped controls; never writes."""
        source_version = self.store.get_version(str(source.get("workflow_version_id", "")))
        if source_version is None:
            raise PresetCopyError("source preset references a missing version")
        if source_version.get("workflow_id") != target_version.get("workflow_id"):
            raise PresetCopyError(
                "cannot copy preset to a version of a different workflow"
            )
        source_number = int(source_version.get("version_number", 0))
        target_number = int(target_version.get("version_number", 0))
        if target_number <= source_number:
            raise PresetCopyError(
                f"target version {target_number} is not newer than "
                f"source version {source_number}"
            )

        target_mapping = self.store.get_mapping_for_version(
            str(target_version.get("workflow_version_id", ""))
        )
        mapped_roles: set[str] = set()
        if target_mapping is not None:
            for raw in target_mapping.get("entries") or []:
                if isinstance(raw, dict) and raw.get("semantic_role"):
                    mapped_roles.add(str(raw["semantic_role"]))

        def _keep_only(container: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
            kept: dict[str, Any] = {}
            dropped: list[str] = []
            for role, value in container.items():
                if role in mapped_roles:
                    kept[role] = copy.deepcopy(value)
                else:
                    dropped.append(role)
            return kept, dropped

        values, dropped_values = _keep_only(dict(source.get("values") or {}))
        model_choices, dropped_models = _keep_only(dict(source.get("model_choices") or {}))
        lora_values, dropped_loras = _keep_only(dict(source.get("lora_values") or {}))
        recommended, dropped_recommended = _keep_only(
            dict(source.get("recommended_values") or {})
        )
        exposed_controls = [
            c for c in (source.get("exposed_controls") or []) if c in mapped_roles
        ]
        dropped = sorted(set(dropped_values + dropped_models + dropped_loras + dropped_recommended))

        now = now_iso()
        preset = WorkflowPreset(
            preset_id=make_preset_id(),
            workflow_version_id=str(target_version.get("workflow_version_id", "")),
            workflow_id=str(target_version.get("workflow_id", "")),
            name=str(source.get("name", "Untitled Preset")),
            description=str(source.get("description", "")),
            values=values,
            model_choices=model_choices,
            lora_values=lora_values,
            exposed_controls=exposed_controls,
            recommended_values=recommended,
            favorite=bool(source.get("favorite", False)),
            tags=list(source.get("tags") or []),
            dropped_controls=dropped,
            created_at=now,
            updated_at=now,
        )
        return preset, dropped

    def copy_preset_to_version(
        self, preset_id: str, target_version_id: str
    ) -> dict[str, Any]:
        source = self.store.get_preset(preset_id)
        if source is None:
            raise WorkflowPresetNotFoundError(f"preset {preset_id!r} not found")
        target_version = self.store.get_version(target_version_id)
        if target_version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {target_version_id!r} not found"
            )
        preset, dropped = self._prepare_copy(source, target_version)
        stored = self.store.insert_preset(preset)
        workflow = self.store.get_workflow(str(target_version.get("workflow_id", "")))
        target_mapping = self.store.get_mapping_for_version(target_version_id)
        state = self.derive_preset_state(stored, target_version, target_mapping)
        enriched = self._enrich_preset(stored, workflow)
        return {
            "preset": enriched,
            "dropped_controls": dropped,
            "state": state.to_dict(),
        }

    def copy_presets_to_version(
        self, preset_ids: list[str], target_version_id: str
    ) -> list[dict[str, Any]]:
        target_version = self.store.get_version(target_version_id)
        if target_version is None:
            raise WorkflowVersionNotFoundError(
                f"workflow version {target_version_id!r} not found"
            )
        # Validate ALL copies first — nothing is written on any failure.
        prepared: list[tuple[dict[str, Any], WorkflowPreset, list[str]]] = []
        for preset_id in preset_ids:
            source = self.store.get_preset(preset_id)
            if source is None:
                raise PresetCopyError(f"preset {preset_id!r} not found")
            preset, dropped = self._prepare_copy(source, target_version)
            prepared.append((source, preset, dropped))
        results: list[dict[str, Any]] = []
        workflow = self.store.get_workflow(str(target_version.get("workflow_id", "")))
        target_mapping = self.store.get_mapping_for_version(target_version_id)
        for source, preset, dropped in prepared:
            stored = self.store.insert_preset(preset)
            state = self.derive_preset_state(stored, target_version, target_mapping)
            results.append({
                "preset": self._enrich_preset(stored, workflow),
                "dropped_controls": dropped,
                "state": state.to_dict(),
                "source_preset_id": source.get("preset_id"),
            })
        return results

    # ── enrichment ───────────────────────────────────────────────────────

    def _enrich_version(self, version: dict[str, Any]) -> dict[str, Any]:
        version_id = version.get("workflow_version_id", "")
        mapping = self.store.get_mapping_for_version(version_id)
        preset_count = len([
            p for p in self.store.list_presets()
            if p.get("workflow_version_id") == version_id
        ])
        enriched = dict(version)
        enriched["state"] = self.derive_version_state(version_id).to_dict()
        enriched["mapping_id"] = mapping.get("mapping_id") if mapping else None
        enriched["mapping"] = self._enrich_mapping(mapping) if mapping else None
        enriched["preset_count"] = preset_count
        return enriched

    def _enrich_preset(
        self, preset: dict[str, Any], workflow: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        enriched = dict(preset)
        version = self.store.get_version(str(preset.get("workflow_version_id", "")))
        mapping = self.store.get_mapping_for_version(
            str(preset.get("workflow_version_id", ""))
        )
        enriched["state"] = self.derive_preset_state(
            enriched, version, mapping
        ).to_dict()
        enriched["is_default"] = (
            bool(workflow) and workflow.get("default_preset_id") == preset.get("preset_id")
        )
        return enriched
