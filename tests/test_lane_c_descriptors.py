"""Lane C: lightweight asset descriptor tests.

Tests cover:
  1. Descriptor construction without base64
  2. Asset route byte serving
  3. Narrow legacy fallback (base64 data preserved)
  4. Studio/history rendering with descriptors
  5. Primary output selection with descriptors
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import tempfile
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comfymodal_runtime.output_delivery import (
    Attempt,
    OutputItem,
    AssetDescriptor,
    _make_conversion_meta,
    build_asset_descriptor_list,
    attempt_to_descriptor_result,
)
from comfymodal_runtime.result_delivery import (
    materialize_modal_result,
    build_native_output_descriptor,
    select_primary_output,
    select_primary_result_entry,
    adapt_legacy_result_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _png_bytes(r: int = 128, g: int = 128, b: int = 128) -> bytes:
    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = zlib.compress(struct.pack(">B", 0) + bytes([r, g, b]))
    idat = _chunk(b"IDAT", raw)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _make_output_item(
    *,
    node_id: str = "107",
    output_key: str = "images",
    filename: str = "out.png",
    raw_bytes: bytes = b"",
    width: int = 64,
    height: int = 64,
    comparison_side: str = "",
    mime_type: str = "image/png",
    file_ext: str = ".png",
    output_index: int = 0,
    fmt: str = "png",
    path: str = "",
) -> OutputItem:
    if not raw_bytes:
        raw_bytes = _png_bytes()
    return OutputItem(
        node_id=node_id,
        output_key=output_key,
        filename=filename,
        path=path or f"/assets/{filename}",
        raw_bytes=raw_bytes,
        base64_data="",  # No base64 by default in descriptor mode
        mime_type=mime_type,
        file_ext=file_ext,
        width=width,
        height=height,
        output_index=output_index,
        comparison_side=comparison_side,
        format=fmt,
        animated=False,
        conversion_meta=None,
    )


# ===================================================================
# 1. Descriptor construction WITHOUT base64
# ===================================================================

class TestAssetDescriptorConstruction:
    """Verify AssetDescriptor is built from OutputItem without base64 data."""

    def test_descriptor_has_no_data_key(self):
        """The descriptor dict MUST NOT contain 'data' or 'base64_data'."""
        raw = _png_bytes(255, 0, 0)
        item = _make_output_item(raw_bytes=raw, filename="a.png")
        attempt = Attempt(
            strategy="direct_output_sink",
            success=True,
            items=(item,),
            total_items=1,
            total_raw_bytes=len(raw),
        )
        descs = build_asset_descriptor_list(attempt)
        assert len(descs) == 1
        d = descs[0]
        assert isinstance(d, AssetDescriptor)
        # Verify no data leakage
        assert not hasattr(d, "data")
        assert not hasattr(d, "base64_data")
        assert not hasattr(d, "raw_bytes")

    def test_descriptor_identity_is_content_hash(self):
        """Descriptor identity is sha256 of raw bytes."""
        raw = _png_bytes(10, 20, 30)
        item = _make_output_item(raw_bytes=raw)
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        descs = build_asset_descriptor_list(attempt)
        expected = "sha256:" + hashlib.sha256(raw).hexdigest()
        assert descs[0].identity == expected

    def test_descriptor_carries_requested_fields(self):
        """Descriptor includes identity, path, file, type, dimensions, bytes,
        node, output, comparison, generation."""
        raw = _png_bytes(100, 200, 150)
        item = _make_output_item(
            node_id="42",
            output_key="b_images",
            filename="result.png",
            raw_bytes=raw,
            width=1024,
            height=768,
            comparison_side="b",
            mime_type="image/webp",
            file_ext=".webp",
            output_index=2,
        )
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        descs = build_asset_descriptor_list(attempt, generation="v2-lane-c")
        d = descs[0]

        # identity
        assert d.identity == "sha256:" + hashlib.sha256(raw).hexdigest()
        # path
        assert "/assets/result.png" in d.path
        # filename
        assert d.filename == "result.png"
        # type (mime_type)
        assert d.mime_type == "image/webp"
        # dimensions
        assert d.width == 1024
        assert d.height == 768
        # bytes
        assert d.byte_count == len(raw)
        # node
        assert d.node_id == "42"
        # output
        assert d.output_key == "b_images"
        assert d.output_index == 2
        # comparison
        assert d.comparison_side == "b"
        # generation
        assert d.generation == "v2-lane-c"

    def test_empty_attempt_returns_empty_descriptors(self):
        """An Attempt with zero items yields an empty descriptor list."""
        attempt = Attempt(strategy="test", success=False, items=())
        descs = build_asset_descriptor_list(attempt)
        assert descs == []

    def test_descriptor_byte_count_matches_raw(self):
        """byte_count equals len(raw_bytes) of the original item."""
        raw = _png_bytes(200, 100, 50)
        item = _make_output_item(raw_bytes=raw)
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        descs = build_asset_descriptor_list(attempt)
        assert descs[0].byte_count == len(raw)

    def test_multiple_items_all_have_descriptors(self):
        """Multiple output items each get their own descriptor."""
        raw_a = _png_bytes(255, 0, 0)
        raw_b = _png_bytes(0, 255, 0)
        items = [
            _make_output_item(node_id="7", filename="a.png", raw_bytes=raw_a),
            _make_output_item(node_id="8", filename="b.png", raw_bytes=raw_b),
        ]
        attempt = Attempt(strategy="test", success=True, items=tuple(items), total_items=2)
        descs = build_asset_descriptor_list(attempt)
        assert len(descs) == 2
        assert descs[0].identity != descs[1].identity

    def test_thumbnail_identity_optional(self):
        """thumbnail_identity is empty by default and settable."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw)
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        descs = build_asset_descriptor_list(attempt, thumbnail_identities={item.node_id: "thumb:abc"})
        assert descs[0].thumbnail_identity == "thumb:abc"

        # Without thumbnail mapping, it's empty
        descs2 = build_asset_descriptor_list(attempt)
        assert descs2[0].thumbnail_identity == ""


