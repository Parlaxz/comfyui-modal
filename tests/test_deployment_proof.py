"""Tests for the Step-2 canonical deployment-static proof.

Covers:
  - BootstrapState proof freeze / stale-marking lifecycle
  - Host-side baked-generation provenance reader parity with the
    container-side freeze extraction (same dict shape)
  - compute_registry_fingerprint roots filtering (in/out of root,
    determinism, relevant-change sensitivity)
  - evaluate_plan_snapshot_parity full matrix (eligible / each mismatch)
  - host-side validation memoization (identical builds run validate_prompt
    once; identity change misses)
  - no Modal/network imports triggered by the new host-side paths

All tests are local (no Modal, no paid anything).  ``execution`` and ``nodes``
are stubbed via ``sys.modules`` where needed.
"""

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from comfymodal_runtime.contracts import (
    DEPLOYMENT_PROOF_SCHEMA_VERSION,
    VALIDATION_PROOF_SCHEMA_VERSION,
    compute_registry_fingerprint,
    evaluate_plan_snapshot_parity,
)
from comfymodal_runtime.runtime_bootstrap import BootstrapState

REPO_ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_A = {
    "1": {"class_type": "X", "inputs": {}},
    "2": {"class_type": "Y", "inputs": {"a": ["1", 0]}},
}


class _DummyNode:
    """Simple stand-in for a NODE_CLASS_MAPPINGS entry."""


_REMOVE = object()


