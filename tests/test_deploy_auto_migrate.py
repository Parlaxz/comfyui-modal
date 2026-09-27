"""
Focused tests for ``_auto_migrate_generated_artifacts`` and the auto-migration
path in ``_run_deploy_background``.

Scope:
    - ``_auto_migrate_generated_artifacts`` passes every detected category to
      ``migrate_category``.
    - Guard-triggered deploy (``SystemExit`` from ``guard_generated_artifacts``)
      calls auto-migration and, on success, proceeds to ``subprocess.Popen``.
    - When auto-migration fails, ``_deploy_status`` is set to ``"error"`` and
      ``Popen`` is never called.
"""

import importlib.util
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_modal_stub():
    stub = types.ModuleType("modal")
    stub.Image = MagicMock()
    stub.Image.debian_slim.return_value.apt_install.return_value.pip_install.return_value.run_commands.return_value = (
        MagicMock()
    )
    stub.App = MagicMock()
    stub.App.return_value.function = lambda **kw: (lambda f: f)
    stub.App.return_value.cls = lambda **kw: (lambda c: c)
    stub.Volume = MagicMock()
    stub.Volume.from_name.return_value = MagicMock()
    stub.Secret = MagicMock()
    stub.Secret.from_name.return_value = MagicMock()
    stub.web_server = lambda *a, **kw: (lambda f: f)
    stub.enter = lambda **kw: (lambda f: f)
    stub.exit = lambda: (lambda f: f)
    stub.method = lambda: (lambda f: f)
    stub.concurrent = lambda **kw: (lambda c: c)
    return stub


def _make_modal_client_stub():
    stub = types.ModuleType("modal_client")
    for fn_name in (
        "run_prompt",
        "run_prompt_stream",
        "get_object_info",
        "health_check",
        "download_model",
        "download_model_stream",
        "batch_download_models",
        "list_models",
        "delete_model",
        "sync_custom_nodes",
        "refresh_custom_nodes",
        "get_sync_status",
        "upload_model_to_volume",
        "upload_model_chunk",
        "resync_runtime",
        "get_runtime_state",
        "set_active_warmup_profile",
        "clear_cache",
        "set_workspace_resolver",
        "get_handle_cache_stats",
        "get_modal_app_name",
        "get_modal_class_name",
        "get_modal_lookup_target",
        "persist_validation_certificate",
    ):
        setattr(stub, fn_name, MagicMock())
    return stub


def _load_init_module():
    """Load ``__init__.py`` as an importable module with stubbed dependencies."""
    original_modal = sys.modules.pop("modal", None)
    original_modal_client = sys.modules.pop("modal_client", None)
    original_path = sys.path[:]
    sys.modules["modal"] = _make_modal_stub()
    sys.modules["modal_client"] = _make_modal_client_stub()
    module_name = f"modal_init_test_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, str(REPO_ROOT / "__init__.py")
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch("threading.Thread") as thread_cls:
            thread_cls.return_value.start.return_value = None
            spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original_path
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)
        if original_modal_client is not None:
            sys.modules["modal_client"] = original_modal_client
        else:
            sys.modules.pop("modal_client", None)
        sys.modules.pop(module_name, None)


class AutoMigrateHelperTests(unittest.TestCase):
    """Tests for the ``_auto_migrate_generated_artifacts`` helper."""

    def setUp(self):
        self.module = _load_init_module()

    def test_all_detected_categories_passed_to_migration(self):
        """Every category from _scan_generated_dirs is forwarded to migrate_category."""
        P = "/fake/plugin_root"
        D = "/fake/data_root"

        detected = {
            "output": 1024,
            ".experiments": 2048,
            "benchmark_logs": 512,
        }

        with (
            patch(
                "deployment_guard._scan_generated_dirs",
                return_value=detected,
            ),
            patch(
                "local_artifacts.get_plugin_root",
                return_value=P,
            ),
            patch(
                "local_artifacts.get_local_data_root",
                return_value=D,
            ),
            patch(
                "tools.migrate_local_artifacts.migrate_category"
            ) as mock_migrate,
            patch(
                "tools.migrate_local_artifacts.MigrationStats"
            ) as mock_stats_cls,
        ):
            mock_stats = mock_stats_cls.return_value
            result = self.module._auto_migrate_generated_artifacts()

        self.assertTrue(result)
        expected_calls = [
            call(".experiments", P, D, dry_run=False, stats=mock_stats),
            call("benchmark_logs", P, D, dry_run=False, stats=mock_stats),
            call("output", P, D, dry_run=False, stats=mock_stats),
        ]
        mock_migrate.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(mock_migrate.call_count, 3)

    def test_no_generated_dirs_returns_true(self):
        """When _scan_generated_dirs returns empty, helper returns True."""
        with (
            patch(
                "deployment_guard._scan_generated_dirs",
                return_value={},
            ) as mock_scan,
            patch(
                "tools.migrate_local_artifacts.migrate_category"
            ) as mock_migrate,
        ):
            result = self.module._auto_migrate_generated_artifacts()

        self.assertTrue(result)
        mock_migrate.assert_not_called()

    def test_migration_systemexit_returns_false(self):
        """When migrate_category raises SystemExit, helper returns False."""
        with (
            patch(
                "deployment_guard._scan_generated_dirs",
                return_value={"output": 42},
            ),
            patch(
                "tools.migrate_local_artifacts.migrate_category",
                side_effect=SystemExit(1),
            ),
        ):
            result = self.module._auto_migrate_generated_artifacts()

        self.assertFalse(result)

    def test_migration_exception_returns_false(self):
        """When migrate_category raises an arbitrary exception, helper returns False."""
        with (
            patch(
                "deployment_guard._scan_generated_dirs",
                return_value={"output": 42},
            ),
            patch(
                "tools.migrate_local_artifacts.migrate_category",
                side_effect=RuntimeError("disk full"),
            ),
        ):
            result = self.module._auto_migrate_generated_artifacts()

        self.assertFalse(result)


