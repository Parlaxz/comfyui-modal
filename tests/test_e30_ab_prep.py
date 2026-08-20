"""E30 A/B prep validation: profiles, diff, metrics, artifact extraction, v2ctl preflight."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

_REPO = Path(__file__).resolve().parents[1]
_QD_READER_SRC = _REPO / "comfymodal_runtime" / "clip_qd_reader.py"
_SPEC_HYDR_SRC = _REPO / "comfymodal_runtime" / "speculative_clip_hydration.py"

EVT_CLIP_QD_SOURCE_SUBMIT_START = "clip_qd_source_submit_start"
EVT_CLIP_QD_FIRST_COMPLETION = "clip_qd_first_completion"
EVT_CLIP_QD_LAST_COMPLETION = "clip_qd_last_completion"
EVT_CLIP_QD_SUBMIT_END = "clip_qd_submit_end"
EVT_CLIP_QD_DEVICE_READY = "clip_qd_device_ready"
EVT_CLIP_QD_STATS = "clip_qd_stats"
EVT_CLIP_QD_SPEC_RECORD_PUBLISH = "clip_qd_spec_record_publish"
EVT_CLIP_QD_TAKE = "clip_qd_take"
EVT_CLIP_QD_BIND = "clip_qd_bind"
EVT_CLIP_QD_OWNER_RETAINED = "clip_qd_owner_retained"

E31_FLAGS = (
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE",
    "COMFYMODAL_V2_E31_FORENSICS",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE",
)

_SHA = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"


def _resolve_arm(arm_name: str):
    from tools.v2_control.profiles import Profiles
    from tools.v2_control.registry import FlagRegistry
    from tools.v2_control.config import ConfigResolver

    profiles = Profiles(_REPO / "config" / "v2" / "profiles")
    reg = FlagRegistry()
    resolver = ConfigResolver(_REPO, profiles, reg)
    return resolver.resolve(profile_name=arm_name)


def _flag_val(config, name: str) -> str | None:
    f = config.flag(name)
    return f.value if f is not None else None


def _make_synthetic_artifact(
    events=None,
    spans=None,
    output_sha=None,
    serial_ledger=None,
    fresh=None,
    restore_count=None,
    request_count=None,
    endpoint_status=None,
):
    ledger = {}
    if events is not None:
        ledger["events"] = events
    if spans is not None:
        ledger["spans"] = spans
    if serial_ledger is not None:
        ledger["serial_ledger"] = serial_ledger
    if endpoint_status is not None:
        ledger["endpoint_status"] = endpoint_status

    artifact = {
        "canonical_ledger": ledger if ledger else None,
        "canonical_ledger_status": "ok",
        "output_sha": output_sha
        or "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260",
    }
    if fresh is not None:
        artifact["fresh"] = fresh
    if restore_count is not None:
        artifact["restore_count"] = restore_count
    if request_count is not None:
        artifact["request_count"] = request_count
    return artifact


class TestE30ProfileResolution(unittest.TestCase):
    def test_arm_a_resolves(self):
        cfg = _resolve_arm("e30-clip-qd-arm-a")
        self.assertIsNotNone(cfg)
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_READER"), "0")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_QD"), "4")

    def test_arm_b_resolves(self):
        cfg = _resolve_arm("e30-clip-qd-arm-b")
        self.assertIsNotNone(cfg)
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_READER"), "1")

    def test_arm_a_qd_off(self):
        cfg = _resolve_arm("e30-clip-qd-arm-a")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_READER"), "0")

    def test_arm_b_qd_on_qd_4(self):
        cfg = _resolve_arm("e30-clip-qd-arm-b")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_READER"), "1")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_QD"), "4")

    def test_e31_off_arm_a(self):
        cfg = _resolve_arm("e30-clip-qd-arm-a")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"), "0")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_E31_FORENSICS"), "0")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_E31_FORWARD_PROFILE"), "0")

    def test_e31_off_arm_b(self):
        cfg = _resolve_arm("e30-clip-qd-arm-b")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"), "0")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_E31_FORENSICS"), "0")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_E31_FORWARD_PROFILE"), "0")

    def test_expected_sha_both_arms(self):
        for arm in ("e30-clip-qd-arm-a", "e30-clip-qd-arm-b"):
            cfg = _resolve_arm(arm)
            self.assertEqual(cfg.workload.expected_output_sha, _SHA, arm)

    def test_run_count_1_both_arms(self):
        for arm in ("e30-clip-qd-arm-a", "e30-clip-qd-arm-b"):
            cfg = _resolve_arm(arm)
            self.assertEqual(cfg.workload.run_count, 1, arm)

    def test_fresh_required_both_arms(self):
        for arm in ("e30-clip-qd-arm-a", "e30-clip-qd-arm-b"):
            cfg = _resolve_arm(arm)
            self.assertTrue(cfg.workload.fresh_required, arm)

    def test_single_use_both_arms(self):
        for arm in ("e30-clip-qd-arm-a", "e30-clip-qd-arm-b"):
            cfg = _resolve_arm(arm)
            self.assertEqual(
                _flag_val(cfg, "COMFYMODAL_V2_SINGLE_USE_CONTAINERS"), "1", arm
            )


class TestE30ProfileDiff(unittest.TestCase):
    def test_diff_clean(self):
        cfg_a = _resolve_arm("e30-clip-qd-arm-a")
        cfg_b = _resolve_arm("e30-clip-qd-arm-b")
        map_a = {f.name: f.value for f in cfg_a.flags}
        map_b = {f.name: f.value for f in cfg_b.flags}
        all_names = sorted(set(map_a) | set(map_b))
        differing = []
        for name in all_names:
            va = map_a.get(name)
            vb = map_b.get(name)
            if va != vb:
                differing.append(name)
        self.assertEqual(differing, ["COMFYMODAL_V2_CLIP_QD_READER"])

    def test_e31_identical(self):
        cfg_a = _resolve_arm("e30-clip-qd-arm-a")
        cfg_b = _resolve_arm("e30-clip-qd-arm-b")
        for flag_name in E31_FLAGS:
            self.assertEqual(
                _flag_val(cfg_a, flag_name), _flag_val(cfg_b, flag_name), flag_name
            )

    def test_target_identical(self):
        cfg_a = _resolve_arm("e30-clip-qd-arm-a")
        cfg_b = _resolve_arm("e30-clip-qd-arm-b")
        self.assertEqual(cfg_a.target.app, cfg_b.target.app)
        self.assertEqual(cfg_a.target.class_name, cfg_b.target.class_name)
        self.assertEqual(cfg_a.target.method, cfg_b.target.method)

    def test_resources_identical(self):
        cfg_a = _resolve_arm("e30-clip-qd-arm-a")
        cfg_b = _resolve_arm("e30-clip-qd-arm-b")
        self.assertEqual(cfg_a.resources.gpu, cfg_b.resources.gpu)
        self.assertEqual(cfg_a.resources.cpu, cfg_b.resources.cpu)
        self.assertEqual(cfg_a.resources.memory_mb, cfg_b.resources.memory_mb)

    def test_workload_identical(self):
        cfg_a = _resolve_arm("e30-clip-qd-arm-a")
        cfg_b = _resolve_arm("e30-clip-qd-arm-b")
        self.assertEqual(
            cfg_a.workload.fresh_required, cfg_b.workload.fresh_required
        )
        self.assertEqual(
            cfg_a.workload.expected_output_sha, cfg_b.workload.expected_output_sha
        )
        self.assertEqual(cfg_a.workload.run_count, cfg_b.workload.run_count)
        self.assertEqual(cfg_a.workload.gap_seconds, cfg_b.workload.gap_seconds)

    def test_e29_tracer_both_arms(self):
        for arm in ("e30-clip-qd-arm-a", "e30-clip-qd-arm-b"):
            cfg = _resolve_arm(arm)
            self.assertEqual(
                _flag_val(cfg, "COMFYMODAL_V2_CRITICAL_PATH_LEDGER"), "1", arm
            )


class TestE30QDPreservesBaseline(unittest.TestCase):
    def test_qd_off_defaults_to_fastsafe(self):
        cfg = _resolve_arm("e30-clip-qd-arm-a")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_READER"), "0")

    def test_qd_on_resolves_qd_4(self):
        cfg = _resolve_arm("e30-clip-qd-arm-b")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_READER"), "1")
        self.assertEqual(_flag_val(cfg, "COMFYMODAL_V2_CLIP_QD_QD"), "4")


class TestE30ArtifactExtraction(unittest.TestCase):
    def _extract(self, artifact: dict):
        from tools.e30_ab import _extract_metrics

        return _extract_metrics(artifact)

    def test_extract_from_synthetic_artifact(self):
        events = [
            {"name": EVT_CLIP_QD_SOURCE_SUBMIT_START, "mono_ns": 1_000_000},
            {"name": EVT_CLIP_QD_FIRST_COMPLETION, "mono_ns": 5_000_000},
            {"name": EVT_CLIP_QD_LAST_COMPLETION, "mono_ns": 8_000_000},
            {"name": EVT_CLIP_QD_SUBMIT_END, "mono_ns": 9_000_000},
            {"name": EVT_CLIP_QD_DEVICE_READY, "mono_ns": 12_000_000},
            {
                "name": EVT_CLIP_QD_STATS,
                "metadata": {
                    "total_source_wall_ms": 7.5,
                    "configured_qd": 4,
                    "observed_max_outstanding": 3,
                    "bytes_read": 67108864,
                    "file_bytes": 67108864,
                    "aggregate_gbps": 8.0,
                    "steady_state_gbps": 9.0,
                    "buffer_pool_wait_ms": 0.1,
                    "submit_count": 4,
                    "completion_count": 4,
                    "per_read_errors": 0,
                },
            },
            {"name": EVT_CLIP_QD_SPEC_RECORD_PUBLISH, "mono_ns": 13_000_000},
            {"name": EVT_CLIP_QD_TAKE, "mono_ns": 14_000_000},
            {"name": EVT_CLIP_QD_BIND, "mono_ns": 15_000_000},
            {"name": EVT_CLIP_QD_OWNER_RETAINED, "mono_ns": 16_000_000},
        ]
        spans = [
            {"name": "CLIP hydration", "duration_ms": 12.3},
            {"name": "CLIP forward", "duration_ms": 45.6},
        ]
        serial = {"total_ms": 250.0, "unattributed_ms": 50.0}
        artifact = _make_synthetic_artifact(
            events=events, spans=spans, serial_ledger=serial, fresh=True,
            endpoint_status="ok",
        )
        m = self._extract(artifact)
        self.assertEqual(m["CLIP_SOURCE_MS"], 7.5)
        self.assertAlmostEqual(m["CLIP_SOURCE_TO_GPU_READY_MS"], 11.0, places=3)
        self.assertEqual(m["CONFIGURED_QD"], 4)
        self.assertEqual(m["OBSERVED_MAX_OUTSTANDING"], 3)
        self.assertTrue(m["QD_USED"])
        self.assertFalse(m["QD_FALLBACK"])
        self.assertEqual(m["RESTORE_TOTAL_MS"], 250.0)
        self.assertEqual(m["REMOTE_PYTHON_TO_DURABLE_MS"], 250.0)
        self.assertEqual(m["OUTPUT_SHA"], _SHA)
        self.assertTrue(m["FRESH"])
        self.assertEqual(m["CLIP_HYDRATION_MS"], 12.3)
        self.assertEqual(m["CLIP_FORWARD_MS"], 45.6)
        self.assertEqual(m["TOTAL_UNATTRIBUTED_MS"], 50.0)
        self.assertEqual(m["E30_EVIDENCE_STATUS"], "OK")

    def test_extract_arm_a_no_qd_events(self):
        spans = [{"name": "CLIP hydration", "duration_ms": 20.0}]
        serial = {"total_ms": 300.0, "unattributed_ms": 100.0}
        artifact = _make_synthetic_artifact(
            events=[], spans=spans, serial_ledger=serial, fresh=True,
            endpoint_status="ok",
        )
        m = self._extract(artifact)
        self.assertEqual(m["CLIP_SOURCE_MS"], 20.0)
        self.assertIsNone(m["CONFIGURED_QD"])
        self.assertFalse(m["QD_USED"])

    def test_extract_missing_ledger_fails(self):
        artifact = {
            "canonical_ledger": None,
            "canonical_ledger_status": "missing",
            "output_sha": _SHA,
            "fresh": True,
        }
        m = self._extract(artifact)
        self.assertEqual(m["E30_EVIDENCE_STATUS"], "MISSING")

    def test_extract_output_sha_missing(self):
        serial = {"total_ms": 200.0, "unattributed_ms": 40.0}
        events = [{"name": EVT_CLIP_QD_STATS, "metadata": {"total_source_wall_ms": 5.0}}]
        artifact = _make_synthetic_artifact(
            events=events, serial_ledger=serial, fresh=True,
            endpoint_status="ok",
        )
        del artifact["output_sha"]
        m = self._extract(artifact)
        self.assertIsNone(m["OUTPUT_SHA"])
        self.assertEqual(m["E30_EVIDENCE_STATUS"], "MISSING")

    def test_extract_freshness_detection(self):
        serial = {"total_ms": 200.0, "unattributed_ms": 40.0}
        events = [{"name": EVT_CLIP_QD_STATS, "metadata": {"total_source_wall_ms": 5.0}}]
        artifact = _make_synthetic_artifact(
            events=events,
            serial_ledger=serial,
            restore_count=1,
            request_count=1,
            endpoint_status="ok",
        )
        m = self._extract(artifact)
        self.assertTrue(m["FRESH"])


class TestE30LedgerEventPresence(unittest.TestCase):
    def test_clip_qd_stats_event_exists(self):
        src = _QD_READER_SRC.read_text(encoding="utf-8")
        self.assertIn("clip_qd_stats", src)

    def test_bytes_read_in_stats(self):
        src = _QD_READER_SRC.read_text(encoding="utf-8")
        idx = src.find("def _finalize_stats")
        self.assertGreater(idx, 0)
        end = src.find("\ndef ", idx + 1)
        if end == -1:
            end = len(src)
        body = src[idx:end]
        self.assertIn("bytes_read", body)

    def test_buffer_wait_accumulation(self):
        src = _QD_READER_SRC.read_text(encoding="utf-8")
        self.assertIn("add_buffer_wait", src)
        self.assertIn("buffer_wait_ms_total", src)

    def test_observed_max_outstanding_in_stats(self):
        src = _QD_READER_SRC.read_text(encoding="utf-8")
        idx = src.find("def _finalize_stats")
        self.assertGreater(idx, 0)
        end = src.find("\ndef ", idx + 1)
        if end == -1:
            end = len(src)
        body = src[idx:end]
        self.assertIn("observed_max_outstanding", body)


class TestE30FallbackVisibility(unittest.TestCase):
    def test_clip_qd_fallback_event_in_seam(self):
        src = _SPEC_HYDR_SRC.read_text(encoding="utf-8")
        self.assertIn("clip_qd_fallback", src)


class TestE30FutureRemoteSequence(unittest.TestCase):
    def test_future_sequence_defined(self):
        cfg_a = _resolve_arm("e30-clip-qd-arm-a")
        cfg_b = _resolve_arm("e30-clip-qd-arm-b")
        self.assertEqual(_flag_val(cfg_a, "COMFYMODAL_V2_CLIP_QD_READER"), "0")
        self.assertEqual(_flag_val(cfg_b, "COMFYMODAL_V2_CLIP_QD_READER"), "1")
        map_a = {f.name: f.value for f in cfg_a.flags}
        map_b = {f.name: f.value for f in cfg_b.flags}
        critical_diffs = [
            n
            for n in sorted(set(map_a) | set(map_b))
            if map_a.get(n) != map_b.get(n) and n != "COMFYMODAL_V2_CLIP_QD_READER"
        ]
        self.assertEqual(critical_diffs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
