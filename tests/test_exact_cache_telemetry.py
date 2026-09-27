"""Focused telemetry tests for ExactConditioningCache lookup/store
observational decomposition.  Telemetry must not change bytes, files,
locking, keys, durability, or commit behavior."""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import torch

from comfymodal_runtime.clip_conditioning_cache import (
    ExactConditioningCache,
    conditioning_cache_key_summary,
    serialize_conditioning,
)


def _base_ctx(text: str = "a cat") -> dict[str, Any]:
    return {
        "request_id": "telemetry-req",
        "clip_identity": "clip.safetensors",
        "clip_type": "flux",
        "loader_class": "CLIPLoader",
        "filenames": ["clip.safetensors"],
        "weight_dtype": "bf16",
        "compute_dtype": "bfloat16",
        "torch_version": torch.__version__,
        "torch_num_threads": 4,
        "model_generation": "gen1",
        "workflow_hash": "wf1",
        "deployment_hash": "dep1",
        "custom_node_generation": "cn1",
        "production_options_hash": "po1",
        "tokenizer_identity": "tok1",
    }


def _entry(text: str = "a cat", role: str = "positive") -> dict[str, Any]:
    return {"text": text, "role": role, "node_class": "CLIPTextEncode", "prompt_input": "text"}


def _value(rows: int = 2048, dim: int = 2048) -> Any:
    return [[torch.randn(rows, dim), {"pooled": torch.randn(1, dim)}]]


def _new_cache(tmp: str, max_entries: int = 32) -> ExactConditioningCache:
    return ExactConditioningCache(root_dir=tmp, max_entries=max_entries, max_bytes=512 * 1024 * 1024)


def _entry_paths(cache: ExactConditioningCache, ctx: dict[str, Any], entry: dict[str, Any]):
    kh = conditioning_cache_key_summary(ctx, [entry])["key_hash"]
    header_path, data_path = cache._entry_paths(kh)
    return kh, header_path, data_path, cache._manifest_path


