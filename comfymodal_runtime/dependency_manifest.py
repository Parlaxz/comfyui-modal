"""Pure identity/build/load/check/diagnostic logic for the immutable
dependency manifest, extracted for focused testability.

This module provides the core manifest operations without depending on
ComfyUI or Modal runtime.  The functions here are used by ``comfyapp.py``
to build, persist, load, check, and emit diagnostics for the immutable
dependency manifest.

Lane B extensions:
  - Snapshot-memory validation certificate with Volume fallback
  - Immutable workflow artifact identity computation (no live/request/model/
    output objects ever captured)
  - Snapshot identity service for pre-scan generation reuse

All existing public/private helper names in ``comfyapp.py`` remain
unchanged and continue to be the patch targets for existing tests.
"""

import hashlib
import inspect
import json
import os
import time
from typing import Any

# ── Schema ──────────────────────────────────────────────────────────────

DEPENDENCY_MANIFEST_SCHEMA_VERSION = 1
"""Current schema version for the persisted immutable dependency manifest."""


# ── Identity ────────────────────────────────────────────────────────────


def build_identity(
    combined_hash: str,
    custom_node_fingerprint: dict | None,
    custom_node_generation: str,
    repair_mode: str,
    schema_version: int = DEPENDENCY_MANIFEST_SCHEMA_VERSION,
) -> str:
    """Build a deterministic identity string.

    Includes manifest schema version, deployment combined hash,
    custom-node source fingerprint overall hash, custom-node generation
    token, and repair mode.

    Returns a 64-character hex SHA-256 digest.
    """
    h = hashlib.sha256()
    h.update(f"manifest_schema={schema_version}\n".encode())
    h.update(f"combined_hash={combined_hash}\n".encode())
    cn_hash = ""
    if custom_node_fingerprint and isinstance(custom_node_fingerprint, dict):
        cn_hash = custom_node_fingerprint.get("overall_dependency_hash", "")
    h.update(f"custom_node_fingerprint={cn_hash}\n".encode())
    h.update(f"custom_node_generation={custom_node_generation}\n".encode())
    h.update(f"repair_mode={repair_mode}\n".encode())
    return h.hexdigest()


# ── Build ───────────────────────────────────────────────────────────────


def build_manifest_dict(
    combined_hash: str,
    custom_node_fingerprint: dict | None,
    custom_node_generation: str,
    repair_mode: str,
    *,
    source: str = "snapshot_manifest",
) -> dict:
    """Build an immutable dependency manifest dict (without persisting).

    Returns the manifest dict with ``identity`` keyed by
    ``build_identity(...)``.
    """
    identity = build_identity(
        combined_hash=combined_hash,
        custom_node_fingerprint=custom_node_fingerprint,
        custom_node_generation=custom_node_generation,
        repair_mode=repair_mode,
    )
    return {
        "schema_version": DEPENDENCY_MANIFEST_SCHEMA_VERSION,
        "identity": identity,
        "created_at_unix": time.time(),
        "combined_hash": combined_hash,
        "custom_node_fingerprint": dict(custom_node_fingerprint) if custom_node_fingerprint else {},
        "custom_node_generation": custom_node_generation,
        "repair_mode": repair_mode,
        "source": source,
    }


# ── Persist ─────────────────────────────────────────────────────────────


def persist_manifest(
    manifest: dict,
    manifest_dir: str,
    manifest_filename: str,
) -> bool:
    """Atomically persist the manifest dict to disk.

    Uses atomic ``os.replace`` (rename) for crash safety.
    Returns ``True`` on success, ``False`` on failure (logs error).
    """
    try:
        os.makedirs(manifest_dir, exist_ok=True)
        tmp = os.path.join(
            manifest_dir,
            f".{manifest_filename}.tmp.{os.getpid()}",
        )
        final = os.path.join(manifest_dir, manifest_filename)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, final)
        return True
    except (OSError, IOError) as exc:
        print(f"[dep_manifest] persist failed: {exc}", flush=True)
        return False


# ── Commit ──────────────────────────────────────────────────────────────


