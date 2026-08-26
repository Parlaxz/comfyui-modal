"""Evidence adaptation for the Studio portability backend (Phase G9).

Composition helpers between the production authorities (WorkflowDomainStore,
DependencyResolver, Model Library, Custom Node Registry, persisted Version
captures) and the pure Phase-G engines (``portability_risk`` /
``portability_targets``).  This module OWNS NO policy: every rule lives in
the frozen contract/risk/target modules; every authority read is performed by
the caller-supplied stores/resolver.

Conservative provenance discipline (G1/G2 evidence, G5 vocabulary):

* a non-empty registry ``repo_url`` alone is NEVER ``exact`` — several
  registry rows carry the ComfyUI host-repo fallback URL;
* UI-graph ``properties.aux_id`` is trusted as DECLARED identity when the
  registry snapshot has no row for a class;
* nothing in the current product verifies pins, so live evidence never
  derives ``exact`` on its own.

No network, no subprocesses, no installs, no filesystem scans beyond
guarded single-path ``os.path.isfile`` existence checks for absolute-path
records.  Import-side only stdlib + the frozen portability modules.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

import portability_contract as pc
import portability_risk as risk
import portability_targets as targets

# Registry rows whose repo_url points at the ComfyUI host repo are fallback
# noise (G1 §8): their repo identity must not be exported as truth.
_HOST_FALLBACK_REPO_RE = re.compile(
    r"^https?://[^/]+/(Comfy-Org/ComfyUI|comfyanonymous/ComfyUI)(\.git)?/?$",
    re.IGNORECASE,
)

_GITHUB_URL_TEMPLATE = "https://github.com/{slug}"

# LoadImage-family classes whose string input is a user asset basename.
_ASSET_CLASS_INPUTS: dict[str, tuple[str, ...]] = {
    "LoadImage": ("image",),
    "LoadImageMask": ("image",),
    "LoadMask": ("mask",),
    "LoadVideo": ("video",),
    "LoadAudio": ("audio",),
}
_ASSET_INPUT_PREFIXES = ("VHS_Load",)
_ASSET_SUFFIX_RE = re.compile(r"\s*\[(input|output|temp)\]\s*$", re.IGNORECASE)

_MODEL_EXT_RE = re.compile(
    r"\.(safetensors|sft|ckpt|pt|pth|bin|gguf)$", re.IGNORECASE
)

_CORE_ROW_NAME = "ComfyUI core"

EXPORTER_ID = "comfyui-modal-studio-portability"


# ── graph-derived facts ───────────────────────────────────────────────────


def extract_aux_id_provenance(graph_json: Any) -> dict[str, str]:
    """Map class_type -> ``properties.aux_id`` from a persisted UI graph.

    aux_id values (e.g. ``"kijai/ComfyUI-KJNodes"``) are author-declared
    node-package identities embedded by the ComfyUI frontend.  The persisted
    Version is never mutated; this is a read-only projection.
    """
    out: dict[str, str] = {}
    if not isinstance(graph_json, dict):
        return out
    for node in graph_json.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("type") or "").strip()
        properties = node.get("properties")
        aux_id = ""
        if isinstance(properties, dict):
            raw = properties.get("aux_id")
            if isinstance(raw, str):
                aux_id = raw.strip()
        if class_type and aux_id:
            out.setdefault(class_type, aux_id)
    return out


def extract_frontend_version(graph_json: Any) -> Optional[str]:
    """Best-effort frontend version string from a persisted UI graph."""
    if not isinstance(graph_json, dict):
        return None
    for value in (
        graph_json.get("frontendVersion"),
        (graph_json.get("extra") or {}).get("frontendVersion")
        if isinstance(graph_json.get("extra"), dict)
        else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_host_fallback(repo_url: str) -> bool:
    return bool(_HOST_FALLBACK_REPO_RE.match(repo_url.strip()))


def derive_node_provenance(
    custom_node_rows,
    aux_ids: Optional[dict[str, str]] = None,
) -> dict[str, dict[str, str]]:
    """Per-class provenance map using the frozen quality vocabulary.

    Precedence (most trustworthy first):
      1. explicit row ``provenance`` field (caller-supplied override);
      2. resolver-state derivation (installed+commit → declared, installed
         w/o commit → inferred, wrong_revision → declared, missing+repo →
         declared, else unresolved);
      3. UI-graph ``aux_id`` declared identity → declared (repo known via
         the graph author, revision unknown);
      4. unresolved.
    """
    aux = aux_ids or {}
    provenance: dict[str, dict[str, str]] = {}
    for row in custom_node_rows or ():
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "") == _CORE_ROW_NAME and not str(
            row.get("repository_url") or ""
        ):
            continue  # core attribution rows carry no package identity
        quality = row.get("provenance")
        repo = str(row.get("repository_url") or "").strip()
        revision = str(row.get("installed_commit") or "").strip() or str(
            row.get("required_revision") or ""
        ).strip()
        if quality not in pc.PROVENANCE_QUALITY_VALUES:
            state = row.get("state")
            has_commit = bool(str(row.get("installed_commit") or "").strip())
            has_repo = bool(repo)
            if state == "wrong_revision":
                quality = pc.PROVENANCE_DECLARED
            elif state == "missing":
                quality = (
                    pc.PROVENANCE_DECLARED if has_repo else pc.PROVENANCE_UNRESOLVED
                )
            elif state == "installed":
                quality = (
                    pc.PROVENANCE_DECLARED if has_commit else pc.PROVENANCE_INFERRED
                )
            else:
                quality = pc.PROVENANCE_UNRESOLVED
        for cls in row.get("classes") or ():
            cls = str(cls)
            provenance.setdefault(
                cls, {"quality": quality, "repo": repo, "revision": revision}
            )
    # aux_id rescue: classes with no usable registry row but a graph-declared
    # package identity become DECLARED (identity known, revision absent).
    for cls, aux_id in sorted(aux.items()):
        entry = provenance.get(cls)
        if entry is not None and entry["quality"] != pc.PROVENANCE_UNRESOLVED:
            continue
        repo = _GITHUB_URL_TEMPLATE.format(slug=aux_id)
        provenance[cls] = {
            "quality": pc.PROVENANCE_DECLARED,
            "repo": repo,
            "revision": "",
        }
    return provenance


def core_classes_from_rows(custom_node_rows) -> set[str]:
    """Classes attributed to ComfyUI core by the DependencyResolver rows."""
    core: set[str] = set()
    for row in custom_node_rows or ():
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "") == _CORE_ROW_NAME and not str(
            row.get("repository_url") or ""
        ):
            for cls in row.get("classes") or ():
                core.add(str(cls))
    return core


def split_core_rows(custom_node_rows) -> tuple[list[dict], list[dict]]:
    """Split resolver rows into (core attribution rows, package rows)."""
    core_rows: list[dict] = []
    package_rows: list[dict] = []
    for row in custom_node_rows or ():
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "") == _CORE_ROW_NAME and not str(
            row.get("repository_url") or ""
        ):
            core_rows.append(row)
        else:
            package_rows.append(row)
    return core_rows, package_rows


# ── manifest record builders (export side) ────────────────────────────────


def build_model_manifest_records(model_rows) -> list[dict[str, Any]]:
    """Manifest ``models[]`` records from resolver model rows.

    Truthful-reference discipline:
    * NEVER exports ``local_path`` / install paths;
    * ``sha256`` only when the library supplied a real 64-hex digest;
    * ``folder`` only from an authoritative library record (never the
      resolver's role-based guess);
    * deduped by ``(filename, sha256-or-None)`` (manifest identity rule).
    """
    records: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for row in sorted(
        (r for r in model_rows or () if isinstance(r, dict)),
        key=lambda r: (str(r.get("filename") or ""), str(r.get("role") or "")),
    ):
        filename = row.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        digest = row.get("hash") or row.get("sha256")
        digest = digest if pc.is_sha256_hex(digest) else None
        identity = (filename, digest)
        if identity in seen:
            continue
        seen.add(identity)
        record: dict[str, Any] = {"filename": filename}
        if digest:
            record["sha256"] = digest
        folder = row.get("folder")
        if isinstance(folder, str) and folder and folder != "unknown":
            record["folder"] = folder
        role = row.get("role")
        if isinstance(role, str) and role:
            record["role"] = role
        size = row.get("size")
        if isinstance(size, int) and not isinstance(size, bool) and size > 0:
            record["size"] = size
        source_urls = [
            u for u in (row.get("source_urls") or []) if isinstance(u, str) and u
        ]
        if source_urls:
            record["source_urls"] = sorted(source_urls)
        records.append(record)
    return records


def build_custom_node_manifest_records(
    custom_node_rows,
    aux_ids: Optional[dict[str, str]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Manifest ``custom_nodes[]`` records + unrepresentable findings.

    The manifest schema requires a non-empty ``repo_url`` AND non-empty
    ``revision`` per record.  Classes without both are NOT invented
    (no guessed repos, no fake revisions); they are returned as findings
    instead: ``[{"code": ..., "message": ...}]`` with stable codes
    ``custom_node_repo_unresolved`` / ``custom_node_revision_unresolved``.
    Host-fallback registry URLs are replaced by aux_id-derived URLs when
    available (declared identity), otherwise emitted as findings.
    """
    aux = aux_ids or {}
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    findings: list[dict[str, str]] = []
    for row in custom_node_rows or ():
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "") == _CORE_ROW_NAME and not str(
            row.get("repository_url") or ""
        ):
            continue
        classes = [str(c) for c in (row.get("classes") or ()) if str(c)]
        repo = str(row.get("repository_url") or "").strip()
        revision = str(row.get("installed_commit") or "").strip() or str(
            row.get("required_revision") or ""
        ).strip()
        primary = classes[0] if classes else str(row.get("name") or "")
        if _is_host_fallback(repo):
            replacement = next(
                (_GITHUB_URL_TEMPLATE.format(slug=aux[c]) for c in sorted(classes) if c in aux),
                "",
            )
            if replacement:
                repo = replacement
        if not repo:
            for cls in sorted(classes) or [primary]:
                findings.append(
                    {
                        "code": "custom_node_repo_unresolved",
                        "message": (
                            "custom node %s has no trustworthy repository "
                            "identity; omitted from manifest custom_nodes"
                            % cls
                        ),
                    }
                )
            continue
        if not revision:
            for cls in sorted(classes) or [primary]:
                findings.append(
                    {
                        "code": "custom_node_revision_unresolved",
                        "message": (
                            "custom node %s has no recorded revision/commit; "
                            "omitted from manifest custom_nodes" % cls
                        ),
                    }
                )
            continue
        key = (repo, revision)
        record_classes = sorted(set(classes))
        existing = next((r for r in records if (r["repo_url"], r["revision"]) == key), None)
        if existing is not None:
            merged = sorted(set(existing.get("classes") or []) | set(record_classes))
            if merged != sorted(existing.get("classes") or []):
                existing["classes"] = merged
            continue
        if key in seen:
            continue
        seen.add(key)
        record: dict[str, Any] = {"repo_url": repo, "revision": revision}
        name = str(row.get("name") or "").strip()
        if name and name != _CORE_ROW_NAME:
            record["name"] = name
        if record_classes:
            record["classes"] = record_classes
        records.append(record)
    records.sort(key=lambda r: (r["repo_url"], r["revision"]))
    findings.sort(key=lambda f: (f["code"], f["message"]))
    return records, findings


