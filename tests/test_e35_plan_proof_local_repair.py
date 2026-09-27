"""Bounded E35 plan-proof production regressions.

These tests exercise only local proof construction/consumption inputs; they do
not invoke Modal or the parent validation owner.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from comfymodal_runtime.contracts import (
    evaluate_plan_snapshot_parity,
    evaluate_plan_validation_consumption,
)
from comfymodal_runtime.registry_proof import evaluate_workflow_registry_parity


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = {
    "1": {"class_type": "Alpha", "inputs": {}},
}
PROOF = {
    "schema_version": 1,
    "workflow_class_count": 1,
    "classes": ["Alpha"],
    "identities": {"Alpha": "id-alpha"},
    "missing_host": [],
    "unresolved_identity": [],
    "complete": True,
}


class TestE35PlanProofLocalRepair(unittest.TestCase):
    def test_exact_dispatch_workflow_hash_lookup(self):
        """The persisted store is keyed by the exact dispatch hash."""
        from canonical_execution import resolve_dispatch_workflow_hash
        from workflow_metadata import prompt_sha256
        import comfymodal_runtime.registry_proof_store as store

        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "deployed_state.json"
            store_path = Path(td) / "proof_store.json"
            state_path.write_text(json.dumps({
                "custom_nodes_generation": "g1",
                "deployment_combined_hash": "d1",
                "overall_dependency_hash": "dep1",
                "comfyui_version": "v1",
                "comfyui_commit": "c1",
            }), encoding="utf-8")
            old_store = os.environ.get("COMFYMODAL_V2_REGISTRY_PROOF_STORE")
            old_state = os.environ.get("COMFYMODAL_V2_DEPLOYED_STATE_JSON")
            os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = str(store_path)
            os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = str(state_path)
            try:
                exact = resolve_dispatch_workflow_hash(WORKFLOW)
                self.assertEqual(exact, prompt_sha256(WORKFLOW))
                store.save({"workflow_hash": exact, "registry_proof": PROOF})
                self.assertIsNotNone(store.lookup(exact))
                self.assertIsNone(store.lookup("0" * 64))
            finally:
                if old_store is None:
                    os.environ.pop("COMFYMODAL_V2_REGISTRY_PROOF_STORE", None)
                else:
                    os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = old_store
                if old_state is None:
                    os.environ.pop("COMFYMODAL_V2_DEPLOYED_STATE_JSON", None)
                else:
                    os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = old_state

    def test_unavailable_proof_fails_closed(self):
        result = evaluate_workflow_registry_parity({}, {})
        self.assertFalse(result["workflow_registry_match"])
        self.assertEqual(result["reason"], "plan_registry_proof_unavailable")
        self.assertEqual(result["workflow_class_count"], 0)

    def test_complete_proof_consumption_inputs(self):
        plan_proof = {
            "schema_version": 1,
            "workflow_class_count": 1,
            "classes": ["Alpha"],
            "identities": {"Alpha": "id-alpha"},
            "missing_host": [],
            "unresolved_identity": [],
            "complete": True,
        }
        manifest = {
            "schema_version": 1,
            "class_count": 1,
            "classes": {"Alpha": "id-alpha"},
            "incomplete_classes": [],
        }
        plan_identity = {
            "schema_version": 1,
            "complete": True,
            "deployment_combined_hash": "d1",
            "custom_nodes_generation": "g1",
            "dependency_manifest_identity": "dep1",
            "registry_proof_complete": True,
            "registry_proof": plan_proof,
        }
        snapshot = {
            "schema_version": 1,
            "complete": True,
            "valid": True,
            "deployment_combined_hash": "d1",
            "custom_nodes_generation": "g1",
            "dependency_manifest_identity": "dep1",
            "registry_manifest": manifest,
        }
        parity = evaluate_plan_snapshot_parity(plan_identity, snapshot)
        self.assertTrue(parity["future_fast_path_eligible"])
        consumed = evaluate_plan_validation_consumption(
            parity,
            {"schema_version": 1, "validated": True},
            workflow_hash_match=True,
            validation_hash_match=True,
            structure_ok=True,
            outputs_nonempty=True,
        )
        self.assertTrue(consumed["eligible"])


if __name__ == "__main__":
    unittest.main()
