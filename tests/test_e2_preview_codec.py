from __future__ import annotations

import io

import pytest

from comfymodal_runtime.contracts import (
    ExecutionOptions,
    DEFAULT_PREVIEW_QUALITY,
    normalize_output_format,
    normalize_quality,
)
from comfymodal_runtime.modal_app import _should_run_posthoc_output_conversion
from comfymodal_runtime.output_delivery import (
    Attempt,
    DirectOutputSink,
    attempt_to_descriptor_result,
)
from output_converter import convert_image_bytes


def _png_bytes() -> bytes:
    from PIL import Image

    image = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _tensor():
    torch = pytest.importorskip("torch")
    return torch.tensor(
        [[
            [[255, 0, 0, 255], [0, 255, 0, 255]],
            [[0, 0, 255, 128], [255, 0, 0, 0]],
        ]],
        dtype=torch.uint8,
    )


def test_execution_options_round_trip_preserves_canonical_conversion_fields():
    options = ExecutionOptions.from_legacy({
        "output_conversion_options": {
            "format": "webp",
            "quality": "70",
            "webp_lossless_compression": "max",
        },
    })

    assert options.output_conversion_options["format"] == "webp_lossy"
    assert options.output_conversion_options["quality"] == DEFAULT_PREVIEW_QUALITY
    assert options.output_conversion_options["webp_lossless_compression"] == "max"
    legacy = options.to_legacy_dict()
    assert legacy["output_format"] == "webp_lossy"
    assert legacy["quality"] == 70
    assert legacy["webp_lossless_compression"] == "max"

    restored = ExecutionOptions.from_legacy(options.to_dict())
    assert restored.to_dict() == options.to_dict()


def test_original_contract_keeps_existing_default_quality():
    options = ExecutionOptions.from_legacy({"output_format": "original"})
    assert options.output_conversion_options["format"] == "original"
    assert "quality" not in options.output_conversion_options
    assert options.to_legacy_dict()["output_format"] == "original"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("webp", "webp_lossy"), ("png", "original"), ("jpg", "jpeg")],
)
def test_codec_aliases_are_canonical(value, expected):
    assert normalize_output_format(value) == expected


def test_unsupported_codec_is_rejected_without_original_silent_fallback():
    with pytest.raises(ValueError, match="unsupported output format"):
        normalize_output_format("avif")

    converted = convert_image_bytes(_png_bytes(), output_format="avif")
    assert converted["fallback"] is True
    assert converted["conversion_fallback"] is True
    assert converted["error"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 75), ("70", 70), (-5, 0), (101, 100), ("not-a-number", 75)],
)
def test_quality_normalization_is_deterministic(value, expected):
    assert normalize_quality(value) == expected


def test_direct_sink_preview_encoder_emits_decodable_webp_and_codec_metadata():
    comfyapp = pytest.importorskip("comfyapp")
    assert comfyapp._collect_production_request_params({
        "output_format": "webp",
        "quality": None,
        "webp_lossless_compression": "balanced",
    }) == ("webp_lossy", 70, "balanced")
    entries, ext, mime, width, height = comfyapp.encode_image_tensor_batch(
        _tensor(), "webp", None, "balanced"
    )
    info = comfyapp.get_last_output_encode_info()

    assert ext == ".webp"
    assert mime == "image/webp"
    assert (width, height) == (2, 2)
    assert info["codec"] == "webp"
    assert info["format"] == "webp_lossy"
    assert info["quality"] == 70
    assert info["output_codec_ms"] >= 0
    assert info["encoded_bytes"] == len(entries[0][0])
    assert info["source_bytes"] == 2 * 2 * 4
    assert info["conversion_fallback"] is False
    assert info["items"][0]["output_codec_ms"] >= 0

    from PIL import Image

    with Image.open(io.BytesIO(entries[0][0])) as image:
        assert image.format == "WEBP"
        assert image.size == (2, 2)


@pytest.mark.parametrize(
    ("output_format", "extension", "mime", "pillow_format"),
    [
        ("original", ".png", "image/png", "PNG"),
        ("webp_lossless", ".webp", "image/webp", "WEBP"),
        ("jpeg", ".jpg", "image/jpeg", "JPEG"),
    ],
)
def test_direct_sink_encoder_formats_are_decodable(
    output_format, extension, mime, pillow_format
):
    comfyapp = pytest.importorskip("comfyapp")
    entries, ext, actual_mime, _, _ = comfyapp.encode_image_tensor_batch(
        _tensor(), output_format, 70, "fast"
    )
    assert ext == extension
    assert actual_mime == mime

    from PIL import Image

    with Image.open(io.BytesIO(entries[0][0])) as image:
        assert image.format == pillow_format


def test_jpeg_direct_sink_composites_transparent_pixels_onto_white():
    comfyapp = pytest.importorskip("comfyapp")
    torch = pytest.importorskip("torch")
    entries, _, _, _, _ = comfyapp.encode_image_tensor_batch(
        torch.tensor([[[[255, 0, 0, 0]]]], dtype=torch.uint8),
        "jpeg",
        70,
        "balanced",
    )

    from PIL import Image

    with Image.open(io.BytesIO(entries[0][0])) as image:
        assert image.mode == "RGB"
        assert all(channel > 245 for channel in image.getpixel((0, 0)))


def test_direct_sink_metadata_reaches_output_attempt_without_reencoding():
    comfyapp = pytest.importorskip("comfyapp")
    entries, ext, mime, width, height = comfyapp.encode_image_tensor_batch(
        _tensor(), "webp", 70, "balanced"
    )
    info = comfyapp.get_last_output_encode_info()
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

    assert attempt.success
    assert attempt.total_conversion_time_ms == info["output_codec_ms"]
    assert attempt.items[0].conversion_meta.codec == "webp"
    assert attempt.items[0].conversion_meta.quality == 70
    assert attempt.items[0].conversion_meta.output_codec_ms >= 0
    descriptor = attempt_to_descriptor_result(attempt)
    assert descriptor["images"][0]["codec"] == "webp"
    assert descriptor["images"][0]["quality"] == 70
    assert descriptor["images"][0]["output_codec_ms"] >= 0
    assert _should_run_posthoc_output_conversion(attempt, "webp_lossy") is False


def test_original_result_is_not_posthoc_converted():
    original = Attempt(strategy="direct_output_sink", success=True)
    fallback = Attempt(strategy="history_output_collector", success=True)
    assert _should_run_posthoc_output_conversion(original, "webp_lossy") is False
    assert _should_run_posthoc_output_conversion(original, "original") is False
    assert _should_run_posthoc_output_conversion(fallback, "webp_lossy") is True


def test_existing_converter_metadata_remains_compatible():
    converted = convert_image_bytes(
        _png_bytes(), output_format="webp_lossless", webp_lossless_compression="max"
    )
    assert converted["error"] is None
    assert converted["output_format"] == "webp_lossless"
    assert converted["webp_lossless_compression"] == "max"
    assert converted["encoded_bytes"] == len(converted["bytes"])
