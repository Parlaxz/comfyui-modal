"""Focused tests for the direct GPU-snapshot workflow waterfall path.

``GpuSnapshotUnetShadow.run_gpu_snapshot_workflow`` bypasses
``ModalRuntimeEntrypoint.run_plan_stream`` (the normal trace/waterfall
assembly), so a small adapter (``_build_gpu_snapshot_waterfall``) synthesizes
the ``build_waterfall`` input from the retained request markers and the
snapshot-retained timing wrappers, using same-process remote wall timestamps
only (never the cross-host local submit clock).  These tests lock the adapter
contract and the best-effort result attachment.
"""

import unittest
from pathlib import Path
from unittest import mock

from comfymodal_runtime.gpu_snapshot_shadow import (
    _build_gpu_snapshot_waterfall,
    _marker_wall,
)
from comfymodal_runtime.v2_waterfall import (
    MEASURED,
    UNAVAILABLE,
    render_waterfall,
    waterfall_to_dict,
)

_REQUEST_ID = "gpu-snap-test-0001"


class _FakeShadow:
    """Minimal stand-in for the shadow instance the adapter reads."""

    def __init__(self, markers):
        self._gpu_snapshot_markers = list(markers)
        self.container_session_id = "session-fake"
        self._restore_count = 1
        self._phase = "restore"


def _markers():
    base = 1_000_000_000  # wall ns epoch anchor
    return [
        {"marker": "gpu_snapshot_post_restore_enter", "wall_unix_ns": base},
        {"marker": "gpu_snapshot_request_method_entry", "wall_unix_ns": base + 500_000_000},
        {"marker": "gpu_snapshot_generation_complete", "wall_unix_ns": base + 1_200_000_000},
    ]


def _timing_events():
    base = 1_000_000_000
    return [
        {
            "kind": "sampler",
            "start_wall_unix_ns": base + 600_000_000,
            "end_wall_unix_ns": base + 1_000_000_000,
        },
        {
            "kind": "vae_decode",
            "start_wall_unix_ns": base + 1_050_000_000,
            "end_wall_unix_ns": base + 1_100_000_000,
        },
    ]


class MarkerWallTests(unittest.TestCase):
    def test_returns_last_wall_for_name(self):
        markers = [
            {"marker": "x", "wall_unix_ns": 100},
            {"marker": "x", "wall_unix_ns": 300},
        ]
        self.assertEqual(_marker_wall(markers, "x"), 300)

    def test_missing_marker_returns_none(self):
        self.assertIsNone(_marker_wall([{"marker": "x", "wall_unix_ns": 1}], "y"))
        self.assertIsNone(_marker_wall([], "x"))

    def test_non_int_wall_returns_none(self):
        self.assertIsNone(_marker_wall([{"marker": "x", "wall_unix_ns": "junk"}], "x"))


class BuildGpuSnapshotWaterfallTests(unittest.TestCase):
    def _build(self):
        shadow = _FakeShadow(_markers())
        with mock.patch(
            "comfymodal_runtime.gpu_snapshot_shadow._SHADOW_TIMING_EVENTS",
            _timing_events(),
        ):
            return _build_gpu_snapshot_waterfall(
                shadow, _REQUEST_ID, {"generation_wall_ms": 1200.0},
                run_label="gpu-snapshot direct workflow",
            )

    def test_total_spans_post_restore_to_generation_same_process(self):
        report = self._build()
        # total = generation_complete - post_restore_enter (1200ms - 0ms)
        self.assertEqual(report.total_ms, 1200.0)
        self.assertEqual(report.request_id, _REQUEST_ID)

    def test_sampler_and_vae_stages_measured(self):
        report = self._build()
        by_key = {s.key: s for s in report.stages}
        self.assertEqual(by_key["sampling"].status, MEASURED)
        self.assertEqual(by_key["sampling"].duration_ms, 400.0)
        self.assertEqual(by_key["vae"].status, MEASURED)
        self.assertEqual(by_key["vae"].duration_ms, 50.0)
        self.assertEqual(by_key["post_sampling_transition"].duration_ms, 50.0)

    def test_restore_stage_measured_from_remote_markers(self):
        report = self._build()
        by_key = {s.key: s for s in report.stages}
        self.assertEqual(by_key["application_restore"].status, MEASURED)
        self.assertEqual(by_key["application_restore"].duration_ms, 500.0)

    def test_absent_stages_are_unavailable_not_zero(self):
        report = self._build()
        by_key = {s.key: s for s in report.stages}
        # No output boundary / no graph start: these must stay unavailable,
        # never fabricated as 0ms.
        for key in ("output_persistence", "remote_method_setup",
                    "prompt_executor_cache_setup", "sampler_node_to_sampling"):
            self.assertEqual(by_key[key].status, UNAVAILABLE, key)
            self.assertIsNone(by_key[key].duration_ms, key)

    def test_identity_and_request_carried(self):
        report = self._build()
        self.assertEqual(report.identity["class_name"], "_FakeShadow")
        self.assertEqual(report.identity["app_name"], "stable-modal-comfy-v2-gpu-snapshot-shadow")

    def test_waterfall_to_dict_round_trip_and_render(self):
        report = self._build()
        data = waterfall_to_dict(report)
        self.assertIn("waterfall", {"waterfall": data})
        self.assertEqual(data["total_ms"], 1200.0)
        self.assertIn("stages", data)
        rendered = render_waterfall(report)
        self.assertIn("V2 COLD WATERFALL", rendered)

    def test_total_falls_back_to_generation_wall_ms_without_restore_marker(self):
        markers = [
            {"marker": "gpu_snapshot_request_method_entry", "wall_unix_ns": 1_000_000_000},
            {"marker": "gpu_snapshot_generation_complete", "wall_unix_ns": 1_700_000_000},
        ]
        shadow = _FakeShadow(markers)
        with mock.patch(
            "comfymodal_runtime.gpu_snapshot_shadow._SHADOW_TIMING_EVENTS", []
        ):
            report = _build_gpu_snapshot_waterfall(
                shadow, _REQUEST_ID, {"generation_wall_ms": 700.0}, run_label="r",
            )
        self.assertEqual(report.total_ms, 700.0)


_SHADOW_SOURCE = (Path(__file__).resolve().parents[1]
                  / "comfymodal_runtime" / "gpu_snapshot_shadow.py").read_text(encoding="utf-8")


class DirectResultAttachmentContractTests(unittest.TestCase):
    def test_method_attaches_waterfall_and_has_error_path(self):
        # read the source file directly: the Modal cls wrapper hides the plain
        # function from inspect.getsource.
        source = _SHADOW_SOURCE
        self.assertIn("attach_waterfall(", source)
        self.assertIn('result["waterfall_error"] =', source)
        # The direct path serializes via the shared helper (prebuilt report).
        self.assertIn("attach_waterfall(\n                    result, report=_report,", source)
        # Only attached for restored workflow attempts (graph workflow path),
        # guarded so a waterfall failure never fails the workflow.
        self.assertIn("getattr(self, \"_phase\", \"unknown\") == \"restore\"", source)

    def test_adapter_and_marker_helpers_are_module_level(self):
        self.assertTrue(callable(_build_gpu_snapshot_waterfall))
        self.assertTrue(callable(_marker_wall))


if __name__ == "__main__":
    unittest.main()
