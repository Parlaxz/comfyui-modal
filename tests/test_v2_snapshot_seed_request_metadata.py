"""Focused Step 3 tests: production wiring of restore-time snapshot-seed metadata.

Covers the request chokepoint ``ModalRuntimeEntrypoint._run_plan_stream_impl``:

  - The frozen restore-time seed is attached to the per-request
    ``ExecutionContext.metadata`` (plus deployment-identity and
    custom-node-generation values) with defensive ``getattr``, so cold
    instances without bootstrap state degrade to ``None``/"".
  - A matching restore-time seed enables a ``match`` seed decision through
    the real executor consumption path.
  - A missing seed remains a no-op (no decision recorded, execution runs).
  - Workflow / deployment identity mismatch fails closed while execution
    continues (a result event is still produced).
  - Metadata hygiene: only the three identity keys are attached; shared
    bootstrap state is never mutated; no v2 seed is rebuilt from
    ``plan.workflow`` at request time; no workflow/output/tensor/request
    state is persisted in metadata.

Deterministic and CPU-only: no ComfyUI, no Modal, no CUDA imports.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
from comfymodal_runtime.execution_seed import build_snapshot_execution_seed
from comfymodal_runtime.runtime_bootstrap import RuntimeBootstrap
from comfymodal_runtime.runtime_executor import ExecutionContext, RuntimeExecutor

import comfymodal_runtime.modal_app as modal_app

# Restore-time identity fixtures shared by every test.
_DEPLOYMENT_HASH = "dep-hash-1"
_CUSTOM_NODE_GENERATION = "cn-gen-1"
_WORKFLOW_HASH = "wf-hash-1"

# Keys the chokepoint must NEVER persist in per-request metadata.
_FORBIDDEN_METADATA_KEYS = (
    "workflow",
    "outputs",
    "tensors",
    "latents",
    "conditioning",
    "request_id",
    "client_id",
    "cancellation",
    "progress",
    "random_state",
    "cuda",
    "plan",
    "prompt",
)


# ── Fixtures ───────────────────────────────────────────────────────────────


def _make_workflow() -> dict[str, dict[str, Any]]:
    """Canonical ComfyUI-shaped workflow (same shape as the Step 3 fixtures)."""
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
    workflow_hash: str = _WORKFLOW_HASH,
    deployment_combined_hash: str = _DEPLOYMENT_HASH,
    custom_node_generation: str = _CUSTOM_NODE_GENERATION,
):
    """Build a deterministic snapshot execution seed with matching identity."""
    return build_snapshot_execution_seed(
        _make_workflow(),
        output_node_ids=["12", "13"],
        workflow_hash=workflow_hash,
        deployment_combined_hash=deployment_combined_hash,
        custom_node_generation=custom_node_generation,
    )


def _make_plan(workflow_hash: str = _WORKFLOW_HASH) -> ExecutionPlan:
    return ExecutionPlan(
        workflow=_make_workflow(),
        workflow_hash=workflow_hash,
        execution_options=ExecutionOptions(production_enabled=False),
    )


def _runner(plan: ExecutionPlan, ctx: ExecutionContext) -> dict[str, Any]:
    """Trivial in-process runner: mirrors test_modal_app_identity._entrypoint."""
    return {
        "result": "ok",
        "trace": modal_app.RuntimeTrace(process="remote").to_dict(),
    }


class _RecordingExecutor:
    """Wraps a RuntimeExecutor and captures the context at the chokepoint."""

    def __init__(self, inner: RuntimeExecutor) -> None:
        self._inner = inner
        self.captured_contexts: list[ExecutionContext | None] = []

    def stream(self, plan: ExecutionPlan, *, context: ExecutionContext | None = None):
        self.captured_contexts.append(context)
        return self._inner.stream(plan, context=context)


# ═══════════════════════════════════════════════════════════════════════
# Chokepoint wiring: run_plan_stream → metadata attachment → seed decision
# ═══════════════════════════════════════════════════════════════════════


class TestSnapshotSeedRequestMetadata(unittest.IsolatedAsyncioTestCase):
    """The real run_plan_stream chokepoint attaches and consumes the seed."""

    def _make_entrypoint(
        self, bootstrap: RuntimeBootstrap
    ) -> tuple[Any, _RecordingExecutor]:
        real = RuntimeExecutor(in_process_runner=_runner)
        recorder = _RecordingExecutor(real)
        entrypoint = modal_app.ModalRuntimeEntrypoint(
            bootstrap=bootstrap,
            executor=recorder,  # type: ignore[arg-type]  # duck-typed stream()
        )
        return entrypoint, recorder

    @staticmethod
    async def _collect(entrypoint: Any, plan: ExecutionPlan) -> list[dict[str, Any]]:
        return [
            msg
            async for msg in entrypoint.run_plan_stream(
                plan.to_dict(), request_id="req-step3"
            )
        ]

    def _bootstrap_with_frozen_seed(self) -> RuntimeBootstrap:
        bootstrap = RuntimeBootstrap()
        bootstrap.state.snapshot_execution_seed = _build_seed()
        bootstrap.state.deployment_combined_hash = _DEPLOYMENT_HASH
        bootstrap.state.snapshot_custom_node_generation = _CUSTOM_NODE_GENERATION
        return bootstrap

    async def test_matching_seed_attaches_and_enables_match_decision(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = self._bootstrap_with_frozen_seed()
            entrypoint, recorder = self._make_entrypoint(bootstrap)
            messages = await self._collect(entrypoint, _make_plan(_WORKFLOW_HASH))

            self.assertEqual(len(recorder.captured_contexts), 1)
            ctx = recorder.captured_contexts[0]
            assert ctx is not None
            # Exactly the three identity keys were attached from bootstrap state.
            self.assertIs(ctx.metadata["snapshot_execution_seed"], bootstrap.state.snapshot_execution_seed)
            self.assertEqual(ctx.metadata["deployment_combined_hash"], _DEPLOYMENT_HASH)
            self.assertEqual(ctx.metadata["custom_node_generation"], _CUSTOM_NODE_GENERATION)
            # The real executor consumption path enabled a match decision.
            decision = ctx.metadata["snapshot_seed_decision"]
            self.assertEqual(decision["status"], "match")
            self.assertTrue(decision["reuse_enabled"])
            self.assertEqual(decision["reasons"], [])
            self.assertTrue(ctx.metadata["pre_sampler_cache"].seed_reuse_enabled)
            # Execution still ran to completion.
            self.assertTrue(any(m.get("type") == "result" for m in messages))

    async def test_missing_seed_is_noop(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = RuntimeBootstrap()  # default state: no frozen seed
            entrypoint, recorder = self._make_entrypoint(bootstrap)
            messages = await self._collect(entrypoint, _make_plan(_WORKFLOW_HASH))

            ctx = recorder.captured_contexts[0]
            assert ctx is not None
            # Key attached (as None) but no seed decision is recorded.
            self.assertIsNone(ctx.metadata["snapshot_execution_seed"])
            self.assertNotIn("snapshot_seed_decision", ctx.metadata)
            self.assertFalse(ctx.metadata["pre_sampler_cache"].seed_reuse_enabled)
            self.assertIsNone(ctx.metadata["pre_sampler_cache"].seed_decision)
            # Execution still ran to completion.
            self.assertTrue(any(m.get("type") == "result" for m in messages))

    async def test_workflow_mismatch_fails_closed_execution_continues(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = self._bootstrap_with_frozen_seed()
            entrypoint, recorder = self._make_entrypoint(bootstrap)
            messages = await self._collect(entrypoint, _make_plan("wf-different"))

            ctx = recorder.captured_contexts[0]
            assert ctx is not None
            decision = ctx.metadata["snapshot_seed_decision"]
            self.assertEqual(decision["status"], "identity_mismatch")
            self.assertFalse(decision["reuse_enabled"])
            self.assertIn("workflow_hash_mismatch", decision["reasons"])
            self.assertFalse(ctx.metadata["pre_sampler_cache"].seed_reuse_enabled)
            # Fail-closed on seed reuse, but execution continues.
            self.assertTrue(any(m.get("type") == "result" for m in messages))

    async def test_deployment_mismatch_fails_closed_execution_continues(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = self._bootstrap_with_frozen_seed()
            # Simulate a running deployment whose combined hash differs from
            # the one frozen into the snapshot seed.
            bootstrap.state.deployment_combined_hash = "dep-different"
            entrypoint, recorder = self._make_entrypoint(bootstrap)
            messages = await self._collect(entrypoint, _make_plan(_WORKFLOW_HASH))

            ctx = recorder.captured_contexts[0]
            assert ctx is not None
            self.assertEqual(ctx.metadata["deployment_combined_hash"], "dep-different")
            decision = ctx.metadata["snapshot_seed_decision"]
            self.assertEqual(decision["status"], "identity_mismatch")
            self.assertFalse(decision["reuse_enabled"])
            self.assertIn("deployment_hash_mismatch", decision["reasons"])
            # Fail-closed on seed reuse, but execution continues.
            self.assertTrue(any(m.get("type") == "result" for m in messages))


# ═══════════════════════════════════════════════════════════════════════
# Metadata hygiene + defensive cold-instance behavior
# ═══════════════════════════════════════════════════════════════════════


class TestSnapshotSeedMetadataHygiene(unittest.TestCase):
    """Unit tests for _attach_snapshot_seed_metadata itself."""

    def test_attaches_exactly_three_keys_and_never_mutates_state(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = RuntimeBootstrap()
            seed = _build_seed()
            bootstrap.state.snapshot_execution_seed = seed
            bootstrap.state.deployment_combined_hash = _DEPLOYMENT_HASH
            bootstrap.state.snapshot_custom_node_generation = _CUSTOM_NODE_GENERATION
            entrypoint = modal_app.ModalRuntimeEntrypoint(bootstrap=bootstrap)

            ctx = ExecutionContext(request_id="req-hygiene")
            before = dict(ctx.metadata)
            entrypoint._attach_snapshot_seed_metadata(ctx)

            added = set(ctx.metadata) - set(before)
            self.assertEqual(
                added,
                {"snapshot_execution_seed", "deployment_combined_hash", "custom_node_generation"},
            )
            self.assertIs(ctx.metadata["snapshot_execution_seed"], seed)
            self.assertEqual(ctx.metadata["deployment_combined_hash"], _DEPLOYMENT_HASH)
            self.assertEqual(ctx.metadata["custom_node_generation"], _CUSTOM_NODE_GENERATION)
            # Shared bootstrap state is untouched and no v2 seed was rebuilt.
            self.assertIs(bootstrap.state.snapshot_execution_seed, seed)
            self.assertFalse(bootstrap.state.snapshot_seed_built, "seed must not be rebuilt at request time")
            self.assertEqual(bootstrap.state.deployment_combined_hash, _DEPLOYMENT_HASH)
            self.assertEqual(bootstrap.state.snapshot_custom_node_generation, _CUSTOM_NODE_GENERATION)
            # No workflow/output/tensor/request state is persisted in metadata.
            for key in _FORBIDDEN_METADATA_KEYS:
                self.assertNotIn(key, ctx.metadata, f"forbidden metadata key leaked: {key}")

    def test_deployment_hash_prefers_module_constant_over_state(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", "dep-module-hash"):
            bootstrap = RuntimeBootstrap()
            bootstrap.state.deployment_combined_hash = "dep-state-hash"
            entrypoint = modal_app.ModalRuntimeEntrypoint(bootstrap=bootstrap)

            ctx = ExecutionContext(request_id="req-pref")
            entrypoint._attach_snapshot_seed_metadata(ctx)
            self.assertEqual(ctx.metadata["deployment_combined_hash"], "dep-module-hash")

    def test_deployment_hash_falls_back_to_state_when_constant_empty(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = RuntimeBootstrap()
            bootstrap.state.deployment_combined_hash = "dep-state-hash"
            entrypoint = modal_app.ModalRuntimeEntrypoint(bootstrap=bootstrap)

            ctx = ExecutionContext(request_id="req-fallback")
            entrypoint._attach_snapshot_seed_metadata(ctx)
            self.assertEqual(ctx.metadata["deployment_combined_hash"], "dep-state-hash")

    def test_custom_node_generation_prefers_snapshot_frozen_value(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = RuntimeBootstrap()
            bootstrap.state.custom_node_generation = "live-gen"
            bootstrap.state.snapshot_custom_node_generation = "frozen-gen"
            entrypoint = modal_app.ModalRuntimeEntrypoint(bootstrap=bootstrap)

            ctx = ExecutionContext(request_id="req-cn")
            entrypoint._attach_snapshot_seed_metadata(ctx)
            self.assertEqual(ctx.metadata["custom_node_generation"], "frozen-gen")

    def test_custom_node_generation_falls_back_to_live_value(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            bootstrap = RuntimeBootstrap()
            bootstrap.state.custom_node_generation = "live-gen"
            # snapshot_custom_node_generation stays "" (default).
            entrypoint = modal_app.ModalRuntimeEntrypoint(bootstrap=bootstrap)

            ctx = ExecutionContext(request_id="req-cn2")
            entrypoint._attach_snapshot_seed_metadata(ctx)
            self.assertEqual(ctx.metadata["custom_node_generation"], "live-gen")

    def test_cold_instance_without_bootstrap_state_is_defensive(self):
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            # Simulate a cold-unpickled instance that lacks bootstrap state.
            entrypoint = object.__new__(modal_app.ModalRuntimeEntrypoint)
            ctx = ExecutionContext(request_id="req-cold")
            entrypoint._attach_snapshot_seed_metadata(ctx)  # must not raise
            self.assertIsNone(ctx.metadata["snapshot_execution_seed"])
            self.assertEqual(ctx.metadata["deployment_combined_hash"], "")
            self.assertEqual(ctx.metadata["custom_node_generation"], "")


if __name__ == "__main__":
    unittest.main()
