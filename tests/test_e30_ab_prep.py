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
        "metric_schema_version": 2,
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
            {"name": "modal_restore_entry", "mono_ns": 1_000_000},
            {"name": "modal_restore_exit", "mono_ns": 251_000_000},
            {"name": "clip_loader_setup_start", "mono_ns": 500_000},
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
            {"name": "unet:lane-pipeline", "duration_ms": 8.0},
        ]
        serial = {"total_ms": 250.0, "unattributed_ms": 50.0}
        artifact = _make_synthetic_artifact(
            events=events, spans=spans, serial_ledger=serial, fresh=True,
            endpoint_status="ok",
        )
        m = self._extract(artifact)
        self.assertEqual(m["CLIP_SOURCE_MS"], 12.3)
        self.assertEqual(m["LEGACY_TOTAL_SOURCE_WALL_MS"], 7.5)
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


class TestE30CanonicalMetricSemantics(unittest.TestCase):
    def _extract(self, artifact: dict):
        from tools.e30_ab import _extract_metrics

        return _extract_metrics(artifact)

    def test_restore_interval_is_not_serial_total(self):
        artifact = _make_synthetic_artifact(
            events=[
                {"name": "modal_restore_entry", "mono_ns": 1_000_000},
                {"name": "modal_restore_exit", "mono_ns": 11_000_000},
            ],
            spans=[{"name": "modal_restore", "duration_ms": 20.5}],
            serial_ledger={"total_ms": 900.0},
            fresh=True,
            endpoint_status="ok",
        )
        metrics = self._extract(artifact)
        self.assertEqual(metrics["RESTORE_TOTAL_MS"], 10.0)
        self.assertEqual(metrics["REMOTE_PYTHON_TO_DURABLE_MS"], 900.0)
        self.assertFalse(metrics["RESTORE_INTERVAL_MISMATCH"])
        self.assertIsNone(metrics["RESTORE_SPAN_MS"])

    def test_unet_metric_requires_dedicated_pipeline_span(self):
        artifact = _make_synthetic_artifact(
            spans=[
                {"name": "model-mgmt:load_models_gpu", "duration_ms": 999.0},
                {"name": "unet:lane-pipeline", "duration_ms": 12.0},
            ],
            serial_ledger={"total_ms": 20.0},
            fresh=True,
            endpoint_status="ok",
        )
        metrics = self._extract(artifact)
        self.assertEqual(metrics["UNET_PIPELINE_MS"], 12.0)

    def test_legacy_source_wall_is_marked_non_comparable(self):
        artifact = _make_synthetic_artifact(
            events=[{"name": EVT_CLIP_QD_STATS, "metadata": {"total_source_wall_ms": 7.0}}],
            serial_ledger={"total_ms": 20.0},
            fresh=True,
            endpoint_status="ok",
        )
        metrics = self._extract(artifact)
        self.assertEqual(metrics["CLIP_SOURCE_MS_STATUS"], "legacy_non_comparable")
        self.assertIsNone(metrics["CLIP_LOADER_TO_DEVICE_READY_MS"])

    def test_repaired_qd_secondary_aliases_are_extracted(self):
        from tools.e30_ab import _extract_metrics

        artifact = _make_synthetic_artifact(
            events=[], spans=[], serial_ledger={"total_ms": 20.0},
            fresh=True, endpoint_status="ok",
        )
        artifact["qd_stats"] = {
            "QD_SOURCE_IO_WALL_MS": 12.5,
            "QD_SOURCE_GBPS": 8.25,
            "QD_MAX_SOURCE_IO_INFLIGHT": 4,
            "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS": 3.5,
            "QD_SOURCE_TO_GPU_READY_MS": 16.0,
            "QD_SOURCE_BYTES": 100,
            "QD_GPU_BYTES_COMPLETED": 96,
            "QD_ERROR_COUNT": 0,
        }
        metrics = _extract_metrics(artifact)
        self.assertEqual(metrics["QD_SOURCE_IO_WALL_MS"], 12.5)
        self.assertEqual(metrics["QD_SOURCE_GBPS"], 8.25)
        self.assertEqual(metrics["QD_MAX_SOURCE_IO_INFLIGHT"], 4)
        self.assertEqual(metrics["QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS"], 3.5)
        self.assertEqual(metrics["QD_SOURCE_TO_GPU_READY_MS"], 16.0)
        self.assertEqual(metrics["QD_SOURCE_BYTES"], 100.0)
        self.assertEqual(metrics["QD_GPU_BYTES_COMPLETED"], 96.0)
        self.assertEqual(metrics["QD_ERROR_COUNT"], 0.0)
        self.assertIsNone(metrics["CLIP_LOADER_TO_DEVICE_READY_MS"])

    def test_lowercase_qd_metric_alias_is_not_canonical(self):
        artifact = _make_synthetic_artifact(
            events=[{"name": EVT_CLIP_QD_STATS, "metadata": {"qd_source_io_wall_ms": 99.0}}],
            serial_ledger={"total_ms": 20.0}, fresh=True, endpoint_status="ok",
        )
        self.assertIsNone(self._extract(artifact)["QD_SOURCE_IO_WALL_MS"])

    def test_legacy_only_source_wall_has_no_canonical_evidence(self):
        artifact = _make_synthetic_artifact(
            events=[{"name": EVT_CLIP_QD_STATS, "metadata": {"total_source_wall_ms": 7.0}}],
            spans=[{"name": "modal_restore", "duration_ms": 900.0},
                   {"name": "model-mgmt:load_models_gpu", "duration_ms": 999.0}],
            serial_ledger={"total_ms": 20.0}, fresh=True, endpoint_status="ok",
        )
        metrics = self._extract(artifact)
        self.assertEqual(metrics["METRIC_SCHEMA_VERSION"], 2)
        self.assertEqual(metrics["E30_EVIDENCE_STATUS"], "MISSING")


