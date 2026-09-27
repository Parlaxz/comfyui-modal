"""Focused tests for V2 static Modal target stability fix.

Verifies:
- Two fresh ModalTransport objects / fresh caches call Cls.from_name with
  identical app/class/environment args.
- Cls.with_options is never called.
- Ambient MODAL_ENVIRONMENT does not affect target resolution.
- Explicit COMFYMODAL_V2_ENVIRONMENT is honored.
- Diagnostic line contains with_options_used=0.

Does NOT deploy or invoke Modal remotely — all Modal SDK calls are mocked.
"""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import MagicMock, patch

from comfymodal_runtime.modal_transport import HandleCache, ModalTransport


class TestV2StaticModalTarget(unittest.TestCase):
    """V2 Modal target is stable: no with_options, no MODAL_ENVIRONMENT
    fallback, cache key is purely target identity."""

    def setUp(self):
        self._saved_env = {}
        for key in ("COMFYMODAL_V2_ENVIRONMENT", "MODAL_ENVIRONMENT",
                     "COMFYMODAL_V2_CLOUD", "COMFYMODAL_V2_APP_NAME",
                     "COMFYMODAL_V2_CLASS_NAME"):
            self._saved_env[key] = os.environ.pop(key, None)
        self._workspace = {
            "id": "test-workspace",
            "token_id": "test-token-id",
            "token_secret": "test-token-secret",
        }

    def tearDown(self):
        for key, val in self._saved_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_transport(self) -> ModalTransport:
        """Return a ModalTransport with an isolated (fresh) handle cache."""
        return ModalTransport(handle_cache=HandleCache())

    def _patch_modal_sdk(self):
        """Return a context manager that mocks ``_modal`` so all Modal SDK
        calls are captured without real API invocation."""
        return patch(
            "comfymodal_runtime.modal_transport._modal",
            spec=["Client", "Cls"],
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_two_fresh_caches_call_from_name_with_identical_args(self):
        """Two ModalTransport objects with fresh caches both invoke
        Cls.from_name with identical app/class/environment arguments."""
        call_args_list = []

        with self._patch_modal_sdk() as mock_modal:
            mock_client = MagicMock()
            mock_cls_handle = MagicMock()
            mock_modal.Client.from_credentials.return_value = mock_client
            mock_modal.Cls.from_name.return_value = mock_cls_handle

            t1 = self._make_transport()
            t1._v2_handle(workspace=self._workspace)

            t2 = self._make_transport()
            t2._v2_handle(workspace=self._workspace)

            call_args_list = mock_modal.Cls.from_name.call_args_list

        self.assertEqual(len(call_args_list), 2)
        self.assertEqual(call_args_list[0], call_args_list[1],
                         "Both calls to Cls.from_name must use identical args")

    def test_with_options_never_called(self):
        """Cls.with_options must never be invoked on the class handle."""
        with self._patch_modal_sdk() as mock_modal:
            mock_client = MagicMock()
            mock_cls_handle = MagicMock()
            mock_modal.Client.from_credentials.return_value = mock_client
            mock_modal.Cls.from_name.return_value = mock_cls_handle

            transport = self._make_transport()
            transport._v2_handle(workspace=self._workspace)

        mock_cls_handle.with_options.assert_not_called()

    def test_ambient_modal_environment_ignored(self):
        """When only MODAL_ENVIRONMENT is set (not
        COMFYMODAL_V2_ENVIRONMENT), Cls.from_name is called with
        environment_name=None (default deployed environment)."""
        os.environ["MODAL_ENVIRONMENT"] = "staging"

        with self._patch_modal_sdk() as mock_modal:
            mock_client = MagicMock()
            mock_cls_handle = MagicMock()
            mock_modal.Client.from_credentials.return_value = mock_client
            mock_modal.Cls.from_name.return_value = mock_cls_handle

            transport = self._make_transport()
            transport._v2_handle(workspace=self._workspace)

        mock_modal.Cls.from_name.assert_called_once()
        _args, kwargs = mock_modal.Cls.from_name.call_args
        self.assertIsNone(
            kwargs.get("environment_name"),
            "Ambient MODAL_ENVIRONMENT must NOT be passed to Cls.from_name",
        )

    def test_explicit_v2_environment_honored(self):
        """When COMFYMODAL_V2_ENVIRONMENT is explicitly set, it is
        forwarded to Cls.from_name."""
        os.environ["COMFYMODAL_V2_ENVIRONMENT"] = "production"

        with self._patch_modal_sdk() as mock_modal:
            mock_client = MagicMock()
            mock_cls_handle = MagicMock()
            mock_modal.Client.from_credentials.return_value = mock_client
            mock_modal.Cls.from_name.return_value = mock_cls_handle

            transport = self._make_transport()
            transport._v2_handle(workspace=self._workspace)

        mock_modal.Cls.from_name.assert_called_once()
        _args, kwargs = mock_modal.Cls.from_name.call_args
        self.assertEqual(
            kwargs.get("environment_name"), "production",
        )

    def test_diagnostic_has_with_options_used_zero(self):
        """The [v2.modal_target] diagnostic line includes
        with_options_used=0 and cloud_override=absent."""
        captured = io.StringIO()

        with self._patch_modal_sdk() as mock_modal, \
             patch("sys.stdout", captured):
            mock_client = MagicMock()
            mock_cls_handle = MagicMock()
            mock_modal.Client.from_credentials.return_value = mock_client
            mock_modal.Cls.from_name.return_value = mock_cls_handle

            transport = self._make_transport()
            transport._v2_handle(workspace=self._workspace)

        output = captured.getvalue()
        self.assertIn("[v2.modal_target]", output)
        self.assertIn("with_options_used=0", output)
        self.assertIn("cloud_override=absent", output)
        # Sanity check: the diagnostic includes app and class names
        self.assertIn("app=stable-modal-comfy-v2-shadow", output)
        self.assertIn("class=ModalRuntimeEntrypointV2", output)

    def test_cache_key_excludes_cloud_and_gpu(self):
        """The cache key (HandleCacheKey) contains only workspace, app_name,
        target, and environment — no cloud, gpu, or factory_identity fields."""
        from comfymodal_runtime.modal_transport import HandleCacheKey

        key = HandleCacheKey("ws", "app", "cls", environment="env")

        # Verify the expected fields exist
        self.assertEqual(key.workspace, "ws")
        self.assertEqual(key.app_name, "app")
        self.assertEqual(key.target, "cls")
        self.assertEqual(key.environment, "env")

        # Verify cloud, gpu, factory_identity are absent
        with self.assertRaises(AttributeError):
            _ = key.cloud
        with self.assertRaises(AttributeError):
            _ = key.gpu
        with self.assertRaises(AttributeError):
            _ = key.factory_identity

    def test_handle_cache_hit_still_works_with_new_key(self):
        """A cached handle must be returned on repeated call with same
        workspace — new HandleCacheKey still matches."""
        with self._patch_modal_sdk() as mock_modal:
            mock_client = MagicMock()
            mock_cls_handle = MagicMock()
            mock_modal.Client.from_credentials.return_value = mock_client
            mock_modal.Cls.from_name.return_value = mock_cls_handle

            transport = self._make_transport()
            h1 = transport._v2_handle(workspace=self._workspace)
            mock_modal.Cls.from_name.assert_called_once()

            h2 = transport._v2_handle(workspace=self._workspace)
            # from_name should still have been called only once (cache hit)
            self.assertEqual(mock_modal.Cls.from_name.call_count, 1)
            self.assertIs(h1, h2, "Cache hit must return the same object")


if __name__ == "__main__":
    unittest.main()