def extract_asset_references(prompt: Any, node_classes=None) -> list[dict[str, str]]:
    """Reference-only asset records for LoadImage-family inputs.

    Only derivable truth is exported: the basename (with ``[input]`` /
    ``[output]`` / ``[temp]`` qualifiers stripped) and the loader role.
    Bytes are never read; sha256/size/mime are omitted (unknown).
    """
    assets: dict[tuple[str, str], dict[str, str]] = {}
    if not isinstance(prompt, dict):
        return []
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        fields = _ASSET_CLASS_INPUTS.get(class_type)
        if fields is None and not class_type.startswith(_ASSET_INPUT_PREFIXES):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        candidates = list(fields or ()) or [k for k in inputs if isinstance(k, str)]
        for name in candidates:
            value = inputs.get(name)
            if not isinstance(value, str) or not value.strip():
                continue
            basename = _ASSET_SUFFIX_RE.sub("", value.strip())
            if not basename or "/" in basename or "\\" in basename:
                continue
            key = (basename, class_type)
            assets.setdefault(
                key, {"filename": basename, "role": class_type}
            )
            break
    del node_classes
    return [assets[k] for k in sorted(assets)]


# ── import-side adaptation (manifest → resolver-shaped evidence) ──────────


def adapt_manifest_models(
    manifest_models,
    model_library: Any = None,
) -> list[dict[str, Any]]:
    """Adapt manifest model records into resolver-row-shaped evidence.

    ``model_library`` is a ``ModelLibraryStore`` (or None).  States mirror
    ``DependencyResolver.resolve_model_refs``: installed / missing /
    wrong_version / unknown.  No filesystem scans; the library's derived
    install state comes from ``model_library.record_is_installed``.
    """
    rows: list[dict[str, Any]] = []
    for rec in manifest_models or ():
        if not isinstance(rec, dict):
            continue
        filename = rec.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        declared_hash = rec.get("sha256")
        declared_hash = declared_hash if pc.is_sha256_hex(declared_hash) else None
        role = rec.get("role") if isinstance(rec.get("role"), str) else ""
        row: dict[str, Any] = {
            "key": "%s|%s" % (role, filename),
            "role": role,
            "filename": filename,
            "state": "unknown",
            "model_id": None,
            "folder": None,
            "hash": declared_hash,
            "size": rec.get("size") if isinstance(rec.get("size"), int) else None,
            "local_path": None,
            "source_urls": [
                u for u in (rec.get("source_urls") or []) if isinstance(u, str)
            ],
            "installed": False,
        }
        record = None
        if model_library is not None:
            try:
                matches = model_library.records_by_filename(filename)
            except Exception:
                matches = []
            record = next((r for r in matches if _record_installed(r)), None)
            if record is None and matches:
                record = max(
                    matches,
                    key=lambda r: str(r.get("updated_at") or r.get("discovered_at") or ""),
                )
        if record is not None and _record_installed(record):
            row["state"] = "installed"
            row["installed"] = True
            row["model_id"] = record.get("model_id")
            row["folder"] = record.get("folder")
            row["hash"] = record.get("hash") or declared_hash
            row["size"] = record.get("size")
            local_source_urls = [
                u for u in (record.get("source_urls") or []) if isinstance(u, str)
            ]
            if local_source_urls:
                row["source_urls"] = local_source_urls
            if declared_hash and record.get("hash") and record.get("hash") != declared_hash:
                row["state"] = "wrong_version"
                row["required_hash"] = declared_hash
        elif record is not None:
            row["state"] = "missing"
            row["folder"] = record.get("folder")
            row["hash"] = record.get("hash") or declared_hash
        else:
            row["state"] = "missing"
        rows.append(row)
    rows.sort(key=lambda r: (str(r.get("filename")), str(r.get("role"))))
    return rows


