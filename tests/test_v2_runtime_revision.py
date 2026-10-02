"""Focused tests for the V2 packaged-runtime source revision."""

from __future__ import annotations

import ast
import hashlib
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_revision_function():
    """Load only the revision helper so this test does not import Modal."""
    tree = ast.parse((ROOT / "comfyapp.py").read_text(encoding="utf-8-sig"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_compute_v2_runtime_revision"
    )
    namespace = {"Path": Path, "hashlib": hashlib}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "comfyapp.py"), "exec"), namespace)
    return namespace["_compute_v2_runtime_revision"]


def _write_sources(root: Path, files: list[tuple[str, bytes]]) -> None:
    for relative_path, content in files:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_runtime_revision_changes_for_non_modal_app_source():
    revision = _load_revision_function()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "comfymodal_runtime"
        _write_sources(root, [
            ("modal_app.py", b"APP = 1\n"),
            ("runtime_bootstrap.py", b"BOOTSTRAP = 1\n"),
        ])
        before = revision(root)
        (root / "runtime_bootstrap.py").write_bytes(b"BOOTSTRAP = 2\n")
        after = revision(root)

    assert before != after
    assert len(before) == len(after) == 16


def test_runtime_revision_is_deterministic_over_sorted_relative_paths():
    revision = _load_revision_function()
    files = [
        ("z_nested.py", b"Z = 1\n"),
        ("a_nested.py", b"A = 1\n"),
        ("runtime_bootstrap.py", b"BOOTSTRAP = 1\n"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        first_root = Path(tmp) / "first" / "comfymodal_runtime"
        second_root = Path(tmp) / "second" / "comfymodal_runtime"
        _write_sources(first_root, files)
        _write_sources(second_root, list(reversed(files)))

        first = revision(first_root)
        second = revision(second_root)

    assert first == second
