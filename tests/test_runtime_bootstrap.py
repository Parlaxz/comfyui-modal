"""Focused tests for remote V2 ComfyUI-Manager offline config.

All tests use ``tmp_path`` as a stand-in for ``comfyui_root`` — no files
outside the temporary directory are touched.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comfymodal_runtime.runtime_bootstrap import (
    BootstrapConfig,
    RuntimeBootstrap,
    _MANAGER_CONFIG_PATHS,
    _write_manager_config_ini,
    configure_manager_offline,
    ensure_models_symlink,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def comfyui_root(tmp_path: Path) -> Path:
    return tmp_path


def all_config_paths(root: Path) -> list[Path]:
    return [root / p for p in _MANAGER_CONFIG_PATHS]


# Legacy ComfyUI-Manager config locations.  Bootstrap must NEVER create these:
# their presence triggers the manager's import-time migration branch which
# pip-installs ComfyUI requirements (not gated by network_mode=offline).
LEGACY_MANAGER_CONFIG_PATHS: tuple[str, ...] = (
    "user/default/__manager/config.ini",
    "user/default/ComfyUI-Manager/config.ini",
)


def read_config_ini(path: Path) -> configparser.ConfigParser:
    p = configparser.ConfigParser(strict=False)
    p.read([str(path)], encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _MANAGER_CONFIG_PATHS — exact tuple guard
# ---------------------------------------------------------------------------


class TestManagerConfigPaths:
    """Canonical-only tuple — never edit without updating deploy expectations."""

    def test_exact_paths(self) -> None:
        assert _MANAGER_CONFIG_PATHS == (
            "user/__manager/config.ini",
        ), "bootstrap must write only the canonical manager config path"


# ---------------------------------------------------------------------------
# _write_manager_config_ini — unit behaviour
# ---------------------------------------------------------------------------


class TestWriteManagerConfigIni:
    def test_creates_file_with_offline(self, tmp_path: Path) -> None:
        target = tmp_path / "user" / "__manager" / "config.ini"
        assert not target.exists()
        _write_manager_config_ini(target)
        assert target.exists()
        cp = read_config_ini(target)
        assert cp.get("default", "network_mode") == "offline"

    def test_preserves_existing_sections_and_options(self, tmp_path: Path) -> None:
        target = tmp_path / "user" / "default" / "config.ini"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "[default]\nfoo = bar\n[other]\nbaz = qux\n",
            encoding="utf-8",
        )
        _write_manager_config_ini(target)
        cp = read_config_ini(target)
        assert cp.get("default", "network_mode") == "offline"
        assert cp.get("default", "foo") == "bar"
        assert cp.get("other", "baz") == "qux"

    def test_overwrites_existing_network_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "user" / "default" / "ComfyUI-Manager" / "config.ini"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("[default]\nnetwork_mode = remote\n", encoding="utf-8")
        _write_manager_config_ini(target)
        cp = read_config_ini(target)
        assert cp.get("default", "network_mode") == "offline"

    def test_handles_duplicate_sections(self, tmp_path: Path) -> None:
        """ConfigParser(strict=False) tolerates duplicate ``[default]`` headers."""
        target = tmp_path / "user" / "__manager" / "config.ini"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "[default]\nkey_a = 1\n[default]\nkey_b = 2\n",
            encoding="utf-8",
        )
        _write_manager_config_ini(target)
        cp = read_config_ini(target)
        # strict=False means the last value for network_mode wins — must be offline
        assert cp.get("default", "network_mode") == "offline"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c" / "config.ini"
        assert not target.parent.exists()
        _write_manager_config_ini(target)
        assert target.parent.exists()
        cp = read_config_ini(target)
        assert cp.get("default", "network_mode") == "offline"

    def test_atomic_write_does_not_corrupt_on_failure(self, tmp_path: Path) -> None:
        """Simulate a write failure — original file is left intact."""
        target = tmp_path / "user" / "__manager" / "config.ini"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("[default]\nnetwork_mode = remote\n", encoding="utf-8")

        # Patch os.replace to simulate a failure
        with patch.object(os, "replace", side_effect=RuntimeError("disk full")):
            with pytest.raises(RuntimeError, match="disk full"):
                _write_manager_config_ini(target)

        # Original file unchanged
        cp = read_config_ini(target)
        assert cp.get("default", "network_mode") == "remote", (
            "atomic write failure must not corrupt the original file"
        )


# ---------------------------------------------------------------------------
# configure_manager_offline — canonical config.ini only; environ setdefault
# ---------------------------------------------------------------------------


class TestConfigureManagerOffline:
    """``configure_manager_offline`` writes ONLY the canonical config.ini
    (``user/__manager/config.ini``) plus env hints — never the legacy paths."""

    def test_canonical_only_config_created(self, comfyui_root: Path) -> None:
        paths = all_config_paths(comfyui_root)
        assert paths == [comfyui_root / "user" / "__manager" / "config.ini"]
        for p in paths:
            assert not p.exists()
        configure_manager_offline(str(comfyui_root))
        for p in paths:
            assert p.exists(), f"{p} was not created"
            cp = read_config_ini(p)
            assert cp.get("default", "network_mode") == "offline"

    def test_legacy_paths_never_created(self, comfyui_root: Path) -> None:
        """Legacy manager config paths would trigger ComfyUI-Manager's
        import-time migration (pip-install of ComfyUI requirements), which
        ``network_mode = offline`` does NOT gate."""
        configure_manager_offline(str(comfyui_root))
        for rel in LEGACY_MANAGER_CONFIG_PATHS:
            assert not (comfyui_root / rel).exists(), (
                f"{rel} must never be created by snapshot/runtime bootstrap"
            )

    def test_existing_settings_preserved(self, comfyui_root: Path) -> None:
        canonical = comfyui_root / "user" / "__manager" / "config.ini"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(
            "[default]\ncat = meow\n[extra]\nkey = val\n",
            encoding="utf-8",
        )
        configure_manager_offline(str(comfyui_root))
        cp = read_config_ini(canonical)
        assert cp.get("default", "network_mode") == "offline"
        assert cp.get("default", "cat") == "meow"
        assert cp.get("extra", "key") == "val"

    def test_existing_network_mode_overwritten(self, comfyui_root: Path) -> None:
        canonical = comfyui_root / "user" / "__manager" / "config.ini"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("[default]\nnetwork_mode = remote\n", encoding="utf-8")
        configure_manager_offline(str(comfyui_root))
        cp = read_config_ini(canonical)
        assert cp.get("default", "network_mode") == "offline"

    def test_environ_setdefault_respects_caller_overrides(
        self, comfyui_root: Path,
    ) -> None:
        env = {
            "COMFYUI_MANAGER_MODE": "cache-only",
            "COMFYUI_MANAGER_NETWORK_MODE": "cache-only",
        }
        result = configure_manager_offline(str(comfyui_root), environ=env)
        # setdefault — caller values are NOT overwritten
        assert env["COMFYUI_MANAGER_MODE"] == "cache-only"
        assert env["COMFYUI_MANAGER_NETWORK_MODE"] == "cache-only"
        # But the return value always reports what *would* have been set
        assert result == {
            "COMFYUI_MANAGER_MODE": "offline",
            "COMFYUI_MANAGER_NETWORK_MODE": "offline",
        }
        # Config files still written regardless
        for p in all_config_paths(comfyui_root):
            cp = read_config_ini(p)
            assert cp.get("default", "network_mode") == "offline"

    def test_environ_default_when_not_pre_set(self, comfyui_root: Path) -> None:
        env: dict[str, str] = {}
        result = configure_manager_offline(str(comfyui_root), environ=env)
        assert env["COMFYUI_MANAGER_MODE"] == "offline"
        assert env["COMFYUI_MANAGER_NETWORK_MODE"] == "offline"
        assert result == {
            "COMFYUI_MANAGER_MODE": "offline",
            "COMFYUI_MANAGER_NETWORK_MODE": "offline",
        }

    def test_returns_changes_dict(self, comfyui_root: Path) -> None:
        result = configure_manager_offline(str(comfyui_root))
        assert result == {
            "COMFYUI_MANAGER_MODE": "offline",
            "COMFYUI_MANAGER_NETWORK_MODE": "offline",
        }


# ---------------------------------------------------------------------------
# RuntimeBootstrap integration — startup invokes configure with comfyui_root
# ---------------------------------------------------------------------------


class TestRuntimeBootstrapStartup:
    """Verify that ``RuntimeBootstrap.startup()`` calls ``configure_manager_offline``
    with the configured ``comfyui_root`` before ``start_backend``, and that the
    offline config files are observable by the time the backend runs."""

    def test_configure_invoked_with_comfyui_root(
        self, comfyui_root: Path,
    ) -> None:
        """Bootstrap calls configure_manager_offline(self.config.comfyui_root)."""
        bootstrap = RuntimeBootstrap(
            config=BootstrapConfig(comfyui_root=str(comfyui_root)),
            start_backend=MagicMock(return_value="test_backend"),
        )
        with patch(
            "comfymodal_runtime.runtime_bootstrap.ensure_models_symlink",
            return_value=str(comfyui_root / "models"),
        ):
            with patch.object(
                bootstrap, "start_backend", wraps=bootstrap.start_backend,
            ) as spylist:
                with patch(
                    "comfymodal_runtime.runtime_bootstrap.configure_manager_offline",
                    wraps=configure_manager_offline,
                ) as spy:
                    bootstrap.startup(snapshot=False)
                    spy.assert_called_once_with(str(comfyui_root))
                    spylist.assert_called_once()

    def test_backend_observes_offline_files(
        self, comfyui_root: Path,
    ) -> None:
        """Before start_backend is called, the config.ini files already exist."""
        seen_root: list[str] = []

        def check_config_before_backend() -> str:
            # Called at the point where the real backend would run
            for p in all_config_paths(comfyui_root):
                assert p.exists(), f"{p} must exist before backend starts"
                cp = read_config_ini(p)
                assert cp.get("default", "network_mode") == "offline"
            seen_root.append("checked")
            return "fake_backend"

        bootstrap = RuntimeBootstrap(
            config=BootstrapConfig(comfyui_root=str(comfyui_root)),
            start_backend=check_config_before_backend,
        )
        with patch(
            "comfymodal_runtime.runtime_bootstrap.ensure_models_symlink",
            return_value=str(comfyui_root / "models"),
        ):
            bootstrap.startup(snapshot=False)
        assert seen_root == ["checked"]

    def test_skip_when_manager_offline_false(
        self, comfyui_root: Path,
    ) -> None:
        """When ``manager_offline=False``, no config files are written."""
        bootstrap = RuntimeBootstrap(
            config=BootstrapConfig(
                comfyui_root=str(comfyui_root),
                manager_offline=False,
            ),
            start_backend=MagicMock(return_value="test"),
        )
        with patch(
            "comfymodal_runtime.runtime_bootstrap.ensure_models_symlink",
            return_value=str(comfyui_root / "models"),
        ):
            bootstrap.startup(snapshot=False)
        for p in all_config_paths(comfyui_root):
            assert not p.exists(), f"{p} should not exist when manager_offline=False"
