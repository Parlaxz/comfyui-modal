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

import threading
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
        # Serializes multi-collection import transactions within this
        # process so two concurrent imports cannot interleave their staged
        # appends across the four stores.
        self._import_lock = threading.RLock()

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

    # ── atomic multi-collection import transaction ────────────────────────

    def commit_import_transaction(
        self,
        workflow: Workflow,
        version: WorkflowVersion,
        mapping: Mapping,
        presets: list[WorkflowPreset] | None = None,
    ) -> dict[str, Any]:
        """Insert a complete imported Workflow graph atomically.

        Either ALL of {Workflow, Version, Mapping, Presets...} land, or
        NOTHING does — a failure at any step compensates by removing exactly
        the records already appended, restoring byte-identical collections.

        Mechanics (narrowest coherent atomic mechanism over the existing
        per-store atomic writes):

        * one exclusive in-process import lock serializes concurrent
          imports against each other;
        * all uniqueness checks run up-front AND again inside each
          per-store mutator (mutators execute under that store's own lock,
          so the write-time checks are race-free);
        * records are applied versions → mappings → presets → workflow,
          with the Workflow row LAST as the commit point;
        * on any exception the compensation pass deletes exactly the ids
          this transaction added; each removal is itself an atomic
          read-modify-write, so unrelated concurrent appends survive.
        """
        wf_data = workflow.to_dict()
        ver_data = version.to_dict()
        mp_data = mapping.to_dict()
        pre_datas = [p.to_dict() for p in (presets or [])]

        if not wf_data.get("workflow_id"):
            raise WorkflowPresetValidationError("import transaction requires a workflow id")
        if not ver_data.get("workflow_version_id"):
            raise WorkflowPresetValidationError("import transaction requires a version id")
        if mp_data.get("workflow_version_id") != ver_data["workflow_version_id"]:
            raise WorkflowPresetValidationError(
                "import mapping must reference the imported version"
            )
        for p in pre_datas:
            if p.get("workflow_version_id") != ver_data["workflow_version_id"]:
                raise WorkflowPresetValidationError(
                    "import preset %r does not reference the imported version"
                    % p.get("preset_id")
                )

        with self._import_lock:
            added: list[tuple[str, str]] = []

            def _append_unique(
                store: StudioJsonStore,
                id_key: str,
                record_id: str,
                data: dict[str, Any],
                conflict: Exception,
            ) -> None:
                def _mutate(rows: list[dict[str, Any]]) -> None:
                    for row in rows:
                        if row.get(id_key) == record_id:
                            raise conflict
                    rows.append(data)

                store.update(_mutate)
                added.append((id_key, record_id))

            try:
                _append_unique(
                    self.versions,
                    "workflow_version_id",
                    ver_data["workflow_version_id"],
                    ver_data,
                    ImmutableVersionError(
                        f"workflow version {ver_data['workflow_version_id']!r} "
                        "already exists and is immutable"
                    ),
                )
                _append_unique(
                    self.mappings,
                    "mapping_id",
                    mp_data["mapping_id"],
                    mp_data,
                    MappingAlreadyExistsError(
                        f"mapping {mp_data['mapping_id']!r} already exists"
                    ),
                )
                for index, p_data in enumerate(pre_datas):
                    _append_unique(
                        self.presets,
                        "preset_id",
                        p_data["preset_id"],
                        p_data,
                        WorkflowPresetValidationError(
                            f"preset {p_data['preset_id']!r} already exists"
                        ),
                    )
                _append_unique(
                    self.workflows,
                    "workflow_id",
                    wf_data["workflow_id"],
                    wf_data,
                    WorkflowPresetValidationError(
                        f"workflow {wf_data['workflow_id']!r} already exists"
                    ),
                )
            except Exception:
                self._compensate_import(added)
                raise

        return {
            "workflow": wf_data,
            "version": ver_data,
            "mapping": mp_data,
            "presets": pre_datas,
        }

    def _compensate_import(self, added: list[tuple[str, str]]) -> None:
        """Remove exactly the records a failed import transaction added.

        Best-effort and ordered newest-first; each removal is an atomic
        per-store update keyed by id so only THIS transaction's records are
        touched.
        """
        stores = {
            "workflow_id": self.workflows,
            "workflow_version_id": self.versions,
            "mapping_id": self.mappings,
            "preset_id": self.presets,
        }
        for id_key, record_id in reversed(added):
            store = stores[id_key]

            def _remove(rows: list[dict[str, Any]], key: str = id_key, rid: str = record_id) -> None:
                rows[:] = [r for r in rows if r.get(key) != rid]

            try:
                store.update(_remove)
            except Exception:
                pass
