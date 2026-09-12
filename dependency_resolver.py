"""Workflow dependency resolution: models + custom nodes for a version.

The resolver reads the persisted stores (model library, custom-node
registry) — it never scans the filesystem and never triggers a model scan.
Resolution is best-effort: missing/bad inputs degrade to "missing"/"unknown"
states and every public method is guarded so it never raises.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from custom_node_registry import CustomNodeDiscovery, CustomNodeRegistryStore
from model_library import ModelLibraryStore, record_is_installed
from studio_store import StudioStoreError
from workflow_metadata import extract_workflow_model_refs

# Node classes that can never resolve to an installed pack: ComfyUI class
# keys are Python identifiers, so anything else (bare UUIDs from
# frontend-only proxy/subgraph nodes, display titles like
# "Label (rgthere)" or "easy int") is a graph artifact, not a dependency.
# These are reported separately (see unresolvable_classes) instead of
# "missing" so they never inflate the attention count or block readiness.
_CLASS_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_resolvable_class_name(value: Any) -> bool:
    return isinstance(value, str) and bool(_CLASS_NAME_RE.match(value))


def _group_node_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse per-class rows into one row per pack.

    Groups by pack identity; merges classes sorted and deduped. First-seen
    group order is preserved. Row dict shapes are unchanged.
    """
    grouped: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("name") or ""),
            str(row.get("state") or ""),
            str(row.get("install_path") or ""),
            str(row.get("installed_commit") or ""),
            str(row.get("required_revision") or ""),
            str(row.get("repository_url") or ""),
        )
        if key not in grouped:
            grouped[key] = dict(row)
            grouped[key]["classes"] = []
            order.append(key)
        for cls in row.get("classes") or []:
            if cls not in grouped[key]["classes"]:
                grouped[key]["classes"].append(cls)
    for key in order:
        try:
            grouped[key]["classes"] = sorted(grouped[key]["classes"], key=str)
        except Exception:
            pass
    return [grouped[key] for key in order]

# Canonical role -> best-known model folder (used for missing refs with no
# library record to fall back on).
_ROLE_TO_FOLDER: dict[str, str] = {
    "checkpoint": "checkpoints",
    "unet": "unet",
    "clip": "clip",
    "vae": "vae",
    "lora": "loras",
    "controlnet": "controlnet",
}


