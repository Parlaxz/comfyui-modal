"""Focused P1.6 destination-control contracts (no real Modal access)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import modal_workspaces
from tools.v2_control import cli
from tools.v2_control.backend import BackendRunner, BackendSpec
from tools.v2_control.errors import BackendError, GateError
from tools.v2_control.fingerprints import FingerprintEngine


def _git_common(monkeypatch, common):
    monkeypatch.setattr(
        modal_workspaces.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=str(common), stderr=""
        ),
    )


def _registry(root, workspaces, active):
    return modal_workspaces.save_workspace_registry(
        root / ".modal_workspaces.json",
        {
            "version": 1,
            "active_workspace_id": active,
            "workspaces": workspaces,
            "deploy_state_by_workspace": {},
        },
    )


def _workspace(identifier, label):
    return {
        "id": identifier,
        "label": label,
        "token_id": "ak-test",
        "token_secret": "as-test",
    }


def _target(root, identifier="ws-six", label="Testing 6", environment="(default)"):
    path = root / "config" / "v2"
    path.mkdir(parents=True)
    (path / "modal_target.toml").write_text(
        f'schema_version = 1\n\n[modal]\nworkspace_id = "{identifier}"\n'
        f'workspace_label = "{label}"\nenvironment = "{environment}"\n',
        encoding="utf-8",
    )


def test_shared_registry_migrates_valid_legacy_without_deleting_it(tmp_path, monkeypatch):
    common = tmp_path / "common-git"
    legacy = _workspace("ws-six", "Testing 6")
    _registry(tmp_path, [legacy], "ws-six")
    _git_common(monkeypatch, common)

    shared = modal_workspaces.resolve_workspace_registry_path(tmp_path)

    assert shared == common / "comfymodal" / "modal_workspaces.json"
    assert shared.is_file()
    assert (tmp_path / ".modal_workspaces.json").is_file()


def test_malformed_legacy_registry_fails_closed(tmp_path, monkeypatch):
    common = tmp_path / "common-git"
    (tmp_path / ".modal_workspaces.json").write_text("{bad", encoding="utf-8")
    _git_common(monkeypatch, common)

    with pytest.raises(ValueError):
        modal_workspaces.resolve_workspace_registry_path(tmp_path)
    assert not (common / "comfymodal" / "modal_workspaces.json").exists()


def test_target_is_exact_and_does_not_consult_active_workspace(tmp_path, monkeypatch):
    common = tmp_path / "common-git"
    six = _workspace("ws-six", "Testing 6")
    three = _workspace("ws-three", "Testing 3")
    _registry(tmp_path, [six, three], "ws-three")
    _target(tmp_path)
    _git_common(monkeypatch, common)

    destination = modal_workspaces.resolve_modal_destination(tmp_path)

    assert destination["workspace_id"] == "ws-six"
    assert destination["workspace_label"] == "Testing 6"
    assert destination["environment"] == "(default)"


def test_target_label_mismatch_fails_before_resolution(tmp_path, monkeypatch):
    common = tmp_path / "common-git"
    _registry(tmp_path, [_workspace("ws-six", "Testing 3")], "ws-six")
    _target(tmp_path)
    _git_common(monkeypatch, common)

    with pytest.raises(ValueError, match="label"):
        modal_workspaces.resolve_modal_destination(tmp_path)


def test_environment_override_is_rejected_for_canonical_args(tmp_path, monkeypatch):
    common = tmp_path / "common-git"
    _registry(tmp_path, [_workspace("ws-six", "Testing 6")], "ws-six")
    _target(tmp_path)
    _git_common(monkeypatch, common)
    args = SimpleNamespace(workspace_id=None, workspace=None, environment="staging")

    with pytest.raises(cli.GateError, match="config-owned"):
        cli._workspace_binding_for_args(args, tmp_path)


def test_fingerprint_contains_destination_identity():
    from tests.v2ctl_fakes import FakeConfig

    config = FakeConfig()
    setattr(config, "modal_destination", SimpleNamespace(
        workspace_id="ws-six", label="Testing 6", environment="(default)"
    ))
    inputs = FingerprintEngine(config).deploy_inputs()
    assert inputs["modal_destination"] == {
        "workspace_id": "ws-six",
        "workspace_label": "Testing 6",
        "environment": "(default)",
    }


def test_destination_change_invalidates_deploy_fingerprint():
    from tests.v2ctl_fakes import FakeConfig

    first = FakeConfig()
    second = FakeConfig()
    setattr(first, "modal_destination", SimpleNamespace(
        workspace_id="ws-six", label="Testing 6", environment="(default)"
    ))
    setattr(second, "modal_destination", SimpleNamespace(
        workspace_id="ws-three", label="Testing 3", environment="(default)"
    ))
    assert FingerprintEngine(first).deploy_fingerprint() != FingerprintEngine(second).deploy_fingerprint()


def test_native_modal_invocation_requires_frozen_destination(monkeypatch):
    from tests.v2ctl_fakes import FakeConfig

    called = []
    monkeypatch.setattr("tools.v2_control.backend.subprocess.run", lambda *a, **k: called.append(a))
    runner = BackendRunner(Path.cwd(), cli.env_mod.EnvironmentBuilder())
    with pytest.raises(BackendError, match="frozen config-owned destination"):
        runner.run(
            BackendSpec(name="history", executable=["modal", "app", "history", "x"], kind="deploy"),
            config=FakeConfig(),
        )
    assert called == []


def test_adversarial_testing3_environment_is_irrelevant(monkeypatch):
    from tests.v2ctl_fakes import FakeConfig

    destination = SimpleNamespace(
        workspace_id="ws-six",
        label="Testing 6",
        environment="(default)",
        token_id="ak-testing6",
        token_secret="as-testing6",
    )
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-testing3")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "as-testing3")
    monkeypatch.setenv("MODAL_ENVIRONMENT", "testing3")
    monkeypatch.setenv("MODAL_CLIENT_ID", "client-testing3")
    monkeypatch.setenv("MODAL_AUTH", "profile-testing3")
    monkeypatch.setattr("tools.v2_control.backend.subprocess.run", fake_run)
    monkeypatch.setattr("tools.v2_control.cli.assert_workspace_binding_current", lambda *_args: None)

    runner = BackendRunner(Path.cwd(), cli.env_mod.EnvironmentBuilder(), destination)
    runner.run(
        BackendSpec(name="deploy", executable=["modal", "deploy", "x"], kind="deploy"),
        config=FakeConfig(),
    )

    assert captured["MODAL_TOKEN_ID"] == "ak-testing6"
    assert captured["MODAL_TOKEN_SECRET"] == "as-testing6"
    assert "MODAL_ENVIRONMENT" not in captured
    assert "MODAL_CLIENT_ID" not in captured
    assert "MODAL_AUTH" not in captured
    assert captured["MODAL_WORKSPACE_ID"] == "ws-six"
    assert captured["MODAL_WORKSPACE_LABEL"] == "Testing 6"


def test_canonical_publisher_consumes_frozen_destination(monkeypatch):
    from tools import publish_custom_nodes_volume as publisher

    monkeypatch.setenv("COMFYMODAL_V2CTL_DESTINATION_FROZEN", "1")
    monkeypatch.setenv("MODAL_WORKSPACE_ID", "ws-six")
    monkeypatch.setenv("MODAL_WORKSPACE_LABEL", "Testing 6")
    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-six")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "as-six")
    monkeypatch.setenv("MODAL_ENVIRONMENT", "(default)")

    destination = publisher._load_active_workspace()
    assert destination["id"] == "ws-six"
    assert destination["label"] == "Testing 6"
    assert destination["token_id"] == "ak-six"


def test_strict_receipt_without_destination_fails_closed(tmp_path):
    from tools.v2_control.deployment_receipt import DeploymentReceipt, write_deployment_receipt

    from tests.v2ctl_fakes import FakeConfig

    config = FakeConfig(profile_name="golden_p1")
    config.target.method = "run_golden_serial_stream"
    with pytest.raises(GateError, match="destination"):
        write_deployment_receipt(
            tmp_path,
            DeploymentReceipt(
                profile="golden_p1",
                target={"app": "a", "class": "C", "method": "run_golden_serial_stream"},
                deploy_fingerprint="a" * 64,
                effective_environment={},
                deployment_version=1,
                created_at="now",
                modal_app="a",
                deployment_identity={"app": "a", "version": 1, "deploy_fingerprint": "a" * 64},
                source_probe={"expected": {"modules": {}}},
                image_identity={"status": "not_observed_at_deploy"},
                s4_generation="g",
                s4_identity={"generation": "g", "manifest_digest": "m"},
                effective_config={"profile": "golden_p1"},
                manifest_path="manifest.json",
                manifest_digest="m",
            ),
        )


def test_serial_and_parallel_destination_resolution_is_identical(tmp_path, monkeypatch):
    common = tmp_path / "common-git"
    workspace = _workspace("ws-six", "Testing 6")
    _registry(tmp_path, [workspace], "ws-six")
    _target(tmp_path)
    _git_common(monkeypatch, common)

    serial = modal_workspaces.resolve_modal_destination(tmp_path)
    parallel = modal_workspaces.resolve_modal_destination(tmp_path)
    assert (serial["workspace_id"], serial["environment"]) == (
        parallel["workspace_id"], parallel["environment"]
    )


@pytest.mark.skipif(not shutil.which("git"), reason="git is required for worktree proof")
def test_real_linked_worktrees_share_common_registry(tmp_path):
    main = tmp_path / "main"
    linked = tmp_path / "linked"
    main.mkdir()
    def git(*args, cwd=main):
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        )

    git("init", "-b", "main")
    (main / "config" / "v2").mkdir(parents=True)
    (main / "config" / "v2" / "modal_target.toml").write_text(
        'schema_version = 1\n\n[modal]\nworkspace_id = "ws-six"\n'
        'workspace_label = "Testing 6"\nenvironment = "(default)"\n',
        encoding="utf-8",
    )
    (main / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    git("add", ".")
    git("-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "init")
    (main / ".modal_workspaces.json").write_text(
        __import__("json").dumps({
            "version": 1,
            "active_workspace_id": "ws-three",
            "workspaces": [
                {"id": "ws-six", "label": "Testing 6", "token_id": "ak-six", "token_secret": "as-six"},
                {"id": "ws-three", "label": "Testing 3", "token_id": "ak-three", "token_secret": "as-three"},
            ],
            "deploy_state_by_workspace": {},
        }),
        encoding="utf-8",
    )
    git("worktree", "add", str(linked))

    first = modal_workspaces.resolve_modal_destination(main)
    second = modal_workspaces.resolve_modal_destination(linked)
    assert first["workspace_id"] == second["workspace_id"] == "ws-six"
    assert first["token_id"] == second["token_id"] == "ak-six"
    assert first["registry"] == second["registry"]
