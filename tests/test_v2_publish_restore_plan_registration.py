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
