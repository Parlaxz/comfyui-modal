"""Pure studio-workflow manifest assembly, validation, canonicalization, hashing.

A manifest is a JSON-shaped dict with fixed root sections (``ROOT_SECTIONS``).
This module performs NO I/O, NO network, NO filesystem access and imports only
the stdlib; every public function is pure.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any

MANIFEST_SCHEMA_VERSION = 1
SUPPORTED_MANIFEST_VERSIONS = (1,)
HASH_ALGORITHM = "sha256"

ROOT_SECTIONS = (
    "manifest_version",
    "workflow",
    "version",
    "mapping",
    "presets",
    "models",
    "custom_nodes",
    "assets",
    "metadata",
)
REQUIRED_ROOTS = ("manifest_version", "workflow", "version", "mapping")

# Canonical JSON serialisation (project convention, see production_workflow.py).
_CANONICAL_JSON_KWARGS = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": False,
    "allow_nan": False,
}

_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")


class ManifestValidationError(ValueError):
    """Raised when a manifest fails validation; carries every issue found."""

    def __init__(self, issues):
        self.issues = list(issues)
        super().__init__("; ".join(self.issues))


# ── Private helpers ───────────────────────────────────────────────────────


def _sha256_hex(s) -> bool:
    """Return True when ``s`` is a 64-char lowercase sha256 hex string."""
    return isinstance(s, str) and _SHA256_HEX_RE.fullmatch(s) is not None


def _is_number(o) -> bool:
    return isinstance(o, (int, float)) and not isinstance(o, bool)


def _is_finite_number(o) -> bool:
    return _is_number(o) and (not isinstance(o, float) or math.isfinite(o))


def _deep_sort(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _deep_sort(o[k]) for k in sorted(o, key=lambda k: str(k))}
    if isinstance(o, list):
        return [_deep_sort(v) for v in o]
    return o


def _reject_json_constant(name: str):
    raise ValueError("non-finite JSON constant: %s" % name)


def _append_issue(issues, message):
    issues.append(message)


def _collect_issues(manifest) -> list:
    """Collect every validation issue; never raises."""
    issues = []
    if not isinstance(manifest, dict):
        _append_issue(issues, "root manifest must be a dict")
        return issues

    for key in manifest:
        if key not in ROOT_SECTIONS:
            _append_issue(issues, "unknown root section: %r" % (key,))
    for name in REQUIRED_ROOTS:
        if name not in manifest:
            _append_issue(issues, "missing required section: %s" % name)

    mv = manifest.get("manifest_version")
    if isinstance(mv, bool) or not isinstance(mv, int):
        _append_issue(issues, "manifest_version must be an int")
    elif mv not in SUPPORTED_MANIFEST_VERSIONS:
        supported = ", ".join(str(v) for v in SUPPORTED_MANIFEST_VERSIONS)
        _append_issue(issues, "unsupported manifest version: %s (supported: %s)" % (mv, supported))

    wf = manifest.get("workflow")
    if wf is not None and not isinstance(wf, dict):
        _append_issue(issues, "workflow must be a dict")
        wf = None
    if isinstance(wf, dict):
        wf_id = wf.get("workflow_id")
        if not isinstance(wf_id, str) or not wf_id:
            _append_issue(issues, "workflow.workflow_id must be a non-empty string")
        wf_vid = wf.get("version_id")
        if not isinstance(wf_vid, str) or not wf_vid:
            _append_issue(issues, "workflow.version_id must be a non-empty string")
        graph = wf.get("graph")
        if not isinstance(graph, dict):
            _append_issue(issues, "workflow.graph must be a dict (graph JSON object)")
        gh = wf.get("graph_hash")
        if not isinstance(gh, str) or not _sha256_hex(gh):
            _append_issue(issues, "workflow.graph_hash must be a 64-character lowercase hex sha256")
        elif isinstance(graph, dict):
            try:
                expected = graph_hash(graph)
            except ValueError:
                _append_issue(
                    issues,
                    "workflow.graph_hash does not match canonical hash of embedded graph "
                    "(graph contains non-finite values)",
                )
            else:
                if gh != expected:
                    _append_issue(
                        issues,
                        "workflow.graph_hash does not match canonical hash of embedded graph",
                    )
        for key in ("display", "source"):
            val = wf.get(key)
            if val is not None and not isinstance(val, dict):
                _append_issue(issues, "workflow.%s must be a dict if present" % key)

    vs = manifest.get("version")
    if vs is not None and not isinstance(vs, dict):
        _append_issue(issues, "version must be a dict")
        vs = None
    if isinstance(vs, dict):
        vs_vid = vs.get("workflow_version_id")
        if not isinstance(vs_vid, str) or not vs_vid:
            _append_issue(issues, "version.workflow_version_id must be a non-empty string")
        vs_wfid = vs.get("workflow_id")
        if not isinstance(vs_wfid, str) or not vs_wfid:
            _append_issue(issues, "version.workflow_id must be a non-empty string")
        vn = vs.get("version_number")
        if isinstance(vn, bool) or not isinstance(vn, int):
            _append_issue(issues, "version.version_number must be an int")
        elif vn < 1:
            _append_issue(issues, "version.version_number must be >= 1")
        val = vs.get("immutable")
        if val is not None and not isinstance(val, bool):
            _append_issue(issues, "version.immutable must be a bool if present")
        vgh = vs.get("graph_hash")
        if vgh is not None and not _sha256_hex(vgh):
            _append_issue(issues, "version.graph_hash must be a 64-character lowercase hex sha256 if present")
        ca = vs.get("created_at")
        if ca is not None and not isinstance(ca, str):
            _append_issue(issues, "version.created_at must be a string if present")

    if isinstance(wf, dict) and isinstance(vs, dict):
        wf_vid = wf.get("version_id")
        vs_vid = vs.get("workflow_version_id")
        if (
            isinstance(wf_vid, str) and wf_vid and isinstance(vs_vid, str) and vs_vid
            and wf_vid != vs_vid
        ):
            _append_issue(issues, "workflow.version_id does not match version.workflow_version_id")
        wf_id = wf.get("workflow_id")
        vs_wfid = vs.get("workflow_id")
        if (
            isinstance(wf_id, str) and wf_id and isinstance(vs_wfid, str) and vs_wfid
            and wf_id != vs_wfid
        ):
            _append_issue(issues, "version.workflow_id does not match workflow.workflow_id")

    mp = manifest.get("mapping")
    if mp is not None and not isinstance(mp, dict):
        _append_issue(issues, "mapping must be a dict")
        mp = None
    if isinstance(mp, dict):
        mid = mp.get("mapping_id")
        if not isinstance(mid, str) or not mid:
            _append_issue(issues, "mapping.mapping_id must be a non-empty string")
        mp_vid = mp.get("workflow_version_id")
        if not isinstance(mp_vid, str) or not mp_vid:
            _append_issue(issues, "mapping.workflow_version_id must be a non-empty string")
        entries = mp.get("entries")
        if not isinstance(entries, dict):
            _append_issue(issues, "mapping.entries must be a dict")
        else:
            for role, entry in entries.items():
                if not isinstance(role, str) or not role:
                    _append_issue(issues, "mapping.entries keys must be non-empty strings (semantic roles)")
                    continue
                if not isinstance(entry, dict):
                    _append_issue(issues, "mapping.entries[%r] must be a dict" % role)
                    continue
                for fld in ("required", "multiline"):
                    val = entry.get(fld)
                    if val is not None and not isinstance(val, bool):
                        _append_issue(issues, "mapping.entries[%r].%s must be a bool" % (role, fld))
                val = entry.get("enum_options")
                if val is not None and not isinstance(val, list):
                    _append_issue(issues, "mapping.entries[%r].enum_options must be a list" % role)
                for fld in ("minimum", "maximum", "step"):
                    val = entry.get(fld)
                    if val is not None and not _is_finite_number(val):
                        _append_issue(
                            issues, "mapping.entries[%r].%s must be a finite number or None" % (role, fld)
                        )
                for fld in (
                    "node_id", "input_name", "output_name", "kind",
                    "data_type", "control_kind", "display_name",
                ):
                    val = entry.get(fld)
                    if val is not None and not isinstance(val, str):
                        _append_issue(issues, "mapping.entries[%r].%s must be a string" % (role, fld))
        onid = mp.get("output_node_id")
        if onid is not None and not isinstance(onid, str):
            _append_issue(issues, "mapping.output_node_id must be a string if present")

    if isinstance(mp, dict) and isinstance(vs, dict):
        mp_vid = mp.get("workflow_version_id")
        vs_vid = vs.get("workflow_version_id")
        if (
            isinstance(mp_vid, str) and mp_vid and isinstance(vs_vid, str) and vs_vid
            and mp_vid != vs_vid
        ):
            _append_issue(issues, "mapping.workflow_version_id does not match version.workflow_version_id")

    for name in ("presets", "models", "custom_nodes", "assets"):
        val = manifest.get(name)
        if val is None:
            continue
        if not isinstance(val, list):
            _append_issue(issues, "%s must be a list" % name)
        else:
            for item in val:
                if not isinstance(item, dict):
                    _append_issue(issues, "%s entries must be dicts" % name)

    presets = manifest.get("presets")
    if isinstance(presets, list):
        seen_ids = {}
        default_count = 0
        for idx, p in enumerate(presets):
            if not isinstance(p, dict):
                continue
            pid = p.get("preset_id")
            if not isinstance(pid, str) or not pid:
                _append_issue(issues, "preset at index %d: preset_id must be a non-empty string" % idx)
                pid = None
            if pid is not None:
                if pid in seen_ids:
                    _append_issue(issues, "duplicate preset id: %s" % pid)
                seen_ids[pid] = True
            label = pid if pid is not None else ("index %d" % idx)
            pwvid = p.get("workflow_version_id")
            if not isinstance(pwvid, str) or not pwvid:
                _append_issue(issues, "preset %s: workflow_version_id must be a non-empty string" % label)
            nm = p.get("name")
            if not isinstance(nm, str) or not nm:
                _append_issue(issues, "preset %s: name must be a non-empty string" % label)
            for fld in ("is_default", "favorite"):
                val = p.get(fld)
                if val is not None and not isinstance(val, bool):
                    _append_issue(issues, "preset %s: %s must be a bool" % (label, fld))
            if p.get("is_default") is True:
                default_count += 1
            for fld in ("exposed_controls", "dropped_controls", "tags"):
                val = p.get(fld)
                if val is None:
                    continue
                if not isinstance(val, list):
                    _append_issue(issues, "preset %s: %s must be a list" % (label, fld))
                else:
                    for item in val:
                        if not isinstance(item, str):
                            _append_issue(issues, "preset %s: %s items must be strings" % (label, fld))
            for fld in ("values", "model_choices", "lora_values", "recommended_values"):
                val = p.get(fld)
                if val is not None and not isinstance(val, dict):
                    _append_issue(issues, "preset %s: %s must be a dict" % (label, fld))
            for fld in ("description", "created_at", "updated_at"):
                val = p.get(fld)
                if val is not None and not isinstance(val, str):
                    _append_issue(issues, "preset %s: %s must be a string" % (label, fld))
        if default_count > 1:
            _append_issue(issues, "multiple default presets")

    if isinstance(vs, dict) and isinstance(presets, list):
        vs_vid = vs.get("workflow_version_id")
        for p in presets:
            if not isinstance(p, dict):
                continue
            pid = p.get("preset_id")
            label = pid if isinstance(pid, str) and pid else "?"
            pwvid = p.get("workflow_version_id")
            if (
                isinstance(vs_vid, str) and vs_vid and isinstance(pwvid, str) and pwvid
                and pwvid != vs_vid
            ):
                _append_issue(issues, "preset %s is not associated with the manifest version" % label)

    models = manifest.get("models")
    if isinstance(models, list):
        seen_identities = {}
        for idx, rec in enumerate(models):
            if not isinstance(rec, dict):
                continue
            fn = rec.get("filename")
            if not isinstance(fn, str) or not fn:
                _append_issue(issues, "model at index %d: filename must be a non-empty string" % idx)
                fn = None
            label = fn if fn is not None else ("index %d" % idx)
            h = rec.get("sha256")
            if h is not None:
                if not _sha256_hex(h):
                    _append_issue(issues, "invalid model hash: %s" % label)
                    h = None
            if fn is not None:
                identity = (fn, h)
                if identity in seen_identities:
                    htxt = h if h is not None else "no hash"
                    _append_issue(issues, "duplicate model dependency: %s (%s)" % (fn, htxt))
                seen_identities[identity] = True
            sz = rec.get("size")
            if sz is not None:
                if isinstance(sz, bool) or not isinstance(sz, int):
                    _append_issue(issues, "model %s: size must be an int" % label)
                elif sz < 0:
                    _append_issue(issues, "model %s: size must be >= 0" % label)
            for fld in ("folder", "model_type", "display_name", "provider", "revision", "compatibility", "role"):
                val = rec.get(fld)
                if val is not None and not isinstance(val, str):
                    _append_issue(issues, "model %s: %s must be a string" % (label, fld))
            urls = rec.get("source_urls")
            if urls is not None:
                if not isinstance(urls, list):
                    _append_issue(issues, "model %s: source_urls must be a list" % label)
                else:
                    for u in urls:
                        if not isinstance(u, str):
                            _append_issue(issues, "model %s: source_urls items must be strings" % label)

    custom_nodes = manifest.get("custom_nodes")
    if isinstance(custom_nodes, list):
        seen_pairs = set()
        for idx, c in enumerate(custom_nodes):
            if not isinstance(c, dict):
                continue
            url = c.get("repo_url")
            if not isinstance(url, str) or not url:
                _append_issue(issues, "custom node at index %d: repo_url must be a non-empty string" % idx)
                url = None
            elif url != url.strip():
                _append_issue(issues, "custom node %s: repo_url must not have leading/trailing whitespace" % url)
            rev = c.get("revision")
            if not isinstance(rev, str) or not rev:
                _append_issue(
                    issues,
                    "custom node %s: revision must be a non-empty string"
                    % (url if url is not None else ("index %d" % idx)),
                )
                rev = None
            if url is not None and rev is not None:
                pair = (url, rev)
                if pair in seen_pairs:
                    _append_issue(issues, "duplicate custom-node dependency: %s@%s" % (url, rev))
                seen_pairs.add(pair)
            label = url if url is not None else ("index %d" % idx)
            clist = c.get("classes")
            if clist is not None:
                if not isinstance(clist, list):
                    _append_issue(issues, "custom node %s: classes must be a list" % label)
                else:
                    for s in clist:
                        if not isinstance(s, str) or not s:
                            _append_issue(issues, "custom node %s: classes items must be non-empty strings" % label)
            for fld in ("name", "display_name"):
                val = c.get(fld)
                if val is not None and not isinstance(val, str):
                    _append_issue(issues, "custom node %s: %s must be a string" % (label, fld))

    assets = manifest.get("assets")
    if isinstance(assets, list):
        for idx, a in enumerate(assets):
            if not isinstance(a, dict):
                continue
            fn = a.get("filename")
            if not isinstance(fn, str) or not fn:
                _append_issue(issues, "asset at index %d: filename must be a non-empty string" % idx)
                fn = None
            label = fn if fn is not None else ("index %d" % idx)
            h = a.get("sha256")
            if h is not None and not _sha256_hex(h):
                _append_issue(issues, "asset %s: sha256 must be a 64-character lowercase hex string" % label)
            sz = a.get("size")
            if sz is not None:
                if isinstance(sz, bool) or not isinstance(sz, int):
                    _append_issue(issues, "asset %s: size must be an int" % label)
                elif sz < 0:
                    _append_issue(issues, "asset %s: size must be >= 0" % label)
            for fld in ("mime_type", "role"):
                val = a.get(fld)
                if val is not None and not isinstance(val, str):
                    _append_issue(issues, "asset %s: %s must be a string" % (label, fld))

    md = manifest.get("metadata")
    if md is not None and not isinstance(md, dict):
        _append_issue(issues, "metadata must be a dict")

    return issues


# ── Public API ────────────────────────────────────────────────────────────


def graph_hash(graph: dict) -> str:
    """SHA-256 of a graph dict via canonical JSON (raises ValueError on non-finite floats)."""
    encoded = json.dumps(graph, **_CANONICAL_JSON_KWARGS)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonicalize(manifest: dict) -> dict:
    """Return a NEW dict with keys recursively sorted; lists keep their order."""
    return _deep_sort(manifest)


def canonical_json(manifest: dict) -> str:
    """Canonical JSON string (sorted keys, compact separators, no NaN)."""
    return json.dumps(
        canonicalize(manifest), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def canonical_bytes(manifest: dict) -> bytes:
    """UTF-8 bytes of canonical_json(manifest)."""
    return canonical_json(manifest).encode("utf-8")


def manifest_hash(manifest: dict, include_metadata: bool = True) -> str:
    """SHA-256 hex digest over canonical bytes.

    When ``include_metadata`` is False the metadata root is replaced with {}
    before hashing (timestamps live in metadata and are thereby excluded from
    identity).
    """
    if include_metadata:
        data = manifest
    else:
        data = dict(manifest)
        data["metadata"] = {}
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def validate_manifest(manifest: dict) -> None:
    """Validate a manifest; raise ManifestValidationError carrying ALL issues."""
    issues = _collect_issues(manifest)
    if issues:
        raise ManifestValidationError(issues)


def build_manifest(
    *,
    workflow: dict,
    version: dict,
    mapping: dict,
    presets: list | None = None,
    models: list | None = None,
    custom_nodes: list | None = None,
    assets: list | None = None,
    metadata: dict | None = None,
) -> dict:
    """Assemble, validate, and canonicalize a manifest from section dicts.

    Missing optional collections become [], missing metadata becomes {}.
    No timestamps or other fields are ever added.
    """
    manifest = {
        "manifest_version": MANIFEST_SCHEMA_VERSION,
        "workflow": workflow,
        "version": version,
        "mapping": mapping,
        "presets": presets if presets is not None else [],
        "models": models if models is not None else [],
        "custom_nodes": custom_nodes if custom_nodes is not None else [],
        "assets": assets if assets is not None else [],
        "metadata": metadata if metadata is not None else {},
    }
    validate_manifest(manifest)
    return canonicalize(manifest)


def parse_manifest(source) -> dict:
    """Parse a dict/str/bytes manifest, validate, and return the canonical dict.

    Missing optional roots are normalized: presets/models/custom_nodes/assets
    become [], metadata becomes {}. Invalid JSON or validation failures raise
    ManifestValidationError.
    """
    if isinstance(source, dict):
        data = copy.deepcopy(source)
    elif isinstance(source, (str, bytes)):
        try:
            data = json.loads(source, parse_constant=_reject_json_constant)
        except ValueError as exc:
            raise ManifestValidationError(["invalid JSON: %s" % exc]) from None
    else:
        raise TypeError("parse_manifest expects a dict, str, or bytes")
    issues = _collect_issues(data)
    if issues:
        raise ManifestValidationError(issues)
    for name in ("presets", "models", "custom_nodes", "assets"):
        if name not in data:
            data[name] = []
    if "metadata" not in data:
        data["metadata"] = {}
    return canonicalize(data)


def check_readiness(manifest: dict) -> dict:
    """Pure structural readiness: return {"ready": bool, "missing": list}.

    Missing = model refs without a valid sha256 and custom nodes without
    repo_url or revision. No disk access; actual local resolution is a later
    wiring-time concern.
    """
    missing = []
    for rec in manifest.get("models") or []:
        if not isinstance(rec, dict):
            continue
        fn = rec.get("filename")
        h = rec.get("sha256")
        label = fn if isinstance(fn, str) and fn else "?"
        if not _sha256_hex(h):
            missing.append("models: %s (missing hash)" % label)
    for c in manifest.get("custom_nodes") or []:
        if not isinstance(c, dict):
            continue
        url = c.get("repo_url")
        rev = c.get("revision")
        if not (isinstance(url, str) and url and isinstance(rev, str) and rev):
            label = (
                url
                if isinstance(url, str) and url
                else (c.get("name") if isinstance(c.get("name"), str) and c.get("name") else "?")
            )
            missing.append("custom_nodes: %s (missing repo/revision)" % label)
    return {"ready": not missing, "missing": missing}
