"""Construction-time generation marker for the runtime-state/config Volume.

Batch B — guard and skip redundant restore-time ``reload_runtime_state``
Volume reloads.  Revision 2 (content-based): the marker carries a manifest of
the correctness-relevant construction files so the restore-time skip is proven
by CONTENT (exact generation + exact local file manifest), not by write-order
visibility alone.

Mechanism
---------
At construction (snapshot build) the runtime-state Volume is written by
several actors (prescan record, optional GPU-capacity freeze).  Historical
evidence shows a restored mount can LAG behind construction-time writes (the
frozen-capacity file was invisible until a ``Volume.reload()``).  An
unconditional skip is therefore unsafe.

At the END of construction (after every correctness-relevant runtime-state
write, before snapshot capture) this module's marker is written atomically:

.. code-block:: json

   {
     "schema_version": 2,
     "generation": "<uuid hex>",
     "files": {
       "prescan_custom_nodes.json": {"present": true, "sha256": "..."},
       "gpu_capacity_frozen.json": {"present": false}
     }
   }

At restore the marker is read from the mounted volume using LOCAL filesystem
access only.  An exact skip requires BOTH:

A. marker ``generation`` == snapshot baseline generation, AND
B. every correctness-relevant file on the restored mount matches the
   captured manifest: expected-present files exist with matching sha256;
   expected-absent files remain absent.

Any missing/unexpected/hash-mismatched/unreadable/invalid state performs the
existing ``Volume.reload()`` (fail closed).  The generation token is retained
(not replaced by hashes) to reject stale-but-coincidentally-similar states
and to keep diagnostics simple.

No-RPC contract: this module performs ZERO Modal/network operations.  All
helpers are ``os``/``json``/``hashlib`` local filesystem access on the mounted
volume.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

RUNTIME_STATE_GENERATION_FILENAME: str = "runtime_config_generation.json"
"""Marker filename on the runtime-state Volume root (``{RUNTIME_STATE_PATH}/``)."""

RUNTIME_STATE_GENERATION_SCHEMA_VERSION: int = 2
"""Marker schema version.  Schema v1 (generation only, no content manifest)
is deliberately NOT accepted for a skip — the restore decision treats any
non-v2 marker as invalid and reloads (fail closed)."""

# Correctness-relevant construction files on the runtime-state Volume,
# relative to the volume root.  From the Batch B1 construction-write audit:
#   - prescan_custom_nodes.json — written at construction on the /mnt mount;
#     read at restore by the custom-node fast path before any rewrite.
#   - gpu_capacity_frozen.json — the mount-lag evidence file; written at
#     construction when the frozen-VRAM arm is enabled; absence at
#     construction is the correct state when the arm is off.
# dependency_manifest/immutable_manifest.json is deliberately NOT included:
# in the V2 image it is written to the container-local
# /root/comfymodal_runtime_state path (snapshot-carried), NOT the /mnt
# runtime-state mount, so it cannot participate in a mount-content proof.
DEFAULT_RUNTIME_STATE_MANIFEST_FILES: tuple[str, ...] = (
    "prescan_custom_nodes.json",
    "gpu_capacity_frozen.json",
)

# Files that must be PRESENT at construction (fail closed when absent).
DEFAULT_RUNTIME_STATE_MANIFEST_REQUIRED: tuple[str, ...] = (
    "prescan_custom_nodes.json",
)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_runtime_state_manifest(
    root_dir: str,
    relative_files: tuple[str, ...] = DEFAULT_RUNTIME_STATE_MANIFEST_FILES,
    *,
    required: tuple[str, ...] = DEFAULT_RUNTIME_STATE_MANIFEST_REQUIRED,
) -> dict[str, dict]:
    """Build the content manifest of the correctness-relevant construction
    files via LOCAL filesystem reads (no remote RPC).

    For every relative file:
      - present and readable  -> ``{"present": true, "sha256": "<hex>"}``
      - absent and not required -> ``{"present": false}`` (optional file whose
        absence is the correct construction state)
      - absent and required  -> raises (fail closed: no usable baseline)
      - present but unreadable -> raises (fail closed)

    Volatile timestamps are never included in the comparison data.
    """
    root = str(root_dir or "")
    if not root:
        raise ValueError("runtime-state generation root_dir is empty")
    required_set = set(required or ())
    manifest: dict[str, dict] = {}
    for rel in relative_files or ():
        rel = str(rel).lstrip("/\\")
        if not rel:
            continue
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            manifest[rel] = {"present": True, "sha256": _sha256_file(path)}
        elif rel in required_set:
            raise OSError(f"required runtime-state file missing: {rel}")
        else:
            manifest[rel] = {"present": False}
    return manifest


def write_runtime_state_generation_marker(
    root_dir: str,
    *,
    generation: str | None = None,
    reason: str = "construction",
    files_manifest: dict[str, dict] | None = None,
) -> str:
    """Atomically write the schema-v2 generation marker.

    Uses the same temp-file + ``fsync`` + ``os.replace`` local-write pattern
    as the other construction-time runtime-state writers (prescan record,
    GPU-capacity freeze).  ``root_dir`` is the volume mount root
    (``{RUNTIME_STATE_PATH}``); the marker lands at
    ``{root_dir}/runtime_config_generation.json``.

    ``files_manifest`` is the content manifest (see
    :func:`build_runtime_state_manifest`) captured for this construction.
    Stored verbatim in the payload — never re-hashed here.

    Returns the generation string (uuid hex) written.  Raises on failure —
    callers (``RuntimeBootstrap.finalize_runtime_state_generation``) capture
    the exception and fail closed to an empty baseline.
    """
    generation = str(generation or "") or uuid.uuid4().hex
    payload = {
        "schema_version": RUNTIME_STATE_GENERATION_SCHEMA_VERSION,
        "generation": generation,
        "files": dict(files_manifest or {}),
        "updated_at_unix": time.time(),
        "reason": str(reason or "construction"),
    }
    root = str(root_dir or "")
    if not root:
        raise ValueError("runtime-state generation marker root_dir is empty")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, RUNTIME_STATE_GENERATION_FILENAME)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, separators=(",", ":"))
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, path)
    return generation


def read_runtime_state_generation_marker(root_dir: str) -> dict | None:
    """Read the marker via LOCAL filesystem access only (no remote RPC).

    Fail-closed reader: returns ``None`` for a missing file, unreadable file,
    parse error, or non-dict/empty-generation payload.  Returns the parsed
    dict (``schema_version``, ``generation``, ``files``) for any well-formed
    marker — the caller decides schema/version acceptance so legacy v1
    markers (generation only) fail closed to a reload with an accurate reason.
    """
    root = str(root_dir or "")
    if not root:
        return None
    path = os.path.join(root, RUNTIME_STATE_GENERATION_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    generation = data.get("generation")
    if not isinstance(generation, str) or not generation:
        return None
    return {
        "schema_version": int(data.get("schema_version", 0)),
        "generation": generation,
        "files": data.get("files"),
    }


def verify_runtime_state_manifest(
    root_dir: str,
    expected_manifest: dict[str, dict],
) -> tuple[bool, str]:
    """Verify the restored mount's correctness-relevant files against the
    construction manifest via LOCAL filesystem access only.

    For every manifest entry:
      - expected-present: file must exist AND sha256 must match
      - expected-absent:  file must remain absent

    Returns ``(True, "exact_match")`` or ``(False, reason)`` with reason in:
    ``manifest_file_missing``, ``manifest_hash_mismatch``,
    ``manifest_file_unexpected``, ``manifest_read_error:<exc-type>``.
    """
    root = str(root_dir or "")
    if not root:
        return False, "manifest_read_error:ValueError"
    for rel, entry in (expected_manifest or {}).items():
        rel = str(rel).lstrip("/\\")
        if not rel:
            continue
        path = os.path.join(root, rel)
        expected_present = bool((entry or {}).get("present", False))
        if expected_present:
            if not os.path.isfile(path):
                return False, "manifest_file_missing"
            try:
                actual = _sha256_file(path)
            except OSError as exc:
                return False, f"manifest_read_error:{type(exc).__name__}"
            expected_sha = (entry or {}).get("sha256", "")
            if not expected_sha or actual != expected_sha:
                return False, "manifest_hash_mismatch"
        else:
            if os.path.isfile(path) or os.path.lexists(path):
                return False, "manifest_file_unexpected"
    return True, "exact_match"
