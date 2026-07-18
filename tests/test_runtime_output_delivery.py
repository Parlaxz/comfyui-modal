"""Focused tests for output_delivery.py strategy chain."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comfymodal_runtime.output_delivery import (
    Attempt,
    ConversionMeta,
    OutputItem,
    DirectOutputSink,
    HistoryOutputCollector,
    RequestBoundFilesystemCollector,
    SubprocessOutputCollector,
    run_strategy_chain,
    build_default_chain,
    _make_conversion_meta,
    _hash_raw_bytes,
)
from comfymodal_runtime.contracts import OutputStrategy


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


def _entry(
    filename: str,
    payload: bytes,
    *,
    node_id: str = "107",
    output_key: str = "images",
    comparison_side: str = "",
    output_index: int = 0,
    mime_type: str = "image/png",
    file_ext: str = ".png",
    fmt: str = "png",
    raw_key: str = "raw_bytes",
) -> dict:
    return {
        "filename": filename,
        raw_key: payload,
        "node_id": node_id,
        "output_key": output_key,
        "comparison_side": comparison_side,
        "output_index": output_index,
        "mime_type": mime_type,
        "file_ext": file_ext,
        "format": fmt,
        "width": 64,
        "height": 64,
    }


# ---------------------------------------------------------------------------
# ConversionMeta tests
# ---------------------------------------------------------------------------

class TestConversionMeta:
    def test_make_conversion_meta_counts_bytes_correctly(self):
        raw = b"hello-image-bytes"
        meta = _make_conversion_meta(raw, "original", "image/png", ".png", 1.5)
        assert meta.raw_bytes == len(raw)
        assert meta.base64_bytes == len(base64.b64encode(raw))
        json_result = json.dumps({"data": base64.b64encode(raw).decode("ascii")}, separators=(",", ":")).encode("utf-8")
        assert meta.json_result_bytes == len(json_result)
        assert meta.hash_of_raw == hashlib.sha256(raw).hexdigest()
        assert meta.conversion_time_ms == 1.5

    def test_png_webp_jpeg_byte_accounting(self):
        for ext, mime, fmt in [(".png", "image/png", "png"), (".webp", "image/webp", "webp"), (".jpg", "image/jpeg", "jpeg")]:
            raw = _png_bytes()
            if ext == ".webp":
                raw = b"RIFF\x00\x00\x00\x00WEBP" + raw[12:]
            elif ext == ".jpg":
                raw = b"\xff\xd8\xff\xe0" + raw[4:]
            meta = _make_conversion_meta(raw, fmt, mime, ext, 2.0)
            b64 = base64.b64encode(raw)
            assert meta.raw_bytes == len(raw)
            assert meta.base64_bytes == len(b64)
            assert meta.mime_type == mime
            assert meta.file_ext == ext
            assert meta.format == fmt

    def test_hash_before_base64(self):
        raw = b"raw-converted-bytes"
        meta = _make_conversion_meta(raw, "original", "image/png", ".png", 0)
        b64_data = base64.b64encode(raw).decode("ascii")
        # The hash should be of the raw bytes, not the base64
        assert meta.hash_of_raw == hashlib.sha256(raw).hexdigest()
        assert meta.hash_of_raw != hashlib.sha256(b64_data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# DirectOutputSink tests
# ---------------------------------------------------------------------------

class TestDirectOutputSink:
    def test_collects_live_flat_registry_shape(self):
        registry = {
            "107": [
                _entry(
                    "out.png",
                    _png_bytes(0, 255, 0),
                    node_id="107",
                    output_key="b_images",
                    comparison_side="b",
                ),
            ],
        }
        attempt = DirectOutputSink.from_registry(registry).collect(
            prompt_id="p1", output_node_ids=("107",)
        )
        assert attempt.success
        assert attempt.total_items == 1
        assert attempt.items[0].output_key == "b_images"
        assert attempt.items[0].comparison_side == "b"

    def test_collect_single_node_output(self):
        registry = {
            "107": {
                "images": [
                    _entry("out.png", _png_bytes(255, 0, 0), node_id="107"),
                ],
            },
        }
        sink = DirectOutputSink(registry=registry)
        attempt = sink.collect(prompt_id="p1", output_node_ids=("107",))
        assert attempt.success
        assert attempt.total_items == 1
        assert attempt.items[0].node_id == "107"
        assert attempt.items[0].raw_bytes == registry["107"]["images"][0]["raw_bytes"]

    def test_collect_empty_registry(self):
        sink = DirectOutputSink(registry={})
        attempt = sink.collect(prompt_id="p1", output_node_ids=("107",))
        assert not attempt.success
        assert attempt.total_items == 0

    def test_filter_by_output_node_ids(self):
        registry = {
            "107": {"images": [_entry("a.png", b"data-a", node_id="107")]},
            "108": {"images": [_entry("b.png", b"data-b", node_id="108")]},
        }
        sink = DirectOutputSink(registry=registry)
        attempt = sink.collect(prompt_id="p1", output_node_ids=("107",))
        assert attempt.total_items == 1
        assert attempt.items[0].node_id == "107"

    def test_image_comparer_a_b(self):
        a_bytes = _png_bytes(255, 0, 0)
        b_bytes = _png_bytes(0, 255, 0)
        registry = {
            "107": {
                "a_images": [
                    _entry("compare_a.png", a_bytes, node_id="107", output_key="a_images", comparison_side="a"),
                ],
                "b_images": [
                    _entry("compare_b.png", b_bytes, node_id="107", output_key="b_images", comparison_side="b"),
                ],
            },
        }
        sink = DirectOutputSink(registry=registry)
        attempt = sink.collect(prompt_id="p1", output_node_ids=("107",))
        assert attempt.total_items == 2
        keys = {item.output_key for item in attempt.items}
        assert keys == {"a_images", "b_images"}
        sides = {item.comparison_side for item in attempt.items}
        assert sides == {"a", "b"}

    def test_multiple_output_nodes(self):
        registry = {
            "107": {"images": [_entry("a.png", b"data-a", node_id="107")]},
            "108": {"images": [_entry("b.png", b"data-b", node_id="108")]},
        }
        sink = DirectOutputSink(registry=registry)
        attempt = sink.collect(prompt_id="p1", output_node_ids=())
        assert attempt.total_items == 2
        assert len({i.node_id for i in attempt.items}) == 2

    def test_animated_video_output(self):
        registry = {
            "200": {
                "gifs": [
                    _entry("anim.gif", b"gif-bytes", node_id="200", output_key="gifs", mime_type="image/gif", file_ext=".gif"),
                ],
            },
        }
        sink = DirectOutputSink(registry=registry)
        attempt = sink.collect(prompt_id="p1", output_node_ids=("200",))
        assert attempt.total_items == 1
        assert attempt.items[0].animated is False  # animated is False unless explicit

    def test_metrics_recorded(self):
        raw = _png_bytes()
        registry = {
            "107": {"images": [_entry("out.png", raw, node_id="107")]},
        }
        sink = DirectOutputSink(registry=registry)
        attempt = sink.collect(prompt_id="p1", output_node_ids=("107",))
        assert attempt.total_raw_bytes == len(raw)
        assert attempt.total_base64_bytes > 0
        assert attempt.metrics.get("node_count") == 1

    def test_conversion_meta_preserved(self):
        raw = _png_bytes()
        meta = _make_conversion_meta(raw, "webp_lossless", "image/webp", ".webp", 3.0)
        registry = {
            "107": {
                "images": [
                    {
                        "filename": "out.webp",
                        "raw_bytes": raw,
                        "conversion_meta": meta,
                        "node_id": "107",
                        "output_key": "images",
                        "mime_type": "image/webp",
                        "file_ext": ".webp",
                        "format": "webp_lossless",
                        "width": 64,
                        "height": 64,
                        "output_index": 0,
                    },
                ],
            },
        }
        sink = DirectOutputSink(registry=registry)
        attempt = sink.collect(prompt_id="p1", output_node_ids=("107",))
        assert attempt.total_items == 1
        item = attempt.items[0]
        assert item.conversion_meta is not None
        cm = item.conversion_meta
        assert cm.format == "webp_lossless"
        assert cm.conversion_time_ms == 3.0


# ---------------------------------------------------------------------------
# HistoryOutputCollector tests
# ---------------------------------------------------------------------------

class TestHistoryOutputCollector:
    def test_collect_from_history(self):
        history = {
            "prompt-1": {
                "outputs": {
                    "107": {
                        "images": [
                            {
                                "filename": "out.png",
                                "data": base64.b64encode(_png_bytes()).decode("ascii"),
                                "type": "output",
                            },
                        ],
                    },
                },
            },
        }
        collector = HistoryOutputCollector(history=history)
        attempt = collector.collect(prompt_id="prompt-1", output_node_ids=("107",))
        assert attempt.success
        assert attempt.total_items == 1

    def test_empty_history(self):
        collector = HistoryOutputCollector(history={})
        attempt = collector.collect(prompt_id="missing", output_node_ids=())
        assert not attempt.success
        assert attempt.total_items == 0

    def test_with_materials_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "out.png")
            Path(fpath).write_bytes(_png_bytes())
            history = {
                "p1": {
                    "outputs": {
                        "7": {
                            "images": [
                                {"filename": "out.png", "type": "output"},
                            ],
                        },
                    },
                },
            }
            collector = HistoryOutputCollector(history=history)
            attempt = collector.collect(prompt_id="p1", output_node_ids=("7",), materials_dir=tmp)
            assert attempt.success
            assert attempt.items[0].path == fpath

    def test_multi_output_node_history(self):
        history = {
            "p1": {
                "outputs": {
                    "7": {"images": [{"filename": "a.png", "type": "output"}]},
                    "8": {"images": [{"filename": "b.png", "type": "output"}]},
                },
            },
        }
        collector = HistoryOutputCollector(history=history)
        attempt = collector.collect(prompt_id="p1", output_node_ids=())
        assert attempt.total_items == 2


# ---------------------------------------------------------------------------
# RequestBoundFilesystemCollector tests (constrained fallback)
# ---------------------------------------------------------------------------

class TestRequestBoundFilesystemCollector:
    def test_constrained_fallback_by_prompt_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = _png_bytes()
            Path(os.path.join(tmp, "output_prompt-123_0.png")).write_bytes(data)
            Path(os.path.join(tmp, "output_other_0.png")).write_bytes(data)  # no match

            collector = RequestBoundFilesystemCollector(materials_dir=tmp)
            attempt = collector.collect(prompt_id="prompt-123", output_node_ids=())
            assert attempt.success
            assert attempt.total_items == 1
            assert "prompt-123" in attempt.items[0].filename

    def test_constrained_by_node_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "node_107_out.png")).write_bytes(b"data")
            Path(os.path.join(tmp, "other.png")).write_bytes(b"data")

            collector = RequestBoundFilesystemCollector(materials_dir=tmp)
            attempt = collector.collect(prompt_id="", output_node_ids=("107",))
            assert attempt.success
            assert attempt.total_items == 1

    def test_no_tokens_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "some_file.png")).write_bytes(b"data")
            collector = RequestBoundFilesystemCollector(materials_dir=tmp)
            attempt = collector.collect(prompt_id="", output_node_ids=())
            assert not attempt.success
            assert "no search tokens" in attempt.error

    def test_request_start_boundary_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_file = os.path.join(tmp, "old_output.png")
            new_file = os.path.join(tmp, "new_prompt-1_output.png")
            Path(old_file).write_bytes(b"old-data")
            time.sleep(0.1)
            boundary = time.time()
            time.sleep(0.1)
            Path(new_file).write_bytes(b"new-data")

            collector = RequestBoundFilesystemCollector(materials_dir=tmp)
            attempt = collector.collect(
                prompt_id="prompt-1",
                output_node_ids=(),
                request_start_boundary=boundary,
            )
            assert attempt.total_items == 1
            assert "new" in attempt.items[0].filename

    def test_missing_materials_dir(self):
        collector = RequestBoundFilesystemCollector(materials_dir="/nonexistent/path")
        attempt = collector.collect(prompt_id="p1", output_node_ids=())
        assert not attempt.success
        assert "not available" in attempt.error

    def test_no_unrestricted_scan(self):
        """Verify we never scan without prompt_id or node_id tokens."""
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(5):
                Path(os.path.join(tmp, f"file_{i}.txt")).write_bytes(b"data")
            collector = RequestBoundFilesystemCollector(materials_dir=tmp)
            attempt = collector.collect(prompt_id="", output_node_ids=())
            assert not attempt.success
            assert "no search tokens" in attempt.error


# ---------------------------------------------------------------------------
# SubprocessOutputCollector tests
# ---------------------------------------------------------------------------

class TestSubprocessOutputCollector:
    def test_collect_from_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "stdout_p1.txt")).write_bytes(b"output data")
            collector = SubprocessOutputCollector(subprocess_output_dir=tmp)
            attempt = collector.collect(prompt_id="p1", output_node_ids=())
            assert attempt.success
            assert attempt.total_items >= 1

    def test_empty_dir(self):
        """Empty dir with constraint token returns failure (no files matched)."""
        with tempfile.TemporaryDirectory() as tmp:
            collector = SubprocessOutputCollector(subprocess_output_dir=tmp)
            attempt = collector.collect(prompt_id="p1", output_node_ids=())
            assert not attempt.success

    def test_no_tokens_fails_closed(self):
        """No prompt_id or output_node_ids must fail closed, never scan all files."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "some_file.txt")).write_bytes(b"data")
            collector = SubprocessOutputCollector(subprocess_output_dir=tmp)
            attempt = collector.collect(prompt_id="", output_node_ids=())
            assert not attempt.success
            assert "no constraint tokens" in attempt.error
            assert attempt.total_items == 0

    def test_no_tokens_does_not_scan_files(self):
        """Verify no-token failure prevents any file scan."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "visible.txt")).write_bytes(b"sensitive")
            collector = SubprocessOutputCollector(subprocess_output_dir=tmp)
            attempt = collector.collect(prompt_id="", output_node_ids=())
            assert not attempt.success
            assert attempt.total_items == 0
            assert "no constraint tokens" in attempt.error


# ---------------------------------------------------------------------------
# Strategy chain runner tests
# ---------------------------------------------------------------------------

class TestRunStrategyChain:
    def test_runs_all_strategies(self):
        sink = DirectOutputSink(registry={})
        hist = HistoryOutputCollector(history={})
        results = run_strategy_chain([sink, hist], prompt_id="p1", output_node_ids=())
        assert len(results) == 2
        assert all(isinstance(r, Attempt) for r in results)

    def test_chain_with_filesystem_collector(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "node_107_p1.png")).write_bytes(_png_bytes())
            chain = [
                DirectOutputSink(registry={}),
                RequestBoundFilesystemCollector(materials_dir=tmp),
            ]
            results = run_strategy_chain(
                chain, prompt_id="p1", output_node_ids=("107",), materials_dir=tmp,
            )
            assert len(results) == 2
            # Second one (filesystem) should succeed
            assert results[1].success

    def test_strategy_exception_returns_failed_attempt(self):
        class BrokenStrategy(DirectOutputSink):
            NAME = "broken"
            def collect(self, *a, **kw):
                raise RuntimeError("crashed")

        results = run_strategy_chain([BrokenStrategy()], prompt_id="p1", output_node_ids=())
        assert len(results) == 1
        assert not results[0].success
        assert "RuntimeError" in results[0].error


# ---------------------------------------------------------------------------
# Build default chain test
# ---------------------------------------------------------------------------

class TestBuildDefaultChain:
    def test_default_chain_structure(self):
        chain = build_default_chain(
            registry={"107": {"images": []}},
            history={"p1": {"outputs": {}}},
            materials_dir="/tmp",
            subprocess_output_dir="/tmp",
        )
        assert len(chain) == 4
        assert isinstance(chain[0], DirectOutputSink)
        assert isinstance(chain[1], HistoryOutputCollector)
        assert isinstance(chain[2], RequestBoundFilesystemCollector)
        assert isinstance(chain[3], SubprocessOutputCollector)

    def test_default_chain_no_fs_fallbacks(self):
        chain = build_default_chain(registry={}, history={})
        assert len(chain) == 2
        assert isinstance(chain[0], DirectOutputSink)
        assert isinstance(chain[1], HistoryOutputCollector)


# ---------------------------------------------------------------------------
# OutputItem conversion meta test
# ---------------------------------------------------------------------------

class TestOutputItemConversion:
    def test_item_with_conversion_meta(self):
        raw = _png_bytes()
        meta = _make_conversion_meta(raw, "jpeg", "image/jpeg", ".jpg", 5.0)
        item = OutputItem(
            node_id="9",
            output_key="images",
            filename="test.jpg",
            raw_bytes=raw,
            base64_data=base64.b64encode(raw).decode("ascii"),
            mime_type="image/jpeg",
            file_ext=".jpg",
            conversion_meta=meta,
        )
        assert item.conversion_meta is not None
        assert item.conversion_meta.raw_bytes == len(raw)
        assert item.conversion_meta.format == "jpeg"

    def test_conversion_failure_fails_batch(self):
        """Conversion failure must not report success."""
        from comfymodal_runtime.result_delivery import ConversionFailedError
        raw = b"not-an-image"
        bad_converter = MagicMock(side_effect=ValueError("invalid image data"))
        from comfymodal_runtime.result_delivery import convert_output_items
        with pytest.raises(ConversionFailedError):
            convert_output_items(
                [OutputItem(node_id="9", output_key="images", raw_bytes=raw)],
                converter_fn=bad_converter,
            )
