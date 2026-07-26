"""Focused tests for publish_restore_plan_remote registration and diagnostics.

Verifies:
- Registration source (app.function(...)) contains startup_timeout=120.
- Function body contains entry/success/error diagnostics with flush.
- Exception handler re-raises.

Does NOT invoke Modal remotely — all assertions operate on source text
analysis (AST-based extraction from the file).
"""

from __future__ import annotations

import unittest
from pathlib import Path

# Path to the production source file.
_MODAL_APP_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "modal_app.py"


# ── Registration source tests ─────────────────────────────────────────────


class TestPublishRestorePlanRegistration(unittest.TestCase):
    """Registration call to app.function(...) includes startup_timeout=120."""

    def test_startup_timeout_in_registration(self):
        """The app.function(...) call for publish_restore_plan_remote
        includes startup_timeout=120 alongside existing timeout=300,
        min_containers=0, scaledown_window."""
        source = _MODAL_APP_PATH.read_text(encoding="utf-8")
        # Confirm the parameter is somewhere in the file.
        self.assertIn(
            "startup_timeout=120",
            source,
            "startup_timeout=120 must appear in modal_app.py",
        )
        # Confirm it appears in the publish_restore_plan_remote registration
        # block — specifically between "timeout=300" and the next
        # registration-stanza boundary keyword.
        idx = source.index("publish_restore_plan_remote")
        block = source[idx:]
        # The registration spans from the function(... call through its
        # closing ); locate the "timeout=300" within this block and verify
        # startup_timeout comes before the next scaledown_window.
        self.assertIn("timeout=300", block)
        self.assertIn("startup_timeout=120", block)
        block_after_timeout = block.split("timeout=300")[1]
        self.assertIn(
            "startup_timeout=120",
            block_after_timeout.split("scaledown_window")[0],
            "startup_timeout=120 should appear between timeout=300 and "
            "scaledown_window in the registration call",
        )


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