def _record_installed(record: dict[str, Any]) -> bool:
    try:
        from model_library import record_is_installed

        return bool(record_is_installed(record))
    except Exception:
        return False


def adapt_manifest_custom_nodes(
    manifest_custom_nodes,
    registry_store: Any = None,
) -> list[dict[str, Any]]:
    """Adapt manifest custom-node records into resolver-row-shaped evidence.

    ``registry_store`` is a ``CustomNodeRegistryStore`` (or None).  One row
    per manifest class; states mirror ``resolve_custom_nodes``.
    """
    rows: list[dict[str, Any]] = []

    def _registry_by_class(cls: str) -> Optional[dict[str, Any]]:
        if registry_store is None:
            return None
        try:
            return registry_store.record_by_class(cls)
        except Exception:
            return None

    def _registry_by_repo(repo_url: str) -> Optional[dict[str, Any]]:
        if registry_store is None:
            return None
        try:
            for record in registry_store.list_records():
                if str(record.get("repo_url") or "").strip() == repo_url:
                    return record
        except Exception:
            return None
        return None

    for rec in manifest_custom_nodes or ():
        if not isinstance(rec, dict):
            continue
        repo = rec.get("repo_url")
        revision = rec.get("revision")
        if not isinstance(repo, str) or not repo:
            continue
        if not isinstance(revision, str) or not revision:
            continue
        classes = [str(c) for c in (rec.get("classes") or []) if isinstance(c, str)]
        name = rec.get("name") if isinstance(rec.get("name"), str) else ""
        if not classes:
            record = _registry_by_repo(repo)
            state = "missing"
            installed_commit = ""
            if record is not None:
                installed_commit = str(record.get("installed_commit") or "")
                state = (
                    "wrong_revision"
                    if installed_commit and installed_commit != revision
                    else "installed"
                )
            rows.append(
                {
                    "name": name or repo.rsplit("/", 1)[-1],
                    "state": state,
                    "install_path": "",
                    "installed_commit": installed_commit,
                    "required_revision": revision,
                    "repository_url": repo,
                    "classes": [],
                }
            )
            continue
        for cls in sorted(classes):
            record = _registry_by_class(cls)
            state = "missing"
            installed_commit = ""
            if record is not None:
                installed_commit = str(record.get("installed_commit") or "")
                state = (
                    "wrong_revision"
                    if installed_commit and installed_commit != revision
                    else "installed"
                )
            rows.append(
                {
                    "name": name or cls,
                    "state": state,
                    "install_path": "",
                    "installed_commit": installed_commit,
                    "required_revision": revision,
                    "repository_url": repo,
                    "classes": [cls],
                }
            )
    rows.sort(key=lambda r: (str(r.get("classes") or [""]), str(r.get("name"))))
    return rows


