"""Frozen import-time source identity for snapshot-surviving modules.

A Modal container restored from a memory snapshot keeps the *code objects* that
were imported before the snapshot was captured, while the source tree mounted
into the restored container can be newer.  Hashing ``module.__file__`` at
request time therefore reports the mounted file's identity even when the
interpreter is executing a different, snapshotted code object -- which is
exactly the case this module exists to detect.

The fix is to freeze the identity when the module is *imported*: that read
happens while the image and the mounted tree still agree, and the resulting
string then lives in module memory for the life of the container.  Comparing
that frozen value against the mounted bytes distinguishes the two states:

    healthy          expected == imported == mounted
    stale snapshot   expected == mounted, imported != mounted

Only a module that records its own identity at import can make that
distinction; nothing computed during a request can.
"""

from __future__ import annotations

import hashlib
import sys
from typing import Any

# Frozen identities, keyed by dotted module name.  Populated at import time by
# ``freeze_imported_sha``; read (never recomputed) during requests.
IMPORTED_SOURCE_SHA256: dict[str, str] = {}

# Production-critical modules whose stale execution could invalidate a Golden
# measurement.  The source probe's required-module set is the canonical list of
# first-party modules that must byte-match the deployed image; these are the
# ones that can additionally survive in snapshot memory and are therefore
# required to prove *executing* identity, not just mounted identity.
CRITICAL_MODULES: tuple[str, ...] = (
    "comfymodal_runtime.modal_app",
    "comfymodal_runtime.golden_parallel",
    "comfymodal_runtime.golden_serial",
    "comfymodal_runtime.golden_model_transport",
    "comfymodal_runtime.golden_io_process_v2",
    "comfymodal_runtime.golden_source_threads",
)

_DIGEST_LIMIT = 1 << 20


def sha256_file(path: str) -> str:
    """SHA-256 of the exact bytes currently at *path*."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_DIGEST_LIMIT), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_imported_sha(module_name: str, module_file: str | None) -> str:
    """Record and return the importing module's source identity.

    Must be called from the module's own top level so the value is captured
    while the image and the mounted tree still agree.  Calling it again for the
    same module is a no-op, so a module that is genuinely re-imported into a
    fresh interpreter records the identity it was actually compiled from.
    """
    if not module_file:
        return ""
    try:
        digest = sha256_file(module_file)
    except Exception:  # noqa: BLE001 - identity aid must never break an import
        return ""
    IMPORTED_SOURCE_SHA256[module_name] = digest
    return digest


def imported_sha(module_name: str) -> str:
    """Frozen import-time identity for *module_name* ('' when not recorded)."""
    return IMPORTED_SOURCE_SHA256.get(module_name, "")


def mounted_sha(module_name: str) -> str:
    """Identity of the bytes currently mounted for *module_name*."""
    module = sys.modules.get(module_name)
    path = getattr(module, "__file__", None) if module is not None else None
    if not path:
        return ""
    try:
        return sha256_file(path)
    except Exception:  # noqa: BLE001
        return ""


def runtime_identity(module_names: tuple[str, ...] = CRITICAL_MODULES) -> dict[str, Any]:
    """Per-module executing vs mounted identity for one request.

    ``stale`` is true when a module's frozen import-time identity disagrees with
    the bytes now mounted at its path: the interpreter is provably running a
    code object that no longer matches the deployed source tree.
    """
    modules: dict[str, dict[str, str]] = {}
    stale: list[str] = []
    missing: list[str] = []
    for name in module_names:
        imported = imported_sha(name)
        mounted = mounted_sha(name)
        modules[name] = {"imported_source_sha256": imported,
                         "mounted_source_sha256": mounted}
        if not imported:
            missing.append(name)
        elif imported != mounted:
            stale.append(name)
    return {
        "modules": modules,
        "stale_modules": stale,
        "unrecorded_modules": missing,
        "all_match": not stale and not missing,
    }


def compare_to_expected(identity: dict[str, Any],
                         expected: dict[str, str]) -> dict[str, Any]:
    """Fail-closed comparison of executing identity against expected shas.

    *expected* maps dotted module name to the sha the caller expects the
    executing code to have been compiled from.  Absence, mismatch and stale
    snapshot execution are all reported as failures; nothing is downgraded.
    """
    modules = identity.get("modules") or {}
    mismatched: list[str] = []
    absent: list[str] = []
    for name, want in sorted(expected.items()):
        got = (modules.get(name) or {}).get("imported_source_sha256") or ""
        if not got:
            absent.append(name)
        elif want and got != want:
            mismatched.append(name)
    ok = (
        not mismatched
        and not absent
        and not identity.get("stale_modules")
        and not identity.get("unrecorded_modules")
    )
    return {
        "ok": ok,
        "mismatched_modules": mismatched,
        "absent_modules": absent,
        "stale_modules": list(identity.get("stale_modules") or []),
        "unrecorded_modules": list(identity.get("unrecorded_modules") or []),
    }