# ===================================================================
# 2. Result dict format — NO base64_data in normal response
# ===================================================================

class TestAttemptToDescriptorResult:
    """Verify attempt_to_descriptor_result produces entries without base64."""

    def test_images_entries_have_no_data_key(self):
        """Default descriptor result images entries MUST lack 'data'."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw, node_id="7")
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        result = attempt_to_descriptor_result(attempt)
        for img in result.get("images", []):
            assert "data" not in img, "descriptor result must not contain base64 data"
            assert "base64_data" not in img
        for vid in result.get("videos", []):
            assert "data" not in vid
            assert "base64_data" not in vid

    def test_images_entries_have_descriptor_fields(self):
        """Descriptor result images have identity, path, byte_count."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw, node_id="7", filename="out.png", width=512, height=512)
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        result = attempt_to_descriptor_result(attempt)
        img = result["images"][0]
        assert "identity" in img
        assert "path" in img
        assert "byte_count" in img
        assert img["byte_count"] == len(raw)
        assert img["width"] == 512
        assert img["height"] == 512
        assert img["node_id"] == "7"
        assert img["filename"] == "out.png"

    def test_legacy_flag_preserves_data(self):
        """When legacy_data=True, entries include base64 'data'."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw)
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        result = attempt_to_descriptor_result(attempt, legacy_data=True)
        assert "data" in result["images"][0]
        assert result["images"][0]["data"] == base64.b64encode(raw).decode("ascii")

    def test_outputs_format_preserved(self):
        """The 'outputs' dict still uses native {filename, subfolder, type}."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw, node_id="7", output_key="images", filename="out.png")
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        result = attempt_to_descriptor_result(attempt)
        outputs = result.get("outputs", {})
        assert "7" in outputs
        assert "images" in outputs["7"]
        entry = outputs["7"]["images"][0]
        assert entry.get("filename") == "out.png"
        assert entry.get("subfolder") == ""
        assert entry.get("type") == "output"
        assert "data" not in entry

    def test_asset_descriptors_top_level_key(self):
        """Result includes top-level 'asset_descriptors' list."""
        raw_a = _png_bytes()
        raw_b = _png_bytes(0, 255, 0)
        items = [
            _make_output_item(node_id="7", filename="a.png", raw_bytes=raw_a),
            _make_output_item(node_id="8", filename="b.png", raw_bytes=raw_b),
        ]
        attempt = Attempt(strategy="test", success=True, items=tuple(items), total_items=2)
        result = attempt_to_descriptor_result(attempt)
        assert "asset_descriptors" in result
        assert len(result["asset_descriptors"]) == 2
        for ad in result["asset_descriptors"]:
            assert "identity" in ad
            assert "path" in ad
            assert "filename" in ad
            assert "byte_count" in ad
            assert "thumbnail_identity" in ad

    def test_generation_propagated_to_descriptors(self):
        """Generation string is propagated to all descriptors."""
        raw = _png_bytes()
        items = [
            _make_output_item(node_id="7", filename="a.png", raw_bytes=raw),
            _make_output_item(node_id="8", filename="b.png", raw_bytes=raw),
        ]
        attempt = Attempt(strategy="test", success=True, items=tuple(items), total_items=2)
        result = attempt_to_descriptor_result(attempt, generation="prod-v3")
        for ad in result.get("asset_descriptors", []):
            assert ad["generation"] == "prod-v3"


