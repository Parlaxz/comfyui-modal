"""CPU-only unit tests for tools.benchmark_source_io_e14.

Builds tiny, valid safetensors fixtures on the fly (two shards with the same
basename in different directories to exercise TMP_STAGE collision safety, a
gap between tensor data extents, and trailing bytes) and verifies manifest
parsing, contiguous-region merging, per-arm byte accounting, cache metadata,
markdown rendering, the optional pinned subtest, and the standalone CLI
wrapper.  No Modal, no deploy, no network, no CUDA.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.benchmark_source_io_e14 as e14
from tools.benchmark_source_io_e14 import (
    CURRENT_RANGE,
    MMAP,
    PREAD,
    SEQUENTIAL,
    TMP_STAGE,
    load_manifest,
    render_markdown,
    run_benchmark,
    run_current_range,
    run_mmap,
    run_pinned_subtest,
    run_sequential,
    run_tmp_stage,
)

_IDENTITY_CHUNK = 1 << 20


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_IDENTITY_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_shard(path: Path, tensors, gap: int = 0, trailing: int = 0) -> None:
    """Write a valid safetensors file.

    ``tensors`` is a list of (name, raw_bytes).  A ``gap`` of zero bytes is
    inserted between consecutive tensor data extents (so gap=0 makes them
    physically adjacent), and ``trailing`` bytes are appended after the last
    tensor.  Header is 8-byte little-endian JSON length followed by the JSON
    header; ``data_offsets`` are relative to the start of the data section.
    """
    data = b""
    entries = {}
    for index, (name, raw) in enumerate(tensors):
        begin = len(data)
        data += raw
        end = len(data)
        entries[name] = {
            "dtype": "F32",
            "shape": [len(raw)],
            "data_offsets": [begin, end],
        }
        if index < len(tensors) - 1:
            data += b"\x00" * gap
    data += b"\x00" * trailing
    header = json.dumps(entries, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + data)


def _parse_expected(path: Path) -> dict:
    """Independently parse a shard to compute expected manifest values."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        header_len = struct.unpack("<Q", handle.read(8))[0]
        header = json.loads(handle.read(header_len).decode("utf-8"))
    data_bytes = size - 8 - header_len
    extents = []
    payload = 0
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        begin, end = entry["data_offsets"]
        extents.append((8 + header_len + begin, 8 + header_len + end, name))
        payload += end - begin
    extents.sort(key=lambda item: (item[0], item[1]))
    return {
        "path": str(path),
        "size_bytes": size,
        "header_len": header_len,
        "data_bytes": data_bytes,
        "extents": extents,
        "payload_bytes": payload,
        "sha256": _file_sha256(path),
    }


def _expected_payload_sha256(shards) -> str:
    digest = hashlib.sha256()
    for shard in shards:
        with open(shard["path"], "rb") as handle:
            for begin, end, _name in shard["extents"]:
                handle.seek(begin)
                remaining = end - begin
                while remaining:
                    chunk = handle.read(min(remaining, _IDENTITY_CHUNK))
                    digest.update(chunk)
                    remaining -= len(chunk)
    return digest.hexdigest()


