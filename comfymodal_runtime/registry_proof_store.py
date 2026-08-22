"""Disk-persisted registry-proof + validation-proof store (D1 zero-gap).

Purpose
-------
A fresh external benchmark command (``run_v2_single.bat``) previously paid a
17-90 s full ComfyUI node-registry import before reaching ``modal_submission_attempt``.
The prior D1 fix preloaded the registry once inside the harness process, which
fixed *attribution* (the import was moved out of the per-run window) but the
fresh command still *paid* the import.

This store eliminates the payment: plan construction reuses a persisted
``registry_fingerprint`` / ``registry_proof`` / validation payload WITHOUT
importing ``nodes``.  The store is keyed by:

  * the deploy-frozen identity (``.deployed_state.json``:
    ``custom_nodes_generation`` + ``deployment_combined_hash`` +
    ``comfyui_version`` + ``comfyui_commit``) — written by
    ``tools/record_deployment_identity.py`` from the container readback, so the
    persisted proof reflects the DEPLOYED registry (parity-correct even if the
    local tree later drifts — the drift is not deployed); plus
  * the normalized ``comfyui_root``; plus
  * the workflow hash.

The registry fingerprint/proof are deterministic pure functions of registry
content + workflow, so reusing persisted payloads verbatim is sound.

Fail-closed contract
--------------------
Every public read path returns ``None`` / ``False`` on ANY mismatch: missing
or unreadable store file, wrong schema version, empty deploy-frozen identity,
wrong generation, wrong workflow hash.  Writes are best-effort (never raise).
This module is stdlib-only (``json``, ``os``, ``sys``, ``threading``, ``time``,
``hashlib``, ``tempfile``, ``pathlib``) and mirrors the established
``.cache/v2_*.json`` pattern: atomic ``tempfile.mkstemp`` + ``os.replace``,
thread-locked, schema-versioned, bounded entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

REGISTRY_PROOF_STORE_SCHEMA_VERSION = 1
"""Schema version of the store file format.  Bump on incompatible changes."""

_MAX_ENTRIES = 8
"""Maximum store entries before oldest-``created_at_unix`` eviction."""

_REPO_ROOT = Path(__file__).resolve().parents[1]

_STORE_LOCK = threading.Lock()
"""Thread lock for store I/O (parallel harness threads share the file)."""


def store_path() -> Path:
    """Path to the store file.

    Env override ``COMFYMODAL_V2_REGISTRY_PROOF_STORE`` wins; otherwise
    ``<repo root>/.cache/v2_registry_proof_store.json``.
    """
    override = os.environ.get("COMFYMODAL_V2_REGISTRY_PROOF_STORE", "").strip()
    if override:
        return Path(override)
    return _REPO_ROOT / ".cache" / "v2_registry_proof_store.json"


def deployed_state_path() -> Path:
    """Path to the deploy-frozen identity record (``.deployed_state.json``).

    Env override ``COMFYMODAL_V2_DEPLOYED_STATE_JSON`` wins; otherwise
    ``<repo root>/.deployed_state.json``.
    """
    override = os.environ.get("COMFYMODAL_V2_DEPLOYED_STATE_JSON", "").strip()
    if override:
        return Path(override)
    return _REPO_ROOT / ".deployed_state.json"


def current_identity_anchor() -> dict:
    """Read the deploy-frozen identity anchor from ``.deployed_state.json``.

    Returns ``{"generation", "deployment_hash", "dependency_hash",
    "comfyui_version", "comfyui_commit"}`` ONLY when all five are non-empty;
    ANY missing/empty
    value → ``{}`` (fail closed; never a partial anchor).  Missing/unreadable
    file → ``{}``.
    """
    try:
        with open(deployed_state_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    generation = str(raw.get("custom_nodes_generation", "") or "").strip()
    deployment_hash = str(raw.get("deployment_combined_hash", "") or "").strip()
    dependency_hash = str(raw.get("overall_dependency_hash", "") or "").strip()
    comfyui_version = str(raw.get("comfyui_version", "") or "").strip()
    comfyui_commit = str(raw.get("comfyui_commit", "") or "").strip()
    if not (generation and deployment_hash and dependency_hash and comfyui_version and comfyui_commit):
        return {}
    return {
        "generation": generation,
        "deployment_hash": deployment_hash,
        "dependency_hash": dependency_hash,
        "comfyui_version": comfyui_version,
        "comfyui_commit": comfyui_commit,
    }


def _entry_key(anchor: dict, comfyui_root: str, workflow_hash: str) -> str:
    """sha256 hex over the sorted identity parts.

    ``comfyui_root`` is normalized via ``os.path.normpath`` so equivalent
    spellings (``C:\\a\\b`` vs ``C:/a/b``, trailing separators) collide.
    """
    payload = {
        "generation": str(anchor.get("generation", "") or ""),
        "deployment_hash": str(anchor.get("deployment_hash", "") or ""),
        "dependency_hash": str(anchor.get("dependency_hash", "") or ""),
        "comfyui_version": str(anchor.get("comfyui_version", "") or ""),
        "comfyui_commit": str(anchor.get("comfyui_commit", "") or ""),
        "comfyui_root_norm": os.path.normpath(str(comfyui_root or "")),
        "workflow_hash": str(workflow_hash or ""),
    }
    encoded = json.dumps(
        {k: payload[k] for k in sorted(payload)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_store() -> dict:
    """Load + validate the store file.  Fail-closed: returns ``{"entries": {}}``
    on missing/corrupt/wrong-schema files.  Never raises."""
    try:
        path = store_path()
        if not path.is_file():
            return {"schema_version": REGISTRY_PROOF_STORE_SCHEMA_VERSION, "entries": {}}
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"schema_version": REGISTRY_PROOF_STORE_SCHEMA_VERSION, "entries": {}}
        if data.get("schema_version") != REGISTRY_PROOF_STORE_SCHEMA_VERSION:
            return {"schema_version": REGISTRY_PROOF_STORE_SCHEMA_VERSION, "entries": {}}
        entries = data.get("entries")
        if not isinstance(entries, dict):
            entries = {}
        return {"schema_version": REGISTRY_PROOF_STORE_SCHEMA_VERSION, "entries": dict(entries)}
    except Exception:
        return {"schema_version": REGISTRY_PROOF_STORE_SCHEMA_VERSION, "entries": {}}


def _write_store(store: dict) -> None:
    """Atomically write the store file (best-effort, never raises)."""
    try:
        path = store_path()
        parent = path.parent
        if not parent.is_dir():
            parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix="v2_registry_proof_store_",
            suffix=".tmp",
            dir=str(parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(store, fh, indent=2, sort_keys=True, default=str)
            os.replace(tmp, str(path))
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception:
        pass


def _proof_is_structurally_complete(proof: object, workflow_hash: str = "") -> bool:
    """Return whether *proof* is a complete, hash-bound registry proof."""
    if not isinstance(proof, dict) or not proof.get("complete"):
        return False
    if proof.get("schema_version") != 1:
        return False
    classes = proof.get("classes")
    identities = proof.get("identities")
    if (
        not isinstance(classes, list)
        or not classes
        or any(not isinstance(name, str) or not name for name in classes)
        or len(classes) != len(set(classes))
    ):
        return False
    if not isinstance(identities, dict) or set(identities) != set(classes):
        return False
    if any(not isinstance(value, str) or not value for value in identities.values()):
        return False
    if proof.get("missing_host") or proof.get("unresolved_identity"):
        return False
    if proof.get("workflow_class_count") != len(classes):
        return False
    if workflow_hash and str(proof.get("workflow_hash", "") or "") != str(workflow_hash):
        return False
    return True


def lookup(workflow_hash: str, comfyui_root: str = "") -> dict | None:
    """Return the stored entry dict ONLY when it matches the CURRENT anchor +
    normalized comfyui_root + workflow_hash.  ANY mismatch → ``None``.

    Also requires the store file to exist/parse and the schema version to
    match.  Never raises (all failures return ``None``).
    """
    try:
        anchor = current_identity_anchor()
        if not anchor:
            return None
        key = _entry_key(anchor, comfyui_root, workflow_hash)
        store = _load_store()
        entry = store.get("entries", {}).get(key)
        if not isinstance(entry, dict):
            return None
        if entry.get("schema_version") != REGISTRY_PROOF_STORE_SCHEMA_VERSION:
            return None
        # The key is hash-derived, but retain an explicit payload check so a
        # corrupt or hand-edited entry cannot be consumed for a neighboring
        # workflow.
        if str(entry.get("workflow_hash", "") or "") != str(workflow_hash or ""):
            return None
        # Defensive: re-validate the stored anchor matches the current one.
        stored_anchor = entry.get("identity_anchor")
        if not isinstance(stored_anchor, dict) or stored_anchor != anchor:
            return None
        # Validation-only, partial, or unbound proofs are misses.  The caller
        # must rebuild from the live registry instead of promoting them.
        if not _proof_is_structurally_complete(entry.get("registry_proof"), workflow_hash):
            return None
        return dict(entry)
    except Exception:
        return None


def entries() -> dict:
    """Return current-anchor stored entries (best-effort, never raises).

    E29: used by the plan-validation fallback to scan for a stored deployed
    proof matching the current workflow by node-type fingerprint (the per-run
    conditioning nonce changes the full workflow hash but not the node
    structure).  Never raises; returns {} on any error.
    """
    try:
        store = _load_store()
        anchor = current_identity_anchor()
        if not anchor:
            return {}
        out = store.get("entries") or {}
        # Fallback scans must never consider a proof from another deployment,
        # generation, or dependency anchor.
        return {
            k: dict(v) for k, v in out.items()
            if isinstance(v, dict) and v.get("identity_anchor") == anchor
        }
    except Exception:
        return {}


def save(fields: dict) -> None:
    """Persist a store entry (best-effort, never raises).

    ``fields`` may carry ``workflow_hash``, ``comfyui_root``,
    ``registry_fingerprint``, ``registry_proof`` (dict), ``validation``
    (dict | None).  The anchor is derived via ``current_identity_anchor()``;
    no-op when the anchor is empty.  Existing key → dict update; missing →
    append.  Bounded to ``_MAX_ENTRIES`` (drop oldest by ``created_at_unix``,
    keep newest).  Atomic write, thread-locked.
    """
    try:
        anchor = current_identity_anchor()
        if not anchor:
            return
        workflow_hash = str(fields.get("workflow_hash", "") or "")
        if not workflow_hash:
            return
        comfyui_root = str(fields.get("comfyui_root", "") or "")
        key = _entry_key(anchor, comfyui_root, workflow_hash)
        entry: dict[str, Any] = {
            "schema_version": REGISTRY_PROOF_STORE_SCHEMA_VERSION,
            "created_at_unix": time.time(),
            "identity_anchor": anchor,
            "comfyui_root": os.path.normpath(comfyui_root),
            "workflow_hash": workflow_hash,
        }
        # Only carry payload fields that were actually provided so a partial
        # save (e.g. validation-only) merges without clobbering existing
        # fingerprint/proof values.  A supplied proof must be complete and
        # bound to this finalized dispatch hash.
        supplied_proof = fields.get("registry_proof")
        if isinstance(supplied_proof, dict) and supplied_proof:
            supplied_proof = dict(supplied_proof)
            proof_hash = str(supplied_proof.get("workflow_hash", "") or "")
            if proof_hash and proof_hash != workflow_hash:
                return
            # Bind complete proofs produced by older builders that omitted the
            # planner's finalized hash.  Incomplete proofs are never repaired.
            supplied_proof.setdefault("workflow_hash", workflow_hash)
            if not _proof_is_structurally_complete(supplied_proof, workflow_hash):
                return
            entry["registry_proof"] = supplied_proof
        if str(fields.get("registry_fingerprint", "") or ""):
            entry["registry_fingerprint"] = str(fields["registry_fingerprint"])
        if isinstance(fields.get("validation"), dict):
            entry["validation"] = dict(fields["validation"])
        with _STORE_LOCK:
            store = _load_store()
            entries = store.get("entries", {})
            existing = entries.get(key)
            if isinstance(existing, dict):
                # Validation-only updates are permitted only as an extension
                # of an already complete proof for this exact anchor/hash.
                if "registry_proof" not in entry and not _proof_is_structurally_complete(
                    existing.get("registry_proof"), workflow_hash
                ):
                    return
                # Merge: keep the earlier creation time, refresh payload fields.
                merged = dict(existing)
                merged.update(entry)
                merged["created_at_unix"] = existing.get("created_at_unix", entry["created_at_unix"])
                entries[key] = merged
            else:
                # Never create a validation-only entry.
                if "registry_proof" not in entry:
                    return
                entries[key] = entry
            if len(entries) > _MAX_ENTRIES:
                # Drop oldest created_at_unix; keep newest.
                by_created = sorted(
                    entries.items(), key=lambda kv: float(kv[1].get("created_at_unix", 0.0) or 0.0)
                )
                for _drop_key, _ in by_created[: len(entries) - _MAX_ENTRIES]:
                    entries.pop(_drop_key, None)
            _write_store({"schema_version": REGISTRY_PROOF_STORE_SCHEMA_VERSION, "entries": entries})
    except Exception:
        pass


def has_generation_entry() -> bool:
    """True when any stored entry's identity_anchor == current anchor.

    Schema-validated (store file parses, version matches).  Fail-closed False.
    """
    try:
        anchor = current_identity_anchor()
        if not anchor:
            return False
        store = _load_store()
        for entry in store.get("entries", {}).values():
            if not isinstance(entry, dict):
                continue
            entry_hash = str(entry.get("workflow_hash", "") or "")
            if (
                entry.get("identity_anchor") == anchor
                and entry.get("schema_version") == REGISTRY_PROOF_STORE_SCHEMA_VERSION
                and entry_hash
                and _proof_is_structurally_complete(
                    entry.get("registry_proof"), entry_hash
                )
            ):
                return True
    except Exception:
        return False
    return False