async def commit_volume_async(volume: Any) -> bool:
    """Async commit using Modal's awaited ``volume.commit.aio()``.

    When ``.aio()`` is itself awaitable (e.g. AsyncMock), awaits it
    directly.  When ``.aio()`` is a callable that returns an awaitable
    (real Modal 1.4.x), calls it then awaits the result.

    Falls back to ``asyncio.to_thread(volume.commit)`` when neither path
    yields an awaitable (e.g. plain MagicMock, legacy Modal).  Exactly one
    underlying commit call on real Modal; never calls a blocking commit
    directly on the event loop.

    Returns ``True`` on success.
    """
    import asyncio

    if volume is None:
        return False
    try:
        # Prefer Modal 1.4.x async interface
        aio_fn = getattr(volume.commit, "aio", None)
        if aio_fn is not None:
            # aio_fn itself may be awaitable (AsyncMock, coroutine)
            if inspect.isawaitable(aio_fn):
                await aio_fn
                return True
            # aio_fn is a callable; invoke it and check the result
            result = aio_fn()
            if inspect.isawaitable(result):
                await result
                return True
        # Fallback: run synchronous commit in thread to avoid blocking
        # the event loop directly.
        await asyncio.to_thread(volume.commit)
        return True
    except Exception as exc:
        print(f"[dep_manifest] commit_async failed: {exc}", flush=True)
        return False


