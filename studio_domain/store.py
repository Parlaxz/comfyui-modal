"""Persistence layer for the Workflow domain.

``WorkflowDomainStore`` manages four JSON collections (one file each) built
on the shared ``StudioJsonStore`` (thread-safe, atomic tmp+os.replace):

* ``.studio_workflows.json``
* ``.studio_workflow_versions.json``
* ``.studio_workflow_mappings.json``
* ``.studio_workflow_presets.json``

Immutability rules enforced here:

* WorkflowVersion records have NO update/delete path — only ``insert_version``.
* ``insert_version`` raises ``ImmutableVersionError`` if the id already exists.
* Exactly ONE Mapping per WorkflowVersion — ``set_mapping_for_version``
  replaces the previous mapping for that version inside one atomic update.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from studio_store import StudioJsonStore

from .models import (
    ImmutableVersionError,
    Mapping,
    MappingAlreadyExistsError,
    Workflow,
    WorkflowPreset,
    WorkflowPresetValidationError,
    WorkflowVersion,
)

WORKFLOWS_FILENAME = ".studio_workflows.json"
VERSIONS_FILENAME = ".studio_workflow_versions.json"
MAPPINGS_FILENAME = ".studio_workflow_mappings.json"
PRESETS_FILENAME = ".studio_workflow_presets.json"


class WorkflowDomainStore:
    """File-backed store for Workflow, WorkflowVersion, Mapping, WorkflowPreset."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self.workflows = StudioJsonStore(self._root / WORKFLOWS_FILENAME)
        self.versions = StudioJsonStore(self._root / VERSIONS_FILENAME)
        self.mappings = StudioJsonStore(self._root / MAPPINGS_FILENAME)
        self.presets = StudioJsonStore(self._root / PRESETS_FILENAME)

    @property
    def root(self) -> Path:
        return self._root

    # ── generic helpers ──────────────────────────────────────────────────

    def _find(
        self, store: StudioJsonStore, id_key: str, record_id: str
    ) -> dict | None:
        for item in store.read():
            if item.get(id_key) == record_id:
                return item
        return None

    def _replace_in_list(self, data: list[dict], id_key: str, item: dict) -> None:
        for i, existing in enumerate(data):
            if existing.get(id_key) == item.get(id_key):
                data[i] = item
                return
        data.append(item)

    # ── Workflows ────────────────────────────────────────────────────────

    def list_workflows(self) -> list[dict[str, Any]]:
        return self.workflows.read()

    def get_workflow(self, workflow_id: str) -> dict | None:
        return self._find(self.workflows, "workflow_id", workflow_id)

    def insert_workflow(self, workflow: Workflow) -> dict[str, Any]:
        data = workflow.to_dict()
        if self._find(self.workflows, "workflow_id", data["workflow_id"]) is not None:
            raise WorkflowPresetValidationError(
                f"workflow {data['workflow_id']!r} already exists"
            )
        self.workflows.update(lambda rows: rows.append(data))
        return data

    def update_workflow(self, workflow: Workflow) -> dict[str, Any]:
        data = workflow.to_dict()
        if self._find(self.workflows, "workflow_id", data["workflow_id"]) is None:
            raise WorkflowPresetValidationError(
                f"workflow {data['workflow_id']!r} does not exist"
            )
        self.workflows.update(
            lambda rows: self._replace_in_list(rows, "workflow_id", data)
        )
        return data

    # ── Workflow Versions (immutable) ────────────────────────────────────

    def list_versions(self) -> list[dict[str, Any]]:
        return self.versions.read()

    def list_versions_for_workflow(self, workflow_id: str) -> list[dict[str, Any]]:
        return [
            v
            for v in self.versions.read()
            if v.get("workflow_id") == workflow_id
        ]

    def get_version(self, workflow_version_id: str) -> dict | None:
        return self._find(self.versions, "workflow_version_id", workflow_version_id)

    def insert_version(self, version: WorkflowVersion) -> dict[str, Any]:
        """Write a version record. Raises ``ImmutableVersionError`` when a
        record with the same id already exists (versions are write-once)."""
        data = version.to_dict()
        if self._find(
            self.versions, "workflow_version_id", data["workflow_version_id"]
        ) is not None:
            raise ImmutableVersionError(
                f"workflow version {data['workflow_version_id']!r} already exists "
                "and is immutable"
            )
        self.versions.update(lambda rows: rows.append(data))
        return data

    # ── Mappings (exactly one per version) ───────────────────────────────

    def list_mappings(self) -> list[dict[str, Any]]:
        return self.mappings.read()

    def get_mapping(self, mapping_id: str) -> dict | None:
        return self._find(self.mappings, "mapping_id", mapping_id)

    def get_mapping_for_version(self, workflow_version_id: str) -> dict | None:
        for item in self.mappings.read():
            if item.get("workflow_version_id") == workflow_version_id:
                return item
        return None

    def insert_mapping(self, mapping: Mapping) -> dict[str, Any]:
        """Insert the single Mapping for a Workflow Version.

        Exactly one Mapping may exist per Workflow Version; once inserted
        it is immutable. Raises ``MappingAlreadyExistsError`` when a
        Mapping already exists for the version — it is never replaced.
        The existence check and append happen inside one atomic update.
        """
        data = mapping.to_dict()
        version_id = data["workflow_version_id"]

        def _mutate(rows: list[dict]) -> None:
            for row in rows:
                if row.get("workflow_version_id") == version_id:
                    raise MappingAlreadyExistsError(
                        f"workflow version {version_id!r} already has an "
                        "immutable mapping"
                    )
            rows.append(data)

        self.mappings.update(_mutate)
        return data

    # ── Presets ──────────────────────────────────────────────────────────

    def list_presets(self) -> list[dict[str, Any]]:
        return self.presets.read()

    def get_preset(self, preset_id: str) -> dict | None:
        return self._find(self.presets, "preset_id", preset_id)

    def insert_preset(self, preset: WorkflowPreset) -> dict[str, Any]:
        data = preset.to_dict()
        if self._find(self.presets, "preset_id", data["preset_id"]) is not None:
            raise WorkflowPresetValidationError(
                f"preset {data['preset_id']!r} already exists"
            )
        self.presets.update(lambda rows: rows.append(data))
        return data

    def update_preset(self, preset: WorkflowPreset) -> dict[str, Any]:
        data = preset.to_dict()
        if self._find(self.presets, "preset_id", data["preset_id"]) is None:
            raise WorkflowPresetValidationError(
                f"preset {data['preset_id']!r} does not exist"
            )
        self.presets.update(
            lambda rows: self._replace_in_list(rows, "preset_id", data)
        )
        return data

    def delete_preset(self, preset_id: str) -> None:
        def _mutate(rows: list[dict]) -> None:
            rows[:] = [r for r in rows if r.get("preset_id") != preset_id]

        self.presets.update(_mutate)

    # ── batch access helper (for enrichment) ─────────────────────────────

    def snapshot_all(self) -> dict[str, list[dict[str, Any]]]:
        """Read every collection once. Convenience for list endpoints."""
        return {
            "workflows": self.workflows.read(),
            "versions": self.versions.read(),
            "mappings": self.mappings.read(),
            "presets": self.presets.read(),
        }
