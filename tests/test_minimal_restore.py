"""Focused source-contract tests for the E37 minimal restore path."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


COMFYAPP_PATH = Path(__file__).resolve().parents[1] / "comfyapp.py"


class MinimalRestoreSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        cls.tree = ast.parse(cls.source)
        cls.restore = next(
            node
            for node in ast.walk(cls.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "restore"
        )
        cls.restore_source = ast.get_source_segment(cls.source, cls.restore) or ""

    def _minimal_branch(self) -> ast.If:
        for node in ast.walk(self.restore):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Name):
                if node.test.id == "_minimal_restore_effective":
                    return node
        self.fail("minimal restore branch not found")

    def test_gate_defaults_on_and_is_explicitly_diagnostic(self):
        self.assertIn(
            'MINIMAL_RESTORE_DEFAULT = True',
            self.source,
        )
        self.assertIn('"COMFYMODAL_MINIMAL_RESTORE"', self.restore_source)
        self.assertIn('"minimal_restore_effective"', self.restore_source)
        self.assertIn('"minimal_restore_path"', self.restore_source)

    def test_minimal_branch_has_no_model_or_optional_warmup_calls(self):
        branch = self._minimal_branch()
        called = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(branch)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }
        forbidden = {
            "_sync_custom_nodes_from_volume",
            "_install_custom_node_requirements",
            "_start_restore_preload",
            "_join_restore_preload",
            "_maybe_submit_restore_background_unet",
            "_start_production_restore_unet",
            "_warmup_direct",
            "_warmup_vae_decode",
            "_run_optional_cuda_warmup",
            "_preload_models_to_cpu",
            "_patch_clip_text_encode_cache",
        }
        self.assertFalse(forbidden & called)

    def test_minimal_branch_keeps_only_backend_cuda_reattachment_and_identity(self):
        branch = self._minimal_branch()
        called = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(branch)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }
        self.assertIn("_start_backend", called)
        self.assertIn("_initialize_cuda_context", called)
        self.assertIn("_record_critical_path_restore", called)
        self.assertIn("_log_remote_identity", called)
        self.assertIn("_last_restore_timing", self.restore_source)

    def test_minimal_return_precedes_all_heavy_restore_owners(self):
        branch = self._minimal_branch()
        minimal_return = max(
            node.end_lineno or node.lineno
            for node in ast.walk(branch)
            if isinstance(node, ast.Return)
        )
        for owner in (
            "_sync_custom_nodes_from_volume",
            "_start_restore_preload",
            "_join_restore_preload",
            "_maybe_submit_restore_background_unet",
            "_start_production_restore_unet",
            "_warmup_direct",
            "_warmup_vae_decode",
        ):
            owner_lines = [
                node.lineno
                for node in ast.walk(self.restore)
                if isinstance(node, ast.Attribute) and node.attr == owner
            ]
            self.assertTrue(owner_lines, f"restore owner {owner} disappeared")
            self.assertLess(
                minimal_return,
                min(owner_lines),
                f"minimal restore must return before {owner}",
            )

    def test_timing_is_populated_before_minimal_return(self):
        branch = self._minimal_branch()
        timing_assignment = next(
            node
            for node in ast.walk(branch)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Attribute)
                and target.attr == "_last_restore_timing"
                for target in node.targets
            )
        )
        return_node = next(node for node in ast.walk(branch) if isinstance(node, ast.Return))
        self.assertLess(timing_assignment.lineno, return_node.lineno)

    def test_identity_and_stale_state_reset_precede_minimal_branch(self):
        self._minimal_branch()
        for marker in (
            "self._current_restore_session_id =",
            "self._active_next_read_dedup = set()",
            "self._last_restore_timing = None",
            "self._init_critical_path_recorder(",
        ):
            self.assertLess(self.restore_source.index(marker), self.restore_source.index("if _minimal_restore_effective:"))


if __name__ == "__main__":
    unittest.main()