def commit_volume_sync(volume: Any) -> bool:
    """Deterministic synchronous bridge for committing a Modal Volume.

    Invokes ``commit_volume_async`` to completion via ``asyncio.run()``.
    Rejects with a clear error when called from an already-running event
    loop (use ``commit_volume_async`` directly from async contexts).
    Never spawns daemon/background work.  Exactly one one-shot bridge
    with no retry after the coroutine starts.
    Returns ``True`` on success.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        raise RuntimeError(
            "commit_volume_sync is a synchronous bridge and must not be "
            "called from an async context; use commit_volume_async instead."
        )
    return asyncio.run(commit_volume_async(volume))


# ── Load ────────────────────────────────────────────────────────────────


def load_manifest(
    manifest_dir: str,
    manifest_filename: str,
    schema_version: int = DEPENDENCY_MANIFEST_SCHEMA_VERSION,
) -> dict | None:
    """Load and validate the persisted dependency manifest.

    Returns the manifest dict on success, or ``None`` if missing,
    corrupt, schema-mismatched, or missing identity.
    Never raises.
    """
    path = os.path.join(manifest_dir, manifest_filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if data.get("schema_version") != schema_version:
            print(
                f"[dep_manifest] schema_version mismatch: {data.get('schema_version')}",
                flush=True,
            )
            return None
        if not data.get("identity"):
            print("[dep_manifest] missing identity", flush=True)
            return None
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[dep_manifest] corrupt: {exc}", flush=True)
        return None


# ── Check identity ──────────────────────────────────────────────────────


def check_identity(
    manifest: dict | None,
    combined_hash: str,
    custom_node_fingerprint: dict | None,
    custom_node_generation: str,
    repair_mode: str,
) -> dict:
    """Cheap identity comparison between persisted and expected values.

    Returns a dict with:
      ``identity_match`` (bool), ``manifest_load_ms`` (0 — caller provides),
      ``cheap_check_ms`` (float), ``computed_identity`` (str),
      ``stored_identity`` (str), ``reason`` (str).

    When ``identity_match`` is ``False``, the caller should run full
    validation and rebuild the manifest.
    """
    t0 = time.time()
    if manifest is None:
        return {
            "identity_match": False,
            "manifest_load_ms": 0.0,
            "cheap_check_ms": round((time.time() - t0) * 1000, 1),
            "computed_identity": "",
            "stored_identity": "",
            "reason": "manifest_missing",
        }
    chk_t0 = time.time()
    expected = build_identity(
        combined_hash=combined_hash,
        custom_node_fingerprint=custom_node_fingerprint,
        custom_node_generation=custom_node_generation,
        repair_mode=repair_mode,
    )
    stored = manifest.get("identity", "")
    match = bool(stored and expected and stored == expected)
    reason = ""
    if not match:
        if not stored:
            reason = "stored_identity_empty"
        elif not expected:
            reason = "computed_identity_empty"
        else:
            reason = "identity_mismatch"
    return {
        "identity_match": match,
        "manifest_load_ms": 0.0,
        "cheap_check_ms": round((time.time() - chk_t0) * 1000, 1),
        "computed_identity": expected,
        "stored_identity": stored,
        "reason": reason,
    }


# ── Emit diagnostic ─────────────────────────────────────────────────────


def emit_validation_diagnostic(
    *,
    source: str = "",
    identity_match: bool = False,
    manifest_load_ms: float = 0.0,
    cheap_check_ms: float = 0.0,
    fingerprint_ms: float = 0.0,
    full_validation_ms: float = 0.0,
    total_ms: float = 0.0,
    refresh_performed: bool = False,
    reason: str = "",
) -> None:
    """Emit a single ``[v2.dependency_validation]`` diagnostic line.

    Fields:
      source — ``snapshot_manifest`` | ``persistent_manifest`` | ``request_rebuild``
      identity_match — ``1`` when persisted manifest identity matches expected
      manifest_load_ms — time to load the persisted manifest from volume
      cheap_check_ms — time for the cheap identity comparison
      fingerprint_ms — time for dependency fingerprint computation
      full_validation_ms — time for full dependency validation
      total_ms — total elapsed (load + check + fingerprint + validation)
      refresh_performed — ``1`` if a write/replacement was performed
      reason — short string explaining the outcome
    """
    print(
        f"[v2.dependency_validation] "
        f"source={source} "
        f"identity_match={int(identity_match)} "
        f"manifest_load_ms={manifest_load_ms} "
        f"cheap_check_ms={cheap_check_ms} "
        f"fingerprint_ms={fingerprint_ms} "
        f"full_validation_ms={full_validation_ms} "
        f"total_ms={total_ms} "
        f"refresh_performed={int(refresh_performed)} "
        f"reason={reason}",
        flush=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# Lane B — Snapshot-memory validation certificate (Volume-compatible)
# ═══════════════════════════════════════════════════════════════════════

SNAPSHOT_CERT_PAYLOAD_SCHEMA_VERSION = 1
SNAPSHOT_CERT_FILENAME_PREFIX = "snapshot_cert_"


def build_snapshot_cert_payload(
    *,
    runtime_generation: str,
    custom_node_generation: str,
    sage_mode: str,
    sage_reason: str,
    unet_identity: str = "",
    clip_identity: str = "",
    clip_type: str = "",
) -> dict[str, Any]:
    """Build a serializable, verifiable snapshot-memory validation
    certificate payload.

    This is the **data-plane** representation (pure dict, no Volume
    reference).  The caller is responsible for persisting it via
    ``persist_snapshot_cert_to_volume`` or an equivalent Volume write.

    Fields capture only snapshot-safe identity values — never live
    objects, model references, request state, or mutable state.

    Returns a dict with an embedded ``cert_identity`` (deterministic
    SHA-256 of semantic content, excluding ``created_at``).
    """
    identity_components: dict[str, str] = {
        "runtime_generation": str(runtime_generation),
        "custom_node_generation": str(custom_node_generation),
        "sage_mode": str(sage_mode),
        "sage_reason": str(sage_reason),
        "unet_identity": str(unet_identity),
        "clip_identity": str(clip_identity),
        "clip_type": str(clip_type),
    }
    h = hashlib.sha256()
    h.update(f"schema={SNAPSHOT_CERT_PAYLOAD_SCHEMA_VERSION}\n".encode())
    for key in sorted(identity_components):
        h.update(f"{key}={identity_components[key]}\n".encode())
    cert_identity = h.hexdigest()

    return {
        "schema_version": SNAPSHOT_CERT_PAYLOAD_SCHEMA_VERSION,
        "cert_identity": cert_identity,
        "created_at": time.time(),
        "identity_components": identity_components,
    }


def validate_snapshot_cert_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate a previously built snapshot cert payload.

    Returns ``{"valid": True, "cert_identity": ..., "reason": ""}`` on
    success or ``{"valid": False, "cert_identity": "", "reason": ...}``
    on failure.  Never raises.
    """
    result: dict[str, Any] = {
        "valid": False, "cert_identity": "", "reason": "",
    }
    if not isinstance(payload, dict):
        result["reason"] = "not_a_dict"
        return result
    try:
        sv = payload.get("schema_version")
        if sv != SNAPSHOT_CERT_PAYLOAD_SCHEMA_VERSION:
            result["reason"] = f"schema_version_mismatch:got={sv}"
            return result
        stored_identity = str(payload.get("cert_identity", ""))
        if not stored_identity:
            result["reason"] = "missing_cert_identity"
            return result

        # Recompute identity from components
        components = payload.get("identity_components", {})
        if not isinstance(components, dict):
            result["reason"] = "invalid_identity_components"
            return result

        h = hashlib.sha256()
        h.update(f"schema={SNAPSHOT_CERT_PAYLOAD_SCHEMA_VERSION}\n".encode())
        for key in sorted(components):
            h.update(f"{key}={str(components[key])}\n".encode())
        computed = h.hexdigest()

        if stored_identity != computed:
            result["reason"] = (
                f"identity_mismatch:stored={stored_identity[:16]}"
                f"!=computed={computed[:16]}"
            )
            return result

        result["valid"] = True
        result["cert_identity"] = stored_identity
        result["reason"] = ""
        return result
    except Exception as exc:
        result["reason"] = f"validation_error:{exc}"
        return result


