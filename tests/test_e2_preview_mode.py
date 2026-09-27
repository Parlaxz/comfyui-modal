from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import experiment_modern_plan as experiment_plan
import studio_workflow_run
from comfymodal_runtime.contracts import (
    ExecutionOptions,
    ExecutionPlan,
    build_logical_output_key,
)
from comfymodal_runtime.output_delivery import (
    Attempt,
    ConversionMeta,
    OutputItem,
    attempt_to_descriptor_result,
)


class PreviewModeContractTests(unittest.TestCase):
    def test_preview_settings_become_explicit_lossy_webp_quality_70(self):
        options = ExecutionOptions.from_legacy({
            "preview_enabled": True,
            "preview_codec": "webp",
            "preview_quality": 70,
            "production": {"enabled": False},
        })
        self.assertEqual(options.output_mode, "preview")
        self.assertEqual(options.output_conversion_options["format"], "webp_lossy")
        self.assertEqual(options.output_conversion_options["quality"], 70)
        legacy = options.to_legacy_dict()
        self.assertEqual(legacy["output_mode"], "preview")
        self.assertEqual(legacy["output_format"], "webp_lossy")
        self.assertEqual(legacy["quality"], 70)

    def test_original_webp_is_not_inferred_as_preview(self):
        options = ExecutionOptions.from_legacy({
            "output_mode": "original",
            "output_format": "webp",
            "quality": 91,
            "production": {"enabled": False},
        })
        self.assertEqual(options.output_mode, "original")
        self.assertEqual(options.output_conversion_options["format"], "webp_lossy")
        self.assertEqual(options.output_conversion_options["quality"], 91)

    def test_single_plan_freezes_preview_mode_and_settings(self):
        bundle = {
            "workflow": {"workflow_id": "wf_1", "name": "Workflow"},
            "version": {"workflow_version_id": "ver_1"},
            "preset": {"preset_id": "preset_1", "name": "Preset"},
            "mapping": {"output_node_id": "1"},
            "executable_prompt": {
                "1": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
                "2": {"class_type": "EmptyLatentImage", "inputs": {}},
            },
            "control_schema": {},
        }
        accepted = {
            "production": {"enabled": False},
            "preview_enabled": True,
            "preview_codec": "webp",
            "preview_quality": 70,
        }
        plan, error = studio_workflow_run.build_workflow_execution_plan(
            bundle, {}, modal_options=accepted
        )
        self.assertIsNone(error)
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.execution_options.output_mode, "preview")
        self.assertEqual(plan.execution_options.output_conversion_options["quality"], 70)
        self.assertEqual(plan.request_metadata["output_mode"], "preview")
        accepted["preview_quality"] = 99
        self.assertEqual(plan.execution_options.output_conversion_options["quality"], 70)
        self.assertEqual(plan.to_dict()["execution_options"]["output_mode"], "preview")

    def test_experiment_cells_share_frozen_preview_mode(self):
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

        self.assertEqual(plan.modal_options["output_mode"], "preview")
        self.assertEqual(
            len(calls), 2,
            [cell.error for cell in plan.cells],
        )
        self.assertTrue(all(call["output_mode"] == "preview" for call in calls))
        self.assertTrue(all(cell.output_mode == "preview" for cell in plan.cells))
        for cell in plan.cells:
            self.assertIsNotNone(cell.execution_plan_dict)
            cell_plan_dict = dict(cell.execution_plan_dict or {})
            self.assertEqual(
                cell_plan_dict["execution_options"]["output_mode"], "preview"
            )
        accepted["preview_quality"] = 12
        first_plan_dict = dict(plan.cells[0].execution_plan_dict or {})
        self.assertEqual(
            first_plan_dict["execution_options"]["output_conversion_options"]["quality"],
            70,
        )

    def test_descriptor_variant_and_logical_key_are_mode_independent(self):
        item = OutputItem(
            node_id="6",
            output_key="images",
            filename="preview.webp",
            raw_bytes=b"encoded",
            file_ext=".webp",
            mime_type="image/webp",
            output_index=2,
            format="webp_lossy",
            conversion_meta=ConversionMeta(
                format="webp_lossy",
                mime_type="image/webp",
                file_ext=".webp",
                raw_bytes=7,
                hash_of_raw="hash",
                codec="webp",
                quality=70,
                output_codec_ms=1.5,
                encoded_bytes=7,
                source_bytes=24,
            ),
        )
        attempt = Attempt(strategy="direct_output_sink", success=True, items=(item,))
        result = attempt_to_descriptor_result(
            attempt, output_mode="preview", variant="preview"
        )
        descriptor = result["asset_descriptors"][0]
        self.assertEqual(result["output_mode"], "preview")
        self.assertEqual(descriptor["variant"], "preview")
        self.assertEqual(descriptor["logical_output_key"], "node:6:slot:images:item:2")
        self.assertEqual(
            descriptor["logical_output_key"],
            build_logical_output_key("6", "images", 2),
        )
        original_result = attempt_to_descriptor_result(
            attempt, output_mode="original", variant="original"
        )
        self.assertEqual(original_result["asset_descriptors"][0]["variant"], "original")
        self.assertEqual(
            original_result["asset_descriptors"][0]["logical_output_key"],
            descriptor["logical_output_key"],
        )

    def test_logical_key_changes_only_for_node_slot_or_item(self):
        base = build_logical_output_key("6", "images", 0)
        self.assertIsNotNone(base)
        base = str(base)
        self.assertEqual(base, "node:6:slot:images:item:0")
        self.assertNotEqual(base, build_logical_output_key("6", "images", 1))
        self.assertNotEqual(base, build_logical_output_key("7", "images", 0))
        self.assertNotIn("run_", base)
        self.assertNotIn("preview", base)
        self.assertNotIn("webp", base)


if __name__ == "__main__":
    unittest.main()
