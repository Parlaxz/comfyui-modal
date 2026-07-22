"""Pure identity/build/load/check/diagnostic logic for the immutable
dependency manifest, extracted for focused testability.

This module provides the core manifest operations without depending on
ComfyUI or Modal runtime.  The functions here are used by ``comfyapp.py``
to build, persist, load, check, and emit diagnostics for the immutable
dependency manifest.

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