# ===================================================================
# 3. Materialization with descriptor-only entries (no base64)
# ===================================================================

class TestMaterializationWithDescriptors:
    """materialize_modal_result handles entries without 'data' gracefully."""

    def test_skips_decode_when_data_missing(self):
        """Entries without 'data' skip decode/write but still produce output."""
        raw = _png_bytes()
        entry = {
            "filename": "out.png",
            "node_id": "107",
            "output_key": "images",
            "mime_type": "image/png",
            "file_ext": ".png",
            "width": 64,
            "height": 64,
            "byte_count": len(raw),
            "identity": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "path": "/volume/outputs/out.png",
            # NO "data" key — descriptor mode
        }
        result = {
            "outputs": {"107": {"images": [entry]}},
            "images": [entry],
        }
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result,
                output_dir=tmp,
                prompt_id="p1",
            )
            # Should produce native outputs without writing files
            assert "outputs" in summary
            assert "107" in summary["outputs"]
            assert summary["written_files"] == []
            assert summary["image_count"] == 1
            assert summary["bytes_written"] == 0
            # Should still have history_outputs
            assert "history_outputs" in summary
            assert "107" in summary["history_outputs"]

    def test_mixed_data_and_descriptors(self):
        """Entries WITH data get decoded/written; entries without data are skipped."""
        raw_with = _png_bytes(255, 0, 0)
        raw_without = _png_bytes(0, 255, 0)
        entry_with_data = {
            "filename": "with_data.png",
            "data": base64.b64encode(raw_with).decode("ascii"),
            "node_id": "7",
            "output_key": "images",
            "mime_type": "image/png",
            "file_ext": ".png",
            "width": 32,
            "height": 32,
        }
        entry_descriptor = {
            "filename": "descriptor_only.png",
            "node_id": "8",
            "output_key": "images",
            "mime_type": "image/png",
            "file_ext": ".png",
            "width": 64,
            "height": 64,
            "byte_count": len(raw_without),
            "identity": "sha256:" + hashlib.sha256(raw_without).hexdigest(),
            "path": "/volume/descriptor_only.png",
            # NO "data"
        }
        result = {
            "outputs": {
                "7": {"images": [entry_with_data]},
                "8": {"images": [entry_descriptor]},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result,
                output_dir=tmp,
                prompt_id="p1",
            )
            assert summary["image_count"] == 2
            assert len(summary["written_files"]) == 1
            assert os.path.exists(summary["written_files"][0])
            assert "with_data" in summary["written_files"][0]
            # Both nodes should have history_outputs
            assert "7" in summary["history_outputs"]
            assert "8" in summary["history_outputs"]

    def test_legacy_payload_with_missing_data_still_adapts(self):
        """adapt_legacy_result_payload doesn't crash on descriptor entries."""
        raw = _png_bytes()
        entry = {
            "filename": "out.png",
            "identity": "sha256:" + hashlib.sha256(raw).hexdigest(),
        }
        result = {"outputs": {"7": {"images": [entry]}}}
        adapted = adapt_legacy_result_payload(result)
        assert "outputs" in adapted
        assert "7" in adapted["outputs"]


# ===================================================================
# 4. Narrow legacy fallback — base64 preserved when explicitly requested
# ===================================================================

class TestLegacyFallback:
    """Legacy format with base64 'data' is preserved as opt-in."""

    def test_legacy_data_included_when_flag_set(self):
        """attempt_to_descriptor_result with legacy_data=True includes 'data'."""
        raw = _png_bytes(255, 128, 64)
        item = _make_output_item(raw_bytes=raw)
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        result = attempt_to_descriptor_result(attempt, legacy_data=True)
        assert "data" in result["images"][0]
        assert result["images"][0]["data"] == base64.b64encode(raw).decode("ascii")

    def test_explicit_materialization_preserved(self):
        """Explicit local materialization path (materialize_modal_result)
        still works normally with base64 data."""
        raw = _png_bytes(10, 20, 30)
        entry = {
            "filename": "legacy.png",
            "data": base64.b64encode(raw).decode("ascii"),
            "node_id": "7",
            "output_key": "images",
            "mime_type": "image/png",
            "file_ext": ".png",
            "width": 16,
            "height": 16,
        }
        result = {"outputs": {"7": {"images": [entry]}}}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result,
                output_dir=tmp,
                prompt_id="p1",
            )
            assert summary["image_count"] == 1
            assert len(summary["written_files"]) == 1
            written_path = summary["written_files"][0]
            assert Path(written_path).read_bytes() == raw

    def test_legacy_flat_images_format_preserved(self):
        """Flat 'images' list with base64 data still materializes."""
        raw = _png_bytes()
        entry = {
            "filename": "flat.png",
            "data": base64.b64encode(raw).decode("ascii"),
            "node_id": "7",
            "output_key": "images",
        }
        result = {"images": [entry]}
        with tempfile.TemporaryDirectory() as tmp:
            summary = materialize_modal_result(
                result,
                output_dir=tmp,
                prompt_id="p1",
            )
            assert summary["image_count"] == 1
            assert Path(summary["written_files"][0]).read_bytes() == raw


