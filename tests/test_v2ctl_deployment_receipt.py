"""Focused tests for the Golden deployment receipt authority."""

from __future__ import annotations

import json

import pytest

from tools.v2_control import cli, source_probe
from tools.v2_control.config import ConfigResolver
from tools.v2_control.deployment_receipt import (
    DeploymentReceipt,
    latest_deployment_receipt,
    receipt_path,
    read_deployment_receipt,
    write_deployment_receipt,
)
from tools.v2_control.errors import FlagError, GateError
from tools.v2_control.fingerprints import FingerprintEngine
from tools.v2_control.validation import mark_runtime_health_verified
from tests.v2ctl_fakes import FakeConfig, FakeFlag


def _config() -> FakeConfig:
    config = FakeConfig(profile_name="golden_p1")
    config.target.app = "receipt-golden"
    config.target.method = "run_golden_serial_stream"
    return config


def _receipt(config: FakeConfig, *, version: int = 7) -> DeploymentReceipt:
    fingerprint = FingerprintEngine(config).deploy_fingerprint()
    return DeploymentReceipt(
        profile=config.profile_name,
        deploy_id="a" * 64,
        target={
            "app": config.target.app,
            "class": config.target.class_name,
            "method": config.target.method,
        },
        deploy_fingerprint=fingerprint,
        effective_environment={"COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "1"},
        deployment_version=version,
        created_at="2026-08-30T00:00:00+00:00",
        modal_app=config.target.app,
        profile_config_fingerprint="profile-A",
        # Workspace binding is checked unconditionally: deploying into the wrong
        # Modal workspace is a real operational failure, so it is validated once
        # here rather than re-proved through every record that mentions it.
        modal_destination={
            "workspace_id": "ws-test",
            "workspace_label": "test",
            "environment": "test",
            "source": "config/v2/modal_target.toml",
        },
    )


def test_receipt_is_immutable_and_malformed_receipts_fail_closed(tmp_path):
    config = _config()
    receipt = _receipt(config)
    path = write_deployment_receipt(tmp_path, receipt)
    assert read_deployment_receipt(path).to_dict() == receipt.to_dict()

    changed = DeploymentReceipt(**{**receipt.__dict__, "created_at": "later"})
    with pytest.raises(GateError, match="immutable"):
        write_deployment_receipt(tmp_path, changed)

    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(GateError, match="corrupt"):
        read_deployment_receipt(path)


def test_local_source_drift_warns_but_receipt_binding_uses_remote_identity(
    tmp_path, monkeypatch, capsys
):
    config = _config()
    stored = _receipt(config)
    path = write_deployment_receipt(tmp_path, stored)
    config.git.head = "B"
    monkeypatch.setattr(cli, "_app_version_number", lambda _app: 7)
    selected_path, selected = cli._bound_deployment_receipt(
        tmp_path, config, command="run"  # type: ignore[arg-type]
    )
    assert selected_path == path
    assert selected.deploy_fingerprint == stored.deploy_fingerprint
    assert "source drift is warning-only" in capsys.readouterr().err


def test_changed_modal_version_is_diagnostic_not_authoritative(
    tmp_path, monkeypatch, capsys
):
    """A Modal version drift must not invalidate an otherwise good receipt.

    It used to raise GateError, which meant a Modal-side version reset made a
    working deployment unusable and forced a redeploy -- without ever proving
    which code served a request. The request's own deploy_id is the authority;
    the version is reported for debugging only.
    """
    config = _config()
    stored = _receipt(config, version=7)
    path = write_deployment_receipt(tmp_path, stored)
    monkeypatch.setattr(cli, "_app_version_number", lambda _app: 8)

    selected_path, selected = cli._bound_deployment_receipt(
        tmp_path, config, command="gate"  # type: ignore[arg-type]
    )

    assert selected_path == path
    assert selected.deployment_version == stored.deployment_version
    err = capsys.readouterr().err
    assert "diagnostic only" in err
    assert "deploy_id" in err


def test_receipt_environment_can_prove_registered_metadata_is_not_local_truth():
    config = _config()
    config.flags.append(
        FakeFlag(
            name="COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS",
            value="1",
            source="set",
            change_requires="deploy",
        )
    )
    # A value explicitly proven by the immutable receipt is admitted; no
    # receipt/effective value leaves the unknown or changed value untrusted.
    resolver = ConfigResolver.__new__(ConfigResolver)
    resolver.check_run_safety(
        config, run_only=True,  # type: ignore[arg-type]
        trusted_environment={"COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "1"},
    )
    with pytest.raises(FlagError):
        resolver.check_run_safety(config, run_only=True)  # type: ignore[arg-type]


@pytest.mark.parametrize("environment", [
    {"PATH": "C:/secret-path"},
    {"MODAL_TOKEN_SECRET": "secret"},
    {"COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "forged"},
    {"COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "<redacted>"},
])
def test_receipt_rejects_host_auth_reserved_and_redacted_environment(tmp_path, environment):
    config = _config()
    with pytest.raises(GateError):
        write_deployment_receipt(
            tmp_path,
            DeploymentReceipt(**{**_receipt(config).__dict__, "effective_environment": environment}),
        )




def test_unrelated_same_version_receipt_does_not_block_target_selection(tmp_path):
    config = _config()
    requested = _receipt(config, version=3)
    requested_path = write_deployment_receipt(tmp_path, requested)
    unrelated = DeploymentReceipt(**{
        **_receipt(config, version=3).__dict__,
        "target": {
            "app": "unrelated-app",
            "class": config.target.class_name,
            "method": config.target.method,
        },
        "modal_app": "unrelated-app",
        "deploy_fingerprint": "c" * 64,
    })
    write_deployment_receipt(tmp_path, unrelated)

    result = latest_deployment_receipt(
        tmp_path,
        profile=config.profile_name,
        target={
            "app": config.target.app,
            "class": config.target.class_name,
            "method": config.target.method,
        },
    )
    assert result is not None
    selected_path, selected = result
    assert selected_path == requested_path
    assert selected.target["app"] == config.target.app




def test_source_probe_uses_deployed_expected_source_and_fails_mismatch():
    expected = {"git_head": "A", "modules": {"comfymodal_runtime/foo.py": {"sha256": "a"}}}
    remote = {
        "modules": {"comfymodal_runtime/foo.py": {"sha256": "b", "file": "/workspace/foo.py"}},
        "ledger": {},
    }
    original_modules = source_probe.REQUIRED_MODULES
    original_names = source_probe.REMOTE_MODULE_NAMES
    source_probe.REQUIRED_MODULES = ("comfymodal_runtime/foo.py",)
    source_probe.REMOTE_MODULE_NAMES = {"comfymodal_runtime/foo.py": "comfymodal_runtime/foo.py"}
    try:
        report = source_probe.classify_source_probe(expected, remote)
    finally:
        source_probe.REQUIRED_MODULES = original_modules
        source_probe.REMOTE_MODULE_NAMES = original_names
    assert report["verdict"] == "MISMATCH"


