"""Fast tests for first-party benchmark-node publication boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from comfymodal_runtime import publication_policy


pytestmark = pytest.mark.fast_unit


HARNESS_NAMES = {
    "modal-single-volume-parallelism",
    "modal-volume-read-ceiling",
}
REGISTERED_NODE_NAMES = {"ComfyUI-KJNodes", "comfyui-easy-use"}


def _build_fixture(root: Path) -> None:
    for name in HARNESS_NAMES:
        node = root / name
        node.mkdir()
        (node / "__init__.py").write_text("# benchmark harness\n", encoding="utf-8")
        (node / "harness.py").write_text("benchmark = True\n", encoding="utf-8")

    for name in REGISTERED_NODE_NAMES:
        node = root / name
        nested = node / "modal-single-volume-parallelism"
        nested.mkdir(parents=True)
        (node / "__init__.py").write_text(
            "NODE_CLASS_MAPPINGS = {}\n", encoding="utf-8"
        )
        (nested / "runtime_asset.py").write_text(
            "asset = True\n", encoding="utf-8"
        )


def test_harness_nodes_are_absent_from_syncable_dirs(tmp_path):
    _build_fixture(tmp_path)

    syncable = set(publication_policy.iter_syncable_custom_node_dirs(tmp_path))

    assert HARNESS_NAMES.isdisjoint(syncable)
    assert REGISTERED_NODE_NAMES.issubset(syncable)


def test_harness_nodes_are_absent_from_publication_files(tmp_path):
    _build_fixture(tmp_path)

    published = {
        path.relative_to(tmp_path).as_posix()
        for path in publication_policy.iter_publication_files(tmp_path)
    }

    assert not any(path.split("/", 1)[0] in HARNESS_NAMES for path in published)
    for name in REGISTERED_NODE_NAMES:
        assert f"{name}/__init__.py" in published


def test_same_named_nested_harness_directory_remains_published(tmp_path):
    _build_fixture(tmp_path)

    published = {
        path.relative_to(tmp_path).as_posix()
        for path in publication_policy.iter_publication_files(tmp_path)
    }

    for name in REGISTERED_NODE_NAMES:
        assert (
            f"{name}/modal-single-volume-parallelism/runtime_asset.py"
            in published
        )
