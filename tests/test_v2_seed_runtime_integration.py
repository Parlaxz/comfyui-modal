"""Focused Step 3 tests: bootstrap + executor seed runtime integration.

Covers:
  - ``BootstrapState.build_snapshot_execution_seed_v2`` builds/stores the
    schema-v2 seed from the canonical workflow while the v1 builder keeps its
    exact existing behavior (no outputs/tensors/request state serialized).
  - ``seed_identity_decision`` / ``PreSamplerCache.consume_snapshot_seed``
    fail-closed identity validation (workflow + deployment).
  - Eligible loader/static structure reuse excludes sampler nodes and never
    serves seed-dependent (dynamic) inputs.
  - ``RuntimeExecutor`` consumes the seed at request start from
    ``context.metadata`` and preserves existing behavior without a seed.

Deterministic and CPU-only: no ComfyUI, no Modal, no CUDA imports.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
from comfymodal_runtime.execution_seed import build_snapshot_execution_seed
from comfymodal_runtime.runtime_bootstrap import BootstrapState
from comfymodal_runtime.runtime_executor import (
    ExecutionContext,
    PreSamplerCache,
    RuntimeExecutor,
    seed_eligible_static_structure,
    seed_identity_decision,
)


# ── Fixtures ───────────────────────────────────────────────────────────────


def _make_workflow() -> dict[str, dict[str, Any]]:
    """Canonical ComfyUI-shaped workflow with an unreachable orphan node."""
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd3.5_large.safetensors"}},
        "6": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "sd3"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["6", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad", "clip": ["6", 0]}},
        "9": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 4.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["5", 0],
                "negative": ["8", 0],
                "latent_image": ["9", 0],
            },
        },
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["7", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["13", 0]}},
        "99": {"class_type": "CLIPTextEncode", "inputs": {"text": "orphan", "clip": ["6", 0]}},
    }


def _build_seed(
    *,
    workflow_hash: str = "wf-hash-1",
    deployment_combined_hash: str = "dep-hash-1",
    custom_node_generation: str = "cn-gen-1",
):
    return build_snapshot_execution_seed(
        _make_workflow(),
        output_node_ids=["12", "13"],
        workflow_hash=workflow_hash,
        deployment_combined_hash=deployment_combined_hash,
        custom_node_generation=custom_node_generation,
    )


def _make_plan(workflow_hash: str = "wf-hash-1") -> ExecutionPlan:
    return ExecutionPlan(
        workflow=_make_workflow(),
        workflow_hash=workflow_hash,
        execution_options=ExecutionOptions(production_enabled=False),
    )


_FORBIDDEN_KEYS = (
    "outputs",
    "latents",
    "conditioning",
    "request_id",
    "client_id",
    "cancellation",
    "progress",
    "random_state",
    "cuda",
)


# ═══════════════════════════════════════════════════════════════════════
# 1. Bootstrap: schema-v2 seed build/store + v1 behavior preserved
# ═══════════════════════════════════════════════════════════════════════


class TestBootstrapBuildSnapshotExecutionSeedV2(unittest.TestCase):
    def test_builds_schema_v2_seed_from_canonical_workflow(self):
        state = BootstrapState()
        seed = state.build_snapshot_execution_seed_v2(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
            custom_node_generation="cn-gen-1",
            deployment_combined_hash="dep-hash-1",
        )
        self.assertIs(state.snapshot_execution_seed, seed)
        self.assertTrue(state.snapshot_seed_built)
        self.assertIs(state.get_snapshot_execution_seed(), seed)
        self.assertEqual(seed.schema_version, 2)
        self.assertEqual(seed.workflow_hash, "wf-hash-1")
        self.assertIn("4", seed.loader_node_ids)  # CheckpointLoaderSimple
        self.assertIn("6", seed.loader_node_ids)  # CLIPLoader
        self.assertIn("7", seed.loader_node_ids)  # VAELoader
        self.assertIn("10", seed.sampler_node_ids)  # KSampler
        self.assertNotIn("99", seed.reachable_node_ids, "orphan must not be reachable")
        self.assertTrue(seed.static_node_signatures)
        self.assertTrue(seed.execution_order_hint)
        # Fully JSON-serializable structural payload.
        payload = seed.to_dict()
        json.dumps(payload)
        for key in _FORBIDDEN_KEYS:
            self.assertNotIn(key, payload, f"forbidden key leaked from v2 seed: {key}")

    def test_v1_builder_behavior_unchanged(self):
        state = BootstrapState()
        seed = state.build_snapshot_execution_seed(
            workflow_hash="wf-v1",
            output_node_ids=["4", "10"],
            loader_node_ids=["4", "6", "7"],
            loader_cache_signatures=[{"node_id": "unet", "signature": "sig-unet"}],
            sampler_node_ids=["10"],
            sampler_static_inputs=[{"node_id": "10", "sampler_name": "euler"}],
            custom_node_generation="gen-1",
            deployment_combined_hash="dep-1",
        )
        self.assertIs(state.snapshot_execution_seed, seed)
        self.assertTrue(state.snapshot_seed_built)
        self.assertEqual(seed.workflow_hash, "wf-v1")
        self.assertEqual(seed.loader_node_ids, ("4", "6", "7"))
        self.assertEqual(seed.loader_cache_signatures[0]["node_id"], "unet")
        self.assertEqual(seed.sampler_node_ids, ("10",))
        self.assertEqual(seed.custom_node_generation, "gen-1")
        self.assertEqual(seed.deployment_combined_hash, "dep-1")
        # v1 payload still readable via from_dict.
        restored = seed.__class__.from_dict(seed.to_dict())
        self.assertEqual(restored.workflow_hash, "wf-v1")

    def test_v2_builder_does_not_touch_loader_outputs_or_identities(self):
        state = BootstrapState()
        # Pre-existing runtime state must survive a v2 rebuild untouched.
        fake = object()
        state.snapshot_loader_outputs = {"unet": fake}
        state.snapshot_model_identities = {"unet": "unet-id"}
        state.build_snapshot_execution_seed_v2(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
        )
        self.assertIs(state.snapshot_loader_outputs["unet"], fake)
        self.assertEqual(state.snapshot_model_identities["unet"], "unet-id")


# ═══════════════════════════════════════════════════════════════════════
# 2. Consumer identity validation (fail-closed)
# ═══════════════════════════════════════════════════════════════════════


class TestSeedIdentityDecision(unittest.TestCase):
    def test_no_seed_is_no_op(self):
        decision = seed_identity_decision(None)
        self.assertEqual(decision["status"], "no_seed")
        self.assertFalse(decision["reuse_enabled"])

    def test_match_enables_reuse(self):
        seed = _build_seed()
        decision = seed_identity_decision(
            seed,
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
            custom_node_generation="cn-gen-1",
        )
        self.assertEqual(decision["status"], "match")
        self.assertTrue(decision["reuse_enabled"])
        self.assertEqual(decision["reasons"], [])

    def test_dict_seed_is_normalized(self):
        seed = _build_seed()
        decision = seed_identity_decision(
            seed.to_dict(),
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
            custom_node_generation="cn-gen-1",
        )
        self.assertTrue(decision["reuse_enabled"])

    def test_workflow_hash_mismatch_fails_closed(self):
        seed = _build_seed()
        decision = seed_identity_decision(
            seed,
            workflow_hash="wf-different",
            deployment_combined_hash="dep-hash-1",
        )
        self.assertEqual(decision["status"], "identity_mismatch")
        self.assertFalse(decision["reuse_enabled"])
        self.assertIn("workflow_hash_mismatch", decision["reasons"])

    def test_deployment_hash_mismatch_fails_closed(self):
        seed = _build_seed()
        decision = seed_identity_decision(
            seed,
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-different",
        )
        self.assertFalse(decision["reuse_enabled"])
        self.assertIn("deployment_hash_mismatch", decision["reasons"])

    def test_seed_with_deployment_hash_but_no_request_hash_fails_closed(self):
        seed = _build_seed(deployment_combined_hash="dep-hash-1")
        decision = seed_identity_decision(
            seed,
            workflow_hash="wf-hash-1",
            deployment_combined_hash="",
        )
        self.assertFalse(decision["reuse_enabled"])
        self.assertIn("deployment_hash_unverifiable", decision["reasons"])

    def test_seed_without_deployment_hash_is_accepted(self):
        seed = build_snapshot_execution_seed(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
            deployment_combined_hash="",
        )
        decision = seed_identity_decision(
            seed,
            workflow_hash="wf-hash-1",
            deployment_combined_hash="",
        )
        self.assertEqual(decision["status"], "match")
        self.assertTrue(decision["reuse_enabled"])


# ═══════════════════════════════════════════════════════════════════════
# 3. Eligible loader/static reuse — never sampler, never dynamic
# ═══════════════════════════════════════════════════════════════════════


class TestSeedEligibleStaticStructure(unittest.TestCase):
    def test_sampler_nodes_never_eligible(self):
        seed = _build_seed()
        eligible = seed_eligible_static_structure(seed)
        self.assertNotIn("10", eligible, "KSampler must never be reusable")
        # Loader nodes are eligible (their filenames/options are static).
        self.assertIn("4", eligible)
        self.assertIn("6", eligible)
        self.assertIn("7", eligible)

    def test_empty_seed_returns_empty(self):
        from comfymodal_runtime.contracts import SnapshotExecutionSeed
        self.assertEqual(seed_eligible_static_structure(None), {})
        self.assertEqual(seed_eligible_static_structure(SnapshotExecutionSeed()), {})


class TestPreSamplerCacheSeedConsumption(unittest.TestCase):
    def _cache(self) -> PreSamplerCache:
        return PreSamplerCache()

    @staticmethod
    def _consume_match(cache: PreSamplerCache) -> dict[str, Any]:
        """Consume a fully-identity-matching seed."""
        return cache.consume_snapshot_seed(
            _build_seed(),
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
            custom_node_generation="cn-gen-1",
        )

    def test_consume_match_enables_reuse(self):
        cache = self._cache()
        decision = self._consume_match(cache)
        self.assertTrue(decision["reuse_enabled"])
        self.assertTrue(cache.seed_reuse_enabled)
        self.assertEqual((cache.seed_decision or {}).get("status"), "match")

    def test_consume_mismatch_fails_closed(self):
        cache = self._cache()
        decision = cache.consume_snapshot_seed(
            _build_seed(),
            workflow_hash="wf-different",
            deployment_combined_hash="dep-hash-1",
            custom_node_generation="cn-gen-1",
        )
        self.assertFalse(decision["reuse_enabled"])
        self.assertFalse(cache.seed_reuse_enabled)
        # Nothing reusable is retained.
        self.assertIsNone(cache.reuse_seed_static_inputs("4", "CheckpointLoaderSimple", {"ckpt_name": "sd3.5_large.safetensors"}))

    def test_consume_no_seed_preserves_behavior(self):
        cache = self._cache()
        decision = cache.consume_snapshot_seed(None)
        self.assertEqual(decision["status"], "no_seed")
        self.assertFalse(cache.seed_reuse_enabled)
        # Normal input resolution still works without any seed.
        resolved = cache.resolve_inputs("4", "CheckpointLoaderSimple", {"ckpt_name": "x.safetensors"})
        self.assertEqual(resolved, {"ckpt_name": "x.safetensors"})

    def test_eligible_loader_static_inputs_are_reused(self):
        cache = self._cache()
        self._consume_match(cache)
        # CheckpointLoaderSimple node 4 recorded static inputs match exactly.
        reused = cache.reuse_seed_static_inputs("4", "CheckpointLoaderSimple", {"ckpt_name": "sd3.5_large.safetensors"})
        self.assertEqual(reused, {"ckpt_name": "sd3.5_large.safetensors"})

    def test_dynamic_input_prevents_reuse(self):
        cache = self._cache()
        self._consume_match(cache)
        # CLIPTextEncode node 5 has dynamic text; a differing prompt must not
        # reuse the recorded (clip-only) static inputs.
        self.assertIsNone(
            cache.reuse_seed_static_inputs("5", "CLIPTextEncode", {"text": "different", "clip": ["6", 0]})
        )

    def test_sampler_inputs_never_reused(self):
        cache = self._cache()
        self._consume_match(cache)
        # Even an exact-match static subset on a sampler node must not reuse.
        self.assertIsNone(
            cache.reuse_seed_static_inputs("10", "KSampler", {"sampler_name": "euler"})
        )

    def test_resolve_inputs_uses_seed_without_builder(self):
        cache = self._cache()
        self._consume_match(cache)
        calls: list[str] = []

        def builder() -> dict[str, Any]:
            calls.append("builder-called")
            return {"ckpt_name": "built"}

        resolved = cache.resolve_inputs(
            "4", "CheckpointLoaderSimple",
            {"ckpt_name": "sd3.5_large.safetensors"},
            builder=builder,
        )
        self.assertEqual(resolved, {"ckpt_name": "sd3.5_large.safetensors"})
        self.assertEqual(calls, [], "builder must not run when seed static inputs are reused")
        # The reused hit is recorded as a cache hit.
        summary = cache.to_summary_dict()
        self.assertGreaterEqual(summary["operation_hits"].get("cache_lookup", 0), 1)

    def test_resolve_inputs_falls_back_to_builder_on_mismatch(self):
        cache = self._cache()
        self._consume_match(cache)
        calls: list[str] = []

        def builder() -> dict[str, Any]:
            calls.append("builder-called")
            return {"ckpt_name": "different.safetensors"}

        resolved = cache.resolve_inputs(
            "4", "CheckpointLoaderSimple",
            {"ckpt_name": "different.safetensors"},
            builder=builder,
        )
        self.assertEqual(resolved, {"ckpt_name": "different.safetensors"})
        self.assertEqual(calls, ["builder-called"])

    def test_sampler_never_reused_in_resolve_inputs(self):
        cache = self._cache()
        self._consume_match(cache)
        calls: list[str] = []

        def builder() -> dict[str, Any]:
            calls.append("builder-called")
            return {"sampler_name": "euler"}

        resolved = cache.resolve_inputs(
            "10", "KSampler", {"sampler_name": "euler"}, builder=builder,
        )
        self.assertEqual(resolved, {"sampler_name": "euler"})
        self.assertEqual(calls, ["builder-called"], "sampler node must never reuse seed data")


# ═══════════════════════════════════════════════════════════════════════
# 4. RuntimeExecutor request-start consumption
# ═══════════════════════════════════════════════════════════════════════


class TestRuntimeExecutorSeedConsumption(unittest.IsolatedAsyncioTestCase):
    async def _execute(
        self, plan: ExecutionPlan, metadata: dict[str, Any]
    ) -> tuple[dict[str, Any], ExecutionContext]:
        executor = RuntimeExecutor(in_process_runner=lambda p, c: {"result": "ok"})
        ctx = ExecutionContext(request_id="req-1", metadata=metadata)
        result = await executor.execute(plan, context=ctx)
        return result, ctx

    async def test_seed_consumed_from_context_metadata(self):
        plan = _make_plan("wf-hash-1")
        metadata: dict[str, Any] = {
            "snapshot_execution_seed": _build_seed(),
            "deployment_combined_hash": "dep-hash-1",
            "custom_node_generation": "cn-gen-1",
        }
        _result, ctx = await self._execute(plan, metadata)
        decision = ctx.metadata.get("snapshot_seed_decision")
        self.assertIsNotNone(decision, "seed decision must be recorded")
        assert decision is not None
        self.assertEqual(decision["status"], "match")
        self.assertTrue(decision["reuse_enabled"])
        cache = ctx.metadata["pre_sampler_cache"]
        self.assertTrue(cache.seed_reuse_enabled)

    async def test_identity_mismatch_fails_closed_but_runs(self):
        plan = _make_plan("wf-hash-1")
        metadata: dict[str, Any] = {
            "snapshot_execution_seed": _build_seed(),
            "deployment_combined_hash": "dep-different",
        }
        _result, ctx = await self._execute(plan, metadata)
        decision = ctx.metadata.get("snapshot_seed_decision")
        assert decision is not None
        self.assertEqual(decision["status"], "identity_mismatch")
        self.assertFalse(decision["reuse_enabled"])
        self.assertIn("deployment_hash_mismatch", decision["reasons"])
        cache = ctx.metadata["pre_sampler_cache"]
        self.assertFalse(cache.seed_reuse_enabled)

    async def test_no_seed_preserves_existing_behavior(self):
        plan = _make_plan("wf-hash-1")
        _result, ctx = await self._execute(plan, {})
        self.assertNotIn("snapshot_seed_decision", ctx.metadata)
        cache = ctx.metadata["pre_sampler_cache"]
        self.assertFalse(cache.seed_reuse_enabled)
        self.assertIsNone(cache.seed_decision)

    async def test_plan_request_metadata_deployment_hash_is_used(self):
        seed = _build_seed()
        plan = ExecutionPlan(
            workflow=_make_workflow(),
            workflow_hash="wf-hash-1",
            execution_options=ExecutionOptions(production_enabled=False),
            request_metadata={
                "deployment_combined_hash": "dep-hash-1",
                "custom_node_generation": "cn-gen-1",
            },
        )
        _result, ctx = await self._execute(
            plan,
            {"snapshot_execution_seed": seed},
        )
        decision = ctx.metadata.get("snapshot_seed_decision")
        assert decision is not None
        self.assertEqual(decision["status"], "match", f"reasons={decision.get('reasons')}")

    async def test_stream_consumes_seed(self):
        executor = RuntimeExecutor(
            in_process_runner=lambda p, c: iter([{"type": "result", "data": {"ok": True}}])
        )
        plan = _make_plan("wf-hash-1")
        ctx = ExecutionContext(
            request_id="req-stream",
            metadata={
                "snapshot_execution_seed": _build_seed(),
                "deployment_combined_hash": "dep-hash-1",
                "custom_node_generation": "cn-gen-1",
            },
        )
        events = [event async for event in executor.stream(plan, context=ctx)]
        self.assertEqual(len(events), 1)
        decision = ctx.metadata.get("snapshot_seed_decision")
        assert decision is not None
        self.assertEqual(decision["status"], "match")


if __name__ == "__main__":
    unittest.main()
