"""PART A destructive custom-node publication guard (fast unit).

Covers the nine local cases: new-empty SKIP/WARN, absent/empty/partial-loss
BLOCK, unchanged PASS, new-populated PASS, special-file fatal, override
allowed+receipt-recorded, and blocked zero-remote-mutation.  All authority
comes from the last verified remote receipt plus the generation readback;
the stale shared ``.deployed_state.json`` is never consulted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast_unit

from tools.v2_control.custom_nodes import (
    GENERATION_RECORD_PATH,
    PublicationReceipt,
    RECEIPT_PATH,
    build_source_identity,
    check_publication_safety,
    prepare_publication,
    publish_or_skip,
)


class FakeVolume:
    def __init__(self, name="test-volume"):
        self.name = name
        self.files: dict[str, bytes] = {}

    def read_file(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return iter((self.files[path],))

    class _Batch:
        def __init__(self, volume):
            self.volume = volume

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def put_file(self, handle, path):
            self.volume.files[path] = handle.read()

    def batch_upload(self, *, force):
        assert force is True
        return self._Batch(self)


def _write(root: Path, package: str, files: dict[str, bytes]) -> Path:
    node = root / package
    node.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = node / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def _seed(volume: FakeVolume, identity) -> None:
    volume.files[RECEIPT_PATH] = PublicationReceipt.create(
        identity, volume.name
    ).to_bytes()
    volume.files[GENERATION_RECORD_PATH] = json.dumps({
        "schema_version": 2,
        "content_generation": identity.content_generation,
    }).encode()


def _publishing_fake(volume: FakeVolume, root: Path, calls: list):
    async def publisher(_archive: bytes):
        calls.append(True)
        candidate = build_source_identity(root)
        volume.files[GENERATION_RECORD_PATH] = json.dumps({
            "schema_version": 2,
            "content_generation": candidate.content_generation,
        }).encode()
        return {"status": "ok", "content_generation": candidate.content_generation}

    return publisher


def _run(root, volume, publisher, **kwargs):
    return asyncio.run(publish_or_skip(
        root, volume_name=volume.name, volume=volume,
        publisher=publisher, **kwargs,
    ))


# (1) new empty never-published package: SKIP/WARN, no crash, publish proceeds.
def test_new_empty_package_skips_with_warning(tmp_path, caplog):
    _write(tmp_path, "ext-empty", {"notes.md": b"excluded by policy"})
    calls: list = []
    volume = FakeVolume()
    with caplog.at_level(logging.WARNING, logger="comfymodal_runtime.publication_policy"):
        decision = _run(tmp_path, volume, _publishing_fake(volume, tmp_path, calls))
    assert decision.reason == "published_verified"
    assert decision.identity.file_count == 0
    assert decision.identity.package_manifests == ()
    assert calls == [True]
    assert any("no_publishable_files" in record.message for record in caplog.records)


# (2) previously-populated package now absent: HARD BLOCK.
def test_prev_populated_now_absent_blocks(tmp_path):
    _write(tmp_path, "ext-a", {"a.py": b"a", "b.py": b"b"})
    previous, _archive, _files = prepare_publication(tmp_path)
    volume = FakeVolume()
    _seed(volume, previous)
    shutil.rmtree(tmp_path / "ext-a")

    calls: list = []
    decision = _run(tmp_path, volume, _publishing_fake(volume, tmp_path, calls))
    assert decision.action == "blocked"
    assert decision.reason == "destructive_custom_node_publication_blocked"
    assert calls == []
    (entry,) = decision.destructive_delta["packages"]
    assert entry["package"] == "ext-a"
    assert (entry["prev_files"], entry["cand_files"]) == (2, 0)
    assert entry["missing_count"] == 2
    assert sorted(entry["missing_paths"]) == ["ext-a/a.py", "ext-a/b.py"]
    assert entry["prev_digest"] and not entry["cand_digest"]


# (3) previously-populated package now empty: HARD BLOCK.
def test_prev_populated_now_empty_blocks(tmp_path):
    _write(tmp_path, "ext-a", {"a.py": b"a"})
    previous, _archive, _files = prepare_publication(tmp_path)
    volume = FakeVolume()
    _seed(volume, previous)
    (tmp_path / "ext-a" / "a.py").unlink()
    (tmp_path / "ext-a" / "notes.md").write_bytes(b"excluded by policy")

    calls: list = []
    decision = _run(tmp_path, volume, _publishing_fake(volume, tmp_path, calls))
    assert decision.action == "blocked"
    (entry,) = decision.destructive_delta["packages"]
    assert entry["package"] == "ext-a"
    assert (entry["prev_files"], entry["cand_files"]) == (1, 0)


# (4) partial file loss: HARD BLOCK with missing-path evidence.
def test_partial_loss_blocks_with_missing_paths(tmp_path):
    _write(tmp_path, "ext-a", {"a.py": b"a", "b.py": b"b"})
    previous, _archive, _files = prepare_publication(tmp_path)
    volume = FakeVolume()
    _seed(volume, previous)
    (tmp_path / "ext-a" / "b.py").unlink()

    calls: list = []
    decision = _run(tmp_path, volume, _publishing_fake(volume, tmp_path, calls))
    assert decision.action == "blocked"
    (entry,) = decision.destructive_delta["packages"]
    assert entry["missing_paths"] == ["ext-a/b.py"]
    assert (entry["prev_files"], entry["cand_files"]) == (2, 1)
    assert entry["prev_bytes"] != entry["cand_bytes"]
    assert entry["prev_digest"] != entry["cand_digest"]


# (5) unchanged tree vs verified receipt: exact PASS (skip, no publish).
def test_unchanged_passes_exact_skip(tmp_path):
    _write(tmp_path, "ext-a", {"a.py": b"a"})
    identity, _archive, _files = prepare_publication(tmp_path)
    volume = FakeVolume()
    _seed(volume, identity)

    calls: list = []

    async def publisher(_archive: bytes):
        calls.append(True)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = _run(tmp_path, volume, publisher)
    assert decision.skip and decision.reason == "exact_match"
    assert calls == []


# (6) new populated package alongside unchanged history: PASS.
def test_new_populated_package_passes(tmp_path):
    _write(tmp_path, "ext-a", {"a.py": b"a"})
    previous, _archive, _files = prepare_publication(tmp_path)
    volume = FakeVolume()
    _seed(volume, previous)
    _write(tmp_path, "ext-b", {"b.py": b"b"})

    calls: list = []
    decision = _run(tmp_path, volume, _publishing_fake(volume, tmp_path, calls))
    assert decision.reason == "published_verified"
    assert calls == [True]
    names = [item.name for item in decision.identity.package_manifests]
    assert names == ["ext-a", "ext-b"]
    # Deterministic per-package manifest evidence.
    manifest = decision.identity.package_manifests[0].to_dict()
    assert manifest["name"] == "ext-a"
    assert manifest["file_count"] == 1
    assert manifest["bytes"] == manifest["total_bytes"] == 1
    assert manifest["content_digest"]
    assert manifest["path_list"] == ["ext-a/a.py"]
    assert manifest["path_digest"]
    assert manifest["source_root"]
    assert manifest["generation"] == manifest["content_digest"]


# (7) malformed special-file tree stays fatal (existing contract retained).
def test_special_file_still_fatal(tmp_path, monkeypatch):
    _write(tmp_path, "ext-a", {"a.py": b"a"})
    link = tmp_path / "ext-a" / "link.py"
    try:
        os.symlink(tmp_path / "ext-a" / "a.py", link)
    except OSError:
        # No host symlink privilege: stub scandir so the retained root-level
        # symlink probe still executes against the real validation code.
        import stat as stat_mod

        real_scandir = os.scandir

        class _FakeEntry:
            path = str(tmp_path / "rogue-link")

            def stat(self, *, follow_symlinks=False):
                return os.stat_result((stat_mod.S_IFLNK | 0o777,) + (0,) * 9)

        monkeypatch.setattr(os, "scandir", lambda *_args, **_kwargs: iter((_FakeEntry(),)))
        try:
            with pytest.raises(ValueError, match="not publishable"):
                prepare_publication(tmp_path)
        finally:
            monkeypatch.setattr(os, "scandir", real_scandir)
        return
    with pytest.raises(ValueError, match="not publishable"):
        prepare_publication(tmp_path)


# (8) explicit override: allowed, publisher runs, receipt records override.
def test_override_allowed_and_recorded_in_receipt(tmp_path):
    _write(tmp_path, "ext-a", {"a.py": b"a", "b.py": b"b"})
    previous, _archive, _files = prepare_publication(tmp_path)
    volume = FakeVolume()
    _seed(volume, previous)
    (tmp_path / "ext-a" / "b.py").unlink()

    calls: list = []
    decision = _run(
        tmp_path, volume, _publishing_fake(volume, tmp_path, calls),
        allow_destructive=True,
    )
    assert decision.reason == "published_verified"
    assert calls == [True]
    assert decision.destructive_override is False  # decision itself is not the receipt
    receipt = PublicationReceipt.from_bytes(volume.files[RECEIPT_PATH])
    assert receipt.destructive_override is True
    assert receipt.destructive_delta["blocked"] is True
    assert receipt.destructive_delta["packages"][0]["package"] == "ext-a"
    # check_publication_safety reflects the explicit override, never inference.
    prev_receipt = PublicationReceipt.create(previous, volume.name)
    assert check_publication_safety(prev_receipt, decision.identity)["allowed"] is False
    assert check_publication_safety(
        prev_receipt, decision.identity, allow_destructive=True
    )["allowed"] is True


# (9) blocked publication performs zero remote mutation.
def test_blocked_performs_zero_remote_mutation(tmp_path):
    _write(tmp_path, "ext-a", {"a.py": b"a"})
    previous, _archive, _files = prepare_publication(tmp_path)
    volume = FakeVolume()
    _seed(volume, previous)
    before = dict(volume.files)
    before_generation = volume.files[GENERATION_RECORD_PATH]
    (tmp_path / "ext-a" / "a.py").unlink()

    async def publisher(_archive: bytes):
        raise AssertionError("publisher must not run while blocked")

    decision = _run(tmp_path, volume, publisher)
    assert decision.action == "blocked"
    assert volume.files == before
    assert volume.files[GENERATION_RECORD_PATH] == before_generation


def test_first_party_comfyui_modal_evolution_not_blocked(tmp_path):
    _write(tmp_path, "comfyui-modal", {
        "comfyapp.py": b"app",
        "comfymodal_runtime/modal_app.py": b"modal",
        "extra.py": b"old tracked file",
    })
    previous, _archive, _files = prepare_publication(tmp_path)
    assert previous.package_manifests[0].first_party is True
    volume = FakeVolume()
    _seed(volume, previous)
    (tmp_path / "comfyui-modal" / "extra.py").unlink()

    calls: list = []
    decision = _run(tmp_path, volume, _publishing_fake(volume, tmp_path, calls))
    assert decision.reason == "published_verified"
    assert calls == [True]


def test_override_flag_is_explicit_only():
    from tools.v2_control.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["version"]).allow_destructive_custom_node_publication is False
    parsed = parser.parse_args(
        ["--allow-destructive-custom-node-publication", "version"]
    )
    assert parsed.allow_destructive_custom_node_publication is True
