"""Batch C1 — immutable plan/snapshot deployment identity.

Invariant under test: the plan identity of an ALREADY DEPLOYED runtime must
not change merely because a concurrent local worker regenerated the mutable
``.baked_custom_node_deps/custom_node_deps_baked.json`` artifact.  Once a
deployment freezes its identity record (``.deployed_state.json``, written by
``tools/record_deployment_identity.py`` from the container readback at deploy
time), host plan construction derives ``custom_nodes_generation``,
``overall_dependency_hash`` and the dependency-manifest identity from that
deploy-frozen record ONLY.  A new explicit deployment freezes a new identity.
A missing/corrupt/internally-inconsistent frozen record FAILS CLOSED (no
false fast-path parity) with a named diagnostic instead of silently
substituting the mutable baked manifest.

Scenarios: A frozen-A+baked-A -> plan A; B baked regenerated to B after
deploy -> plans still A; C new deployment -> plans carry B; D missing frozen
identity -> fail closed; E dependency identity in lockstep with the frozen
generation; F deployment_combined_hash precedence unchanged; G no remote I/O
during plan building.

All tests are local (no Modal, no network, no ComfyUI imports).  The frozen
record and the baked manifest are materialized in temporary directories and
the module-level path constants are patched.
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
    evaluate_plan_snapshot_parity,
)
from comfymodal_runtime.dependency_manifest import (
    DEPENDENCY_MANIFEST_SCHEMA_VERSION,
    build_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_DEPLOYMENT_HASH = "COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"


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


_EMPTY_NODES = types.ModuleType("nodes")
"""Stub with no ``NODE_CLASS_MAPPINGS``: registry fingerprint stays empty."""


class _stub_modules:
    """Context manager installing module stubs into sys.modules."""

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


class _ForbidRemoteImports:
    """sys.meta_path finder raising if plan building imports any Modal/remote
    module (remote I/O is prohibited per request)."""

    _FORBIDDEN_LEAVES = ("modal", "modal_client", "modal_transport", "modal_app")

    def __enter__(self):
        self._saved = list(sys.meta_path)
        sys.meta_path.insert(0, self)
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.meta_path[:] = self._saved
        return False

    def find_spec(self, name, path=None, target=None):
        leaf = name.rsplit(".", 1)[-1]
        if leaf in self._FORBIDDEN_LEAVES:
            raise AssertionError(f"remote I/O module imported during plan building: {name}")
        return None


def _dep_identity(dep="D_A", gen="gen-A", overall="overall-A", repair="fail_fast") -> str:
    return build_identity(
        combined_hash=dep,
        custom_node_fingerprint={"overall_dependency_hash": overall},
        custom_node_generation=gen,
        repair_mode=repair,
        schema_version=DEPENDENCY_MANIFEST_SCHEMA_VERSION,
    )


_COMPLETE_REGISTRY_PROOF = {
    "schema_version": 1,
    "workflow_class_count": 1,
    "classes": ["A"],
    "identities": {"A": "ID-A"},
    "missing_host": [],
    "unresolved_identity": [],
    "complete": True,
}

_COMPLETE_REGISTRY_MANIFEST = {
    "schema_version": 1,
    "class_count": 1,
    "classes": {"A": "ID-A"},
    "incomplete_classes": [],
}


def _snapshot_proof(dep, gen, overall):
    """A complete, valid frozen snapshot proof for the given deployment."""
    return {
        "schema_version": DEPLOYMENT_PROOF_SCHEMA_VERSION,
        "deployment_combined_hash": dep,
        "custom_nodes_generation": gen,
        "registry_fingerprint": "fp",
        "dependency_manifest_identity": _dep_identity(dep, gen, overall),
        "registry_manifest": dict(_COMPLETE_REGISTRY_MANIFEST),
        "complete": True,
        "valid": True,
    }


class ImmutablePlanIdentityBase(unittest.TestCase):
    def setUp(self):
        self.mod = _load_canonical()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.frozen_path = os.path.join(self._tmp.name, ".deployed_state.json")
        self.baked_path = os.path.join(self._tmp.name, "custom_node_deps_baked.json")
        self.saved_env = os.environ.get(ENV_DEPLOYMENT_HASH)
        self._patchers = [
            mock.patch.object(self.mod, "_DEPLOY_STATE_JSON_LOCAL", self.frozen_path),
            mock.patch.object(self.mod, "_BAKED_CUSTOM_NODE_DEPS_LOCAL", self.baked_path),
            mock.patch.object(self.mod, "_compute_host_deployment_combined_hash", return_value=""),
            mock.patch(
                "comfymodal_runtime.registry_proof.build_workflow_registry_proof",
                return_value=dict(_COMPLETE_REGISTRY_PROOF),
            ),
        ]
        for patcher in self._patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        if self.saved_env is None:
            os.environ.pop(ENV_DEPLOYMENT_HASH, None)
        else:
            os.environ[ENV_DEPLOYMENT_HASH] = self.saved_env

    def _write_frozen(self, **fields):
        with open(self.frozen_path, "w", encoding="utf-8") as fh:
            json.dump(fields, fh, indent=2, sort_keys=True)

    def _write_baked(self, gen="", overall=""):
        with open(self.baked_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "schema_version": 2,
                    "production_custom_node_generation": gen,
                    "overall_dependency_hash": overall,
                },
                fh,
                indent=2,
                sort_keys=True,
            )

    def _collect(self, metadata=None):
        with _stub_modules({"nodes": _EMPTY_NODES}):
            return self.mod._collect_plan_deployment_identity(
                dict(metadata or {}), "", workflow={"1": {"class_type": "A"}}
            )

    def _eligible_with(self, ident, proof):
        return evaluate_plan_snapshot_parity(ident, proof)["future_fast_path_eligible"]


class TestADeploymentFrozenIdentity(ImmutablePlanIdentityBase):
    def test_plan_carries_deploy_frozen_identity(self):
        """A: deployment identity A + baked manifest A -> plan carries A."""
        self._write_frozen(
            deployment_combined_hash="D_A",
            custom_nodes_generation="gen-A",
            overall_dependency_hash="overall-A",
        )
        self._write_baked(gen="gen-A", overall="overall-A")
        ident = self._collect()
        self.assertEqual(ident["deployment_combined_hash"], "D_A")
        self.assertEqual(ident["deployment_combined_hash_source"], "persisted")
        self.assertEqual(ident["custom_nodes_generation"], "gen-A")
        self.assertIs(ident["deployment_identity_frozen"], True)
        self.assertEqual(ident["deployment_identity_fail_closed_reason"], "")
        self.assertEqual(
            ident["dependency_manifest_identity"],
            _dep_identity("D_A", "gen-A", "overall-A"),
        )
        self.assertIs(ident["complete"], True)
        self.assertTrue(self._eligible_with(ident, _snapshot_proof("D_A", "gen-A", "overall-A")))


class TestBBakedRegenerationImmutable(ImmutablePlanIdentityBase):
    def test_baked_regeneration_does_not_change_plan_identity(self):
        """B: after deployment, mutate/regenerate baked manifest to B while
        deployed state remains A -> plans STILL carry A."""
        self._write_frozen(
            deployment_combined_hash="D_A",
            custom_nodes_generation="gen-A",
            overall_dependency_hash="overall-A",
        )
        self._write_baked(gen="gen-A", overall="overall-A")
        ident_a = self._collect()
        # A concurrent worker regenerates the mutable baked manifest AFTER
        # the deployment froze its identity.
        self._write_baked(gen="gen-B", overall="overall-B")
        ident_b = self._collect()
        self.assertEqual(ident_b["deployment_combined_hash"], "D_A")
        self.assertEqual(ident_b["custom_nodes_generation"], "gen-A")
        self.assertNotEqual(ident_b["custom_nodes_generation"], "gen-B")
        self.assertEqual(
            ident_b["dependency_manifest_identity"], ident_a["dependency_manifest_identity"]
        )
        self.assertEqual(
            ident_b["dependency_manifest_identity"],
            _dep_identity("D_A", "gen-A", "overall-A"),
        )
        self.assertNotEqual(
            ident_b["dependency_manifest_identity"],
            _dep_identity("D_A", "gen-B", "overall-B"),
        )
        self.assertIs(ident_b["complete"], True)
        # Parity with the ORIGINAL deployment proof is preserved.
        self.assertTrue(self._eligible_with(ident_b, _snapshot_proof("D_A", "gen-A", "overall-A")))

    def test_baked_manifest_deletion_does_not_change_plan_identity(self):
        """Even DELETING the baked manifest cannot change the identity of an
        already-deployed runtime."""
        self._write_frozen(
            deployment_combined_hash="D_A",
            custom_nodes_generation="gen-A",
            overall_dependency_hash="overall-A",
        )
        self._write_baked(gen="gen-A", overall="overall-A")
        self._collect()
        os.remove(self.baked_path)
        ident = self._collect()
        self.assertEqual(ident["custom_nodes_generation"], "gen-A")
        self.assertEqual(
            ident["dependency_manifest_identity"],
            _dep_identity("D_A", "gen-A", "overall-A"),
        )
        self.assertIs(ident["complete"], True)


class TestCNewDeploymentNewIdentity(ImmutablePlanIdentityBase):
    def test_new_explicit_deployment_establishes_new_identity(self):
        """C: a new explicit deployment freezes B -> plans now carry B."""
        self._write_frozen(
            deployment_combined_hash="D_A",
            custom_nodes_generation="gen-A",
            overall_dependency_hash="overall-A",
        )
        self._write_baked(gen="gen-B", overall="overall-B")
        ident_a = self._collect()
        # New deployment: container readback freezes B.
        self._write_frozen(
            deployment_combined_hash="D_B",
            custom_nodes_generation="gen-B",
            overall_dependency_hash="overall-B",
        )
        ident_b = self._collect()
        self.assertEqual(ident_b["deployment_combined_hash"], "D_B")
        self.assertEqual(ident_b["custom_nodes_generation"], "gen-B")
        self.assertEqual(
            ident_b["dependency_manifest_identity"],
            _dep_identity("D_B", "gen-B", "overall-B"),
        )
        self.assertIs(ident_b["complete"], True)
        self.assertTrue(self._eligible_with(ident_b, _snapshot_proof("D_B", "gen-B", "overall-B")))
        self.assertFalse(self._eligible_with(ident_b, _snapshot_proof("D_A", "gen-A", "overall-A")))
        self.assertNotEqual(
            ident_a["deployment_combined_hash"], ident_b["deployment_combined_hash"]
        )


class TestDFailClosedMissingFrozenIdentity(ImmutablePlanIdentityBase):
    def test_missing_frozen_generation_fails_closed(self):
        """D1: record with deployment hash but no frozen generation -> fail
        closed; the mutable baked manifest is NOT silently substituted."""
        self._write_frozen(deployment_combined_hash="D_A")
        self._write_baked(gen="gen-X", overall="overall-X")
        ident = self._collect()
        self.assertEqual(ident["deployment_combined_hash"], "D_A")
        self.assertEqual(ident["custom_nodes_generation"], "")
        self.assertEqual(ident["dependency_manifest_identity"], "")
        self.assertIs(ident["complete"], False)
        self.assertEqual(
            ident["deployment_identity_fail_closed_reason"],
            "deploy_frozen_custom_nodes_generation_missing",
        )
        parity = evaluate_plan_snapshot_parity(
            ident, _snapshot_proof("D_A", "gen-X", "overall-X")
        )
        self.assertIs(parity["future_fast_path_eligible"], False)
        self.assertIn("plan_identity_incomplete", parity["future_fast_path_ineligible_reason"])

    def test_missing_frozen_dependency_hash_fails_closed(self):
        """D2: record with generation but no frozen dependency hash -> fail
        closed (no dependency identity, plan incomplete)."""
        self._write_frozen(
            deployment_combined_hash="D_A",
            custom_nodes_generation="gen-A",
        )
        self._write_baked(gen="gen-B", overall="overall-B")
        ident = self._collect()
        self.assertEqual(ident["custom_nodes_generation"], "gen-A")
        self.assertEqual(ident["dependency_manifest_identity"], "")
        self.assertIs(ident["complete"], False)
        self.assertEqual(
            ident["deployment_identity_fail_closed_reason"],
            "deploy_frozen_overall_dependency_hash_missing",
        )
        self.assertFalse(self._eligible_with(ident, _snapshot_proof("D_A", "gen-A", "overall-A")))

    def test_corrupt_frozen_record_fails_closed(self):
        """D3: unreadable/corrupt frozen record -> no identity, no false
        fast-path parity."""
        with open(self.frozen_path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self._write_baked(gen="gen-X", overall="overall-X")
        ident = self._collect()
        self.assertEqual(ident["deployment_combined_hash"], "")
        self.assertEqual(ident["deployment_combined_hash_source"], "unavailable")
        self.assertIs(ident["complete"], False)
        self.assertFalse(self._eligible_with(ident, _snapshot_proof("", "gen-X", "overall-X")))


class TestEDependencyIdentityLockstep(ImmutablePlanIdentityBase):
    def test_dependency_identity_lockstep_with_frozen_generation(self):
        """E: dependency identity stays in lockstep with the custom-node
        generation that belonged to that deployment."""
        self._write_frozen(
            deployment_combined_hash="D_A",
            custom_nodes_generation="gen-A",
            overall_dependency_hash="overall-A",
        )
        self._write_baked(gen="gen-B", overall="overall-B")
        ident = self._collect()
        # Dependency identity follows the FROZEN (generation, overall) pair.
        self.assertEqual(
            ident["dependency_manifest_identity"],
            _dep_identity("D_A", "gen-A", "overall-A"),
        )
        # New deployment moves the pair together; identity follows in lockstep.
        self._write_frozen(
            deployment_combined_hash="D_B",
            custom_nodes_generation="gen-B",
            overall_dependency_hash="overall-B",
        )
        ident_b = self._collect()
        self.assertEqual(
            ident_b["dependency_manifest_identity"],
            _dep_identity("D_B", "gen-B", "overall-B"),
        )
        self.assertNotEqual(
            ident["dependency_manifest_identity"], ident_b["dependency_manifest_identity"]
        )
        # A stale baked manifest can never decouple generation and dependency
        # identity from the frozen record.
        self._write_baked(gen="gen-Z", overall="overall-Z")
        ident_c = self._collect()
        self.assertEqual(ident_c["custom_nodes_generation"], "gen-B")
        self.assertEqual(
            ident_c["dependency_manifest_identity"],
            _dep_identity("D_B", "gen-B", "overall-B"),
        )


class TestFDeploymentHashChainUnchanged(ImmutablePlanIdentityBase):
    def test_metadata_env_persisted_precedence_preserved(self):
        """F: deployment_combined_hash chain (metadata > env > persisted)
        behavior remains correct; non-persisted sources keep the legacy
        baked-manifest provenance."""
        self._write_frozen(
            deployment_combined_hash="D_PERSISTED",
            custom_nodes_generation="gen-A",
            overall_dependency_hash="overall-A",
        )
        self._write_baked(gen="gen-A", overall="overall-A")
        ident = self._collect({"deployment_combined_hash": "D_META"})
        self.assertEqual(ident["deployment_combined_hash"], "D_META")
        self.assertEqual(ident["deployment_combined_hash_source"], "metadata")
        self.assertIs(ident["deployment_identity_frozen"], False)
        os.environ[ENV_DEPLOYMENT_HASH] = "D_ENV"
        ident2 = self._collect({})
        self.assertEqual(ident2["deployment_combined_hash"], "D_ENV")
        self.assertEqual(ident2["deployment_combined_hash_source"], "env")
        self.assertIs(ident2["deployment_identity_frozen"], False)
        os.environ.pop(ENV_DEPLOYMENT_HASH, None)
        ident3 = self._collect({})
        self.assertEqual(ident3["deployment_combined_hash"], "D_PERSISTED")
        self.assertEqual(ident3["deployment_combined_hash_source"], "persisted")
        self.assertIs(ident3["deployment_identity_frozen"], True)
        self.assertEqual(ident3["custom_nodes_generation"], "gen-A")
        # Legacy semantics: an env/metadata deployment hash keeps sourcing the
        # generation from the baked manifest.
        os.environ[ENV_DEPLOYMENT_HASH] = "D_ENV"
        self._write_baked(gen="gen-LEGACY", overall="overall-LEGACY")
        ident4 = self._collect({})
        self.assertEqual(ident4["custom_nodes_generation"], "gen-LEGACY")
        self.assertEqual(
            ident4["dependency_manifest_identity"],
            _dep_identity("D_ENV", "gen-LEGACY", "overall-LEGACY"),
        )
        os.environ.pop(ENV_DEPLOYMENT_HASH, None)


class TestGNoRemoteIO(ImmutablePlanIdentityBase):
    def test_no_remote_io_in_plan_building(self):
        """G: plan identity collection performs no remote I/O (no Modal,
        transport, or client imports) and still carries the frozen identity."""
        self._write_frozen(
            deployment_combined_hash="D_A",
            custom_nodes_generation="gen-A",
            overall_dependency_hash="overall-A",
        )
        self._write_baked(gen="gen-B", overall="overall-B")
        modal_already = "modal" in sys.modules
        with _ForbidRemoteImports():
            ident = self._collect()
        self.assertEqual(ident["custom_nodes_generation"], "gen-A")
        self.assertIs(ident["complete"], True)
        if not modal_already:
            self.assertNotIn("modal", sys.modules)


class TestDeployBatIdentityRecordExitPropagation(unittest.TestCase):
    """C1 operational gate: deploy_and_run_v2_single.bat must propagate a
    nonzero exit from tools/record_deployment_identity.py instead of silently
    continuing (both deploy branches: V1-already-deployed and concurrent)."""

    def test_record_identity_failure_propagates(self):
        bat = (REPO_ROOT / "deploy_and_run_v2_single.bat").read_text(
            encoding="utf-8", errors="replace"
        )
        lines = bat.splitlines()
        hits = [i for i, ln in enumerate(lines) if "record_deployment_identity.py" in ln]
        self.assertGreaterEqual(len(hits), 2, "record step must exist in both deploy branches")
        for i in hits:
            window = lines[i + 1:i + 6]
            joined = "\n".join(window).lower()
            self.assertIn("if errorlevel 1", joined,
                          f"line {i + 1}: record step must be followed by errorlevel guard")
            self.assertIn("exit /b 1", joined,
                          f"line {i + 1}: guard must exit nonzero")
            self.assertIn("deployment identity record failed", joined,
                          f"line {i + 1}: guard must name the failed step")

    def test_record_identity_tool_writes_frozen_triple(self):
        src = (REPO_ROOT / "tools" / "record_deployment_identity.py").read_text(
            encoding="utf-8", errors="replace"
        )
        for field in ("deployment_combined_hash", "custom_nodes_generation",
                      "overall_dependency_hash"):
            self.assertIn(f'"{field}"', src)
        self.assertIn("empty_overall_dependency_hash", src)
        self.assertIn("container_readback", src)


if __name__ == "__main__":
    unittest.main()
