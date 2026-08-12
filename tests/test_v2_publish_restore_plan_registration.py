"""Focused tests for publish_restore_plan registration and diagnostics.

Covers the CURRENT code (no ``_PUBLISHER_MARKER`` / ``startup_timeout=120``
era — those were removed):

- ``publish_restore_plan`` is registered on the V2 entrypoint via
  ``_modal.method()`` and delegates to the module-level
  ``_publish_restore_plan_remote`` body.
- ``_publish_restore_plan_remote`` contains flushed entry/success/error
  diagnostics and re-raises on exception.
- The opt-in ``COMFYMODAL_V2_PUBLISH_RESTORE_PLAN`` flag gates the remote
  publication: default (unset / "0") disables it (``publish_restore_plan_enabled()``
  is False); a truthy value enables the legacy publisher path.
- ``build_modal_resources`` still constructs the runtime-state volume used by
  the publisher.

Does NOT invoke Modal remotely — all assertions operate on source text
analysis (AST-based extraction from the file) or CPU-only unit checks.
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
    """Return the source from the publish_restore_plan method registration
    (inside ``_build_decorated_v2_class``) onward."""
    source = _MODAL_APP_PATH.read_text(encoding="utf-8")
    idx = source.index('"publish_restore_plan", "run_rehoming_experiment"')
    return source[idx:]


# ── Registration source tests ─────────────────────────────────────────────


class TestPublishRestorePlanRegistration(unittest.TestCase):
    """``publish_restore_plan`` is registered via ``_modal.method()`` and is
    listed in the wrapped / non-workflow method sets."""

    def test_registered_via_modal_method(self):
        """The method is registered with ``_modal.method()``."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'setattr(cls, "publish_restore_plan", _modal.method()(cls.publish_restore_plan))',
            source,
            "publish_restore_plan must be registered via _modal.method()",
        )

    def test_listed_in_methods_to_wrap(self):
        """The method is in ``_METHODS_TO_WRAP`` so lazy-init wraps it."""
        block = _registration_block()
        self.assertIn('"publish_restore_plan"', block)
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        methods_block_start = source.index("_METHODS_TO_WRAP = (")
        methods_block_end = source.index("_NON_WORKFLOW_METHODS")
        methods_block = source[methods_block_start:methods_block_end]
        self.assertIn(
            '"publish_restore_plan"',
            methods_block,
            "publish_restore_plan must be in _METHODS_TO_WRAP",
        )

    def test_listed_in_non_workflow_methods(self):
        """The method is in ``_NON_WORKFLOW_METHODS`` (no fabricated graph
        waterfall on its dict result)."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        non_workflow_block = source[source.index("_NON_WORKFLOW_METHODS"):]
        self.assertIn(
            '"publish_restore_plan"',
            non_workflow_block,
            "publish_restore_plan must be in _NON_WORKFLOW_METHODS",
        )

    def test_method_delegates_to_remote_body(self):
        """The entrypoint method body delegates to
        ``_publish_restore_plan_remote(plan_payload, snapshot_seed=...)``."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "result = _publish_restore_plan_remote(plan_payload, snapshot_seed=snapshot_seed)",
            source,
            "publish_restore_plan must delegate to _publish_restore_plan_remote",
        )


# ── Function diagnostics tests ────────────────────────────────────────────


class TestPublishRestorePlanDiagnostics(unittest.TestCase):
    """``_publish_restore_plan_remote`` has flushed entry/success/error
    diagnostics and re-raises on exception."""

    def _get_func_source(self) -> str:
        """Extract the source text of _publish_restore_plan_remote from
        modal_app.py using AST parsing.  Avoids inspect.getsource which
        fails when Modal wraps the function in its own Function class."""
        import ast
        source = _MODAL_APP_PATH.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_publish_restore_plan_remote":
                lines = source.splitlines()
                func_lines = lines[node.lineno - 1 : node.end_lineno]
                return "\n".join(func_lines)
        self.fail("_publish_restore_plan_remote function not found in modal_app.py")

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
        self.assertIn(
            "except Exception as exc:",
            src,
            "must catch Exception as exc",
        )
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
        self.assertIn(
            "\n        raise",
            src,
            "exception handler must re-raise",
        )


# ── Opt-in publish-restore-plan flag tests ────────────────────────────────


class TestPublishRestorePlanFlag(unittest.TestCase):
    """``COMFYMODAL_V2_PUBLISH_RESTORE_PLAN`` gates the legacy remote
    publication: default off, opt-in on."""

    def test_flag_defaults_disabled(self):
        """Unset / "0" → publish_restore_plan_enabled() is False (default
        production path performs no remote publish RPC)."""
        from comfymodal_runtime.execution_seed import publish_restore_plan_enabled
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYMODAL_V2_PUBLISH_RESTORE_PLAN", None)
            self.assertFalse(publish_restore_plan_enabled())
        with patch.dict(os.environ, {"COMFYMODAL_V2_PUBLISH_RESTORE_PLAN": "0"}, clear=False):
            self.assertFalse(publish_restore_plan_enabled())

    def test_flag_opt_in_enables(self):
        """Truthy flag → publish_restore_plan_enabled() is True (legacy
        publisher path kept for diagnostics)."""
        from comfymodal_runtime.execution_seed import publish_restore_plan_enabled
        with patch.dict(os.environ, {"COMFYMODAL_V2_PUBLISH_RESTORE_PLAN": "1"}, clear=False):
            self.assertTrue(publish_restore_plan_enabled())

    def test_harness_publisher_resolution_is_flag_gated(self):
        """The benchmark harness constructs the remote publisher only when
        the flag is truthy; otherwise it passes None so execute_plan performs
        exactly ONE Modal submission (run_plan_stream)."""
        import tools.benchmark_v2_direct as bench
        stub_transport = MagicMock()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYMODAL_V2_PUBLISH_RESTORE_PLAN", None)
            self.assertIsNone(bench._resolve_restore_publisher(stub_transport, {"id": "ws"}))
        with patch.dict(os.environ, {"COMFYMODAL_V2_PUBLISH_RESTORE_PLAN": "1"}, clear=False):
            publisher = bench._resolve_restore_publisher(stub_transport, {"id": "ws"})
            self.assertIsNotNone(publisher)


# ── build_modal_resources profile Volume tests ──────────────────────────────


class TestBuildModalResourcesProfileVolume(unittest.TestCase):
    """build_modal_resources creates profile Volume only when full-trace
    is enabled, and never when disabled.  Publisher & fallback paths
    always have profile_volume: None."""

    def setUp(self):
        from comfymodal_runtime.modal_app import _V2_FULL_TRACE_ENABLED
        self._orig_full_trace = _V2_FULL_TRACE_ENABLED

    def tearDown(self):
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


if __name__ == "__main__":
    unittest.main()
