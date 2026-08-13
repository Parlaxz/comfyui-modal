"""Tests for the Step-1 plan-carried workflow-validation proof.

Covers:
  - build_execution_plan with collect_validation_proof=True carries a
    validation payload (validated flag, sorted outputs, hash binding)
  - invalid workflows fail closed with RuntimeError
  - deterministic payload / hash binding for identical inputs
  - workflow change changes hash binding; validation change changes the
    serialized validation identity only
  - to_dict -> from_dict round trip preserves validation + deployment_identity
  - host/container recompute equality (prompt_sha256 over thawed workflow)
  - deployment identity eligibility (complete only when every component is
    known; never fabricated)
  - compute_registry_fingerprint determinism
  - backward compatibility when the new fields are absent
  - publish_restore_plan default-off contract

All tests are local (no Modal, no paid anything).  ``execution`` and ``nodes``
are stubbed via ``sys.modules`` so the parent-ComfyUI modules are never
imported.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from comfymodal_runtime.contracts import (
    ExecutionPlan,
    VALIDATION_PROOF_SCHEMA_VERSION,
    _thaw,
    compute_registry_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# A small valid 2-node workflow shape (used by most tests).
WORKFLOW_A = {
    "1": {"class_type": "X", "inputs": {}},
    "2": {"class_type": "Y", "inputs": {"a": ["1", 0]}},
}

# Same shape, node "1" carries a different input.
WORKFLOW_B = {
    "1": {"class_type": "X", "inputs": {"steps": 10}},
    "2": {"class_type": "Y", "inputs": {"a": ["1", 0]}},
}


class _DummyNode:
    """Simple stand-in for a NODE_CLASS_MAPPINGS entry."""


_REMOVE = object()
"""Sentinel for ``_stub_modules``: remove the key instead of stubbing it."""


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


def _make_fake_execution(outputs, valid=True, error=None, node_errors=None):
    """Fake ``execution`` module whose validate_prompt is controllable."""
    mod = types.ModuleType("execution")

    async def validate_prompt(prompt_id, prompt, partial_execution_list=None):
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
    """Context manager installing module stubs into sys.modules.

    A value of ``_REMOVE`` pops the key (restoring it afterwards).
    """

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


def _load_workflow_metadata():
    """Load workflow_metadata (container-side recompute source of truth)."""
    spec = importlib.util.spec_from_file_location(
        "workflow_metadata", REPO_ROOT / "workflow_metadata.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["workflow_metadata"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPlanValidationProof(unittest.TestCase):
    def setUp(self):
        self.mod = _load_canonical()

    # ── Payload collection ────────────────────────────────────────────────

    def test_valid_plan_carries_validation_payload(self):
        """A valid plan carries the validation proof with sorted outputs and
        a hash binding to the final dispatch hash."""
        with _stub_modules({
            "execution": _make_fake_execution(["9", "5"]),
            "nodes": _make_fake_nodes(),
        }):
            plan = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        validation = dict(plan.validation)
        self.assertIs(validation["validated"], True)
        # ExecutionPlan freezes list values into tuples; compare the sorted
        # output ids as a list.
        self.assertEqual(list(validation["outputs_to_execute"]), ["5", "9"])
        self.assertEqual(validation["validated_workflow_hash"], plan.workflow_hash)
        self.assertEqual(validation["schema_version"], VALIDATION_PROOF_SCHEMA_VERSION)
        self.assertEqual(validation["source"], "host_validate_prompt")

    def test_invalid_workflow_fails_closed(self):
        """An invalid workflow raises RuntimeError (fail-closed)."""
        with _stub_modules({
            "execution": _make_fake_execution(
                [], valid=False, error={"1": "bad"},
                node_errors={"1": {"errors": [{"message": "bad"}]}},
            ),
            "nodes": _make_fake_nodes(),
        }):
            with self.assertRaises(RuntimeError):
                self.mod.build_execution_plan(
                    dict(WORKFLOW_A), prompt_id="p1", validate=False,
                    collect_validation_proof=True,
                )

    def test_payload_deterministic(self):
        """Identical inputs produce identical payloads and hashes."""
        with _stub_modules({
            "execution": _make_fake_execution(["5", "9"]),
            "nodes": _make_fake_nodes(),
        }):
            plan1 = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
            plan2 = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        self.assertEqual(dict(plan1.validation), dict(plan2.validation))
        self.assertEqual(plan1.workflow_hash, plan2.workflow_hash)

    # ── Hash binding semantics ────────────────────────────────────────────

    def test_workflow_change_changes_hash_binding(self):
        """Different workflows bind different validated_workflow_hashes."""
        with _stub_modules({
            "execution": _make_fake_execution(["5", "9"]),
            "nodes": _make_fake_nodes(),
        }):
            plan_a = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
            plan_b = self.mod.build_execution_plan(
                dict(WORKFLOW_B), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        self.assertNotEqual(plan_a.workflow_hash, plan_b.workflow_hash)
        self.assertEqual(plan_a.validation["validated_workflow_hash"], plan_a.workflow_hash)
        self.assertEqual(plan_b.validation["validated_workflow_hash"], plan_b.workflow_hash)
        self.assertNotEqual(
            plan_a.validation["validated_workflow_hash"],
            plan_b.validation["validated_workflow_hash"],
        )

    def test_validation_change_changes_serialized_identity(self):
        """A validation output-set change alters only the serialized
        validation identity, not the workflow hash."""
        # Step-2: host-side validation is memoized per (workflow hash +
        # deployment identity), so identical builds would reuse the cached
        # payload.  Clear the memo so the distinct fake output sets are
        # actually validated fresh.
        self.mod._PLAN_VALIDATION_MEMO.clear()
        with _stub_modules({
            "execution": _make_fake_execution(["5"]),
            "nodes": _make_fake_nodes(),
        }):
            plan_a = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        self.mod._PLAN_VALIDATION_MEMO.clear()
        with _stub_modules({
            "execution": _make_fake_execution(["5", "9"]),
            "nodes": _make_fake_nodes(),
        }):
            plan_b = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        self.assertEqual(plan_a.workflow_hash, plan_b.workflow_hash)
        self.assertNotEqual(
            plan_a.to_dict()["validation"], plan_b.to_dict()["validation"],
        )

    # ── Serialization / round trip ────────────────────────────────────────

    def test_round_trip_intact(self):
        """to_dict -> from_dict preserves validation + deployment_identity."""
        with _stub_modules({
            "execution": _make_fake_execution(["5", "9"]),
            "nodes": _make_fake_nodes(),
        }):
            plan = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        plan2 = ExecutionPlan.from_dict(plan.to_dict())
        self.assertEqual(dict(plan2.validation), dict(plan.validation))
        self.assertEqual(
            dict(plan2.deployment_identity), dict(plan.deployment_identity),
        )

    def test_container_recompute_matches(self):
        """The container-side recompute over the thawed plan workflow equals
        the host-bound workflow hash (proves host/container equality)."""
        with _stub_modules({
            "execution": _make_fake_execution(["5", "9"]),
            "nodes": _make_fake_nodes(),
        }):
            plan = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        plan2 = ExecutionPlan.from_dict(plan.to_dict())
        wm = _load_workflow_metadata()
        self.assertEqual(wm.prompt_sha256(_thaw(plan2.workflow)), plan2.workflow_hash)
        self.assertEqual(
            plan2.validation["validated_workflow_hash"], plan2.workflow_hash,
        )

    # ── Deployment identity eligibility ───────────────────────────────────

    def test_missing_deployment_identity_ineligible(self):
        """No metadata, no env, no nodes registry, no baked manifest ->
        complete=False and all identity fields empty (never fabricated)."""
        saved_env = os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        try:
            # Step-2: the baked custom-node manifest is the canonical
            # generation source; mock it absent so no generation is available.
            # Step-3: the host deployment-hash mirror would otherwise compute
            # a real value from the local repo; mock it empty so the test
            # proves the ineligible path (no fabricated hash).  The persisted
            # ``.deployed_state.json`` reader is also mocked empty: the on-disk
            # artifact may legitimately exist after a deploy, and this test
            # simulates a host with no persisted deployment identity.
            with mock.patch.object(
                self.mod, "_read_baked_custom_node_manifest", return_value={}
            ), mock.patch.object(
                self.mod, "_compute_host_deployment_combined_hash", return_value=""
            ), mock.patch.object(
                self.mod, "_read_persisted_deployment_combined_hash", return_value=""
            ):
                with _stub_modules({
                    "execution": _make_fake_execution(["5"]),
                    "nodes": _REMOVE,
                }):
                    plan = self.mod.build_execution_plan(
                        dict(WORKFLOW_A), prompt_id="p1", validate=False,
                        collect_validation_proof=True,
                    )
        finally:
            if saved_env is not None:
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = saved_env
        dep = dict(plan.deployment_identity)
        self.assertIs(dep["complete"], False)
        self.assertEqual(dep["deployment_combined_hash"], "")
        self.assertEqual(dep["custom_nodes_generation"], "")
        self.assertEqual(dep["registry_fingerprint"], "")

    def test_deployment_identity_complete_when_all_known(self):
        """Env + baked manifest generation + nodes registry -> complete=True
        and all identity fields populated."""
        saved_env = os.environ.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH")
        os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "dep123"
        try:
            # Step-2: the baked custom-node manifest is the canonical
            # generation source; provide it so the identity is complete.
            with mock.patch.object(
                self.mod, "_read_baked_custom_node_manifest",
                return_value={"production_custom_node_generation": "g1"},
            ):
                with _stub_modules({
                    "execution": _make_fake_execution(["5"]),
                    "nodes": _make_fake_nodes(),
                }):
                    plan = self.mod.build_execution_plan(
                        dict(WORKFLOW_A), prompt_id="p1", validate=False,
                        collect_validation_proof=True,
                    )
        finally:
            if saved_env is None:
                os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
            else:
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = saved_env
        dep = dict(plan.deployment_identity)
        self.assertIs(dep["complete"], True)
        self.assertEqual(dep["deployment_combined_hash"], "dep123")
        self.assertEqual(dep["custom_nodes_generation"], "g1")
        self.assertTrue(dep["registry_fingerprint"])

    # ── Registry fingerprint ──────────────────────────────────────────────

    def test_registry_fingerprint_deterministic(self):
        """compute_registry_fingerprint is deterministic, sensitive to the
        registry, and empty for an empty registry."""
        m1 = {"A": _DummyNode, "B": _DummyNode}
        m2 = {"A": _DummyNode, "C": _DummyNode}
        fp1 = compute_registry_fingerprint(m1)
        self.assertEqual(compute_registry_fingerprint(m1), fp1)
        self.assertNotEqual(compute_registry_fingerprint(m2), fp1)
        self.assertEqual(compute_registry_fingerprint({}), "")

    # ── Backward compatibility / flag defaults ────────────────────────────

    def test_backward_compat_no_validation_fields(self):
        """from_dict without the new fields defaults to empty dicts."""
        base = {
            "schema_version": 1,
            "workflow": dict(WORKFLOW_A),
            "workflow_hash": "abc",
            "source_workflow_hash": "abc",
            "output_node_ids": ["2"],
        }
        plan = ExecutionPlan.from_dict(base)
        self.assertEqual(dict(plan.validation), {})
        self.assertEqual(dict(plan.deployment_identity), {})

    def test_publish_restore_plan_default_off(self):
        """publish_restore_plan_enabled is False by default and True when the
        opt-in flag is truthy."""
        from comfymodal_runtime import execution_seed
        saved = os.environ.get("COMFYMODAL_V2_PUBLISH_RESTORE_PLAN")
        try:
            os.environ.pop("COMFYMODAL_V2_PUBLISH_RESTORE_PLAN", None)
            self.assertIs(execution_seed.publish_restore_plan_enabled(), False)
            os.environ["COMFYMODAL_V2_PUBLISH_RESTORE_PLAN"] = "1"
            self.assertIs(execution_seed.publish_restore_plan_enabled(), True)
        finally:
            if saved is None:
                os.environ.pop("COMFYMODAL_V2_PUBLISH_RESTORE_PLAN", None)
            else:
                os.environ["COMFYMODAL_V2_PUBLISH_RESTORE_PLAN"] = saved


if __name__ == "__main__":
    unittest.main()
