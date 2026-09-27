"""Workflow-relevant registry proof for Step-3 plan validation parity.

Trust model
-----------
ComfyUI's ``validate_prompt`` outcomes (accept vs. reject) for a workflow
are fully determined by the workflow's own class set: every ``class_type``
in the prompt must resolve to a registered node class whose required inputs
are satisfiable by the graph.  This module proves that a target
(snapshot/deployment) registry covers exactly the classes a workflow needs,
pairing the workflow's class list with per-class canonical identities that
are:

* path-independent -- the digest hashes the root-relative *logical* module
  path (derived from caller-provided roots) plus the LF-normalized *content*
  of the class's defining module file, never the absolute on-disk path, so
  identical node source code yields identical identities even when host and
  container directory layouts differ; and
* code-content-sensitive -- any change to node implementation code changes
  the file hash and therefore the identity, so drifted node code
  invalidates parity instead of being silently accepted.

Matching on class presence + code identity is necessary for
``validate_prompt`` outcome parity; it does not by itself prove the
snapshot can *execute* the workflow, but it closes the class of failures
where "the workflow references a class the snapshot does not know".

The module is intentionally pure: it imports only the standard library and
``stable_hash`` from ``comfymodal_runtime.contracts`` (itself stdlib-only),
and never imports ``nodes`` / ComfyUI execution code at module scope.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping

from comfymodal_runtime.contracts import stable_hash

__all__ = [
    "class_canonical_identity",
    "workflow_class_types",
    "build_workflow_registry_proof",
    "build_registry_manifest",
    "evaluate_workflow_registry_parity",
    "format_registry_parity_line",
]

_BOUND = 20


def _resolve_module_file(cls: object) -> str:
    """Absolute path of the module file defining ``cls``.

    Resolution matches the legacy chain exactly: ``sys.modules.get(__module__)``
    -> ``__file__`` -> ``os.path.abspath``.  Only ``abspath`` is applied —
    symlinks are NEVER resolved (``realpath`` would collapse intentionally
    distinct container mounts and defeat the logical-path derivation).

    Returns ``""`` on any failure (module not loaded, no ``__file__``).
    """
    try:
        module = sys.modules.get(cls.__module__)  # type: ignore[attr-defined]
    except Exception:
        return ""
    if module is None:
        return ""
    try:
        path = getattr(module, "__file__", "")
    except Exception:
        return ""
    if not path:
        return ""
    try:
        return os.path.abspath(path)
    except Exception:
        return ""


def _resolve_logical_module_path(file_abs: str, roots) -> str:
    """PATH-INDEPENDENT logical module path for ``file_abs`` under ``roots``.

    For every non-empty root (abspath-normalized, trailing separator
    stripped) that *contains* ``file_abs`` (``commonpath`` == root), the
    ``relpath(file_abs, root)`` is computed; the SHORTEST relpath across
    matching roots wins.  Separators are normalized to ``"/"`` and any
    leading ``"./"`` is stripped.

    Fails closed: returns ``""`` when ``roots`` is empty/None or no root
    contains the file — a logical path is never guessed.  Absolute host vs.
    container paths therefore never participate in the identity: only the
    root-relative layout is hashed.
    """
    if not file_abs or not roots:
        return ""
    candidates: list[str] = []
    for root in roots:
        try:
            if not root:
                continue
            root_abs = os.path.abspath(str(root)).rstrip(os.sep) or os.sep
            if os.path.commonpath([root_abs, file_abs]) != root_abs:
                continue
            rel = os.path.relpath(file_abs, root_abs).replace(os.sep, "/")
            if rel.startswith("./"):
                rel = rel[2:]
            candidates.append(rel)
        except Exception:
            # Unrelated filesystem roots (e.g. different drives on Windows)
            # raise inside commonpath; skip that root.
            continue
    if not candidates:
        return ""
    return min(candidates, key=len)


def _resolve_file_sha256(cls: object, file_sha_cache: dict[str, str]) -> str:
    """sha256 of the module file *content* for ``cls``, cached per file path.

    The digest is computed over LF-normalized bytes
    (``\\r\\n``/``\\r`` -> ``\\n``): Python's byte-compiler semantics are
    identical for CRLF and LF working copies, so content-equal files must
    hash equal across the CRLF host and the LF container.

    Returns ``""`` on any failure (module not loaded, no ``__file__``,
    unreadable file) so callers fail closed.  Only file *content* is
    hashed; file paths never enter the digest.
    """
    try:
        module = sys.modules.get(cls.__module__)  # type: ignore[attr-defined]
    except Exception:
        return ""
    if module is None:
        return ""
    try:
        path = getattr(module, "__file__", "")
    except Exception:
        return ""
    if not path:
        return ""
    cached = file_sha_cache.get(path)
    if cached is not None:
        return cached
    try:
        with open(path, "rb") as fh:
            content = fh.read()
        content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        file_sha256 = hashlib.sha256(content).hexdigest()
    except Exception:
        file_sha256 = ""
    file_sha_cache[path] = file_sha256
    return file_sha256


def _class_identity(cls: object, file_sha_cache: dict[str, str], roots=None) -> str:
    """Shared implementation behind :func:`class_canonical_identity`.

    ``file_sha_cache`` lets callers dedupe file hashing across many classes
    that live in the same module file (e.g. ``nodes.py``).

    ``roots`` (same contract as :func:`class_canonical_identity`) derives the
    path-independent logical module path.  Fails closed (returns ``""``) when
    no root contains the module file — absolute paths never enter the digest.
    """
    try:
        name = cls.__name__  # type: ignore[attr-defined]
        qualname = cls.__qualname__  # type: ignore[attr-defined]
    except Exception:
        return ""
    file_abs = _resolve_module_file(cls)
    if not file_abs:
        return ""
    file_sha256 = _resolve_file_sha256(cls, file_sha_cache)
    if not file_sha256:
        return ""
    logical_module_path = _resolve_logical_module_path(file_abs, roots)
    if not logical_module_path:
        # Fail closed: without a root containing the module file there is no
        # stable logical path, so no canonical identity can be produced.
        return ""
    try:
        return stable_hash(
            {
                "class_name": name,
                "logical_module_path": logical_module_path,
                "qualname": qualname,
                "module_file_sha256": file_sha256,
            }
        )
    except Exception:
        return ""


def class_canonical_identity(cls: object, roots=None) -> str:
    """Canonical 64-hex sha256 identity for ``cls``, or ``""`` if unavailable.

    The identity hashes the class name, the PATH-INDEPENDENT logical module
    path (the shortest root-relative path of the defining module file across
    the given ``roots``, ``"/"``-normalized), the qualname, and the sha256 of
    the module file *content* (LF-normalized, so CRLF and LF working copies
    of the same code hash equal).  Absolute paths NEVER participate in the
    digest: identical node source under different directory layouts yields
    identical identities.

    ``roots`` is a non-empty iterable of directories used to derive the
    logical path.  When ``roots`` is empty/None, or no root contains the
    module file, the identity fails closed to ``""`` (a logical path is
    never guessed).  Any other failure (module missing, ``__file__``
    missing/empty, unreadable file, missing attrs) also yields ``""``.
    """
    return _class_identity(cls, {}, roots)


def workflow_class_types(workflow: object) -> list[str]:
    """Sorted unique ``class_type`` strings from a ComfyUI prompt dict.

    ``workflow`` maps node_id -> {"class_type": ...}; non-dict specs are
    skipped.  Empty input yields ``[]``.
    """
    if not isinstance(workflow, dict):
        return []
    seen: set[str] = set()
    for spec in workflow.values():
        if not isinstance(spec, dict):
            continue
        class_type = spec.get("class_type")
        if isinstance(class_type, str) and class_type:
            seen.add(class_type)
    return sorted(seen)


def build_workflow_registry_proof(
    workflow: object,
    class_mappings: Mapping[str, object] | None = None,
    roots=None,
    *,
    workflow_hash: str = "",
) -> dict:
    """Prove which registered classes a workflow depends on.

    ``class_mappings`` maps node name -> class.  When ``None`` it lazily
    imports ``nodes`` and uses ``NODE_CLASS_MAPPINGS``; on ImportError the
    result fails closed (empty, ``complete=False``, with an ``error`` key).

    ``roots`` is passed through to :func:`class_canonical_identity` so the
    per-class identities use path-independent logical module paths; when it
    is empty/None the identities fail closed (``unresolved_identity``).

    ``workflow_hash`` is an optional binding supplied by the dispatch planner.
    The proof remains class-set scoped, but carrying the exact dispatch hash
    makes the store/plan association auditable without changing legacy calls.
    """
    if class_mappings is None:
        try:
            import nodes  # type: ignore[import-not-found]
        except Exception as exc:
            return {
                "schema_version": 1,
                "workflow_class_count": 0,
                "classes": [],
                "identities": {},
                "missing_host": [],
                "unresolved_identity": [],
                "complete": False,
                "workflow_hash": str(workflow_hash or ""),
                "error": str(exc),
            }
        mappings: Mapping[str, object] = getattr(nodes, "NODE_CLASS_MAPPINGS", {})
    else:
        mappings = class_mappings

    classes = workflow_class_types(workflow)
    identities: dict[str, str] = {}
    missing_host: list[str] = []
    unresolved_identity: list[str] = []
    for name in classes:
        try:
            cls = mappings[name]
        except Exception:
            missing_host.append(name)
            continue
        if cls is None:
            missing_host.append(name)
            continue
        identity = class_canonical_identity(cls, roots=roots)
        identities[name] = identity
        if not identity:
            unresolved_identity.append(name)

    complete = bool(classes) and not missing_host and not unresolved_identity
    return {
        "schema_version": 1,
        "workflow_class_count": len(classes),
        "classes": classes,
        "identities": identities,
        "missing_host": missing_host,
        "unresolved_identity": unresolved_identity,
        "complete": complete,
        "workflow_hash": str(workflow_hash or ""),
    }


def build_registry_manifest(
    class_mappings: Mapping[str, object] | None = None,
    roots=None,
) -> dict:
    """Canonical identity manifest for ALL registered classes.

    ``class_mappings`` maps node name -> class; when ``None`` it lazily
    imports ``nodes``.  File hashing is deduped per resolved module file
    path within one call (many classes share ``nodes.py`` etc.).

    ``roots`` is passed through to the class-identity builder so identities
    use path-independent logical module paths; when it is empty/None the
    classes fail closed (``""`` identities recorded in ``incomplete_classes``).

    Never raises: per-class failures are recorded as ``""`` identities in
    ``incomplete_classes``; any mapping-iteration exception returns a
    fail-closed empty result with an ``error`` key.
    """
    try:
        if class_mappings is None:
            try:
                import nodes  # type: ignore[import-not-found]
            except Exception as exc:
                return {
                    "schema_version": 1,
                    "class_count": 0,
                    "classes": {},
                    "incomplete_classes": [],
                    "module_file_count": 0,
                    "error": str(exc),
                }
            mappings: Mapping[str, object] = getattr(nodes, "NODE_CLASS_MAPPINGS", {})
        else:
            mappings = class_mappings

        file_sha_cache: dict[str, str] = {}
        identities: dict[str, str] = {}
        incomplete_classes: list[str] = []
        for name in sorted(mappings):
            try:
                cls = mappings[name]
            except Exception:
                identities[name] = ""
                incomplete_classes.append(name)
                continue
            identity = _class_identity(cls, file_sha_cache, roots)
            identities[name] = identity
            if not identity:
                incomplete_classes.append(name)

        return {
            "schema_version": 1,
            "class_count": len(identities),
            "classes": identities,
            "incomplete_classes": incomplete_classes,
            "module_file_count": len(file_sha_cache),
        }
    except Exception as exc:
        return {
            "schema_version": 1,
            "class_count": 0,
            "classes": {},
            "incomplete_classes": [],
            "module_file_count": 0,
            "error": str(exc),
        }


def _parity_result(
    match: bool,
    reason: str,
    *,
    workflow_class_count: int = 0,
    host_proved_count: int = 0,
    snapshot_proved_count: int = 0,
    missing_host: list[str] | tuple[str, ...] = (),
    missing_host_total: int = 0,
    missing_snapshot: list[str] | tuple[str, ...] = (),
    missing_snapshot_total: int = 0,
    identity_mismatch: list[str] | tuple[str, ...] = (),
    identity_mismatch_total: int = 0,
) -> dict:
    return {
        "workflow_class_count": workflow_class_count,
        "host_proved_count": host_proved_count,
        "snapshot_proved_count": snapshot_proved_count,
        "missing_host": list(missing_host)[:_BOUND],
        "missing_host_total": missing_host_total,
        "missing_snapshot": list(missing_snapshot)[:_BOUND],
        "missing_snapshot_total": missing_snapshot_total,
        "identity_mismatch": list(identity_mismatch)[:_BOUND],
        "identity_mismatch_total": identity_mismatch_total,
        "workflow_registry_match": bool(match),
        "reason": reason,
    }


def _proof_stats(plan_proof: Mapping) -> tuple[list[str], int, Mapping, int]:
    """Extract (classes, class_count, identities, host_proved) defensively.

    Accepts frozen mappings (``MappingProxyType``): ``ExecutionPlan``
    freezes ``deployment_identity`` (and therefore the nested
    ``registry_proof``) at construction, so the parity evaluator must
    accept ``collections.abc.Mapping`` inputs, not only plain ``dict``.
    """
    classes = plan_proof.get("classes")
    if not isinstance(classes, (list, tuple)):
        classes = []
    identities = plan_proof.get("identities")
    if not isinstance(identities, Mapping):
        identities = {}
    host_proved = sum(1 for v in identities.values() if v)
    class_count = plan_proof.get("workflow_class_count")
    if not isinstance(class_count, int):
        class_count = len(classes)
    return list(classes), class_count, identities, host_proved


def evaluate_workflow_registry_parity(
    plan_proof: object,
    snapshot_manifest: object,
) -> dict:
    """Compare a plan's workflow registry proof against a snapshot manifest.

    Fail-closed gates (in order): unavailable plan proof, unavailable
    snapshot manifest, incomplete plan proof, empty workflow class set.
    Diagnostic lists are bounded to the first 20 entries; the totals are
    reported separately.

    ``plan_proof`` and ``snapshot_manifest`` may be plain dicts or frozen
    mappings (``MappingProxyType``): ``ExecutionPlan`` freezes its
    ``deployment_identity`` (and hence the nested ``registry_proof``) at
    construction, and the snapshot proof is persisted frozen, so strict
    ``isinstance(..., dict)`` checks would reject valid inputs.
    """
    if not isinstance(plan_proof, Mapping) or not plan_proof:
        return _parity_result(False, "plan_registry_proof_unavailable")
    if not isinstance(snapshot_manifest, Mapping) or not snapshot_manifest:
        return _parity_result(False, "snapshot_registry_manifest_unavailable")

    classes, class_count, identities, host_proved = _proof_stats(plan_proof)

    if not plan_proof.get("complete"):
        return _parity_result(
            False,
            "plan_registry_proof_incomplete",
            workflow_class_count=class_count,
            host_proved_count=host_proved,
        )
    if class_count == 0:
        # Explicit guard: an empty workflow class set must never be accepted.
        return _parity_result(
            False,
            "empty_workflow_class_set",
            workflow_class_count=class_count,
        )

    manifest_classes = snapshot_manifest.get("classes")
    if not isinstance(manifest_classes, Mapping):
        manifest_classes = {}

    missing_host_full = plan_proof.get("missing_host")
    if not isinstance(missing_host_full, list):
        missing_host_full = []

    missing_snapshot: list[str] = []
    identity_mismatch: list[str] = []
    snapshot_proved = 0
    for name in classes:
        if name not in manifest_classes:
            missing_snapshot.append(name)
            continue
        manifest_identity = manifest_classes[name]
        if manifest_identity:
            snapshot_proved += 1
        if identities.get(name, "") != manifest_identity:
            identity_mismatch.append(name)

    if missing_host_full:
        reason = "missing_host_class"
    elif missing_snapshot:
        reason = "missing_snapshot_class"
    elif identity_mismatch:
        reason = "identity_mismatch"
    else:
        reason = ""

    return _parity_result(
        reason == "",
        reason,
        workflow_class_count=class_count,
        host_proved_count=host_proved,
        snapshot_proved_count=snapshot_proved,
        missing_host=missing_host_full,
        missing_host_total=len(missing_host_full),
        missing_snapshot=missing_snapshot,
        missing_snapshot_total=len(missing_snapshot),
        identity_mismatch=identity_mismatch,
        identity_mismatch_total=len(identity_mismatch),
    )


def format_registry_parity_line(result: dict) -> str:
    """One-line registry parity summary (totals only; lists are not printed)."""
    match_flag = 1 if result.get("workflow_registry_match") else 0
    return (
        "[v2.plan_proof.registry] "
        f"workflow_class_count={result.get('workflow_class_count', 0)} "
        f"host_proved_count={result.get('host_proved_count', 0)} "
        f"snapshot_proved_count={result.get('snapshot_proved_count', 0)} "
        f"missing_host={result.get('missing_host_total', 0)} "
        f"missing_snapshot={result.get('missing_snapshot_total', 0)} "
        f"identity_mismatch={result.get('identity_mismatch_total', 0)} "
        f"workflow_registry_match={match_flag} "
        f"reason={result.get('reason', '')}"
    )
