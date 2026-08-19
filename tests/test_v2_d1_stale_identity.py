"""D1 stale-identity fail-closed regression (D6 zero-spend preflight).

Read-only audit finding (exp-2): ``.deployed_state.json`` holds a STALE identity
(``deployment_combined_hash`` e8f269ee…, ``custom_nodes_generation`` 4ee9e0d0…,
``source=container_readback``) from an earlier deploy; the failed deploy4 never
recorded.  The registry-proof store's 8 entries are keyed to that stale anchor
(canonical entry key 405eb308…, workflow_hash 2e43d4c0…).  ``_entry_key`` hashes
generation + deployment_hash + comfyui_version + comfyui_commit + comfyui_root
+ workflow_hash, and ``lookup`` re-validates ``entry.identity_anchor ==
current_identity_anchor()`` — so a NEW deployed identity MUST fail closed
(no silent reuse of the stale proof).

These tests pin that §13-required fail-closed contract against the REAL
``registry_proof_store`` and the REAL ``tools.benchmark_v2_direct`` covers
helper:

  * a full anchor change (different generation AND deployment hash) makes
    ``lookup`` miss and ``_registry_proof_store_covers`` flip to False — the
    D1 fast path falls back to a live registry import instead of silently
    reusing the stale proof;
  * the silent-drift class (same generation, ONLY the deployment hash changes)
    also fails closed;
  * ``lookup`` / ``_registry_proof_store_covers`` are READ-ONLY: the store
    file is byte-identical after a miss (never rewritten by a read path).

All fixtures are self-contained in per-test temp dirs via the env overrides
(``COMFYMODAL_V2_REGISTRY_PROOF_STORE`` / ``COMFYMODAL_V2_DEPLOYED_STATE_JSON``)
and restored after; the REAL ``.cache/v2_registry_proof_store.json`` is never
touched (verified byte-identical around the suite run).  No ``comfy`` import
(the store module is stdlib-only; ``resolve_dispatch_workflow_hash`` is pure
dict work and never imports the registry).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]

_ENV_NAMES = (
    "COMFYMODAL_V2_REGISTRY_PROOF_STORE",
    "COMFYMODAL_V2_DEPLOYED_STATE_JSON",
    "COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH",
)

_BVD: Any = None


def _bvd():
    """Lazy guarded import of the heavy benchmark harness module (mirrors
    tests/test_v2_batch_d1_registry_proof_store.py)."""
    global _BVD
    if _BVD is None:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        import tools.benchmark_v2_direct as _mod

        _BVD = _mod
    return _BVD


# A valid 2-node workflow shape (mirrors the D1 batch test).
WORKFLOW = {
    "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
    "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
}


def _deployed_state(
    generation: str = "genA",
    deployment_hash: str = "hashA",
    version: str = "0.24.0",
    commit: str = "c0ffee",
    overall: str = "overall-a",
) -> dict:
    """A deploy-frozen identity record (all four anchor fields present)."""
    return {
        "custom_nodes_generation": generation,
        "deployment_combined_hash": deployment_hash,
        "overall_dependency_hash": overall,
        "comfyui_version": version,
        "comfyui_commit": commit,
    }


def _anchor(generation: str, deployment_hash: str) -> dict:
    """The exact anchor dict ``current_identity_anchor()`` must return."""
    return {
        "generation": generation,
        "deployment_hash": deployment_hash,
        "comfyui_version": "0.24.0",
        "comfyui_commit": "c0ffee",
    }


def _synthetic_entry() -> dict:
    """A complete persisted payload (fingerprint + proof + validation) so the
    covers helper's ``_PLAN_VALIDATION_PROOF`` gate passes under the OLD
    anchor — the flip to False is then attributable to the anchor change."""
    return {
        "registry_fingerprint": "fp-abc123",
        "registry_proof": {
            "schema_version": 1,
            "workflow_class_count": 2,
            "classes": ["KSampler", "SaveImage"],
            "identities": {"KSampler": "id-ks", "SaveImage": "id-si"},
            "missing_host": [],
            "unresolved_identity": [],
            "complete": True,
        },
        "validation": {
            "schema_version": 1,
            "validated": True,
            "outputs_to_execute": ["2"],
            "node_errors": {},
            "source": "host_validate_prompt",
        },
    }


class _StaleIdentityBase(unittest.TestCase):
    """Temp store + deployed-state env isolation (real store never touched)."""

    def setUp(self) -> None:
        self._td = tempfile.mkdtemp(prefix="d1_stale_")
        self.addCleanup(lambda: shutil.rmtree(self._td, ignore_errors=True))
        self._store = Path(self._td) / "store.json"
        self._state = Path(self._td) / "deployed_state.json"
        self._saved = {name: os.environ.get(name) for name in _ENV_NAMES}
        os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = str(self._store)
        os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = str(self._state)
        # The store write path requires the deploy-persisted (frozen) identity;
        # a metadata/env deployment hash would disable it.
        os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        self.addCleanup(self._restore_env)
        import comfymodal_runtime.registry_proof_store as store_mod

        self.store_mod = store_mod
        self.bvd = _bvd()

    def _restore_env(self) -> None:
        for name, saved in self._saved.items():
            if saved is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = saved

    def _write_state(self, state: dict) -> None:
        self._state.write_text(json.dumps(state), encoding="utf-8")

    def _dispatch_hash(self) -> str:
        """The exact hash the covers helper looks up (same inputs, no compile)."""
        return self.bvd.resolve_dispatch_workflow_hash(dict(WORKFLOW))

    def _save_entry(self, workflow_hash: str) -> None:
        root = str(self.bvd._COMFYUI_ROOT_DIR or "")
        self.store_mod.save(
            {
                "workflow_hash": workflow_hash,
                "comfyui_root": root,
                "registry_fingerprint": _synthetic_entry()["registry_fingerprint"],
                "registry_proof": _synthetic_entry()["registry_proof"],
                "validation": _synthetic_entry()["validation"],
            }
        )

    def _lookup_root(self) -> str:
        return str(self.bvd._COMFYUI_ROOT_DIR or "")


class TestStaleIdentityFailClosed(_StaleIdentityBase):
    def test_stale_identity_entries_unreachable_under_new_anchor(self) -> None:
        """(a) Under the OLD anchor A the persisted proof IS reachable; (b) after
        the identity moves to a NEW anchor B (different generation AND
        deployment hash), lookup misses and the covers flip to False — the D1
        fast path falls back to a live registry import (fail closed, no silent
        reuse of the stale proof)."""
        # (a) anchor A -> entry reachable + covers True.
        self._write_state(_deployed_state(generation="genA", deployment_hash="hashA"))
        self.assertEqual(
            self.store_mod.current_identity_anchor(),
            _anchor("genA", "hashA"),
        )
        wf = self._dispatch_hash()
        self._save_entry(wf)
        hit = self.store_mod.lookup(wf, self._lookup_root())
        assert hit is not None, "stale-anchor entry must be reachable under anchor A"
        self.assertEqual(hit["registry_fingerprint"], "fp-abc123")
        self.assertTrue(hit["registry_proof"]["complete"])
        self.assertEqual(hit["identity_anchor"], _anchor("genA", "hashA"))
        self.assertTrue(self.bvd._registry_proof_store_covers(dict(WORKFLOW)))

        # (b) anchor B (different generation AND deployment hash) -> miss,
        # covers False -> harness falls back to the live registry import.
        self._write_state(_deployed_state(generation="genB", deployment_hash="hashB"))
        self.assertEqual(
            self.store_mod.current_identity_anchor(),
            _anchor("genB", "hashB"),
        )
        self.assertIsNone(self.store_mod.lookup(wf, self._lookup_root()))
        self.assertFalse(self.bvd._registry_proof_store_covers(dict(WORKFLOW)))

    def test_partial_anchor_change_also_fails_closed(self) -> None:
        """The silent-drift class the audit flagged: ONLY the deployment_hash
        changes (same generation) -> anchor differs -> lookup misses."""
        self._write_state(_deployed_state(generation="genA", deployment_hash="hashA"))
        wf = self._dispatch_hash()
        self._save_entry(wf)
        self.assertIsNotNone(self.store_mod.lookup(wf, self._lookup_root()))

        self._write_state(_deployed_state(generation="genA", deployment_hash="hashB"))
        self.assertEqual(
            self.store_mod.current_identity_anchor(),
            _anchor("genA", "hashB"),
        )
        self.assertIsNone(self.store_mod.lookup(wf, self._lookup_root()))
        self.assertFalse(self.bvd._registry_proof_store_covers(dict(WORKFLOW)))

    def test_stale_anchor_not_rewritten(self) -> None:
        """The lookup/covers read path never mutates the store file (byte-
        identical before/after a new-anchor miss)."""
        self._write_state(_deployed_state(generation="genA", deployment_hash="hashA"))
        wf = self._dispatch_hash()
        self._save_entry(wf)
        before = self._store.read_bytes()

        self._write_state(_deployed_state(generation="genB", deployment_hash="hashB"))
        self.assertIsNone(self.store_mod.lookup(wf, self._lookup_root()))
        self.assertFalse(self.bvd._registry_proof_store_covers(dict(WORKFLOW)))

        after = self._store.read_bytes()
        self.assertEqual(before, after, "lookup must be read-only (store unchanged)")


class TestD10QuarantinedIdentityUnprimed(_StaleIdentityBase):
    """D10 Gate-D quarantine: deployment d679332c551f0cad is STRUCTURALLY
    INVALID FOR INFERENCE (capture gate failed) and must never be primed.  With
    the empty (unprimed) store under that exact anchor, lookup fails closed and
    the covers helper flips to False — no request could ride a stale proof."""

    D10_DEPLOYMENT_HASH = "d679332c551f0cad22b5f62d7f0935b1776f928844295f0fb0b0c86b359f9bb2"

    def test_quarantined_identity_lookup_fails_closed_unprimed(self) -> None:
        self._write_state(
            _deployed_state(generation="32ffaf27cac17b3c", deployment_hash=self.D10_DEPLOYMENT_HASH)
        )
        wf = self._dispatch_hash()
        # No prime was ever run for this identity -> store is empty -> miss.
        self.assertIsNone(self.store_mod.lookup(wf, self._lookup_root()))
        self.assertFalse(self.bvd._registry_proof_store_covers(dict(WORKFLOW)))

    def test_quarantined_identity_cannot_consume_other_anchor_entry(self) -> None:
        """Even if some OTHER anchor had a persisted entry, the quarantined
        D10 anchor must never match it (entry identity re-validation)."""
        self._write_state(_deployed_state(generation="genA", deployment_hash="hashA"))
        wf = self._dispatch_hash()
        self._save_entry(wf)
        self.assertIsNotNone(self.store_mod.lookup(wf, self._lookup_root()))
        # Identity moves to the quarantined D10 anchor -> same file, zero hit.
        self._write_state(
            _deployed_state(generation="32ffaf27cac17b3c", deployment_hash=self.D10_DEPLOYMENT_HASH)
        )
        self.assertIsNone(self.store_mod.lookup(wf, self._lookup_root()))
        self.assertFalse(self.bvd._registry_proof_store_covers(dict(WORKFLOW)))


if __name__ == "__main__":
    unittest.main()
