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
from model_manifest import WORKFLOW_ROLE_FOLDERS
from model_library import ModelLibraryStore, record_is_installed
from studio_store import StudioStoreError
from workflow_metadata import (
    extract_ui_graph_model_refs,
    extract_workflow_model_refs,
    iter_graph_nodes,
)

# Node classes that can never resolve to an installed pack: ComfyUI class
# keys are Python identifiers, so anything else (bare UUIDs from
# frontend-only proxy/subgraph nodes, display titles like
# "Label (rgthere)" or "easy int") is a graph artifact, not a dependency.
# These are reported separately (see unresolvable_classes) instead of
# "missing" so they never inflate the attention count or block readiness.
_CLASS_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Frontend-only virtual nodes are never installable dependencies. ComfyUI
# drops them from the executable prompt, but skip them defensively so they can
# never become a fake "missing pack" row.
_VIRTUAL_NODE_CLASSES = frozenset({
    "reroute",
    "note",
    "primitive",
    "primitivenode",
    "workflownode",
    "subgraph",
    "groupnode",
})


def _is_resolvable_class_name(value: Any) -> bool:
    return isinstance(value, str) and bool(_CLASS_NAME_RE.match(value))


def _identity_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _pack_identity_of_node(node: Any) -> dict[str, str]:
    """Return a stored UI/API node's non-core pack identity, or {}.

    Mirrors the capture-side extraction (``studio_domain.graph``): an explicit
    string ``properties.cnr_id`` or ``properties.aux_id`` (plus ``ver``)
    counts, and core ids are ignored so they never become a fake pack.
    """
    if not isinstance(node, dict):
        return {}
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return {}
    cnr_id = _identity_text(properties.get("cnr_id"))
    if cnr_id.lower() in ("comfy-core", "comfyui-core"):
        cnr_id = ""
    aux_id = _identity_text(properties.get("aux_id"))
    version = _identity_text(
        properties.get("ver")
        or properties.get("selected_version")
        or properties.get("version")
    )
    if not cnr_id and not aux_id:
        return {}
    identity: dict[str, str] = {}
    if cnr_id:
        identity["cnr_id"] = cnr_id
    if aux_id:
        identity["aux_id"] = aux_id
    if version:
        identity["version"] = version
    return identity


