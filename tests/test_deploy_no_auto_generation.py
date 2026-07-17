"""Source-level assertion: _run_deploy_background success path
contains no automatic GPU generation call/thread.

After deployment completes, the deploy state must be
"deployed_unwarmed" with no background thread that invokes
run_prompt / run_prompt_stream / execute_modal_prompt /
canonical execution / benchmark generation.

The user must explicitly call POST /comfymodal/deploy-warmup/run
to warm the deployment.
"""

import ast
import inspect
import sys
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_MODULE = REPO_ROOT / "__init__.py"

# ── Generation-call identifiers that MUST NOT appear in the
#    deploy-success path of _run_deploy_background ──
_FORBIDDEN_IN_SUCCESS_PATH: frozenset[str] = frozenset({
    "run_prompt",
    "run_prompt_stream",
    "execute_modal_prompt",
    "canonical_execution",
    "_run_auto_warmup",
    "benchmark",
})


class DeployNoAutoGenerationTest(unittest.TestCase):
    """Prove deployment success path contains zero automatic GPU generation."""

    @classmethod
    def setUpClass(cls):
        if not INIT_MODULE.exists():
            raise AssertionError(f"Expected __init__.py at {INIT_MODULE}")
        source = INIT_MODULE.read_text(encoding="utf-8")
        cls.tree = ast.parse(source, filename=str(INIT_MODULE))

    # ── AST helpers ────────────────────────────────────────────────

    @staticmethod
    def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    @staticmethod
    def _find_call_names_in_subtree(node: ast.AST) -> set[str]:
        """Return all attribute-chain call names found under *node*.

        Covers both simple (``foo()``) and chained (``mod.run_prompt()``)
        calls, as well as ``asyncio.run(_do_warmup())`` patterns.
        """
        names: set[str] = set()
        for child in ast.walk(node):
            # Direct function call like ``run_prompt_stream(...)``
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                names.add(child.func.id)
            # Chained call like ``modal_client.run_prompt_stream(...)``
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                names.add(child.func.attr)
                # Also capture the full chain for deeper checks
                # e.g. ``state.mark_warmup_failed(...)``
        return names

    @staticmethod
    def _find_thread_targets(node: ast.AST) -> list[str]:
        """Return all function/variable names used as ``target=``
        in ``threading.Thread(...)`` calls."""
        targets: list[str] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            # Match ``threading.Thread(target=...)`` or ``Thread(target=...)``
            is_thread_call = (
                (isinstance(func, ast.Attribute) and func.attr == "Thread")
                or (isinstance(func, ast.Name) and func.id == "Thread")
            )
            if not is_thread_call:
                continue
            for kw in child.keywords:
                if kw.arg == "target" and isinstance(kw.value, ast.Name):
                    targets.append(kw.value.id)
                elif kw.arg == "target" and isinstance(kw.value, ast.Lambda):
                    # Lambda targets — extract body inference
                    targets.append("<lambda>")
        return targets

    # ── Tests ──────────────────────────────────────────────────────

    def test_run_auto_warmup_function_removed(self):
        """The private helper ``_run_auto_warmup`` must not exist."""
        fn = self._find_function(self.tree, "_run_auto_warmup")
        self.assertIsNone(
            fn,
            "_run_auto_warmup was found but should have been removed. "
            "Remove the function definition from __init__.py.",
        )

    def test_no_auto_warmup_thread_in_deploy_success(self):
        """The ``_run_deploy_background`` function must not start a
        thread targeting any GPU-generation function."""
        fn = self._find_function(self.tree, "_run_deploy_background")
        self.assertIsNotNone(
            fn,
            "_run_deploy_background function not found in __init__.py",
        )
        targets = self._find_thread_targets(fn)
        forbidden = {t for t in targets if not t.startswith("_") or t == "<lambda>"}
        # Explicitly check no thread target is a generation-like name
        for t in targets:
            if t == "_auto_warmup":
                self.fail(
                    f"Found threading.Thread(target={t}) in "
                    f"_run_deploy_background — auto-warmup thread must be removed."
                )
            if t == "<lambda>":
                self.fail(
                    "Found threading.Thread with lambda target in "
                    "_run_deploy_background — must not auto-launch GPU work."
                )
        # Verify the only threads started (if any) are for non-generation purposes
        # (e.g. the deploy subprocess kill timer)
        allowed_thread_targets = {"_kill_timer"}
        for t in targets:
            self.assertIn(
                t, allowed_thread_targets,
                f"Unexpected thread target '{t}' in _run_deploy_background — "
                f"must not auto-launch GPU generation.",
            )

    def test_no_forbidden_calls_in_deploy_success_block(self):
        """The ``if returncode == 0:`` block inside ``_run_deploy_background``
        must not contain calls to ``run_prompt``, ``run_prompt_stream``,
        ``execute_modal_prompt``, or ``_run_auto_warmup``."""
        fn = self._find_function(self.tree, "_run_deploy_background")
        self.assertIsNotNone(fn)

        # Find the ``if returncode == 0:`` branch
        returncode_zero_body: ast.AST | None = None
        for node in ast.walk(fn):
            if isinstance(node, ast.If):
                # Match ``if returncode == 0:``
                test = node.test
                if (isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Name)
                        and test.left.id == "returncode"
                        and len(test.ops) == 1
                        and isinstance(test.ops[0], ast.Eq)
                        and isinstance(test.comparators[0], ast.Constant)
                        and test.comparators[0].value == 0):
                    returncode_zero_body = node
                    break

        self.assertIsNotNone(
            returncode_zero_body,
            "Could not locate ``if returncode == 0:`` block "
            "in _run_deploy_background",
        )

        calls = self._find_call_names_in_subtree(returncode_zero_body)
        found_forbidden = calls & _FORBIDDEN_IN_SUCCESS_PATH
        self.assertSetEqual(
            found_forbidden, set(),
            f"The deploy-success block contains forbidden GPU-generation "
            f"calls: {found_forbidden}.  Remove them so deploy ends at "
            f"deployed_unwarmed / manual-warmup-required.",
        )

    def test_deploy_status_is_deployed_unwarmed(self):
        """The success path sets _deploy_status to deployed_unwarmed,
        not ready/warming."""
        source = INIT_MODULE.read_text(encoding="utf-8")
        # Verify the message indicates manual warmup
        self.assertIn(
            "manual warmup required",
            source,
            "Deploy success status message must indicate manual warmup required",
        )
        self.assertIn(
            '"state": "deployed_unwarmed"',
            source,
            "Deploy success must set state to deployed_unwarmed",
        )


if __name__ == "__main__":
    unittest.main()