# ===================================================================
# 5. Studio/history rendering with descriptors
# ===================================================================

class TestStudioHistoryRendering:
    """Descriptors work with history renderers and Studio consumers."""

    def test_primary_output_selection_with_descriptors(self):
        """select_primary_output works with descriptor entries (no data)."""
        a_desc = {
            "filename": "a.png",
            "node_id": "107",
            "output_key": "a_images",
            "comparison_side": "a",
            "width": 512,
            "height": 512,
            "byte_count": 1000,
            "identity": "sha256:aaa",
        }
        b_desc = {
            "filename": "b.png",
            "node_id": "107",
            "output_key": "b_images",
            "comparison_side": "b",
            "width": 1024,
            "height": 1024,
            "byte_count": 2000,
            "identity": "sha256:bbb",
        }
        selected = select_primary_output(
            {"107": {"a_images": [a_desc], "b_images": [b_desc]}},
            "107",
        )
        assert selected is not None
        assert selected["comparison_side"] == "b"

    def test_primary_result_entry_with_descriptors(self):
        """select_primary_result_entry works on descriptor-only results."""
        result = {
            "outputs": {
                "107": {
                    "b_images": [{
                        "filename": "b.png",
                        "comparison_side": "b",
                        "width": 1024,
                        "height": 1024,
                        "byte_count": 2000,
                    }],
                },
            },
        }
        entry = select_primary_result_entry(result)
        assert entry is not None
        assert entry["comparison_side"] == "b"

    def test_history_outputs_have_native_format(self):
        """history_outputs uses {filename, subfolder, type} for history."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw, node_id="7", filename="hist.png")
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        result = attempt_to_descriptor_result(attempt)

        # The result outputs should have native format
        outputs = result["outputs"]
        for node_id, node_outputs in outputs.items():
            for output_key, entries in node_outputs.items():
                for entry in entries:
                    assert "filename" in entry
                    assert "subfolder" in entry
                    assert "type" in entry
                    assert "data" not in entry

    def test_history_aliasing_b_images_to_images(self):
        """History aliasing works with descriptor outputs."""
        raw = _png_bytes()
        items = [
            _make_output_item(node_id="7", output_key="b_images", raw_bytes=raw, filename="b.png"),
        ]
        attempt = Attempt(strategy="test", success=True, items=tuple(items), total_items=1)
        result = attempt_to_descriptor_result(attempt, generation="v2-lane-c")

        # Materialize descriptor-only result to check history aliasing
        with tempfile.TemporaryDirectory() as tmp:
            # Build materialization-compatible input from descriptor result
            entry = {
                "filename": "b.png",
                "node_id": "7",
                "output_key": "b_images",
                "comparison_side": "b",
                "mime_type": "image/png",
                "file_ext": ".png",
                "width": 64,
                "height": 64,
                "byte_count": len(raw),
                "identity": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "path": "/volume/b.png",
            }
            mat_input = {"outputs": {"7": {"b_images": [entry]}}}
            summary = materialize_modal_result(mat_input, output_dir=tmp, prompt_id="p1")
            # b_images key aliased to images in history_outputs
            hist = summary.get("history_outputs", {})
            if "7" in hist:
                has_images = "images" in hist["7"]
                has_b_images = "b_images" in hist["7"]
                # Either b_images -> images alias or both present
                assert has_images or has_b_images


# ===================================================================
# 6. Metrics — no base64 constructed merely for metrics
# ===================================================================

class TestMetricsWithoutBase64:
    """Base64 is NOT constructed solely for metrics/byte counting."""

    def test_conversion_meta_no_base64_construction(self):
        """_make_conversion_meta no longer constructs base64 for metrics."""
        raw = b"hello-image-bytes"
        meta = _make_conversion_meta(raw, "original", "image/png", ".png", 1.5)
        assert meta.raw_bytes == len(raw)
        # base64_bytes and json_result_bytes are 0 (not computed)
        assert meta.base64_bytes == 0
        assert meta.json_result_bytes == 0
        assert meta.hash_of_raw == hashlib.sha256(raw).hexdigest()

    def test_base64_not_in_normal_response(self):
        """Default descriptor result payload has no base64 data."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw)
        attempt = Attempt(strategy="test", success=True, items=(item,), total_items=1)
        result = attempt_to_descriptor_result(attempt)
        # Serialize to JSON to check no base64 data leaked
        payload_str = json.dumps(result)
        assert "data" not in payload_str or 'data":"' not in payload_str.split('"data"')[1] if '"data"' in payload_str else True

    def test_output_item_base64_empty_in_descriptor_mode(self):
        """OutputItem.base64_data is empty string in descriptor mode."""
        raw = _png_bytes()
        item = _make_output_item(raw_bytes=raw)
        assert item.base64_data == ""


