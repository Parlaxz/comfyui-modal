"""Focused tests for result_delivery.py legacy payload adapters and materialization."""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comfymodal_runtime.result_delivery import (
    build_native_output_descriptor,
    infer_file_ext,
    unique_path,
    stable_output_identity,
    build_materialized_output_entry,
    select_primary_output,
    select_primary_result_entry,
    convert_output_items,
    ConversionFailedError,
    ConversionBatchResult,
    adapt_legacy_result_payload,
    materialize_modal_result,
    make_thumbnail,
)
from comfymodal_runtime.output_delivery import (
    OutputItem,
    _make_conversion_meta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _png_bytes(r: int = 128, g: int = 128, b: int = 128) -> bytes:
    import struct, zlib
    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = zlib.compress(struct.pack(">B", 0) + bytes([r, g, b]))
    idat = _chunk(b"IDAT", raw)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _remote_entry(
    filename: str,
    payload: bytes,
    *,
    node_id: str = "107",
    output_key: str = "images",
    comparison_side: str = "",
    output_index: int = 0,
    mime_type: str = "image/png",
    file_ext: str = ".png",
    image_format: str = "png",
) -> dict:
    return {
        "filename": filename,
        "data": base64.b64encode(payload).decode("ascii"),
        "node_id": node_id,
        "output_key": output_key,
        "comparison_side": comparison_side,
        "output_index": output_index,
        "mime_type": mime_type,
        "file_ext": file_ext,
        "format": image_format,
        "width": 64,
        "height": 64,
    }


# ---------------------------------------------------------------------------
# Native descriptor tests
# ---------------------------------------------------------------------------

class TestBuildNativeOutputDescriptor:
    def test_default_type_is_output(self):
        desc = build_native_output_descriptor("test.png")
        assert desc["filename"] == "test.png"
        assert desc["subfolder"] == ""
        assert desc["type"] == "output"

    def test_explicit_subfolder_and_type(self):
        desc = build_native_output_descriptor("test.png", subfolder="sub", type_="input")
        assert desc["subfolder"] == "sub"
        assert desc["type"] == "input"


# ---------------------------------------------------------------------------
# Infer file extension tests
# ---------------------------------------------------------------------------

class TestInferFileExt:
    def test_png_mime(self):
        assert infer_file_ext("img", mime_type="image/png") == ".png"

    def test_webp_mime(self):
        assert infer_file_ext("img", mime_type="image/webp") == ".webp"

    def test_jpeg_mime(self):
        assert infer_file_ext("img", mime_type="image/jpeg") == ".jpg"

    def test_explicit_ext(self):
        assert infer_file_ext("img.png", file_ext=".webp") == ".webp"

    def test_ext_from_filename(self):
        assert infer_file_ext("output.jpg") == ".jpg"

    def test_fallback_to_png(self):
        assert infer_file_ext("unknown") == ".png"


# ---------------------------------------------------------------------------
# Unique path tests
# ---------------------------------------------------------------------------

class TestUniquePath:
    def test_new_file_returns_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = unique_path(tmp, "test.png")
            assert path == os.path.join(tmp, "test.png")

    def test_existing_file_appends_uuid(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = os.path.join(tmp, "test.png")
            Path(existing).write_bytes(b"data")
            path = unique_path(tmp, "test.png")
            assert path != existing
            assert path.startswith(os.path.join(tmp, "test_"))
            assert path.endswith(".png")

    def test_unsafe_filename_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="unsafe"):
                unique_path(tmp, "../escape.png")


# ---------------------------------------------------------------------------
# Stable identity tests
# ---------------------------------------------------------------------------

class TestStableOutputIdentity:
    def test_basic_identity(self):
        entry = {"output_index": 0, "filename": "out.png", "output_key": "images"}
        ident = stable_output_identity("107", "images", entry)
        assert ident == ("107", "images", "out.png", 0)

    def test_fallback_index(self):
        entry = {"filename": "out.png"}
        ident = stable_output_identity("107", "images", entry, fallback_index=5)
        assert ident[3] == 5


# ---------------------------------------------------------------------------
# Materialized entry tests
# ---------------------------------------------------------------------------

class TestBuildMaterializedEntry:
    def test_basic_fields(self):
        entry = {"mime_type": "image/png", "filename": "test.png", "width": 128}
        result = build_materialized_output_entry(
            entry,
            node_id="7",
            output_key="images",
            local_filename="test.png",
            local_path="/tmp/test.png",
            decoded_bytes=b"data",
        )
        assert result["node_id"] == "7"
        assert result["output_key"] == "images"
        assert result["width"] == 128
        assert result["byte_count"] == 4


# ---------------------------------------------------------------------------
# Primary output selection tests
# ---------------------------------------------------------------------------

class TestSelectPrimaryOutput:
    def test_b_side_preferred(self):
        a = _remote_entry("a.png", b"a", output_key="a_images", comparison_side="a")
        b = _remote_entry("b.png", b"b", output_key="b_images", comparison_side="b")
        selected = select_primary_output(
            {"107": {"a_images": [a], "b_images": [b]}}, "107"
        )
        assert selected is not None
        assert selected["comparison_side"] == "b"

    def test_b_images_key_as_fallback(self):
        b = _remote_entry("b.png", b"b", output_key="b_images", comparison_side="")
        selected = select_primary_output({"107": {"b_images": [b]}}, "107")
        assert selected is not None
        assert selected["output_key"] == "b_images"

    def test_fallback_to_images(self):
        img = _remote_entry("img.png", b"img", output_key="images")
        selected = select_primary_output({"107": {"images": [img]}}, "107")
        assert selected is not None
        assert selected["output_key"] == "images"

    def test_empty_returns_none(self):
        assert select_primary_output({}, "107") is None
        assert select_primary_output({"107": {}}, "107") is None


class TestSelectPrimaryResultEntry:
    def test_from_structured_outputs(self):
        b = _remote_entry("b.png", b"b", node_id="107", output_key="b_images", comparison_side="b")
        result = {"outputs": {"107": {"b_images": [b]}}}
        entry = select_primary_result_entry(result)
        assert entry is not None
        assert entry["comparison_side"] == "b"

    def test_from_flat_images(self):
        img = _remote_entry("img.png", b"img", node_id="7")
        result = {"images": [img]}
        entry = select_primary_result_entry(result)
        assert entry is not None
        assert entry["node_id"] == "7"

    def test_empty_result(self):
        assert select_primary_result_entry({}) is None

    def test_expected_node_binding_skips_unrelated_outputs(self):
        unrelated = _remote_entry("preview.png", b"preview", node_id="12")
        bound = _remote_entry("final.png", b"final", node_id="107")
        entry = select_primary_result_entry(
            {"outputs": {"12": {"images": [unrelated]}, "107": {"images": [bound]}}},
            expected_output_node_ids=("107",),
        )
        assert entry is not None
        assert entry["node_id"] == "107"


# ---------------------------------------------------------------------------
# Conversion batch tests
# ---------------------------------------------------------------------------

class TestConvertOutputItems:
    def test_basic_conversion_with_mock(self):
        mock_converter = MagicMock(return_value={
            "bytes": b"converted",
            "mime_type": "image/webp",
            "file_ext": ".webp",
            "output_format": "webp_lossless",
            "original_size_bytes": 100,
            "returned_size_bytes": 50,
            "conversion_time_ms": 2.0,
            "quality": None,
            "webp_lossless_compression": "fast",
            "fallback": False,
            "error": None,
        })
        items = [OutputItem(node_id="7", output_key="images", raw_bytes=b"input-data")]
        result = convert_output_items(items, converter_fn=mock_converter)
        assert result.converted_count == 1
        assert result.failed_count == 0
        assert result.total_raw_bytes == len(b"converted")
        assert result.total_base64_bytes == 0
        assert result.total_conversion_time_ms == 2.0

    def test_conversion_failure_raises(self):
        bad_converter = MagicMock(return_value={
            "error": "Pillow not available",
            "bytes": b"original",
            "fallback": True,
        })
        items = [OutputItem(node_id="7", output_key="images", raw_bytes=b"data")]
        with pytest.raises(ConversionFailedError, match="reported error"):
            convert_output_items(items, converter_fn=bad_converter)

    def test_conversion_exception_raises(self):
        bad_converter = MagicMock(side_effect=ValueError("invalid image"))
        items = [OutputItem(node_id="7", output_key="images", raw_bytes=b"data")]
        with pytest.raises(ConversionFailedError):
            convert_output_items(items, converter_fn=bad_converter)

    def test_parallel_totals_recorded(self):
        mock = MagicMock(return_value={
            "bytes": b"conv", "mime_type": "image/png", "file_ext": ".png",
            "output_format": "original", "original_size_bytes": 5, "returned_size_bytes": 3,
            "conversion_time_ms": 1.0, "quality": None, "webp_lossless_compression": None,
            "fallback": False, "error": None,
        })
        items = [
            OutputItem(node_id="7", output_key="images", raw_bytes=b"aaa"),
            OutputItem(node_id="8", output_key="images", raw_bytes=b"bbb"),
        ]
        result = convert_output_items(items, converter_fn=mock)
        assert result.converted_count == 2
        assert result.total_raw_bytes == 8  # "conv" (4 bytes) + "conv" (4 bytes) = 8
        assert result.total_conversion_time_ms == 2.0

    def test_empty_items(self):
        result = convert_output_items([], converter_fn=MagicMock())
        assert result.converted_count == 0


# ---------------------------------------------------------------------------
# Legacy payload adapter tests
# ---------------------------------------------------------------------------

class TestAdaptLegacyPayload:
    def test_unwrap_result_key(self):
        adapted = adapt_legacy_result_payload({
            "result": {"outputs": {"7": {"images": []}}},
        })
        assert "outputs" in adapted
        assert "7" in adapted["outputs"]

    def test_result_does_not_overwrite_existing_key(self):
        adapted = adapt_legacy_result_payload({
            "outputs": {"existing": {}},
            "result": {"outputs": {"7": {"images": []}}},
        })
        assert "outputs" in adapted
        # "outputs" already exists so result's nested one should not overwrite
        assert list(adapted["outputs"].keys()) == ["existing"]

    def test_no_outputs_fallback(self):
        adapted = adapt_legacy_result_payload({})
        assert adapted["outputs"] == {}

    def test_legacy_output_candidate(self):
        adapted = adapt_legacy_result_payload({
            "output": {"7": {"images": []}},
        })
        assert "outputs" in adapted
        assert list(adapted["outputs"].keys()) == ["7"]


# ---------------------------------------------------------------------------
# Materialization tests
# ---------------------------------------------------------------------------

class TestMaterializeModalResult:
    def test_png_metadata(self):
        a_bytes = _png_bytes(255, 0, 0)
        b_bytes = _png_bytes(0, 255, 0)
        a_entry = _remote_entry("compare_a.png", a_bytes, output_key="a_images", comparison_side="a", output_index=0)
        b_entry = _remote_entry("compare_b.png", b_bytes, output_key="b_images", comparison_side="b", output_index=1)
        result = {
            "images": [a_entry, b_entry],
            "outputs": {"107": {"a_images": [a_entry], "b_images": [b_entry]}},
        }
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result,
                output_dir=tmp,
                prompt_id="prompt-123",
                client_id="client-abc",
                send_event=lambda event, payload: events.append((event, payload)),
            )
            assert summary["image_count"] == 2
            assert len(summary["written_files"]) == 2
            assert (Path(tmp) / "compare_a.png").read_bytes() == a_bytes
            assert (Path(tmp) / "compare_b.png").read_bytes() == b_bytes
            assert len(events) >= 1
            assert events[0][0] == "executed"

    def test_no_output_returns_empty_summary(self):
        result = {"outputs": {}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            assert summary["image_count"] == 0
            assert summary["video_count"] == 0
            assert summary["written_files"] == []

    def test_required_output_uses_expected_node_binding(self):
        unrelated = _remote_entry("preview.png", _png_bytes(1, 2, 3), node_id="12")
        bound = _remote_entry("final.png", _png_bytes(4, 5, 6), node_id="107")
        result = {
            "execution_id": "exec-107",
            "outputs": {
                "12": {"images": [unrelated]},
                "107": {"images": [bound]},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result,
                output_dir=tmp,
                prompt_id="p1",
                require_output=True,
                expected_output_node_ids=("107",),
            )
            assert summary["primary_output"]["node_id"] == "107"
            assert summary["primary_output"]["filename"] == "final.png"

    def test_required_descriptor_output_is_valid_without_local_write(self):
        descriptor = {
            "filename": "final.png",
            "asset_id": "asset-final",
            "identity": "sha256:asset-final",
            "path": "modal://workspace|A100|outputs/final.png",
            "backend_path": "outputs/final.png",
            "node_id": "107",
            "output_key": "images",
            "byte_count": 128,
            "mime_type": "image/png",
            "file_ext": ".png",
        }
        result = {
            "outputs": {"107": {"images": [{"filename": "final.png"}]}},
            "images": [descriptor],
        }
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result,
                output_dir=tmp,
                prompt_id="p1",
                require_output=True,
                expected_output_node_ids=("107",),
            )
            assert summary["primary_output"]["node_id"] == "107"
            assert summary["primary_output"]["asset_id"] == "asset-final"
            assert summary["written_files"] == []

    def test_required_output_error_identifies_missing_binding(self):
        result = {
            "execution_id": "exec-missing",
            "status": "completed",
            "outputs": {"12": {"images": [_remote_entry("preview.png", b"preview", node_id="12")]}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(
                RuntimeError,
                match=r"execution_id=exec-missing.*expected_output_node=107.*available_output_nodes=\['12'\]",
            ):
                materialize_modal_result(
                    result,
                    output_dir=tmp,
                    prompt_id="p1",
                    require_output=True,
                    expected_output_node_ids=("107",),
                )

    def test_multi_output_nodes(self):
        a = _remote_entry("a.png", b"data-a", node_id="7", output_key="images")
        b = _remote_entry("b.png", b"data-b", node_id="8", output_key="images")
        result = {"outputs": {"7": {"images": [a]}, "8": {"images": [b]}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            assert summary["image_count"] == 2
            assert len(summary["outputs"]) == 2

    def test_comparer_b_primary(self):
        a_entry = _remote_entry("compare_a.png", b"a-data", output_key="a_images", comparison_side="a", output_index=0)
        b_entry = _remote_entry("compare_b.png", b"b-data", output_key="b_images", comparison_side="b", output_index=1)
        result = {
            "images": [a_entry, b_entry],
            "outputs": {"107": {"a_images": [a_entry], "b_images": [b_entry]}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            primary = summary["primary_output"]
            assert primary is not None
            assert primary["comparison_side"] == "b"
            assert primary["output_key"] == "b_images"

    def test_primary_b_only(self):
        """When only a single b_images output exists, it should be primary."""
        b = _remote_entry("b.png", b"b-data", output_key="b_images", comparison_side="b")
        result = {"outputs": {"7": {"b_images": [b]}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            assert summary["primary_output"]["comparison_side"] == "b"

    def test_history_alias_b_images_to_images(self):
        b = _remote_entry("b.png", b"b-data", output_key="b_images", comparison_side="b")
        result = {"outputs": {"107": {"b_images": [b]}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            assert "b_images" in summary["history_outputs"]["107"]
            assert "images" in summary["history_outputs"]["107"]

    def test_animated_video_preserved(self):
        gif_bytes = b"GIF89a" + b"\x00" * 10
        gif = _remote_entry("anim.gif", gif_bytes, output_key="gifs", mime_type="image/gif", file_ext=".gif")
        result = {"outputs": {"200": {"gifs": [gif]}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            assert summary["video_count"] == 1
            assert "animated" in summary["materialized_outputs"]["200"]

    def test_conversion_failure_fails_batch(self):
        """Conversion failure must fail the entire materialization."""
        with patch("comfymodal_runtime.result_delivery.materialize_modal_result") as mock:
            mock.side_effect = ConversionFailedError("conversion failed")
            with pytest.raises(ConversionFailedError):
                mock(
                    {"outputs": {}}, output_dir="/tmp", prompt_id="p1",
                )


# ---------------------------------------------------------------------------
# Thumbnail tests
# ---------------------------------------------------------------------------

class TestMakeThumbnail:
    def test_thumbnail_from_png(self):
        png = _png_bytes(100, 150, 200)
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "input.png")
            dst = os.path.join(tmp, "thumb.webp")
            Path(src).write_bytes(png)
            result = make_thumbnail(src, dst)
            # May be True or False depending on PIL availability
            if result:
                assert Path(dst).exists()
                assert Path(dst).stat().st_size > 0

    def test_thumbnail_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "thumb.webp")
            result = make_thumbnail("/nonexistent.png", dst)
            assert result is False


# ---------------------------------------------------------------------------
# Phase 6 — Materialization decode/write timing
# ---------------------------------------------------------------------------

class TestPhase6MaterializationTiming:
    """Focused tests for Phase 6 materialization timing observability."""

    def test_summary_contains_timing_key(self):
        """materialize_modal_result returns materialization_timing dict."""
        result = {"outputs": {}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            assert "materialization_timing" in summary
            timing = summary["materialization_timing"]
            assert "total_wall_ms" in timing
            assert "total_decode_time_ms" in timing
            assert "total_write_time_ms" in timing
            assert "item_count" in timing
            assert "bytes_written" in timing

    def test_timing_zero_for_no_output(self):
        """Empty output has zero timing values."""
        result = {"outputs": {}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            timing = summary["materialization_timing"]
            assert timing["total_decode_time_ms"] == 0.0
            assert timing["total_write_time_ms"] == 0.0
            assert timing["item_count"] == 0
            assert timing["bytes_written"] == 0
            assert timing["total_wall_ms"] >= 0

    def test_decode_write_time_positive_for_real_output(self):
        """Real output produces non-negative decode and write times."""
        a_bytes = _png_bytes(255, 0, 0)
        a_entry = _remote_entry("out.png", a_bytes, node_id="7")
        result = {"outputs": {"7": {"images": [a_entry]}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            timing = summary["materialization_timing"]
            assert timing["total_decode_time_ms"] >= 0
            assert timing["total_write_time_ms"] >= 0
            assert timing["item_count"] == 1
            assert timing["bytes_written"] == len(a_bytes)
            assert timing["total_wall_ms"] >= timing["total_decode_time_ms"] + timing["total_write_time_ms"] - 1.0

    def test_multiple_outputs_accumulate_timing(self):
        """Multiple outputs accumulate decode/write time correctly."""
        a_bytes = _png_bytes(255, 0, 0)
        b_bytes = _png_bytes(0, 255, 0)
        a_entry = _remote_entry("a.png", a_bytes, node_id="7", output_key="images")
        b_entry = _remote_entry("b.png", b_bytes, node_id="8", output_key="images")
        result = {"outputs": {"7": {"images": [a_entry]}, "8": {"images": [b_entry]}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            timing = summary["materialization_timing"]
            assert timing["item_count"] == 2
            assert timing["bytes_written"] == len(a_bytes) + len(b_bytes)
            assert timing["total_decode_time_ms"] >= 0
            assert timing["total_write_time_ms"] >= 0
            # Total wall >= sum of decode + write (within rounding)
            assert timing["total_wall_ms"] >= timing["total_decode_time_ms"] + timing["total_write_time_ms"] - 1.0

    def test_timing_preserved_with_legacy_payload(self):
        """Legacy payload adapter doesn't strip timing."""
        a_bytes = _png_bytes(100, 100, 100)
        entry = _remote_entry("img.png", a_bytes, node_id="7")
        result = {"result": {"outputs": {"7": {"images": [entry]}}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result, output_dir=tmp, prompt_id="p1",
            )
            timing = summary["materialization_timing"]
            assert timing["total_decode_time_ms"] >= 0
            assert timing["item_count"] == 1