# ── environment facts (cheap + truthful only) ─────────────────────────────


def collect_environment_facts(
    model_rows,
    custom_node_rows,
) -> dict[str, Optional[bool]]:
    """G6 environment dimensions derivable cheaply at request time.

    Only two dimensions have cheap local authorities (the version's own
    dependency evidence).  Torch pins, worktree cleanliness, core-patch
    divergence, and base-image digests would require git subprocesses or
    heavy imports and stay UNKNOWN (None) — never guessed (G5/G9 policy).
    """
    model_hashes_pinned: Optional[bool] = None
    hashes = [
        (r.get("hash") or r.get("sha256"))
        for r in model_rows or ()
        if isinstance(r, dict) and isinstance(r.get("filename"), str) and r.get("filename")
    ]
    if hashes:
        model_hashes_pinned = all(pc.is_sha256_hex(h) for h in hashes)

    custom_sources_pinned: Optional[bool] = None
    _, package_rows = split_core_rows(custom_node_rows)
    commits = [
        str(r.get("installed_commit") or "").strip()
        for r in package_rows
        if isinstance(r.get("classes"), list) and r.get("classes")
    ]
    if commits:
        custom_sources_pinned = all(bool(c) for c in commits)

    return {
        "torch_stack_pinned": None,
        "custom_node_sources_pinned": custom_sources_pinned,
        "plugin_worktree_clean": None,
        "local_core_patch_diverged": None,
        "model_hashes_pinned": model_hashes_pinned,
        "base_image_digest_pinned": None,
    }


