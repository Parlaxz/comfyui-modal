"""Frozen-form regression tests for the workflow-relevant registry parity.

Root cause fixed in ``comfymodal_runtime/registry_proof.py``:
``ExecutionPlan.__post_init__`` freezes ``deployment_identity`` (and its
nested ``registry_proof``) via ``_freeze`` (contracts.py), turning the
nested proof into a ``MappingProxyType`` and its ``classes`` list into a
tuple.  The parity evaluator previously used strict ``isinstance(..., dict)``
gates, so a frozen plan proof was rejected as ``plan_registry_proof_unavailable``
(``workflow_class_count=0``) — the exact production failure.  The same bug
rejected the frozen snapshot manifest
(``snapshot_registry_manifest_unavailable``).

These tests pin the frozen-input behavior using the REAL functions.  The
fail-closed gates (missing snapshot class, identity mismatch, incomplete
proof, empty class set) are unchanged and are re-asserted on frozen forms.

All tests are local (no Modal, no paid anything, no ComfyUI imports).
"""

import unittest
from types import MappingProxyType

from comfymodal_runtime.contracts import (
    DEPLOYMENT_PROOF_SCHEMA_VERSION,
    VALIDATION_PROOF_SCHEMA_VERSION,
    ExecutionPlan,
    _freeze,
    evaluate_plan_snapshot_parity,
)
from comfymodal_runtime.registry_proof import evaluate_workflow_registry_parity


def _proof_3(**overrides) -> dict:
    """A complete 3-class plan-side workflow registry proof."""
    proof = {
        "schema_version": 1,
        "workflow_class_count": 3,
        "classes": ["A", "B", "C"],
        "identities": {"A": "IA", "B": "IB", "C": "IC"},
        "missing_host": [],
        "unresolved_identity": [],
        "complete": True,
    }
    proof.update(overrides)
    return proof


def _manifest_3(**overrides) -> dict:
    """A matching 3-class snapshot-side registry manifest."""
    manifest = {
        "schema_version": 1,
        "class_count": 3,
        "classes": {"A": "IA", "B": "IB", "C": "IC"},
        "incomplete_classes": [],
    }
    manifest.update(overrides)
    return manifest


