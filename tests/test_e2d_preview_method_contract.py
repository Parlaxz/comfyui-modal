"""E2D deterministic release-gate evidence: Preview encoder method contract.

Lightweight allowlist module for the Studio deterministic gate. Proves the
semantic E2D contract WITHOUT torch/comfyapp initialization (the full
production-seam suite ``tests/test_e2_preview_effort.py`` covers both encode
seams but costs ~24s of comfyapp/torch import per run and stays OUTSIDE the
gate as focused diagnostic evidence):

* the frozen Preview accepted-options contract (webp_lossy / q70 / fast)
  through ``ExecutionOptions`` including canonical round-trips;
* the effort→Pillow/libwebp method vocabulary with ``fast → method 0``;
* the fallback converter production seam selecting method 0 for the Preview
  default (PIL only);
* Experiment cell plans freezing the same fast effort.

Actual remote CPU/libwebp latency remains E7 live-only evidence.
"""
from __future__ import annotations

import copy
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import experiment_modern_plan as experiment_plan
from comfymodal_runtime.contracts import (
    WEBP_EFFORT_METHODS,
    ExecutionOptions,
    resolve_webp_pillow_method,
)
from output_converter import convert_image_bytes


def _png_bytes() -> bytes:
    from PIL import Image

    image = Image.new("RGB", (4, 4), (30, 144, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class EffortMethodMappingTests(unittest.TestCase):
    def test_effort_vocabulary_maps_fast_to_method_zero(self):
        self.assertEqual(WEBP_EFFORT_METHODS, {"fast": 0, "balanced": 4, "max": 6})
        self.assertEqual(resolve_webp_pillow_method("fast"), 0)
        self.assertEqual(resolve_webp_pillow_method("balanced"), 4)
        self.assertEqual(resolve_webp_pillow_method("max"), 6)

    def test_unknown_effort_falls_back_to_historical_method(self):
        self.assertEqual(resolve_webp_pillow_method(None), 4)
        self.assertEqual(resolve_webp_pillow_method("nonsense"), 4)


class PreviewFreezeContractTests(unittest.TestCase):
    def test_preview_alias_defaults_to_q70_and_fast_effort(self):
        options = ExecutionOptions.from_legacy({
            "preview_enabled": True,
            "preview_codec": "webp",
            "production": {"enabled": False},
        })
        self.assertEqual(options.output_mode, "preview")
        conversion = options.output_conversion_options
        self.assertEqual(conversion["format"], "webp_lossy")
        self.assertEqual(conversion["quality"], 70)
        self.assertEqual(conversion["webp_lossless_compression"], "fast")

    def test_preview_freeze_survives_canonical_round_trip(self):
        options = ExecutionOptions.from_legacy({"preview_enabled": True})
        restored = ExecutionOptions.from_legacy(options.to_dict())
        self.assertEqual(restored.output_conversion_options, options.output_conversion_options)
        self.assertEqual(restored.to_dict(), options.to_dict())

    def test_preview_legacy_projection_carries_fast_effort(self):
        legacy = ExecutionOptions.from_legacy({"preview_enabled": True}).to_legacy_dict()
        self.assertEqual(legacy["output_format"], "webp_lossy")
        self.assertEqual(legacy["quality"], 70)
        self.assertEqual(legacy["webp_lossless_compression"], "fast")

    def test_original_webp_does_not_inherit_preview_effort(self):
        options = ExecutionOptions.from_legacy({
            "output_mode": "original",
            "output_format": "webp",
            "quality": 91,
        })
        self.assertNotIn(
            "webp_lossless_compression", options.output_conversion_options
        )
        self.assertNotIn(
            "webp_lossless_compression", options.to_legacy_dict()
        )
        self.assertEqual(options.output_conversion_options["quality"], 91)


class FallbackConverterMethodTests(unittest.TestCase):
    def test_preview_default_converts_with_fast_method_zero(self):
        converted = convert_image_bytes(
            _png_bytes(), output_format="webp_lossy", quality=70,
            webp_lossless_compression="fast",
        )
        self.assertIsNone(converted["error"])
        self.assertEqual(converted["webp_effort"], "fast")
        self.assertEqual(converted["webp_method"], 0)
        self.assertIsNone(converted["webp_lossless_compression"])

        from PIL import Image

        with Image.open(io.BytesIO(converted["bytes"])) as image:
            image.load()
            self.assertEqual(image.format, "WEBP")

    def test_original_converter_is_noop_without_effort(self):
        source = _png_bytes()
        converted = convert_image_bytes(source, output_format="original")
        self.assertEqual(converted["bytes"], source)
        self.assertIsNone(converted["webp_effort"])
        self.assertIsNone(converted["webp_method"])


class ExperimentPlanRoundTripTests(unittest.TestCase):
    def test_experiment_cells_freeze_fast_effort(self):
        resolution = experiment_plan.WorkflowResolution(
            status="ok",
            workflow_id="wf_1",
            workflow_version_id="ver_1",
            preset_id="preset_1",
            workflow_name="Workflow",
            preset_name="Preset",
            bundle={
                "preset": {},
                "mapping": {"output_node_id": "1"},
            },
            control_schema={"seed": {}},
            executable_prompt={},
        )
        calls = []

        def fake_build(bundle, values, *, modal_options=None):
            calls.append(copy.deepcopy(modal_options))
            options = ExecutionOptions.from_legacy(modal_options)
            from comfymodal_runtime.contracts import ExecutionPlan

            return ExecutionPlan(
                workflow={"1": {"class_type": "SaveImage", "inputs": {}}},
                output_node_ids=("1",),
                execution_options=options,
                request_metadata={"output_mode": options.output_mode},
            ), None

        accepted = {
            "production": {"enabled": False},
            "preview_enabled": True,
            "preview_codec": "webp",
            "preview_quality": 70,
        }
        definition = {
            "experiment_id": "exp_1",
            "workflows": ["wf_1"],
            "axes": {"seed": [1, 2]},
            "modal_options": accepted,
        }
        with mock.patch.object(
            experiment_plan, "resolve_workflow_axis_value", return_value=resolution
        ), mock.patch.object(
            experiment_plan._seam,
            "build_workflow_execution_plan",
            side_effect=fake_build,
        ):
            plan = experiment_plan.build_cell_plan(definition, str(ROOT))

        for cell in plan.cells:
            self.assertEqual(cell.output_mode, "preview")
            cell_plan_dict = dict(cell.execution_plan_dict or {})
            conversion = cell_plan_dict["execution_options"]["output_conversion_options"]
            self.assertEqual(conversion["format"], "webp_lossy")
            self.assertEqual(conversion["quality"], 70)
            self.assertEqual(conversion["webp_lossless_compression"], "fast")
        for call in calls:
            self.assertEqual(call["webp_lossless_compression"], "fast")


if __name__ == "__main__":
    unittest.main()
