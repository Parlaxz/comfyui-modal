import ast
import os
import tempfile
import types
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from comfymodal_runtime.custom_node_root import (
    CustomNodesRootResolution,
    resolve_custom_nodes_root_details,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


def _load_resolver_functions():
    """Compile only the resolver functions, not comfyapp's import-time code."""
    source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(COMFYAPP_PATH))
    wanted = {
        "_resolve_local_custom_nodes_root_details",
        "_local_custom_nodes_root_diagnostics",
    }
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in wanted
    ]
    if {node.name for node in functions} != wanted:
        raise AssertionError(f"Could not extract resolver functions: {wanted}")

    module = types.ModuleType("comfyapp_rx8a_resolver")
    module.__file__ = str(COMFYAPP_PATH)
    module.__dict__.update(
        os=os,
        _CustomNodesRootResolution=CustomNodesRootResolution,
        _resolve_custom_nodes_root_details=resolve_custom_nodes_root_details,
    )
    code = compile(
        ast.Module(body=cast(list[ast.stmt], functions), type_ignores=[]),
        str(COMFYAPP_PATH),
        "exec",
    )
    exec(code, module.__dict__)
    if module._resolve_local_custom_nodes_root_details.__code__.co_filename != str(COMFYAPP_PATH):
        raise AssertionError("resolver was not compiled with comfyapp.py source fidelity")
    return module


def _node_root(path: Path) -> Path:
    for name in ("node-a", "node-b", "node-c"):
        node = path / name
        node.mkdir(parents=True, exist_ok=True)
        (node / "__init__.py").write_text("", encoding="utf-8")
    return path


def _fixture(base: Path, *, staged: bool) -> tuple[Path, Path, Path]:
    canonical = base / "ComfyUI" / "custom_nodes"
    plugin = canonical / "comfyui-modal"
    worktrees = plugin / ".slim" / "worktrees"
    worktree = worktrees / "rx7"
    worktree.mkdir(parents=True)
    # These sibling lane directories reproduce the metadata topology which
    # must never be selected as a custom-node source root.
    for lane in ("rx7", "rx7a", "rx8"):
        (worktrees / lane).mkdir(parents=True, exist_ok=True)
        (worktrees / lane / "__init__.py").write_text("", encoding="utf-8")
    _node_root(canonical)
    if staged:
        _node_root(worktree / ".slim" / "rx7-custom-nodes")
    return plugin, worktree, canonical


class RX8ACustomNodeRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comfyapp = _load_resolver_functions()

    def _resolve(self, module, anchor: Path, *, configured_env: str | None = None):
        environment = os.environ.copy()
        if configured_env is None:
            environment.pop("COMFYMODAL_LOCAL_CUSTOM_NODES", None)
        else:
            environment["COMFYMODAL_LOCAL_CUSTOM_NODES"] = configured_env
        with patch.dict(os.environ, environment, clear=True), patch.object(
            module, "__file__", str(anchor / "comfyapp.py")
        ):
            return module._resolve_local_custom_nodes_root_details()

    def test_canonical_checkout_uses_canonical_custom_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin, _worktree, canonical = _fixture(Path(tmp), staged=False)
            resolution = self._resolve(self.comfyapp, plugin)
        self.assertEqual(Path(resolution.root), canonical.resolve())
        self.assertEqual(resolution.method, "canonical_checkout_parent")

    def test_staged_worktree_wins_over_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            _plugin, worktree, _canonical = _fixture(Path(tmp), staged=True)
            resolution = self._resolve(self.comfyapp, worktree)
        self.assertEqual(resolution.method, "worktree_staged_root")
        self.assertTrue(resolution.root.endswith(os.path.join(".slim", "rx7-custom-nodes")))

    def test_unstaged_worktree_falls_back_to_canonical_not_worktrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            _plugin, worktree, canonical = _fixture(Path(tmp), staged=False)
            resolution = self._resolve(self.comfyapp, worktree)
        self.assertEqual(Path(resolution.root), canonical.resolve())
        self.assertEqual(resolution.method, "canonical_root_from_worktree")
        self.assertNotIn(os.path.join(".slim", "worktrees"), resolution.root)

    def test_explicit_root_precedes_staged_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            _plugin, worktree, _canonical = _fixture(Path(tmp), staged=True)
            explicit = _node_root(Path(tmp) / "explicit-custom-nodes")
            resolution = self._resolve(
                self.comfyapp, worktree, configured_env=str(explicit)
            )
        self.assertEqual(Path(resolution.root), explicit.resolve())
        self.assertEqual(resolution.method, "explicit_configured_root")

    def test_empty_explicit_root_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            _plugin, worktree, _canonical = _fixture(Path(tmp), staged=False)
            with self.assertRaisesRegex(RuntimeError, "custom-nodes root is empty"):
                self._resolve(self.comfyapp, worktree, configured_env="")

    def test_ambiguous_fallback_candidates_fail_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            _plugin, worktree, _canonical = _fixture(Path(tmp), staged=False)
            fallback = _node_root(worktree / "comfy" / "ComfyUI" / "custom_nodes")
            with self.assertRaisesRegex(RuntimeError, "ambiguous custom-nodes source root"):
                self._resolve(self.comfyapp, worktree)
            self.assertTrue(fallback.is_dir())

    def test_comfyapp_diagnostics_include_resolution_method_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            _plugin, worktree, _canonical = _fixture(Path(tmp), staged=True)
            module = self.comfyapp
            resolution = self._resolve(module, worktree)
            setattr(module, "_LOCAL_CUSTOM_NODES_RESOLUTION", resolution)
            diagnostics_payload = module._local_custom_nodes_root_diagnostics()
        self.assertEqual(diagnostics_payload["custom_nodes_root_resolution_method"], "worktree_staged_root")
        self.assertEqual(
            diagnostics_payload["custom_nodes_root_candidates"],
            [resolution.root, str((_canonical).resolve())],
        )


if __name__ == "__main__":
    unittest.main()