def _merge_identity(
    current: dict[str, str], incoming: dict[str, str]
) -> dict[str, str]:
    if not current:
        return dict(incoming)
    merged = dict(current)
    for key in ("cnr_id", "aux_id", "version"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    return merged


def _has_nonempty_collection(value: Any) -> bool:
    """True when a UI graph node's inputs/outputs field carries content."""
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return False


def _graph_virtual_class_names(version: dict[str, Any]) -> set[str]:
    """Class types whose stored UI graph node is a frontend-only virtual node.

    A node qualifies only when it records no ``cnr_id``/``aux_id`` pack
    identity AND both its UI ``inputs`` and ``outputs`` are empty. ComfyUI
    serialises JS-only virtual panels (``isVirtualNode`` registrations) exactly
    that way, while any node that consumes or produces data carries a
    non-empty collection. This is a shape classifier, not a class allowlist,
    so a new virtual panel is handled without code changes. Nested
    group/subgraph nodes are classified too.
    """
    if not isinstance(version, dict):
        return set()
    virtual: set[str] = set()
    real: set[str] = set()
    for key in ("graph_json", "static_graph"):
        for node in iter_graph_nodes(version.get(key)):
            node_type = node.get("type")
            if not isinstance(node_type, str) or not node_type:
                continue
            if _pack_identity_of_node(node):
                real.add(node_type)  # has pack identity: never a virtual panel
                continue
            if _has_nonempty_collection(node.get("inputs")):
                real.add(node_type)
                continue
            if _has_nonempty_collection(node.get("outputs")):
                real.add(node_type)
                continue
            virtual.add(node_type)
    return virtual - real


def _executable_class_names(version: dict[str, Any]) -> set[str]:
    """Class types actually present in the version's executable API prompt."""
    out: set[str] = set()
    prompt = (version or {}).get("executable_prompt") or {}
    if isinstance(prompt, dict):
        for node in prompt.values():
            if isinstance(node, dict) and node.get("class_type"):
                out.add(str(node["class_type"]))
    return out


def _executable_consuming_classes(version: dict[str, Any]) -> set[str]:
    """Executable classes that actually consume an input binding.

    UI-only virtual panels can survive capture as no-op API prompt entries
    with empty ``inputs`` (ComfyUI serialises ``isVirtualNode`` registrations
    that way). A class whose every executable entry is input-free is treated
    as non-consuming so the graph shape classifier can still recognise the
    panel; a class with at least one real input binding is never dropped.
    """
    out: set[str] = set()
    prompt = (version or {}).get("executable_prompt") or {}
    if isinstance(prompt, dict):
        for node in prompt.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            if not class_type:
                continue
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and inputs:
                out.add(str(class_type))
    return out


def _stored_graph_node_classes(version: dict[str, Any]) -> list[str]:
    """Class types recorded on a stored version's UI/static graph nodes.

    Order-preserving and deduped; checks both the ``graph_json`` field and its
    ``static_graph`` alias, including nodes nested in group/subgraph
    containers. Never raises on malformed graphs.
    """
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(version, dict):
        return out
    for key in ("graph_json", "static_graph"):
        for node in iter_graph_nodes(version.get(key)):
            node_type = node.get("type")
            if not isinstance(node_type, str) or not node_type:
                continue
            if node_type in seen:
                continue
            seen.add(node_type)
            out.append(node_type)
    return out


def _version_node_classes(version: dict[str, Any]) -> list[str]:
    """Union of declared dependency classes and stored graph node types.

    ``dependency_metadata.node_classes`` only reflects the executable API
    prompt, so UI-only / unknown / missing-code nodes never appear there.
    Captures now union the graph at extraction time, but older stored versions
    predate both that union and ``custom_node_requirements``; their persisted
    UI/static graph still records the node types, so merge them here. True
    virtual empty panels are still excluded downstream by the shape classifier.
    """
    out: list[str] = []
    seen: set[str] = set()
    dependency_metadata = (version or {}).get("dependency_metadata")
    if not isinstance(dependency_metadata, dict):
        dependency_metadata = {}
    declared = dependency_metadata.get("node_classes") or []
    if isinstance(declared, list):
        for class_type in declared:
            cls = str(class_type)
            if cls in seen:
                continue
            seen.add(cls)
            out.append(cls)
    for cls in _stored_graph_node_classes(version):
        if cls not in seen:
            seen.add(cls)
            out.append(cls)
    return out


def _class_identity_from_metadata(
    cls: str,
    requirements: dict[str, Any],
    graph_identity_by_class: dict[str, dict[str, str]],
) -> tuple[str, str]:
    """Best-known ``(cnr_id, aux_id)`` identity for a required class."""
    req = requirements.get(cls) or {}
    if not isinstance(req, dict):
        req = {}
    cnr_id = str(req.get("cnr_id") or "")
    aux_id = str(req.get("aux_id") or "")
    if not cnr_id and not aux_id:
        graph_identity = graph_identity_by_class.get(cls) or {}
        cnr_id = str(graph_identity.get("cnr_id") or "")
        aux_id = str(graph_identity.get("aux_id") or "")
    return cnr_id, aux_id


def _is_virtual_workflow_class(
    cls: str,
    *,
    executable_classes: set[str],
    graph_virtual_classes: set[str],
    core: set[str],
    has_identity: bool,
    record_exists: bool,
) -> bool:
    """True for a valid class that is only a frontend virtual panel.

    The class must be absent from the executable prompt, core, registry and
    pack identities, and its stored graph node must match the empty
    inputs/outputs virtual shape. Such panels are not installable dependencies
    and must never inflate missing/attention.
    """
    return (
        not has_identity
        and not record_exists
        and cls not in core
        and cls not in executable_classes
        and cls in graph_virtual_classes
    )


def _class_pack_identities_from_graph(
    version: dict[str, Any]
) -> dict[str, dict[str, str]]:
    """Derive class -> pack identity from a stored version's UI graph.

    Older stored versions predate ``custom_node_requirements`` in
    ``dependency_metadata``, but their persisted UI graph still records
    ``properties.cnr_id``/``aux_id``/``ver`` per node. Indexing node ``type``
    -> identity lets the resolver recover the pack for those versions without
    guessing. Checks both the version's ``graph_json`` field and the
    ``static_graph`` alias, including nodes nested in group/subgraph
    containers.
    """
    out: dict[str, dict[str, str]] = {}
    if not isinstance(version, dict):
        return out
    for key in ("graph_json", "static_graph"):
        for node in iter_graph_nodes(version.get(key)):
            node_type = node.get("type")
            if not isinstance(node_type, str) or not node_type:
                continue
            identity = _pack_identity_of_node(node)
            if identity:
                out[node_type] = _merge_identity(out.get(node_type, {}), identity)
    return out


# Conservative merge order for a physical pack's rows: a pack is only as good
# as its worst member, so a missing class can never be masked by an installed
# one, and a revision mismatch is never hidden by a matching class.
_NODE_STATE_SEVERITY = {"installed": 1, "wrong_revision": 2, "missing": 3}

# Row fields merged across the members of one physical pack. Each keeps the
# first nonempty value seen; nothing is invented.
_PACK_MERGE_FIELDS = (
    "name",
    "install_path",
    "installed_commit",
    "required_revision",
    "repository_url",
    "cnr_id",
    "aux_id",
    "version",
)

# Identity fields weaker than a physical install path, strongest first. They
# group a path-less row and let it join an installed pack it identifies.
_PACK_IDENTITY_FIELDS = (
    ("cnr", "cnr_id"),
    ("aux", "aux_id"),
    ("repo", "repository_url"),
)


def _normalized_identity(value: Any) -> str:
    return _identity_text(value).casefold()


def _normalized_install_path(value: Any) -> str:
    text = _identity_text(value).replace("\\", "/")
    if not text:
        return ""
    text = re.sub(r"/+", "/", text)
    if len(text) > 1:
        text = text.rstrip("/")
    return text.casefold()


def _pack_group_key(row: dict[str, Any]) -> tuple[str, str]:
    """Strongest physical-pack identity for one resolved node row.

    The install path names a physical directory, so it dominates: two rows for
    the same path are one pack even when their stored registry records or
    metadata-derived cnr/aux ids disagree. Only a path-less row falls back to
    CNR id, aux id, repository URL, then a stable name. Per-class fields are
    never part of the key.
    """
    path = _normalized_install_path(row.get("install_path"))
    if path:
        return ("path", path)
    for kind, field in _PACK_IDENTITY_FIELDS:
        identity = _normalized_identity(row.get(field))
        if identity:
            return (kind, identity)
    name = _normalized_identity(row.get("name"))
    return ("name", name) if name else ("row", str(id(row)))


def _merge_node_state(current: Any, incoming: Any) -> Any:
    """Return the more degraded node state (missing > wrong_revision > installed)."""
    if _NODE_STATE_SEVERITY.get(str(incoming or ""), 0) > _NODE_STATE_SEVERITY.get(
        str(current or ""), 0
    ):
        return incoming
    return current


def _group_node_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse per-class rows into one row per physical pack.

    Groups by strongest pack identity: install path first, then CNR id, aux id,
    repository URL, or a stable name. A path-less row whose CNR/aux/repo matches
    an installed pack joins that pack by path. Classes merge sorted and deduped;
    state degrades conservatively; the first nonempty name/repo/cnr/aux/version/
    revision is retained. First-seen group order is preserved. Row dict shapes
    are unchanged.
    """
    valid = [row for row in rows if isinstance(row, dict)]
    # Index installed (path-bearing) packs by identity so a class whose own
    # registry record is absent still lands on the same physical pack.
    path_identity: dict[tuple[str, str], tuple[str, str]] = {}
    for row in valid:
        key = _pack_group_key(row)
        if key[0] != "path":
            continue
        for kind, field in _PACK_IDENTITY_FIELDS:
            identity = _normalized_identity(row.get(field))
            if identity:
                path_identity.setdefault((kind, identity), key)

    grouped: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for row in valid:
        key = _pack_group_key(row)
        if key[0] != "path":
            for kind, field in _PACK_IDENTITY_FIELDS:
                identity = _normalized_identity(row.get(field))
                mapped = path_identity.get((kind, identity)) if identity else None
                if mapped is not None:
                    key = mapped
                    break
        if key not in grouped:
            merged = dict(row)
            merged["classes"] = []
            grouped[key] = merged
            order.append(key)
        merged = grouped[key]
        merged["state"] = _merge_node_state(merged.get("state"), row.get("state"))
        for field in _PACK_MERGE_FIELDS:
            if not _identity_text(merged.get(field)) and _identity_text(row.get(field)):
                merged[field] = row.get(field)
        for cls in row.get("classes") or []:
            if cls not in merged["classes"]:
                merged["classes"].append(cls)
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


def _role_alias_folders(role: str) -> set[str]:
    """Folders that satisfy a dependency role, aliases included.

    ``unet`` and ``diffusion_models`` are one identity in current ComfyUI, as
    are ``clip``/``text_encoders``. ``WORKFLOW_ROLE_FOLDERS`` is the shared
    authority for those aliases; an unknown role falls back to itself.
    """
    aliases = WORKFLOW_ROLE_FOLDERS.get(str(role).strip().lower())
    if aliases:
        return {str(folder).lower() for folder in aliases}
    return set()


def _basename_of_ref(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


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
        # Older persisted versions predate graph-widget extraction; recover any
        # model refs their stored UI graph recorded by name (same guards).
        for graph_key in ("graph_json", "static_graph"):
            for ref in extract_ui_graph_model_refs((version or {}).get(graph_key)):
                role = str(ref.get("role", ""))
                filename = ref.get("filename")
                if isinstance(filename, str) and filename:
                    refs.setdefault(
                        (role, filename), {"role": role, "filename": filename}
                    )
        return list(refs.values())

    @staticmethod
    def _most_recent(records: list[dict[str, Any]]) -> dict[str, Any]:
        def _ts(record: dict[str, Any]) -> str:
            return str(record.get("updated_at") or record.get("discovered_at") or "")

        return max(records, key=_ts)

    def _records_for_ref(
        self, role: str, filename: str
    ) -> list[dict[str, Any]]:
        """Library records matching a ``(role, filename)`` dependency ref.

        A stored ref may arrive folder-qualified (``diffusion_models/x``),
        while records key on the in-bucket relative path, so the basename is
        tried as a fallback. When the role has folder aliases and records exist
        in more than one folder, alias-matching records win so ``unet``
        resolves against ``unet`` or ``diffusion_models`` consistently.
        """
        records = self._models.records_by_filename(filename)
        if not records:
            base = _basename_of_ref(filename)
            if base and base != filename:
                records = self._models.records_by_filename(base)
        aliases = _role_alias_folders(role)
        if records and aliases:
            preferred = [
                r
                for r in records
                if str(r.get("folder") or "").strip().lower() in aliases
            ]
            if preferred:
                records = preferred
        return records

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
                records = self._records_for_ref(role, filename)
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
        # Union declared classes with the stored graph node types so UI-only
        # nodes and covers from old captures (predating the metadata union)
        # still resolve. The shape classifier below still excludes true virtual
        # panels from missing/attention.
        node_classes = _version_node_classes(version)
        requirements = dependency_metadata.get("custom_node_requirements") or {}
        if not isinstance(requirements, dict):
            requirements = {}
        # Older stored versions captured before custom_node_requirements
        # existed still carry pack identity on the persisted UI graph; recover
        # it so classes sharing a pack group into one missing row instead of
        # six.
        graph_identity_by_class = _class_pack_identities_from_graph(version)
        # Only classes that consume an input count as "executable" for the
        # virtual-panel shape check: a no-op prompt entry with empty inputs is
        # the live signature of a UI-only panel (DonutLatestPreview etc.).
        executable_classes = _executable_consuming_classes(version)
        graph_virtual_classes = _graph_virtual_class_names(version)
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
            if cls.lower() in _VIRTUAL_NODE_CLASSES:
                continue  # frontend-only virtual node; never a pack dependency
            req = requirements.get(cls) or {}
            if not isinstance(req, dict):
                req = {}
            required_revision = str(req.get("revision") or "")
            cnr_id, aux_id = _class_identity_from_metadata(
                cls, requirements, graph_identity_by_class
            )
            display_name = (
                req.get("name") or req.get("repository") or cnr_id or aux_id or cls
            )
            if cls in core:
                results.append(
                    {
                        "name": "ComfyUI core",
                        "state": "installed",
                        "install_path": "",
                        "installed_commit": "",
                        "required_revision": required_revision,
                        "repository_url": "",
                        "cnr_id": "",
                        "aux_id": "",
                        "classes": [cls],
                    }
                )
                continue
            try:
                record = self._registry.record_by_class(cls)
            except (StudioStoreError, OSError):
                results.append(
                    {
                        "name": display_name,
                        "state": "missing",
                        "install_path": "",
                        "installed_commit": "",
                        "required_revision": required_revision,
                        "repository_url": req.get("repository") or "",
                        "cnr_id": cnr_id,
                        "aux_id": aux_id,
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
                        "cnr_id": cnr_id,
                        "aux_id": aux_id,
                        "classes": [cls],
                    }
                )
                continue
            # A valid class that only exists in the UI graph as an empty
            # inputs/outputs panel with no pack identity is a frontend virtual
            # node, not an installable dependency. Report it via
            # unresolvable_classes instead of a fake missing pack row.
            if _is_virtual_workflow_class(
                cls,
                executable_classes=executable_classes,
                graph_virtual_classes=graph_virtual_classes,
                core=core,
                has_identity=bool(cnr_id or aux_id),
                record_exists=False,
            ):
                continue
            results.append(
                {
                    "name": display_name,
                    "state": "missing",
                    "install_path": "",
                    "installed_commit": "",
                    "required_revision": required_revision,
                    "repository_url": req.get("repository") or "",
                    "cnr_id": cnr_id,
                    "aux_id": aux_id,
                    "classes": [cls],
                }
            )
        return _group_node_rows(results)

    def unresolvable_classes(self, version: dict[str, Any]) -> list[dict[str, Any]]:
        """Class strings that can never resolve to a pack.

        Two kinds qualify: non-identifier graph artifacts (UUIDs from
        frontend-only proxy/subgraph nodes, display titles recorded as types)
        and valid class names whose stored UI graph node is an empty
        inputs/outputs virtual panel with no pack identity and which never
        appear in the executable prompt, core set, or registry. Neither is an
        installable dependency, so both stay out of missing/attention counts.
        Never raises.
        """
        try:
            dependency_metadata = (version or {}).get("dependency_metadata") or {}
            node_classes = _version_node_classes(version)
            if not node_classes:
                return []
            requirements = dependency_metadata.get("custom_node_requirements") or {}
            if not isinstance(requirements, dict):
                requirements = {}
            graph_identity_by_class = _class_pack_identities_from_graph(version)
            executable_classes = _executable_class_names(version)
            graph_virtual_classes = _graph_virtual_class_names(version)
            _records, core = self._ensure_discovery()
            out: list[dict[str, Any]] = []
            seen: set[str] = set()
            for class_type in node_classes:
                cls = str(class_type)
                if cls in seen:
                    continue
                seen.add(cls)
                if not _is_resolvable_class_name(cls):
                    out.append(
                        {
                            "name": cls,
                            "classes": [cls],
                            "reason": "graph artifact, not a registered node class",
                        }
                    )
                    continue
                if cls.lower() in _VIRTUAL_NODE_CLASSES:
                    continue
                if cls in core or cls in executable_classes:
                    continue
                cnr_id, aux_id = _class_identity_from_metadata(
                    cls, requirements, graph_identity_by_class
                )
                try:
                    record_exists = self._registry.record_by_class(cls) is not None
                except (StudioStoreError, OSError):
                    # Unreadable registry is not proof of absence: leave the
                    # class to resolve_custom_nodes (conservative missing).
                    continue
                if _is_virtual_workflow_class(
                    cls,
                    executable_classes=executable_classes,
                    graph_virtual_classes=graph_virtual_classes,
                    core=core,
                    has_identity=bool(cnr_id or aux_id),
                    record_exists=record_exists,
                ):
                    out.append(
                        {
                            "name": cls,
                            "classes": [cls],
                            "reason": "workflow-only virtual node, not an installable node class",
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
