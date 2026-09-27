"""Twelve proofs for Task 2: plan-time conditioning prefetch + in-memory cache.

Each test maps 1:1 to a Task-2 validation requirement using the REAL
``ExactConditioningCache`` (temp root, constructor injection):

  1. ``test_prefetched_exact_hit_served_from_memory``    — correct exact key is
     served from memory (manifest_memory_hit=1, payload_memory_hit=1) with
     values identical to a file-path hit.
  2. ``test_wrong_key_misses_and_memory_not_used``       — a different key never
     touches the memory entry (plain miss; no memory validation fallback).
  3. ``test_missing_payload_file_at_prefetch_falls_back``— payload files absent
     at prefetch time are skipped and fall back at demand.
  4. ``test_corrupt_payload_never_served``               — corrupt in-memory
     bytes fail validation (normal_lookup_fallback=1), never served, and the
     memory entry is discarded.
  5. ``test_schema_mismatch_falls_back``                 — header schema/format
     drift falls back at demand (never served).
  6. ``test_identity_mismatch_falls_back``               — canonical-key /
     model-identity mismatch (digest matches, components differ) falls back.
  7. ``test_manifest_served_from_memory_not_reread``     — fresh manifest is not
     re-read from disk (manifest_read_bytes == 0).
  8. ``test_payload_served_from_memory_after_files_deleted`` — payload bytes
     come from memory (hit even after entry files are removed).
  9. ``test_self_store_supersedes_prefetch``            — a self-store
     invalidates prefetched bytes; the newer value is served.
 10. ``test_prefetch_never_raises``                      — missing manifest,
     failing reload hook, and unusable context never raise.
 11. ``test_reconciliation_invariants_preserved``        — lookup_wall =
     children + residual; the new keys are NOT in the children sum.
 12. ``test_memory_hit_reports_file_sizes``              — header_bytes_read /
     data_bytes_read report the on-disk file sizes on a memory hit.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import types
from typing import Any
from unittest.mock import patch

import torch

import comfymodal_runtime.model_preload as mp

from comfymodal_runtime.clip_conditioning_cache import (
    ExactConditioningCache,
    _atomic_write,
    _atomic_write_text,
    _merge_entry_context,
    _model_identity_block,
    build_exact_key_components,
    conditioning_cache_key_summary,
    exact_key_digest,
    serialize_conditioning,
)


def _base_ctx(text: str = "a cat", *, workflow_hash: str = "wf1", **overrides) -> dict[str, Any]:
    ctx = {
        "request_id": "prefetch-req",
        "clip_identity": "clip.safetensors",
        "clip_type": "flux",
        "loader_class": "CLIPLoader",
        "filenames": ["clip.safetensors"],
        "weight_dtype": "bf16",
        "compute_dtype": "bfloat16",
        "torch_version": torch.__version__,
        "torch_num_threads": 4,
        "model_generation": "gen1",
        "workflow_hash": workflow_hash,
        "deployment_hash": "dep1",
        "custom_node_generation": "cn1",
        "production_options_hash": "po1",
        "tokenizer_identity": "tok1",
    }
    ctx.update(overrides)
    return ctx


def _entry(text: str = "a cat", role: str = "positive") -> dict[str, Any]:
    return {"text": text, "role": role, "node_class": "CLIPTextEncode", "prompt_input": "text"}


def _value(rows: int = 64, dim: int = 64) -> Any:
    return [[torch.randn(rows, dim), {"pooled": torch.randn(1, dim)}]]


def _new_cache(tmp: str, *, mounted: bool = True, max_entries: int = 64) -> ExactConditioningCache:
    return ExactConditioningCache(
        root_dir=tmp, max_entries=max_entries, max_bytes=512 * 1024 * 1024, mounted=mounted
    )


def _entry_paths(cache: ExactConditioningCache, ctx: dict[str, Any], entry: dict[str, Any]):
    kh = conditioning_cache_key_summary(ctx, [entry])["key_hash"]
    header_path, data_path = cache._entry_paths(kh)
    return kh, header_path, data_path, cache._manifest_path


def _cond_and_pooled(value: Any) -> tuple[torch.Tensor, torch.Tensor]:
    """Return ``(cond_tensor, pooled_tensor)`` from a deserialized value."""
    assert isinstance(value, list) and value, "empty conditioning value"
    cond, meta = value[0]
    assert isinstance(cond, torch.Tensor)
    pooled = meta.get("pooled")
    assert pooled is not None and isinstance(pooled, torch.Tensor)
    return cond, pooled


def _wait_until(predicate, timeout: float = 10.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _seed_header(
    cache: ExactConditioningCache,
    digest: str,
    components: dict[str, Any],
    *,
    schema_version: int | None = None,
    format_version: int | None = None,
    key_hash: str | None = None,
) -> None:
    """Directly write a (possibly mutated) header + data blob for *digest*."""
    header, data = serialize_conditioning(_value())
    assert header is not None
    header["key_hash"] = key_hash if key_hash is not None else digest
    header["key_components"] = components
    header["model_identity"] = _model_identity_block(components)
    header["created_at"] = time.time()
    if schema_version is not None:
        header["schema_version"] = schema_version
    if format_version is not None:
        header["format_version"] = format_version
    hp, dp = cache._entry_paths(digest)
    _atomic_write(dp, data)
    _atomic_write_text(hp, json.dumps(header, sort_keys=True, separators=(",", ":")))


class TestPrefetchMemoryHit:
    """Exact-key memory hits: values identical to file-path hits + diag flags."""

    def test_prefetched_exact_hit_served_from_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("mem-hit"), _entry("mem-hit"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            # 1) File-path hit FIRST, then prefetch, then memory hit.
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            file_cond, file_pooled = _cond_and_pooled(hits[0])
            diag_pre = cache.latest_lookup_diagnostics()
            assert diag_pre.get("manifest_memory_hit") == 0
            assert diag_pre.get("payload_memory_hit") == 0

            pdiag = cache.prefetch_entries(ctx, [entry], request_id="prefetch-req")
            assert pdiag["requested"] == 1
            assert pdiag["loaded"] == 1, pdiag
            assert pdiag["failures"] == 0, pdiag
            assert pdiag["source"] == "full", pdiag

            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            mem_cond, mem_pooled = _cond_and_pooled(hits[0])
            assert torch.equal(mem_cond, file_cond), "memory hit tensor mismatch"
            assert torch.equal(mem_pooled, file_pooled), "memory hit pooled mismatch"
            diag = cache.latest_lookup_diagnostics()
            assert diag["manifest_memory_hit"] == 1, diag
            assert diag["payload_memory_hit"] == 1, diag
            assert diag["normal_lookup_fallback"] == 0, diag
            assert diag["prefetch_overlap_ms"] >= 0, diag
            assert diag["prefetch_requested"] == 1, diag
            assert diag["prefetch_source"] == "full", diag
            cache.flush(timeout=15.0)

    def test_wrong_key_misses_and_memory_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx_a, entry_a, value_a = _base_ctx("wrong-a"), _entry("wrong-a"), _value()
            assert cache.store_entry(ctx_a, entry_a, value_a) is True
            cache.flush(timeout=15.0)
            pdiag = cache.prefetch_entries(ctx_a, [entry_a])
            assert pdiag["loaded"] == 1, pdiag
            # A DIFFERENT key (different workflow hash -> different digest) must
            # miss without touching the memory entry.
            ctx_b = _base_ctx("wrong-a", workflow_hash="wf-other")
            hits, misses, hc, mc = cache.lookup_many(ctx_b, [entry_a])
            assert (hc, mc) == (0, 1)
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 0, diag
            assert diag["normal_lookup_fallback"] == 0, diag
            # The correctly-keyed entry still serves from memory.
            hits, misses, hc, mc = cache.lookup_many(ctx_a, [entry_a])
            assert (hc, mc) == (1, 0)
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 1, diag
            cache.flush(timeout=15.0)


class TestPrefetchFallback:
    """Every failure mode falls back to the file path (fail closed)."""

    def test_missing_payload_file_at_prefetch_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("gone-file"), _entry("gone-file"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            kh, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            os.remove(data_path)  # payload file gone BEFORE prefetch
            pdiag = cache.prefetch_entries(ctx, [entry])
            assert pdiag["loaded"] == 0, pdiag
            assert pdiag["failures"] == 0, pdiag
            # Demand-time falls back to the file path (file gone -> miss).
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (0, 1)
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 0, diag
            assert diag["normal_lookup_fallback"] == 0, diag
            cache.flush(timeout=15.0)

    def test_corrupt_payload_never_served(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("corrupt"), _entry("corrupt"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            kh, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            # Same-length corruption keeps the byte_length check green at
            # prefetch; the checksums must catch it at demand time.  Capture
            # the size BEFORE opening wb (the open truncates the file).
            data_size = os.path.getsize(data_path)
            with open(data_path, "wb") as f:
                f.write(b"\x00" * data_size)
            assert os.path.getsize(data_path) == data_size
            pdiag = cache.prefetch_entries(ctx, [entry])
            assert pdiag["loaded"] == 1, pdiag  # corrupt bytes ARE in memory
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (0, 1), "corrupt payload must never be served"
            diag = cache.latest_lookup_diagnostics()
            assert diag["normal_lookup_fallback"] == 1, diag
            assert diag["payload_memory_hit"] == 0, diag
            # The failed memory entry is discarded after the lookup.
            assert kh not in cache._mem_payloads, "failed memory entry not discarded"
            cache.flush(timeout=15.0)

    def test_schema_mismatch_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("schema"), _entry("schema"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            kh, _, _, _ = _entry_paths(cache, ctx, entry)
            merged = _merge_entry_context(ctx, entry)
            components = build_exact_key_components(merged)
            _seed_header(cache, kh, components, schema_version=999)
            pdiag = cache.prefetch_entries(ctx, [entry])
            assert pdiag["loaded"] == 0, pdiag  # schema check rejects at prefetch
            assert pdiag["failures"] >= 1, pdiag
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (0, 1), "schema-mismatched entry must never hit"
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 0, diag
            cache.flush(timeout=15.0)

    def test_identity_mismatch_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx_a, entry_a, value_a = _base_ctx("identity"), _entry("identity"), _value()
            assert cache.store_entry(ctx_a, entry_a, value_a) is True
            cache.flush(timeout=15.0)
            kh, _, _, _ = _entry_paths(cache, ctx_a, entry_a)
            # Header whose key_hash matches digest_A but whose canonical key
            # components belong to a DIFFERENT context (workflow_hash drift).
            ctx_b = _base_ctx("identity", workflow_hash="wf-drifted")
            merged_b = _merge_entry_context(ctx_b, entry_a)
            components_b = build_exact_key_components(merged_b)
            _seed_header(cache, kh, components_b, key_hash=kh)
            # Prefetch: header-level checks pass (key_hash matches) -> loaded.
            pdiag = cache.prefetch_entries(ctx_a, [entry_a])
            assert pdiag["loaded"] == 1, pdiag
            # Demand: full canonical-key equality fails -> memory fallback ->
            # file path also fails -> miss.
            hits, misses, hc, mc = cache.lookup_many(ctx_a, [entry_a])
            assert (hc, mc) == (0, 1), "identity-drifted entry must never hit"
            diag = cache.latest_lookup_diagnostics()
            assert diag["normal_lookup_fallback"] == 1, diag
            assert diag["payload_memory_hit"] == 0, diag
            cache.flush(timeout=15.0)


class TestMemoryCacheBehavior:
    """Manifest + payload memory caches are actually used and stay correct."""

    def test_manifest_served_from_memory_not_reread(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("mem-manifest"), _entry("mem-manifest"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            cache.prefetch_entries(ctx, [entry])
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            diag = cache.latest_lookup_diagnostics()
            assert diag["manifest_memory_hit"] == 1, diag
            assert diag["manifest_read_bytes"] == 0, diag  # NOT re-read from disk
            assert diag["manifest_read_ms"] == 0.0, diag
            cache.flush(timeout=15.0)

    def test_payload_served_from_memory_after_files_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("mem-payload"), _entry("mem-payload"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            cache.prefetch_entries(ctx, [entry])
            _, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            os.remove(header_path)
            os.remove(data_path)
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0), "payload must be served from memory"
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 1, diag
            cond, pooled = _cond_and_pooled(hits[0])
            assert torch.equal(cond, value[0][0])
            assert torch.equal(pooled, value[0][1]["pooled"])
            cache.flush(timeout=15.0)

    def test_self_store_supersedes_prefetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry = _base_ctx("supersede"), _entry("supersede")
            value1 = _value()
            assert cache.store_entry(ctx, entry, value1) is True
            # Wait for the worker to persist value1 WITHOUT flush() — flush is
            # terminal (closes the queue), so the second store below must run
            # on an open cache.
            assert _wait_until(lambda: cache._worker_diag.get("persisted", 0) >= 1)
            cache.prefetch_entries(ctx, [entry])
            hits, _, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            assert torch.equal(hits[0][0][0], value1[0][0]), "prefetch hit != value1"
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 1, diag
            # A NEW self-store of the same key with different bytes supersedes
            # the prefetched value: enqueue-time invalidation + the rewritten
            # manifest force the file path, which serves the NEW value.
            value2 = _value()
            assert cache.store_entry(ctx, entry, value2) is True
            assert _wait_until(lambda: cache._worker_diag.get("persisted", 0) >= 2)
            hits, _, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            cond, pooled = _cond_and_pooled(hits[0])
            assert torch.equal(cond, value2[0][0]), "self-store did not supersede prefetch"
            assert not torch.equal(cond, value1[0][0])
            diag = cache.latest_lookup_diagnostics()
            assert diag["manifest_memory_hit"] == 0, diag
            assert diag["payload_memory_hit"] == 0, diag
            cache.flush(timeout=15.0)

    def test_prefetch_never_raises(self):
        # (a) Missing manifest / empty volume -> no raise, fail-open diag.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            pdiag = cache.prefetch_entries(_base_ctx("nope"), [_entry("nope")])
            assert isinstance(pdiag, dict)
            assert pdiag["source"] == "manifest_missing", pdiag
            assert pdiag["requested"] == 1, pdiag
        # (b) Failing reload hook -> swallowed, prefetch still returns.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)

            def _boom():
                raise RuntimeError("simulated prefetch reload failure")

            cache.set_reload_hook(_boom)
            pdiag = cache.prefetch_entries(_base_ctx("r"), [_entry("r")])
            assert isinstance(pdiag, dict)
        # (c) Unusable base context (missing required key fields) -> counted,
        #     never raised.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            assert cache.store_entry(_base_ctx("ok"), _entry("ok"), _value()) is True
            cache.flush(timeout=15.0)
            pdiag = cache.prefetch_entries({}, [_entry("ok")])
            assert isinstance(pdiag, dict)
            assert pdiag["failures"] >= 1, pdiag
            cache.flush(timeout=15.0)


class TestDiagInvariants:
    """Reconciliation math is untouched and bytes-served reports file sizes."""

    def test_reconciliation_invariants_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("reconcile"), _entry("reconcile"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            cache.prefetch_entries(ctx, [entry])
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            diag = cache.latest_lookup_diagnostics()
            # The new prefetch/memory keys exist...
            for key in (
                "prefetch_requested",
                "prefetch_wall_ms",
                "prefetch_overlap_ms",
                "prefetch_source",
                "manifest_memory_hit",
                "payload_memory_hit",
                "normal_lookup_fallback",
            ):
                assert key in diag, f"missing diag key {key!r}"
            # ...and are NOT part of the measured-children sum.
            children = (
                diag["lock_wait_ms"]
                + diag["volume_reload_ms"]
                + diag["manifest_read_ms"]
                + diag["key_build_digest_ms"]
                + diag["entry_lookup_ms"]
                + diag["lru_touch_ms"]
            )
            assert round(children, 3) == diag["measured_children_ms"], diag
            assert round(diag["measured_children_ms"] + diag["residual_ms"], 3) == round(
                diag["total_ms"], 3
            ), diag
            cache.flush(timeout=15.0)

    def test_memory_hit_reports_file_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("sizes"), _entry("sizes"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            _, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            cache.prefetch_entries(ctx, [entry])
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 1
            assert diag["header_bytes_read"] == os.path.getsize(header_path), diag
            assert diag["data_bytes_read"] == os.path.getsize(data_path), diag
            cache.flush(timeout=15.0)

    def test_prefetch_reload_not_counted_in_lookup_diag(self):
        reloads: list[int] = []

        def reload_hook():
            reloads.append(1)

        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            cache.set_reload_hook(reload_hook)
            ctx, entry, value = _base_ctx("noreload"), _entry("noreload"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            pdiag = cache.prefetch_entries(ctx, [entry])
            assert isinstance(pdiag, dict)
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            diag = cache.latest_lookup_diagnostics()
            # The lookup path STILL performs zero reloads: the prefetch reload
            # is tracked only in the prefetch diagnostics.
            assert abs(diag.get("volume_reload_ms", 1.0)) < 0.001, diag
            cache.flush(timeout=15.0)


class TestMaybePrefetchConditioning:
    """The plan-receipt launch function (model_preload) derives a plan-time
    context and wires the prefetch into the real cache."""

    def _fake_plan(self):
        workflow = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "plan cat"},
                "_meta": {"title": "positive"},
            },
        }
        return types.SimpleNamespace(
            workflow=workflow,
            workflow_hash="planwf",
            source_workflow_hash="planwf",
            deployment_identity={
                "deployment_combined_hash": "dep1",
                "custom_nodes_generation": "cn1",
            },
            execution_options=types.SimpleNamespace(
                to_dict=lambda: {"production_enabled": True, "result_route": "test"}
            ),
            model_stack={
                "loaders": {
                    "clip": [{
                        "loader_class": "CLIPLoader",
                        "clip_name": "clip.safetensors",
                        "weight_dtype": "bf16",
                    }]
                }
            },
            prompt_bundle={
                "encodes": [{
                    "node_id": "2",
                    "node_class": "CLIPTextEncode",
                    "prompt_input": "text",
                    "role": "positive",
                    "text": "plan cat",
                }]
            },
        )

    def test_disabled_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            with patch.object(mp, "env_flag", return_value=False), patch.object(
                mp, "get_exact_conditioning_cache", return_value=cache
            ):
                diag = mp.maybe_prefetch_conditioning(self._fake_plan(), request_id="t")
            assert diag == {}

    def _plan_without_loader(self):
        """A plan whose workflow has no CLIP loader -> plan-time context is
        unusable (clip_identity empty) -> key_build_failed evidence."""
        return types.SimpleNamespace(
            workflow={"2": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}}},
            workflow_hash="planwf",
            source_workflow_hash="planwf",
            deployment_identity={},
            execution_options=types.SimpleNamespace(to_dict=lambda: {"a": 1}),
            model_stack={},
            prompt_bundle={"encodes": [{"text": "x", "role": "positive"}]},
        )

    def _plan_workflow_only(self):
        """A raw-source-workflow-style plan: CLIPLoader node present, no
        model stack and no prompt bundle — the identity must come from the
        workflow node (derive_model_key and/or the node fallback)."""
        return types.SimpleNamespace(
            workflow={
                "1": {
                    "class_type": "CLIPLoader",
                    "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
                },
                "2": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": "wf cat"},
                    "_meta": {"title": "positive"},
                },
            },
            workflow_hash="wfonlwf",
            source_workflow_hash="wfonlwf",
            deployment_identity={
                "deployment_combined_hash": "dep1",
                "custom_nodes_generation": "cn1",
            },
            execution_options=types.SimpleNamespace(to_dict=lambda: {"a": 1}),
            model_stack={},
            prompt_bundle={},
        )

    def _plan_with_weight_dtype(self, *, source: str, value: str = "bf16"):
        """A plan that carries ``weight_dtype`` in exactly ONE of the three
        plan-time sources: ``workflow`` (CLIPLoader node input),
        ``prompt_bundle`` (per-entry encodes field), or ``model_stack``
        (loader spec field)."""
        workflow = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "wd cat"},
                "_meta": {"title": "positive"},
            },
        }
        if source == "workflow":
            workflow["1"]["inputs"]["weight_dtype"] = value
        prompt_bundle: dict[str, Any] = {}
        model_stack: dict[str, Any] = {}
        if source == "prompt_bundle":
            prompt_bundle = {
                "encodes": [{
                    "node_id": "2",
                    "node_class": "CLIPTextEncode",
                    "prompt_input": "text",
                    "role": "positive",
                    "text": "wd cat",
                    "loader_class": "CLIPLoader",
                    "clip_type": "flux",
                    "filenames": ["clip.safetensors"],
                    "weight_dtype": value,
                }]
            }
        elif source == "model_stack":
            model_stack = {
                "loaders": {
                    "clip": [{
                        "loader_class": "CLIPLoader",
                        "clip_name": "clip.safetensors",
                        "weight_dtype": value,
                    }]
                }
            }
        return types.SimpleNamespace(
            workflow=workflow,
            workflow_hash="wdplanwf",
            source_workflow_hash="wdplanwf",
            deployment_identity={
                "deployment_combined_hash": "dep1",
                "custom_nodes_generation": "cn1",
            },
            execution_options=types.SimpleNamespace(to_dict=lambda: {"a": 1}),
            model_stack=model_stack,
            prompt_bundle=prompt_bundle,
        )

    def _plan_no_weight_dtype(self):
        """Mirrors the RUN-3 benchmark workload: CLIPLoader node with
        clip_name/device/type but NO weight_dtype input (verified against
        the compiled workflow), so plan-time weight_dtype stays ""."""
        return types.SimpleNamespace(
            workflow={
                "62": {
                    "class_type": "CLIPLoader",
                    "inputs": {
                        "clip_name": "qwen_3_4b.safetensors",
                        "device": "default",
                        "type": "lumina2",
                    },
                },
                "67": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": "warrior"},
                    "_meta": {"title": "positive"},
                },
            },
            workflow_hash="run3wf",
            source_workflow_hash="run3wf",
            deployment_identity={
                "deployment_combined_hash": "9e99140736d5fec1",
                "custom_nodes_generation": "cn1",
            },
            execution_options=types.SimpleNamespace(to_dict=lambda: {"a": 1}),
            model_stack={},
            prompt_bundle={},
        )

    def test_env_off_records_engagement_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            with patch.object(mp, "env_flag", return_value=False), patch.object(
                mp, "get_exact_conditioning_cache", return_value=cache
            ):
                diag = mp.maybe_prefetch_conditioning(self._fake_plan(), request_id="env-off-req")
            assert diag == {}
            ev = mp._prefetch_evidence_for("env-off-req")
            assert ev.get("prefetch_requested") == 1, ev
            assert ev.get("prefetch_source") == "none", ev
            assert ev.get("prefetch_reason") == "env_off", ev

    def test_cache_off_records_engagement_evidence(self):
        with patch.object(mp, "env_flag", return_value=True), patch.object(
            mp, "get_exact_conditioning_cache", return_value=None
        ):
            diag = mp.maybe_prefetch_conditioning(self._fake_plan(), request_id="co-req")
        assert diag == {}
        ev = mp._prefetch_evidence_for("co-req")
        assert ev.get("prefetch_requested") == 1, ev
        assert ev.get("prefetch_source") == "none", ev
        assert ev.get("prefetch_reason") == "cache_off", ev

    def test_key_build_failed_records_engagement_evidence(self):
        # key_build_failed now fires ONLY when there is no workflow hash at
        # all (the relaxed gate proceeds on partial identity instead).
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            plan = self._plan_without_loader()
            plan.workflow_hash = ""
            plan.source_workflow_hash = ""
            with patch.object(mp, "env_flag", return_value=True), patch.object(
                mp, "get_exact_conditioning_cache", return_value=cache
            ):
                diag = mp.maybe_prefetch_conditioning(plan, request_id="kbf-req")
            assert diag == {}
            ev = mp._prefetch_evidence_for("kbf-req")
            assert ev.get("prefetch_requested") == 1, ev
            assert ev.get("prefetch_source") == "none", ev
            assert ev.get("prefetch_reason") == "key_build_failed", ev

    def test_partial_identity_proceeds_with_partial_evidence(self):
        # RUN-1 root cause: workflow_hash present but loader identity missing
        # used to kill the whole context.  Now the context PROCEEDS (the
        # manifest can still be prefetched) and the evidence records the
        # missing required fields as key_build_partial:<fields>.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            with patch.object(mp, "env_flag", return_value=True), patch.object(
                mp, "get_exact_conditioning_cache", return_value=cache
            ):
                pdiag = mp.maybe_prefetch_conditioning(
                    self._plan_without_loader(), request_id="partial-req"
                )
            assert isinstance(pdiag, dict), pdiag
            ev = mp._prefetch_evidence_for("partial-req")
            reason = ev.get("prefetch_reason", "")
            assert reason.startswith("key_build_partial"), ev
            assert "clip_identity" in reason, ev
            assert ev.get("prefetch_requested") == 1, ev

    def test_raw_workflow_ctx_has_clip_identity_filename(self):
        # A raw-source-workflow-style dict (CLIPLoader node) yields a
        # non-empty plan-time context with clip_identity == the filename.
        plan = self._plan_workflow_only()
        with patch.object(mp, "_read_models_generation", return_value="gen1"):
            ctx = mp._build_plan_time_cache_context(plan)
        assert ctx, "raw workflow context must be non-empty"
        assert ctx["clip_identity"] == "clip.safetensors", ctx
        assert ctx["clip_type"] == "flux", ctx
        assert ctx["loader_class"] == "CLIPLoader", ctx
        assert ctx["filenames"] == ["clip.safetensors"], ctx

    def test_workflow_fallback_fills_identity_when_model_key_empty(self):
        # derive_model_key returning an empty model key must NOT kill the
        # context: the workflow CLIPLoader node fallback fills clip_identity.
        import comfymodal_runtime.restore_plan as rp
        from comfymodal_runtime.contracts import ModelRestoreKey

        with patch.object(rp, "derive_model_key", return_value=ModelRestoreKey()):
            ctx = mp._build_plan_time_cache_context(self._plan_workflow_only())
        assert ctx, "ctx must proceed even with an empty model key"
        assert ctx["clip_identity"] == "clip.safetensors", ctx
        assert ctx["clip_type"] == "flux", ctx
        assert ctx["loader_class"] == "CLIPLoader", ctx

    def test_workflow_node_weight_dtype_filled(self):
        # C.1: CLIPLoader node with a weight_dtype input -> plan-time ctx
        # fills weight_dtype (matches the demand-time request mirror).
        ctx = mp._build_plan_time_cache_context(
            self._plan_with_weight_dtype(source="workflow", value="bf16")
        )
        assert ctx, ctx
        assert ctx["weight_dtype"] == "bf16", ctx

    def test_prompt_bundle_weight_dtype_filled(self):
        # C.2: prompt_bundle.encodes per-entry weight_dtype -> filled.
        ctx = mp._build_plan_time_cache_context(
            self._plan_with_weight_dtype(source="prompt_bundle", value="bf16")
        )
        assert ctx, ctx
        assert ctx["weight_dtype"] == "bf16", ctx
        assert ctx["clip_identity"] == "clip.safetensors", ctx

    def test_model_stack_weight_dtype_filled(self):
        # C.3: model_stack loader spec weight_dtype field -> filled.
        ctx = mp._build_plan_time_cache_context(
            self._plan_with_weight_dtype(source="model_stack", value="bf16")
        )
        assert ctx, ctx
        assert ctx["weight_dtype"] == "bf16", ctx
        assert ctx["clip_identity"] == "clip.safetensors", ctx

    def test_no_weight_dtype_anywhere_reports_partial(self):
        # C.4 + RUN-3 workload: the CLIPLoader node has clip_name/device/type
        # but NO weight_dtype input (verified against the compiled workflow),
        # so plan-time weight_dtype stays "" (fail-closed) and the evidence
        # reason lists it — while the context STILL proceeds (manifest-only).
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            with patch.object(mp, "_read_models_generation", return_value="gen1"):
                ctx = mp._build_plan_time_cache_context(self._plan_no_weight_dtype())
            assert ctx, "RUN-3 workload context must proceed"
            assert ctx["clip_identity"] == "qwen_3_4b.safetensors", ctx
            assert ctx["clip_type"] == "lumina2", ctx
            assert ctx["weight_dtype"] == "", ctx
            with patch.object(mp, "env_flag", return_value=True), patch.object(
                mp, "get_exact_conditioning_cache", return_value=cache
            ):
                pdiag = mp.maybe_prefetch_conditioning(
                    self._plan_no_weight_dtype(), request_id="run3-req"
                )
            assert isinstance(pdiag, dict), pdiag
            ev = mp._prefetch_evidence_for("run3-req")
            reason = ev.get("prefetch_reason", "")
            assert reason.startswith("key_build_partial"), ev
            assert "weight_dtype" in reason, ev
            assert ev.get("prefetch_requested") == 1, ev

    def test_inner_ctx_exception_logs_and_records_failed(self, capsys):
        # A plan-time ctx-build exception is never silent: a bounded
        # [cache.prefetch] ctx_build_failed line is printed and the evidence
        # records key_build_failed.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            with patch.object(mp, "env_flag", return_value=True), patch.object(
                mp, "get_exact_conditioning_cache", return_value=cache
            ), patch.object(
                mp, "_plan_time_options_hash", side_effect=RuntimeError("boom-opts")
            ):
                diag = mp.maybe_prefetch_conditioning(
                    self._fake_plan(), request_id="boom-req"
                )
            assert diag == {}
            ev = mp._prefetch_evidence_for("boom-req")
            assert ev.get("prefetch_reason") == "key_build_failed", ev
            out = capsys.readouterr().out
            assert "ctx_build_failed" in out, out
            assert "boom-opts" in out, out

    def test_lookup_diag_carries_merged_evidence(self):
        # B: the host-visible path — the lookup diag dict itself (which the
        # host formatter reads via lookup_diagnostics) carries the merged
        # prefetch engagement keys after the merge helper runs.
        mp._record_prefetch_evidence(
            "host-ev", requested=1, source="manifest_only",
            reason="key_build_partial:clip_identity",
        )
        try:
            diag = mp._merge_prefetch_evidence_into_diag(
                {"prefetch_requested": 0, "prefetch_source": "none", "total_ms": 1.0},
                "host-ev",
            )
            assert diag["prefetch_requested"] == 1, diag
            assert diag["prefetch_source"] == "manifest_only", diag
            assert diag["prefetch_reason"] == "key_build_partial:clip_identity", diag
            assert "total_ms" in diag  # existing fields preserved
            # No evidence for a different request_id -> unchanged.
            diag2 = mp._merge_prefetch_evidence_into_diag(
                {"prefetch_requested": 0, "total_ms": 1.0}, "no-evidence-req"
            )
            assert diag2["prefetch_requested"] == 0, diag2
            assert "prefetch_reason" not in diag2, diag2
        finally:
            mp._record_prefetch_evidence(
                "host-ev", requested=0, source="none", reason="none"
            )

    def test_host_trace_lookup_diagnostics_carry_evidence(self, capsys):
        # B (integration): with evidence recorded, the REAL prefill hook's
        # clip_conditioning_cache_lookup trace event carries
        # lookup_diagnostics.prefetch_requested=1 + prefetch_reason, AND the
        # container-stdout breakdown emission shows the SAME merged values —
        # the RUN-4 discrepancy (stdout merged, trace not) is gone for the
        # evidence-ready case.
        from comfymodal_runtime.trace import RuntimeTrace
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan

        class _FakeCache:
            last_store_reason = ""

            def lookup_many(self, base_ctx, entries):
                return {}, [dict(e) for e in entries], 0, len(entries)

            def latest_lookup_diagnostics(self):
                return {"prefetch_requested": 0, "prefetch_source": "none"}

            def pop_store_diagnostics(self):
                return {}

            def store_entry(self, base_ctx, entry, value):
                return True

        mp._record_prefetch_evidence(
            "host-flow-req", requested=1, source="none", reason="key_build_failed"
        )
        try:
            bridge = mp.V2LoaderBridge(max_workers=2)
            bridge.install = lambda nodes=None, trace=None: True
            bridge._request_list = lambda bucket: [{"clip_name": "clip_l.safetensors"}]
            bridge._model_spec = {
                "loaders": {
                    "unet": [],
                    "clip": [{"clip_name": "clip_l.safetensors"}],
                    "vae": [],
                }
            }
            bridge.coordinator.clip_loader = (
                lambda key: types.SimpleNamespace(patcher=types.SimpleNamespace())
            )
            bridge.coordinator.unet_loader = lambda key: "unet-done"
            bridge._invoke_original = (
                lambda class_name, kwargs: (f"conditioning:{kwargs['text']}",)
            )
            trace = RuntimeTrace(request_id="host-flow-req", process="remote")
            model_key = ModelRestoreKey(
                unet_identity="unet.safetensors",
                clip_identity="clip_l.safetensors",
                clip_type="stable_diffusion",
            )
            prefill_key = PrefillKey(
                model_key=model_key,
                prompt_bundle_hash="hash-host-flow",
                encode_options={
                    "eligible": True,
                    "encodes": [{"node_id": "6", "text": "a happy cat", "role": "positive"}],
                },
            )
            plan = RestorePlan(model_key=model_key, prefill_key=prefill_key)
            with patch.object(mp, "get_exact_conditioning_cache", return_value=_FakeCache()):
                bridge.prepare(plan, trace=trace)
                prep = bridge._preparation
                assert bridge.schedule_execution_prefill(trace=trace) is True
                prep.prefill_future.result(timeout=5)
            lookups = [
                dict(e.metadata) for e in trace.events
                if e.name == "clip_conditioning_cache_lookup"
            ]
            assert len(lookups) == 1, len(lookups)
            ldiag = lookups[0].get("lookup_diagnostics") or {}
            assert ldiag.get("prefetch_requested") == 1, ldiag
            assert ldiag.get("prefetch_source") == "none", ldiag
            assert ldiag.get("prefetch_reason") == "key_build_failed", ldiag
            # The top-level trace metadata fields agree.
            assert lookups[0].get("prefetch_reason") == "key_build_failed", lookups[0]
            # The container-stdout breakdown emission shows the SAME merged
            # values for the same request (RUN-4 discrepancy gone).
            out = capsys.readouterr().out
            assert "decision=miss_stored" in out, out
            assert "prefetch_requested=1" in out, out
            assert "prefetch_reason=key_build_failed" in out, out
            bridge.coordinator.close()
        finally:
            mp._record_prefetch_evidence(
                "host-flow-req", requested=0, source="none", reason="none"
            )

    def test_breakdown_emission_merges_engagement_evidence(self, capsys):
        # Simulates the RUN-1 miss line: the cache diag says 0/none (prefetch
        # never ran) but the plan-time evidence records env_off engagement.
        mp._record_prefetch_evidence("brk-ev", requested=1, source="none", reason="env_off")
        try:
            mp._emit_conditioning_exact_hit_breakdown(
                {
                    "total_ms": 562.243,
                    "key_build_digest_ms": 0.2,
                    "lock_wait_ms": 0.001,
                    "manifest_read_ms": 561.783,
                    "manifest_read_bytes": 2048,
                    "manifest_entries": 1,
                    "entry_lookup_ms": 0.3,
                    "header_bytes_read": 0,
                    "data_bytes_read": 0,
                    "lru_touch_ms": 0.0,
                    "lru_touch_mode": "sync",
                    "measured_children_ms": 562.284,
                    "residual_ms": -0.041,
                    "prefetch_requested": 0,
                    "prefetch_source": "none",
                },
                request_id="brk-ev",
                decision="miss_stored",
            )
            out = capsys.readouterr().out
            assert "decision=miss_stored" in out
            # Evidence overrides the cache defaults truthfully.
            assert "prefetch_requested=1" in out, out
            assert "prefetch_source=none" in out, out
            assert "prefetch_reason=env_off" in out, out
            # Reconciliation fields remain intact and opt=1 ordering holds.
            assert "children_ms=562.284" in out, out
            assert "residual_ms=-0.041" in out, out
            assert "opt=1" in out, out
        finally:
            mp._record_prefetch_evidence("brk-ev", requested=0, source="none", reason="none")

    def test_prefetches_from_plan_and_serves_memory_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            plan = self._fake_plan()
            with patch.object(mp, "_read_models_generation", return_value="gen1"):
                ctx = mp._build_plan_time_cache_context(plan)
            assert ctx, "plan-time context must be non-empty"
            assert ctx["clip_identity"] == "clip.safetensors"
            assert ctx["clip_type"] == "flux"
            assert ctx["loader_class"] == "CLIPLoader"
            assert ctx["workflow_hash"] == "planwf"
            assert ctx["deployment_hash"] == "dep1"
            assert ctx["custom_node_generation"] == "cn1"
            assert ctx["compute_dtype"], "compute_dtype approximation must be non-empty"
            assert ctx["tokenizer_identity"], "tokenizer identity approximation must be non-empty"
            entry = _entry("plan cat", role="positive")
            assert cache.store_entry(ctx, entry, _value()) is True
            assert _wait_until(lambda: cache._worker_diag.get("persisted", 0) >= 1)
            with patch.object(mp, "_read_models_generation", return_value="gen1"), patch.object(
                mp, "env_flag", return_value=True
            ), patch.object(mp, "get_exact_conditioning_cache", return_value=cache):
                pdiag = mp.maybe_prefetch_conditioning(plan, request_id="plan-req")
            assert pdiag.get("loaded") == 1, pdiag
            ev = mp._prefetch_evidence_for("plan-req")
            assert ev.get("prefetch_reason") == "ok", ev
            assert ev.get("prefetch_source") == "full", ev
            assert ev.get("prefetch_requested") == 1, ev
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            ldiag = cache.latest_lookup_diagnostics()
            assert ldiag["payload_memory_hit"] == 1, ldiag
            assert ldiag["manifest_memory_hit"] == 1, ldiag
            cache.flush(timeout=15.0)

    def test_entry_time_evidence_recorded_mid_flight(self):
        # RUN-4 root cause: the prefetch thread records engagement at ENTRY
        # (reason "running"), so a demand-time observer sees
        # prefetch_requested=1 even while the prefetch is mid-flight — the
        # trace emit can no longer race ahead of the evidence.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            _entered = threading.Event()
            _release = threading.Event()

            def _blocking_prefetch(ctx, entries, request_id=""):
                _entered.set()
                _release.wait(timeout=15)
                return {"requested": 1, "loaded": 0, "failures": 0, "source": "manifest_only"}

            with patch.object(cache, "prefetch_entries", side_effect=_blocking_prefetch), patch.object(
                mp, "env_flag", return_value=True
            ), patch.object(mp, "_read_models_generation", return_value="gen1"), patch.object(
                mp, "get_exact_conditioning_cache", return_value=cache
            ):
                t = threading.Thread(
                    target=mp.maybe_prefetch_conditioning,
                    args=(self._fake_plan(),),
                    kwargs={"request_id": "midflight-req"},
                    daemon=True,
                )
                t.start()
                assert _entered.wait(timeout=15), "prefetch thread never entered"
                # While the prefetch is blocked, the entry-time record is
                # already visible to a demand-time observer.
                ev = mp._prefetch_evidence_for("midflight-req")
                assert ev.get("prefetch_requested") == 1, ev
                assert ev.get("prefetch_reason") == "running", ev
                _release.set()
                t.join(timeout=15)
            # After completion the final outcome is recorded.
            ev = mp._prefetch_evidence_for("midflight-req")
            assert ev.get("prefetch_reason") == "ok", ev
            assert ev.get("prefetch_source") == "manifest_only", ev
            mp._record_prefetch_evidence("midflight-req", requested=0, source="none", reason="none")

    def test_prefill_trace_and_stdout_agree_while_prefetch_in_flight(self, capsys):
        # RUN-4 reproduction end-to-end: the demand-time trace emit races
        # ahead of the (daemon) prefetch thread.  With entry-time recording
        # the trace metadata carries prefetch_requested=1 + prefetch_reason
        # even while the prefetch is mid-flight, and the container-stdout
        # emission (same request) agrees.
        from comfymodal_runtime.trace import RuntimeTrace
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan

        class _FakeCache:
            last_store_reason = ""

            def lookup_many(self, base_ctx, entries):
                return {}, [dict(e) for e in entries], 0, len(entries)

            def latest_lookup_diagnostics(self):
                return {"prefetch_requested": 0, "prefetch_source": "none"}

            def pop_store_diagnostics(self):
                return {}

            def store_entry(self, base_ctx, entry, value):
                return True

        _entered = threading.Event()
        _release = threading.Event()

        def _blocking_prefetch(ctx, entries, request_id=""):
            _entered.set()
            _release.wait(timeout=15)
            return {"requested": 1, "loaded": 0, "failures": 0, "source": "manifest_only"}

        fake = _FakeCache()
        with patch.object(
            fake, "prefetch_entries", side_effect=_blocking_prefetch, create=True
        ), patch.object(
            mp, "env_flag", return_value=True
        ), patch.object(mp, "_read_models_generation", return_value="gen1"), patch.object(
            mp, "get_exact_conditioning_cache", return_value=fake
        ):
            t = threading.Thread(
                target=mp.maybe_prefetch_conditioning,
                args=(self._fake_plan(),),
                kwargs={"request_id": "race-req"},
                daemon=True,
            )
            t.start()
            assert _entered.wait(timeout=15), "prefetch thread never entered prefetch_entries"

            bridge = mp.V2LoaderBridge(max_workers=2)
            bridge.install = lambda nodes=None, trace=None: True
            bridge._request_list = lambda bucket: [{"clip_name": "clip_l.safetensors"}]
            bridge._model_spec = {
                "loaders": {"unet": [], "clip": [{"clip_name": "clip_l.safetensors"}], "vae": []}
            }
            bridge.coordinator.clip_loader = (
                lambda key: types.SimpleNamespace(patcher=types.SimpleNamespace())
            )
            bridge.coordinator.unet_loader = lambda key: "unet-done"
            bridge._invoke_original = (
                lambda class_name, kwargs: (f"conditioning:{kwargs['text']}",)
            )
            trace = RuntimeTrace(request_id="race-req", process="remote")
            model_key = ModelRestoreKey(
                unet_identity="unet.safetensors",
                clip_identity="clip_l.safetensors",
                clip_type="stable_diffusion",
            )
            prefill_key = PrefillKey(
                model_key=model_key,
                prompt_bundle_hash="hash-race",
                encode_options={
                    "eligible": True,
                    "encodes": [{"node_id": "6", "text": "a happy cat", "role": "positive"}],
                },
            )
            plan = RestorePlan(model_key=model_key, prefill_key=prefill_key)
            with patch.object(mp, "get_exact_conditioning_cache", return_value=fake):
                bridge.prepare(plan, trace=trace)
                prep = bridge._preparation
                assert bridge.schedule_execution_prefill(trace=trace) is True
                prep.prefill_future.result(timeout=5)

            # (a) The trace-event lookup_diagnostics carries the merged
            # evidence even though the prefetch thread is STILL in flight.
            lookups = [
                dict(e.metadata) for e in trace.events
                if e.name == "clip_conditioning_cache_lookup"
            ]
            assert len(lookups) == 1, len(lookups)
            ldiag = lookups[0].get("lookup_diagnostics") or {}
            assert ldiag.get("prefetch_requested") == 1, ldiag
            assert "prefetch_source" in ldiag, ldiag
            assert "prefetch_reason" in ldiag, ldiag
            assert ldiag.get("prefetch_reason") in ("running", "ok"), ldiag
            assert lookups[0].get("prefetch_requested") == 1, lookups[0]

            # (b) The container-stdout breakdown emission agrees.
            out = capsys.readouterr().out
            assert "prefetch_requested=1" in out, out
            assert "prefetch_reason=" in out, out

            bridge.coordinator.close()
            _release.set()
            t.join(timeout=15)
        # After the prefetch thread completes, the final outcome is recorded.
        ev = mp._prefetch_evidence_for("race-req")
        assert ev.get("prefetch_reason") == "ok", ev
        assert ev.get("prefetch_source") == "manifest_only", ev
        mp._record_prefetch_evidence("race-req", requested=0, source="none", reason="none")

    def test_empty_launch_id_evidence_found_by_real_request_id(self):
        # Correlation fallback: a launch that carried no request id records
        # under "" — the demand-time real request id must still find the
        # engagement (bounded "" fallback in _prefetch_evidence_for).
        mp._record_prefetch_evidence("", requested=1, source="none", reason="env_off")
        try:
            ev = mp._prefetch_evidence_for("v2-benchmark-0-real-req")
            assert ev.get("prefetch_requested") == 1, ev
            assert ev.get("prefetch_source") == "none", ev
            assert ev.get("prefetch_reason") == "env_off", ev
            # A stale cleanup entry (requested=0) is NOT honored as fallback.
            mp._record_prefetch_evidence("", requested=0, source="none", reason="none")
            ev2 = mp._prefetch_evidence_for("v2-benchmark-0-real-req")
            assert ev2 == {}, ev2
        finally:
            mp._record_prefetch_evidence("", requested=0, source="none", reason="none")


class TestPrefetchDemandJoin:
    """RUN-2: the demand-time lookup can boundedly wait for an in-flight
    prefetch (join) so the memory manifest/payloads serve the exact hit, and
    the first prefetch of the container skips the volume reload."""

    def test_demand_join_waits_for_inflight_prefetch(self):
        # C.1: prefetch in flight -> join_prefetch waits for it -> the memory
        # manifest/payloads are installed and the exact hit is served from
        # memory (manifest_memory_hit=1 / payload_memory_hit=1).
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("join-hit"), _entry("join-hit"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            _entered = threading.Event()
            _orig_read = cache._read_manifest

            def _slow_read(*args, **kwargs):
                _entered.set()
                time.sleep(0.3)
                return _orig_read(*args, **kwargs)

            cache._read_manifest = _slow_read
            t = threading.Thread(
                target=cache.prefetch_entries,
                args=(ctx, [entry]),
                kwargs={"request_id": "join-req"},
            )
            t.start()
            assert _entered.wait(timeout=5), "prefetch thread never entered the slow read"
            # The prefetch is in flight; the demand join waits for it.
            assert cache.join_prefetch("join-req", timeout_s=5.0) is True
            t.join(timeout=10)
            cache._read_manifest = _orig_read
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            diag = cache.latest_lookup_diagnostics()
            assert diag["manifest_memory_hit"] == 1, diag
            assert diag["payload_memory_hit"] == 1, diag
            cache.flush(timeout=15.0)

    def test_join_timeout_returns_false_within_bound(self):
        # C.2: a prefetch blocked beyond the bound -> join returns False
        # within the bound (never raises, never blocks longer); no in-flight
        # prefetch -> immediate True.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("join-to"), _entry("join-to"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            _entered = threading.Event()
            _release = threading.Event()
            _orig_read = cache._read_manifest

            def _blocked_read(*args, **kwargs):
                _entered.set()
                _release.wait(timeout=15)
                return _orig_read(*args, **kwargs)

            cache._read_manifest = _blocked_read
            t = threading.Thread(
                target=cache.prefetch_entries,
                args=(ctx, [entry]),
                kwargs={"request_id": "join-to-req"},
            )
            t.start()
            assert _entered.wait(timeout=5)
            _join_start = time.monotonic()
            assert cache.join_prefetch("join-to-req", timeout_s=0.2) is False
            assert (time.monotonic() - _join_start) < 1.0, "join exceeded its bound"
            # No prefetch in flight -> nothing to wait for -> True.
            assert cache.join_prefetch("other-req", timeout_s=0.2) is True
            _release.set()
            t.join(timeout=10)
            cache._read_manifest = _orig_read
            cache.flush(timeout=15.0)

    def test_prefill_hook_records_join_timeout(self):
        # C.2 (hook): when the in-flight prefetch does not complete within
        # the join bound, the prefill hook records prefetch_join_timeout=1 in
        # the trace lookup_diagnostics and falls through to the cold path.
        from comfymodal_runtime.trace import RuntimeTrace
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan

        class _FakeCache:
            last_store_reason = ""

            def lookup_many(self, base_ctx, entries):
                return {}, [dict(e) for e in entries], 0, len(entries)

            def latest_lookup_diagnostics(self):
                return {"prefetch_requested": 0, "prefetch_source": "none"}

            def pop_store_diagnostics(self):
                return {}

            def store_entry(self, base_ctx, entry, value):
                return True

            def join_prefetch(self, request_id="", timeout_s=1.5):
                return False  # in-flight prefetch never completes in time

        fake = _FakeCache()
        bridge = mp.V2LoaderBridge(max_workers=2)
        bridge.install = lambda nodes=None, trace=None: True
        bridge._request_list = lambda bucket: [{"clip_name": "clip_l.safetensors"}]
        bridge._model_spec = {
            "loaders": {"unet": [], "clip": [{"clip_name": "clip_l.safetensors"}], "vae": []}
        }
        bridge.coordinator.clip_loader = (
            lambda key: types.SimpleNamespace(patcher=types.SimpleNamespace())
        )
        bridge.coordinator.unet_loader = lambda key: "unet-done"
        bridge._invoke_original = (
            lambda class_name, kwargs: (f"conditioning:{kwargs['text']}",)
        )
        trace = RuntimeTrace(request_id="join-to-flow", process="remote")
        model_key = ModelRestoreKey(
            unet_identity="unet.safetensors",
            clip_identity="clip_l.safetensors",
            clip_type="stable_diffusion",
        )
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="hash-join-to",
            encode_options={
                "eligible": True,
                "encodes": [{"node_id": "6", "text": "a happy cat", "role": "positive"}],
            },
        )
        plan = RestorePlan(model_key=model_key, prefill_key=prefill_key)
        with patch.object(mp, "get_exact_conditioning_cache", return_value=fake):
            bridge.prepare(plan, trace=trace)
            prep = bridge._preparation
            assert bridge.schedule_execution_prefill(trace=trace) is True
            prep.prefill_future.result(timeout=5)
        lookups = [
            dict(e.metadata) for e in trace.events
            if e.name == "clip_conditioning_cache_lookup"
        ]
        assert len(lookups) == 1, len(lookups)
        ldiag = lookups[0].get("lookup_diagnostics") or {}
        assert ldiag.get("prefetch_join_timeout") == 1, ldiag
        assert "prefetch_join_ms" in ldiag, ldiag
        bridge.coordinator.close()

    def test_first_prefetch_reload_skipped(self):
        # C.3: single-use containers see the latest volume commit at mount —
        # the FIRST prefetch skips the volume reload (prefetch_reload=
        # skipped_first); later prefetches keep the throttled reload.
        reloads: list[int] = []

        def reload_hook():
            reloads.append(1)

        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            cache.set_reload_hook(reload_hook)
            ctx, entry, value = _base_ctx("skip-rel"), _entry("skip-rel"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            reloads.clear()  # drop the persistence worker's reload-before-batch
            pdiag = cache.prefetch_entries(ctx, [entry])
            assert pdiag.get("prefetch_reload") == "skipped_first", pdiag
            assert len(reloads) == 0, reloads
            pdiag2 = cache.prefetch_entries(ctx, [entry])
            assert pdiag2.get("prefetch_reload") in ("ran", "skipped_throttled"), pdiag2
            assert len(reloads) >= 1, reloads
            cache.flush(timeout=15.0)


class TestServeByComponents:
    """RUN-6: the prefetch loads the manifest's existing entries keyed by
    their OWN stored digests, and the demand-time memory path can serve via a
    component-match scan when the plan-time digest drifted."""

    def test_component_match_serves_drifted_plan_digest(self):
        # D.1 / RUN-2: the plan-time digest drifts from the demand digest
        # (compute_dtype/tokenizer approximations).  The manifest-entry
        # fallback loads the real stored entry keyed by its OWN digest, so
        # the demand lookup serves the exact hit from memory with values
        # equal to the stored value.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("drift"), _entry("drift"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            # Plan-time prefetch with a DRIFTED context -> different digest.
            drifted = _base_ctx(
                "drift", compute_dtype="torch.float32", tokenizer_identity="tok-drifted"
            )
            pdiag = cache.prefetch_entries(drifted, [entry])
            assert pdiag.get("prefetch_payload_entries", 0) >= 1, pdiag
            assert pdiag.get("source") == "full", pdiag
            # The memory store holds the real entry keyed by its own digest.
            assert len(cache._mem_payloads) >= 1, cache._mem_payloads
            # Demand lookup with the REAL ctx serves from memory.
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            cond, pooled = _cond_and_pooled(hits[0])
            assert torch.equal(cond, value[0][0])
            assert torch.equal(pooled, value[0][1]["pooled"])
            diag = cache.latest_lookup_diagnostics()
            assert diag["manifest_memory_hit"] == 1, diag
            assert diag["payload_memory_hit"] == 1, diag
            assert diag.get("payload_memory_source") in ("key_hit", "component_match"), diag
            cache.flush(timeout=15.0)

    def test_component_match_scan_serves_miskeyed_payload(self):
        # Direct exercise of the component-match scan branch: a payload
        # stored under a dict key DIFFERENT from its header key_hash (the
        # drifted-plan-digest keying case) is still served — the scan
        # validates with the demand digest, which the stored key_hash equals
        # IFF the stored canonical components equal the live ones.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("scan-serve"), _entry("scan-serve"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            kh, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            with open(header_path, "rb") as f:
                hb = f.read()
            with open(data_path, "rb") as f:
                db = f.read()
            with cache._prefetch_lock:
                cache._mem_payloads["some-other-digest"] = {
                    "header_bytes": hb,
                    "data_bytes": db,
                    "read_mono_ns": time.monotonic_ns(),
                }
                cache._mem_manifest = cache._read_manifest()
                _st = os.stat(cache._manifest_path)
                cache._mem_manifest_mtime_ns = int(_st.st_mtime_ns)
                cache._mem_manifest_size = int(_st.st_size)
                cache._mem_invalidated = False
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 1, diag
            assert diag.get("payload_memory_source") == "component_match", diag
            cache.flush(timeout=15.0)

    def test_component_match_scan_rejects_wrong_entry(self):
        # D.2: the component-match scan REJECTS a stored entry whose
        # components differ from the live components and the lookup falls
        # back to the cold file path (miss).  The memory source is never
        # reported as a component match.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx_a, entry_a, value_a = _base_ctx("scan-a"), _entry("scan-a"), _value()
            assert cache.store_entry(ctx_a, entry_a, value_a) is True
            cache.flush(timeout=15.0)
            pdiag = cache.prefetch_entries(ctx_a, [entry_a])
            assert pdiag.get("prefetch_payload_entries", 0) >= 1, pdiag
            ctx_b = _base_ctx("scan-a", workflow_hash="wf-other")
            hits, misses, hc, mc = cache.lookup_many(ctx_b, [entry_a])
            assert (hc, mc) == (0, 1)
            diag = cache.latest_lookup_diagnostics()
            assert diag["payload_memory_hit"] == 0, diag
            assert diag.get("payload_memory_source", "") != "component_match", diag
            cache.flush(timeout=15.0)

    def test_prefetch_entries_bounded(self):
        # D.3: at most _PREFETCH_MAX_ENTRIES manifest-entry payloads are
        # loaded (env override respected, clamped to [0,8]).
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, max_entries=64)
            for i in range(5):
                c = _base_ctx(f"bounded-{i}", workflow_hash=f"wf-{i}")
                assert cache.store_entry(c, _entry(f"bounded-{i}"), _value()) is True
            cache.flush(timeout=15.0)
            with patch.dict(os.environ, {"COMFYMODAL_V2_CONDITIONING_PREFETCH_MAX_ENTRIES": "2"}):
                pdiag = cache.prefetch_entries(_base_ctx("x"), [_entry("y")])
            assert pdiag.get("prefetch_payload_entries", 0) <= 2, pdiag
            assert len(cache._mem_payloads) <= 2, cache._mem_payloads
            with patch.dict(os.environ, {"COMFYMODAL_V2_CONDITIONING_PREFETCH_MAX_ENTRIES": "99"}):
                pdiag_clamp = cache.prefetch_entries(_base_ctx("x"), [_entry("y")])
            assert pdiag_clamp.get("prefetch_payload_entries", 0) <= 8, pdiag_clamp
            cache.flush(timeout=15.0)

    def test_prefetch_source_manifest_only_when_no_entry_files(self):
        # D.4: manifest loads but no entry files exist -> prefetch_source=
        # manifest_only, zero payload entries loaded.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            ctx, entry, value = _base_ctx("mo"), _entry("mo"), _value()
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            kh, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            os.remove(header_path)
            os.remove(data_path)
            pdiag = cache.prefetch_entries(ctx, [entry])
            assert pdiag.get("source") == "manifest_only", pdiag
            assert pdiag.get("prefetch_payload_entries", 0) == 0, pdiag
            cache.flush(timeout=15.0)


class TestMaybePrefetchConditioningEnvDefault:
    """The ``COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH`` gate defaults ON.

    ``mp.env_flag`` is deliberately NOT patched here — the REAL
    ``env_flag(ENV_PREFETCH, default=True)`` path is exercised so the
    production default semantics are proven end-to-end:

    * env UNSET   -> the prefetch proceeds past the gate (its failure, when
      any, is a downstream cache-off — never ``env_off``).
    * env "0"     -> the gate fails closed with ``prefetch_reason=env_off``.
    * env "1"     -> the prefetch proceeds past the gate (cache_off evidence
      when the cache is unavailable, never env_off).
    """

    def _fake_plan(self):
        workflow = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "plan cat"},
                "_meta": {"title": "positive"},
            },
        }
        return types.SimpleNamespace(
            workflow=workflow,
            workflow_hash="planwf",
            source_workflow_hash="planwf",
            deployment_identity={
                "deployment_combined_hash": "dep1",
                "custom_nodes_generation": "cn1",
            },
            execution_options=types.SimpleNamespace(
                to_dict=lambda: {"production_enabled": True, "result_route": "test"}
            ),
            model_stack={
                "loaders": {
                    "clip": [{
                        "loader_class": "CLIPLoader",
                        "clip_name": "clip.safetensors",
                        "weight_dtype": "bf16",
                    }]
                }
            },
            prompt_bundle={
                "encodes": [{
                    "node_id": "2",
                    "node_class": "CLIPTextEncode",
                    "prompt_input": "text",
                    "role": "positive",
                    "text": "plan cat",
                }]
            },
        )

    def test_env_unset_defaults_to_attempted(self, monkeypatch):
        # UNSET -> default=True: the gate PASSES and the prefetch proceeds to
        # the cache (which is off here), so the evidence is cache_off, never
        # env_off — proving the prefetch was attempted by default.
        monkeypatch.delenv("COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH", raising=False)
        with patch.object(mp, "get_exact_conditioning_cache", return_value=None):
            diag = mp.maybe_prefetch_conditioning(self._fake_plan(), request_id="default-on-req")
        assert diag == {}
        ev = mp._prefetch_evidence_for("default-on-req")
        assert ev.get("prefetch_requested") == 1, ev
        assert ev.get("prefetch_reason") == "cache_off", ev

    def test_env_unset_full_prefetch_reaches_ok(self, monkeypatch):
        # UNSET + a usable cache -> the prefetch actually RUNS and records ok
        # (end-to-end proof that the default-enabled gate arms the feature).
        monkeypatch.delenv("COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH", raising=False)
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            plan = self._fake_plan()
            try:
                with patch.object(mp, "_read_models_generation", return_value="gen1"):
                    ctx = mp._build_plan_time_cache_context(plan)
                assert ctx, "plan-time context must be non-empty"
                entry = _entry("plan cat", role="positive")
                assert cache.store_entry(ctx, entry, _value()) is True
                assert _wait_until(lambda: cache._worker_diag.get("persisted", 0) >= 1)
                with patch.object(
                    mp, "_read_models_generation", return_value="gen1"
                ), patch.object(mp, "get_exact_conditioning_cache", return_value=cache):
                    pdiag = mp.maybe_prefetch_conditioning(
                        plan, request_id="default-on-full-req"
                    )
                assert pdiag.get("loaded") == 1, pdiag
                ev = mp._prefetch_evidence_for("default-on-full-req")
                assert ev.get("prefetch_reason") == "ok", ev
                assert ev.get("prefetch_source") == "full", ev
            finally:
                # Always close the cache worker so the session never lingers.
                cache.flush(timeout=15.0)

    def test_env_zero_disables(self, monkeypatch):
        # Explicit "0" -> the gate fails closed with env_off evidence.
        monkeypatch.setenv("COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH", "0")
        with patch.object(mp, "get_exact_conditioning_cache", return_value=None):
            diag = mp.maybe_prefetch_conditioning(self._fake_plan(), request_id="env-zero-req")
        assert diag == {}
        ev = mp._prefetch_evidence_for("env-zero-req")
        assert ev.get("prefetch_requested") == 1, ev
        assert ev.get("prefetch_reason") == "env_off", ev

    def test_env_one_enables(self, monkeypatch):
        # Explicit "1" -> the gate passes (cache_off evidence, never env_off).
        monkeypatch.setenv("COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH", "1")
        with patch.object(mp, "get_exact_conditioning_cache", return_value=None):
            diag = mp.maybe_prefetch_conditioning(self._fake_plan(), request_id="env-one-req")
        assert diag == {}
        ev = mp._prefetch_evidence_for("env-one-req")
        assert ev.get("prefetch_requested") == 1, ev
        assert ev.get("prefetch_reason") == "cache_off", ev
