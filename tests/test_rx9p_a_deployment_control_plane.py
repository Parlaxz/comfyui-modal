"""RX9P-A workspace binding and publisher preflight contracts."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

import modal_workspaces
from tools.v2_control import cli


def _workspace(root, *, label="Testing", set_active=True):
    registry = modal_workspaces.upsert_workspace(
        root / ".modal_workspaces.json",
        label,
        "ak-test-token",
        "as-test-secret",
        set_active=set_active,
    )
    return registry["workspaces"][-1]


def test_explicit_workspace_and_environment_are_frozen(tmp_path):
    workspace = _workspace(tmp_path)
    binding = cli.resolve_workspace_binding(
        tmp_path, workspace_id=workspace["id"], environment="staging"
    )

    assert binding.workspace_id == workspace["id"]
    assert binding.environment == "staging"
    assert binding.public == {"workspace": workspace["id"], "environment": "staging"}
    assert "token" not in str(binding.public).lower()


def test_missing_workspace_fails_before_backend_probe(tmp_path):
    _workspace(tmp_path)
    called = []

    with pytest.raises(cli.GateError, match="not registered"):
        cli.resolve_workspace_binding(tmp_path, workspace_id="missing")
    # The preflight cannot even be constructed, so an injected backend probe is
    # necessarily untouched.
    assert called == []


def test_active_workspace_change_fails_before_probe(tmp_path):
    first = _workspace(tmp_path, label="first")
    second = _workspace(tmp_path, label="second", set_active=False)
    binding = cli.resolve_workspace_binding(tmp_path, workspace_id=first["id"])
    modal_workspaces.set_active_workspace(tmp_path / ".modal_workspaces.json", second["id"])
    called = []

    with pytest.raises(cli.GateError, match="active Modal workspace"):
        cli.run_publisher_preflight(
            tmp_path,
            binding,
            local_content_generation="local",
            probe=lambda *_args: called.append(True),
        )
    assert called == []


def test_publisher_missing_requires_bootstrap(tmp_path):
    workspace = _workspace(tmp_path)
    binding = cli.resolve_workspace_binding(tmp_path, workspace_id=workspace["id"])
    result = cli.run_publisher_preflight(
        tmp_path,
        binding,
        local_content_generation="local",
        probe=lambda *_args: {
            "publisher_exists": False,
            "publisher_function_exists": False,
            "publisher_version": 0,
            "remote_generation": None,
        },
    )

    assert result["PUBLICATION_DECISION"] == "bootstrap_required"
    assert result["REQUIRES_PUBLICATION"] is True
    assert result["READY_FOR_CONSUMER_DEPLOY"] is False


def test_publisher_function_missing_requires_bootstrap(tmp_path):
    workspace = _workspace(tmp_path)
    binding = cli.resolve_workspace_binding(tmp_path, workspace_id=workspace["id"])
    result = cli.run_publisher_preflight(
        tmp_path,
        binding,
        local_content_generation="local",
        probe=lambda *_args: {
            "publisher_exists": True,
            "publisher_function_exists": False,
            "publisher_version": 4,
            "remote_generation": "local",
        },
    )

    assert result["PUBLICATION_DECISION"] == "bootstrap_required"
    assert result["READY_FOR_CONSUMER_DEPLOY"] is False


def test_require_ready_rejects_publish_required_and_unknown_generation(tmp_path):
    workspace = _workspace(tmp_path)
    binding = cli.resolve_workspace_binding(tmp_path, workspace_id=workspace["id"])

    for remote_generation in ("different", None):
        with pytest.raises(cli.GateError, match="has not been performed"):
            cli.run_publisher_preflight(
                tmp_path,
                binding,
                local_content_generation="local",
                require_ready=True,
                probe=lambda *_args, remote_generation=remote_generation: {
                    "publisher_exists": True,
                    "publisher_function_exists": True,
                    "publisher_version": 4,
                    "remote_generation": remote_generation,
                },
            )


def test_frozen_process_environment_restores_parent(monkeypatch, tmp_path):
    workspace = _workspace(tmp_path)
    binding = cli.resolve_workspace_binding(tmp_path, workspace_id=workspace["id"], environment="staging")
    monkeypatch.setenv("MODAL_TOKEN_ID", "ambient-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "ambient-secret")
    before = dict(os.environ)

    with cli._workspace_process_environment(binding, {"COMFYMODAL_V2_APP_NAME": "rx9p-a"}):
        assert os.environ["MODAL_TOKEN_ID"] == binding.token_id
        assert os.environ["MODAL_TOKEN_SECRET"] == binding.token_secret
        assert os.environ["MODAL_ENVIRONMENT"] == "staging"

    assert dict(os.environ) == before


def test_gate_and_confirm_backend_wrapper_injects_frozen_environment(tmp_path):
    workspace = _workspace(tmp_path)
    binding = cli.resolve_workspace_binding(tmp_path, workspace_id=workspace["id"], environment="staging")
    captured = []

    class FakeRunner:
        def run(self, spec, **kwargs):
            captured.append(kwargs["extra_env"])
            return "ok"

    wrapped = cli._FrozenWorkspaceBackendRunner(FakeRunner(), tmp_path, binding)
    wrapped.run("spec", config=object(), extra_env={"MODAL_TOKEN_ID": "ambient"})
    env = captured[0]
    assert env["MODAL_TOKEN_ID"] == binding.token_id
    assert env["MODAL_TOKEN_SECRET"] == binding.token_secret
    assert env["MODAL_ENVIRONMENT"] == "staging"
    assert "MODAL_CLIENT_SECRET" not in env


def test_publication_diagnostic_is_bounded_and_redacted():
    exc = RuntimeError(
        "publisher failed: {'token_id': 'ak-live-secret', "
        "'token_secret': 'as-live-secret'}"
    )
    diagnostic = cli._safe_exception_diagnostic(
        exc,
        secrets={"token_id": "ak-live-secret", "token_secret": "as-live-secret"},
    )
    assert "RuntimeError" in diagnostic
    assert "ak-live-secret" not in diagnostic
    assert "as-live-secret" not in diagnostic
    assert "token_secret" in diagnostic


def test_verified_publication_generation_is_authoritative_despite_mismatch(capsys):
    publication = SimpleNamespace(
        identity=SimpleNamespace(generation="published"),
        result={"content_generation": "published"},
    )
    assert cli._resolve_publication_generation(publication, "preflight") == "published"
    assert "pre-publication generation differs" in capsys.readouterr().out
    assert cli._publication_verified_generation(publication) == "published"


def test_missing_publication_generation_fails_closed():
    with pytest.raises(cli.GateError, match="no verified generation"):
        cli._resolve_publication_generation(
            SimpleNamespace(identity=SimpleNamespace(generation="")),
            "preflight",
        )
    with pytest.raises(cli.GateError, match="no verified generation"):
        cli._resolve_publication_generation(SimpleNamespace(identity=None), "")
