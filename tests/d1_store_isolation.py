"""Test-side isolation for the shared D1 registry-proof store.

The real store at ``<repo>/.cache/v2_registry_proof_store.json`` is shared
mutable state bounded to ``_MAX_ENTRIES = 8``.  Any test that calls the REAL
``canonical_execution.build_execution_plan`` under a deploy-frozen identity
(the repo's real ``.deployed_state.json`` makes ``deployment_identity_frozen``
True) writes the real store via ``_proof_store_save`` — and once 8 entries are
exceeded, the oldest is EVICTED.  The canonical prime entry (workflow_hash
2e43d4c0…) was lost this way.  This module provides the module-scoped
redirect used by every polluting test file (never write the real store).

``isolate_module_store()`` redirects ``COMFYMODAL_V2_REGISTRY_PROOF_STORE`` to
a temp COPY of the real store for the duration of ONE test module (called from
the module's ``setUpModule``); ``restore_module_store()`` (``tearDownModule``)
restores the environment and cleans up.  Reads keep seeing the real store's
entries (the copy); writes go to the temp copy only, so the real store is
byte-identical after any test run.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_STORE = _REPO_ROOT / ".cache" / "v2_registry_proof_store.json"
_STORE_ENV = "COMFYMODAL_V2_REGISTRY_PROOF_STORE"

# Module-scoped state (setUpModule/tearDownModule pair per polluting file).
_D1_STATE: dict = {}


def _real_store_bytes() -> bytes:
    """Bytes of the real store file (b'' when absent)."""
    try:
        return _REAL_STORE.read_bytes()
    except Exception:
        return b""


def isolate_module_store() -> None:
    """Point ``COMFYMODAL_V2_REGISTRY_PROOF_STORE`` at a temp COPY of the real
    store for the duration of one test module.

    The copy preserves read behavior (a plan build that expects a store hit
    still sees the primed entries) while redirecting every write away from the
    real shared store.  No-op-safe: any prior un-restored state is replaced.
    """
    global _D1_STATE
    td = tempfile.mkdtemp(prefix="d1_store_")
    temp_store = Path(td) / "v2_registry_proof_store.json"
    real_bytes = _real_store_bytes()
    if real_bytes:
        temp_store.write_bytes(real_bytes)
    _D1_STATE = {
        "temp_dir": td,
        "temp_store": str(temp_store),
        "saved": os.environ.get(_STORE_ENV),
    }
    os.environ[_STORE_ENV] = str(temp_store)


def restore_module_store() -> None:
    """Restore the pre-test store env and remove the temp dir.  Idempotent."""
    global _D1_STATE
    state = _D1_STATE
    _D1_STATE = {}
    if not state:
        return
    saved = state.get("saved")
    if saved is None:
        os.environ.pop(_STORE_ENV, None)
    else:
        os.environ[_STORE_ENV] = saved
    temp_dir = state.get("temp_dir", "")
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)