class TestFrozenRegistryParity(unittest.TestCase):
    def test_frozen_proof_frozen_manifest_matches(self):
        """THE root-cause regression: frozen (``_freeze``d) proof + frozen
        manifest must match with full 3/3/3 counts.  Before the fix this
        returned ``plan_registry_proof_unavailable`` with 0/0/0."""
        result = evaluate_workflow_registry_parity(_freeze(_proof_3()), _freeze(_manifest_3()))
        self.assertIs(result["workflow_registry_match"], True)
        self.assertEqual(result["workflow_class_count"], 3)
        self.assertEqual(result["host_proved_count"], 3)
        self.assertEqual(result["snapshot_proved_count"], 3)
        self.assertEqual(result["reason"], "")
        # Plain dicts still pass (regression guard on the shared code path).
        plain = evaluate_workflow_registry_parity(_proof_3(), _manifest_3())
        self.assertIs(plain["workflow_registry_match"], True)

    def test_frozen_proof_plain_manifest_matches(self):
        """Mixed form: frozen plan proof + plain snapshot manifest."""
        result = evaluate_workflow_registry_parity(_freeze(_proof_3()), _manifest_3())
        self.assertIs(result["workflow_registry_match"], True)
        self.assertEqual(result["workflow_class_count"], 3)

    def test_plain_proof_frozen_manifest_matches(self):
        """Mixed form: plain plan proof + frozen snapshot manifest."""
        result = evaluate_workflow_registry_parity(_proof_3(), _freeze(_manifest_3()))
        self.assertIs(result["workflow_registry_match"], True)
        self.assertEqual(result["snapshot_proved_count"], 3)

    def test_frozen_classes_tuple_and_identities(self):
        """Exactly what ``_freeze`` produces: classes is a tuple, identities
        is a mappingproxy — both must be accepted."""
        frozen = _freeze(_proof_3())
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertIsInstance(frozen["classes"], tuple)
        self.assertIsInstance(frozen["identities"], MappingProxyType)
        self.assertIsInstance(frozen["missing_host"], tuple)
        result = evaluate_workflow_registry_parity(frozen, _freeze(_manifest_3()))
        self.assertIs(result["workflow_registry_match"], True)
        self.assertEqual(result["host_proved_count"], 3)

    def test_frozen_missing_snapshot_still_fails_closed(self):
        """Frozen forms: a workflow class absent from the snapshot manifest ->
        match False with the class named (gate unchanged)."""
        manifest = _manifest_3(classes={"A": "IA", "B": "IB"})  # C missing
        result = evaluate_workflow_registry_parity(_freeze(_proof_3()), _freeze(manifest))
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "missing_snapshot_class")
        self.assertIn("C", result["missing_snapshot"])

    def test_frozen_identity_mismatch_still_fails_closed(self):
        """Frozen forms: a drifted identity -> identity_mismatch (gate
        unchanged)."""
        manifest = _manifest_3(classes={"A": "IA-OTHER", "B": "IB", "C": "IC"})
        result = evaluate_workflow_registry_parity(_freeze(_proof_3()), _freeze(manifest))
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "identity_mismatch")
        self.assertIn("A", result["identity_mismatch"])

    def test_frozen_incomplete_proof_still_fails_closed(self):
        """Frozen forms: an incomplete plan proof -> plan_registry_proof_incomplete
        (gate unchanged)."""
        result = evaluate_workflow_registry_parity(
            _freeze(_proof_3(complete=False)), _freeze(_manifest_3())
        )
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "plan_registry_proof_incomplete")

    def test_empty_frozen_proof_still_fails_closed(self):
        """Frozen empty proof -> plan_registry_proof_unavailable (gate
        unchanged)."""
        result = evaluate_workflow_registry_parity(_freeze({}), _freeze(_manifest_3()))
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "plan_registry_proof_unavailable")
        self.assertEqual(result["workflow_class_count"], 0)

    def test_execution_plan_frozen_identity_gate_roundtrip(self):
        """FULL end-to-end regression: an ExecutionPlan built via from_dict
        freezes its deployment_identity (mappingproxy with a nested frozen
        registry_proof); evaluate_plan_snapshot_parity on the frozen identity
        must be workflow-registry-matched and future-fast-path-eligible.
        Before the fix this produced plan_registry_proof_unavailable — the
        exact production failure."""
        plan = ExecutionPlan.from_dict({
            "workflow": {
                "1": {"class_type": "A", "inputs": {}},
                "2": {"class_type": "B", "inputs": {}},
                "3": {"class_type": "C", "inputs": {}},
            },
            "workflow_hash": "h",
            "source_workflow_hash": "h",
            "output_node_ids": ["3"],
            "deployment_identity": {
                "complete": True,
                "schema_version": VALIDATION_PROOF_SCHEMA_VERSION,
                "deployment_combined_hash": "X",
                "custom_nodes_generation": "G",
                "dependency_manifest_identity": "D1",
                "registry_fingerprint": "F",
                "registry_proof_complete": True,
                "registry_proof": _proof_3(),
            },
        })
        # ExecutionPlan freezes deployment_identity at construction.
        frozen = plan.deployment_identity
        self.assertIsInstance(frozen["registry_proof"], MappingProxyType)
        self.assertIsInstance(frozen["registry_proof"]["classes"], tuple)
        snapshot = {
            "schema_version": DEPLOYMENT_PROOF_SCHEMA_VERSION,
            "valid": True,
            "complete": True,
            "deployment_combined_hash": "X",
            "custom_nodes_generation": "G",
            "dependency_manifest_identity": "D1",
            "registry_fingerprint": "F",
            "registry_manifest": _manifest_3(),
        }
        result = evaluate_plan_snapshot_parity(plan.deployment_identity, snapshot)
        self.assertIs(result["workflow_registry_match"], True)
        self.assertIs(result["registry_parity_reason"], "")
        self.assertIs(result["future_fast_path_eligible"], True)
        self.assertEqual(result["future_fast_path_ineligible_reason"], "")
        # Round-trip through to_dict / from_dict preserves the proof.
        plan2 = ExecutionPlan.from_dict(plan.to_dict())
        self.assertIsInstance(plan2.deployment_identity["registry_proof"], MappingProxyType)
        result2 = evaluate_plan_snapshot_parity(plan2.deployment_identity, snapshot)
        self.assertIs(result2["future_fast_path_eligible"], True)


if __name__ == "__main__":
    unittest.main()
