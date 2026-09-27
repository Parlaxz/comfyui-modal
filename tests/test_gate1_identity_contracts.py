"""Focused Gate 1 identity/control-plane contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from comfymodal_runtime.contracts import (
    DEPLOYMENT_HASH_NAMESPACE,
    DeploymentIdentity,
)
from comfymodal_runtime.deployment_spec import (
    build_canonical_boundary_identity,
    validate_canonical_boundary_identity,
)
from tools.v2_control import cli


class TestCanonicalDeploymentIdentity(unittest.TestCase):
    def test_namespace_and_compatibility_alias_are_explicit(self) -> None:
        identity = build_canonical_boundary_identity(
            foundation_inputs={"foundation": "f"},
            dependency_inputs={"dependency": "d"},
            accelerator_inputs={"accelerator": "a"},
            source_inputs={"source": "s"},
            late_config_inputs={"late": "l"},
        )
        validate_canonical_boundary_identity(identity)
        self.assertEqual(identity.hash_namespace, DEPLOYMENT_HASH_NAMESPACE)
        self.assertEqual(identity.combined_hash, identity.deployment)
        self.assertEqual(identity.to_dict()["schema_version"], 2)

    def test_deployment_identity_alias_can_be_bound_to_canonical_hash(self) -> None:
        source = DeploymentIdentity(
            runtime_hash="runtime",
            dependency_hash="dependency",
            custom_node_hash="custom",
        )
        canonical_hash = "canonical-deployment-hash"
        bound = source.with_deployment_hash(canonical_hash)
        self.assertEqual(bound.combined_hash, canonical_hash)
        self.assertEqual(bound.to_dict()["hash_namespace"], DEPLOYMENT_HASH_NAMESPACE)

    def test_incomplete_canonical_identity_is_rejected(self) -> None:
        identity = build_canonical_boundary_identity(
            foundation_inputs={"foundation": "f"},
            dependency_inputs={"dependency": "d"},
            accelerator_inputs={"accelerator": "a"},
            source_inputs={"source": "s"},
            late_config_inputs={"late": "l"},
        )
        identity = replace(identity, foundation="")
        with self.assertRaisesRegex(ValueError, "canonical identity incomplete"):
            validate_canonical_boundary_identity(identity)


class TestV2ctlManifestVersioning(unittest.TestCase):
    def test_schema_one_manifest_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / ".v2ctl" / "deployments"
            directory.mkdir(parents=True)
            (directory / "deploy_old.json").write_text(
                json.dumps({"schema_version": 1, "deploy_fingerprint": "old"}),
                encoding="utf-8",
            )
            self.assertIsNone(cli.latest_deployment_manifest(root))


if __name__ == "__main__":
    unittest.main()
