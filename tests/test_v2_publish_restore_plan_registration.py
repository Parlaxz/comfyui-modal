"""Focused tests for publish_restore_plan_remote registration and diagnostics.

Verifies:
- Registration source (app.function(...)) contains startup_timeout=120,
  retries=0, env={_PUBLISHER_MARKER: "1"}.
- Function body contains entry/success/error diagnostics with flush.
- Exception handler re-raises.
- build_modal_resources early-return when publisher marker is set.

Does NOT invoke Modal remotely — all assertions operate on source text
analysis (AST-based extraction from the file).
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Path to the production source file.
_MODAL_APP_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "modal_app.py"


def _registration_block() -> str:
    """Return the publish_restore_plan_remote registration block from the
    app.function(...) call onward."""
    source = _MODAL_APP_PATH.read_text(encoding="utf-8")
    idx = source.index("publish_restore_plan_remote")
    return source[idx:]


# ── Registration source tests ─────────────────────────────────────────────


class TestPublishRestorePlanRegistration(unittest.TestCase):
    """Registration call to app.function(...) includes all required kwargs."""

    def test_startup_timeout_in_registration(self):
        """The app.function(...) call for publish_restore_plan_remote
        includes startup_timeout=120 alongside existing timeout=300,
        min_containers=0, scaledown_window."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "startup_timeout=120",
            source,
            "startup_timeout=120 must appear in modal_app.py",
        )
        block = _registration_block()
        self.assertIn("timeout=300", block)
        self.assertIn("startup_timeout=120", block)
        block_after_timeout = block.split("timeout=300")[1]
        self.assertIn(
            "startup_timeout=120",
            block_after_timeout.split("scaledown_window")[0],
            "startup_timeout=120 should appear between timeout=300 and "
            "scaledown_window in the registration call",
        )

    def test_retries_zero_in_registration(self):
        """Registration includes retries=0."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "retries=0",
            source,
            "retries=0 must appear in modal_app.py",
        )
        block = _registration_block()
        self.assertIn("retries=0", block)

    def test_env_marker_in_registration(self):
        """Registration includes env={_PUBLISHER_MARKER: "1"}."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "_PUBLISHER_MARKER",
            source,
            "_PUBLISHER_MARKER constant must be defined",
        )
        self.assertIn(
            'env={_PUBLISHER_MARKER: "1"}',
            source,
            "registration must include env={_PUBLISHER_MARKER: '1'}",
        )


# ── Publisher marker constant tests ────────────────────────────────────────