class E14FixtureMixin:
    """Builds the two-shard fixture set and exposes expected values."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="e14_test_")
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        dir_a = Path(self._tmp) / "a"
        dir_b = Path(self._tmp) / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        # Same basename in two different directories -> TMP_STAGE collision risk.
        self.shard_a = dir_a / "weights.safetensors"
        self.shard_b = dir_b / "weights.safetensors"
        # Shard A: two tensors separated by a GAP, plus trailing bytes.
        _write_shard(
            self.shard_a,
            [("t0", b"AAAA"), ("t1", b"BBBBBB")],
            gap=3,
            trailing=5,
        )
        # Shard B: two tensors ADJACENT (no gap), plus trailing bytes.
        _write_shard(
            self.shard_b,
            [("u0", b"CC"), ("u1", b"DDDDDDDD")],
            gap=0,
            trailing=4,
        )
        self.expected_a = _parse_expected(self.shard_a)
        self.expected_b = _parse_expected(self.shard_b)
        self.expected_shards = [self.expected_a, self.expected_b]
        self.expected_payload = (
            self.expected_a["payload_bytes"] + self.expected_b["payload_bytes"]
        )
        self.expected_digest = _expected_payload_sha256(self.expected_shards)
        self.manifest = load_manifest([dir_a, dir_b])


class ManifestTests(E14FixtureMixin, unittest.TestCase):
    def test_deterministic_file_ordering(self):
        # Files must be sorted by full path string regardless of input order.
        manifest = load_manifest([self._tmp])
        self.assertEqual(
            manifest["files"],
            [str(self.shard_a), str(self.shard_b)],
        )
        self.assertEqual(
            [shard["path"] for shard in manifest["shards"]],
            [str(self.shard_a), str(self.shard_b)],
        )

    def test_header_and_extent_absolute_offsets(self):
        shard_a = self.manifest["shards"][0]
        shard_b = self.manifest["shards"][1]
        self.assertEqual(shard_a["header_len"], self.expected_a["header_len"])
        self.assertEqual(shard_a["data_bytes"], self.expected_a["data_bytes"])
        self.assertEqual(shard_b["header_len"], self.expected_b["header_len"])
        self.assertEqual(shard_b["data_bytes"], self.expected_b["data_bytes"])
        # Absolute extents (8 + header_len + relative offset).
        self.assertEqual(shard_a["extents"], self.expected_a["extents"])
        self.assertEqual(shard_b["extents"], self.expected_b["extents"])
        # Gap between t0 and t1 must be reflected in absolute offsets.
        t0_end = shard_a["extents"][0][1]
        t1_begin = shard_a["extents"][1][0]
        self.assertEqual(t1_begin - t0_end, 3)
        # Adjacent tensors in shard B share a boundary.
        u0_end = shard_b["extents"][0][1]
        u1_begin = shard_b["extents"][1][0]
        self.assertEqual(u1_begin - u0_end, 0)

    def test_payload_byte_total(self):
        self.assertEqual(self.manifest["payload_bytes"], self.expected_payload)
        self.assertEqual(
            sum(shard["payload_bytes"] for shard in self.manifest["shards"]),
            self.expected_payload,
        )

    def test_full_file_identity_fields(self):
        for shard, expected in zip(self.manifest["shards"], self.expected_shards):
            self.assertEqual(shard["size_bytes"], expected["size_bytes"])
            self.assertEqual(shard["sha256"], expected["sha256"])
            self.assertEqual(shard["payload_bytes"], expected["payload_bytes"])

    def test_expected_payload_digest(self):
        self.assertEqual(
            self.manifest["expected_payload_sha256"],
            self.expected_digest,
        )


class ContiguousRegionTests(E14FixtureMixin, unittest.TestCase):
    def test_adjacent_extents_merge_no_gap_merging(self):
        # Shard A has a gap -> two separate regions.
        regions_a = list(e14._contiguous_regions_of(self.manifest["shards"][0]))
        self.assertEqual(len(regions_a), 2)
        # Shard B has adjacent extents -> merged into one region.
        regions_b = list(e14._contiguous_regions_of(self.manifest["shards"][1]))
        self.assertEqual(len(regions_b), 1)
        merged_begin, merged_end = regions_b[0]
        self.assertEqual(merged_end - merged_begin, 10)  # 2 + 8

    def test_iter_contiguous_regions_preserves_payload_order(self):
        regions = list(e14._iter_contiguous_regions(self.manifest))
        # Shard A: two regions; Shard B: one region -> 3 total.
        self.assertEqual(len(regions), 3)
        total = sum(length for _path, _begin, length in regions)
        self.assertEqual(total, self.expected_payload)


class ArmAccountingTests(E14FixtureMixin, unittest.TestCase):
    def test_all_arms_equal_payload_and_digest(self):
        results = run_benchmark(
            self.manifest,
            arms=[CURRENT_RANGE, SEQUENTIAL, TMP_STAGE, MMAP, PREAD],
            block_mib=1,
            range_mib=1,
            cache_label="cold_unknown",
        )
        by_arm = {arm["arm"]: arm for arm in results["arms"]}
        for arm in (CURRENT_RANGE, SEQUENTIAL, TMP_STAGE, MMAP):
            record = by_arm[arm]
            self.assertEqual(record["status"], "ok", record.get("error"))
            self.assertIs(record["digest_match"], True)
            self.assertEqual(record["payload_bytes"], self.expected_payload)
            self.assertEqual(record["bytes"], self.expected_payload)
        # PREAD is either UNSUPPORTED (no public API) or a valid ok run.
        pread = by_arm[PREAD]
        self.assertIn(pread["status"], ("ok", "unsupported"))
        if pread["status"] == "ok":
            self.assertIs(pread["digest_match"], True)
            self.assertEqual(pread["payload_bytes"], self.expected_payload)

    def test_exact_source_byte_accounting(self):
        results = run_benchmark(
            self.manifest,
            arms=[CURRENT_RANGE, SEQUENTIAL, TMP_STAGE, MMAP],
            block_mib=1,
            range_mib=1,
            cache_label="cold_unknown",
        )
        by_arm = {arm["arm"]: arm for arm in results["arms"]}
        # Extent-only arms read exactly the payload bytes.
        for arm in (CURRENT_RANGE, SEQUENTIAL, MMAP):
            self.assertEqual(by_arm[arm]["source_bytes_read"], self.expected_payload)
        # TMP_STAGE copies the full files, then rereads only the payload.
        tmp = by_arm[TMP_STAGE]
        self.assertEqual(tmp["source_bytes_read"], self.manifest["total_size_bytes"])
        self.assertEqual(tmp["local_reread_bytes"], self.expected_payload)


class TmpStageTests(E14FixtureMixin, unittest.TestCase):
    def test_same_basenames_use_distinct_staged_paths_and_cleanup(self):
        results = run_benchmark(
            self.manifest,
            arms=[TMP_STAGE],
            block_mib=1,
            cache_label="cold_unknown",
            keep_temp=True,
            temp_dir=self._tmp,
        )
        tmp = results["arms"][0]
        self.assertEqual(tmp["status"], "ok", tmp.get("error"))
        self.assertIs(tmp["digest_match"], True)
        temp_dir = Path(tmp["temp_dir"])
        self.assertTrue(temp_dir.is_dir())
        staged = sorted(p.name for p in temp_dir.iterdir() if p.is_file())
        # Two staged files, distinct names despite identical basenames.
        self.assertEqual(len(staged), 2)
        self.assertEqual(len(set(staged)), 2)
        self.assertTrue(all(name.endswith("_weights.safetensors") for name in staged))
        # Timing/rate fields are present (values not asserted).
        for field in (
            "temp_copy_ms",
            "temp_copy_cpu_ms",
            "temp_reread_ms",
            "temp_reread_cpu_ms",
            "combined_ms",
            "temp_copy_GBps",
            "temp_reread_GBps",
        ):
            self.assertIsNotNone(tmp.get(field), field)
        shutil.rmtree(temp_dir, ignore_errors=True)
        self.assertFalse(temp_dir.exists())

    def test_keep_temp_false_cleans_up(self):
        results = run_benchmark(
            self.manifest,
            arms=[TMP_STAGE],
            block_mib=1,
            cache_label="cold_unknown",
            keep_temp=False,
            temp_dir=self._tmp,
        )
        tmp = results["arms"][0]
        self.assertEqual(tmp["status"], "ok", tmp.get("error"))
        self.assertIsNone(tmp["temp_dir"])


class ReadDistributionTests(E14FixtureMixin, unittest.TestCase):
    def test_sequential_honors_small_block_and_merges_contiguous(self):
        record = run_sequential(self.manifest, block_bytes=3, cache_label="cold_unknown")
        self.assertEqual(record["status"], "ok", record.get("error"))
        self.assertIs(record["digest_match"], True)
        # 4 bytes -> 3+1 (2 calls), 6 bytes -> 3+3 (2 calls) for shard A;
        # merged 10 bytes -> 3+3+3+1 (4 calls) for shard B. Total 8 calls.
        self.assertEqual(record["read_call_count"], 8)
        self.assertEqual(record["min_read_bytes"], 1)
        self.assertEqual(record["max_read_bytes"], 3)
        self.assertEqual(record["source_bytes_read"], self.expected_payload)

    def test_current_range_honors_small_range(self):
        record = run_current_range(self.manifest, range_bytes=3, cache_label="cold_unknown")
        self.assertEqual(record["status"], "ok", record.get("error"))
        self.assertIs(record["digest_match"], True)
        # Extent-wise reads (no merging): t0 3+1, t1 3+3, u0 2, u1 3+3+2 -> 8 calls.
        self.assertEqual(record["read_call_count"], 8)
        self.assertEqual(record["min_read_bytes"], 1)
        self.assertEqual(record["max_read_bytes"], 3)
        self.assertEqual(record["source_bytes_read"], self.expected_payload)

    def test_mmap_honors_small_block(self):
        record = run_mmap(self.manifest, block_bytes=3, cache_label="cold_unknown")
        self.assertEqual(record["status"], "ok", record.get("error"))
        self.assertIs(record["digest_match"], True)
        self.assertEqual(record["read_call_count"], 8)
        self.assertEqual(record["source_bytes_read"], self.expected_payload)


class CacheMetadataTests(E14FixtureMixin, unittest.TestCase):
    def test_one_drop_attempt_per_selected_arm(self):
        mocked = {"attempted": True, "supported": False, "error": "mocked"}
        with mock.patch.object(e14, "_attempt_drop_caches", return_value=mocked):
            results = run_benchmark(
                self.manifest,
                arms=[SEQUENTIAL, MMAP],
                block_mib=1,
                cache_label="cold_unknown",
                drop_caches=True,
            )
        cache = results["cache"]
        self.assertEqual(len(cache["drop_attempts"]), 2)
        self.assertIs(cache["drop_attempted"], True)
        self.assertIs(cache["drop_supported"], False)
        self.assertEqual(cache["drop_error"], "mocked")
        for arm in results["arms"]:
            self.assertEqual(arm["cache_drop_before_arm"], mocked)

    def test_contradictory_warm_plus_drop_rejected(self):
        with self.assertRaises(ValueError):
            run_benchmark(
                self.manifest,
                arms=[SEQUENTIAL],
                block_mib=1,
                cache_label="page_cache_warm",
                drop_caches=True,
            )

    def test_no_drop_is_noop(self):
        record = e14._attempt_drop_caches(False)
        self.assertIs(record["attempted"], False)


class MarkdownTests(E14FixtureMixin, unittest.TestCase):
    def test_markdown_has_caveats_and_local_vs_remote(self):
        results = run_benchmark(
            self.manifest,
            arms=[SEQUENTIAL, TMP_STAGE],
            block_mib=1,
            cache_label="cold_unknown",
        )
        md = render_markdown(results)
        # Exact-byte / cache caveat.
        self.assertIn("cache_label is a requested process-level label", md)
        self.assertIn("Windows cannot drop the page cache", md)
        # Explicit local-vs-remote section.
        self.assertIn("Local observations vs remote conclusions", md)
        self.assertIn("must NOT be drawn from this report", md)
        self.assertIn("Nothing here ran on Modal containers", md)


class PinnedSubtestTests(E14FixtureMixin, unittest.TestCase):
    def test_pinned_subtest_fails_soft(self):
        record = run_pinned_subtest(self.manifest, block_bytes=64)
        self.assertIn(record["status"], ("unsupported", "error", "ok"))
        if record["status"] == "ok":
            self.assertIs(record["digest_match"], True)
            self.assertEqual(record["bytes"], self.expected_payload)

    def test_pinned_subtest_via_benchmark_fails_soft(self):
        results = run_benchmark(
            self.manifest,
            arms=[SEQUENTIAL],
            block_mib=1,
            cache_label="cold_unknown",
            pinned_subtest=True,
        )
        sub = results["pinned_subtest"]
        self.assertIsNotNone(sub)
        self.assertIn(sub["status"], ("unsupported", "error", "ok"))
        if sub["status"] == "ok":
            self.assertIs(sub["digest_match"], True)


class WrapperTests(E14FixtureMixin, unittest.TestCase):
    def test_main_launches_standalone_tool(self):
        json_out = Path(self._tmp) / "out.json"
        md_out = Path(self._tmp) / "out.md"
        rc = e14.main([
            str(self._tmp),
            "--block-mib", "1",
            "--range-mib", "1",
            "--cache-label", "cold_unknown",
            "--json-out", str(json_out),
            "--markdown-out", str(md_out),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue(json_out.exists())
        self.assertTrue(md_out.exists())
        data = json.loads(json_out.read_text(encoding="utf-8"))
        self.assertEqual(data["tool"], "benchmark_source_io_e14")
        self.assertEqual(data["config"]["block_mib"], 1)
        self.assertEqual(data["config"]["range_mib"], 1)

    def test_no_modal_deploy_or_run_command(self):
        source = Path(e14.__file__).read_text(encoding="utf-8")
        self.assertNotIn("modal deploy", source)
        self.assertNotIn("modal run", source)

    def test_explicit_cache_block_range_defaults(self):
        source = Path(e14.__file__).read_text(encoding="utf-8")
        self.assertIn("default=256", source)  # --block-mib
        self.assertIn("default=32", source)  # --range-mib
        self.assertIn('default="cold_unknown"', source)  # --cache-label


class BatchFileTests(unittest.TestCase):
    """CPU-only checks on the run_e14_source_io.bat wrapper.

    Verifies the batch file invokes the standalone source-I/O tool with the
    explicit block/range/cache-label defaults and never references Modal or the
    v2 single-run deploy wrappers.
    """

    @classmethod
    def setUpClass(cls):
        cls.bat_path = Path(__file__).resolve().parent.parent / "run_e14_source_io.bat"
        cls.bat_text = cls.bat_path.read_text(encoding="utf-8")

    def test_batch_file_exists(self):
        self.assertTrue(self.bat_path.is_file())

    def test_batch_invokes_standalone_tool(self):
        self.assertIn("python tools\\benchmark_source_io_e14.py", self.bat_text)

    def test_batch_explicit_block_range_cache_defaults(self):
        # Explicit CLI flags passed to the tool.
        self.assertIn("--block-mib", self.bat_text)
        self.assertIn("--range-mib", self.bat_text)
        self.assertIn("--cache-label", self.bat_text)
        # Defaults/variables are declared explicitly.
        self.assertIn("E14_BLOCK_MIB=256", self.bat_text)
        self.assertIn("E14_RANGE_MIB=32", self.bat_text)
        self.assertIn("E14_CACHE_LABEL=cold_unknown", self.bat_text)

    def test_batch_has_no_modal_or_v2_deploy(self):
        self.assertNotIn("modal deploy", self.bat_text)
        self.assertNotIn("modal run", self.bat_text)
        self.assertNotIn("deploy_and_run_v2_single.bat", self.bat_text)
        self.assertNotIn("run_v2_single.bat", self.bat_text)


if __name__ == "__main__":
    unittest.main()
