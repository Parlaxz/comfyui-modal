"""Pure Workflow portability risk engine (Phase G6).

Static, deterministic analysis of ONE immutable WorkflowVersion from
PREPARED evidence. This module performs NO I/O of any kind: no filesystem
scans, no network, no git, no registry/model-store reads, no installs,
no provider SDKs, and it holds NO global mutable state. Every environment
and dependency fact must be PASSED IN by a later route/service adapter.

Owned by this lane (G6):
  * static portability signals (frozen G5 vocabulary in ``portability_contract``)
  * global Workflow portability findings (issues) and summary risk level
  * environment-reproducibility report assembly from supplied facts
  * pure full-report assembly combining workflow + supplied target results
    + environment + invalidation stamp (validated via ``portability_contract``)

Explicitly NOT owned here: target readiness rules (G7), manifest readiness
(consumed as input from ``studio_workflow_manifest.check_readiness``),
dependency resolution (consumed from ``DependencyResolver`` output shape),
report cache, routes, frontend.

Hard policy (G5): environment reproducibility NEVER forces the Workflow's
or any target's risk level (``POLICY_ENVIRONMENT_ISOLATION``). Subgraphs are
target-sensitive, not a universal blocker (``POLICY_SUBGRAPHS``). Absolute
paths are a global finding whose cross-target severity belongs to the
target rules (``POLICY_ABSOLUTE_PATHS``); they do NOT force summary HIGH.

Summary-risk philosophy (frozen G5 §4):
  low     — no blocking/unresolved findings; structurally portable.
  medium  — portable with explicit setup/attention (unpinned-but-known
            dependencies, missing hashes, separately transported assets,
            resolvable mismatches, soft structural concerns).
  high    — likely true portability blocker (unresolved required node
            identity, unavailable source, manifest readiness failure).
  unknown — analyzer cannot make a defensible determination.

Issue codes: foundational frozen codes from ``portability_contract`` plus
three NEW stable codes required by audited conditions the frozen set cannot
represent (documented in PHASE_G6_PORTABILITY_RISK_ENGINE_2026-08-23.md):
  graph_hash_mismatch, env_bound_registry_leak, analysis_unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import portability_contract as c

# ── New stable issue codes (additions; frozen codes never renamed) ────────

ISSUE_GRAPH_HASH_MISMATCH = "graph_hash_mismatch"
ISSUE_ENV_BOUND_REGISTRY_LEAK = "env_bound_registry_leak"
ISSUE_ANALYSIS_UNAVAILABLE = "analysis_unavailable"

NEW_ISSUE_CODES = (
    ISSUE_GRAPH_HASH_MISMATCH,
    ISSUE_ENV_BOUND_REGISTRY_LEAK,
    ISSUE_ANALYSIS_UNAVAILABLE,
)

ALL_ENGINE_ISSUE_CODES = tuple(c.FOUNDATIONAL_ISSUE_CODES) + NEW_ISSUE_CODES

# ── Detection constants ────────────────────────────────────────────────────

# UI-graph node types whose text payloads are documentation, never functional.
_NOTE_NODE_TYPES = frozenset({"Note", "MarkdownNote"})

_WINDOWS_DRIVE_RE = re.compile(r"\b[A-Za-z]:[\\/][^\s\"'|<>]*")
_UNC_RE = re.compile(r"\\\\[^\\/:*?\"<>|\r\n\s]+\\[^\s\"'|<>]*")
_POSIX_ABS_RE = re.compile(r"(?<![\w:])/(?:[A-Za-z0-9._\-]+/)+[A-Za-z0-9._\-]+")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

_MODEL_EXT_RE = re.compile(
    r"\.(safetensors|sft|ckpt|pt|pth|bin|gguf)$", re.IGNORECASE
)

_CREDENTIAL_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|token|secret|password|passwd|authorization|"
    r"credential|cookie|session[_-]?id)",
    re.IGNORECASE,
)

_EXACT_ASSET_CLASSES = frozenset(
    {
        "LoadImage",
        "LoadImageMask",
        "LoadMask",
        "LoadVideo",
        "LoadAudio",
    }
)
_ASSET_CLASS_PREFIXES = ("VHS_Load",)

_EVIDENCE_SAMPLE_CAP = 5
_MESSAGE_LIST_CAP = 6
_SAMPLE_TRUNCATE = 120


# ── Evidence input object ──────────────────────────────────────────────────


@dataclass(frozen=True)
class PortabilityEvidence:
    """Immutable prepared-evidence input for one WorkflowVersion analysis.

    Every field is supplied by the caller (route/service adapter). The
    engine never opens stores, files, git, or the network itself.
    """

    version_id: str
    graph_hash: str
    executable_prompt: Any = None
    api_prompt_json: Any = None
    graph_json: Any = None
    dependency_metadata: Any = None
    model_evidence: tuple = ()
    custom_node_evidence: tuple = ()
    node_provenance: dict = field(default_factory=dict)
    core_classes: frozenset = frozenset()
    manifest_readiness: Any = None
    referenced_assets: tuple = ()
    extraction_gap_refs: tuple = ()
    models_available: bool = True
    custom_nodes_available: bool = True
    env_bound_registry_leak: bool = False
    exact_roundtrip_proven_override: Any = None


def make_evidence(**kwargs) -> PortabilityEvidence:
    """Build a PortabilityEvidence with light normalization (pure)."""
    known = {f for f in PortabilityEvidence.__dataclass_fields__}
    unknown = sorted(set(kwargs) - known)
    if unknown:
        raise c.PortabilityContractError(
            ["unknown evidence fields: %s" % ", ".join(unknown)]
        )
    kwargs["model_evidence"] = _as_tuple_of_dicts(kwargs.get("model_evidence"))
    kwargs["custom_node_evidence"] = _as_tuple_of_dicts(
        kwargs.get("custom_node_evidence")
    )
    kwargs["referenced_assets"] = _as_tuple_of_dicts(
        kwargs.get("referenced_assets")
    )
    kwargs["extraction_gap_refs"] = _as_tuple_of_dicts(
        kwargs.get("extraction_gap_refs")
    )
    prov = kwargs.get("node_provenance") or {}
    if not isinstance(prov, dict):
        raise c.PortabilityContractError(["node_provenance must be a dict"])
    kwargs["node_provenance"] = dict(prov)
    core = kwargs.get("core_classes") or frozenset()
    kwargs["core_classes"] = frozenset(str(x) for x in core)
    return PortabilityEvidence(**kwargs)


def _as_tuple_of_dicts(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise c.PortabilityContractError(["expected a list of dicts, got %r" % (value,)])


# ── DependencyResolver adapter ────────────────────────────────────────────


def evidence_from_version_record(
    version,
    *,
    model_rows=(),
    custom_node_rows=(),
    core_classes=(),
    manifest_readiness=None,
    referenced_assets=(),
    models_available=True,
    custom_nodes_available=True,
    node_provenance=None,
    env_bound_registry_leak=False,
    extraction_gap_refs=(),
) -> PortabilityEvidence:
    """Adapt a WorkflowVersion record + ``DependencyResolver.resolve_version``
    outputs into engine evidence WITHOUT modifying the resolver.

    Accepted row shapes are exactly the current resolver shapes:
      models:       {key, role, filename, state, hash|sha256?, folder,
                     source_urls, installed, ...}
      custom_nodes: {name, state, install_path, installed_commit,
                     required_revision, repository_url, classes}

    Provenance quality derivation (adapter-level, deliberately conservative;
    a non-empty registry ``repo_url`` alone is NEVER trusted as exact —
    G1/G2 proved host-ComfyUI fallback noise):
      installed   + commit → declared   (recorded, not verified)
      installed   w/o commit → inferred
      wrong_revision → declared
      missing     + repo candidate → declared (identity known, absent)
      missing     w/o repo candidate → unresolved
    Callers may override per-class via ``node_provenance`` (highest trust
    authority, e.g. exact after verified pinning).
    """
    version = version if isinstance(version, dict) else {}
    dependency_metadata = version.get("dependency_metadata")
    if node_provenance is None:
        node_provenance = _derive_provenance_from_rows(custom_node_rows)
    return make_evidence(
        version_id=str(version.get("version_id") or ""),
        graph_hash=str(version.get("graph_hash") or ""),
        executable_prompt=version.get("executable_prompt"),
        api_prompt_json=version.get("api_prompt_json"),
        graph_json=version.get("graph_json"),
        dependency_metadata=dependency_metadata,
        model_evidence=model_rows,
        custom_node_evidence=custom_node_rows,
        node_provenance=node_provenance,
        core_classes=core_classes,
        manifest_readiness=manifest_readiness,
        referenced_assets=referenced_assets,
        extraction_gap_refs=extraction_gap_refs,
        models_available=models_available,
        custom_nodes_available=custom_nodes_available,
        env_bound_registry_leak=env_bound_registry_leak,
    )


def _derive_provenance_from_rows(rows) -> dict:
    provenance: dict[str, str] = {}
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        quality = row.get("provenance")
        if quality not in c.PROVENANCE_QUALITY_VALUES:
            state = row.get("state")
            has_commit = bool(str(row.get("installed_commit") or "").strip())
            has_repo = bool(str(row.get("repository_url") or "").strip())
            if state == "wrong_revision":
                quality = c.PROVENANCE_DECLARED
            elif state == "missing":
                quality = (
                    c.PROVENANCE_DECLARED if has_repo else c.PROVENANCE_UNRESOLVED
                )
            elif state == "installed":
                quality = (
                    c.PROVENANCE_DECLARED if has_commit else c.PROVENANCE_INFERRED
                )
            else:
                quality = c.PROVENANCE_UNRESOLVED
        for cls in row.get("classes") or ():
            provenance.setdefault(str(cls), quality)
    return provenance


# ── Small deterministic helpers ───────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_samples(values, cap: int = _EVIDENCE_SAMPLE_CAP) -> list:
    unique = sorted({str(v)[:_SAMPLE_TRUNCATE] for v in values if v})
    return unique[:cap]


def _join_names(names, cap: int = _MESSAGE_LIST_CAP) -> str:
    ordered = sorted({str(n) for n in names if n})
    shown = ordered[:cap]
    text = ", ".join(shown)
    if len(ordered) > cap:
        text += " and %d more" % (len(ordered) - cap)
    return text


def _iter_prompt_nodes(prompt: dict):
    for node_id, node in prompt.items():
        if isinstance(node, dict):
            yield str(node_id), node


def _functional_string_inputs(prompt: dict):
    """Yield (node_id, input_name, value) for string inputs of prompt nodes."""
    for node_id, node in _iter_prompt_nodes(prompt):
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for name, value in inputs.items():
            if isinstance(value, str) and value.strip():
                yield node_id, str(name), value


def _is_filesystem_path(value: str) -> bool:
    """Conservative environment-bound path detection.

    URL path segments are stripped first so ordinary http(s) URLs never
    classify as filesystem paths; remaining Windows drive paths, UNC paths,
    and multi-segment POSIX absolute paths count as path evidence.
    """
    without_urls = _URL_RE.sub(" ", value)
    if _WINDOWS_DRIVE_RE.search(without_urls):
        return True
    if _UNC_RE.search(without_urls):
        return True
    if _POSIX_ABS_RE.search(without_urls):
        return True
    return False


def _is_basename(value: str) -> bool:
    if "/" in value or "\\" in value:
        return False
    return not _WINDOWS_DRIVE_RE.search(value)


def _resolved_executable_prompt(evidence: PortabilityEvidence):
    """Executable prompt resolution mirroring extract_executable_prompt
    preference for ``api_prompt_json.output`` (projection, not rewrite)."""
    ep = evidence.executable_prompt
    if isinstance(ep, dict):
        return ep
    ap = evidence.api_prompt_json
    if isinstance(ap, dict):
        out = ap.get("output")
        if isinstance(out, dict):
            return out
    return None


def _structural_unreadable_reason(evidence: PortabilityEvidence):
    """Return a reason string when supplied analyzer input is structurally
    unreadable, or None when the shapes are usable (possibly empty)."""
    checks = (
        ("executable_prompt", evidence.executable_prompt),
        ("api_prompt_json", evidence.api_prompt_json),
        ("graph_json", evidence.graph_json),
        ("dependency_metadata", evidence.dependency_metadata),
    )
    for name, value in checks:
        if value is not None and not isinstance(value, dict):
            return "%s must be a dict or null (got %s)" % (
                name,
                type(value).__name__,
            )
    if not str(evidence.version_id or "").strip():
        return "version_id is empty"
    return None


# ── Static signals ─────────────────────────────────────────────────────────


def compute_signals(evidence: PortabilityEvidence) -> dict:
    """Compute every frozen static signal from prepared evidence (pure)."""
    prompt = _resolved_executable_prompt(evidence)
    graph = evidence.graph_json if isinstance(evidence.graph_json, dict) else {}

    # Node classification -------------------------------------------------
    node_classes = set()
    dm = evidence.dependency_metadata if isinstance(evidence.dependency_metadata, dict) else {}
    raw_classes = dm.get("node_classes")
    if isinstance(raw_classes, (list, tuple)):
        node_classes = {str(x) for x in raw_classes if x}
    if prompt:
        for _nid, node in _iter_prompt_nodes(prompt):
            ct = node.get("class_type")
            if ct:
                node_classes.add(str(ct))
    core = evidence.core_classes
    custom_classes = sorted(cls for cls in node_classes if cls not in core)

    unresolved_classes = []
    for cls in custom_classes:
        if _provenance_quality(evidence, cls) == c.PROVENANCE_UNRESOLVED:
            unresolved_classes.append(cls)

    # Custom-node rows / repos ---------------------------------------------
    repo_ids = set()
    for row in evidence.custom_node_evidence:
        url = str(row.get("repository_url") or "").strip()
        if url:
            repo_ids.add(url.rstrip("/"))
    for cls in custom_classes:
        entry = evidence.node_provenance.get(cls)
        if isinstance(entry, dict):
            repo = str(entry.get("repo") or entry.get("repo_url") or "").strip()
            if repo:
                repo_ids.add(repo.rstrip("/"))

    revision_pinned = True
    for cls in custom_classes:
        quality = _provenance_quality(evidence, cls)
        revision = _provenance_revision(evidence, cls)
        if quality != c.PROVENANCE_EXACT or not revision:
            revision_pinned = False
            break

    # Path / endpoint scans (functional positions only) --------------------
    path_values = []
    endpoint_values = []
    credential_keys = []
    if prompt:
        for node_id, name, value in _functional_string_inputs(prompt):
            if _is_filesystem_path(value):
                path_values.append(value)
            if _HTTP_URL_RE.match(value.strip()):
                endpoint_values.append(value.strip())
            if _CREDENTIAL_KEY_RE.search(name) and value.strip():
                credential_keys.append("%s.%s" % (node_id, name))
    if isinstance(graph, dict):
        for ui_node in graph.get("nodes") or []:
            if not isinstance(ui_node, dict):
                continue
            if str(ui_node.get("type") or "") in _NOTE_NODE_TYPES:
                continue
            widgets = ui_node.get("widgets_values")
            if not isinstance(widgets, (list, tuple)):
                continue
            for value in widgets:
                if isinstance(value, str) and value.strip():
                    if _is_filesystem_path(value):
                        path_values.append(value)

    # Model refs ------------------------------------------------------------
    model_filenames = []
    unpinned_hashes = []
    hash_pinned = True
    for row in evidence.model_evidence:
        filename = row.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        model_filenames.append(filename)
        digest = row.get("hash") or row.get("sha256")
        if c.is_sha256_hex(digest):
            continue
        hash_pinned = False
        unpinned_hashes.append(filename)
    basename_only = all(_is_basename(fn) for fn in model_filenames)

    gap_refs = _detect_extraction_gaps(evidence, prompt)

    # Assets ------------------------------------------------------------------
    asset_classes = []
    for cls in sorted(node_classes):
        if cls in _EXACT_ASSET_CLASSES or cls.startswith(_ASSET_CLASS_PREFIXES):
            asset_classes.append(cls)
    requires_asset = bool(asset_classes) or len(evidence.referenced_assets) > 0

    # Subgraphs ----------------------------------------------------------------
    definitions = graph.get("definitions") if isinstance(graph, dict) else None
    subgraphs = (
        definitions.get("subgraphs")
        if isinstance(definitions, dict)
        else None
    )
    uses_subgraphs = isinstance(subgraphs, (list, tuple)) and len(subgraphs) > 0

    # Roundtrip ------------------------------------------------------------------
    roundtrip = evidence.exact_roundtrip_proven_override
    if roundtrip is None:
        roundtrip = False
        if prompt and c.is_sha256_hex(evidence.graph_hash):
            try:
                roundtrip = c.sha256_of_canonical(prompt) == evidence.graph_hash
            except ValueError:
                roundtrip = False

    return {
        c.SIGNAL_HAS_ABSOLUTE_PATH: bool(path_values),
        c.SIGNAL_HAS_UNRESOLVED_NODE_TYPE: bool(unresolved_classes),
        c.SIGNAL_UNRESOLVED_NODE_COUNT: len(unresolved_classes),
        c.SIGNAL_CUSTOM_NODE_COUNT: len(custom_classes),
        c.SIGNAL_CUSTOM_REPO_COUNT: len(repo_ids),
        c.SIGNAL_CUSTOM_NODE_REVISION_PINNED: bool(revision_pinned),
        c.SIGNAL_MODEL_REF_BASENAME_ONLY: bool(basename_only),
        c.SIGNAL_MODEL_HASH_PINNED: bool(hash_pinned),
        c.SIGNAL_MODEL_EXTRACTION_GAP: bool(gap_refs),
        c.SIGNAL_REQUIRES_INPUT_ASSET: bool(requires_asset),
        c.SIGNAL_HAS_EXTERNAL_ENDPOINT: bool(endpoint_values),
        c.SIGNAL_USES_SUBGRAPHS: bool(uses_subgraphs),
        c.SIGNAL_EXACT_ROUNDTRIP_PROVEN: bool(roundtrip),
        c.SIGNAL_ENV_BOUND_REGISTRY_LEAK: bool(evidence.env_bound_registry_leak),
        # Internal detail channels (stripped before wire normalization):
        "__path_values__": sorted(set(path_values)),
        "__endpoint_values__": sorted(set(endpoint_values)),
        "__credential_keys__": sorted(set(credential_keys)),
        "__gap_refs__": gap_refs,
        "__asset_classes__": asset_classes,
        "__unpinned_model_hashes__": sorted(set(unpinned_hashes)),
        "__subgraph_count__": len(subgraphs or ()) if uses_subgraphs else 0,
    }


def _public_signals(signals: dict) -> dict:
    return {k: v for k, v in signals.items() if not k.startswith("__")}


def _provenance_quality(evidence: PortabilityEvidence, cls: str) -> str:
    entry = evidence.node_provenance.get(cls)
    if isinstance(entry, dict):
        quality = entry.get("quality")
        if quality in c.PROVENANCE_QUALITY_VALUES:
            return quality
    elif isinstance(entry, str) and entry in c.PROVENANCE_QUALITY_VALUES:
        return entry
    for row in evidence.custom_node_evidence:
        classes = row.get("classes") or ()
        if cls in {str(x) for x in classes}:
            quality = row.get("provenance")
            if quality in c.PROVENANCE_QUALITY_VALUES:
                return quality
            state = row.get("state")
            has_commit = bool(str(row.get("installed_commit") or "").strip())
            has_repo = bool(str(row.get("repository_url") or "").strip())
            if state == "wrong_revision":
                return c.PROVENANCE_DECLARED
            if state == "missing":
                return (
                    c.PROVENANCE_DECLARED if has_repo else c.PROVENANCE_UNRESOLVED
                )
            if state == "installed":
                return (
                    c.PROVENANCE_DECLARED if has_commit else c.PROVENANCE_INFERRED
                )
            return c.PROVENANCE_UNRESOLVED
    return c.PROVENANCE_UNRESOLVED


def _provenance_revision(evidence: PortabilityEvidence, cls: str) -> str:
    entry = evidence.node_provenance.get(cls)
    if isinstance(entry, dict):
        rev = entry.get("revision")
        if isinstance(rev, str) and rev.strip():
            return rev.strip()
    for row in evidence.custom_node_evidence:
        classes = row.get("classes") or ()
        if cls in {str(x) for x in classes}:
            for key in ("required_revision", "installed_commit"):
                val = row.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    return ""


def _detect_extraction_gaps(evidence: PortabilityEvidence, prompt) -> list:
    """Loader-like model references current extraction does not understand.

    A gap is a loader-suffixed class with a model-extension string input for
    which NO supplied model-evidence row exists (the motivating audited case:
    ModelPatchLoader). Explicitly supplied ``extraction_gap_refs`` are
    honored verbatim. No extraction mappings are patched here.
    """
    gaps: dict[tuple, dict] = {}
    for ref in evidence.extraction_gap_refs:
        if isinstance(ref, dict):
            key = (
                str(ref.get("class_type") or "?"),
                str(ref.get("input") or "?"),
                str(ref.get("filename") or "?"),
            )
            gaps[key] = {
                "class_type": key[0],
                "input": key[1],
                "filename": key[2],
            }
    tracked = {
        str(row.get("filename"))
        for row in evidence.model_evidence
        if isinstance(row.get("filename"), str)
    }
    if prompt:
        for _node_id, node in _iter_prompt_nodes(prompt):
            class_type = str(node.get("class_type") or "")
            if "loader" not in class_type.lower():
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for name, value in inputs.items():
                if not isinstance(value, str) or not _MODEL_EXT_RE.search(value):
                    continue
                if value in tracked:
                    continue
                key = (class_type, str(name), value)
                gaps.setdefault(
                    key,
                    {"class_type": class_type, "input": str(name), "filename": value},
                )
    return [gaps[k] for k in sorted(gaps)]


# ── Issue emission (workflow-domain only) ─────────────────────────────────


def _emit_issues(evidence: PortabilityEvidence, signals: dict) -> list:
    issues = []

    def add(code, severity, message, subject, fix_hint="", evidence_payload=None):
        issues.append(
            c.build_issue(
                code=code,
                severity=severity,
                message=message,
                subject=subject,
                fix_hint=fix_hint,
                evidence=evidence_payload,
            )
        )

    path_values = signals["__path_values__"]
    if path_values:
        add(
            c.ISSUE_LOCAL_PATH_REFERENCE,
            c.SEVERITY_MEDIUM,
            "%d environment-bound filesystem path value(s) referenced by "
            "functional workflow inputs (%s)."
            % (len(path_values), _join_names(path_values)),
            c.SUBJECT_PATHS,
            "Replace host-bound paths with ComfyUI folder-relative basenames.",
            {"samples": _clean_samples(path_values), "count": len(path_values)},
        )

    unresolved = [
        cls
        for cls in _custom_classes(evidence)
        if _provenance_quality(evidence, cls) == c.PROVENANCE_UNRESOLVED
    ]
    if unresolved:
        add(
            c.ISSUE_UNRESOLVED_NODE_TYPE,
            c.SEVERITY_HIGH,
            "%d required node class(es) have no usable identity evidence: %s."
            % (len(unresolved), _join_names(unresolved)),
            c.SUBJECT_CUSTOM_NODES,
            "Install or map the owning node package, then re-run analysis.",
            {"classes": _clean_samples(unresolved), "count": len(unresolved)},
        )

    unpinned = [
        cls
        for cls in _custom_classes(evidence)
        if _provenance_quality(evidence, cls) != c.PROVENANCE_EXACT
        or not _provenance_revision(evidence, cls)
    ]
    if unpinned:
        add(
            c.ISSUE_CUSTOM_NODE_UNPINNED,
            c.SEVERITY_MEDIUM,
            "%d custom node class(es) lack trusted revision pinning: %s."
            % (len(unpinned), _join_names(unpinned)),
            c.SUBJECT_CUSTOM_NODES,
            "Pin exact trusted repo revisions for each custom node.",
            {"classes": _clean_samples(unpinned), "count": len(unpinned)},
        )

    unpinned_hashes = signals["__unpinned_model_hashes__"]
    if unpinned_hashes:
        add(
            c.ISSUE_MODEL_HASH_UNPINNED,
            c.SEVERITY_MEDIUM,
            "%d model reference(s) have no pinned sha256: %s."
            % (len(unpinned_hashes), _join_names(unpinned_hashes)),
            c.SUBJECT_MODELS,
            "Populate sha256 in the model library and pin hashes at export.",
            {
                "filenames": _clean_samples(unpinned_hashes),
                "count": len(unpinned_hashes),
            },
        )

    gap_refs = signals["__gap_refs__"]
    if gap_refs:
        labels = ["%s.%s" % (g["class_type"], g["input"]) for g in gap_refs]
        add(
            c.ISSUE_MODEL_EXTRACTION_GAP,
            c.SEVERITY_MEDIUM,
            "%d model-like loader input(s) are not covered by known extraction "
            "mappings: %s." % (len(labels), _join_names(labels)),
            c.SUBJECT_MODELS,
            "Extend model-ref extraction mappings for these loader classes.",
            {
                "refs": _clean_samples(
                    ["%s.%s=%s" % (g["class_type"], g["input"], g["filename"])
                     for g in gap_refs]
                ),
                "count": len(labels),
            },
        )

    missing_models_with_source = []
    missing_models_without_source = []
    missing_nodes_with_repo = []
    wrong_revision = []
    for row in evidence.model_evidence:
        state = row.get("state")
        filename = str(row.get("filename") or "")
        sources = row.get("source_urls") or ()
        if state == "missing":
            if sources:
                missing_models_with_source.append(filename)
            else:
                missing_models_without_source.append(filename)
        elif state == "wrong_version":
            wrong_revision.append("model:%s" % filename)
    for row in evidence.custom_node_evidence:
        state = row.get("state")
        name = str(row.get("name") or "")
        if state == "missing":
            missing_nodes_with_repo.append(name)
        elif state == "wrong_revision":
            wrong_revision.append("node:%s" % name)

    missing_total = (
        len(missing_models_with_source)
        + len(missing_models_without_source)
        + len(missing_nodes_with_repo)
    )
    if missing_total:
        parts = []
        subjects = []
        if missing_models_with_source or missing_models_without_source:
            parts.append(
                "models: %s"
                % _join_names(
                    missing_models_with_source + missing_models_without_source
                )
            )
            subjects.append(c.SUBJECT_MODELS)
        if missing_nodes_with_repo:
            parts.append("custom nodes: %s" % _join_names(missing_nodes_with_repo))
            subjects.append(c.SUBJECT_CUSTOM_NODES)
        unsourceable = len(missing_models_without_source)
        severity = (
            c.SEVERITY_HIGH if unsourceable else c.SEVERITY_MEDIUM
        )
        message = "Required dependencies are missing (%s)." % "; ".join(parts)
        if unsourceable:
            message += (
                " %d model reference(s) expose no source reference." % unsourceable
            )
        add(
            c.ISSUE_DEPENDENCY_MISSING,
            severity,
            message,
            subjects[0],
            "Install the missing dependencies on the target or attach source "
            "references.",
            {
                "models_without_source": _clean_samples(missing_models_without_source),
                "count": missing_total,
            },
        )
    if wrong_revision:
        add(
            c.ISSUE_DEPENDENCY_WRONG_REVISION,
            c.SEVERITY_MEDIUM,
            "%d installed dependenc(y/ies) differ from the required revision: %s."
            % (len(wrong_revision), _join_names(wrong_revision)),
            c.SUBJECT_MODELS if wrong_revision[0].startswith("model:") else c.SUBJECT_CUSTOM_NODES,
            "Align installed revisions/hashes with the required pins.",
            {"items": _clean_samples(wrong_revision), "count": len(wrong_revision)},
        )

    asset_labels = list(signals["__asset_classes__"])
    asset_labels.extend(
        str(a.get("filename") or a.get("name") or "?")
        for a in evidence.referenced_assets
        if isinstance(a, dict)
    )
    if signals[c.SIGNAL_REQUIRES_INPUT_ASSET]:
        add(
            c.ISSUE_REQUIRED_INPUT_ASSET,
            c.SEVERITY_MEDIUM,
            "%d external user asset requirement(s) must travel separately: %s."
            % (len(asset_labels), _join_names(asset_labels)),
            c.SUBJECT_ASSETS,
            "Ship referenced assets alongside the workflow into the target "
            "input folder.",
            {"assets": _clean_samples(asset_labels), "count": len(asset_labels)},
        )

    endpoints = signals["__endpoint_values__"]
    if endpoints:
        add(
            c.ISSUE_EXTERNAL_ENDPOINT_REFERENCE,
            c.SEVERITY_MEDIUM,
            "%d functional external endpoint(s) referenced by executable "
            "inputs: %s." % (len(endpoints), _join_names(endpoints)),
            c.SUBJECT_ENDPOINTS,
            "Confirm reachability from the target environment or remove the "
            "runtime dependency.",
            {"urls": _clean_samples(endpoints), "count": len(endpoints)},
        )

    credential_keys = signals["__credential_keys__"]
    if credential_keys:
        add(
            c.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED,
            c.SEVERITY_HIGH,
            "Credential-shaped input key(s) detected: %s."
            % _join_names(credential_keys),
            c.SUBJECT_GRAPH,
            "Remove embedded credentials; supply secrets via the environment.",
            {"keys": _clean_samples(credential_keys), "count": len(credential_keys)},
        )

    subgraph_count = signals["__subgraph_count__"]
    if subgraph_count:
        add(
            c.ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT,
            c.SEVERITY_LOW,
            "Graph defines %d subgraph definition(s); loading requires a "
            "frontend >= 1.44." % subgraph_count,
            c.SUBJECT_FRONTEND,
            "Ensure the target frontend >= 1.44 or flatten subgraphs.",
            {"count": subgraph_count},
        )

    readiness = evidence.manifest_readiness
    if isinstance(readiness, dict) and readiness.get("ready") is False:
        missing = [str(m) for m in (readiness.get("missing") or ()) if m]
        add(
            c.ISSUE_MANIFEST_NOT_READY,
            c.SEVERITY_HIGH,
            "Manifest structural readiness failed: %s." % _join_names(missing),
            c.SUBJECT_MANIFEST,
            "Fix manifest structure (hashes, repo/revision records) before "
            "export.",
            {"missing": _clean_samples(missing), "count": len(missing)},
        )

    if signals[c.SIGNAL_ENV_BOUND_REGISTRY_LEAK]:
        add(
            ISSUE_ENV_BOUND_REGISTRY_LEAK,
            c.SEVERITY_MEDIUM,
            "Supplied evidence indicates the export would include "
            "environment-bound registry paths (local_path/install_path).",
            c.SUBJECT_ENVIRONMENT,
            "Scrub local_path/install_path fields before export.",
        )

    if (
        signals[c.SIGNAL_EXACT_ROUNDTRIP_PROVEN] is False
        and evidence.exact_roundtrip_proven_override is None
        and _resolved_executable_prompt(evidence)
        and c.is_sha256_hex(evidence.graph_hash)
    ):
        add(
            ISSUE_GRAPH_HASH_MISMATCH,
            c.SEVERITY_MEDIUM,
            "Supplied graph_hash does not match the recomputed canonical hash "
            "of the executable prompt.",
            c.SUBJECT_GRAPH,
            "Re-capture the version or correct the supplied evidence.",
        )

    return issues


def _custom_classes(evidence: PortabilityEvidence) -> list:
    node_classes = set()
    dm = (
        evidence.dependency_metadata
        if isinstance(evidence.dependency_metadata, dict)
        else {}
    )
    raw = dm.get("node_classes")
    if isinstance(raw, (list, tuple)):
        node_classes = {str(x) for x in raw if x}
    prompt = _resolved_executable_prompt(evidence)
    if prompt:
        for _nid, node in _iter_prompt_nodes(prompt):
            ct = node.get("class_type")
            if ct:
                node_classes.add(str(ct))
    return sorted(cls for cls in node_classes if cls not in evidence.core_classes)


# ── Core analysis ──────────────────────────────────────────────────────────


def analyze_workflow_version(evidence, analyzed_at=None) -> dict:
    """Analyze one immutable WorkflowVersion from prepared evidence.

    Returns a partial report payload: version identity, risk_level, counts,
    deterministic issue list, and frozen static signals. UNKNOWN is returned
    (never normalized away) when essential analysis is impossible:
    structurally unreadable input, missing executable prompt, or an
    explicitly unavailable critical evidence provider.
    """
    if not isinstance(evidence, PortabilityEvidence):
        try:
            evidence = make_evidence(**dict(evidence or {}))
        except Exception:
            evidence = None
    if evidence is None:
        return _unknown_result(
            version_id="unknown",
            graph_hash="",
            reason="analyzer input could not be interpreted",
            analyzed_at=analyzed_at,
        )

    vid = str(evidence.version_id or "").strip() or "unknown"
    gh = evidence.graph_hash if c.is_sha256_hex(evidence.graph_hash) else ""

    unreadable = _structural_unreadable_reason(evidence)
    if unreadable:
        return _unknown_result(vid, gh, unreadable, analyzed_at)

    prompt = _resolved_executable_prompt(evidence)
    if not prompt:
        return _unknown_result(
            vid, gh, "no executable prompt available for analysis", analyzed_at
        )
    if not gh:
        return _unknown_result(
            vid,
            gh,
            "graph_hash missing or not a valid sha256 hex digest",
            analyzed_at,
        )
    if not evidence.models_available or not evidence.custom_nodes_available:
        unavailable = []
        if not evidence.models_available:
            unavailable.append("model evidence provider")
        if not evidence.custom_nodes_available:
            unavailable.append("custom-node evidence provider")
        return _unknown_result(
            vid,
            gh,
            "critical evidence provider explicitly unavailable: %s"
            % ", ".join(unavailable),
            analyzed_at,
        )

    signals = compute_signals(evidence)
    issues = _emit_issues(evidence, signals)
    issues = c.sort_issues(issues)
    counts = {sev: 0 for sev in c.COUNT_KEYS}
    for issue in issues:
        counts[issue["severity"]] += 1

    if counts[c.SEVERITY_HIGH] > 0:
        risk = c.PortabilityRiskLevel.HIGH
    elif counts[c.SEVERITY_MEDIUM] > 0:
        risk = c.PortabilityRiskLevel.MEDIUM
    else:
        risk = c.PortabilityRiskLevel.LOW

    return {
        "version_id": vid,
        "graph_hash": gh,
        "risk_level": risk,
        "rule_version": c.PORTABILITY_RULE_VERSION,
        "issue_count": len(issues),
        "counts": counts,
        "issues": issues,
        "signals": c.normalize_signals(_public_signals(signals)),
        "unknown_reason": None,
    }


def _unknown_result(version_id: str, graph_hash: str, reason: str, analyzed_at) -> dict:
    """Report-level UNKNOWN with one explanatory issue (never LOW/MEDIUM)."""
    vid = str(version_id or "").strip() or "unknown"
    gh = graph_hash if c.is_sha256_hex(graph_hash) else ""
    if not gh:
        gh = c.sha256_of_canonical(
            {"analysis_unavailable": True, "reason": reason, "version_id": vid}
        )
    issue = c.build_issue(
        code=ISSUE_ANALYSIS_UNAVAILABLE,
        severity=c.SEVERITY_MEDIUM,
        message="Analysis unavailable: %s." % reason,
        subject=c.SUBJECT_GRAPH,
        fix_hint="Supply readable evidence and re-run analysis.",
        evidence={"reason": reason[:_SAMPLE_TRUNCATE]},
    )
    return {
        "version_id": vid,
        "graph_hash": gh,
        "risk_level": c.PortabilityRiskLevel.UNKNOWN,
        "rule_version": c.PORTABILITY_RULE_VERSION,
        "issue_count": 1,
        "counts": {c.SEVERITY_HIGH: 0, c.SEVERITY_MEDIUM: 1, c.SEVERITY_LOW: 0},
        "issues": [issue],
        "signals": {},
        "unknown_reason": reason,
    }


# ── Environment reproducibility (distinct section; isolated) ──────────────


def build_environment_result(env_evidence, analyzed_at=None) -> dict:
    """Assemble the environment section from PREPARED facts (pure).

    ``env_evidence`` maps dimension keys to True/False/None (None = unknown,
    never fabricated into a finding):
      torch_stack_pinned          False → torch_stack_unpinned (high)
      custom_node_sources_pinned  False → custom_node_source_unpinned (high)
      plugin_worktree_clean       False → plugin_worktree_dirty (high)
      local_core_patch_diverged   True  → local_core_patch_divergence (high)
      model_hashes_pinned         False → model_hash_unpinned (medium)
      base_image_digest_pinned    False → base_image_digest_unpinned (medium)

    The result NEVER feeds workflow or target risk (G5 isolation policy).
    """
    del analyzed_at  # environment section carries no timestamp of its own
    facts = env_evidence if isinstance(env_evidence, dict) else None
    issues = []
    if facts is None:
        issues.append(
            c.build_issue(
                code=ISSUE_ANALYSIS_UNAVAILABLE,
                severity=c.SEVERITY_MEDIUM,
                message="Analysis unavailable: no environment evidence supplied.",
                subject=c.SUBJECT_ENVIRONMENT,
                fix_hint="Supply prepared environment facts and re-run.",
            )
        )
        return {
            "risk_level": c.PortabilityRiskLevel.UNKNOWN,
            "issues": issues,
            "source": c.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
        }

    def fact(key):
        value = facts.get(key)
        return value if isinstance(value, bool) else None

    dimension_specs = (
        ("torch_stack_pinned", False, c.ENV_TORCH_STACK_UNPINNED, c.SEVERITY_HIGH,
         "Torch/torchvision/torchaudio stack has no version pins."),
        ("custom_node_sources_pinned", False, c.ENV_CUSTOM_NODE_SOURCE_UNPINNED,
         c.SEVERITY_HIGH,
         "Custom-node sources are deployed without recorded/enforced revisions."),
        ("plugin_worktree_clean", False, c.ENV_PLUGIN_WORKTREE_DIRTY, c.SEVERITY_HIGH,
         "Plugin deployment is a dirty working tree with no reproducing ref."),
        ("local_core_patch_diverged", True, c.ENV_LOCAL_CORE_PATCH_DIVERGENCE,
         c.SEVERITY_HIGH,
         "Local ComfyUI core carries patches that exist in no published ref."),
        ("model_hashes_pinned", False, c.ENV_MODEL_HASH_UNPINNED, c.SEVERITY_MEDIUM,
         "Model bytes are not pinned by sha256 coverage."),
        ("base_image_digest_pinned", False, c.ENV_BASE_IMAGE_DIGEST_UNPINNED,
         c.SEVERITY_MEDIUM,
         "Container base image is referenced by mutable tag without digest."),
    )
    any_known = False
    for key, bad_value, code, severity, message in dimension_specs:
        value = fact(key)
        if value is None:
            continue
        any_known = True
        if value == bad_value:
            issues.append(
                c.build_issue(
                    code=code,
                    severity=severity,
                    message=message,
                    subject=c.SUBJECT_ENVIRONMENT,
                )
            )
    if not any_known:
        issues.append(
            c.build_issue(
                code=ISSUE_ANALYSIS_UNAVAILABLE,
                severity=c.SEVERITY_MEDIUM,
                message=(
                    "Analysis unavailable: all environment dimensions unknown."
                ),
                subject=c.SUBJECT_ENVIRONMENT,
                fix_hint="Supply prepared environment facts and re-run.",
            )
        )
        return {
            "risk_level": c.PortabilityRiskLevel.UNKNOWN,
            "issues": issues,
            "source": c.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
        }

    issues = c.sort_issues(issues)
    if any(i["severity"] == c.SEVERITY_HIGH for i in issues):
        risk = c.PortabilityRiskLevel.HIGH
    elif any(i["severity"] == c.SEVERITY_MEDIUM for i in issues):
        risk = c.PortabilityRiskLevel.MEDIUM
    else:
        risk = c.PortabilityRiskLevel.LOW
    return {
        "risk_level": risk,
        "issues": issues,
        "source": c.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
    }


# ── Full report assembly ──────────────────────────────────────────────────


def assemble_report(
    workflow_result,
    *,
    target_results=None,
    environment_result=None,
    invalidation=None,
    analyzed_at=None,
    stale=False,
) -> dict:
    """Combine workflow risk + supplied target results + environment +
    invalidation stamp into the frozen report payload (contract-validated).

    Target results are ACCEPTED, never computed: G6 owns no target policy.
    Absent targets default to honest ``unknown`` with advice pointing at the
    target-rules lane (G7).
    """
    if analyzed_at is None:
        analyzed_at = _utc_now_iso()

    targets = {}
    supplied = target_results if isinstance(target_results, dict) else {}
    for tid in c.TARGET_IDS:
        result = supplied.get(tid)
        if isinstance(result, dict):
            targets[tid] = c.make_target_result(
                risk_level=c.normalize_risk_level(result.get("risk_level")),
                issue_codes=result.get("issue_codes"),
                advice=result.get("advice"),
            )
        else:
            targets[tid] = c.make_target_result(
                risk_level=c.PortabilityRiskLevel.UNKNOWN,
                issue_codes=[],
                advice=["target rules not evaluated"],
            )

    if environment_result is None:
        environment = build_environment_result(None)
    else:
        environment = {
            "risk_level": c.normalize_risk_level(environment_result.get("risk_level")),
            "issues": [
                c.normalize_issue(i) for i in (environment_result.get("issues") or [])
            ],
            "source": c.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
        }

    if invalidation is None:
        invalidation = c.build_invalidation_stamp()

    report = {
        "version_id": workflow_result["version_id"],
        "graph_hash": workflow_result["graph_hash"],
        "risk_level": c.normalize_risk_level(workflow_result["risk_level"]),
        "rule_version": c.PORTABILITY_RULE_VERSION,
        "issue_count": workflow_result["issue_count"],
        "counts": dict(workflow_result["counts"]),
        "issues": [c.normalize_issue(i) for i in workflow_result["issues"]],
        "signals": c.normalize_signals(workflow_result.get("signals") or {}),
        "targets": targets,
        "environment": environment,
        "stale": bool(stale),
        "invalidation": invalidation,
        "analyzed_at": str(analyzed_at),
    }
    c.validate_report(report)
    return report


def build_workflow_report(evidence, *, analyzed_at=None, **assemble_kwargs) -> dict:
    """Convenience: analyze one version and assemble the full report."""
    result = analyze_workflow_version(evidence, analyzed_at=analyzed_at)
    return assemble_report(result, analyzed_at=analyzed_at, **assemble_kwargs)


__all__ = [
    "PortabilityEvidence",
    "make_evidence",
    "evidence_from_version_record",
    "compute_signals",
    "analyze_workflow_version",
    "build_environment_result",
    "assemble_report",
    "build_workflow_report",
    "ISSUE_GRAPH_HASH_MISMATCH",
    "ISSUE_ENV_BOUND_REGISTRY_LEAK",
    "ISSUE_ANALYSIS_UNAVAILABLE",
    "NEW_ISSUE_CODES",
    "ALL_ENGINE_ISSUE_CODES",
]