class DependencyResolver:
    """Resolve the model + custom-node dependencies declared by a version."""

    def __init__(self, library_root: str | Path, comfyui_root: str | Path) -> None:
        self.library_root = Path(library_root)
        self.comfyui_root = str(comfyui_root)
        self._models = ModelLibraryStore(self.library_root)
        self._registry = CustomNodeRegistryStore(self.library_root)
        self._node_discovery = CustomNodeDiscovery(self.library_root)
        self._discovery_cache: Optional[tuple[list, set[str]]] = None

    # ── model refs ────────────────────────────────────────────────────────

    def _model_refs(self, version: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect (role, filename) refs from the stack + executable prompt.

        Deduplicated by (role, filename); refs extracted from the executable
        prompt win over the model_stack entry for the same key.
        """
        dependency_metadata = (version or {}).get("dependency_metadata") or {}
        stack = dependency_metadata.get("model_stack") or {}
        refs: dict[tuple, dict[str, Any]] = {}
        if isinstance(stack, dict):
            for role, filenames in stack.items():
                if not isinstance(filenames, (list, tuple)):
                    continue
                for filename in filenames:
                    if isinstance(filename, str) and filename:
                        refs.setdefault(
                            (str(role), filename),
                            {"role": str(role), "filename": filename},
                        )
                    elif not isinstance(filename, str):
                        # Non-string ref: mark unknown during resolution.
                        refs[(str(role), "__non_str__")] = {
                            "role": str(role),
                            "filename": filename,
                        }
        prompt = (version or {}).get("executable_prompt") or {}
        if isinstance(prompt, dict):
            for ref in extract_workflow_model_refs(prompt):
                role = str(ref.get("role", ""))
                filename = ref.get("filename")
                if isinstance(filename, str) and filename:
                    refs[(role, filename)] = {"role": role, "filename": filename}
        return list(refs.values())

    @staticmethod
    def _most_recent(records: list[dict[str, Any]]) -> dict[str, Any]:
        def _ts(record: dict[str, Any]) -> str:
            return str(record.get("updated_at") or record.get("discovered_at") or "")

        return max(records, key=_ts)

    def resolve_model_refs(self, version: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve each model ref to installed / missing / wrong_version / unknown."""
        dependency_metadata = (version or {}).get("dependency_metadata") or {}
        required_models = dependency_metadata.get("required_models") or {}
        if not isinstance(required_models, dict):
            required_models = {}
        results: list[dict[str, Any]] = []
        for ref in self._model_refs(version):
            role = ref.get("role", "")
            filename = ref.get("filename")
            if not isinstance(filename, str) or not filename:
                results.append(
                    {
                        "key": f"{role}|{filename}",
                        "role": role,
                        "filename": str(filename),
                        "state": "unknown",
                        "model_id": None,
                        "folder": None,
                        "hash": None,
                        "size": None,
                        "local_path": None,
                        "source_urls": [],
                        "installed": False,
                    }
                )
                continue
            try:
                records = self._models.records_by_filename(filename)
            except (StudioStoreError, OSError):
                results.append(
                    {
                        "key": f"{role}|{filename}",
                        "role": role,
                        "filename": str(filename),
                        "state": "unknown",
                        "model_id": None,
                        "folder": None,
                        "hash": None,
                        "size": None,
                        "local_path": None,
                        "source_urls": [],
                        "installed": False,
                        "reason": "library store unreadable",
                    }
                )
                continue
            installed_records = [r for r in records if record_is_installed(r)]
            req_hash = required_models.get(filename)
            if installed_records:
                rec = installed_records[0]
                state = "installed"
                required_hash = req_hash if isinstance(req_hash, str) else ""
                if required_hash and rec.get("hash") != required_hash:
                    state = "wrong_version"
                results.append(
                    {
                        "key": f"{role}|{filename}",
                        "role": role,
                        "filename": filename,
                        "state": state,
                        "model_id": rec.get("model_id"),
                        "folder": rec.get("folder"),
                        "hash": rec.get("hash"),
                        "size": rec.get("size"),
                        "local_path": rec.get("local_path"),
                        "source_urls": list(rec.get("source_urls") or []),
                        "installed": True,
                        "required_hash": required_hash if state == "wrong_version" else None,
                    }
                )
                continue
            if records:
                rec = self._most_recent(records)
                results.append(
                    {
                        "key": f"{role}|{filename}",
                        "role": role,
                        "filename": filename,
                        "state": "missing",
                        "model_id": None,
                        "folder": rec.get("folder"),
                        "hash": rec.get("hash"),
                        "size": None,
                        "local_path": None,
                        "source_urls": list(rec.get("source_urls") or []),
                        "installed": False,
                    }
                )
                continue
            results.append(
                {
                    "key": f"{role}|{filename}",
                    "role": role,
                    "filename": filename,
                    "state": "missing",
                    "model_id": None,
                    "folder": _ROLE_TO_FOLDER.get(role, "unknown"),
                    "hash": None,
                    "size": None,
                    "local_path": None,
                    "source_urls": [],
                    "installed": False,
                }
            )
        return results

    # ── custom node resolution ────────────────────────────────────────────

    def _ensure_discovery(self) -> tuple[list, set[str]]:
        if self._discovery_cache is None:
            records, core = self._node_discovery.discover(self.comfyui_root)
            self._discovery_cache = (records, core)
        return self._discovery_cache

    def resolve_custom_nodes(self, version: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve required node classes, grouped one row per pack.

        Graph artifacts (non-identifier class strings) are excluded here
        and reported via unresolvable_classes instead.
        """
        dependency_metadata = (version or {}).get("dependency_metadata") or {}
        node_classes = dependency_metadata.get("node_classes") or []
        requirements = dependency_metadata.get("custom_node_requirements") or {}
        if not isinstance(node_classes, list):
            node_classes = []
        if not isinstance(requirements, dict):
            requirements = {}
        _records, core = self._ensure_discovery()
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for class_type in node_classes:
            cls = str(class_type)
            if cls in seen:
                continue
            seen.add(cls)
            if not _is_resolvable_class_name(cls):
                continue  # graph artifact; reported via unresolvable_classes
            req = requirements.get(cls) or {}
            if not isinstance(req, dict):
                req = {}
            required_revision = str(req.get("revision") or "")
            if cls in core:
                results.append(
                    {
                        "name": "ComfyUI core",
                        "state": "installed",
                        "install_path": "",
                        "installed_commit": "",
                        "required_revision": required_revision,
                        "repository_url": "",
                        "classes": [cls],
                    }
                )
                continue
            try:
                record = self._registry.record_by_class(cls)
            except (StudioStoreError, OSError):
                results.append(
                    {
                        "name": req.get("name") or req.get("repository") or cls,
                        "state": "missing",
                        "install_path": "",
                        "installed_commit": "",
                        "required_revision": required_revision,
                        "repository_url": req.get("repository") or "",
                        "classes": [cls],
                    }
                )
                continue
            if record is not None:
                state = "installed"
                if required_revision and record.get("installed_commit") != required_revision:
                    state = "wrong_revision"
                results.append(
                    {
                        "name": record.get("name", cls),
                        "state": state,
                        "install_path": record.get("install_path", ""),
                        "installed_commit": record.get("installed_commit", ""),
                        "required_revision": required_revision,
                        "repository_url": record.get("repo_url", ""),
                        "classes": [cls],
                    }
                )
                continue
            results.append(
                {
                    "name": req.get("name") or req.get("repository") or cls,
                    "state": "missing",
                    "install_path": "",
                    "installed_commit": "",
                    "required_revision": required_revision,
                    "repository_url": req.get("repository") or "",
                    "classes": [cls],
                }
            )
        return _group_node_rows(results)

    def unresolvable_classes(self, version: dict[str, Any]) -> list[dict[str, Any]]:
        """Graph-artifact class strings that can never resolve to a pack.

        UUIDs from frontend-only proxy/subgraph nodes and display titles
        recorded as types are not installable dependencies, so they are
        excluded from missing/attention counts. Never raises.
        """
        try:
            dependency_metadata = (version or {}).get("dependency_metadata") or {}
            node_classes = dependency_metadata.get("node_classes") or []
            if not isinstance(node_classes, list):
                return []
            out: list[dict[str, Any]] = []
            seen: set[str] = set()
            for class_type in node_classes:
                cls = str(class_type)
                if cls in seen:
                    continue
                seen.add(cls)
                if _is_resolvable_class_name(cls):
                    continue
                out.append(
                    {
                        "name": cls,
                        "classes": [cls],
                        "reason": "graph artifact, not a registered node class",
                    }
                )
            return out
        except Exception:
            return []

    # ── aggregate ─────────────────────────────────────────────────────────

    def resolve_version(self, version: dict[str, Any]) -> dict[str, Any]:
        """Full dependency report: models + custom nodes + summary.

        Graph artifacts that can never resolve are listed under
        ``unresolvable`` and excluded from the summary counts.
        """
        models = self.resolve_model_refs(version)
        custom_nodes = self.resolve_custom_nodes(version)
        m_installed = sum(1 for m in models if m["state"] == "installed")
        m_missing = sum(1 for m in models if m["state"] == "missing")
        m_wrong = sum(1 for m in models if m["state"] == "wrong_version")
        m_unknown = sum(1 for m in models if m["state"] == "unknown")
        n_installed = sum(1 for n in custom_nodes if n["state"] == "installed")
        n_missing = sum(1 for n in custom_nodes if n["state"] == "missing")
        n_wrong = sum(1 for n in custom_nodes if n["state"] == "wrong_revision")
        installed = m_installed + n_installed
        missing = m_missing + n_missing
        wrong_version = m_wrong + n_wrong
        unknown = m_unknown
        attention = missing + wrong_version + unknown
        return {
            "models": models,
            "custom_nodes": custom_nodes,
            "unresolvable": self.unresolvable_classes(version),
            "summary": {
                "installed": installed,
                "missing": missing,
                "wrong_version": wrong_version,
                "unknown": unknown,
                "attention": attention,
                "ready": attention == 0,
            },
        }

    def reasons_for(self, version: dict[str, Any]) -> list[str]:
        """Exact human-readable reasons for every unresolved dependency.

        Never raises; a malformed version dict yields ``[]``.
        """
        reasons: list[str] = []
        try:
            for entry in self.resolve_model_refs(version):
                state = entry.get("state")
                if state == "missing":
                    reasons.append(
                        f"missing model '{entry.get('filename')}' "
                        f"({entry.get('folder') or 'unknown'})"
                    )
                elif state == "wrong_version":
                    reasons.append(
                        f"installed model '{entry.get('filename')}' hash does not "
                        f"match required {entry.get('required_hash') or ''}"
                    )
                elif state == "unknown":
                    reasons.append(
                        f"model dependency '{entry.get('key')}' could not be identified"
                    )
            for entry in self.resolve_custom_nodes(version):
                state = entry.get("state")
                if state == "missing":
                    reasons.append(
                        f"required custom node '{entry.get('name')}' not installed"
                    )
                elif state == "wrong_revision":
                    reasons.append(
                        f"installed custom node '{entry.get('name')}' "
                        f"(commit {entry.get('installed_commit')}) differs from "
                        f"required revision {entry.get('required_revision')}"
                    )
        except Exception:
            pass
        return reasons
