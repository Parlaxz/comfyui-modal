"""Focused tests for the schema-v3 semantic certificate identity.

Covers:
  1. Round-trip: ``_compute_v2_cert_identity`` -> ``set_snapshot_certificate``
     validates (the recompute must stay byte-identical to the computation).
  2. Deployment-only difference yields the SAME identity (the cutover: the
     churning deployment hash is provenance, not skip key).
  3. Any semantic digest difference (registry / exec-env / config) yields a
     different identity (fail closed).
  4. ``_validate_cert_dict_payload`` decides on semantic components only;
     stored provenance extras are ignored.
  5. Digest helpers are deterministic, cached, and total on garbage input.
  6. Legacy schema-v2 certificates still validate via the legacy branch.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.fast_unit

import comfymodal_runtime.modal_app as modal_app
from comfymodal_runtime.modal_app import (
    _compute_v2_cert_identity,
    _validate_cert_dict_payload,
    execution_environment_digest,
    registry_digest_from_proof,
    runtime_config_digest,
)
from comfymodal_runtime.runtime_bootstrap import BootstrapState


_SEMANTIC = {
    "registry_digest": "reg123",
    "exec_env_digest": "env456",
    "config_digest": "cfg789",
}


def _v3_cert_dict(identity: str, components: dict) -> dict:
    return {
        "schema_version": 3,
        "identity": identity,
        "preflight_ok": True,
        "outputs_to_execute": ["7", "9"],
        "node_errors": {},
        "identity_components": dict(components),
    }


def test_v3_round_trip_validates() -> None:
    identity, components = _compute_v2_cert_identity(
        "wf1", repair_mode="fail_fast", custom_nodes_generation="gen1", **_SEMANTIC  # type: ignore[arg-type]
    )
    state = BootstrapState()
    state.set_snapshot_certificate(_v3_cert_dict(identity, components))
    assert state.snapshot_cert_valid is True
    assert state.snapshot_cert_identity == identity


def test_deployment_only_difference_keeps_identity() -> None:
    kwargs: dict = {"repair_mode": "fail_fast", "custom_nodes_generation": "gen1"}
    kwargs.update(_SEMANTIC)
    with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", "deploy-aaa"):
        id_a, _ = _compute_v2_cert_identity("wf1", **kwargs)  # type: ignore[arg-type]
    with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", "deploy-bbb-dirty-tree"):
        id_b, _ = _compute_v2_cert_identity("wf1", **kwargs)  # type: ignore[arg-type]
    assert id_a == id_b


def test_semantic_differences_bust_identity() -> None:
    base: dict = {"repair_mode": "fail_fast", "custom_nodes_generation": "gen1"}
    base.update(_SEMANTIC)
    identity, _ = _compute_v2_cert_identity("wf1", **base)  # type: ignore[arg-type]
    for key in ("registry_digest", "exec_env_digest", "config_digest"):
        varied = dict(base)
        varied[key] = "CHANGED"
        other, _ = _compute_v2_cert_identity("wf1", **varied)  # type: ignore[arg-type]
        assert other != identity, key
    other_wf, _ = _compute_v2_cert_identity("wf2", **base)  # type: ignore[arg-type]
    assert other_wf != identity


def test_validator_ignores_provenance_extras() -> None:
    identity, components = _compute_v2_cert_identity(
        "wf1", repair_mode="fail_fast", custom_nodes_generation="gen1", **_SEMANTIC  # type: ignore[arg-type]
    )
    payload = _v3_cert_dict(identity, components)
    payload["deployment_hash"] = "deploy-zzz-provenance"
    payload["identity_components"]["deployment_hash"] = "deploy-old"
    # Validator iterates EXPECTED keys only: provenance drift never busts.
    result = _validate_cert_dict_payload(payload, identity, expected_components=dict(components))
    assert result is not None
    assert result["outputs_to_execute"] == ["7", "9"]


def test_validator_rejects_semantic_mismatch() -> None:
    identity, components = _compute_v2_cert_identity(
        "wf1", repair_mode="fail_fast", custom_nodes_generation="gen1", **_SEMANTIC  # type: ignore[arg-type]
    )
    payload = _v3_cert_dict(identity, components)
    expected = dict(components)
    expected["registry_digest"] = "DIFFERENT"
    assert _validate_cert_dict_payload(payload, identity, expected_components=expected) is None


def test_registry_digest_deterministic_and_total() -> None:
    proof = {"complete": True, "identities": {"B": "b1", "A": "a1"}}
    first = registry_digest_from_proof(proof)
    assert first
    assert registry_digest_from_proof({"complete": True, "identities": {"A": "a1", "B": "b1"}}) == first
    assert registry_digest_from_proof({"complete": False, "identities": {"A": "a1", "B": "b1"}}) != first
    for garbage in (None, {}, {"identities": {}}, {"identities": "nope"}, "x"):
        assert registry_digest_from_proof(garbage) == ""


def test_exec_env_digest_deterministic_and_cached() -> None:
    modal_app._EXEC_ENV_DIGEST_CACHE.pop("digest", None)
    first = execution_environment_digest()
    assert first
    assert execution_environment_digest() == first
    # Cache hit path: digest returned without touching the filesystem.
    with patch("pathlib.Path.glob", side_effect=AssertionError("must use cache")):
        assert execution_environment_digest() == first


def test_runtime_config_digest_deterministic() -> None:
    modal_app._RUNTIME_CONFIG_DIGEST_CACHE.pop("digest", None)
    first = runtime_config_digest()
    assert first
    assert runtime_config_digest() == first


def test_legacy_v2_cert_still_validates() -> None:
    components = {
        "schema_version": "2",
        "workflow_hash": "wf1",
        "deployment_hash": "dep1",
        "repair_mode": "fail_fast",
        "custom_nodes_generation": "gen1",
    }
    h = hashlib.sha256()
    h.update(b"cert_schema=2\n")
    h.update(b"workflow_hash=wf1\n")
    h.update(b"deployment_hash=dep1\n")
    h.update(b"repair_mode=fail_fast\n")
    h.update(b"custom_nodes_generation=gen1\n")
    payload = {
        "schema_version": 2,
        "identity": h.hexdigest(),
        "preflight_ok": True,
        "outputs_to_execute": ["7"],
        "node_errors": {},
        "identity_components": components,
    }
    state = BootstrapState()
    state.set_snapshot_certificate(payload)
    assert state.snapshot_cert_valid is True


def test_v3_tampered_identity_rejected() -> None:
    identity, components = _compute_v2_cert_identity(
        "wf1", repair_mode="fail_fast", custom_nodes_generation="gen1", **_SEMANTIC  # type: ignore[arg-type]
    )
    payload = _v3_cert_dict("0" * 64, components)
    assert identity != "0" * 64
    state = BootstrapState()
    state.set_snapshot_certificate(payload)
    assert state.snapshot_cert_valid is False


def test_config_digest_excludes_volatile_per_request_keys() -> None:
    import os

    modal_app._RUNTIME_CONFIG_DIGEST_CACHE.pop("digest", None)
    os.environ["COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"] = "comfy_kitchen"
    os.environ["COMFYMODAL_RESTORED_INSTANCE_ID"] = "uuid-run-1"
    os.environ["COMFYMODAL_INPUT_ID"] = "in-1234-0"
    os.environ["COMFYMODAL_CONTAINER_ID"] = "container-aaa"
    first = runtime_config_digest()
    assert first
    # Per-request identity churn must not move the digest...
    os.environ["COMFYMODAL_RESTORED_INSTANCE_ID"] = "uuid-run-2"
    os.environ["COMFYMODAL_INPUT_ID"] = "in-5678-0"
    os.environ["COMFYMODAL_CONTAINER_ID"] = "container-bbb"
    modal_app._RUNTIME_CONFIG_DIGEST_CACHE.pop("digest", None)
    assert runtime_config_digest() == first
    # ...but a real flag change must.
    os.environ["COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"] = "sage"
    modal_app._RUNTIME_CONFIG_DIGEST_CACHE.pop("digest", None)
    assert runtime_config_digest() != first
    # Restore a sane default for other tests.
    os.environ["COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"] = "comfy_kitchen"
    modal_app._RUNTIME_CONFIG_DIGEST_CACHE.pop("digest", None)
    for key in (
        "COMFYMODAL_RESTORED_INSTANCE_ID",
        "COMFYMODAL_INPUT_ID",
        "COMFYMODAL_CONTAINER_ID",
    ):
        os.environ.pop(key, None)


def test_exec_digest_captures_failure_reason() -> None:
    from pathlib import Path

    modal_app._EXEC_ENV_DIGEST_CACHE.pop("digest", None)
    modal_app._EXEC_ENV_DIGEST_ERROR.clear()
    with patch.object(Path, "glob", return_value=[]):
        assert execution_environment_digest() == ""
        assert modal_app._EXEC_ENV_DIGEST_ERROR.get("reason") == "no_runtime_py_files"
    modal_app._EXEC_ENV_DIGEST_CACHE.pop("digest", None)
    modal_app._EXEC_ENV_DIGEST_ERROR.clear()
    assert execution_environment_digest() != ""
    assert modal_app._EXEC_ENV_DIGEST_ERROR.get("reason", "") == ""
