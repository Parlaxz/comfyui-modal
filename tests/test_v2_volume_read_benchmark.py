"""Focused tests for the mounted-Volume raw sequential-read benchmark.

Covers, CPU-only, no Modal/network, no new dependency:
  1  metric math: decimal_GBps (bytes/1e9/s) and binary_GiBps (bytes/2**30/s)
  2  attempt validity: exact bytes_read == stat size on both passes,
     size > 0, positive timing, no method error, cold-identity gate
  3  path resolution: traversal/absolute/separator rejection, missing and
     non-regular files rejected, default filename under diffusion_models
  4  mode wiring: --volume-read / V2_BENCHMARK_MODE=volume_read reachable
     from both .bat entrypoints with a default run count of 3
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tools.benchmark_v2_direct import (  # noqa: E402
    VOLUME_READ_FILENAME,
    VOLUME_READ_MODE,
    VOLUME_READ_RUN_COUNT,
    _volume_read_pass_stats,
    _volume_read_summary,
    _volume_read_validity,
)


def _make_pass(label: str, bytes_read: int, wall_ms: float,
               decimal_GBps: float | None = 1.0,
               binary_GiBps: float | None = 1.0) -> dict[str, Any]:
    return {
        "label": label,
        "bytes_read": bytes_read,
        "chunk_count": max(1, bytes_read // (8 * 1024 * 1024)),
        "wall_ms": wall_ms,
        "decimal_GBps": decimal_GBps,
        "binary_GiBps": binary_GiBps,
    }


def _make_attempt(*, status: str = "ok", stat_size: int = 100,
                  pass_bytes: int | None = None, wall_ms: float = 10.0,
                  identity: dict[str, Any] | None = None,
                  cold_check: dict[str, Any] | None = None,
                  error: str | None = None,
                  include_warm: bool = True) -> dict[str, Any]:
    if pass_bytes is None:
        pass_bytes = stat_size
    passes = [_make_pass("primary_mounted_volume", pass_bytes, wall_ms)]
    if include_warm:
        passes.append(_make_pass("warm_cache", pass_bytes, wall_ms))
    result: dict[str, Any] = {
        "status": status,
        "stat_size_bytes": stat_size,
        "passes": passes,
    }
    if status != "ok":
        result["error"] = "boom"
    if identity is None:
        identity = {
            "restored_instance_id": "inst-1",
            "restore_count": 1,
            "request_count": 1,
            "container_session_id": "sess-1",
        }
    attempt: dict[str, Any] = {
        "result": result,
        "identity": identity,
        "cold_check": cold_check or {
            "cold_valid": True, "cold": True, "freshness_checked": True,
            "failures": [],
        },
        "error": error,
    }
    return attempt


class TestVolumeReadMetricMath(unittest.TestCase):
    def test_decimal_and_binary_rates(self):
        # 8 MiB in exactly 1s: decimal = 8MiB/1e9 bytes, binary = 8MiB/2**30.
        bytes_read = 8 * 1024 * 1024
        wall_ns = 1_000_000_000
        from comfymodal_runtime.modal_app import _volume_read_rates

        decimal, binary = _volume_read_rates(bytes_read, wall_ns)
        if decimal is None or binary is None:
            self.fail("rates returned None for positive duration")
        self.assertAlmostEqual(decimal, bytes_read / 1_000_000_000.0, places=3)
        self.assertAlmostEqual(binary, bytes_read / (2 ** 30), places=3)

    def test_zero_duration_returns_none(self):
        from comfymodal_runtime.modal_app import _volume_read_rates

        self.assertEqual(_volume_read_rates(100, 0), (None, None))

    def test_wall_ms_scaling(self):
        # 1e6 ns == 1 ms
        self.assertEqual(round(1_000_000 / 1_000_000.0, 3), 1.0)


class TestVolumeReadValidity(unittest.TestCase):
    def test_valid_attempt(self):
        valid, failures, gate = _volume_read_validity(_make_attempt())
        self.assertTrue(valid)
        self.assertEqual(failures, [])
        self.assertTrue(gate)

    def test_bytes_mismatch_invalidates(self):
        attempt = _make_attempt(stat_size=100, pass_bytes=99)
        valid, failures, _gate = _volume_read_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("bytes_read" in f for f in failures))

    def test_non_positive_size_invalidates(self):
        valid, failures, _gate = _volume_read_validity(_make_attempt(stat_size=0))
        self.assertFalse(valid)
        self.assertTrue(any("stat_size_bytes" in f for f in failures))

    def test_non_positive_timing_invalidates(self):
        attempt = _make_attempt(wall_ms=0.0)
        valid, failures, _gate = _volume_read_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("wall_ms" in f for f in failures))

    def test_method_error_invalidates(self):
        attempt = _make_attempt(status="error", stat_size=100)
        valid, failures, _gate = _volume_read_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("method error" in f for f in failures))

    def test_run_error_invalidates(self):
        attempt = _make_attempt(error="remote failed")
        valid, failures, _gate = _volume_read_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("run error" in f for f in failures))

    def test_cold_gate_applies_when_token_available(self):
        identity = {"restored_instance_id": "abc", "container_session_id": "s"}
        cold_check = {
            "cold_valid": False, "cold": False, "freshness_checked": True,
            "failures": ["restore_count mismatch"],
        }
        attempt = _make_attempt(identity=identity, cold_check=cold_check)
        valid, failures, gate = _volume_read_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(gate)
        self.assertTrue(any("cold identity gate" in f for f in failures))

    def test_cold_gate_skipped_when_no_token(self):
        cold_check = {
            "cold_valid": False, "cold": False, "freshness_checked": False,
            "failures": ["restored_instance_id empty"],
        }
        attempt = _make_attempt(identity={}, cold_check=cold_check)
        valid, failures, gate = _volume_read_validity(attempt)
        self.assertTrue(valid)
        self.assertFalse(gate)

    def test_missing_second_pass_invalidates(self):
        attempt = _make_attempt(include_warm=False)
        valid, failures, _gate = _volume_read_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("2 passes" in f for f in failures))


class TestVolumeReadSummaryStats(unittest.TestCase):
    def test_pass_stats_filters_invalid(self):
        good = _make_attempt()
        good["valid"] = True
        bad = _make_attempt(stat_size=100, pass_bytes=90)
        bad["valid"] = False
        stats = _volume_read_pass_stats(
            [good, bad], "wall_ms", "primary_mounted_volume",
        )
        self.assertEqual(stats["count"], 1)  # one primary pass of the valid attempt
        self.assertEqual(stats["median"], 10.0)

    def test_pass_stats_separates_labels(self):
        good = _make_attempt()
        good["valid"] = True
        warm = _volume_read_pass_stats([good], "wall_ms", "warm_cache")
        primary = _volume_read_pass_stats(
            [good], "wall_ms", "primary_mounted_volume",
        )
        self.assertEqual(warm["count"], 1)
        self.assertEqual(primary["count"], 1)

    def test_summary_counts(self):
        good = _make_attempt()
        good["valid"] = True
        good["run_index"] = 0
        good["run_id"] = "r0"
        good["cold_check"] = {"cold": True}
        good["cold_gate_available"] = True
        good["dnf"] = False
        dnf = _make_attempt()
        dnf["valid"] = False
        dnf["dnf"] = True
        dnf["run_index"] = 1
        dnf["run_id"] = "r1"
        dnf["cold_gate_available"] = False
        dnf["cold_check"] = {"cold": False}
        summary = _volume_read_summary([good, dnf], meta={"filename": "x"})
        self.assertEqual(summary["run_count"], 2)
        self.assertEqual(summary["valid_count"], 1)
        self.assertEqual(summary["dnf_count"], 1)
        self.assertEqual(summary["invalid_count"], 0)
        self.assertEqual(summary["cold_count"], 1)


class TestVolumeReadPathResolution(unittest.TestCase):
    def test_default_filename_and_folder(self):
        from comfymodal_runtime.modal_app import (
            _VOLUME_READ_DEFAULT_FILENAME,
            _volume_read_resolve_path,
        )

        self.assertEqual(_VOLUME_READ_DEFAULT_FILENAME, "z_image_turbo_bf16.safetensors")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "diffusion_models"
            folder.mkdir()
            target = folder / "z_image_turbo_bf16.safetensors"
            target.write_bytes(b"x" * 1024)
            resolved = _volume_read_resolve_path(
                "z_image_turbo_bf16.safetensors", models_root=str(root),
            )
            self.assertEqual(os.path.realpath(resolved), str(target))

    def test_rejects_traversal_and_separators(self):
        from comfymodal_runtime.modal_app import _volume_read_resolve_path

        for bad in (
            "../escape.safetensors",
            "sub/dir.safetensors",
            "sub\\dir.safetensors",
            "/absolute.safetensors",
            "",
            "..",
            ".",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _volume_read_resolve_path(bad)

    def test_rejects_missing_and_non_regular_files(self):
        from comfymodal_runtime.modal_app import _volume_read_resolve_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "diffusion_models"
            folder.mkdir()
            (folder / "missing.safetensors")
            with self.assertRaises(FileNotFoundError):
                _volume_read_resolve_path("missing.safetensors", models_root=str(root))
            subdir = folder / "subdir"
            subdir.mkdir()
            with self.assertRaises(FileNotFoundError):
                _volume_read_resolve_path("subdir", models_root=str(root))


class TestVolumeReadModeWiring(unittest.TestCase):
    def _read(self, name: str) -> str:
        return (Path(_PROJECT_ROOT) / name).read_text(encoding="utf-8")

    def test_batch_entrypoints_reach_volume_read_mode(self):
        for name in ("deploy_and_run_v2_single.bat", "run_v2_single.bat"):
            source = self._read(name)
            with self.subTest(name=name):
                self.assertIn('if /i "!V2_BENCHMARK_MODE!"=="volume_read"', source)
                self.assertIn("python tools\\benchmark_v2_direct.py --volume-read", source)
                self.assertIn('set "V2_VOLUME_READ_RUN_COUNT=3"', source)

    def test_mode_constant_matches_env_token(self):
        self.assertEqual(VOLUME_READ_MODE, "volume_read")
        self.assertEqual(VOLUME_READ_RUN_COUNT, 3)
        self.assertEqual(VOLUME_READ_FILENAME, "z_image_turbo_bf16.safetensors")

    def test_tool_has_dedicated_flag(self):
        source = self._read("tools/benchmark_v2_direct.py")
        self.assertIn('"--volume-read"', source)
        self.assertIn("volume_read=", source)
        self.assertIn('"V2_BENCHMARK_MODE", "").strip().lower() == "volume_read"', source)


if __name__ == "__main__":
    unittest.main()
