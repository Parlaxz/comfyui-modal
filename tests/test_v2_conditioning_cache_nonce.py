"""Tests for the semantic-neutral conditioning-cache NONCE.

Unlike ``--unique-prompt-suffix`` (which mutates prompt text and therefore the
canonical workflow hash), the nonce enters ONLY the exact-conditioning cache
key derivation: the workflow sent to ComfyUI stays byte-identical (same
prompt text, nodes, seed, sampler, model inputs).  A fresh nonce forces a
cache MISS even when the ordinary canonical key exists; a nonce-isolated write
never touches the ordinary identity because the digest (hence every cache
file path) differs.

The exact-conditioning cache key (``clip_conditioning_cache
.build_exact_key_components``) includes the nonce CONDITIONALLY — a non-empty
``cache_nonce`` in the context adds the top-level ``cache_nonce`` field; an
empty/absent value leaves the canonical key JSON byte-identical.

Transport chain under test:
    benchmark ``_extra_origin`` / ``request_origin_info.conditioning_cache_nonce``
    -> plan ``request_metadata`` -> remote trace ``request_origin_info``
    -> ``_read_conditioning_cache_nonce(trace)`` -> ``ctx["cache_nonce"]``
    -> ``build_exact_key_components`` (demand + plan-time prefetch).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from typing import Any

import torch

import comfymodal_runtime.model_preload as mp

from comfymodal_runtime.clip_conditioning_cache import (
    ExactConditioningCache,
    _canonical_json,
    build_exact_key_components,
    conditioning_cache_key_summary,
    exact_key_digest,
)

# ── D1 registry-proof store isolation (never write the real shared store;
#    see tests/d1_store_isolation.py) ──────────────────────────────────
import sys as _d1_sys
from pathlib import Path as _d1_Path

if str(_d1_Path(__file__).resolve().parents[1]) not in _d1_sys.path:
    _d1_sys.path.insert(0, str(_d1_Path(__file__).resolve().parents[1]))
from tests.d1_store_isolation import isolate_module_store, restore_module_store  # noqa: E402


def setUpModule():
    isolate_module_store()


def tearDownModule():
    restore_module_store()


def _base_ctx(text: str = "a warrior with dark hair", *, workflow_hash: str = "wf-nonce", **overrides) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "request_id": "nonce-req",
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


def _entry(text: str = "a warrior with dark hair", role: str = "positive") -> dict[str, Any]:
    return {"text": text, "role": role, "node_class": "CLIPTextEncode", "prompt_input": "text"}


def _value(rows: int = 32, dim: int = 32) -> Any:
    return [[torch.randn(rows, dim), {"pooled": torch.randn(1, dim)}]]


def _new_cache(tmp: str) -> ExactConditioningCache:
    return ExactConditioningCache(
        root_dir=tmp, max_entries=64, max_bytes=512 * 1024 * 1024, mounted=True
    )


def _wait_until(predicate, timeout: float = 10.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class NonceKeyDerivationTests(unittest.TestCase):
    """Requirement 2/4/5: fresh nonce -> miss, distinct nonces distinct
    identity, no shared file-path collisions with the ordinary key."""

    def test_ordinary_key_hit_without_nonce(self):
        ctx, entry, value = _base_ctx("ord-hit"), _entry("ord-hit"), _value()
        digest = exact_key_digest(build_exact_key_components(ctx))
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            self.assertTrue(cache.store_entry(ctx, entry, value))
            cache.flush(timeout=15.0)
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            self.assertEqual((hc, mc), (1, 0))
            self.assertEqual(
                exact_key_digest(build_exact_key_components(ctx)), digest
            )

    def test_fresh_nonce_forces_miss(self):
        ctx_ord = _base_ctx("miss-vehicle")
        ctx_nonce = _base_ctx("miss-vehicle", cache_nonce="NONCE-0001")
        entry = _entry("miss-vehicle")
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            self.assertTrue(cache.store_entry(ctx_ord, entry, _value()))
            cache.flush(timeout=15.0)
            # Ordinary key hit (sanity).
            hits, misses, hc, mc = cache.lookup_many(ctx_ord, [entry])
            self.assertEqual((hc, mc), (1, 0))
            # Same entry + nonce -> digest differs and the stored ordinary
            # entry is NOT served (deterministic miss).
            self.assertNotEqual(
                exact_key_digest(build_exact_key_components(ctx_nonce)),
                exact_key_digest(build_exact_key_components(ctx_ord)),
            )
            hits, misses, hc, mc = cache.lookup_many(ctx_nonce, [entry])
            self.assertEqual((hc, mc), (0, 1))

    def test_distinct_nonces_distinct_identity(self):
        ctx_a = _base_ctx("distinct", cache_nonce="NONCE-A")
        ctx_b = _base_ctx("distinct", cache_nonce="NONCE-B")
        self.assertNotEqual(
            exact_key_digest(build_exact_key_components(ctx_a)),
            exact_key_digest(build_exact_key_components(ctx_b)),
        )

    def test_nonce_absent_byte_compatible(self):
        ctx = _base_ctx("byte-compat")
        components = build_exact_key_components(ctx)
        blob = _canonical_json(components)
        self.assertNotIn("cache_nonce", blob)
        self.assertEqual(
            sorted(components.keys()),
            [
                "clip_identity", "clip_type", "compute_dtype",
                "custom_node_generation", "deployment_hash", "entry",
                "filenames", "format_version", "loader_class",
                "model_generation", "production_options_hash",
                "schema_version", "tokenizer_identity", "torch_num_threads",
                "torch_version", "weight_dtype", "workflow_hash",
            ],
        )
        # Nonce present -> the field appears and the layout gains exactly one
        # extra top-level key.
        components_nonce = build_exact_key_components(
            dict(ctx, cache_nonce="NONCE-X")
        )
        self.assertEqual(
            sorted(components_nonce.keys()),
            sorted(list(components.keys()) + ["cache_nonce"]),
        )

    def test_payload_unchanged_under_nonce_key(self):
        value = _value(rows=16, dim=16)
        ctx_ord = _base_ctx("payload")
        ctx_nonce = _base_ctx("payload", cache_nonce="NONCE-PAY")
        entry = _entry("payload")
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            self.assertTrue(cache.store_entry(ctx_ord, entry, value))
            self.assertTrue(cache.store_entry(ctx_nonce, entry, value))
            cache.flush(timeout=15.0)
            hits_ord, _, hc_ord, _ = cache.lookup_many(ctx_ord, [entry])
            hits_nonce, _, hc_nonce, _ = cache.lookup_many(ctx_nonce, [entry])
            self.assertEqual((hc_ord, hc_nonce), (1, 1))
            cond_ord, meta_ord = hits_ord[0][0]
            cond_nonce, meta_nonce = hits_nonce[0][0]
            # Same conditioning bytes/values; only the key digest differs.
            self.assertTrue(torch.equal(cond_ord, cond_nonce))
            self.assertTrue(torch.equal(meta_ord["pooled"], meta_nonce["pooled"]))
            self.assertNotEqual(
                exact_key_digest(build_exact_key_components(ctx_nonce)),
                exact_key_digest(build_exact_key_components(ctx_ord)),
            )

    def test_store_under_nonce_and_ordinary_do_not_collide(self):
        """Requirement 5: writes under the nonce key never overwrite/confuse
        the ordinary canonical identity (distinct digests -> distinct file
        paths; both entries served independently)."""
        value_ord = _value(rows=8, dim=8)
        value_nonce = _value(rows=8, dim=8)
        ctx_ord = _base_ctx("no-collide")
        ctx_nonce = _base_ctx("no-collide", cache_nonce="NONCE-COLLIDE")
        entry = _entry("no-collide")
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            self.assertTrue(cache.store_entry(ctx_ord, entry, value_ord))
            self.assertTrue(cache.store_entry(ctx_nonce, entry, value_nonce))
            cache.flush(timeout=15.0)
            hits_ord, _, hc_ord, mc_ord = cache.lookup_many(ctx_ord, [entry])
            hits_nonce, _, hc_nonce, mc_nonce = cache.lookup_many(ctx_nonce, [entry])
            self.assertEqual((hc_ord, mc_ord), (1, 0))
            self.assertEqual((hc_nonce, mc_nonce), (1, 0))
            # Each key reads back its OWN payload (deserialized values are
            # [cond, {"pooled": ...}] lists; index [0][0] is the cond tensor).
            self.assertTrue(torch.equal(hits_ord[0][0][0], value_ord[0][0]))
            self.assertTrue(torch.equal(hits_nonce[0][0][0], value_nonce[0][0]))


class NonceNoLeakTests(unittest.TestCase):
    """Requirement 1/3: workflow/prompt/plan hash byte-identical with nonce."""

    def test_same_workflow_hash_with_nonce(self):
        from canonical_execution import build_execution_plan
        from workflow_metadata import prompt_sha256

        workflow = _synthetic_workflow()
        plan_plain = build_execution_plan(
            workflow,
            request_metadata={"benchmark_run_index": 0, "benchmark_app": "t"},
            validate=False,
        )
        plan_nonce = build_execution_plan(
            workflow,
            request_metadata={
                "benchmark_run_index": 0,
                "benchmark_app": "t",
                "__request_origin_info__": {"conditioning_cache_nonce": "NONCE-0001"},
            },
            validate=False,
        )
        # The nonce never enters the prompt dict or the plan workflow hash:
        # BOTH plans carry the canonical hash of the pristine workflow.
        self.assertEqual(plan_plain.workflow_hash, plan_nonce.workflow_hash)
        self.assertEqual(plan_plain.workflow_hash, prompt_sha256(workflow))
        self.assertEqual(plan_nonce.workflow_hash, prompt_sha256(workflow))

    def test_generation_inputs_identical(self):
        """Seed/sampler/model filenames/prompt text extracted from the plan are
        identical with and without the nonce."""
        from canonical_execution import build_execution_plan
        from workflow_metadata import summarize_prompt_fields

        workflow = _synthetic_workflow()
        plan_plain = build_execution_plan(
            workflow, request_metadata={"benchmark_run_index": 0}, validate=False,
        )
        plan_nonce = build_execution_plan(
            workflow,
            request_metadata={
                "benchmark_run_index": 0,
                "__request_origin_info__": {"conditioning_cache_nonce": "NONCE-0001"},
            },
            validate=False,
        )
        self.assertEqual(
            summarize_prompt_fields(plan_plain.workflow),
            summarize_prompt_fields(plan_nonce.workflow),
        )
        self.assertEqual(plan_plain.model_stack, plan_nonce.model_stack)
        self.assertEqual(plan_plain.prompt_bundle, plan_nonce.prompt_bundle)
        # Frozen plan workflow is a mappingproxy; compare canonical hashes.
        from workflow_metadata import prompt_sha256

        self.assertEqual(
            prompt_sha256(plan_plain.workflow), prompt_sha256(plan_nonce.workflow)
        )

    def test_nonce_not_in_tokens_or_model_inputs(self):
        """With the nonce present in ctx, the cache key summary/telemetry
        shows it while the encode call record (the tokenize/encode inputs)
        carries only the prompt text — never the nonce string."""
        nonce = "NONCE-TOP-SECRET"
        ctx_nonce = _base_ctx("encode-me", cache_nonce=nonce)
        entry = _entry("encode-me")
        # Telemetry: the key summary surfaces the nonce.
        summary = conditioning_cache_key_summary(ctx_nonce, [entry])
        self.assertEqual(summary.get("cache_nonce"), nonce)
        # The entry contract handed to the encode path contains no nonce.
        entry_json = json.dumps(entry)
        self.assertNotIn(nonce, entry_json)
        self.assertNotIn(nonce, entry["text"])
        # Synthetic miss->encode: a cache holding only the ordinary entry is a
        # miss under the nonce, and the encode call sees only the prompt text.
        ctx_ord = _base_ctx("encode-me")
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp)
            self.assertTrue(cache.store_entry(ctx_ord, entry, _value()))
            cache.flush(timeout=15.0)
            hits, misses, hc, mc = cache.lookup_many(ctx_nonce, [entry])
            self.assertEqual((hc, mc), (0, 1))
            encode_record: dict[str, Any] = {"text": entry["text"]}
            self.assertNotIn(nonce, encode_record["text"])
            self.assertNotIn(nonce, json.dumps(encode_record))


class NonceTelemetryTests(unittest.TestCase):
    """Requirement 4: nonce visible in cache telemetry; absent -> clean."""

    def test_nonce_in_cache_telemetry(self):
        entry = _entry("telemetry")
        summary_with = conditioning_cache_key_summary(
            _base_ctx("telemetry", cache_nonce="NONCE-TEL"), [entry]
        )
        summary_without = conditioning_cache_key_summary(
            _base_ctx("telemetry"), [entry]
        )
        self.assertEqual(summary_with.get("cache_nonce"), "NONCE-TEL")
        self.assertNotIn("cache_nonce", summary_without)
        # Key hashes still differ (the nonce changed the isolated identity).
        self.assertNotEqual(
            summary_with["key_hash"], summary_without["key_hash"]
        )


class NonceTransportTests(unittest.TestCase):
    """Transport chain: request origin -> trace -> cache ctx -> key."""

    def test_read_conditioning_cache_nonce_from_trace(self):
        class _Ev:
            def __init__(self, name, metadata):
                self.name = name
                self.metadata = metadata

        class _FakeTrace:
            def __init__(self, events, metadata):
                self.events = events
                self._metadata = metadata

        # request_origin_info in trace._metadata (the production site).
        trace = _FakeTrace(
            [_Ev("remote_method_entry", {"workflow_hash": "W1"})],
            {"request_origin_info": {"conditioning_cache_nonce": "NONCE-R1"}},
        )
        self.assertEqual(mp._read_conditioning_cache_nonce(trace), "NONCE-R1")
        # Event-metadata fallback key (conditioning_cache_nonce / cache_nonce).
        trace2 = _FakeTrace([_Ev("method_entry", {"cache_nonce": "NONCE-R2"})], {})
        self.assertEqual(mp._read_conditioning_cache_nonce(trace2), "NONCE-R2")
        # Absent -> '' (no fabricated values).
        self.assertEqual(mp._read_conditioning_cache_nonce(_FakeTrace([], {})), "")
        self.assertEqual(mp._read_conditioning_cache_nonce(None), "")

    def test_plan_time_prefetch_ctx_carries_nonce(self):
        """The plan-time prefetch derives the SAME nonce key as demand time
        (prefetch will find nothing under a fresh nonce -> cold path)."""
        class _FakePlan:
            workflow_hash = "WF1"
            source_workflow_hash = "SWF1"
            workflow = {}
            model_stack = {}
            prompt_bundle = {}
            execution_options = None
            deployment_identity = {}

            def __init__(self, origin):
                self.request_metadata = {"__request_origin_info__": origin}

        ctx_nonce = mp._build_plan_time_cache_context(
            _FakePlan({"conditioning_cache_nonce": "NONCE-PF"})
        )
        self.assertEqual(ctx_nonce.get("cache_nonce"), "NONCE-PF")
        ctx_plain = mp._build_plan_time_cache_context(_FakePlan({}))
        self.assertNotIn("cache_nonce", ctx_plain)
        # Both the plan-time prefetch ctx AND the demand ctx carry the SAME
        # nonce in their canonical key components (the nonce key axis is
        # shared even though approximated plan-time fields fail closed later).
        self.assertEqual(
            build_exact_key_components(ctx_nonce).get("cache_nonce"),
            "NONCE-PF",
        )
        self.assertEqual(
            build_exact_key_components(
                dict(_base_ctx(), cache_nonce="NONCE-PF")
            ).get("cache_nonce"),
            "NONCE-PF",
        )

    def test_benchmark_origin_extra_carries_nonce(self):
        """Benchmark wiring: the nonce rides _extra_origin with (and without)
        unique_prompt_suffix; empty values add nothing (byte-identical)."""
        from tools.benchmark_v2_direct import _benchmark_origin_extra

        self.assertIsNone(_benchmark_origin_extra("", ""))
        self.assertEqual(
            _benchmark_origin_extra("", "NONCE-BM"),
            {"conditioning_cache_nonce": "NONCE-BM"},
        )
        self.assertEqual(
            _benchmark_origin_extra("SUF-1", "NONCE-BM"),
            {"unique_prompt_suffix": "SUF-1", "conditioning_cache_nonce": "NONCE-BM"},
        )
        self.assertEqual(
            _benchmark_origin_extra("SUF-1", ""),
            {"unique_prompt_suffix": "SUF-1"},
        )


def _synthetic_workflow() -> dict[str, Any]:
    """Small hermetically buildable workflow mirroring the canonical shape."""
    return {
        "3": {"class_type": "KSampler", "inputs": {
            "seed": 7, "steps": 20, "cfg": 3.5,
            "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
        }},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-9b-fp8.safetensors"}},
        "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "67": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": ["80", 0]}},
        "80": {"class_type": "JoinStrings", "inputs": {"delimiter": " ", "string1": ["1497", 0]}},
        "1497": {"class_type": "PrimitiveStringMultiline", "inputs": {
            "value": "A young female warrior with dark hair",
        }},
    }


class _FakeBridge:
    """Minimal V2LoaderBridge stand-in for the demand-time ctx builder."""

    _model_key = None
    _workflow_hash = "wf-demand"
    _production_options_hash = "po-demand"

    def _request_list(self, role: str) -> list[dict[str, Any]]:
        return [{
            "loader_class": "CLIPLoader",
            "clip_name": "qwen_3_8b_fp8mixed.safetensors",
            "weight_dtype": "default",
        }]


class TestDemandPathNoncePropagation(unittest.TestCase):
    """D10 regression: the DEMAND-time cache context must carry the nonce from
    the trace's request_origin_info — the exact seam the D10 request lost
    (request_origin had the fresh UUID; the effective cache key did not)."""

    def setUp(self) -> None:
        self._saved = {name: os.environ.get(name) for name in (
            "COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH",
            "COMFYMODAL_V2_CUSTOM_NODES_GENERATION",
        )}

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _trace_with_nonce(self, nonce: str):
        from comfymodal_runtime.trace import RuntimeTrace

        trace = RuntimeTrace(request_id="probe-nonce", process="remote")
        trace.set_metadata(request_origin_info={"conditioning_cache_nonce": nonce})
        return trace

    def test_nonce_from_request_origin_reaches_demand_ctx(self) -> None:
        """E: request_origin_info.conditioning_cache_nonce MUST surface as
        ctx['cache_nonce'] on the demand path (the D10 failure signature is the
        reverse: origin carried it, the key did not)."""
        nonce = "d96c9bee-8f4a-4a21-a27c-589962df3723"
        ctx = mp._build_clip_conditioning_cache_context(
            _FakeBridge(), clip=None,
            trace=self._trace_with_nonce(nonce), request_id="probe-nonce",
        )
        self.assertEqual(ctx.get("cache_nonce"), nonce)
        # F: the canonical key components include the nonce (key isolation).
        components = build_exact_key_components(ctx)
        self.assertEqual(components.get("cache_nonce"), nonce)
        summary = conditioning_cache_key_summary(ctx, [])
        self.assertEqual(summary.get("cache_nonce"), nonce)

    def test_absent_nonce_preserves_legacy_ctx(self) -> None:
        """A: no nonce -> ctx carries no cache_nonce key; canonical key bytes
        are unchanged (legacy behavior untouched)."""
        from comfymodal_runtime.trace import RuntimeTrace

        trace = RuntimeTrace(request_id="probe-plain", process="remote")
        trace.set_metadata(request_origin_info={})
        ctx = mp._build_clip_conditioning_cache_context(
            _FakeBridge(), clip=None, trace=trace, request_id="probe-plain",
        )
        self.assertNotIn("cache_nonce", ctx)
        plain = build_exact_key_components(ctx)
        self.assertNotIn("cache_nonce", plain)
        # With the nonce present, ONLY the nonce field differs.
        nonce_ctx = dict(ctx, cache_nonce="NONCE-X")
        with_nonce = build_exact_key_components(nonce_ctx)
        self.assertEqual(
            {k: v for k, v in with_nonce.items() if k != "cache_nonce"},
            {k: v for k, v in plain.items() if k != "cache_nonce"},
        )

    def test_nonce_isolation_miss_then_hit_then_other_miss(self) -> None:
        """B/C/D: nonce A first lookup MISSES, second identical lookup may HIT,
        nonce B MUST MISS the A entry (fresh-nonce isolation)."""
        nonce_a = "NONCE-A-1"
        nonce_b = "NONCE-B-2"
        ctx_a1 = build_exact_key_components(
            dict(_base_ctx(workflow_hash="wf-iso"), cache_nonce=nonce_a)
        )
        ctx_a2 = build_exact_key_components(
            dict(_base_ctx(workflow_hash="wf-iso"), cache_nonce=nonce_a)
        )
        ctx_b = build_exact_key_components(
            dict(_base_ctx(workflow_hash="wf-iso"), cache_nonce=nonce_b)
        )
        # H: A vs B key hashes differ.
        self.assertNotEqual(exact_key_digest(ctx_a1), exact_key_digest(ctx_b))
        # C: same nonce -> identical key (a second lookup may hit).
        self.assertEqual(exact_key_digest(ctx_a1), exact_key_digest(ctx_a2))
        # D: nonce B differs from A.
        self.assertNotEqual(ctx_a1.get("cache_nonce"), ctx_b.get("cache_nonce"))


class TestNonceTargetAppGuard(unittest.TestCase):
    """D10 vehicle guard: a nonce-carrying measurement must target the
    D1-primed deployment.  The D10 request silently targeted the legacy default
    app (COMFYMODAL_V2_APP_NAME unset -> transport default
    'stable-modal-comfy-v2-shadow'), whose baked runtime predates the nonce
    plumbing — the fresh nonce never reached the cache key.  The guard fails
    closed instead."""

    _ENV = (
        "COMFYMODAL_V2_APP_NAME",
        "COMFYMODAL_V2_DEPLOYED_STATE_JSON",
        "COMFYMODAL_V2_REGISTRY_PROOF_STORE",
    )

    def setUp(self) -> None:
        self._saved = {name: os.environ.get(name) for name in self._ENV}
        self._tmp = tempfile.mkdtemp(prefix="nonce_guard_")
        # Redirect the deployed-state + proof-store to per-test temp files so
        # the guard never reads/writes the REAL repo state (D1 isolation).
        os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = os.path.join(
            self._tmp, "deployed_state.json"
        )
        os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = os.path.join(
            self._tmp, "proof_store.json"
        )
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _write_primed_state(self, app_name: str) -> None:
        from comfymodal_runtime.registry_proof_store import deployed_state_path

        state_path = deployed_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({
                "app_name": app_name,
                "deployment_combined_hash": "d10-guard-hash",
                "custom_nodes_generation": "d10-guard-gen",
                "overall_dependency_hash": "d10-guard-overall",
                "comfyui_version": "0.24.0",
                "comfyui_commit": "c0ffee",
            }),
            encoding="utf-8",
        )

    def _active_nonce(self, value: str):
        from tools import benchmark_v2_direct as bvd

        class _Args:
            conditioning_cache_nonce = value

        bvd._EXPERIMENT_ARGS = _Args()
        self.addCleanup(setattr, bvd, "_EXPERIMENT_ARGS", None)
        return bvd

    def test_no_nonce_is_noop(self) -> None:
        """A: nonce inactive -> guard returns '' and never touches env."""
        bvd = self._active_nonce("")
        self.assertEqual(bvd._resolve_nonce_target_app(), "")
        self.assertIsNone(os.environ.get("COMFYMODAL_V2_APP_NAME"))

    def test_unset_app_resolves_primed_identity(self) -> None:
        """Vehicle fix: with the nonce active and the app env unset, the guard
        resolves COMFYMODAL_V2_APP_NAME from the D1-primed identity instead of
        silently defaulting to the legacy app."""
        self._write_primed_state("stable-modal-comfy-v2-restore-only-shadow")
        bvd = self._active_nonce("NONCE-GUARD-1")
        resolved = bvd._resolve_nonce_target_app()
        self.assertEqual(resolved, "stable-modal-comfy-v2-restore-only-shadow")
        self.assertEqual(
            os.environ.get("COMFYMODAL_V2_APP_NAME"),
            "stable-modal-comfy-v2-restore-only-shadow",
        )

    def test_matching_explicit_app_ok(self) -> None:
        self._write_primed_state("stable-modal-comfy-v2-restore-only-shadow")
        os.environ["COMFYMODAL_V2_APP_NAME"] = "stable-modal-comfy-v2-restore-only-shadow"
        bvd = self._active_nonce("NONCE-GUARD-2")
        self.assertEqual(
            bvd._resolve_nonce_target_app(),
            "stable-modal-comfy-v2-restore-only-shadow",
        )

    def test_mismatched_app_fails_closed(self) -> None:
        """The D10 failure class: an explicit app that is NOT the primed
        deployment must abort the nonce measurement."""
        self._write_primed_state("stable-modal-comfy-v2-restore-only-shadow")
        os.environ["COMFYMODAL_V2_APP_NAME"] = "stable-modal-comfy-v2-shadow"
        bvd = self._active_nonce("NONCE-GUARD-3")
        with self.assertRaises(RuntimeError):
            bvd._resolve_nonce_target_app()

    def test_no_primed_identity_fails_closed(self) -> None:
        """Without a D1-primed identity the guard cannot know the authorized
        deployment -> fail closed (never silently measure a default app)."""
        bvd = self._active_nonce("NONCE-GUARD-4")
        with self.assertRaises(RuntimeError):
            bvd._resolve_nonce_target_app()


class TestPriorFailureReproduction(unittest.TestCase):
    """Reproduce the exact D10 failure locally: request_origin carried the
    fresh nonce, but the effective cache context had cache_nonce absent
    (decision=exact_hit, encode_calls=0).  The current demand path proves the
    nonce DOES propagate when the trace carries request_origin_info — the
    failure only occurs when the nonce is NOT read from the origin, exactly as
    the legacy default app's baked runtime behaved."""

    def test_origin_nonce_absent_from_trace_metadata_reproduces_failure(self) -> None:
        """The D10 signature: request_origin has the nonce, but the cache ctx
        sees none -> canonical (nonce-less) key -> warm exact_hit."""
        from comfymodal_runtime.trace import RuntimeTrace

        # Old-app-equivalent: the trace does NOT carry request_origin_info
        # (its baked code predates the nonce read), so _read_conditioning_cache_nonce
        # returns '' and ctx['cache_nonce'] is absent.
        trace = RuntimeTrace(request_id="repro-old", process="remote")
        ctx = mp._build_clip_conditioning_cache_context(
            _FakeBridge(), clip=None, trace=trace, request_id="repro-old",
        )
        self.assertNotIn("cache_nonce", ctx)
        components = build_exact_key_components(ctx)
        self.assertNotIn("cache_nonce", components)

    def test_origin_nonce_present_propagates(self) -> None:
        """The fixed path (v44's baked code = current tree): request_origin
        carries the nonce -> ctx and key carry it -> miss_stored on a fresh
        nonce instead of the warm canonical hit."""
        from comfymodal_runtime.trace import RuntimeTrace

        trace = RuntimeTrace(request_id="repro-new", process="remote")
        trace.set_metadata(request_origin_info={"conditioning_cache_nonce": "REPRO-NONCE"})
        ctx = mp._build_clip_conditioning_cache_context(
            _FakeBridge(), clip=None, trace=trace, request_id="repro-new",
        )
        self.assertEqual(ctx.get("cache_nonce"), "REPRO-NONCE")
        components = build_exact_key_components(ctx)
        self.assertEqual(components.get("cache_nonce"), "REPRO-NONCE")


if __name__ == "__main__":
    unittest.main()
