"""Regression guard: NO test path may write the REAL D1 registry-proof store.

The real store at ``<repo>/.cache/v2_registry_proof_store.json`` is shared
mutable state bounded to 8 entries (``registry_proof_store._MAX_ENTRIES``).
A real ``build_execution_plan`` under the deploy-frozen identity writes it via
``_proof_store_save``; once 8 entries are exceeded the oldest is EVICTED —
and the canonical prime entry (workflow_hash 2e43d4c0…) was lost this way.

This guard proves the isolation contract: a REAL plan build against the
canonical workflow, with the store path and deployed-state anchor redirected
to per-test temp files, leaves the real store byte-identical while the write
lands in the temp store under the temp anchor (positive control — the write
path is genuinely exercised, so the guard cannot pass vacuously).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_STORE = _REPO_ROOT / ".cache" / "v2_registry_proof_store.json"
_CANONICAL_WORKFLOW = _REPO_ROOT / "latest_benchmark_workflow.json"

_ENV_NAMES = (
    "COMFYMODAL_V2_REGISTRY_PROOF_STORE",
    "COMFYMODAL_V2_DEPLOYED_STATE_JSON",
    "COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH",
)


def _deployed_state() -> dict:
    """A complete deploy-frozen anchor (all four required fields)."""
    return {
        "custom_nodes_generation": "gen-guard",
        "deployment_combined_hash": "dep-guard",
        "overall_dependency_hash": "overall-guard",
        "comfyui_version": "0.24.0",
        "comfyui_commit": "c0ffee",
    }


def _canonical_workflow() -> tuple[dict, dict]:
    snapshot = json.loads(_CANONICAL_WORKFLOW.read_text(encoding="utf-8"))
    payload = snapshot.get("payload", snapshot)
    return payload.get("prompt", payload), payload.get("modal_options", {})


def _real_store_bytes() -> bytes:
    try:
        return _REAL_STORE.read_bytes()
    except Exception:
        return b""


def _real_store_keys() -> list[str]:
    try:
        data = json.loads(_REAL_STORE.read_text(encoding="utf-8"))
        return sorted((data.get("entries") or {}).keys())
    except Exception:
        return []


class TestRealStoreNotPolluted(unittest.TestCase):
    def test_real_plan_build_writes_only_temp_store(self):
        saved = {name: os.environ.get(name) for name in _ENV_NAMES}
        td = tempfile.mkdtemp(prefix="d1_guard_")
        self.addCleanup(lambda: shutil.rmtree(td, ignore_errors=True))
        try:
            temp_store = Path(td) / "store.json"
            temp_state = Path(td) / "deployed_state.json"
            temp_state.write_text(json.dumps(_deployed_state()), encoding="utf-8")
            os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = str(temp_store)
            os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = str(temp_state)
            # Ensure the plan identity is deploy-persisted (frozen) — a
            # metadata/env deployment hash would disable the store write.
            os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)

            real_before = _real_store_bytes()
            real_keys_before = _real_store_keys()

            from canonical_execution import build_execution_plan

            workflow, modal_options = _canonical_workflow()
            plan = build_execution_plan(
                workflow, validate=False, modal_options=modal_options,
            )

            real_after = _real_store_bytes()
            real_keys_after = _real_store_keys()

            # (c) The real store is unchanged: byte-identical, same key set,
            # no new entries — no test path writes it.
            self.assertEqual(real_before, real_after)
            self.assertEqual(real_keys_before, real_keys_after)

            # Positive control: the write DID happen — in the temp store, keyed
            # by the TEMP anchor (correct isolation), carrying the canonical
            # dispatch workflow hash.
            self.assertTrue(temp_store.is_file(), "temp store must receive the write")
            data = json.loads(temp_store.read_text(encoding="utf-8"))
            entries = data.get("entries", {})
            self.assertGreaterEqual(len(entries), 1)
            first = next(iter(entries.values()))
            self.assertEqual(first.get("workflow_hash", ""), plan.workflow_hash)
            anchor = first.get("identity_anchor") or {}
            self.assertEqual(anchor.get("deployment_hash"), "dep-guard")
            self.assertEqual(anchor.get("generation"), "gen-guard")
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