class TestPublisherMarkerConstant(unittest.TestCase):
    """_PUBLISHER_MARKER constant is defined and has the expected value."""

    def test_marker_constant_defined(self):
        """The _PUBLISHER_MARKER constant equals COMFYMODAL_PUBLISHER_CONTAINER."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            '_PUBLISHER_MARKER = "COMFYMODAL_PUBLISHER_CONTAINER"',
            source,
            "_PUBLISHER_MARKER must be defined with value COMFYMODAL_PUBLISHER_CONTAINER",
        )


# ── build_modal_resources early-return tests ──────────────────────────────


def _null_resources(spec: Any = None) -> dict[str, Any]:
    """Return the expected null-resource mapping for the publisher branch."""
    from comfymodal_runtime.modal_app import ModalRuntimeSpec
    return {
        "app": None,
        "image": None,
        "models_volume": None,
        "custom_nodes_volume": None,
        "runtime_state_volume": None,
        "profile_volume": None,
        "source_identity": None,
        "spec": spec or ModalRuntimeSpec(),
    }


class TestBuildModalResourcesMarker(unittest.TestCase):
    """build_modal_resources returns null resources when publisher marker=1
    without calling heavyweight helpers."""

    def test_early_return_when_marker_set(self):
        """When COMFYMODAL_PUBLISHER_CONTAINER=1, build_modal_resources returns
        null resources and does not call _local_custom_nodes_root,
        build_deployment_identity, or _reference_image."""
        from comfymodal_runtime.modal_app import build_modal_resources, _PUBLISHER_MARKER, ModalRuntimeSpec
        with patch.dict(os.environ, {_PUBLISHER_MARKER: "1"}, clear=False):
            with patch(
                "comfymodal_runtime.modal_app._local_custom_nodes_root",
                MagicMock(side_effect=RuntimeError("_local_custom_nodes_root should not be called")),
            ):
                with patch(
                    "comfymodal_runtime.modal_app.build_deployment_identity",
                    MagicMock(side_effect=RuntimeError("build_deployment_identity should not be called")),
                ):
                    with patch(
                        "comfymodal_runtime.modal_app._reference_image",
                        MagicMock(side_effect=RuntimeError("_reference_image should not be called")),
                    ):
                        spec = ModalRuntimeSpec()
                        result = build_modal_resources(spec=spec)
        expected = _null_resources(spec)
        self.assertEqual(result, expected)


# ── Function diagnostics tests ────────────────────────────────────────────


class TestPublishRestorePlanDiagnostics(unittest.TestCase):
    """publish_restore_plan_remote has flushed entry/success/error diagnostics
    and re-raises on exception."""

    def _get_func_source(self) -> str:
        """Extract the source text of publish_restore_plan_remote from
        modal_app.py using AST parsing.  Avoids inspect.getsource which
        fails when Modal wraps the function in its own Function class."""
        import ast
        source = _MODAL_APP_PATH.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "publish_restore_plan_remote":
                lines = source.splitlines()
                func_lines = lines[node.lineno - 1 : node.end_lineno]
                return "\n".join(func_lines)
        self.fail("publish_restore_plan_remote function not found in modal_app.py")

    def test_entry_diagnostic(self):
        """Function prints an entry diagnostic at start with flush=True."""
        src = self._get_func_source()
        self.assertIn(
            '"[publish_restore_plan] entry"',
            src,
            "missing entry diagnostic",
        )
        self.assertIn(
            "flush=True",
            src,
            "entry print must flush",
        )

    def test_success_diagnostic(self):
        """Function prints a success diagnostic with elapsed_ms."""
        src = self._get_func_source()
        self.assertIn(
            "[publish_restore_plan] success",
            src,
            "missing success diagnostic",
        )
        self.assertIn(
            "elapsed_ms",
            src,
            "success diagnostic must include elapsed_ms",
        )

    def test_error_diagnostic_and_reraise(self):
        """On exception the function prints an error diagnostic with
        elapsed_ms and exception_type, then re-raises."""
        src = self._get_func_source()
        # Must use except Exception as exc:
        self.assertIn(
            "except Exception as exc:",
            src,
            "must catch Exception as exc",
        )
        # Error diagnostic message includes elapsed_ms and exception_type
        self.assertIn(
            "[publish_restore_plan] error",
            src,
            "missing error diagnostic",
        )
        self.assertIn(
            "exception_type",
            src,
            "error diagnostic must include exception_type",
        )
        # Re-raise: a bare 'raise' statement after the error block
        self.assertIn(
            "\n        raise",
            src,
            "exception handler must re-raise",
        )


# ── build_modal_resources profile Volume tests ──────────────────────────────


class TestBuildModalResourcesProfileVolume(unittest.TestCase):
    """build_modal_resources creates profile Volume only when full-trace
    is enabled, and never when disabled.  Publisher & fallback paths
    always have profile_volume: None."""

    def setUp(self):
        from comfymodal_runtime.modal_app import _V2_FULL_TRACE_ENABLED
        self._orig_full_trace = _V2_FULL_TRACE_ENABLED

    def tearDown(self):
        from comfymodal_runtime.modal_app import _V2_FULL_TRACE_ENABLED as _flag
        # Restore via direct attribute set (cannot reimport)
        import comfymodal_runtime.modal_app as _ma
        _ma._V2_FULL_TRACE_ENABLED = self._orig_full_trace

    def test_profile_volume_created_when_enabled(self):
        """When _V2_FULL_TRACE_ENABLED is True and Modal is available,
        build_modal_resources creates profile_volume via
        _modal.Volume.from_name exactly once."""
        from comfymodal_runtime.modal_app import (
            build_modal_resources, ModalRuntimeSpec,
        )
        mock_volume = MagicMock()
        mock_image = MagicMock()
        mock_image.add_local_python_source.return_value = mock_image

        from_name_calls: list[str] = []

        class FakeVolume:
            @staticmethod
            def from_name(name, create_if_missing=False):
                from_name_calls.append(name)
                return mock_volume

        class FakeModal:
            Volume = FakeVolume

            @staticmethod
            def App(*args, **kwargs):
                return MagicMock()

        with patch("comfymodal_runtime.modal_app._modal", FakeModal), \
             patch("comfymodal_runtime.modal_app._local_custom_nodes_root",
                   return_value=MagicMock()), \
             patch("comfymodal_runtime.modal_app.build_deployment_identity",
                   return_value=MagicMock()), \
             patch("comfymodal_runtime.modal_app._reference_image",
                   return_value=mock_image):
            import comfymodal_runtime.modal_app as _ma
            _ma._V2_FULL_TRACE_ENABLED = True
            spec = ModalRuntimeSpec()
            result = build_modal_resources(spec=spec)

        self.assertIsNotNone(result["profile_volume"],
                             "profile_volume must not be None when full-trace is enabled")
        self.assertEqual(result["profile_volume"], mock_volume)
        # At least one from_name call should reference the profile volume name
        profile_calls = [n for n in from_name_calls if "v2-profiles" in n]
        self.assertGreaterEqual(len(profile_calls), 1,
                                "Volume.from_name must be called for profile volume name")
        # Models, custom_nodes, runtime_state volumes also exist
        self.assertIsNotNone(result["models_volume"])
        self.assertIsNotNone(result["custom_nodes_volume"])
        self.assertIsNotNone(result["runtime_state_volume"])

    def test_profile_volume_none_when_disabled(self):
        """When _V2_FULL_TRACE_ENABLED is False, profile_volume is None
        and Volume.from_name is NOT called for the profile volume name."""
        from comfymodal_runtime.modal_app import (
            build_modal_resources, ModalRuntimeSpec,
        )
        mock_volume = MagicMock()
        mock_image = MagicMock()
        mock_image.add_local_python_source.return_value = mock_image

        from_name_calls: list[str] = []

        class FakeVolume:
            @staticmethod
            def from_name(name, create_if_missing=False):
                from_name_calls.append(name)
                return mock_volume

        class FakeModal:
            Volume = FakeVolume

            @staticmethod
            def App(*args, **kwargs):
                return MagicMock()

        with patch("comfymodal_runtime.modal_app._modal", FakeModal), \
             patch("comfymodal_runtime.modal_app._local_custom_nodes_root",
                   return_value=MagicMock()), \
             patch("comfymodal_runtime.modal_app.build_deployment_identity",
                   return_value=MagicMock()), \
             patch("comfymodal_runtime.modal_app._reference_image",
                   return_value=mock_image):
            import comfymodal_runtime.modal_app as _ma
            _ma._V2_FULL_TRACE_ENABLED = False
            spec = ModalRuntimeSpec()
            result = build_modal_resources(spec=spec)

        self.assertIsNone(result["profile_volume"],
                          "profile_volume must be None when full-trace is disabled")
        # Volume.from_name was called for models, custom_nodes, runtime_state
        # but NOT for the profile volume name
        profile_calls = [n for n in from_name_calls if "profile" in n.lower() or "v2-profiles" in n]
        self.assertEqual(
            len(profile_calls), 0,
            "Volume.from_name must NOT be called for profile volume when disabled",
        )


# ── _register_remote_entrypoint profile mount tests ─────────────────────────


class TestRegisterRemoteEntrypointProfileMount(unittest.TestCase):
    """_register_remote_entrypoint mounts profile path only when full-trace
    is enabled, retains existing mounts, and raises when profile_volume is
    unexpectedly None."""

    def setUp(self):
        from comfymodal_runtime.modal_app import _V2_FULL_TRACE_ENABLED
        self._orig_full_trace = _V2_FULL_TRACE_ENABLED

    def tearDown(self):
        import comfymodal_runtime.modal_app as _ma
        _ma._V2_FULL_TRACE_ENABLED = self._orig_full_trace

    def _make_fake_app(self):
        class FakeApp:
            def __init__(self):
                self.kwargs = None
            def cls(self, **kwargs):
                self.kwargs = kwargs
                return lambda cls: cls
        return FakeApp()

    def _make_fake_modal(self):
        class FakeModal:
            @staticmethod
            def concurrent(**kwargs):
                return lambda cls: cls
        return FakeModal

    def test_mounts_profile_path_when_enabled(self):
        """When _V2_FULL_TRACE_ENABLED is True, _volumes includes the
        profile path key."""
        from comfymodal_runtime.modal_app import (
            _register_remote_entrypoint, ModalRuntimeSpec, PROFILE_PATH,
        )
        app = self._make_fake_app()
        mock_pv = MagicMock()
        resources = {
            "app": app,
            "models_volume": MagicMock(),
            "custom_nodes_volume": MagicMock(),
            "runtime_state_volume": MagicMock(),
            "profile_volume": mock_pv,
        }
        spec = ModalRuntimeSpec(app_name="variance-test-app")

        import comfymodal_runtime.modal_app as _ma
        _ma._V2_FULL_TRACE_ENABLED = True
        with patch("comfymodal_runtime.modal_app._modal", self._make_fake_modal()), \
             patch("comfymodal_runtime.modal_app._build_decorated_v2_class",
                   return_value=object):
            _register_remote_entrypoint(resources, spec)

        self.assertIsNotNone(app.kwargs, "app.cls must have been called")
        volumes = app.kwargs.get("volumes", {})
        self.assertIn(
            spec.profile_path, volumes,
            f"profile_path {spec.profile_path!r} must be in volumes when enabled",
        )
        self.assertIs(volumes[spec.profile_path], mock_pv,
                      "profile_volume must be mounted at profile_path")

    def test_no_profile_mount_when_disabled(self):
        """When _V2_FULL_TRACE_ENABLED is False, _volumes does NOT include
        the profile path, but standard volumes are still present."""
        from comfymodal_runtime.modal_app import (
            _register_remote_entrypoint, ModalRuntimeSpec,
        )
        app = self._make_fake_app()
        resources = {
            "app": app,
            "models_volume": MagicMock(),
            "custom_nodes_volume": MagicMock(),
            "runtime_state_volume": MagicMock(),
        }
        spec = ModalRuntimeSpec()

        import comfymodal_runtime.modal_app as _ma
        _ma._V2_FULL_TRACE_ENABLED = False
        with patch("comfymodal_runtime.modal_app._modal", self._make_fake_modal()), \
             patch("comfymodal_runtime.modal_app._build_decorated_v2_class",
                   return_value=object):
            _register_remote_entrypoint(resources, spec)

        self.assertIsNotNone(app.kwargs, "app.cls must have been called")
        volumes = app.kwargs.get("volumes", {})
        self.assertNotIn(
            spec.profile_path, volumes,
            f"profile_path must NOT be in volumes when disabled",
        )
        # Standard volumes must still be present
        self.assertIn(spec.models_path, volumes)
        self.assertIn(spec.custom_nodes_path, volumes)
        self.assertIn(spec.runtime_state_path, volumes)

    def test_raises_when_profile_volume_none_and_enabled(self):
        """When _V2_FULL_TRACE_ENABLED but profile_volume is None in
        resources, _register_remote_entrypoint raises RuntimeError."""
        from comfymodal_runtime.modal_app import (
            _register_remote_entrypoint, ModalRuntimeSpec,
        )
        app = self._make_fake_app()
        resources = {
            "app": app,
            "models_volume": MagicMock(),
            "custom_nodes_volume": MagicMock(),
            "runtime_state_volume": MagicMock(),
            "profile_volume": None,
        }
        spec = ModalRuntimeSpec()

        import comfymodal_runtime.modal_app as _ma
        _ma._V2_FULL_TRACE_ENABLED = True
        with patch("comfymodal_runtime.modal_app._modal", self._make_fake_modal()), \
             patch("comfymodal_runtime.modal_app._build_decorated_v2_class",
                   return_value=object):
            with self.assertRaises(RuntimeError) as ctx:
                _register_remote_entrypoint(resources, spec)
        self.assertIn("profile_volume is None", str(ctx.exception))

    def test_existing_mounts_retained_when_profile_added(self):
        """When full-trace is enabled, the standard mounts (models_path,
        custom_nodes_path, runtime_state_path) are still present alongside
        the profile mount."""
        from comfymodal_runtime.modal_app import (
            _register_remote_entrypoint, ModalRuntimeSpec,
        )
        app = self._make_fake_app()
        mock_pv = MagicMock()
        resources = {
            "app": app,
            "models_volume": MagicMock(),
            "custom_nodes_volume": MagicMock(),
            "runtime_state_volume": MagicMock(),
            "profile_volume": mock_pv,
        }
        spec = ModalRuntimeSpec()

        import comfymodal_runtime.modal_app as _ma
        _ma._V2_FULL_TRACE_ENABLED = True
        with patch("comfymodal_runtime.modal_app._modal", self._make_fake_modal()), \
             patch("comfymodal_runtime.modal_app._build_decorated_v2_class",
                   return_value=object):
            _register_remote_entrypoint(resources, spec)

        volumes = app.kwargs.get("volumes", {})
        self.assertEqual(len(volumes), 4,
                         "Expected 4 volumes: models, custom_nodes, runtime_state, profile")
        self.assertIn(spec.models_path, volumes)
        self.assertIn(spec.custom_nodes_path, volumes)
        self.assertIn(spec.runtime_state_path, volumes)
        self.assertIn(spec.profile_path, volumes)


# ── _register_remote_entrypoint env= propagation test ────────────────────────


class TestRegisterRemoteEntrypointEnvPropagation(unittest.TestCase):
    """_register_remote_entrypoint passes _runtime_env() values through
    to app.cls(env=...)."""

    def test_env_contains_all_trace_and_profile_keys(self):
        """The env dict passed to app.cls includes all required
        full-trace and profile propagation keys with their expected values."""
        from comfymodal_runtime.modal_app import (
            _register_remote_entrypoint, ModalRuntimeSpec,
            _V2_FULL_TRACE_ENABLED,
        )

        class FakeApp:
            def __init__(self):
                self.kwargs = None
            def cls(self, **kwargs):
                self.kwargs = kwargs
                return lambda cls: cls

        class FakeModal:
            @staticmethod
            def concurrent(**kwargs):
                return lambda cls: cls

        app = FakeApp()
        resources = {
            "app": app,
            "models_volume": MagicMock(),
            "custom_nodes_volume": MagicMock(),
            "runtime_state_volume": MagicMock(),
            "profile_volume": MagicMock(),
        }
        spec = ModalRuntimeSpec()

        with patch("comfymodal_runtime.modal_app._modal", FakeModal), \
             patch("comfymodal_runtime.modal_app._build_decorated_v2_class",
                   return_value=object):
            import comfymodal_runtime.modal_app as _ma
            _ma._V2_FULL_TRACE_ENABLED = False  # ensure clean env
            _register_remote_entrypoint(resources, spec)

        self.assertIsNotNone(app.kwargs, "app.cls must have been called")
        env = app.kwargs.get("env", {})
        self.assertEqual(env.get("COMFYMODAL_V2_APP_NAME"), spec.app_name)
        required_env_keys = [
            "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
            "COMFYMODAL_V2_UNET_PRETOUCH",
            "COMFYMODAL_V2_FULL_TRACE",
            "COMFYMODAL_V2_FULL_TRACE_TORCH",
            "COMFYMODAL_V2_FULL_TRACE_ENTRIES",
            "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS",
            "COMFYMODAL_V2_PROFILE_VOLUME",
        ]
        for key in required_env_keys:
            self.assertIn(key, env, f"Required env key {key!r} missing from app.cls(env=)")
            # Value should be a non-empty string
            self.assertIsInstance(env[key], str)
            self.assertGreater(len(env[key]), 0)
