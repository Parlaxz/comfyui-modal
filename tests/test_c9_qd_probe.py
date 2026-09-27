"""Offline tests for the C9 Modal Volume queue-depth probe
(``comfymodal_runtime.unet_qd_probe``).

Pure-math, hashing, validity, and synthetic-file smoke tests only — no Modal
calls, no GPU, no real model.  The paid measurement runs on the Linux Modal
container via ``run_unet_qd_probe``.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import comfymodal_runtime.unet_qd_probe as qdp

_TOTAL = 12_309_817_472  # exact ZImage data-section bytes


class StaticSegmentsTests(unittest.TestCase):
    def test_exact_coverage(self):
        for qd in (1, 2, 4, 8, 16):
            segs = qdp.static_segments(_TOTAL, qd)
            self.assertEqual(sum(e - s for s, e in segs), _TOTAL)
            ok, reason = qdp.partition_coverage(segs, _TOTAL)
            self.assertTrue(ok, reason)
            self.assertLessEqual(len(segs), qd)

    def test_remainder_handling(self):
        segs = qdp.static_segments(100, 3)
        self.assertEqual([(0, 34), (34, 68), (68, 100)], segs)
        ok, _ = qdp.partition_coverage(segs, 100)
        self.assertTrue(ok)

    def test_single_worker(self):
        segs = qdp.static_segments(1234, 1)
        self.assertEqual([(0, 1234)], segs)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            qdp.static_segments(-1, 2)
        with self.assertRaises(ValueError):
            qdp.static_segments(100, 0)


class PartitionCoverageTests(unittest.TestCase):
    def test_detects_gap(self):
        ok, reason = qdp.partition_coverage([(0, 10), (12, 20)], 20)
        self.assertFalse(ok)
        self.assertIn("gap", reason)

    def test_detects_overlap(self):
        ok, _ = qdp.partition_coverage([(0, 10), (5, 20)], 20)
        self.assertFalse(ok)

    def test_detects_wrong_total(self):
        ok, _ = qdp.partition_coverage([(0, 10)], 11)
        self.assertFalse(ok)

    def test_empty(self):
        self.assertTrue(qdp.partition_coverage([], 0)[0])
        self.assertFalse(qdp.partition_coverage([], 5)[0])


class DynamicBlocksTests(unittest.TestCase):
    def test_exact_coverage(self):
        for total, block in ((100, 32), (_TOTAL, 64 * 1024 * 1024),
                             (123456789, 128 * 1024 * 1024)):
            items = qdp.dynamic_blocks(total, block)
            self.assertEqual(sum(ln for _, ln in items), total)
            self.assertTrue(all(ln <= block for _, ln in items))
            off = 0
            for s, ln in items:
                self.assertEqual(s, off)
                off += ln

    def test_invalid(self):
        with self.assertRaises(ValueError):
            qdp.dynamic_blocks(10, 0)


class RotateWindowTests(unittest.TestCase):
    def test_rotation_distinct(self):
        wins = [qdp.rotate_window(i, 2 * 1024 * 1024 * 1024, _TOTAL)
                for i in range(6)]
        starts = [w[0] for w in wins]
        self.assertEqual(len(set(starts)), 6)

    def test_wraps(self):
        self.assertEqual(qdp.rotate_window(6, 2 * 1024 * 1024 * 1024, _TOTAL),
                         qdp.rotate_window(0, 2 * 1024 * 1024 * 1024, _TOTAL))

    def test_clamps_to_total(self):
        start, ln = qdp.rotate_window(0, 2 * 1024 * 1024 * 1024, 100)
        self.assertLessEqual(start + ln, 100)
        self.assertGreaterEqual(start, 0)


class SampleRegionsTests(unittest.TestCase):
    def test_bounded(self):
        regions = qdp.sample_regions(_TOTAL)
        self.assertGreaterEqual(len(regions), 4)
        for s, ln in regions:
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(s + ln, _TOTAL)
            self.assertLessEqual(ln, qdp._HASH_SEG)

    def test_head_tail_present(self):
        total = 2 * 1024 * 1024 * 1024
        regions = qdp.sample_regions(total)
        starts = {s for s, _ in regions}
        self.assertIn(0, starts)
        self.assertIn(total - qdp._HASH_SEG, starts)


class HashValidityTests(unittest.TestCase):
    def test_sample_hash_deterministic(self):
        import torch
        tensors_a = {"a": torch.arange(100000, dtype=torch.float32),
                     "b": torch.zeros(64, dtype=torch.bfloat16)}
        tensors_b = {"a": tensors_a["a"].clone(),
                     "b": tensors_a["b"].clone()}
        self.assertEqual(qdp.sample_hash_of_tensors(tensors_a),
                         qdp.sample_hash_of_tensors(tensors_b))
        tensors_c = dict(tensors_a)
        tensors_c["a"] = torch.ones_like(tensors_c["a"])
        self.assertNotEqual(qdp.sample_hash_of_tensors(tensors_a),
                            qdp.sample_hash_of_tensors(tensors_c))

    def test_sample_hash_sorted_order(self):
        import torch
        a = {"k1": torch.arange(10, dtype=torch.float32),
             "k2": torch.ones(10, dtype=torch.float32)}
        b = {"k2": a["k2"].clone(), "k1": a["k1"].clone()}
        self.assertEqual(qdp.sample_hash_of_tensors(a),
                         qdp.sample_hash_of_tensors(b))

    def test_key_set_ok(self):
        header = {"__metadata__": {}, "a": {"data_offsets": [0, 4]},
                  "b": {"data_offsets": [4, 8]}}
        self.assertTrue(qdp.key_set_ok(["a", "b"], header))
        self.assertTrue(qdp.key_set_ok(["b", "a"], header))
        self.assertFalse(qdp.key_set_ok(["a"], header))
        self.assertFalse(qdp.key_set_ok(["a", "b", "c"], header))

    def test_spot_check(self):
        import torch
        header = {"__metadata__": {},
                  "t0": {"dtype": "F32", "shape": [2, 3],
                         "data_offsets": [0, 24]},
                  "t1": {"dtype": "BF16", "shape": [4],
                         "data_offsets": [24, 32]}}
        tensors = {"t0": torch.zeros(2, 3), "t1": torch.zeros(4, dtype=torch.bfloat16)}
        res = qdp.spot_check_tensors(tensors, header)
        self.assertTrue(res["ok"], res)
        bad = dict(tensors)
        bad["t1"] = torch.zeros(4, dtype=torch.float32)
        self.assertFalse(qdp.spot_check_tensors(bad, header)["ok"])

    def test_tensor_bytes_from_header(self):
        header = {"a": {"data_offsets": [0, 10]}, "b": {"data_offsets": [10, 30]}}
        self.assertEqual(qdp.tensor_bytes_from_header(header), 30)


class PinnedAllocTests(unittest.TestCase):
    def test_alloc_free(self):
        buf, peak = qdp.pinned_alloc(1024 * 1024)
        self.assertGreaterEqual(peak, 1024 * 1024)
        qdp.pinned_free(buf)
        self.assertEqual(qdp._PINNED_LIVE_BYTES[0], 0)


def _make_synthetic_safetensors(path: Path, nbytes: int = 8 * 1024 * 1024):
    """Create a small real safetensors file with a few tensors."""
    import numpy as np
    import torch
    import safetensors.torch as st
    n = nbytes // 4
    tensors = {
        "a": torch.from_numpy(np.arange(n // 2, dtype=np.float32)),
        "b": torch.from_numpy(np.full(n // 2, 3.5, dtype=np.float32)),
        "c": torch.zeros(4, dtype=torch.bfloat16),
    }
    st.save_file(tensors, str(path))
    return path


class BatterySmokeTests(unittest.TestCase):
    def test_structural_mode_synthetic_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = _make_synthetic_safetensors(Path(td) / "synth.safetensors")
            result = qdp.run_unet_qd_probe_battery(str(path), mode="structural")
            self.assertIsInstance(result, dict)
            self.assertEqual(result.get("probe"), "unet_qd")
            sections = result.get("sections") or {}
            self.assertIn("env", sections)
            self.assertIn("file", sections)
            self.assertIn("loader_imports", sections)
            self.assertIn("structural_qd1", sections)
            self.assertEqual(sections["file"]["status"], "ok")
            self.assertEqual(sections["file"]["tensor_count"], 3)
            self.assertGreater(sections["file"]["total_data_bytes"], 0)
            self.assertIn("summary", sections)

    def test_evidence_mode_synthetic_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = _make_synthetic_safetensors(Path(td) / "synth2.safetensors")
            result = qdp.run_unet_qd_probe_battery(str(path), mode="evidence")
            self.assertIsInstance(result, dict)
            sections = result.get("sections") or {}
            for key in ("baseline_mmap", "baseline_seq_preadv", "screen",
                        "fullfile", "fullfile_warm_qd1_control",
                        "gpu_transfer", "external", "summary"):
                self.assertIn(key, sections)
            self.assertEqual(sections["baseline_mmap"]["tensor_count"], 3)
            self.assertGreater(sections["baseline_mmap"]["aggregate_gbps"], 0.0)
            summary = sections["summary"]
            self.assertEqual(summary["total_data_bytes"],
                             sections["file"]["total_data_bytes"])
            self.assertIn("qd_ratios", summary)

    def test_evidence_mode_missing_file(self):
        result = qdp.run_unet_qd_probe_battery("C:/definitely/not/here.safetensors",
                                               mode="evidence")
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("error"), "header_unavailable")


class LoaderImportTests(unittest.TestCase):
    def test_import_probe_never_raises(self):
        out = qdp._loader_imports()
        self.assertIn("runai_model_streamer", out)
        self.assertIn("fastsafetensors", out)
        self.assertIn("safetensors_version", out)


class FullPathMockedPreadvTests(unittest.TestCase):
    """Exercise the COMPLETE worker path (threads, pinned buffers, steady
    state, verification, JSON-safety) on Windows by faking os.preadv with
    os.pread over a real synthetic file."""

    @staticmethod
    def _install_fake_preadv():
        import os as _os
        import threading as _th
        if callable(getattr(_os, "preadv", None)):
            return None  # real preadv available; nothing to do
        if not callable(getattr(_os, "pread", None)):
            # Positional reads via a lock-guarded lseek+read (Windows build
            # without os.pread).  Correct content, serialized access — fine
            # for exercising the worker/verify/steady-state machinery.
            _lock = _th.Lock()

            def _fake_preadv(fd, iovs, offset):
                mv = iovs[0]
                n = len(mv)
                with _lock:
                    _os.lseek(fd, int(offset), 0)
                    got = _os.read(fd, n)
                mv[:len(got)] = got
                return len(got)

            qdp._os.preadv = _fake_preadv
            return _fake_preadv

        def _fake_preadv(fd, iovs, offset):
            mv = iovs[0]
            n = len(mv)
            got = _os.pread(fd, n, int(offset))
            mv[:len(got)] = got
            return len(got)

        qdp._os.preadv = _fake_preadv
        return _fake_preadv

    def test_structural_full_path_with_mocked_preadv(self):
        self._install_fake_preadv()
        with tempfile.TemporaryDirectory() as td:
            path = _make_synthetic_safetensors(Path(td) / "synth3.safetensors")
            result = qdp.run_unet_qd_probe_battery(str(path), mode="structural")
            self.assertIsInstance(result, dict)
            cfg = (result.get("sections") or {}).get("structural_qd1") or {}
            # The fake preadv path must complete a full config successfully.
            self.assertEqual(cfg.get("status"), "ok", cfg)
            self.assertGreater(cfg.get("bytes_returned", 0), 0)
            self.assertIsNotNone(cfg.get("aggregate_gbps"))
            # JSON round-trip of the full result must work (catches int/iter
            # bugs in worker records).
            import json as _json
            self.assertIsInstance(
                _json.loads(_json.dumps(result, default=str)), dict)

    def test_qd4_full_path_with_mocked_preadv(self):
        self._install_fake_preadv()
        with tempfile.TemporaryDirectory() as td:
            path = _make_synthetic_safetensors(Path(td) / "synth4.safetensors")
            from comfymodal_runtime.model_preload import _c6_parse_safetensors_header
            hdr = _c6_parse_safetensors_header(str(path))
            import struct as _stx
            with open(path, "rb") as f:
                head_len = _stx.unpack("<Q", f.read(8))[0]
            total = qdp.tensor_bytes_from_header(hdr)
            cfg = qdp.run_qd_config(str(path), hdr, 8 + head_len, total,
                                    qd=4, block_mib=8,
                                    window=(0, total), schedule="static",
                                    warm_repeat=True, verify=True)
            self.assertEqual(cfg.get("status"), "ok", cfg)
            self.assertEqual(cfg.get("bytes_returned"), total)
            self.assertIn("steady_state_gbps", cfg)
            self.assertIn("ctxt_switches_delta", cfg)
            import json as _json
            _json.dumps(cfg, default=str)  # must not raise


class ExternalModeTests(unittest.TestCase):
    """Loader-only battery on a synthetic file.  fastsafetensors runs for
    real (win wheel installed); RunAI is Linux-only and must degrade to a
    recorded error/skip without raising."""

    def _make_file(self, td):
        return _make_synthetic_safetensors(Path(td) / "ext.safetensors")

    def test_external_mode_battery_synthetic(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._make_file(td)
            result = qdp.run_unet_qd_probe_battery(str(path), mode="external")
            self.assertIsInstance(result, dict)
            sections = result.get("sections") or {}
            self.assertIn("external", sections)
            self.assertIn("summary", sections)
            summary = sections["summary"]
            self.assertEqual(summary["status"], "ok")
            self.assertIn("loader_smoke", sections)
            self.assertIn("loader_imports", sections)
            for e in sections["external"]:
                self.assertIn("loader", e)
                self.assertIn("status", e)

    def test_run_external_loader_fastsafetensors_local(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._make_file(td)
            from comfymodal_runtime.model_preload import _c6_parse_safetensors_header
            hdr = _c6_parse_safetensors_header(str(path))
            res = qdp.run_external_loader(
                str(path), hdr, "fastsafetensors", concurrency=4,
                device="cpu", block_mib=1)
            self.assertEqual(res.get("status"), "ok", res)
            self.assertEqual(res.get("tensor_count"), 3)
            self.assertTrue(res.get("key_set_ok"))
            self.assertTrue((res.get("spot_check") or {}).get("ok"))
            self.assertGreater(res.get("total_bytes", 0), 0)

    def test_structural_smoke_key_present(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._make_file(td)
            result = qdp.run_unet_qd_probe_battery(str(path), mode="structural")
            sections = result.get("sections") or {}
            smoke = sections.get("loader_smoke") or {}
            self.assertIn("loaders", smoke)
            # RunAI cannot import on Windows; must degrade gracefully.
            runai = (smoke.get("loaders") or {}).get("runai") or {}
            self.assertIn("status", runai)
            if runai.get("status") == "error":
                self.assertTrue(runai.get("error"))


class EnvHelperTests(unittest.TestCase):
    def test_env_set_restore(self):
        os.environ["QD_TEST_VAR"] = "old"
        prev = qdp._env_set({"QD_TEST_VAR": "new", "QD_TEST_VAR2": "x"})
        self.assertEqual(os.environ["QD_TEST_VAR"], "new")
        self.assertEqual(os.environ["QD_TEST_VAR2"], "x")
        qdp._env_restore(prev)
        self.assertEqual(os.environ["QD_TEST_VAR"], "old")
        self.assertNotIn("QD_TEST_VAR2", os.environ)
        os.environ.pop("QD_TEST_VAR", None)


if __name__ == "__main__":
    unittest.main()