# ── target-evidence assembly ──────────────────────────────────────────────


def build_target_evidence_payload(
    *,
    workflow_issue_codes,
    signals,
    model_rows,
    custom_node_rows,
    node_provenance,
    path_values,
    graph_json=None,
    requires_input_asset=False,
    uses_subgraphs=False,
    manifest_ready=True,
) -> dict:
    """Assemble the validated ``portability_targets.build_target_evidence``
    payload from prepared portability evidence (pure composition).

    Dynamic provider facts (catalog membership, native capability,
    persistent storage) have no local authority and stay UNKNOWN tri-states
    so G7 emits ``target_capability_unknown`` instead of guessing.
    """
    _, package_rows = split_core_rows(custom_node_rows)
    per_class: dict[str, dict[str, Any]] = {}
    for row in package_rows:
        for cls in row.get("classes") or ():
            cls = str(cls)
            quality = node_provenance.get(cls)
            quality_value = (
                quality.get("quality")
                if isinstance(quality, dict)
                else (quality if isinstance(quality, str) else "")
            )
            if quality_value not in pc.PROVENANCE_QUALITY_VALUES:
                quality_value = pc.PROVENANCE_UNRESOLVED
            state = str(row.get("state") or "unknown")
            install_status = (
                "installed"
                if state == "installed"
                else ("missing" if state in ("missing", "wrong_revision") else "unknown")
            )
            per_class[cls] = {
                "name": cls,
                "provenance": quality_value,
                "manager_restorable": False,
                "product_internal": False,
                "install_status": install_status,
                "requires_python_install": False,
                "requires_system_packages": False,
                "requires_native_build": False,
                "requires_cuda_build": False,
                "target_supported": {},
            }

    models = []
    for row in model_rows or ():
        if not isinstance(row, dict):
            continue
        filename = row.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        digest = row.get("hash") or row.get("sha256")
        models.append(
            {
                "name": filename,
                "sha256": digest if pc.is_sha256_hex(digest) else None,
                "private_or_gated": False,
                "present_locally": bool(row.get("installed"))
                if row.get("state") in ("installed", "missing")
                else None,
                "target_catalog_available": {},
            }
        )

    absolute_paths = []
    for value in path_values or ():
        text = str(value)
        try:
            exists = bool(text) and os.path.isfile(text)
        except Exception:
            exists = False
        absolute_paths.append(
            {
                "path": text,
                "source_host_consistent": exists,
                "product_materialized": False,
            }
        )

    return targets.build_target_evidence(
        global_issue_codes=sorted({str(c) for c in workflow_issue_codes}),
        signals=signals,
        custom_nodes=sorted(per_class.values(), key=lambda n: n["name"]),
        models=sorted(models, key=lambda m: m["name"]),
        absolute_paths=absolute_paths,
        requires_input_asset=bool(requires_input_asset),
        uses_subgraphs=bool(uses_subgraphs),
        frontend_version=extract_frontend_version(graph_json),
        manifest_ready=bool(manifest_ready),
        frontend_support={},
        runcomfy_native_capability=targets.RUNCOMFY_NATIVE_UNKNOWN,
        baseten_persistent_storage=targets.BASETEN_STORAGE_UNKNOWN,
    )


