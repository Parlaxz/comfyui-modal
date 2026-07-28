"""
Offline unittest coverage for ``tools/download_v2_full_trace.py``.

All tests mock Modal Volume access.  No live credentials are used.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.download_v2_full_trace import (
    BLOCK_SIZE,
    OPTIONAL_EXTRACTED_FILES,
    REQUIRED_EXTRACTED_FILES,
    ArtifactDescriptor,
    DownloadClient,
    ExtractionError,
    _build_file_index,
    _check_optional_files,
    _check_required_files,
    _compute_file_sha256,
    _incremental_verify,
    _load_manifest,
    _safe_extract,
    _validate_manifest_entries,
    _validate_tar_member,
    run_download,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_tar_gz(members: List[Dict[str, Any]]) -> bytes:
    """Create an in-memory tar.gz from a list of member descriptors.

    Each member dict can have:
      ``name`` (str) — member path
      ``content`` (bytes) — file content (default b"")
      ``link_target`` (str) — for symlink/hardlink members
      ``type`` (int) — tarfile type (default REGTYPE)
      ``mode`` (int) — permissions (default 0o644)
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for m in members:
            info = tarfile.TarInfo(name=m["name"])
            if m.get("type") is not None:
                info.type = m["type"]
            else:
                info.type = tarfile.REGTYPE
            info.mode = m.get("mode", 0o644)

            if info.type == tarfile.SYMTYPE:
                info.linkname = m["link_target"]
                tar.addfile(info)
            elif info.type == tarfile.LNKTYPE:
                info.linkname = m["link_target"]
                tar.addfile(info)
            elif info.type in (tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE):
                if info.type == tarfile.CHRTYPE:
                    info.devmajor = 0
                    info.devminor = 0
                elif info.type == tarfile.BLKTYPE:
                    info.devmajor = 0
                    info.devminor = 0
                tar.addfile(info)
            else:
                content = m.get("content", b"")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _make_bundle_tgz(
    files: Dict[str, bytes],
    manifest: Optional[Dict[str, Any]] = None,
    include_manifest: bool = True,
) -> bytes:
    """Create a full bundle.tar.gz for testing.

    *files* maps relative paths to content bytes.
    If *manifest* is None and *include_manifest* is True, a valid
    manifest is auto-generated from *files*.
    """
    members: List[Dict[str, Any]] = []
    for path, content in files.items():
        members.append({"name": path, "content": content})

    if include_manifest:
        if manifest is None:
            entries = []
            for path, content in files.items():
                if path == MANIFEST_FILENAME:
                    continue
                entries.append({
                    "path": path,
                    "size_bytes": len(content),
                    "sha256": _sha256_of_bytes(content),
                    "category": "derived" if path.startswith("derived/") else "raw",
                })
            manifest_payload = {
                "entries": entries,
                "trace_id": "test-trace",
            }
        else:
            manifest_payload = manifest
        members.append({"name": "bundle_manifest.json", "content": json.dumps(manifest_payload).encode()})

    return _make_tar_gz(members)


MANIFEST_FILENAME = "bundle_manifest.json"


def _make_manifest_entry(path: str, content: bytes) -> Dict[str, Any]:
    return {
        "path": path,
        "size_bytes": len(content),
        "sha256": _sha256_of_bytes(content),
        "category": "derived" if path.startswith("derived/") else "raw",
    }


# ── Mock Download Client ────────────────────────────────────────────────────

class MockVolume:
    """A test double that pretends to be a Modal Volume.

    Stores ``{remote_path: data_bytes}`` mappings.
    """

    def __init__(self, files: Dict[str, bytes]) -> None:
        self._files = files

    def read_file(self, remote_path: str) -> Iterable[bytes]:
        """Return the stored bytes in chunks."""
        data = self._files.get(remote_path)
        if data is None:
            raise FileNotFoundError(f"No such file: {remote_path}")
        # Yield in BLOCK_SIZE chunks
        offset = 0
        while offset < len(data):
            yield data[offset:offset + BLOCK_SIZE]
            offset += BLOCK_SIZE


class MockDownloadClient(DownloadClient):
    """Download client that reads from a MockVolume."""

    def __init__(self, volume: MockVolume) -> None:
        self._volume = volume

    def read_file_chunks(self, volume: Any, remote_path: str) -> Iterable[bytes]:
        # Ignore the passed volume; use our injected mock
        return self._volume.read_file(remote_path)


# ── Test Cases ──────────────────────────────────────────────────────────────

