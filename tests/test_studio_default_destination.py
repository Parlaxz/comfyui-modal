"""FAST_UNIT: studio-default destination sentinel follows the Studio active workspace."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast_unit

import modal_workspaces
from tools.v2_control import profile_catalog


def _write_registry(path: Path, active_id: str | None, entries: list[dict]) -> None:
    payload = {
        "version": 1,
        "active_workspace_id": active_id,
        "workspaces": entries,
        "deploy_state_by_workspace": {},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _entry(ws_id: str, label: str) -> dict:
    return {
        "id": ws_id,
        "label": label,
        "token_id": "ak-test-token",
        "token_secret": "as-test-secret",
        "last_used_at": None,
        "last_deploy_status": "idle",
        "notes": "",
    }


def _write_sentinel_target(root: Path, workspace_id: str = "studio-default") -> None:
    target_dir = root / "config" / "v2"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "modal_target.toml").write_text(
        'schema_version = 1\n\n[modal]\n'
        f'workspace_id = "{workspace_id}"\n'
        'workspace_label = "Studio Default"\n'
        'environment = "(default)"\n',
        encoding="utf-8",
    )


def test_sentinel_spellings_normalize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert modal_workspaces.is_studio_default_workspace_id("studio-default")
    assert modal_workspaces.is_studio_default_workspace_id("Studio Default")
    assert modal_workspaces.is_studio_default_workspace_id("STUDIO_DEFAULT")
    assert not modal_workspaces.is_studio_default_workspace_id("ws_123")
    assert not modal_workspaces.is_studio_default_workspace_id("")

    _write_sentinel_target(tmp_path)
    registry = tmp_path / "registry.json"
    _write_registry(registry, "ws_active", [_entry("ws_active", "Testing 7")])
    monkeypatch.setattr(
        modal_workspaces, "resolve_workspace_registry_path", lambda _root: registry
    )
    dest = modal_workspaces.resolve_modal_destination(tmp_path)
    assert dest["workspace_id"] == "ws_active"
    assert dest["workspace_label"] == "Testing 7"
    assert dest["source"] == "config/v2/modal_target.toml"


def test_sentinel_follows_active_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_sentinel_target(tmp_path)
    registry = tmp_path / "registry.json"
    _write_registry(
        registry, "ws_6", [_entry("ws_6", "Testing 6"), _entry("ws_7", "Testing 7")]
    )
    monkeypatch.setattr(
        modal_workspaces, "resolve_workspace_registry_path", lambda _root: registry
    )
    first = modal_workspaces.resolve_modal_destination(tmp_path)
    assert first["workspace_id"] == "ws_6"

    _write_registry(
        registry, "ws_7", [_entry("ws_6", "Testing 6"), _entry("ws_7", "Testing 7")]
    )
    second = modal_workspaces.resolve_modal_destination(tmp_path)
    assert second["workspace_id"] == "ws_7"


def test_sentinel_without_active_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_sentinel_target(tmp_path)
    registry = tmp_path / "registry.json"
    # Two workspaces and no active id: get_active_workspace() is None.
    _write_registry(
        registry, None, [_entry("ws_6", "Testing 6"), _entry("ws_7", "Testing 7")]
    )
    monkeypatch.setattr(
        modal_workspaces, "resolve_workspace_registry_path", lambda _root: registry
    )
    with pytest.raises(ValueError):
        modal_workspaces.resolve_modal_destination(tmp_path)
    assert profile_catalog._destination_record(tmp_path) is None


def test_catalog_destination_record_resolves_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_sentinel_target(tmp_path)
    registry = tmp_path / "registry.json"
    _write_registry(registry, "ws_7", [_entry("ws_7", "Testing 7")])
    monkeypatch.setattr(
        modal_workspaces, "resolve_workspace_registry_path", lambda _root: registry
    )
    record = profile_catalog._destination_record(tmp_path)
    assert record is not None
    assert record["workspace_id"] == "ws_7"
    assert record["workspace_label"] == "Testing 7"


def test_catalog_signature_moves_on_active_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_sentinel_target(tmp_path)
    (tmp_path / ".v2ctl" / "deployments").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "v2" / "profiles").mkdir(parents=True, exist_ok=True)
    registry = tmp_path / "registry.json"
    _write_registry(
        registry, "ws_6", [_entry("ws_6", "Testing 6"), _entry("ws_7", "Testing 7")]
    )
    monkeypatch.setattr(
        modal_workspaces, "resolve_workspace_registry_path", lambda _root: registry
    )
    before = profile_catalog._catalog_signature(tmp_path)
    _write_registry(
        registry, "ws_7", [_entry("ws_6", "Testing 6"), _entry("ws_7", "Testing 7")]
    )
    after = profile_catalog._catalog_signature(tmp_path)
    assert before != after
