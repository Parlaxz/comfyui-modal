import hashlib
import io
import os
import stat
import tarfile
from pathlib import Path

import pytest

from comfymodal_runtime import publication_policy
from tools.v2_control.custom_nodes import (
    SemanticFile,
    archive_content_digest,
    build_source_identity,
    build_archive,
    collect_semantic_files,
)


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = (
                path.read_bytes(),
                stat.S_IMODE(path.stat(follow_symlinks=False).st_mode),
            )
    return result


def _fixture(root: Path) -> None:
    node = root / "node-a"
    node.mkdir(parents=True)
    (node / "script.py").write_bytes(b"#!/usr/bin/env python\r\nprint('ok')\r\n")
    (node / "run.sh").write_bytes(b"#!/bin/sh\necho ok\n")
    (node / "run.sh").chmod(0o751)
    (node / "config.json").write_bytes(b'{"enabled": true}\n')


@pytest.mark.fast_unit
def test_archive_matches_canonical_candidate_tree_and_modes(tmp_path):
    source = tmp_path / "source"
    extracted = tmp_path / "extracted"
    source.mkdir()
    extracted.mkdir()
    _fixture(source)

    files = collect_semantic_files(source)
    identity = build_source_identity(source, semantic_files=files)
    archive = build_archive(files)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        tar.extractall(extracted, filter="data")

    expected = {
        item.path: (
            item.source_data if item.source_data is not None else item.data,
            stat.S_IMODE(item.mode),
        )
        for item in files
    }
    assert _snapshot(extracted) == expected
    generation_before = publication_policy.compute_publication_generation(source)
    generation_after = publication_policy.compute_publication_generation(extracted)
    assert identity.content_generation == generation_before == generation_after


@pytest.mark.fast_unit
def test_archive_is_deterministic_and_cache_key_is_content_addressed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture(source)
    files = collect_semantic_files(source)
    first = build_archive(files)
    second = build_archive(files)
    assert first == second
    key = archive_content_digest(files)
    assert key == archive_content_digest(tuple(reversed(files)))
    assert len(key) == hashlib.sha256(first).digest_size * 2
    assert f"custom_nodes-{key}.tar.gz".endswith(".tar.gz")

    (source / "node-a" / "run.sh").write_bytes(b"#!/bin/sh\necho changed\n")
    changed = collect_semantic_files(source)
    assert archive_content_digest(changed) != key


@pytest.mark.fast_unit
def test_archive_preserves_executable_mode_in_member_and_extraction(tmp_path):
    item = SemanticFile(
        path="node-a/run.sh",
        size=10,
        sha256="0" * 64,
        data=b"#!/bin/sh\n",
        mode=0o751,
    )
    archive = build_archive((item,))
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        assert tar.getmember("node-a/run.sh").mode & 0o111
        tar.extractall(extracted, filter="data")
    if os.name == "nt":
        pytest.skip("Windows chmod cannot materialize POSIX executable bits")
    assert stat.S_IMODE((extracted / "node-a" / "run.sh").stat().st_mode) & 0o111


@pytest.mark.fast_unit
def test_publication_walker_rejects_symlink_entries(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture(source)
    try:
        (source / "node-a" / "link.py").symlink_to(source / "node-a" / "script.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this Windows test host")
    with pytest.raises(ValueError, match="symlink"):
        collect_semantic_files(source)


@pytest.mark.fast_unit
def test_archive_builder_rejects_path_traversal_entries():
    item = SemanticFile(
        path="../escape.txt",
        size=4,
        sha256="0" * 64,
        data=b"safe",
    )
    with pytest.raises(ValueError, match="unsafe archive member path"):
        build_archive((item,))


@pytest.mark.fast_unit
def test_comfyapp_uses_content_addressed_archive_layer(tmp_path):
    source = Path(__file__).resolve().parents[1] / "comfyapp.py"
    text = source.read_text(encoding="utf-8")
    assert "_prepare_custom_node_archive(_LOCAL_CUSTOM_NODES)" in text
    assert "add_local_file(" in text
    assert "custom_nodes-{archive_key}.tar.gz" in text
    assert "--preserve-permissions" in text
    assert "_custom_node_archive_generation" in text
    assert "_image_base = _image_base.run_commands(" in text