_CREDENTIAL_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|token|secret|password|passwd|authorization|"
    r"credential|cookie|session[_-]?id)",
    re.IGNORECASE,
)

_NOTE_NODE_TYPES = frozenset({"Note", "MarkdownNote"})


def detect_manifest_credential_shapes(manifest: Any) -> list[dict[str, Any]]:
    """Deterministic credential-shape scan over a BUILT manifest artifact.

    Mirrors the G6 detection discipline (credential-shaped KEY names with
    non-empty string values; values themselves are NEVER returned) across
    every graph payload the artifact embeds:

    * ``workflow.graph`` (executable prompt or foreign UI graph);
    * ``version.api_prompt_json`` (``output`` and ``workflow`` sub-objects);
    * ``version.graph_json`` UI nodes (skipping Note/MarkdownNote), scanning
      ``inputs[].name`` widget entries.

    Returns sorted ``[{"key": <field name>, "locations": [str...]}]``.
    """
    locations: dict[str, set[str]] = {}

    def _scan_inputs(inputs: Any, where: str) -> None:
        if not isinstance(inputs, dict):
            return
        for name, value in inputs.items():
            if (
                isinstance(name, str)
                and _CREDENTIAL_KEY_RE.search(name)
                and isinstance(value, str)
                and value.strip()
            ):
                locations.setdefault(name, set()).add(where)

    def _scan_prompt(payload: Any, where: str) -> None:
        if not isinstance(payload, dict):
            return
        for node in payload.values():
            if isinstance(node, dict):
                _scan_inputs(node.get("inputs"), where)

    def _scan_ui_graph(graph: Any, where: str) -> None:
        if not isinstance(graph, dict):
            return
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            if str(node.get("type") or "") in _NOTE_NODE_TYPES:
                continue
            for entry in node.get("inputs") or []:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                widget = entry.get("widget")
                value = widget.get("value") if isinstance(widget, dict) else None
                if (
                    isinstance(name, str)
                    and _CREDENTIAL_KEY_RE.search(name)
                    and isinstance(value, str)
                    and value.strip()
                ):
                    locations.setdefault(name, set()).add(where)

    if not isinstance(manifest, dict):
        return []
    workflow_section = manifest.get("workflow")
    if isinstance(workflow_section, dict):
        graph = workflow_section.get("graph")
        if isinstance(graph, dict) and "nodes" in graph:
            _scan_ui_graph(graph, "workflow.graph")
        else:
            _scan_prompt(graph, "workflow.graph")
    version_section = manifest.get("version")
    if isinstance(version_section, dict):
        api = version_section.get("api_prompt_json")
        if isinstance(api, dict):
            _scan_prompt(api.get("output"), "version.api_prompt_json.output")
            _scan_prompt(api.get("workflow"), "version.api_prompt_json.workflow")
        _scan_ui_graph(version_section.get("graph_json"), "version.graph_json")

    return [
        {"key": key, "locations": sorted(locs)}
        for key, locs in sorted(locations.items())
    ]


__all__ = [
    "EXPORTER_ID",
    "extract_aux_id_provenance",
    "extract_frontend_version",
    "derive_node_provenance",
    "core_classes_from_rows",
    "split_core_rows",
    "build_model_manifest_records",
    "build_custom_node_manifest_records",
    "extract_asset_references",
    "adapt_manifest_models",
    "adapt_manifest_custom_nodes",
    "collect_environment_facts",
    "build_target_evidence_payload",
    "detect_manifest_credential_shapes",
    "risk",
]