class TestE30EvidenceGate(unittest.TestCase):
    def _pair(self, root: Path):
        from tools.e30_ab import _artifact_sha256, _expected_control_plane_fingerprints, _expected_fingerprints

        expected = _expected_fingerprints()

        def make(arm: str, request_id: str, invocation_id: str) -> Path:
            enabled = arm == "B"
            events = [
                {"name": "modal_restore_entry", "mono_ns": 1_000_000},
                {"name": "modal_restore_exit", "mono_ns": 11_000_000},
                {"name": "clip_loader_setup_start", "mono_ns": 12_000_000},
                {"name": "clip_qd_device_ready" if enabled else "clip_device_ready", "mono_ns": 20_000_000 if enabled else 22_000_000},
            ]
            if enabled:
                events.extend([
                    {"name": "clip_qd_stats", "metadata": {
                        "configured_qd": 4,
                        "QD_MAX_SOURCE_IO_INFLIGHT": 4,
                        "QD_SOURCE_BYTES": 100,
                        "QD_GPU_BYTES_COMPLETED": 100,
                        "QD_ERROR_COUNT": 0,
                        "bytes_read": 100,
                        "file_bytes": 100,
                        "per_read_errors": 0,
                        "status": "ok",
                        "fallback": {"pin_fallback": 0},
                    }},
                    {"name": "clip_qd_spec_record_publish", "mono_ns": 23_000_000},
                ])
            path = root / f"{arm.lower()}.json"
            artifact = {
                "metric_schema_version": 2,
                "profile": f"e30-clip-qd-arm-{arm.lower()}",
                "profile_config_fingerprint": next(iter(expected[arm])),
                "v2ctl_invocation_id": invocation_id,
                "request_id": request_id,
                "artifact_path": str(path.resolve()),
                "effective_env": {
                    "COMFYMODAL_V2_CLIP_QD_READER": "1" if enabled else "0",
                    "COMFYMODAL_V2_E31_FORENSICS": "0",
                    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
                    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
                },
                "fresh": True,
                "output_sha": _SHA,
                "canonical_ledger_status": "ok",
                "canonical_ledger": {
                    "endpoint_status": "ok",
                    "events": events,
                    "spans": [{"name": "unet:lane-pipeline", "duration_ms": 8.0}],
                    "serial_ledger": {"total_ms": 100.0 if enabled else 110.0, "zero_gap": True},
                },
            }
            path.write_text(json.dumps(artifact), encoding="utf-8")
            control = _expected_control_plane_fingerprints()[arm]
            (root / f"{arm.lower()}.json.v2ctl-provenance.json").write_text(
                json.dumps({"profile": artifact["profile"], "request_id": request_id,
                            "v2ctl_invocation_id": invocation_id,
                            "profile_config_fingerprint": artifact["profile_config_fingerprint"],
                            "deploy_fingerprint": next(iter(control["deploy_fingerprint"])),
                            "run_fingerprint": next(iter(control["run_fingerprint"])),
                            "artifact_path": str(path.resolve()),
                            "artifact_sha256": _artifact_sha256(path)}), encoding="utf-8"
            )
            return path

        return make("A", "req-a", "invoke-a"), make("B", "req-b", "invoke-b")

    def test_valid_pair_reaches_arm_b_win(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "ARM_B_WIN")
            self.assertTrue(result["EXPERIMENT_VALID"])
            self.assertTrue(result["CORRECTNESS_PASS"])

    def test_wrong_provenance_fingerprint_fails_closed(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            provenance_path = Path(str(b) + ".v2ctl-provenance.json")
            provenance = json.loads(provenance_path.read_text())
            provenance["run_fingerprint"] = "wrong-run-fingerprint"
            provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertTrue(any("run_fingerprint" in reason for reason in result["validity"]["reasons"]))

    def test_old_or_ambiguous_metric_schema_fails_closed(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(a.read_text())
            data["metric_schema_version"] = 1
            a.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertIn("A:metric_schema_missing_or_old", result["validity"]["reasons"])

            a, b = self._pair(Path(td))
            data = json.loads(a.read_text())
            data["schema_version"] = 1
            a.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertIn("A:metric_schema_missing_or_old", result["validity"]["reasons"])

    def test_zero_gap_is_required_separately_from_endpoint_status(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(b.read_text())
            data["canonical_ledger"]["serial_ledger"]["zero_gap"] = False
            b.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertIn("B:serial_zero_gap_not_true", result["validity"]["reasons"])

    def test_missing_evidence_status_and_primary_metric_are_invalid(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(a.read_text())
            data["canonical_ledger"]["events"] = [
                event for event in data["canonical_ledger"]["events"]
                if event.get("name") != "clip_loader_setup_start"
            ]
            a.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertTrue(any("e30_evidence_status_not_ok" in reason or "missing_clip_loader" in reason for reason in result["validity"]["reasons"]))

    def test_single_use_setting_does_not_infer_freshness(self):
        from tools.e30_ab import _extract_metrics

        artifact = _make_synthetic_artifact(
            events=[], spans=[], serial_ledger={"total_ms": 1.0},
            fresh=None, endpoint_status="ok",
        )
        artifact["effective_env"] = {"COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1"}
        artifact["snapshot_identity"] = "snapshot-1"
        self.assertEqual(_extract_metrics(artifact)["FRESH"], "unknown")

    def test_missing_effective_qd_config_is_invalid(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(b.read_text())
            del data["effective_env"]["COMFYMODAL_V2_CLIP_QD_READER"]
            b.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertIn("B:missing_effective_qd_reader", result["validity"]["reasons"])

    def test_duplicate_actual_artifact_sha_is_invalid(self):
        from tools.e30_ab import _extract_metrics, validate_e30_pair

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            ma = _extract_metrics(json.loads(a.read_text()), a)
            mb = _extract_metrics(json.loads(b.read_text()), b)
            mb["IDENTITY"]["actual_artifact_sha256"] = ma["IDENTITY"]["actual_artifact_sha256"]
            result = validate_e30_pair(ma, mb)
            self.assertIn("duplicate_artifact_sha256", result["validity"]["reasons"])

    def test_multiple_qd_stats_are_aggregated(self):
        from tools.e30_ab import _extract_metrics

        artifact = _make_synthetic_artifact(
            events=[
                {"name": EVT_CLIP_QD_STATS, "metadata": {"configured_qd": 4, "qd_max_source_io_inflight": 4, "bytes_read": 10, "file_bytes": 10, "per_read_errors": 0}},
                {"name": EVT_CLIP_QD_STATS, "metadata": {"configured_qd": 4, "qd_max_source_io_inflight": 4, "bytes_read": 20, "file_bytes": 20, "per_read_errors": 0}},
            ],
            serial_ledger={"total_ms": 1.0}, endpoint_status="ok", fresh=True,
        )
        metrics = _extract_metrics(artifact)
        self.assertEqual(metrics["QD_STATS_EVENT_COUNT"], 2)
        self.assertEqual(metrics["QD_BYTES_READ"], 30.0)
        self.assertFalse(metrics["QD_STATS_INCONSISTENT"])

    def test_duplicate_ids_and_paths_are_invalid(self):
        from tools.e30_ab import _extract_metrics, validate_e30_pair

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            ma = _extract_metrics(json.loads(a.read_text()), a)
            mb = _extract_metrics(json.loads(b.read_text()), b)
            mb["IDENTITY"]["request_id"] = ma["IDENTITY"]["request_id"]
            mb["IDENTITY"]["artifact_path"] = ma["IDENTITY"]["artifact_path"]
            mb["IDENTITY"]["v2ctl_invocation_id"] = ma["IDENTITY"]["v2ctl_invocation_id"]
            result = validate_e30_pair(ma, mb)
            self.assertFalse(result["validity"]["valid"])
            self.assertIn("duplicate_request_id", result["validity"]["reasons"])
            self.assertIn("duplicate_artifact_path", result["validity"]["reasons"])
            self.assertIn("duplicate_v2ctl_invocation_id", result["validity"]["reasons"])

    def test_missing_invocation_is_invalid_evidence(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(b.read_text())
            del data["v2ctl_invocation_id"]
            b.write_text(json.dumps(data), encoding="utf-8")
            provenance_path = Path(str(b) + ".v2ctl-provenance.json")
            provenance = json.loads(provenance_path.read_text())
            del provenance["v2ctl_invocation_id"]
            provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertIsNone(result["PERFORMANCE_RESULT"])

    def test_bad_output_sha_blocks_performance_as_correctness_failure(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(b.read_text())
            data["output_sha"] = "bad"
            b.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertIsNone(result["PERFORMANCE_RESULT"])
            self.assertFalse(result["CORRECTNESS_PASS"])

    def test_qd_fallback_and_byte_mismatch_fail_closed(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(b.read_text())
            stats = next(e for e in data["canonical_ledger"]["events"] if e.get("name") == EVT_CLIP_QD_STATS)
            stats["metadata"]["fallback"] = {"pin_fallback": 1}
            stats["metadata"]["file_bytes"] = 101
            b.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertTrue(any("qd_fallback" in r or "byte_reconciliation" in r for r in result["validity"]["reasons"]))

    def test_missing_source_io_inflight_fails_closed(self):
        from tools.e30_ab import _comparison_data

        with tempfile.TemporaryDirectory() as td:
            a, b = self._pair(Path(td))
            data = json.loads(b.read_text())
            stats = next(e for e in data["canonical_ledger"]["events"] if e.get("name") == EVT_CLIP_QD_STATS)
            del stats["metadata"]["QD_MAX_SOURCE_IO_INFLIGHT"]
            b.write_text(json.dumps(data), encoding="utf-8")
            result = _comparison_data(str(a), str(b))["verdict"]
            self.assertEqual(result["verdict"], "INVALID_EVIDENCE")
            self.assertIn("B:missing_source_io_max_inflight", result["validity"]["reasons"])

    def test_qd_ready_without_common_caller_start_is_not_primary(self):
        from tools.e30_ab import _extract_metrics

        artifact = _make_synthetic_artifact(
            events=[{"name": "clip_qd_device_ready", "mono_ns": 10_000_000}],
            spans=[{"name": "CLIP hydration", "duration_ms": 4.0}],
            serial_ledger={"total_ms": 20.0},
            fresh=True,
            endpoint_status="ok",
        )
        metrics = _extract_metrics(artifact)
        self.assertIsNone(metrics["CLIP_LOADER_TO_DEVICE_READY_MS"])
        self.assertEqual(metrics["CLIP_SOURCE_MS_STATUS"], "secondary")

    def test_manifest_copies_raw_artifacts_and_provenance(self):
        from tools.e30_ab import build_evidence_manifest

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = self._pair(root)
            out = root / "manifest"
            manifest = build_evidence_manifest(a, b, out)
            self.assertTrue((out / "e30_evidence_manifest.json").is_file())
            self.assertEqual((out / f"arm_A_{a.name}").read_bytes(), a.read_bytes())
            self.assertEqual((out / f"arm_B_{b.name}").read_bytes(), b.read_bytes())
            self.assertIsNotNone(manifest["selected_artifacts"][0]["provenance_sibling"])
            self.assertIn("comparison_result", manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