class DeployBackgroundAutoMigrateTests(unittest.TestCase):
    """Tests for the auto-migration path inside _run_deploy_background."""

    def setUp(self):
        self.module = _load_init_module()
        # Reset deploy status after module load
        self.module._deploy_status = {"state": "idle", "message": ""}
        self.workspace = {
            "id": "ws-test-1",
            "label": "Test Workspace",
            "token_id": "ak-test-id",
            "token_secret": "as-test-secret",
        }

    @patch("subprocess.Popen")
    def test_guard_triggered_auto_migrate_success_proceeds_to_deploy(self, mock_popen):
        """SystemExit from guard → auto-migrate succeeds → deploy (Popen) is called."""
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = MagicMock(side_effect=["line1\n", ""])
        mock_process.poll.return_value = 0
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        with (
            patch(
                "deployment_guard.guard_generated_artifacts",
                side_effect=SystemExit(1),
            ) as mock_guard,
            patch.object(
                self.module, "_auto_migrate_generated_artifacts",
                return_value=True,
            ),
            patch.object(self.module, "_find_modal_executable",
                         return_value="/usr/bin/modal"),
        ):
            self.module._run_deploy_background(
                workspace=self.workspace,
                custom_nodes_fingerprint="fp123",
            )

        mock_guard.assert_called_once()
        # Popen should have been called (deploy proceeded)
        mock_popen.assert_called_once()

        # Deploy status should reflect progress past the guard
        self.assertNotEqual(
            self.module._deploy_status.get("state"), "error",
            msg="Deploy status should not be 'error' when auto-migration succeeded",
        )

    @patch("subprocess.Popen")
    def test_guard_triggered_auto_migrate_failure_prevents_popen(self, mock_popen):
        """SystemExit from guard → auto-migrate fails → error status, no Popen."""
        with (
            patch(
                "deployment_guard.guard_generated_artifacts",
                side_effect=SystemExit(1),
            ) as mock_guard,
            patch.object(
                self.module, "_auto_migrate_generated_artifacts",
                return_value=False,
            ),
        ):
            self.module._run_deploy_background(
                workspace=self.workspace,
                custom_nodes_fingerprint="fp123",
            )

        mock_guard.assert_called_once()
        # Popen should NOT have been called
        mock_popen.assert_not_called()

        # Deploy status must be error with an auto-migration failure message
        self.assertEqual(
            self.module._deploy_status.get("state"), "error",
        )
        msg = self.module._deploy_status.get("message", "")
        self.assertIn("Automatic migration", msg)
        self.assertIn("failed", msg.lower())
        self.assertIn("tools/migrate_local_artifacts.py", msg)

    @patch("subprocess.Popen")
    def test_guard_no_systemexit_skips_auto_migration(self, mock_popen):
        """When guard_generated_artifacts does NOT raise SystemExit, auto-migrate is not called."""
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = MagicMock(side_effect=["line1\n", ""])
        mock_process.poll.return_value = 0
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        with (
            patch(
                "deployment_guard.guard_generated_artifacts",
                return_value=None,
            ) as mock_guard,
            patch.object(
                self.module, "_auto_migrate_generated_artifacts"
            ) as mock_auto,
            patch.object(self.module, "_find_modal_executable",
                         return_value="/usr/bin/modal"),
        ):
            self.module._run_deploy_background(
                workspace=self.workspace,
                custom_nodes_fingerprint="fp123",
            )

        mock_guard.assert_called_once()
        mock_auto.assert_not_called()
        mock_popen.assert_called_once()

    @patch("subprocess.Popen")
    def test_auto_migrate_failure_systemexit_sets_error(self, mock_popen):
        """Verify the _deploy_status error message is clear on auto-migration failure."""
        with (
            patch(
                "deployment_guard.guard_generated_artifacts",
                side_effect=SystemExit(1),
            ) as mock_guard,
            patch.object(
                self.module, "_auto_migrate_generated_artifacts",
                return_value=False,
            ),
        ):
            self.module._run_deploy_background(
                workspace=self.workspace,
                custom_nodes_fingerprint="fp123",
            )

        mock_guard.assert_called_once()
        mock_popen.assert_not_called()
        self.assertEqual(self.module._deploy_status.get("state"), "error")
        self.assertIn(
            "Automatic migration",
            self.module._deploy_status.get("message", ""),
        )

    @patch("subprocess.Popen")
    def test_auto_migrate_exception_escapes_to_error(self, mock_popen):
        """An unexpected exception from _auto_migrate_generated_artifacts is caught by deploy."""
        with (
            patch(
                "deployment_guard.guard_generated_artifacts",
                side_effect=SystemExit(1),
            ) as mock_guard,
            patch.object(
                self.module, "_auto_migrate_generated_artifacts",
                side_effect=RuntimeError("unexpected crash"),
            ),
        ):
            self.module._run_deploy_background(
                workspace=self.workspace,
                custom_nodes_fingerprint="fp123",
            )

        mock_guard.assert_called_once()
        mock_popen.assert_not_called()
        self.assertEqual(self.module._deploy_status.get("state"), "error")


if __name__ == "__main__":
    unittest.main()