def _load_canonical():
    """Load canonical_execution module without parent-ComfyUI imports."""
    spec = importlib.util.spec_from_file_location(
        "canonical_execution", REPO_ROOT / "canonical_execution.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canonical_execution"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_fake_execution(outputs, valid=True, error=None, node_errors=None, counter=None):
    """Fake ``execution`` module whose validate_prompt is controllable."""
    mod = types.ModuleType("execution")

    async def validate_prompt(prompt_id, prompt, partial_execution_list=None):
        if counter is not None:
            counter[0] += 1
        return (valid, error, outputs, node_errors or {})

    mod.validate_prompt = validate_prompt
    return mod


def _make_fake_nodes(mappings=None):
    """Fake ``nodes`` module carrying a NODE_CLASS_MAPPINGS registry."""
    mod = types.ModuleType("nodes")
    if mappings is None:
        mappings = {"X": _DummyNode, "Y": _DummyNode}
    mod.NODE_CLASS_MAPPINGS = mappings
    return mod


class _stub_modules:
    """Context manager installing module stubs into sys.modules."""

    def __init__(self, stubs):
        self._stubs = stubs
        self._saved = {}

    def __enter__(self):
        for name, value in self._stubs.items():
            self._saved[name] = sys.modules.get(name)
            if value is _REMOVE:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self._saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return False


def _full_proof(**overrides) -> dict:
    """A complete, valid frozen proof dict."""
    proof = {
        "schema_version": DEPLOYMENT_PROOF_SCHEMA_VERSION,
        "deployment_combined_hash": "dep123",
        "custom_nodes_generation": "gen1",
        "generation_matches_observed": True,
        "registry_fingerprint": "fp1",
        "dependency_manifest_identity": "depid1",
        "repair_mode": "off",
        "registry_manifest": {
            "schema_version": 1,
            "class_count": 1,
            "classes": {"A": "ID-A"},
            "incomplete_classes": [],
        },
        "complete": True,
        "valid": True,
        "invalid_reason": "",
        "source": "snapshot_startup",
    }
    proof.update(overrides)
    return proof


def _full_plan_identity(**overrides) -> dict:
    """A complete plan-carried deployment identity (Step-1 semantics)."""
    identity = {
        "schema_version": VALIDATION_PROOF_SCHEMA_VERSION,
        "deployment_combined_hash": "dep123",
        "custom_nodes_generation": "gen1",
        "registry_fingerprint": "fp1",
        "dependency_manifest_identity": "depid1",
        "registry_proof": {
            "schema_version": 1,
            "workflow_class_count": 1,
            "classes": ["A"],
            "identities": {"A": "ID-A"},
            "missing_host": [],
            "unresolved_identity": [],
            "complete": True,
        },
        "registry_proof_complete": True,
        "complete": True,
    }
    identity.update(overrides)
    return identity


class TestBootstrapProofLifecycle(unittest.TestCase):
    def test_proof_freeze_complete(self):
        """freeze_validation_proof stores the payload intact."""
        state = BootstrapState()
        proof = _full_proof()
        state.freeze_validation_proof(proof)
        self.assertEqual(state.snapshot_validation_proof, proof)
        self.assertIsNot(state.snapshot_validation_proof, proof)  # copied, not aliased

    def test_proof_incomplete_when_deployment_hash_missing(self):
        """An empty deployment hash makes the proof incomplete and names the
        missing component (never fabricates)."""
        state = BootstrapState()
        state.freeze_validation_proof(_full_proof(deployment_combined_hash="", complete=False, valid=False,
                                                  invalid_reason="deployment_hash_unavailable"))
        proof = state.snapshot_validation_proof
        self.assertIs(proof["complete"], False)
        self.assertEqual(proof["deployment_combined_hash"], "")
        self.assertIn("deployment_hash_unavailable", proof["invalid_reason"])

    def test_mark_stale_flips_valid(self):
        """mark_validation_proof_stale flips valid and records the reason
        while preserving the rest of the payload."""
        state = BootstrapState()
        state.freeze_validation_proof(_full_proof())
        state.mark_validation_proof_stale("custom_node_generation_mismatch")
        proof = state.snapshot_validation_proof
        self.assertIs(proof["valid"], False)
        self.assertEqual(proof["invalid_reason"], "custom_node_generation_mismatch")
        self.assertEqual(proof["deployment_combined_hash"], "dep123")
        self.assertEqual(proof["custom_nodes_generation"], "gen1")
        self.assertEqual(proof["registry_fingerprint"], "fp1")

    def test_mark_stale_noop_when_empty(self):
        """marking stale on an empty proof is a no-op (nothing to invalidate)."""
        state = BootstrapState()
        state.mark_validation_proof_stale("x")
        self.assertEqual(state.snapshot_validation_proof, {})


class TestRegistryManifestPublication(unittest.TestCase):
    def test_manifest_error_and_root_count_are_published_fail_closed(self):
        """Manifest failure detail remains observable without inventing data."""
        from comfymodal_runtime.modal_app import _registry_manifest_publication_fields

        fields = _registry_manifest_publication_fields(
            {"classes": {}, "error": "nodes import failed"},
            root_count=3,
        )
        self.assertEqual(
            fields["registry_manifest"],
            {"classes": {}, "error": "nodes import failed"},
        )
        self.assertEqual(fields["registry_manifest_error"], "nodes import failed")
        self.assertEqual(fields["registry_manifest_root_count"], 3)
        self.assertEqual(fields["registry_manifest_class_count"], 0)

        fallback = _registry_manifest_publication_fields(
            None,
            error="RuntimeError: builder failed",
            root_count=2,
        )
        self.assertEqual(fallback["registry_manifest"], {})
        self.assertEqual(
            fallback["registry_manifest_error"], "RuntimeError: builder failed"
        )
        self.assertEqual(fallback["registry_manifest_root_count"], 2)


class TestBakedGenerationProvenance(unittest.TestCase):
    def test_generation_provenance_same_both_sides(self):
        """Host reader and container freeze extraction consume the same value
        from the same baked-manifest dict shape."""
        mod = _load_canonical()
        baked = {
            "production_custom_node_generation": "gen_x123",
            "overall_dependency_hash": "h" * 64,
            "schema_version": 2,
        }
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "custom_node_deps_baked.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(baked, f)
            with mock.patch.object(mod, "_BAKED_CUSTOM_NODE_DEPS_LOCAL", path):
                host_gen = mod._read_baked_custom_node_generation()
        # Container freeze extraction: same dict shape -> same value.
        container_gen = str((dict(baked) or {}).get("production_custom_node_generation", "") or "")
        self.assertEqual(host_gen, "gen_x123")
        self.assertEqual(host_gen, container_gen)


class TestRegistryFingerprintRoots(unittest.TestCase):
    def setUp(self):
        class _InRoot:
            __module__ = "dep_proof_inroot_mod"

        class _OutRoot:
            __module__ = "dep_proof_outroot_mod"

        class _AlsoInRoot:
            __module__ = "dep_proof_inroot_mod"

        self._in_cls = _InRoot
        self._also_in_cls = _AlsoInRoot
        self._out_cls = _OutRoot
        self._in_mod = types.ModuleType("dep_proof_inroot_mod")
        self._out_mod = types.ModuleType("dep_proof_outroot_mod")
        self._root = os.path.normpath("C:/fake/roots/comfy")
        self._in_mod.__file__ = os.path.join(self._root, "nodes", "in_nodes.py")
        self._out_mod.__file__ = os.path.normpath("D:/elsewhere/out_nodes.py")

    def test_registry_fingerprint_deterministic(self):
        """Same mappings + same roots twice -> equal fingerprint."""
        mappings = {"In": self._in_cls}
        with _stub_modules({"dep_proof_inroot_mod": self._in_mod}):
            fp1 = compute_registry_fingerprint(mappings, roots=[self._root])
            fp2 = compute_registry_fingerprint(mappings, roots=[self._root])
        self.assertEqual(fp1, fp2)
        self.assertTrue(fp1)

    def test_registry_fingerprint_excludes_out_of_root(self):
        """Out-of-root classes are excluded; in-root classes are kept."""
        both = {"In": self._in_cls, "Out": self._out_cls}
        only_in = {"In": self._in_cls}
        in_and_also = {"In": self._in_cls, "Also": self._also_in_cls}
        with _stub_modules({
            "dep_proof_inroot_mod": self._in_mod,
            "dep_proof_outroot_mod": self._out_mod,
        }):
            fp_both = compute_registry_fingerprint(both, roots=[self._root])
            fp_only_in = compute_registry_fingerprint(only_in, roots=[self._root])
            fp_in_and_also = compute_registry_fingerprint(in_and_also, roots=[self._root])
        self.assertEqual(fp_both, fp_only_in)  # Out excluded
        self.assertNotEqual(fp_in_and_also, fp_only_in)  # in-root addition changes it

    def test_registry_fingerprint_changes_on_relevant_change(self):
        """Renaming an in-root class changes the fingerprint."""
        class _Renamed:
            __module__ = "dep_proof_inroot_mod"

        mappings_a = {"In": self._in_cls}
        mappings_b = {"Renamed": _Renamed}
        with _stub_modules({"dep_proof_inroot_mod": self._in_mod}):
            fp_a = compute_registry_fingerprint(mappings_a, roots=[self._root])
            fp_b = compute_registry_fingerprint(mappings_b, roots=[self._root])
        self.assertNotEqual(fp_a, fp_b)

    def test_roots_none_full_registry(self):
        """roots=None keeps the full registry (backward compat)."""
        with _stub_modules({"dep_proof_inroot_mod": self._in_mod, "dep_proof_outroot_mod": self._out_mod}):
            fp_full = compute_registry_fingerprint({"In": self._in_cls, "Out": self._out_cls})
        with _stub_modules({"dep_proof_inroot_mod": self._in_mod, "dep_proof_outroot_mod": self._out_mod}):
            fp_in = compute_registry_fingerprint({"In": self._in_cls}, roots=[self._root])
        self.assertNotEqual(fp_full, fp_in)


class TestParityMatrix(unittest.TestCase):
    def test_parity_full_match_eligible(self):
        result = evaluate_plan_snapshot_parity(_full_plan_identity(), _full_proof())
        self.assertIs(result["future_fast_path_eligible"], True)
        self.assertEqual(result["future_fast_path_ineligible_reason"], "")
        self.assertTrue(result["deployment_hash_match"])
        self.assertTrue(result["custom_nodes_generation_match"])
        self.assertTrue(result["registry_fingerprint_match"])
        self.assertTrue(result["workflow_registry_match"])
        self.assertTrue(result["dependency_proof_match"])
        self.assertTrue(result["snapshot_proof_complete"])
        self.assertTrue(result["snapshot_proof_valid"])

    def test_parity_generation_mismatch(self):
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(custom_nodes_generation="gen_other"), _full_proof()
        )
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("custom_nodes_generation_mismatch", result["future_fast_path_ineligible_reason"])

    def test_parity_deployment_hash_mismatch(self):
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(deployment_combined_hash="dep_other"), _full_proof()
        )
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("deployment_hash_mismatch", result["future_fast_path_ineligible_reason"])

    def test_parity_workflow_registry_mismatch(self):
        """A snapshot-manifest identity mismatch on a workflow-relevant class
        fails the AUTHORITATIVE workflow-registry axis (ineligible) even when
        the legacy full-registry fingerprint (diagnostic) still matches."""
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(),
            _full_proof(registry_manifest={
                "schema_version": 1,
                "class_count": 1,
                "classes": {"A": "ID-A-OTHER"},
                "incomplete_classes": [],
            }),
        )
        self.assertIs(result["workflow_registry_match"], False)
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("workflow_registry_mismatch", result["future_fast_path_ineligible_reason"])
        self.assertTrue(result["registry_fingerprint_match"])  # diagnostic unaffected

    def test_parity_full_fingerprint_mismatch_diagnostic_only(self):
        """The legacy full-registry fingerprint is DIAGNOSTIC only: a
        fingerprint mismatch alone no longer blocks eligibility when the
        workflow-relevant registry proof matches."""
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(registry_fingerprint="fp_other"), _full_proof()
        )
        self.assertIs(result["registry_fingerprint_match"], False)
        self.assertTrue(result["workflow_registry_match"])
        self.assertIs(result["future_fast_path_eligible"], True)
        self.assertEqual(result["future_fast_path_ineligible_reason"], "")

    def test_parity_incomplete_proof_ineligible(self):
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(), _full_proof(complete=False)
        )
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("snapshot_proof_incomplete", result["future_fast_path_ineligible_reason"])

    def test_parity_stale_proof_ineligible(self):
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(), _full_proof(valid=False, invalid_reason="custom_node_generation_mismatch")
        )
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("snapshot_proof_invalid_or_unsupported", result["future_fast_path_ineligible_reason"])

    def test_parity_dependency_mismatch(self):
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(dependency_manifest_identity="depid_other"), _full_proof()
        )
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("dependency_proof_mismatch", result["future_fast_path_ineligible_reason"])

    def test_parity_empty_inputs(self):
        result = evaluate_plan_snapshot_parity(None, None)
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("plan_identity_incomplete", result["future_fast_path_ineligible_reason"])
        self.assertIn("snapshot_proof_incomplete", result["future_fast_path_ineligible_reason"])