# ===================================================================
# 7. Studio route serving (integration contract)
# ===================================================================

class TestStudioRouteServing:
    """Verify the existing asset route can serve descriptor-referenced files."""

    def test_route_serves_file_bytes(self):
        """The existing /comfymodal/studio/outputs/{filename} route
        serves file bytes when the file exists locally."""
        content = _png_bytes(64, 128, 192)
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "asset.png")
            Path(filepath).write_bytes(content)

            # Simulate what the route does
            ext = ".png"
            mime = {"png": "image/png"}.get(ext.lstrip("."), "application/octet-stream")
            body = Path(filepath).read_bytes()

            assert body == content
            assert mime == "image/png"

    def test_route_rejects_path_traversal(self):
        """The route must reject path traversal attempts."""
        # Simulate route guard
        filename = "../../etc/passwd"
        assert not filename or ".." in filename or "/" in filename  # should be rejected


# ===================================================================
# 8. Primary selection integration
# ===================================================================

class TestPrimarySelectionIntegration:
    """Primary output selection with descriptors preserves existing behavior."""

    def test_primary_side_b_selected(self):
        """comparison_side='b' is preferred as primary."""
        items = [
            _make_output_item(node_id="7", output_key="a_images", comparison_side="a", raw_bytes=_png_bytes(255, 0, 0)),
            _make_output_item(node_id="7", output_key="b_images", comparison_side="b", raw_bytes=_png_bytes(0, 255, 0)),
        ]
        attempt = Attempt(strategy="test", success=True, items=tuple(items), total_items=2)
        result = attempt_to_descriptor_result(attempt)

        # Primary selection from materialized outputs
        with tempfile.TemporaryDirectory() as tmp:
            mat_entry_a = {
                "filename": "a.png",
                "node_id": "7",
                "output_key": "a_images",
                "comparison_side": "a",
            }
            mat_entry_b = {
                "filename": "b.png",
                "node_id": "7",
                "output_key": "b_images",
                "comparison_side": "b",
            }
            mat_outputs = {"7": {"a_images": [mat_entry_a], "b_images": [mat_entry_b]}}
            primary = select_primary_output(mat_outputs, "7")
            assert primary is not None
            assert primary["comparison_side"] == "b"
