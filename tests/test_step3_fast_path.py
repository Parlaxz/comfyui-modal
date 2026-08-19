"""Tests for the Step-3 plan-validation trust gate (fast path).

Covers:
  - evaluate_plan_validation_consumption: full eligibility matrix
  - parity-derived ineligibility reasons (deployment/generation/registry/
    dependency/stale/incomplete)
  - host deployment-hash provenance chain (env -> persisted -> computed-memo)
  - host validation memoization (identical builds / identity change)
  - apply_repair_invalidation (Oracle Gate 2) and writeback guard
  - no new remote calls in plan-construction paths

All tests are local (no Modal, no paid anything).  ``execution``/``nodes``
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
    VALIDATION_PROOF_SCHEMA_VERSION,
    apply_repair_invalidation,
    evaluate_plan_validation_consumption,
    should_write_validation_cert,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_A = {
    "1": {"class_type": "X", "inputs": {}},
    "2": {"class_type": "Y", "inputs": {"a": ["1", 0]}},
}


class _DummyNode:
    """Simple stand-in for a NODE_CLASS_MAPPINGS entry."""


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
    mod = types.ModuleType("execution")

    async def validate_prompt(prompt_id, prompt, partial_execution_list=None):
        if counter is not None:
            counter[0] += 1
        return (valid, error, outputs, node_errors or {})

    mod.validate_prompt = validate_prompt
    return mod


def _make_fake_nodes(mappings=None):
    mod = types.ModuleType("nodes")
    if mappings is None:
        mappings = {"X": _DummyNode, "Y": _DummyNode}
    mod.NODE_CLASS_MAPPINGS = mappings
    return mod


class _stub_modules:
    def __init__(self, stubs):
        self._stubs = stubs
        self._saved = {}

    def __enter__(self):
        for name, value in self._stubs.items():
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = value
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self._saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return False


def _full_parity(**overrides) -> dict:
    parity = {
        "plan_validation_schema": VALIDATION_PROOF_SCHEMA_VERSION,
        "plan_deployment_complete": True,
        "snapshot_proof_present": True,
        "snapshot_proof_complete": True,
        "snapshot_proof_valid": True,
        "deployment_hash_match": True,
        "custom_nodes_generation_match": True,
        "registry_fingerprint_match": True,
        "workflow_registry_match": True,
        "dependency_proof_match": True,
        "future_fast_path_eligible": True,
        "future_fast_path_ineligible_reason": "",
    }
    parity.update(overrides)
    return parity


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


def _gate(parity=None, plan_validation=None, **kw) -> dict:
    args = dict(
        workflow_hash_match=True,
        validation_hash_match=True,
        structure_ok=True,
        outputs_nonempty=True,
    )
    args.update(kw)
    return evaluate_plan_validation_consumption(
        parity if parity is not None else _full_parity(),
        plan_validation if plan_validation is not None else _full_plan_validation(),
        **args,
    )


class TestConsumptionGate(unittest.TestCase):
    def test_exact_parity_eligible(self):
        result = _gate()
        self.assertIs(result["eligible"], True)
        self.assertEqual(result["ineligible_reason"], "")

    def test_workflow_hash_mismatch_not_consumable(self):
        result = _gate(workflow_hash_match=False)
        self.assertIs(result["eligible"], False)
        self.assertIn("workflow_hash_mismatch", result["ineligible_reason"])

    def test_validation_hash_mismatch(self):
        result = _gate(validation_hash_match=False)
        self.assertIs(result["eligible"], False)
        self.assertIn("validation_hash_mismatch", result["ineligible_reason"])

    def test_unsupported_schema(self):
        result = _gate(plan_validation=_full_plan_validation(schema_version=99))
        self.assertIs(result["eligible"], False)
        self.assertIn("unsupported_validation_schema", result["ineligible_reason"])

    def test_not_validated(self):
        result = _gate(plan_validation=_full_plan_validation(validated=False))
        self.assertIs(result["eligible"], False)
        self.assertIn("validation_not_validated", result["ineligible_reason"])

    def test_empty_outputs(self):
        result = _gate(outputs_nonempty=False)
        self.assertIs(result["eligible"], False)
        self.assertIn("empty_outputs", result["ineligible_reason"])

    def test_structure_failed(self):
        result = _gate(structure_ok=False)
        self.assertIs(result["eligible"], False)
        self.assertIn("structure_check_failed", result["ineligible_reason"])

    def test_deployment_mismatch_parity(self):
        result = _gate(parity=_full_parity(deployment_hash_match=False, future_fast_path_eligible=False,
                                           future_fast_path_ineligible_reason="deployment_hash_mismatch"))
        self.assertIs(result["eligible"], False)
        self.assertIn("deployment_hash_mismatch", result["ineligible_reason"])

    def test_generation_mismatch(self):
        result = _gate(parity=_full_parity(custom_nodes_generation_match=False, future_fast_path_eligible=False,
                                           future_fast_path_ineligible_reason="custom_nodes_generation_mismatch"))
        self.assertIs(result["eligible"], False)
        self.assertIn("custom_nodes_generation_mismatch", result["ineligible_reason"])

    def test_workflow_registry_mismatch(self):
        result = _gate(parity=_full_parity(workflow_registry_match=False, future_fast_path_eligible=False,
                                           future_fast_path_ineligible_reason="workflow_registry_mismatch"))
        self.assertIs(result["eligible"], False)
        self.assertIn("workflow_registry_mismatch", result["ineligible_reason"])

    def test_dependency_mismatch(self):
        result = _gate(parity=_full_parity(dependency_proof_match=False, future_fast_path_eligible=False,
                                           future_fast_path_ineligible_reason="dependency_proof_mismatch"))
        self.assertIs(result["eligible"], False)
        self.assertIn("dependency_proof_mismatch", result["ineligible_reason"])

    def test_stale_proof(self):
        result = _gate(parity=_full_parity(snapshot_proof_valid=False, future_fast_path_eligible=False,
                                           future_fast_path_ineligible_reason="snapshot_proof_invalid_or_unsupported"))
        self.assertIs(result["eligible"], False)
        self.assertIn("snapshot_proof_invalid_or_unsupported", result["ineligible_reason"])

    def test_incomplete_plan_identity(self):
        result = _gate(parity=_full_parity(plan_deployment_complete=False, future_fast_path_eligible=False,
                                           future_fast_path_ineligible_reason="plan_identity_incomplete"))
        self.assertIs(result["eligible"], False)
        self.assertIn("plan_identity_incomplete", result["ineligible_reason"])

    def test_missing_plan_validation(self):
        result = _gate(plan_validation={})
        self.assertIs(result["eligible"], False)
        self.assertIn("unsupported_validation_schema", result["ineligible_reason"])
        self.assertIn("validation_not_validated", result["ineligible_reason"])

    def test_fallback_path_preserved(self):
        """Every single-reason failure maps to an explicit ineligible reason
        (the legacy fallback path is driven by eligible=False)."""
        for kwargs in (
            {"workflow_hash_match": False},
            {"validation_hash_match": False},
            {"structure_ok": False},
            {"outputs_nonempty": False},
        ):
            result = _gate(**kwargs)
            self.assertIs(result["eligible"], False, kwargs)


class TestRepairAndWritebackHelpers(unittest.TestCase):
    def test_apply_repair_invalidation_consumed(self):
        self.assertEqual(apply_repair_invalidation(True, "repair_changed"), (False, "repair_changed"))

    def test_apply_repair_invalidation_not_consumed(self):
        self.assertEqual(apply_repair_invalidation(False, "repair_changed"), (False, "repair_changed"))

    def test_writeback_guard_false_when_not_scheduled(self):
        self.assertIs(should_write_validation_cert(False, True), False)
        self.assertIs(should_write_validation_cert(False, False), False)

    def test_writeback_guard_false_without_preflight(self):
        self.assertIs(should_write_validation_cert(True, False), False)

    def test_writeback_guard_true_only_full(self):
        self.assertIs(should_write_validation_cert(True, True), True)


class TestHostDeploymentHashChain(unittest.TestCase):
    def setUp(self):
        self.mod = _load_canonical()
        self.mod._HOST_DEPLOYMENT_HASH_COMPUTED = None
        self.saved_env = os.environ.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH")

    def tearDown(self):
        if self.saved_env is None:
            os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        else:
            os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = self.saved_env
        self.mod._HOST_DEPLOYMENT_HASH_COMPUTED = None

    def test_env_wins(self):
        os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "env_hash"
        ident = self.mod._collect_plan_deployment_identity({}, "")
        self.assertEqual(ident["deployment_combined_hash"], "env_hash")

    def test_persisted_file_when_env_unset(self):
        os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, ".deployed_state.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"deployment_combined_hash": "persisted_hash"}, f)
            with mock.patch.object(self.mod, "_read_persisted_deployment_combined_hash",
                                   return_value="persisted_hash"):
                ident = self.mod._collect_plan_deployment_identity({}, "")
        self.assertEqual(ident["deployment_combined_hash"], "persisted_hash")

    def test_computed_memo_runs_once(self):
        os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        fake_identity = types.SimpleNamespace(combined_hash="combined1")
        calls = [0]

        def fake_build(runtime_root, *, dependency_hash="", custom_node_paths=None):
            calls[0] += 1
            return fake_identity

        fake_shape = types.SimpleNamespace(identity_payload=lambda: {"runtime_shape": "rs1"})
        with mock.patch.object(self.mod, "_read_persisted_deployment_combined_hash", return_value=""), \
             mock.patch("comfymodal_runtime.deployment_spec.build_deployment_identity", fake_build), \
             mock.patch("comfymodal_runtime.runtime_shape.runtime_shape_config",
                        return_value=fake_shape):
            h1 = self.mod._compute_host_deployment_combined_hash()
            h2 = self.mod._compute_host_deployment_combined_hash()
        self.assertEqual(h1, h2)
        self.assertTrue(h1)
        self.assertEqual(calls[0], 1)

    def test_host_deployment_hash_never_per_request_scan(self):
        os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        calls = [0]
        fake_identity = types.SimpleNamespace(combined_hash="combined1")

        def fake_build(runtime_root, *, dependency_hash="", custom_node_paths=None):
            calls[0] += 1
            return fake_identity

        fake_shape = types.SimpleNamespace(identity_payload=lambda: {"runtime_shape": "rs1"})
        with mock.patch.object(self.mod, "_read_persisted_deployment_combined_hash", return_value=""), \
             mock.patch("comfymodal_runtime.deployment_spec.build_deployment_identity", fake_build), \
             mock.patch("comfymodal_runtime.runtime_shape.runtime_shape_config",
                        return_value=fake_shape):
            self.mod._compute_host_deployment_combined_hash()
            self.mod._compute_host_deployment_combined_hash()
            self.mod._compute_host_deployment_combined_hash()
        self.assertEqual(calls[0], 1)


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

    def test_memo_hit_identical_request(self):
        counter = [0]
        with _stub_modules({
            "execution": _make_fake_execution(["5", "9"], counter=counter),
            "nodes": _make_fake_nodes(),
        }):
            self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
            self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True,
            )
        self.assertEqual(counter[0], 1)

    def test_memo_miss_on_identity_change(self):
        counter = [0]
        saved = os.environ.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH")
        try:
            with _stub_modules({
                "execution": _make_fake_execution(["5", "9"], counter=counter),
                "nodes": _make_fake_nodes(),
            }):
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "dep_a"
                self.mod.build_execution_plan(
                    dict(WORKFLOW_A), prompt_id="p1", validate=False,
                    collect_validation_proof=True,
                )
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "dep_b"
                self.mod.build_execution_plan(
                    dict(WORKFLOW_A), prompt_id="p1", validate=False,
                    collect_validation_proof=True,
                )
        finally:
            if saved is None:
                os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
            else:
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = saved
        self.assertEqual(counter[0], 2)

    def test_no_new_remote_call_plan_construction(self):
        """Gate helpers + hash chain complete with only stdlib (no modal)."""
        modal_already = "modal" in sys.modules
        result = _gate()
        self.assertIs(result["eligible"], True)
        _hash = self.mod._compute_host_deployment_combined_hash()
        self.assertIsInstance(_hash, str)
        if not modal_already:
            self.assertNotIn("modal", sys.modules)


if __name__ == "__main__":
    unittest.main()
