"""Persistence layer for the Workflow domain.

``WorkflowDomainStore`` manages five JSON collections (one file each) built
on the shared ``StudioJsonStore`` (thread-safe, atomic tmp+os.replace):

* ``.studio_workflows.json``
* ``.studio_workflow_versions.json``
* ``.studio_workflow_mappings.json``
* ``.studio_workflow_folders.json``

Immutability rules enforced here:

* WorkflowVersion records have NO direct update/delete path — only
  ``insert_version`` (workflow deletion cascades them).
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
    WorkflowDomainValidationError,
    WorkflowVersion,
)

WORKFLOWS_FILENAME = ".studio_workflows.json"
VERSIONS_FILENAME = ".studio_workflow_versions.json"
MAPPINGS_FILENAME = ".studio_workflow_mappings.json"
FOLDERS_FILENAME = ".studio_workflow_folders.json"


class WorkflowDomainStore:
    """File-backed store for Workflow, WorkflowVersion, Mapping, Folder."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self.workflows = StudioJsonStore(self._root / WORKFLOWS_FILENAME)
        self.versions = StudioJsonStore(self._root / VERSIONS_FILENAME)
        self.mappings = StudioJsonStore(self._root / MAPPINGS_FILENAME)
        self.folders = StudioJsonStore(self._root / FOLDERS_FILENAME)
        # Serializes multi-collection transactions within this process so
        # imports and cascaded deletes cannot interleave across the four
        # stores.
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

    def insert_workflow(
        self,
        workflow: Workflow,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert one durable Workflow record.

        ``Workflow`` is the compatibility dataclass for the original domain
        fields.  The wrapper-owned configuration is deliberately carried as
        additional JSON fields so it remains one record in the same durable
        authority without introducing a second store or a migration layer.
        The uniqueness check lives in the mutator, not in a preceding read.
        """
        data = workflow.to_dict()
        if fields:
            data.update(fields)

        def _mutate(rows: list[dict[str, Any]]) -> None:
            if any(row.get("workflow_id") == data["workflow_id"] for row in rows):
                raise WorkflowDomainValidationError(
                    f"workflow {data['workflow_id']!r} already exists"
                )
            rows.append(data)

        self.workflows.update(_mutate)
        return data

    def update_workflow(self, workflow: Workflow) -> dict[str, Any]:
        data = workflow.to_dict()
        result: dict[str, Any] = {}

        def _mutate(rows: list[dict[str, Any]]) -> None:
            for index, existing in enumerate(rows):
                if existing.get("workflow_id") != data["workflow_id"]:
                    continue
                # Preserve wrapper-owned fields unknown to the compatibility
                # dataclass.  Metadata edits must never erase saved config.
                merged = dict(existing)
                merged.update(data)
                rows[index] = merged
                result.update(merged)
                return
            raise WorkflowDomainValidationError(
                f"workflow {data['workflow_id']!r} does not exist"
            )

        self.workflows.update(_mutate)
        return result

    def update_workflow_fields(
        self,
        workflow_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically autosave wrapper-owned fields on one Workflow record."""
        result: dict[str, Any] = {}

        def _mutate(rows: list[dict[str, Any]]) -> None:
            for index, existing in enumerate(rows):
                if existing.get("workflow_id") != workflow_id:
                    continue
                merged = dict(existing)
                merged.update(fields)
                rows[index] = merged
                result.update(merged)
                return
            raise WorkflowDomainValidationError(
                f"workflow {workflow_id!r} does not exist"
            )

        self.workflows.update(_mutate)
        return result

    # ── Workflow Folders ─────────────────────────────────────────────────

    def list_folders(self) -> list[dict[str, Any]]:
        return self.folders.read()

    def insert_folder(self, path: str) -> dict[str, str]:
        data = {"path": path}
        result: dict[str, str] = {}

        def _mutate(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                if row.get("path") == path:
                    result.update({"path": str(row.get("path", path))})
                    return
            rows.append(data)
            result.update(data)

        self.folders.update(_mutate)
        return result

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a Workflow and all records owned by its versions.

        Each collection is changed through its atomic read-modify-write
        primitive.  The workflow row is removed last so a successful cascade
        cannot leave a live parent pointing at deleted children.
        """
        with self._import_lock:
            if self.get_workflow(workflow_id) is None:
                return False

            version_ids = {
                str(version.get("workflow_version_id", ""))
                for version in self.versions.read()
                if version.get("workflow_id") == workflow_id
                and version.get("workflow_version_id")
            }

            def remove_versions(rows: list[dict[str, Any]]) -> None:
                rows[:] = [
                    row for row in rows if row.get("workflow_id") != workflow_id
                ]

            def remove_mappings(rows: list[dict[str, Any]]) -> None:
                rows[:] = [
                    row
                    for row in rows
                    if row.get("workflow_version_id") not in version_ids
                ]

            def remove_workflow(rows: list[dict[str, Any]]) -> None:
                rows[:] = [
                    row for row in rows if row.get("workflow_id") != workflow_id
                ]

            self.versions.update(remove_versions)
            self.mappings.update(remove_mappings)
            self.workflows.update(remove_workflow)
        return True

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


    # ── batch access helper (for enrichment) ─────────────────────────────

    def snapshot_all(self) -> dict[str, list[dict[str, Any]]]:
        """Read every collection once. Convenience for list endpoints."""
        return {
            "workflows": self.workflows.read(),
            "versions": self.versions.read(),
            "mappings": self.mappings.read(),
                        "folders": self.folders.read(),
        }

    # ── atomic multi-collection import transaction ────────────────────────

    def commit_import_transaction(
        self,
        workflow: Workflow,
        version: WorkflowVersion,
        mapping: Mapping,
    ) -> dict[str, Any]:
        """Insert a complete imported Workflow graph atomically.

        Either ALL of {Workflow, Version, Mapping} land, or
        NOTHING does — a failure at any step compensates by removing exactly
        the records already appended, restoring byte-identical collections.

        Mechanics (narrowest coherent atomic mechanism over the existing
        per-store atomic writes):

        * one exclusive in-process import lock serializes concurrent
          imports against each other;
        * all uniqueness checks run up-front AND again inside each
          per-store mutator (mutators execute under that store's own lock,
          so the write-time checks are race-free);
        * records are applied versions → mappings → workflow,
          with the Workflow row LAST as the commit point;
        * on any exception the compensation pass deletes exactly the ids
          this transaction added; each removal is itself an atomic
          read-modify-write, so unrelated concurrent appends survive.
        """
        wf_data = workflow.to_dict()
        ver_data = version.to_dict()
        mp_data = mapping.to_dict()
        if not wf_data.get("workflow_id"):
            raise WorkflowDomainValidationError("import transaction requires a workflow id")
        if not ver_data.get("workflow_version_id"):
            raise WorkflowDomainValidationError("import transaction requires a version id")
        if mp_data.get("workflow_version_id") != ver_data["workflow_version_id"]:
            raise WorkflowDomainValidationError(
                "import mapping must reference the imported version"
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
                _append_unique(
                    self.workflows,
                    "workflow_id",
                    wf_data["workflow_id"],
                    wf_data,
                    WorkflowDomainValidationError(
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
        }
        for id_key, record_id in reversed(added):
            store = stores[id_key]

            def _remove(rows: list[dict[str, Any]], key: str = id_key, rid: str = record_id) -> None:
                rows[:] = [r for r in rows if r.get(key) != rid]

            try:
                store.update(_remove)
            except Exception:
                pass