class TestPlanProofDecisionReporting(unittest.TestCase):
    def test_consumed_proof_does_not_report_not_eligible(self):
        from comfymodal_runtime.modal_app import _get_plan_proof_decision_reason

        self.assertEqual(
            _get_plan_proof_decision_reason(True, "", "parity_ineligible"),
            "",
        )
        # The fallback remains fail-closed and keeps its existing reasons.
        self.assertEqual(
            _get_plan_proof_decision_reason(False, "repair_changed", ""),
            "repair_changed",
        )
        self.assertEqual(
            _get_plan_proof_decision_reason(False, "", ""),
            "not_eligible",
        )


class TestHostValidationMemo(unittest.TestCase):
    def setUp(self):
        import tempfile as _tf
        import shutil as _sh
        self._td = _tf.mkdtemp()
        self.addCleanup(lambda: _sh.rmtree(self._td, ignore_errors=True))
        self._saved_store = os.environ.get("COMFYMODAL_V2_REGISTRY_PROOF_STORE")
        os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = os.path.join(
            self._td, "v2_registry_proof_store.json"
        )
        self.addCleanup(self._restore_store_env)
        self.mod = _load_canonical()
        self.mod._PLAN_VALIDATION_MEMO.clear()

    def _restore_store_env(self):
        if self._saved_store is None:
            os.environ.pop("COMFYMODAL_V2_REGISTRY_PROOF_STORE", None)
        else:
            os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = self._saved_store

    def test_host_validation_memoized(self):
        """Identical workflow + identity runs validate_prompt exactly once and
        produces equal payloads on both builds."""
        counter = [0]
        with _stub_modules({
            "execution": _make_fake_execution(["5", "9"], counter=counter),
            "nodes": _make_fake_nodes(),
        }):
            plan_a = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
            plan_b = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        self.assertEqual(counter[0], 1)
        self.assertEqual(dict(plan_a.validation), dict(plan_b.validation))
        self.assertEqual(plan_a.validation["validated_workflow_hash"], plan_a.workflow_hash)
        self.assertEqual(plan_b.validation["validated_workflow_hash"], plan_b.workflow_hash)

    def test_memo_misses_on_identity_change(self):
        """A different deployment hash misses the memo and re-runs
        validate_prompt."""
        counter = [0]
        saved_env = os.environ.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH")
        try:
            with _stub_modules({
                "execution": _make_fake_execution(["5", "9"], counter=counter),
                "nodes": _make_fake_nodes(),
            }):
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "dep_a"
                plan_a = self.mod.build_execution_plan(
                    dict(WORKFLOW_A), prompt_id="p1", validate=False,
                    collect_validation_proof=True,
                )
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "dep_b"
                plan_b = self.mod.build_execution_plan(
                    dict(WORKFLOW_A), prompt_id="p1", validate=False,
                    collect_validation_proof=True,
                )
        finally:
            if saved_env is None:
                os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
            else:
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = saved_env
        self.assertEqual(counter[0], 2)
        self.assertNotEqual(
            dict(plan_a.deployment_identity)["deployment_combined_hash"],
            dict(plan_b.deployment_identity)["deployment_combined_hash"],
        )
        self.assertEqual(dict(plan_a.validation), dict(plan_b.validation))

    def test_no_remote_calls_before_submission(self):
        """The new host-side paths (baked reader, memo key, identity builder)
        complete with no Modal/network/Volume imports."""
        modal_already = "modal" in sys.modules
        gen = self.mod._read_baked_custom_node_generation()
        self.assertIsInstance(gen, str)
        ident = self.mod._collect_plan_deployment_identity({}, "")
        self.assertIsInstance(ident.get("dependency_manifest_identity", None), str)
        key = self.mod._memo_key_plan_validation("h" * 64, dict(ident))
        self.assertIsInstance(key, tuple)
        self.assertEqual(len(key), 5)
        if not modal_already:
            self.assertNotIn("modal", sys.modules)


if __name__ == "__main__":
    unittest.main()
