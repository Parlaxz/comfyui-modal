"""E2D: fast lossy Preview encoder effort.

Covers the effort→method policy at both production WebP save seams
(direct tensor sink and byte converter), the frozen Preview contract
(webp_lossy / q70 / fast), round-trips through ExecutionOptions and the
Experiment cell plan, and preservation of Original and lossless semantics.
"""

from __future__ import annotations

import copy
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import experiment_modern_plan as experiment_plan
from comfymodal_runtime.contracts import (
    WEBP_EFFORT_METHODS,
    ExecutionOptions,
    resolve_webp_pillow_method,
)
from comfymodal_runtime.output_delivery import (
    DirectOutputSink,
    attempt_to_descriptor_result,
)
from output_converter import convert_image_bytes


def _png_bytes() -> bytes:
    from PIL import Image

    image = Image.new("RGB", (4, 4), (30, 144, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _tensor():
    torch = pytest.importorskip("torch")
    return torch.tensor(
        [[
            [[255, 0, 0], [0, 255, 0]],
            [[0, 0, 255], [255, 255, 0]],
        ]],
        dtype=torch.uint8,
    )


@pytest.mark.parametrize(
    ("effort", "expected_method"),
    [("fast", 0), ("balanced", 4), ("max", 6)],
)
def test_direct_sink_uses_selected_lossy_method(effort, expected_method):
    comfyapp = pytest.importorskip("comfyapp")
    entries, ext, mime, _, _ = comfyapp.encode_image_tensor_batch(
        _tensor(), "webp", None, effort
    )
    info = comfyapp.get_last_output_encode_info()
    assert ext == ".webp"
    assert mime == "image/webp"
    assert info["format"] == "webp_lossy"
    assert info["quality"] == 70
    assert info["webp_effort"] == effort
    assert info["webp_method"] == expected_method
    assert info["items"][0]["webp_method"] == expected_method

    from PIL import Image

    with Image.open(io.BytesIO(entries[0][0])) as image:
        image.load()
        assert image.format == "WEBP"


@pytest.mark.parametrize(
    ("effort", "expected_method"),
    [("fast", 0), ("balanced", 4), ("max", 6)],
)
def test_fallback_converter_uses_same_lossy_method(effort, expected_method):
    converted = convert_image_bytes(
        _png_bytes(), output_format="webp_lossy", quality=70,
        webp_lossless_compression=effort,
    )
    assert converted["error"] is None
    assert converted["webp_effort"] == effort
    assert converted["webp_method"] == expected_method
    assert converted["webp_lossless_compression"] is None

    from PIL import Image

    with Image.open(io.BytesIO(converted["bytes"])) as image:
        image.load()
        assert image.format == "WEBP"


@pytest.mark.parametrize(
    ("effort", "expected_method"),
    [("fast", 0), ("balanced", 4), ("max", 6)],
)
def test_lossless_semantics_unchanged(effort, expected_method):
    converted = convert_image_bytes(
        _png_bytes(), output_format="webp_lossless",
        webp_lossless_compression=effort,
    )
    assert converted["error"] is None
    assert converted["quality"] is None
    assert converted["webp_lossless_compression"] == effort
    assert converted["webp_method"] == expected_method

    from PIL import Image

    with Image.open(io.BytesIO(converted["bytes"])) as image:
        image.load()
        assert image.format == "WEBP"


import pytest  # noqa: E402  (kept explicit after sys.path setup)


class EffortMethodMappingTests(unittest.TestCase):
    def test_effort_vocabulary_maps_to_pillow_methods(self):
        self.assertEqual(WEBP_EFFORT_METHODS, {"fast": 0, "balanced": 4, "max": 6})
        self.assertEqual(resolve_webp_pillow_method("fast"), 0)
        self.assertEqual(resolve_webp_pillow_method("balanced"), 4)
        self.assertEqual(resolve_webp_pillow_method("max"), 6)

    def test_unknown_effort_falls_back_to_historical_method(self):
        self.assertEqual(resolve_webp_pillow_method(None), 4)
        self.assertEqual(resolve_webp_pillow_method("nonsense"), 4)


class PreviewDefaultContractTests(unittest.TestCase):
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

    def test_explicit_preview_effort_is_respected(self):
        options = ExecutionOptions.from_legacy({
            "preview_enabled": True,
            "output_conversion_options": {"webp_lossless_compression": "max"},
        })
        self.assertEqual(
            options.output_conversion_options["webp_lossless_compression"], "max"
        )

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

    def test_replayed_original_switches_format_without_preview_encoding(self):
        # E3 replay builds fresh Original-mode options; nothing injects the
        # Preview codec defaults once the mode is original.
        options = ExecutionOptions.from_legacy({"output_mode": "original"})
        self.assertEqual(options.output_mode, "original")
        self.assertNotIn("format", options.output_conversion_options)
        self.assertNotIn(
            "webp_lossless_compression", options.output_conversion_options
        )
        legacy = options.to_legacy_dict()
        self.assertEqual(legacy.get("output_format", "original"), "original")
        self.assertNotIn("webp_lossless_compression", legacy)


class DirectSinkEffortTests(unittest.TestCase):
    def _encode(self, effort):
        comfyapp = pytest.importorskip("comfyapp")
        entries, ext, mime, width, height = comfyapp.encode_image_tensor_batch(
            _tensor(), "webp", None, effort
        )
        info = comfyapp.get_last_output_encode_info()
        return comfyapp, entries, ext, mime, width, height, info

    def test_direct_sink_entry_metadata_carries_method(self):
        comfyapp, entries, ext, mime, width, height, info = self._encode("fast")
        entry = {
            "filename": "preview.webp",
            "bytes": entries[0][0],
            "file_ext": ext,
            "mime_type": mime,
            "format": info["format"],
            "width": width,
            "height": height,
            **comfyapp._encode_entry_metadata(info, 0, entries[0][0]),
        }
        attempt = DirectOutputSink.from_registry({"7": {"images": [entry]}}).collect(
            prompt_id="p", output_node_ids=("7",)
        )
        meta = attempt.items[0].conversion_meta
        assert meta is not None
        self.assertEqual(meta.webp_effort, "fast")
        self.assertEqual(meta.webp_method, 0)
        result = attempt_to_descriptor_result(attempt)
        self.assertEqual(result["images"][0]["webp_method"], 0)
        self.assertEqual(result["images"][0]["webp_effort"], "fast")
        descriptor = result["asset_descriptors"][0]
        self.assertEqual(descriptor["webp_method"], 0)
        self.assertEqual(descriptor["webp_effort"], "fast")

    def test_direct_sink_original_has_no_webp_method(self):
        comfyapp = pytest.importorskip("comfyapp")
        comfyapp.encode_image_tensor_batch(_tensor(), "original", None, "balanced")
        info = comfyapp.get_last_output_encode_info()
        self.assertIsNone(info["webp_effort"])
        self.assertIsNone(info["webp_method"])


class FallbackConverterParityTests(unittest.TestCase):
    def test_direct_and_fallback_methods_match_for_preview_default(self):
        comfyapp = pytest.importorskip("comfyapp")
        comfyapp.encode_image_tensor_batch(_tensor(), "webp", None, "fast")
        sink_info = comfyapp.get_last_output_encode_info()
        converted = convert_image_bytes(
            _png_bytes(), output_format="webp_lossy", quality=70,
            webp_lossless_compression="fast",
        )
        self.assertEqual(sink_info["webp_method"], converted["webp_method"])
        self.assertEqual(sink_info["webp_method"], 0)

    def test_fallback_converter_result_propagates_method_to_items(self):
        from comfymodal_runtime.output_delivery import OutputItem
        from comfymodal_runtime.result_delivery import convert_output_items

        items = [OutputItem(node_id="7", output_key="images", raw_bytes=_png_bytes())]
        result = convert_output_items(
            items, output_format="webp_lossy", quality=70,
            webp_lossless_compression="fast",
        )
        meta = result.items[0].conversion_meta
        assert meta is not None
        self.assertEqual(meta.webp_effort, "fast")
        self.assertEqual(meta.webp_method, 0)


class PreservationTests(unittest.TestCase):
    def test_original_converter_is_noop_without_effort(self):
        source = _png_bytes()
        converted = convert_image_bytes(source, output_format="original")
        self.assertEqual(converted["bytes"], source)
        self.assertIsNone(converted["webp_effort"])
        self.assertIsNone(converted["webp_method"])

    def test_direct_sink_lossless_reports_mapped_methods(self):
        comfyapp = pytest.importorskip("comfyapp")
        for effort, expected in (("fast", 0), ("balanced", 4), ("max", 6)):
            comfyapp.encode_image_tensor_batch(
                _tensor(), "webp_lossless", None, effort
            )
            info = comfyapp.get_last_output_encode_info()
            self.assertEqual(info["format"], "webp_lossless")
            self.assertEqual(info["webp_lossless_compression"], effort)
            self.assertEqual(info["webp_method"], expected)


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
