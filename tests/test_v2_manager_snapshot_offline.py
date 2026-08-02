"""Focused tests for ComfyUI-Manager read-only behavior at snap=True.

Verifies that snapshot startup forces ComfyUI-Manager into offline mode
(config files + env-var hints) so the snapshot is read-only with respect to
package installation, update, and migration, while the normal UI runtime
remains available (offline mode does not disable the manager, it only
restricts network operations).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def _modal_stub():
    modal = types.ModuleType("modal")
    modal.Image = MagicMock()
    modal.Image.from_registry.return_value = MagicMock()
    modal.Image.debian_slim.return_value = MagicMock()
    modal.App = MagicMock()
    modal.App.return_value.function = lambda **_: lambda fn: fn
    modal.App.return_value.cls = lambda **_: lambda cls: cls
    modal.Volume = MagicMock()
    modal.Volume.from_name.return_value = MagicMock()
    modal.Dict = MagicMock()
    modal.Dict.from_name.return_value = MagicMock()
    modal.Secret = MagicMock()
    modal.Secret.from_name.return_value = MagicMock()
    modal.web_server = lambda *_, **__: lambda fn: fn
    modal.enter = lambda **_: lambda fn: fn
    modal.exit = lambda: lambda fn: fn
    modal.method = lambda *_, **__: lambda fn: fn
    modal.concurrent = lambda **_: lambda cls: cls
    return modal


def _load_comfyapp():
    old_modal = sys.modules.pop("modal", None)
    sys.modules["modal"] = _modal_stub()
    name = f"comfyapp_manager_offline_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / "comfyapp.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        if old_modal is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = old_modal


def test_set_manager_network_mode_offline_writes_offline_config(tmp_path):
    """snap=True startup must write ``network_mode = offline`` so the
    manager cannot install/update/migrate packages during the snapshot."""
    module = _load_comfyapp()

    def _fake_makedirs(path, exist_ok=False):
        return None

    with patch.object(module.os, "makedirs", side_effect=_fake_makedirs):
        with patch.object(module.os, "environ", {}):
            with patch("builtins.open", create=True, new=MagicMock()):
                written = module.set_manager_network_mode_offline()
    # The canonical config path (the one the manager actually reads via
    # folder_paths.get_user_directory() + '__manager') must be covered.
    expected_paths = {
        "/root/comfy/ComfyUI/user/__manager/config.ini",
    }
    assert set(written) == expected_paths


def test_set_manager_network_mode_offline_does_not_write_legacy_config():
    """Writing the legacy config alongside the new one would make
    ComfyUI-Manager's import-time migration take the "first update after
    upgrade" branch, which pip-installs ComfyUI requirements and moves the
    legacy directory — an actual installation during snap=True that the
    offline config does NOT gate."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    fn_idx = src.index("def set_manager_network_mode_offline() -> list[str]:")
    fn_src = src[fn_idx:fn_idx + 1500]
    # Only the config_paths literal must be free of the legacy/new-path pair;
    # the docstring may reference them for explanation.
    paths_start = fn_src.index("config_paths = [")
    paths_end = fn_src.index("]", paths_start)
    paths_src = fn_src[paths_start:paths_end]
    assert "/root/comfy/ComfyUI/user/__manager/config.ini" in paths_src
    assert "user/default/ComfyUI-Manager/config.ini" not in paths_src
    assert "user/default/__manager/config.ini" not in paths_src


def test_set_manager_network_mode_offline_sets_env_hints(tmp_path):
    """Env-var hints keep ComfyUI-Manager read-only even when it reads
    environment variables before config files."""
    module = _load_comfyapp()
    fake_env = {}
    with patch.object(module.os, "makedirs"):
        with patch.object(module.os, "environ", fake_env):
            with patch("builtins.open", create=True):
                module.set_manager_network_mode_offline()
    assert fake_env.get("COMFYUI_MANAGER_MODE") == "offline"
    assert fake_env.get("COMFYUI_MANAGER_NETWORK_MODE") == "offline"


def test_startup_calls_manager_offline_before_backend_start():
    """snap=True startup must force manager offline before backend init so
    custom-node import does not trigger manager package operations."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    startup_idx = src.index("def startup(self):")
    startup_src = src[startup_idx:]
    assert "set_manager_network_mode_offline()" in startup_src
    # The offline call must appear before backend start in the snap=True body.
    manager_idx = startup_src.index("set_manager_network_mode_offline()")
    backend_idx = startup_src.index("self._start_backend()")
    assert manager_idx < backend_idx


def test_snapshot_backend_start_runs_under_manager_migration_guard():
    """A config/env hint alone is insufficient: ComfyUI-Manager's import-time
    migration (``migrate_legacy_config`` -> ``_handle_first_update_migration``
    -> ``pip install -r <ComfyUI>/requirements.txt``) is not gated by
    ``network_mode``.  The snapshot backend start must therefore run inside
    the narrow read-only manager guard."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    startup_idx = src.index("def startup(self):")
    startup_src = src[startup_idx:]
    guard_calls = startup_src.count("with _readonly_comfyui_manager_during_snapshot():")
    assert guard_calls >= 2, f"snapshot backend start not guarded (found {guard_calls})"
    # Every _start_backend() call in startup must be wrapped by the guard.
    assert "with _readonly_comfyui_manager_during_snapshot():\n                        self._start_backend()" in src
    assert "with _readonly_comfyui_manager_during_snapshot():\n                self._start_backend()" in src


def test_manager_migration_guard_patches_and_restores_run_migration_checks():
    """The guard must swap ``manager_migration.run_migration_checks`` for a
    read-only no-op while active and restore the real function afterwards, so
    the normal UI runtime keeps genuine migration behavior."""
    module = _load_comfyapp()
    fake = types.ModuleType("manager_migration")

    def _real_checks(user_dir, manager_files_path):
        return "migrated"

    setattr(fake, "run_migration_checks", _real_checks)
    sys.modules["manager_migration"] = fake
    try:
        with module._readonly_comfyui_manager_during_snapshot():
            assert fake.run_migration_checks("u", "m") is None
            # The read-only no-op must not raise for the snapshot call shape.
            fake.run_migration_checks("/root/comfy/ComfyUI/user", "/root/comfy/ComfyUI/user/__manager")
        assert fake.run_migration_checks("u", "m") == "migrated"
    finally:
        sys.modules.pop("manager_migration", None)


def test_manager_offline_does_not_disable_ui_runtime():
    """Offline mode restricts network operations but must not disable the
    manager entirely — normal UI runtime availability is preserved.  The
    config written is a minimal network_mode=offline (no front-disable)."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert 'f.write("[default]\\nnetwork_mode = offline\\n")' in src
    # setdefault (not assignment) preserves caller-managed manager mode.
    assert 'os.environ.setdefault("COMFYUI_MANAGER_MODE", "offline")' in src
