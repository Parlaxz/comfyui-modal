"""Step-3 final parity tests: fail-closed deployment-identity chain and the
workflow-relevant registry proof.

Covers:
  - Deployment identity: the authoritative value comes ONLY from the
    metadata -> env ``COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH`` -> persisted
    ``.deployed_state.json`` chain.  The host-mirror recomputation is a
    DIAGNOSTIC field (``host_mirror_deployment_combined_hash``) and never
    grants identity when the baked value is unknown.
  - Dependency proof: ``dependency_manifest_identity`` equality between plan
    and snapshot (build_identity over combined hash / overall fingerprint /
    generation / repair mode).
  - Registry: workflow-relevant parity via ``registry_proof.py`` — plan
    proof classes are compared against the snapshot manifest for exactly
    those classes; unrelated classes on either side never invalidate;
    missing classes / identity drift / malformed proofs fail closed.
  - Path stability: class canonical identity is a pure function of module
    file *content* (path-independent, content-sensitive).
  - Cross-file: full ``evaluate_plan_snapshot_parity`` eligibility with a
    complete workflow proof, and the diagnostic line formatter.

All tests are local (no Modal, no paid anything, no ComfyUI imports).
``nodes`` is stubbed with an empty module where a fail-closed registry proof
is required, and ``_read_persisted_deployment_combined_hash`` is patched.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from comfymodal_runtime.contracts import (
    DEPLOYMENT_PROOF_SCHEMA_VERSION,
    VALIDATION_PROOF_SCHEMA_VERSION,
    apply_repair_invalidation,
    evaluate_plan_snapshot_parity,
    evaluate_plan_validation_consumption,
)
from comfymodal_runtime.dependency_manifest import (
    DEPENDENCY_MANIFEST_SCHEMA_VERSION,
    build_identity,
)
from comfymodal_runtime.registry_proof import (
    build_registry_manifest,
    build_workflow_registry_proof,
    class_canonical_identity,
    evaluate_workflow_registry_parity,
    format_registry_parity_line,
    workflow_class_types,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_DEPLOYMENT_HASH = "COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"


class _NodeAlpha:
    """Stand-in node class (defined in this test module so its identity can
    be resolved from the test file content)."""


class _NodeBeta:
    """Second stand-in node class for multi-class proofs."""


class _NodeAlphaMismatched:
    """Different class under the same mapping name -> identity mismatch."""


_EMPTY_NODES = types.ModuleType("nodes")
"""Stub with no ``NODE_CLASS_MAPPINGS``: every workflow class fails host-side."""


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


def _plan_proof_dict(classes, identities, complete=True, missing_host=(), unresolved=()):
    return {
        "schema_version": 1,
        "workflow_class_count": len(classes),
        "classes": list(classes),
        "identities": dict(identities),
        "missing_host": list(missing_host),
        "unresolved_identity": list(unresolved),
        "complete": complete,
    }


def _manifest_dict(classes):
    return {
        "schema_version": 1,
        "class_count": len(classes),
        "classes": dict(classes),
        "incomplete_classes": [],
    }


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


def _full_snapshot_proof(**overrides) -> dict:
    """A complete, valid frozen snapshot proof dict."""
    proof = {
        "schema_version": DEPLOYMENT_PROOF_SCHEMA_VERSION,
        "deployment_combined_hash": "dep123",
        "custom_nodes_generation": "gen1",
        "registry_fingerprint": "fp1",
        "dependency_manifest_identity": "depid1",
        "registry_manifest": {
            "schema_version": 1,
            "class_count": 1,
            "classes": {"A": "ID-A"},
            "incomplete_classes": [],
        },
        "complete": True,
        "valid": True,
    }
    proof.update(overrides)
    return proof


def _full_plan_validation(**overrides) -> dict:
    pv = {
        "schema_version": VALIDATION_PROOF_SCHEMA_VERSION,
        "validated": True,
        "outputs_to_execute": ["5", "9"],
        "node_errors": {},
        "validated_workflow_hash": "abc123",
        "source": "host_validate_prompt",
    }
    pv.update(overrides)
    return pv


def _dep_identity(combined_hash="Z", overall="O", gen="G", repair="fail_fast") -> str:
    return build_identity(
        combined_hash=combined_hash,
        custom_node_fingerprint={"overall_dependency_hash": overall},
        custom_node_generation=gen,
        repair_mode=repair,
        schema_version=DEPENDENCY_MANIFEST_SCHEMA_VERSION,
    )


def _pop_env_deployment_hash():
    """Pop the deployment-hash env var; return the saved value."""
    return os.environ.pop(ENV_DEPLOYMENT_HASH, None)


def _restore_env_deployment_hash(saved):
    if saved is None:
        os.environ.pop(ENV_DEPLOYMENT_HASH, None)
    else:
        os.environ[ENV_DEPLOYMENT_HASH] = saved


# ── 1. Deployment identity chain ─────────────────────────────────────────


class TestDeploymentIdentityChain(unittest.TestCase):
    def setUp(self):
        self.mod = _load_canonical()

    def test_plan_uses_persisted_baked_hash(self):
        """The persisted ``.deployed_state.json`` hash is the authoritative
        value when metadata and env are absent."""
        saved = _pop_env_deployment_hash()
        try:
            with mock.patch.object(
                self.mod, "_read_persisted_deployment_combined_hash", return_value="ab" * 32
            ), _stub_modules({"nodes": _EMPTY_NODES}):
                ident = self.mod._collect_plan_deployment_identity(
                    {}, "", workflow={"1": {"class_type": "A"}}
                )
        finally:
            _restore_env_deployment_hash(saved)
        self.assertEqual(ident["deployment_combined_hash"], "ab" * 32)
        self.assertEqual(ident["deployment_combined_hash_source"], "persisted")

    def test_metadata_and_env_override(self):
        """Metadata beats env; env beats persisted."""
        saved = _pop_env_deployment_hash()
        try:
            os.environ[ENV_DEPLOYMENT_HASH] = "env_val"
            ident = self.mod._collect_plan_deployment_identity(
                {"deployment_combined_hash": "meta_val"}, ""
            )
            self.assertEqual(ident["deployment_combined_hash"], "meta_val")
            self.assertEqual(ident["deployment_combined_hash_source"], "metadata")
            # Empty metadata -> env wins.
            ident2 = self.mod._collect_plan_deployment_identity({}, "")
            self.assertEqual(ident2["deployment_combined_hash"], "env_val")
            self.assertEqual(ident2["deployment_combined_hash_source"], "env")
        finally:
            _restore_env_deployment_hash(saved)

    def test_mutable_diagnostic_files_do_not_change_identity(self):
        """The identity is purely a function of the persisted/env value: two
        calls with different local tree states (host-mirror recomputation is
        per-call) but the same persisted value yield the same hash; a
        different persisted value yields a different hash."""
        saved = _pop_env_deployment_hash()
        try:
            with mock.patch.object(
                self.mod, "_read_persisted_deployment_combined_hash", return_value="p" * 64
            ), _stub_modules({"nodes": _EMPTY_NODES}):
                ident_a = self.mod._collect_plan_deployment_identity(
                    {}, "", workflow={"1": {"class_type": "A"}}
                )
            with mock.patch.object(
                self.mod, "_read_persisted_deployment_combined_hash", return_value="p" * 64
            ), _stub_modules({"nodes": _EMPTY_NODES}):
                ident_b = self.mod._collect_plan_deployment_identity(
                    {}, "", workflow={"1": {"class_type": "A"}}
                )
            self.assertEqual(
                ident_a["deployment_combined_hash"], ident_b["deployment_combined_hash"]
            )
            with mock.patch.object(
                self.mod, "_read_persisted_deployment_combined_hash", return_value="q" * 64
            ), _stub_modules({"nodes": _EMPTY_NODES}):
                ident_c = self.mod._collect_plan_deployment_identity(
                    {}, "", workflow={"1": {"class_type": "A"}}
                )
            self.assertNotEqual(
                ident_a["deployment_combined_hash"], ident_c["deployment_combined_hash"]
            )
        finally:
            _restore_env_deployment_hash(saved)

    def test_absent_deployed_identity_ineligible(self):
        """No metadata, no env, no persisted value -> empty hash,
        ``unavailable`` source, complete False and registry proof incomplete."""
        saved = _pop_env_deployment_hash()
        try:
            with mock.patch.object(
                self.mod, "_read_persisted_deployment_combined_hash", return_value=""
            ), _stub_modules({"nodes": _EMPTY_NODES}):
                ident = self.mod._collect_plan_deployment_identity(
                    {}, "", workflow={"1": {"class_type": "A"}}
                )
        finally:
            _restore_env_deployment_hash(saved)
        self.assertEqual(ident["deployment_combined_hash"], "")
        self.assertEqual(ident["deployment_combined_hash_source"], "unavailable")
        self.assertIs(ident["complete"], False)
        self.assertIs(ident["registry_proof_complete"], False)

    def test_wrong_persisted_identity_causes_parity_mismatch(self):
        """Plan identity X vs snapshot proof Y -> deployment_hash_match False,
        ineligible, named reason."""
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(deployment_combined_hash="X"),
            _full_snapshot_proof(deployment_combined_hash="Y"),
        )
        self.assertIs(result["deployment_hash_match"], False)
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("deployment_hash_mismatch", result["future_fast_path_ineligible_reason"])

    def test_no_request_time_tree_reconstruction_grants_eligibility(self):
        """With empty persisted/env values the plan identity is incomplete
        EVEN IF the diagnostic host mirror recomputes a real hash."""
        saved = _pop_env_deployment_hash()
        try:
            with mock.patch.object(
                self.mod, "_read_persisted_deployment_combined_hash", return_value=""
            ), _stub_modules({"nodes": _EMPTY_NODES}):
                ident = self.mod._collect_plan_deployment_identity(
                    {}, "", workflow={"1": {"class_type": "A"}}
                )
        finally:
            _restore_env_deployment_hash(saved)
        # The host mirror is diagnostic-only and never included in complete.
        self.assertTrue(ident["host_mirror_deployment_combined_hash"])
        self.assertEqual(ident["deployment_combined_hash"], "")
        self.assertIs(ident["complete"], False)


# ── 2. Dependency proof ──────────────────────────────────────────────────


class TestDependencyProof(unittest.TestCase):
    def test_dependency_proof_matches_with_matching_deployment_hash(self):
        """Equal build_identity inputs on both sides -> dependency proof match."""
        dep = _dep_identity()
        plan = _full_plan_identity(
            deployment_combined_hash="Z",
            custom_nodes_generation="G",
            dependency_manifest_identity=dep,
        )
        snap = _full_snapshot_proof(
            deployment_combined_hash="Z",
            custom_nodes_generation="G",
            dependency_manifest_identity=dep,
        )
        result = evaluate_plan_snapshot_parity(plan, snap)
        self.assertIs(result["dependency_proof_match"], True)
        self.assertIs(result["future_fast_path_eligible"], True)

    def test_dependency_input_mismatch_falls_back(self):
        """Different repair_mode or overall fingerprint -> no match."""
        dep_fail_fast = _dep_identity(repair="fail_fast")
        dep_off = _dep_identity(repair="off")
        result = evaluate_plan_snapshot_parity(
            _full_plan_identity(deployment_combined_hash="Z", dependency_manifest_identity=dep_fail_fast),
            _full_snapshot_proof(deployment_combined_hash="Z", dependency_manifest_identity=dep_off),
        )
        self.assertIs(result["dependency_proof_match"], False)
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("dependency_proof_mismatch", result["future_fast_path_ineligible_reason"])

        dep_other_overall = _dep_identity(overall="O-OTHER")
        result2 = evaluate_plan_snapshot_parity(
            _full_plan_identity(deployment_combined_hash="Z", dependency_manifest_identity=dep_fail_fast),
            _full_snapshot_proof(deployment_combined_hash="Z", dependency_manifest_identity=dep_other_overall),
        )
        self.assertIs(result2["dependency_proof_match"], False)


# ── 3. Registry proof (pure) ─────────────────────────────────────────────


class TestWorkflowRegistryProof(unittest.TestCase):
    def test_unrelated_host_only_class_does_not_invalidate(self):
        """A manifest containing only the workflow classes matches; adding an
        unrelated host-only class to the manifest still matches (the evaluator
        only compares classes covered by the plan proof)."""
        proof = _plan_proof_dict(["A"], {"A": "I1"})
        manifest_only_a = _manifest_dict({"A": "I1"})
        self.assertIs(
            evaluate_workflow_registry_parity(proof, manifest_only_a)["workflow_registry_match"],
            True,
        )
        manifest_with_extra = _manifest_dict({"A": "I1", "HostOnly": "I2"})
        self.assertIs(
            evaluate_workflow_registry_parity(proof, manifest_with_extra)["workflow_registry_match"],
            True,
        )

    def test_unrelated_container_only_class_does_not_invalidate(self):
        """Plan proof has {A,B}; manifest has {A,B,C} -> match True."""
        proof = _plan_proof_dict(["A", "B"], {"A": "I1", "B": "I2"})
        manifest = _manifest_dict({"A": "I1", "B": "I2", "C": "I3"})
        result = evaluate_workflow_registry_parity(proof, manifest)
        self.assertIs(result["workflow_registry_match"], True)

    def test_relevant_class_missing_host_side(self):
        """A workflow class absent from the host class mappings -> proof
        incomplete -> parity fails closed (plan_registry_proof_incomplete)."""
        workflow = {"1": {"class_type": "Alpha"}}
        proof = build_workflow_registry_proof(
            workflow, class_mappings={"Other": _NodeBeta}, roots=[str(REPO_ROOT)]
        )
        self.assertIs(proof["complete"], False)
        self.assertEqual(proof["missing_host"], ["Alpha"])
        manifest = build_registry_manifest(
            {"Alpha": _NodeAlpha, "Other": _NodeBeta}, roots=[str(REPO_ROOT)]
        )
        result = evaluate_workflow_registry_parity(proof, manifest)
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "plan_registry_proof_incomplete")

    def test_relevant_class_missing_snapshot_side(self):
        """A complete plan proof referencing a class absent from the snapshot
        manifest -> match False with the class named."""
        proof = build_workflow_registry_proof(
            {"1": {"class_type": "Alpha"}}, {"Alpha": _NodeAlpha}, roots=[str(REPO_ROOT)]
        )
        self.assertIs(proof["complete"], True)
        manifest = build_registry_manifest({"Beta": _NodeBeta}, roots=[str(REPO_ROOT)])
        result = evaluate_workflow_registry_parity(proof, manifest)
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "missing_snapshot_class")
        self.assertIn("Alpha", result["missing_snapshot"])

    def test_relevant_class_identity_mismatch(self):
        """Same class name but a different implementation -> identity drift."""
        proof = build_workflow_registry_proof(
            {"1": {"class_type": "Alpha"}}, {"Alpha": _NodeAlpha}, roots=[str(REPO_ROOT)]
        )
        self.assertIs(proof["complete"], True)
        manifest = build_registry_manifest({"Alpha": _NodeAlphaMismatched}, roots=[str(REPO_ROOT)])
        result = evaluate_workflow_registry_parity(proof, manifest)
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "identity_mismatch")
        self.assertIn("Alpha", result["identity_mismatch"])

    def test_relevant_class_source_identity_mismatch(self):
        """Two classes with the same name+qualname but different module source
        produce different canonical identities."""
        with tempfile.TemporaryDirectory() as td:
            path_a = os.path.join(td, "same_name_mod_a.py")
            path_b = os.path.join(td, "same_name_mod_b.py")
            with open(path_a, "w", encoding="utf-8") as fh:
                fh.write("class SameName:\n    pass\n")
            with open(path_b, "w", encoding="utf-8") as fh:
                fh.write("class SameName:\n    def extra(self):\n        return 1\n")
            try:
                spec_a = importlib.util.spec_from_file_location("same_name_mod_a", path_a)
                assert spec_a is not None and spec_a.loader is not None
                mod_a = importlib.util.module_from_spec(spec_a)
                sys.modules["same_name_mod_a"] = mod_a
                spec_a.loader.exec_module(mod_a)
                spec_b = importlib.util.spec_from_file_location("same_name_mod_b", path_b)
                assert spec_b is not None and spec_b.loader is not None
                mod_b = importlib.util.module_from_spec(spec_b)
                sys.modules["same_name_mod_b"] = mod_b
                spec_b.loader.exec_module(mod_b)
                cls_a = mod_a.SameName
                cls_b = mod_b.SameName
                self.assertEqual(cls_a.__name__, cls_b.__name__)
                self.assertEqual(cls_a.__qualname__, cls_b.__qualname__)
                id_a = class_canonical_identity(cls_a, roots=[td])
                id_b = class_canonical_identity(cls_b, roots=[td])
            finally:
                sys.modules.pop("same_name_mod_a", None)
                sys.modules.pop("same_name_mod_b", None)
            self.assertTrue(id_a)
            self.assertTrue(id_b)
            self.assertNotEqual(id_a, id_b)

    def test_workflow_change_modifies_proof(self):
        """The proof is class-set-based: adding a class changes the proof;
        changing node ids/inputs while keeping the same class set does not
        (documented by design — validate_prompt outcome parity depends only on
        the class set)."""
        mappings = {"Alpha": _NodeAlpha, "Beta": _NodeBeta}
        proof_a = build_workflow_registry_proof(
            {"1": {"class_type": "Alpha"}}, mappings, roots=[str(REPO_ROOT)]
        )
        proof_b = build_workflow_registry_proof(
            {"1": {"class_type": "Alpha"}, "2": {"class_type": "Beta"}},
            mappings, roots=[str(REPO_ROOT)],
        )
        self.assertNotEqual(proof_a["classes"], proof_b["classes"])
        self.assertNotEqual(proof_a["identities"], proof_b["identities"])
        self.assertEqual(proof_b["workflow_class_count"], 2)
        self.assertEqual(
            workflow_class_types({"1": {"class_type": "Alpha"}, "2": {"class_type": "Beta"}}),
            ["Alpha", "Beta"],
        )
        proof_c = build_workflow_registry_proof(
            {
                "10": {"class_type": "Beta", "inputs": {"x": 1}},
                "11": {"class_type": "Alpha"},
                "12": {"class_type": "Beta"},
            },
            mappings, roots=[str(REPO_ROOT)],
        )
        self.assertEqual(proof_b["classes"], proof_c["classes"])
        self.assertEqual(proof_b["identities"], proof_c["identities"])

    def test_gate2_repair_invalidation_preserved(self):
        """Regression pin: a consumed plan-proof is invalidated by repair."""
        self.assertEqual(apply_repair_invalidation(True, "repair_changed"), (False, "repair_changed"))

    def test_malformed_registry_proof_falls_back(self):
        """A non-complete plan proof or a missing snapshot manifest fails closed."""
        result = evaluate_workflow_registry_parity({"bad": True}, _manifest_dict({"A": "I1"}))
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "plan_registry_proof_incomplete")

        result2 = evaluate_workflow_registry_parity(_plan_proof_dict(["A"], {"A": "I1"}), None)
        self.assertIs(result2["workflow_registry_match"], False)
        self.assertEqual(result2["reason"], "snapshot_registry_manifest_unavailable")

    def test_empty_used_class_set_not_accepted(self):
        """An empty workflow class set must never be accepted, whether the
        proof builder rejects it (complete False) or a hand-crafted proof
        claims completeness (explicit empty_workflow_class_set gate)."""
        real_proof = build_workflow_registry_proof({}, {"Alpha": _NodeAlpha})
        self.assertIs(real_proof["complete"], False)
        result = evaluate_workflow_registry_parity(real_proof, _manifest_dict({"Alpha": "I1"}))
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "plan_registry_proof_incomplete")

        crafted = _plan_proof_dict([], {}, complete=True)
        result2 = evaluate_workflow_registry_parity(crafted, _manifest_dict({"Alpha": "I1"}))
        self.assertIs(result2["workflow_registry_match"], False)
        self.assertEqual(result2["reason"], "empty_workflow_class_set")

    def test_legacy_full_validation_still_works_when_proof_unavailable(self):
        """Parity ineligible (no registry proof) -> consumption ineligible;
        parity eligible on all axes incl. workflow_registry_match -> eligible."""
        parity_ineligible = evaluate_plan_snapshot_parity({}, {})
        result = evaluate_plan_validation_consumption(
            parity_ineligible, _full_plan_validation(),
            workflow_hash_match=True, validation_hash_match=True,
            structure_ok=True, outputs_nonempty=True,
        )
        self.assertIs(result["eligible"], False)

        parity_ok = evaluate_plan_snapshot_parity(_full_plan_identity(), _full_snapshot_proof())
        self.assertIs(parity_ok["future_fast_path_eligible"], True)
        result2 = evaluate_plan_validation_consumption(
            parity_ok, _full_plan_validation(),
            workflow_hash_match=True, validation_hash_match=True,
            structure_ok=True, outputs_nonempty=True,
        )
        self.assertIs(result2["eligible"], True)
        self.assertEqual(result2["ineligible_reason"], "")


# ── 4. Path stability ────────────────────────────────────────────────────


class TestIdentityPathStability(unittest.TestCase):
    def test_identity_path_independent(self):
        """A module file copied to a DIFFERENT absolute root (same relative
        layout under its root, same content) yields the identical canonical
        identity — absolute paths never enter the digest."""
        cls = _NodeAlpha
        mod = sys.modules[cls.__module__]
        original = str(mod.__file__)
        identity_before = class_canonical_identity(cls, roots=[str(REPO_ROOT)])
        with tempfile.TemporaryDirectory() as td:
            mirror_root = os.path.join(td, "mirror_root")
            tmp_path = os.path.join(mirror_root, "tests", "test_step3_final_parity.py")
            os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
            shutil.copyfile(original, tmp_path)
            try:
                mod.__file__ = tmp_path
                identity_after = class_canonical_identity(cls, roots=[mirror_root])
            finally:
                mod.__file__ = original
        self.assertTrue(identity_before)
        self.assertTrue(identity_after)
        self.assertEqual(identity_before, identity_after)

    def test_identity_sensitive_to_content(self):
        """Any change to the module file content flips the identity even when
        the root-relative logical path is unchanged."""
        cls = _NodeAlpha
        mod = sys.modules[cls.__module__]
        original = str(mod.__file__)
        identity_original = class_canonical_identity(cls, roots=[str(REPO_ROOT)])
        with tempfile.TemporaryDirectory() as td:
            mirror_root = os.path.join(td, "mirror_root")
            tmp_path = os.path.join(mirror_root, "tests", "test_step3_final_parity.py")
            os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
            shutil.copyfile(original, tmp_path)
            with open(tmp_path, "a", encoding="utf-8") as fh:
                fh.write("\n# content-tamper marker\n")
            try:
                mod.__file__ = tmp_path
                identity_modified = class_canonical_identity(cls, roots=[mirror_root])
            finally:
                mod.__file__ = original
        self.assertTrue(identity_original)
        self.assertTrue(identity_modified)
        self.assertNotEqual(identity_original, identity_modified)


# ── 5. Cross-file parity ─────────────────────────────────────────────────


class TestCrossFileParity(unittest.TestCase):
    def test_evaluate_plan_snapshot_parity_eligible_with_workflow_proof(self):
        """Full synthetic fixture: complete plan workflow proof matching the
        snapshot manifest -> eligible on the workflow-relevant axis, with the
        legacy full fingerprint still computed as diagnostic."""
        result = evaluate_plan_snapshot_parity(_full_plan_identity(), _full_snapshot_proof())
        self.assertIs(result["workflow_registry_match"], True)
        self.assertIs(result["registry_parity_reason"], "")
        self.assertIs(result["future_fast_path_eligible"], True)
        self.assertEqual(result["future_fast_path_ineligible_reason"], "")
        self.assertIs(result["registry_fingerprint_match"], True)

    def test_parity_diagnostics_format(self):
        """format_registry_parity_line renders the exact prefix and the
        workflow_registry_match flag."""
        result = evaluate_workflow_registry_parity(
            _plan_proof_dict(["A"], {"A": "I1"}), _manifest_dict({"A": "I1"})
        )
        line = format_registry_parity_line(result)
        self.assertTrue(line.startswith("[v2.plan_proof.registry] workflow_class_count="))
        self.assertIn("workflow_registry_match=1", line)

        mismatch = evaluate_workflow_registry_parity(
            _plan_proof_dict(["A"], {"A": "I1"}), _manifest_dict({"A": "I2"})
        )
        self.assertIn("workflow_registry_match=0", format_registry_parity_line(mismatch))


if __name__ == "__main__":
    unittest.main()