def _snapshot_cert_filename(cert_identity: str) -> str:
    """Return the on-volume filename for a snapshot cert identity."""
    return f"{SNAPSHOT_CERT_FILENAME_PREFIX}{cert_identity}.json"


def persist_snapshot_cert_to_volume(
    volume: Any,
    *,
    payload: dict[str, Any],
    volume_dir: str = "",
) -> bool:
    """Persist a snapshot cert payload to a Modal-compatible Volume.

    *volume* is expected to expose ``write_bytes(path, data)`` and
    ``commit()``.  *volume_dir* is an optional subdirectory prefix
    within the volume.

    Never raises.  Returns ``True`` on success.
    """
    try:
        cert_identity = str(payload.get("cert_identity", ""))
        if not cert_identity:
            return False

        filename = _snapshot_cert_filename(cert_identity)
        if volume_dir:
            filepath = os.path.join(volume_dir, filename)
        else:
            filepath = filename

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        volume.write_bytes(filepath, encoded)
        # Commit via safe helper
        try:
            commit_volume_sync(volume)
        except Exception:
            pass
        return True
    except Exception as exc:
        print(f"[snapshot_cert] persist error: {exc}", flush=True)
        return False


def read_snapshot_cert_from_volume(
    volume: Any,
    *,
    cert_identity: str,
    volume_dir: str = "",
) -> dict[str, Any] | None:
    """Read and validate a snapshot cert from a Modal-compatible Volume.

    Returns the validated payload dict on hit, or ``None`` on
    miss/mismatch/error.  Never raises.
    """
    try:
        filename = _snapshot_cert_filename(cert_identity)
        if volume_dir:
            filepath = os.path.join(volume_dir, filename)
        else:
            filepath = filename

        if not volume.exists(filepath):
            return None

        raw = volume.read_bytes(filepath)
        if not raw:
            return None

        import json as _json
        payload = _json.loads(raw.decode("utf-8"))
        validation = validate_snapshot_cert_payload(payload)
        if not validation.get("valid"):
            return None

        return payload
    except Exception as exc:
        print(f"[snapshot_cert] read error: {exc}", flush=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
# Lane B — Immutable workflow artifact identity
# ═══════════════════════════════════════════════════════════════════════
#
# Returns a deterministic identity for a workflow artifact WITHOUT
# capturing prompt text, model objects, node outputs, or any live/
# request-scoped state.  Only structural topology and class types
# participate.

IMMUTABLE_ARTIFACT_SCHEMA_VERSION = 1


def build_immutable_artifact_identity(
    *,
    compiled_workflow_hash: str,
    source_workflow_hash: str,
    production_plan_hash: str,
    output_node_ids: list[str] | None = None,
    topology_hash: str = "",
) -> dict[str, Any]:
    """Compute a deterministic identity for an immutable workflow
    artifact.

    Only structural metadata participates — never live objects,
    prompt text, model outputs, or runtime state.  This identity
    can be used as a certificate key or cache tag that survives
    snapshot boundaries.

    Returns:
      * artifact_identity — SHA-256 hex string
      * components — dict of all fields that were hashed
      * schema_version — current schema version
    """
    components: dict[str, str] = {
        "schema_version": str(IMMUTABLE_ARTIFACT_SCHEMA_VERSION),
        "compiled_workflow_hash": str(compiled_workflow_hash),
        "source_workflow_hash": str(source_workflow_hash),
        "production_plan_hash": str(production_plan_hash),
        "topology_hash": str(topology_hash),
    }
    if output_node_ids:
        components["output_node_ids"] = ",".join(sorted(str(i) for i in output_node_ids))

    h = hashlib.sha256()
    for key in sorted(components):
        h.update(f"{key}={components[key]}\n".encode())

    return {
        "artifact_identity": h.hexdigest(),
        "components": components,
        "schema_version": IMMUTABLE_ARTIFACT_SCHEMA_VERSION,
    }


# ═══════════════════════════════════════════════════════════════════════
# Lane B — Snapshot identity service (pre-scan generation reuse)
# ═══════════════════════════════════════════════════════════════════════
#
# Lightweight service that bridges the pre-scan generation identity
# (captured during startup) to the restore phase without coupling to
# the BootstrapState dataclass.

SNAPSHOT_IDENTITY_SCHEMA_VERSION = 1


def build_snapshot_identity(
    *,
    runtime_generation: str,
    custom_node_generation: str,
    combined_hash: str = "",
) -> dict[str, Any]:
    """Build a snapshot identity that can be used to detect changes
    between startup (pre-scan) and restore.

    Returns a dict with:
      * snapshot_identity — SHA-256 hex string
      * runtime_generation — from bootstrap state
      * custom_node_generation — from bootstrap state
      * combined_hash — deployment combined hash
      * schema_version — current version
    """
    h = hashlib.sha256()
    h.update(f"schema={SNAPSHOT_IDENTITY_SCHEMA_VERSION}\n".encode())
    h.update(f"runtime_gen={str(runtime_generation)}\n".encode())
    h.update(f"cn_gen={str(custom_node_generation)}\n".encode())
    h.update(f"combined_hash={str(combined_hash)}\n".encode())

    return {
        "snapshot_identity": h.hexdigest(),
        "schema_version": SNAPSHOT_IDENTITY_SCHEMA_VERSION,
        "runtime_generation": str(runtime_generation),
        "custom_node_generation": str(custom_node_generation),
        "combined_hash": str(combined_hash),
        "created_at": time.time(),
    }


def check_snapshot_identity_match(
    identity_a: dict[str, Any] | None,
    identity_b: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare two snapshot identity dicts.

    Returns a dict with:
      * match — bool
      * reason — str (empty on match, describes difference on mismatch)
      * identity_a_hash, identity_b_hash — the hex digests
    """
    result: dict[str, Any] = {
        "match": False,
        "reason": "",
        "identity_a_hash": "",
        "identity_b_hash": "",
    }
    if not isinstance(identity_a, dict):
        result["reason"] = "identity_a_missing"
        return result
    if not isinstance(identity_b, dict):
        result["reason"] = "identity_b_missing"
        return result
    hash_a = str(identity_a.get("snapshot_identity", ""))
    hash_b = str(identity_b.get("snapshot_identity", ""))
    result["identity_a_hash"] = hash_a
    result["identity_b_hash"] = hash_b
    if hash_a and hash_b and hash_a == hash_b:
        result["match"] = True
    else:
        result["reason"] = "identity_mismatch"
    return result