class TestStoreTelemetry:
    """Store diagnostics match real files, bytes identical, fields reconcile."""

    def test_store_bytes_match_actual_files_and_reconcile(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry = _base_ctx("seed"), _entry("seed")
            value = _value()
            assert cache.store_entry(ctx, entry, value) is True
            diag = cache.pop_store_diagnostics()

            kh, header_path, data_path, manifest_path = _entry_paths(cache, ctx, entry)
            assert os.path.isfile(header_path) and os.path.isfile(data_path)
            header_size = os.path.getsize(header_path)
            data_size = os.path.getsize(data_path)
            manifest_size = os.path.getsize(manifest_path)

            assert diag["store_calls"] == 1
            assert diag["stored_ok"] == 1
            assert diag["store_failed"] == 0
            assert diag["payload_bytes_written"] == data_size
            assert diag["header_bytes_written"] == header_size
            assert diag["header_bytes"] == header_size
            assert diag["manifest_bytes_written"] == manifest_size
            assert diag["serialized_payload_bytes"] == data_size
            assert diag["compression"] == "none"
            assert diag["safetensors"] is False
            assert diag["fsync_count"] >= 2

            with open(data_path, "rb") as f:
                _expected = serialize_conditioning(value)
                assert _expected is not None
                assert f.read() == _expected[1]

            assert diag["total_ms"] >= 0
            assert abs(diag["total_ms"] - diag["measured_children_ms"] - diag["residual_ms"]) <= 0.01
            assert diag["serialize_ms"] >= 0
            assert diag["materialize_bytes"] == data_size
            assert diag["checksum_ms"] >= 0
            assert diag["key_build_digest_ms"] >= 0
            assert diag["lock_wait_ms"] >= 0
            assert diag["lock_held_ms"] >= 0
            assert diag["data_write_ms"] >= 0
            assert diag["manifest_read_ms"] >= 0
            assert diag["manifest_write_ms"] >= 0
            assert diag["commit_ms"] >= 0

    def test_files_identical_with_and_without_telemetry(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            cache_telem = _new_cache(t1)
            cache_plain = _new_cache(t2)
            ctx, entry, value = _base_ctx("same"), _entry("same"), _value()
            assert cache_telem.store_entry(ctx, entry, value) is True
            cache_telem.pop_store_diagnostics()
            assert cache_plain.store_entry(ctx, entry, value) is True

            _, h1, d1, m1 = _entry_paths(cache_telem, ctx, entry)
            _, h2, d2, m2 = _entry_paths(cache_plain, ctx, entry)

            def _strip_created_at(text: bytes) -> bytes:
                obj = json.loads(text)
                for field in ("created_at",):
                    obj.pop(field, None)
                for e in obj.get("entries", []):
                    e.pop("created_at", None)
                return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

            with open(d1, "rb") as f1, open(d2, "rb") as f2:
                assert f1.read() == f2.read()
            with open(h1, "rb") as f1, open(h2, "rb") as f2:
                assert _strip_created_at(f1.read()) == _strip_created_at(f2.read())
            with open(m1, "rb") as f1, open(m2, "rb") as f2:
                assert _strip_created_at(f1.read()) == _strip_created_at(f2.read())


class TestLookupTelemetry:
    """Miss reads zero entry bytes (manifest only); hit reads exact files."""

    def test_miss_reads_zero_entry_bytes_and_no_extra_ops(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            assert cache.store_entry(_base_ctx("seed"), _entry("seed"), _value()) is True
            cache.pop_store_diagnostics()
            entries_before = sorted(os.listdir(cache._entries_dir))
            manifest_before = open(cache._manifest_path, encoding="utf-8").read()

            hits, misses, hc, mc = cache.lookup_many(_base_ctx("other"), [_entry("other")])
            assert hc == 0 and mc == 1 and hits == {} and len(misses) == 1
            diag = cache.latest_lookup_diagnostics()

            assert diag["hit_count"] == 0
            assert diag["miss_count"] == 1
            assert diag["header_bytes_read"] == 0
            assert diag["data_bytes_read"] == 0
            assert diag["manifest_read_bytes"] > 0
            assert diag["manifest_entries"] == 1
            assert diag["lru_touch_ms"] == 0.0
            assert diag["total_ms"] >= 0
            assert abs(diag["total_ms"] - diag["measured_children_ms"] - diag["residual_ms"]) <= 0.01

            assert sorted(os.listdir(cache._entries_dir)) == entries_before
            assert open(cache._manifest_path, encoding="utf-8").read() == manifest_before

    def test_hit_reads_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("hit"), _entry("hit"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.pop_store_diagnostics()
            _, header_path, data_path, _ = _entry_paths(cache, ctx, entry)

            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert hc == 1 and mc == 0
            diag = cache.latest_lookup_diagnostics()
            assert diag["hit_count"] == 1
            assert diag["header_bytes_read"] == os.path.getsize(header_path)
            assert diag["data_bytes_read"] == os.path.getsize(data_path)
            assert diag["manifest_read_bytes"] > 0
            assert diag["lru_touch_ms"] > 0 or diag["manifest_entries"] >= 1


class TestTelemetryIsolation:
    """Per-thread diagnostics never cross-contaminate concurrent stores."""

    def test_concurrent_store_diagnostics_isolated_per_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, max_entries=64)

            def worker(text: str):
                ok = cache.store_entry(_base_ctx(text), _entry(text), _value(512, 512))
                diag = cache.pop_store_diagnostics()
                return ok, diag

            with ThreadPoolExecutor(max_workers=4) as ex:
                results = list(ex.map(worker, ["t1", "t2", "t3", "t4"]))

            for ok, diag in results:
                assert ok is True
                assert diag["store_calls"] == 1
                assert diag["stored_ok"] == 1
                assert diag["store_failed"] == 0
                assert diag["serialized_payload_bytes"] > 0
                assert diag["total_ms"] >= 0

    def test_lookup_and_store_diag_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("sep"), _entry("sep"), _value(512, 512)
            cache.store_entry(ctx, entry, value)
            cache.lookup_many(ctx, [entry])
            store_diag = cache.pop_store_diagnostics()
            lookup_diag = cache.latest_lookup_diagnostics()
            assert "manifest_read_ms" in store_diag
            assert "store_calls" in store_diag
            assert "entry_lookup_ms" in lookup_diag
            assert "lock_wait_ms" in lookup_diag
            assert "store_calls" not in lookup_diag
            assert "manifest_entries" in lookup_diag