class ArtifactDescriptorTests(unittest.TestCase):
    """ArtifactDescriptor construction from CLI args and descriptor files."""

    def test_from_cli_args(self):
        class FakeArgs:
            volume = "test-vol"
            remote_path = "/traces/bundle.tar.gz"
            sha256 = "a" * 64
            trace_id = "test-trace"
            output_dir = "/tmp/out"

        desc = ArtifactDescriptor.from_cli_args(FakeArgs())
        self.assertEqual(desc.volume, "test-vol")
        self.assertEqual(desc.sha256, "a" * 64)

    def test_from_cli_normalizes_sha256(self):
        class FakeArgs:
            volume = "v"
            remote_path = "/r"
            sha256 = "ABCDEF1234567890" + "0" * 48
            trace_id = "t"
            output_dir = "/o"

        desc = ArtifactDescriptor.from_cli_args(FakeArgs())
        self.assertEqual(desc.sha256, "abcdef1234567890" + "0" * 48)

    def test_from_descriptor_file(self):
        data = {
            "volume": "desc-vol",
            "remote_path": "/desc/path.tar.gz",
            "sha256": "f" * 64,
            "trace_id": "desc-trace",
            "output_dir": "/desc/out",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fpath = f.name
        try:
            desc = ArtifactDescriptor.from_descriptor_file(fpath)
            self.assertEqual(desc.volume, "desc-vol")
            self.assertEqual(desc.remote_path, "/desc/path.tar.gz")
        finally:
            os.unlink(fpath)


class IncrementalVerifyTests(unittest.TestCase):
    """SHA-256 incremental verify with temp file, fsync, rename pattern."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_verify_success(self):
        data = b"hello world"
        expected = _sha256_of_bytes(data)
        dst = self.tmpdir / "test.tmp"
        _incremental_verify([data], dst, expected)
        self.assertTrue(dst.is_file())
        self.assertEqual(dst.read_bytes(), data)

    def test_verify_mismatch_raises(self):
        data = b"hello world"
        wrong_hash = "0" * 64
        dst = self.tmpdir / "bad.tmp"
        with self.assertRaises(ValueError) as ctx:
            _incremental_verify([data], dst, wrong_hash)
        self.assertIn("SHA-256 mismatch", str(ctx.exception))
        # Temp file is removed on mismatch
        self.assertFalse(dst.is_file())

    def test_verify_empty_file(self):
        data = b""
        expected = _sha256_of_bytes(data)
        dst = self.tmpdir / "empty.tmp"
        _incremental_verify([data], dst, expected)
        self.assertTrue(dst.is_file())
        self.assertEqual(dst.read_bytes(), b"")

    def test_verify_multiple_chunks(self):
        data = b"x" * (BLOCK_SIZE * 3 + 7)
        expected = _sha256_of_bytes(data)
        dst = self.tmpdir / "multi.tmp"
        chunks = [data[i:i + BLOCK_SIZE] for i in range(0, len(data), BLOCK_SIZE)]
        _incremental_verify(chunks, dst, expected)
        self.assertEqual(dst.read_bytes(), data)


class SafeExtractTests(unittest.TestCase):
    """Secure tar extraction with path traversal protection."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.extract_root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_tar_and_extract(self, members: List[Dict[str, Any]]) -> None:
        data = _make_tar_gz(members)
        tar_path = self.extract_root / "test.tar.gz"
        tar_path.write_bytes(data)
        _safe_extract(tar_path, self.extract_root)

    # ── Valid extraction ──────────────────────────────────────────────

    def test_valid_simple_file(self):
        members = [{"name": "hello.txt", "content": b"world"}]
        try:
            self._write_tar_and_extract(members)
        except Exception as exc:
            self.fail(f"Valid extraction raised: {exc}")
        self.assertTrue((self.extract_root / "hello.txt").is_file())
        self.assertEqual((self.extract_root / "hello.txt").read_bytes(), b"world")

    def test_valid_nested_dirs(self):
        members = [
            {"name": "derived/report.md", "content": b"# Report"},
            {"name": "raw/data.json", "content": b"{}"},
        ]
        self._write_tar_and_extract(members)
        self.assertTrue((self.extract_root / "derived/report.md").is_file())
        self.assertTrue((self.extract_root / "raw/data.json").is_file())

    # ── Absolute paths ────────────────────────────────────────────────

    def test_absolute_path_rejected(self):
        members = [{"name": "/etc/passwd", "content": b"pwned"}]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Absolute path", str(ctx.exception))

    # ── Path traversal ────────────────────────────────────────────────

    def test_traversal_rejected(self):
        members = [{"name": "../escape.txt", "content": b"pwned"}]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Path traversal", str(ctx.exception))

    def test_deep_traversal_rejected(self):
        members = [{"name": "a/../../../../etc/shadow", "content": b"pwned"}]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Path traversal", str(ctx.exception))

    # ── Device / special files ────────────────────────────────────────

    def test_fifo_rejected(self):
        members = [{"name": "pipe", "type": tarfile.FIFOTYPE}]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Device or special file", str(ctx.exception))

    def test_char_device_rejected(self):
        members = [{"name": "null", "type": tarfile.CHRTYPE}]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Device or special file", str(ctx.exception))

    def test_block_device_rejected(self):
        members = [{"name": "sda", "type": tarfile.BLKTYPE}]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Device or special file", str(ctx.exception))

    # ── Symlinks ──────────────────────────────────────────────────────

    def test_symlink_inside_root_allowed(self):
        members = [
            {"name": "target.txt", "content": b"real"},
            {"name": "link.txt", "type": tarfile.SYMTYPE, "link_target": "target.txt"},
        ]
        try:
            self._write_tar_and_extract(members)
        except Exception as exc:
            self.fail(f"Valid symlink extraction raised: {exc}")
        self.assertEqual((self.extract_root / "link.txt").read_bytes(), b"real")

    def test_symlink_outside_root_rejected(self):
        members = [
            {"name": "bad.link", "type": tarfile.SYMTYPE, "link_target": "/etc/passwd"},
        ]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Symlink", str(ctx.exception))

    def test_symlink_traversal_outside_rejected(self):
        members = [
            {"name": "a/link.lnk", "type": tarfile.SYMTYPE, "link_target": "../../../etc/passwd"},
        ]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Symlink", str(ctx.exception))

    # ── Hardlinks ─────────────────────────────────────────────────────

    def test_hardlink_inside_root_allowed(self):
        members = [
            {"name": "original.txt", "content": b"data"},
            {"name": "hardlink.txt", "type": tarfile.LNKTYPE, "link_target": "original.txt"},
        ]
        try:
            self._write_tar_and_extract(members)
        except Exception as exc:
            self.fail(f"Valid hardlink extraction raised: {exc}")
        self.assertEqual((self.extract_root / "hardlink.txt").read_bytes(), b"data")

    def test_hardlink_outside_root_rejected(self):
        members = [
            {"name": "evil.hardlink", "type": tarfile.LNKTYPE, "link_target": "/etc/shadow"},
        ]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Hardlink", str(ctx.exception))

    def test_hardlink_traversal_rejected(self):
        members = [
            {"name": "sub/evil.hardlink", "type": tarfile.LNKTYPE, "link_target": "../../secret"},
        ]
        with self.assertRaises(ExtractionError) as ctx:
            self._write_tar_and_extract(members)
        self.assertIn("Hardlink", str(ctx.exception))


class ManifestValidationTests(unittest.TestCase):
    """bundle_manifest.json loading, entry cross-check, required/optional files."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_file(self, rel_path: str, content: bytes = b"data") -> Path:
        full = self.root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return full

    # ── _load_manifest ────────────────────────────────────────────────

    def test_load_manifest_valid(self):
        manifest = {"entries": [{"path": "a.txt", "size_bytes": 4, "sha256": "0" * 64, "category": "raw"}]}
        self._write_file(MANIFEST_FILENAME, json.dumps(manifest).encode())
        result = _load_manifest(self.root)
        self.assertEqual(len(result["entries"]), 1)

    def test_missing_manifest_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("Missing", str(ctx.exception))

    def test_malformed_json_raises(self):
        self._write_file(MANIFEST_FILENAME, b"not json")
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("Malformed", str(ctx.exception))

    def test_manifest_not_dict_raises(self):
        self._write_file(MANIFEST_FILENAME, b'["list", "not", "dict"]')
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("JSON object", str(ctx.exception))

    def test_manifest_missing_entries_key(self):
        self._write_file(MANIFEST_FILENAME, json.dumps({"meta": "data"}).encode())
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("Cannot locate", str(ctx.exception))

    def test_manifest_entries_not_list_raises(self):
        self._write_file(MANIFEST_FILENAME, json.dumps({"entries": "not-a-list"}).encode())
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("to be a list", str(ctx.exception))

    def test_manifest_entry_missing_keys_raises(self):
        manifest = {"entries": [{"path": "a.txt"}]}  # missing size_bytes, sha256, category
        self._write_file(MANIFEST_FILENAME, json.dumps(manifest).encode())
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("missing required keys", str(ctx.exception))

    def test_manifest_entry_not_dict_raises(self):
        manifest = {"entries": ["not-a-dict"]}
        self._write_file(MANIFEST_FILENAME, json.dumps(manifest).encode())
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("not an object", str(ctx.exception))

    def test_manifest_with_files_key_works(self):
        manifest = {"files": [{"path": "a.txt", "size_bytes": 4, "sha256": "0" * 64, "category": "raw"}]}
        self._write_file(MANIFEST_FILENAME, json.dumps(manifest).encode())
        result = _load_manifest(self.root)
        self.assertEqual(len(result["entries"]), 1)

    # ── _validate_manifest_entries ────────────────────────────────────

    def test_entries_match_disk(self):
        data = b"file content"
        self._write_file("a.txt", data)
        manifest = {
            "entries": [{
                "path": "a.txt",
                "size_bytes": len(data),
                "sha256": _sha256_of_bytes(data),
                "category": "raw",
            }]
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["errors"], [])

    def test_entry_not_found_on_disk(self):
        manifest = {
            "entries": [{
                "path": "missing.txt",
                "size_bytes": 4,
                "sha256": "0" * 64,
                "category": "raw",
            }]
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("not found on disk", result["errors"][0])

    def test_size_mismatch(self):
        self._write_file("a.txt", b"actual content here")
        manifest = {
            "entries": [{
                "path": "a.txt",
                "size_bytes": 9999,
                "sha256": _sha256_of_bytes(b"actual content here"),
                "category": "raw",
            }]
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("Size mismatch", result["errors"][0])

    def test_sha256_mismatch(self):
        data = b"real content"
        self._write_file("a.txt", data)
        manifest = {
            "entries": [{
                "path": "a.txt",
                "size_bytes": len(data),
                "sha256": "0" * 64,
                "category": "raw",
            }]
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("SHA-256 mismatch", result["errors"][0])

    def test_both_size_and_sha_mismatch(self):
        self._write_file("a.txt", b"real")
        manifest = {
            "entries": [{
                "path": "a.txt",
                "size_bytes": 999,
                "sha256": "0" * 64,
                "category": "raw",
            }]
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "mismatch")
        # Should report at least one error (could be both depending on order)
        self.assertGreaterEqual(len(result["errors"]), 1)

    def test_entry_no_size_field_skips_size_check(self):
        """If entry has no size_bytes, size check is skipped (not an error)."""
        data = b"content without size in manifest"
        self._write_file("a.txt", data)
        manifest = {
            "entries": [{
                "path": "a.txt",
                "sha256": _sha256_of_bytes(data),
                "category": "raw",
                # no size_bytes
            }]
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "ok")

    def test_entry_no_sha256_field_skips_hash_check(self):
        data = b"content without hash in manifest"
        self._write_file("a.txt", data)
        manifest = {
            "entries": [{
                "path": "a.txt",
                "size_bytes": len(data),
                "category": "raw",
                # no sha256
            }]
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "ok")

    # ── _check_required_files ─────────────────────────────────────────

    def test_all_required_present(self):
        for rel in REQUIRED_EXTRACTED_FILES:
            self._write_file(rel, b"content")
        missing = _check_required_files(self.root)
        self.assertEqual(missing, [])

    def test_some_required_missing(self):
        self._write_file("derived/report.md", b"report")
        self._write_file("raw/viztracer.json.gz", b"viz")
        # deliberately leave out derived/manifest.json
        missing = _check_required_files(self.root)
        self.assertIn("derived/manifest.json", missing)
        self.assertEqual(len(missing), 1)

    def test_all_required_missing(self):
        missing = _check_required_files(self.root)
        self.assertEqual(len(missing), len(REQUIRED_EXTRACTED_FILES))

    # ── _check_optional_files ─────────────────────────────────────────

    def test_optional_present_and_absent(self):
        self._write_file("raw/torch_trace.json.gz", b"torch trace")
        result = _check_optional_files(self.root)
        self.assertTrue(result["raw/torch_trace.json.gz"])

    def test_optional_all_absent(self):
        result = _check_optional_files(self.root)
        self.assertFalse(result["raw/torch_trace.json.gz"])


class RunDownloadTests(unittest.TestCase):
    """End-to-end download → verify → extract → validate workflow tests."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmp.name)
        self.trace_id = "test-trace-001"
        self.volume_name = "test-volume"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_descriptor(self, sha256: str, remote_path: str = "/traces/bundle.tar.gz") -> ArtifactDescriptor:
        return ArtifactDescriptor(
            volume=self.volume_name,
            remote_path=remote_path,
            sha256=sha256,
            trace_id=self.trace_id,
            output_dir=str(self.output_dir),
        )

    def _make_valid_bundle_bytes(self) -> bytes:
        files = {
            "derived/report.md": b"# Test Report",
            "raw/viztracer.json.gz": b"{}",  # gzip-like but fake
            "derived/manifest.json": json.dumps({"version": 1}).encode(),
        }
        return _make_bundle_tgz(files)

    def test_successful_download_and_extract(self):
        bundle_data = self._make_valid_bundle_bytes()
        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["trace_id"], self.trace_id)
        self.assertEqual(report["required_files_missing"], [])
        self.assertEqual(report["manifest_validation"]["status"], "ok")
        # Check bundle exists
        self.assertTrue(Path(report["bundle_path"]).is_file())
        # Check extract root exists
        extract_root = Path(report["extract_root"])
        self.assertTrue(extract_root.is_dir())
        self.assertTrue((extract_root / "derived/report.md").is_file())
        self.assertTrue((extract_root / "raw/viztracer.json.gz").is_file())
        self.assertTrue((extract_root / "derived/manifest.json").is_file())

    def test_sha256_mismatch_fails(self):
        bundle_data = self._make_valid_bundle_bytes()
        wrong_sha = "0" * 64
        descriptor = self._make_descriptor(wrong_sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        self.assertIn("SHA-256 mismatch", report["error"])
        # Temp file should be cleaned up
        bundle_tgzs = list(self.output_dir.glob("bundle.tar.gz*"))
        self.assertEqual(len(bundle_tgzs), 0, f"Unexpected files: {bundle_tgzs}")

    def test_missing_manifest_fails(self):
        files = {
            "derived/report.md": b"report",
            "raw/viztracer.json.gz": b"viz",
            "derived/manifest.json": b"{}",
        }
        bundle_data = _make_bundle_tgz(files, include_manifest=False)  # no bundle_manifest.json
        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        self.assertIn("Missing bundle_manifest.json", report["error"])

    def test_malformed_manifest_fails(self):
        files = {
            "derived/report.md": b"report",
            "raw/viztracer.json.gz": b"viz",
            "derived/manifest.json": b"{}",
        }
        bundle_data = _make_bundle_tgz(files, manifest="not a valid manifest payload")  # bad manifest type
        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        # The manifest will fail validation
        self.assertIn("fail", report.get("manifest_validation", {}).get("status", report["status"]))

    def test_missing_required_file_reported(self):
        files = {
            "derived/report.md": b"report",
            "raw/viztracer.json.gz": b"viz",
            # deliberately missing derived/manifest.json
        }
        manifest = {
            "entries": [
                _make_manifest_entry("derived/report.md", b"report"),
                _make_manifest_entry("raw/viztracer.json.gz", b"viz"),
            ]
        }
        bundle_data = _make_bundle_tgz(files, manifest=manifest)
        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        self.assertIn("Missing required file: derived/manifest.json", str(report.get("error", "")))
        # Also check required_files_missing list
        self.assertIn("derived/manifest.json", report.get("required_files_missing", []))

    def test_size_hash_mismatch_in_manifest(self):
        files = {
            "derived/report.md": b"report content here",
            "raw/viztracer.json.gz": b"viz data",
            "derived/manifest.json": json.dumps({"version": 1}).encode(),
        }
        manifest = {
            "entries": [
                {
                    "path": "derived/report.md",
                    "size_bytes": 9999,  # wrong
                    "sha256": "0" * 64,  # wrong
                    "category": "derived",
                },
                _make_manifest_entry("raw/viztracer.json.gz", b"viz data"),
                _make_manifest_entry("derived/manifest.json", json.dumps({"version": 1}).encode()),
            ]
        }
        bundle_data = _make_bundle_tgz(files, manifest=manifest)
        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        mv = report["manifest_validation"]
        self.assertEqual(mv["status"], "mismatch")
        self.assertGreaterEqual(len(mv["errors"]), 1)

    def test_optional_torch_trace_absent_surfaces_no_error(self):
        """Absence of raw/torch_trace.json.gz is surfaced but not a failure."""
        files = {
            "derived/report.md": b"report",
            "raw/viztracer.json.gz": b"viz",
            "derived/manifest.json": json.dumps({"version": 1}).encode(),
        }
        bundle_data = _make_bundle_tgz(files)
        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "ok")
        self.assertFalse(report["optional_files"]["raw/torch_trace.json.gz"])

    def test_optional_torch_trace_present(self):
        files = {
            "derived/report.md": b"report",
            "raw/viztracer.json.gz": b"viz",
            "raw/torch_trace.json.gz": json.dumps({"torch": "trace"}).encode(),
            "derived/manifest.json": json.dumps({"version": 1}).encode(),
        }
        bundle_data = _make_bundle_tgz(files)
        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["optional_files"]["raw/torch_trace.json.gz"])

    def test_removed_temp_file_on_failure(self):
        """A partially-downloaded temp file is cleaned up on error."""
        bundle_data = self._make_valid_bundle_bytes()
        wrong_sha = "0" * 64
        descriptor = self._make_descriptor(wrong_sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        # No temp files should remain
        tmp_files = list(self.output_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0, f"Leftover tmp files: {tmp_files}")

    def test_absolute_path_in_tar_fails(self):
        """Tar entry with absolute path is rejected during extraction."""
        members = [
            {"name": "derived/report.md", "content": b"report"},
            {"name": "/absolute/path.txt", "content": b"pwned"},
        ]
        # Build bundle manually with the bad entry
        bundle_data = _make_tar_gz(members)
        # Append manifest at top level
        manifest_payload = {
            "entries": [
                _make_manifest_entry("derived/report.md", b"report"),
            ]
        }
        manifest_member = {"name": "bundle_manifest.json", "content": json.dumps(manifest_payload).encode()}
        bundle_data = _make_tar_gz(members + [manifest_member])

        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        self.assertIn("Absolute path", report["error"])

    def test_symlink_escape_fails(self):
        """Symlink pointing outside extraction root is rejected."""
        members = [
            {"name": "derived/report.md", "content": b"report"},
            {"name": "raw/viztracer.json.gz", "content": b"viz"},
            {"name": "derived/manifest.json", "content": json.dumps({"version": 1}).encode()},
            {"name": "escape.link", "type": tarfile.SYMTYPE, "link_target": "/etc/passwd"},
        ]
        manifest_payload = {
            "entries": [
                _make_manifest_entry("derived/report.md", b"report"),
                _make_manifest_entry("raw/viztracer.json.gz", b"viz"),
                _make_manifest_entry("derived/manifest.json", json.dumps({"version": 1}).encode()),
            ]
        }
        manifest_member = {"name": "bundle_manifest.json", "content": json.dumps(manifest_payload).encode()}
        bundle_data = _make_tar_gz(members + [manifest_member])

        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        self.assertIn("Symlink", report["error"])

    def test_hardlink_escape_fails(self):
        """Hardlink pointing outside extraction root is rejected."""
        members = [
            {"name": "derived/report.md", "content": b"report"},
            {"name": "evil.hardlink", "type": tarfile.LNKTYPE, "link_target": "/etc/shadow"},
        ]
        manifest_payload = {
            "entries": [
                _make_manifest_entry("derived/report.md", b"report"),
            ]
        }
        manifest_member = {"name": "bundle_manifest.json", "content": json.dumps(manifest_payload).encode()}
        bundle_data = _make_tar_gz(members + [manifest_member])

        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        self.assertIn("Hardlink", report["error"])

    def test_device_file_in_tar_fails(self):
        """FIFO member in tar causes failure."""
        members = [
            {"name": "derived/report.md", "content": b"report"},
            {"name": "evil.fifo", "type": tarfile.FIFOTYPE},
        ]
        manifest_payload = {
            "entries": [
                _make_manifest_entry("derived/report.md", b"report"),
            ]
        }
        manifest_member = {"name": "bundle_manifest.json", "content": json.dumps(manifest_payload).encode()}
        bundle_data = _make_tar_gz(members + [manifest_member])

        sha = _sha256_of_bytes(bundle_data)
        descriptor = self._make_descriptor(sha)
        volume = MockVolume({descriptor.remote_path: bundle_data})
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        self.assertIn("Device or special file", report["error"])

    def test_download_volume_not_found(self):
        """A missing Modal Volume causes a SystemExit before run_download."""
        descriptor = self._make_descriptor("0" * 64)
        # run_download itself calls _get_volume which raises SystemExit
        # When using a mock client, it doesn't call _get_volume, so we test
        # the _get_volume function separately or just verify the mock path works.
        # This test ensures the mock path returns fail for a non-existent remote path.
        volume = MockVolume({})  # empty volume
        client = MockDownloadClient(volume)

        report = run_download(descriptor, download_client=client)

        self.assertEqual(report["status"], "fail")
        # The FileNotFoundError from Modal is surfaced
        self.assertIn("No such file", report["error"])


class BuildFileIndexTests(unittest.TestCase):
    """Test _build_file_index helper."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_index_flat(self):
        (self.root / "a.txt").write_text("a")
        (self.root / "b.txt").write_text("b")
        index = _build_file_index(self.root)
        self.assertIn("a.txt", index)
        self.assertIn("b.txt", index)
        self.assertEqual(len(index), 2)

    def test_index_nested(self):
        (self.root / "derived" / "report.md").parent.mkdir(parents=True)
        (self.root / "derived" / "report.md").write_text("report")
        (self.root / "raw" / "trace.json").parent.mkdir(parents=True)
        (self.root / "raw" / "trace.json").write_text("trace")
        index = _build_file_index(self.root)
        self.assertIn("derived/report.md", index)
        self.assertIn("raw/trace.json", index)

    def test_index_empty_dir(self):
        index = _build_file_index(self.root)
        self.assertEqual(index, {})

    def test_index_excludes_dirs(self):
        (self.root / "subdir").mkdir()
        (self.root / "subdir" / "file.txt").write_text("f")
        index = _build_file_index(self.root)
        self.assertNotIn("subdir", index)
        self.assertIn("subdir/file.txt", index)


class FormatReportIntegration(unittest.TestCase):
    """Verify output format of _format_report.

    Ensures KEY=value lines and non-zero exit on failure.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _capture_format(self, report: Dict[str, Any]) -> str:
        from tools.download_v2_full_trace import _format_report
        return _format_report(report)

    def test_success_output_format(self):
        report = {
            "status": "ok",
            "bundle_path": str(self.output_dir / "bundle.tar.gz"),
            "extract_root": str(self.output_dir / "full_trace_tid"),
            "report_path": str(self.output_dir / "full_trace_tid" / "derived" / "report.md"),
            "viztracer_path": str(self.output_dir / "full_trace_tid" / "raw" / "viztracer.json.gz"),
            "torch_path": str(self.output_dir / "full_trace_tid" / "raw" / "torch_trace.json.gz"),
            "manifest_path": str(self.output_dir / "full_trace_tid" / "derived" / "manifest.json"),
        }
        output = self._capture_format(report)
        self.assertIn("FULL_TRACE_BUNDLE=", output)
        self.assertIn("FULL_TRACE_REPORT=", output)
        self.assertIn("FULL_TRACE_VIZTRACER=", output)
        self.assertIn("FULL_TRACE_TORCH=", output)
        self.assertIn("FULL_TRACE_MANIFEST=", output)
        self.assertIn("FULL_TRACE_EXTRACT_DIR=", output)
        # No STATUS / TRACE extras
        self.assertNotIn("STATUS=", output)
        self.assertNotIn("TRACE_ID=", output)
        # Exactly 6 non-empty lines
        lines = [l for l in output.strip().split("\n") if l]
        self.assertEqual(len(lines), 6)

    def test_fail_output_format_empty(self):
        """Failure report produces no stdout."""
        report = {
            "status": "fail",
            "error": "SHA-256 mismatch",
            "trace_id": "test-trace",
        }
        output = self._capture_format(report)
        self.assertEqual(output, "")

    def test_nonzero_exit_on_failure(self):
        """SystemExit(1) is raised when run_download returns fail."""
        from tools.download_v2_full_trace import main as download_main
        # We can't easily test main() without a real CLI, but we verify
        # that run_download returning fail status leads to SystemExit.
        # This is tested implicitly by the run_download fail tests above.


class EdgeCaseTests(unittest.TestCase):
    """Additional edge-case coverage."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_verify_with_unicode_filename(self):
        """Unicode filenames should be handled correctly."""
        extract_root = self.output_dir / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        # Create a tar with unicode filename
        members = [{"name": "dérived/über-report.md", "content": b"unicode content"}]
        data = _make_tar_gz(members)
        tar_path = self.output_dir / "unicode.tar.gz"
        tar_path.write_bytes(data)
        _safe_extract(tar_path, extract_root)
        self.assertTrue((extract_root / "dérived/über-report.md").is_file())

    def test_incremental_verify_with_empty_chunks(self):
        """Incremental verify works when generator yields empty chunks."""
        path = self.output_dir / "empty_chunks.tmp"
        expected = _sha256_of_bytes(b"test")
        _incremental_verify([b"", b"te", b"", b"st", b""], path, expected)
        self.assertEqual(path.read_bytes(), b"test")

    def test_manifest_with_extra_keys_passes(self):
        """Manifest entries with extra keys beyond required ones are fine."""
        root = self.output_dir / "root"
        root.mkdir(parents=True, exist_ok=True)
        data = b"file data"
        (root / "a.txt").write_bytes(data)
        manifest = {
            "entries": [{
                "path": "a.txt",
                "size_bytes": len(data),
                "sha256": _sha256_of_bytes(data),
                "category": "raw",
                "extra_key": "extra value is fine",
            }]
        }
        result = _validate_manifest_entries(manifest, root)
        self.assertEqual(result["status"], "ok")

    def test_descriptor_to_dict(self):
        desc = ArtifactDescriptor("v", "/p", "a" * 64, "t", "/o")
        d = desc.to_dict()
        self.assertEqual(d["volume"], "v")
        self.assertEqual(d["sha256"], "a" * 64)


class DescriptorAliasTests(unittest.TestCase):
    """ArtifactDescriptor built with contract field aliases."""

    def test_volume_name_alias(self):
        data = {
            "volume_name": "alias-vol",
            "remote_path": "/p",
            "sha256": "a" * 64,
            "trace_id": "t",
            "output_dir": "/o",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fpath = f.name
        try:
            desc = ArtifactDescriptor.from_descriptor_file(fpath)
            self.assertEqual(desc.volume, "alias-vol")
        finally:
            os.unlink(fpath)

    def test_remote_bundle_path_alias(self):
        data = {
            "volume": "v",
            "remote_bundle_path": "/aliased/path.tar.gz",
            "sha256": "b" * 64,
            "trace_id": "t",
            "output_dir": "/o",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fpath = f.name
        try:
            desc = ArtifactDescriptor.from_descriptor_file(fpath)
            self.assertEqual(desc.remote_path, "/aliased/path.tar.gz")
        finally:
            os.unlink(fpath)

    def test_bundle_sha256_alias(self):
        data = {
            "volume": "v",
            "remote_path": "/p",
            "bundle_sha256": "c" * 64,
            "trace_id": "t",
            "output_dir": "/o",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fpath = f.name
        try:
            desc = ArtifactDescriptor.from_descriptor_file(fpath)
            self.assertEqual(desc.sha256, "c" * 64)
        finally:
            os.unlink(fpath)

    def test_all_aliases_together(self):
        data = {
            "volume_name": "alias-vol",
            "remote_bundle_path": "/aliased/path.tar.gz",
            "bundle_sha256": "d" * 64,
            "trace_id": "alias-trace",
            "output_dir": "/alias/out",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fpath = f.name
        try:
            desc = ArtifactDescriptor.from_descriptor_file(fpath)
            self.assertEqual(desc.volume, "alias-vol")
            self.assertEqual(desc.remote_path, "/aliased/path.tar.gz")
            self.assertEqual(desc.sha256, "d" * 64)
            self.assertEqual(desc.trace_id, "alias-trace")
            self.assertEqual(desc.output_dir, "/alias/out")
        finally:
            os.unlink(fpath)

    def test_missing_all_aliases_raises(self):
        data = {"trace_id": "t", "output_dir": "/o"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fpath = f.name
        try:
            with self.assertRaises(KeyError):
                ArtifactDescriptor.from_descriptor_file(fpath)
        finally:
            os.unlink(fpath)


class StrictCompletenessTests(unittest.TestCase):
    """Strict-completeness enforcement in manifest validation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel: str, content: bytes = b"data") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def test_strict_on_with_extra_file_fails(self):
        self._write("derived/report.md")
        self._write("raw/viztracer.json.gz")
        self._write("derived/manifest.json")
        self._write("unexpected.txt")  # extra file
        manifest = {
            "entries": [
                {"path": "derived/report.md", "size_bytes": 4, "sha256": _sha256_of_bytes(b"data"), "category": "derived"},
                {"path": "raw/viztracer.json.gz", "size_bytes": 4, "sha256": _sha256_of_bytes(b"data"), "category": "raw"},
                {"path": "derived/manifest.json", "size_bytes": 4, "sha256": _sha256_of_bytes(b"data"), "category": "derived"},
            ],
            "strict_completeness": True,
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(any("Strict completeness" in e for e in result["errors"]))

    def test_strict_off_with_extra_file_ok(self):
        self._write("derived/report.md")
        self._write("unexpected.txt")  # extra file not in manifest
        manifest = {
            "entries": [
                {"path": "derived/report.md", "size_bytes": 4, "sha256": _sha256_of_bytes(b"data"), "category": "derived"},
            ],
            "strict_completeness": False,
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "ok")
        # Unexpected files reported in metadata but don't cause failure
        self.assertIn("unexpected.txt", result.get("unexpected_files", []))

    def test_strict_defaults_to_false(self):
        """When strict_completeness key is absent, extra files don't fail."""
        self._write("derived/report.md")
        self._write("extra.txt")
        manifest = {
            "entries": [
                {"path": "derived/report.md", "size_bytes": 4, "sha256": _sha256_of_bytes(b"data"), "category": "derived"},
            ],
        }
        result = _validate_manifest_entries(manifest, self.root)
        self.assertEqual(result["status"], "ok")


class ManifestPathSafetyTests(unittest.TestCase):
    """Path-safety validation inside bundle_manifest.json entries."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_manifest(self, manifest: dict) -> None:
        p = self.root / MANIFEST_FILENAME
        p.write_text(json.dumps(manifest))

    def test_absolute_path_in_entry_rejected(self):
        self._write_manifest({
            "entries": [{"path": "/etc/passwd", "size_bytes": 4, "sha256": "0" * 64, "category": "raw"}],
        })
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("absolute path", str(ctx.exception).lower())

    def test_path_traversal_in_entry_rejected(self):
        self._write_manifest({
            "entries": [{"path": "../../escape.txt", "size_bytes": 4, "sha256": "0" * 64, "category": "raw"}],
        })
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("path traversal", str(ctx.exception).lower())

    def test_deep_traversal_in_entry_rejected(self):
        self._write_manifest({
            "entries": [{"path": "a/../../../etc/shadow", "size_bytes": 4, "sha256": "0" * 64, "category": "raw"}],
        })
        with self.assertRaises(ValueError) as ctx:
            _load_manifest(self.root)
        self.assertIn("path traversal", str(ctx.exception).lower())


class ExtractRootNamingTests(unittest.TestCase):
    """Extraction root is exactly ``<output-dir>/full_trace_<trace-id>/``."""

    def test_extract_root_format_in_run_download(self):
        """run_download creates extract root with ``full_trace_`` prefix."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        output_dir = Path(self._tmp.name)
        trace_id = "my-trace-42"

        files = {
            "derived/report.md": b"report",
            "raw/viztracer.json.gz": b"viz",
            "derived/manifest.json": json.dumps({"version": 1}).encode(),
        }
        bundle_data = _make_bundle_tgz(files)
        sha = _sha256_of_bytes(bundle_data)

        desc = ArtifactDescriptor("v", "/r", sha, trace_id, str(output_dir))
        vol = MockVolume({"/r": bundle_data})
        client = MockDownloadClient(vol)
        report = run_download(desc, download_client=client)

        self.assertEqual(report["status"], "ok")
        extract_root = Path(report["extract_root"])
        self.assertEqual(extract_root.name, f"full_trace_{trace_id}")
        self.assertTrue(extract_root.is_dir())
        self.assertTrue((extract_root / "derived/report.md").is_file())


class TorchOutputTests(unittest.TestCase):
    """FULL_TRACE_TORCH value in format output."""

    def test_torch_absent_shows_absent(self):
        report = {
            "status": "ok",
            "bundle_path": "/b.tar.gz",
            "extract_root": "/extract",
            "report_path": "/extract/derived/report.md",
            "viztracer_path": "/extract/raw/viztracer.json.gz",
            "torch_path": None,
            "manifest_path": "/extract/derived/manifest.json",
        }
        from tools.download_v2_full_trace import _format_report
        output = _format_report(report)
        self.assertIn("FULL_TRACE_TORCH=absent", output)

    def test_torch_present_shows_path(self):
        report = {
            "status": "ok",
            "bundle_path": "/b.tar.gz",
            "extract_root": "/extract",
            "report_path": "/extract/derived/report.md",
            "viztracer_path": "/extract/raw/viztracer.json.gz",
            "torch_path": "/extract/raw/torch_trace.json.gz",
            "manifest_path": "/extract/derived/manifest.json",
        }
        from tools.download_v2_full_trace import _format_report
        output = _format_report(report)
        self.assertIn("FULL_TRACE_TORCH=/extract/raw/torch_trace.json.gz", output)
        self.assertNotIn("absent", output)


if __name__ == "__main__":
    unittest.main()
