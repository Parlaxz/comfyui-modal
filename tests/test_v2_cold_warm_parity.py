"""Step 3 cold/warm parity + executor seed-apply seam tests.

Covers the bounded Step 3 corrections:

  - Publisher-side schema-v2 seed payload build → persist → hydrate round trip
    (``FakeVolume``/``MountedStateVolume`` based, deployment-scoped JSON).
  - Honest minimal schema-v2 fallback (``seed_source=startup_minimal``,
    ``topology_available=False``) when no persisted payload is available.
  - ``apply_snapshot_seed_to_executor``:
      * identity mismatch fails closed and continues
      * stale loader entries are invalidated (deleted) and reported
      * loader entries are NEVER inserted/replaced
      * sampler entries are NEVER touched
      * budget is measured with ``within_budget``
      * no forbidden state is ever stored
  - Cold/warm request parity: a frozen hydrated seed produces identical
    decisions and executor results on the first (cold) and later (warm)
    requests, without mutating shared bootstrap state per request.

Deterministic and CPU-only: no ComfyUI, no Modal, no CUDA imports.
"""

from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, SnapshotExecutionSeed
from comfymodal_runtime.execution_seed import (
    build_snapshot_execution_seed,
    build_snapshot_seed_payload,
    minimal_snapshot_seed_payload,
    persist_snapshot_seed_payload,
    read_snapshot_seed_payload,
    snapshot_seed_observability,
    snapshot_seed_payload_from_dict,
)
from comfymodal_runtime.runtime_bootstrap import BootstrapState
from comfymodal_runtime.runtime_executor import (
    ExecutionContext,
    RuntimeExecutor,
    apply_snapshot_seed_to_executor,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_workflow() -> dict[str, dict[str, Any]]:
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd3.5_large.safetensors"}},
        "6": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "sd3"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["6", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad", "clip": ["6", 0]}},
        "9": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42, "steps": 20, "cfg": 4.5,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                "model": ["4", 0], "positive": ["5", 0], "negative": ["8", 0],
                "latent_image": ["9", 0],
            },
        },
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["7", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["13", 0]}},
    }


def _build_seed(
    *,
    workflow_hash: str = "wf-hash-1",
    deployment_combined_hash: str = "dep-hash-1",
    custom_node_generation: str = "cn-gen-1",
) -> SnapshotExecutionSeed:
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


class _OutputsCache:
    """Fake executor outputs cache: tracks deletes/sets so tests can prove
    invalidation-only behavior."""

    def __init__(self, seeded: dict[str, Any] | None = None) -> None:
        self.cache_key_set = types.SimpleNamespace(get_data_key=lambda n: f"key_{n}")
        self.initialized = True
        self._store: dict[str, Any] = dict(seeded or {})
        self.deleted: list[str] = []
        self.set_calls: list[str] = []

    async def set_prompt(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return {"prompt": "ok"}

    async def delete(self, node_id: str) -> None:
        self.deleted.append(node_id)
        self._store.pop(node_id, None)

    async def get(self, node_id: str) -> Any:
        return self._store.get(node_id)

    async def set(self, node_id: str, entry: Any) -> None:
        self.set_calls.append(node_id)
        self._store[node_id] = entry


class _FakeExecutor:
    def __init__(self, seeded: dict[str, Any] | None = None) -> None:
        self.caches = types.SimpleNamespace(outputs=_OutputsCache(seeded=seeded))


# ── 1. Published payload build → persist → hydrate ─────────────────────────


class TestPublishedSeedPayloadRoundTrip(unittest.TestCase):
    def test_build_payload_topology_and_seed(self):
        payload = build_snapshot_seed_payload(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["seed_source"], "publisher_plan")
        self.assertTrue(payload["topology_available"])
        seed = SnapshotExecutionSeed.from_dict(payload["seed"])
        self.assertEqual(seed.schema_version, 2)
        # Topology/static data present — never outputs/tensors/request state.
        self.assertTrue(seed.reachable_node_ids)
        self.assertTrue(seed.static_node_signatures)
        self.assertIn("10", seed.sampler_node_ids)
        self.assertTrue(seed.loader_node_ids)

    def test_empty_workflow_returns_none(self):
        self.assertIsNone(build_snapshot_seed_payload({}))

    def test_persist_and_read_round_trip(self):
        payload = build_snapshot_seed_payload(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
        )
        assert payload is not None
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(persist_snapshot_seed_payload(payload, root=tmp))
            loaded = read_snapshot_seed_payload(root=tmp)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["seed_source"], "publisher_plan")
        self.assertTrue(loaded["topology_available"])
        self.assertEqual(loaded["workflow_hash"], payload["workflow_hash"])

    def test_read_missing_or_invalid_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_snapshot_seed_payload(root=tmp))
            Path(tmp, "snapshot_seed.json").write_text(
                json.dumps({"seed_source": "publisher_plan", "seed": {"schema_version": 1}}),
                encoding="utf-8",
            )
            self.assertIsNone(read_snapshot_seed_payload(root=tmp))

    def test_payload_from_dict_rejects_forbidden_shape(self):
        self.assertIsNone(snapshot_seed_payload_from_dict({"seed": {"schema_version": 2}}))
        self.assertIsNone(snapshot_seed_payload_from_dict(None))
        self.assertIsNone(snapshot_seed_payload_from_dict({"seed_source": "unknown", "seed": {}}))

    def test_state_hydrates_persisted_payload(self):
        payload = build_snapshot_seed_payload(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
        )
        assert payload is not None
        state = BootstrapState()
        self.assertTrue(state.hydrate_snapshot_seed_payload(payload))
        self.assertTrue(state.snapshot_seed_built)
        self.assertEqual(state.snapshot_seed_source, "publisher_plan")
        self.assertTrue(state.snapshot_seed_topology_available)
        self.assertEqual(state.snapshot_seed_schema_version, 2)
        self.assertEqual(state.snapshot_seed_workflow_hash, payload["workflow_hash"])
        seed = state.get_snapshot_execution_seed()
        self.assertIsNotNone(seed)
        assert seed is not None
        self.assertEqual(seed.schema_version, 2)
        self.assertTrue(seed.static_node_signatures)

    def test_state_rejects_invalid_payload(self):
        state = BootstrapState()
        self.assertFalse(state.hydrate_snapshot_seed_payload({"seed_source": "unknown", "seed": {}}))
        self.assertFalse(state.snapshot_seed_built)


# ── 2. Minimal fallback (startup_minimal) ─────────────────────────────────


class TestMinimalFallbackSeed(unittest.TestCase):
    def test_minimal_payload_shape(self):
        payload = minimal_snapshot_seed_payload(
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["seed_source"], "startup_minimal")
        self.assertFalse(payload["topology_available"])
        seed = SnapshotExecutionSeed.from_dict(payload["seed"])
        self.assertEqual(seed.schema_version, 2)
        # Minimal: identity only — no topology/static data.
        self.assertEqual(seed.static_node_signatures, ())
        self.assertEqual(seed.reachable_node_ids, ())
        self.assertEqual(seed.loader_node_ids, ())
        self.assertEqual(seed.workflow_hash, "wf-hash-1")

    def test_state_builds_minimal_seed(self):
        state = BootstrapState()
        seed = state.build_minimal_snapshot_seed_v2(
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
            custom_node_generation="cn-gen-1",
            loader_cache_signatures=[{"node_id": "unet", "signature": "abc"}],
        )
        self.assertEqual(seed.schema_version, 2)
        self.assertTrue(state.snapshot_seed_built)
        self.assertEqual(state.snapshot_seed_source, "startup_minimal")
        self.assertFalse(state.snapshot_seed_topology_available)
        self.assertEqual(state.snapshot_seed_schema_version, 2)
        # Never stores forbidden state.
        obs = snapshot_seed_observability(state.snapshot_execution_seed)
        self.assertEqual(obs["schema_version"], 2)
        self.assertFalse(obs["topology_available"])
        self.assertEqual(obs["static_signature_count"], 0)

    def test_observability_never_stores_forbidden_keys(self):
        payload = build_snapshot_seed_payload(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
        )
        assert payload is not None
        obs = snapshot_seed_observability(SnapshotExecutionSeed.from_dict(payload["seed"]))
        for key in ("outputs", "latents", "conditioning", "request_id", "cuda", "random_state"):
            self.assertNotIn(key, obs)


# ── 3. apply_snapshot_seed_to_executor ────────────────────────────────────


class TestApplySnapshotSeedToExecutor(unittest.IsolatedAsyncioTestCase):
    async def _marker(
        self,
        executor: _FakeExecutor,
        seed: Any,
        *,
        workflow: dict[str, Any] | None = None,
        workflow_hash: str = "wf-hash-1",
        deployment_combined_hash: str = "dep-hash-1",
    ) -> dict[str, Any]:
        return await apply_snapshot_seed_to_executor(
            executor,
            seed,
            workflow=workflow if workflow is not None else _make_workflow(),
            workflow_hash=workflow_hash,
            source_workflow_hash=workflow_hash,
            deployment_combined_hash=deployment_combined_hash,
            custom_node_generation="cn-gen-1",
        )

    async def test_match_verifies_and_never_inserts(self):
        executor = _FakeExecutor(seeded={"4": "e", "6": "e"})
        marker = await self._marker(executor, _build_seed())
        self.assertEqual(marker["decision"], "match")
        self.assertEqual(marker["schema"], 2)
        self.assertTrue(marker["within_budget"])
        self.assertEqual(marker["verified"], 3)  # "4" + "6" + "7" loaders
        self.assertEqual(marker["invalidated"], 0)
        self.assertTrue(marker["sampler_untouched"])
        self.assertEqual(marker["fallback_reason"], "none")
        self.assertEqual(executor.caches.outputs.set_calls, [])
        self.assertEqual(executor.caches.outputs.deleted, [])

    async def test_identity_mismatch_fails_closed_and_continues(self):
        executor = _FakeExecutor(seeded={"4": "e", "6": "e"})
        marker = await self._marker(executor, _build_seed(), deployment_combined_hash="dep-different")
        self.assertEqual(marker["decision"], "identity_mismatch")
        self.assertIn("deployment_hash_mismatch", marker["fallback_reason"])
        self.assertEqual(marker["verified"], 0)
        self.assertEqual(marker["invalidated"], 0)
        self.assertTrue(marker["sampler_untouched"])
        # Nothing mutated.
        self.assertEqual(executor.caches.outputs.set_calls, [])
        self.assertEqual(executor.caches.outputs.deleted, [])

    async def test_no_seed_is_honest_fallback(self):
        executor = _FakeExecutor(seeded={"4": "e"})
        marker = await self._marker(executor, None)
        self.assertEqual(marker["decision"], "no_seed")
        self.assertEqual(marker["fallback_reason"], "no_seed")
        self.assertTrue(marker["sampler_untouched"])
        self.assertEqual(marker["invalidated"], 0)

    async def test_stale_loader_signature_is_invalidated(self):
        workflow = _make_workflow()
        # CLIP loader filename changed → recorded static signature differs.
        workflow["6"] = {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "DIFFERENT.safetensors", "type": "sd3"},
        }
        executor = _FakeExecutor(seeded={"4": "e", "6": "e"})
        marker = await self._marker(executor, _build_seed(), workflow=workflow)
        self.assertEqual(marker["decision"], "match")
        self.assertEqual(marker["invalidated"], 1)
        self.assertIn("6", marker["invalidated_node_ids"].split(","))
        self.assertEqual(executor.caches.outputs.deleted, ["6"])
        # "4" still verified; sampler node "10" untouched.
        self.assertNotIn("10", executor.caches.outputs.deleted)
        self.assertEqual(executor.caches.outputs.set_calls, [])

    async def test_sampler_entries_never_touched(self):
        workflow = _make_workflow()
        workflow["10"]["inputs"]["sampler_name"] = "DIFFERENT_SAMPLER"
        executor = _FakeExecutor(seeded={"4": "e", "6": "e"})
        marker = await self._marker(executor, _build_seed(), workflow=workflow)
        # Sampler static input change must NOT invalidate anything — sampler
        # entries are excluded by construction.
        self.assertNotIn("10", executor.caches.outputs.deleted)
        self.assertEqual(marker["invalidated"], 0)
        self.assertTrue(marker["sampler_untouched"])

    async def test_budget_measured(self):
        executor = _FakeExecutor(seeded={"4": "e", "6": "e"})
        marker = await self._marker(executor, _build_seed())
        self.assertIn("budget_ms", marker)
        self.assertEqual(marker["budget_ms"], 25.0)
        self.assertIsInstance(marker["validate_ms"], float)
        self.assertIsInstance(marker["apply_ms"], float)
        self.assertIsInstance(marker["total_ms"], float)
        self.assertTrue(marker["within_budget"])

    async def test_missing_outputs_cache_is_honest_fallback(self):
        executor = _FakeExecutor()
        executor.caches = types.SimpleNamespace(outputs=None)
        marker = await self._marker(executor, _build_seed())
        self.assertEqual(marker["decision"], "match")
        self.assertEqual(marker["fallback_reason"], "outputs_cache_unavailable")
        self.assertEqual(marker["invalidated"], 0)

    async def test_no_forbidden_state_in_marker(self):
        executor = _FakeExecutor(seeded={"4": "e", "6": "e"})
        marker = await self._marker(executor, _build_seed())
        for key in ("outputs", "latents", "conditioning", "request_id", "cuda", "random_state"):
            self.assertNotIn(key, marker)


# ── 5. Publisher-side build (execute_plan) ────────────────────────────────


class TestPublisherSeedBuild(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        from comfymodal_runtime.execution_seed import snapshot_seed_state_root

        try:
            Path(snapshot_seed_state_root(), "snapshot_seed.json").unlink(missing_ok=True)
        except Exception:
            pass

    async def test_execute_plan_builds_and_persists_seed(self):
        from canonical_execution import build_execution_plan, execute_plan
        from comfymodal_runtime.modal_transport import ModalTransport

        observed: dict[str, Any] = {}

        async def stream(**kwargs: Any):
            observed.update(kwargs)
            yield {"type": "status", "data": {"phase": "restore"}}
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        plan = build_execution_plan(
            _make_workflow(),
            prompt_id="prompt-seed",
            validate=False,
        )
        transport = ModalTransport(prompt_stream_fn=stream)
        result = await execute_plan(plan, transport=transport)

        trace = result.get("trace", {})
        events = trace.get("events", []) if isinstance(trace, dict) else []
        build_events = [e for e in events if isinstance(e, dict) and e.get("name") == "snapshot_seed_build"]
        self.assertEqual(len(build_events), 1, "snapshot_seed_build trace event must be emitted")
        meta = build_events[0].get("metadata", {})
        self.assertEqual(meta.get("built"), 1)
        self.assertEqual(meta.get("schema_version"), 2)
        self.assertEqual(meta.get("topology_available"), 1)
        self.assertEqual(meta.get("persisted"), 1)

        # The deployment-scoped payload must be persisted and re-readable.
        from comfymodal_runtime.execution_seed import read_snapshot_seed_payload

        loaded = read_snapshot_seed_payload()
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["seed_source"], "publisher_plan")
        self.assertTrue(loaded["topology_available"])


# ── 6. Restore-time hydration / minimal fallback ──────────────────────────


class TestRestoreHydration(unittest.TestCase):
    def test_restore_falls_back_to_minimal_without_payload(self):
        from comfymodal_runtime.runtime_bootstrap import RuntimeBootstrap

        bootstrap = RuntimeBootstrap()
        state = bootstrap.restore()
        self.assertTrue(state.snapshot_seed_built)
        self.assertEqual(state.snapshot_seed_source, "startup_minimal")
        self.assertFalse(state.snapshot_seed_topology_available)
        self.assertEqual(state.snapshot_seed_schema_version, 2)
        seed = state.get_snapshot_execution_seed()
        self.assertIsNotNone(seed)
        assert seed is not None
        self.assertEqual(seed.schema_version, 2)
        self.assertEqual(seed.static_node_signatures, ())

    def test_restore_hydrates_persisted_payload(self):
        from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap

        payload = build_snapshot_seed_payload(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
        )
        assert payload is not None
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(persist_snapshot_seed_payload(payload, root=tmp))
            config = BootstrapConfig(
                seed_payload_path=str(Path(tmp, "snapshot_seed.json")),
            )
            bootstrap = RuntimeBootstrap(config)
            state = bootstrap.restore()
        self.assertTrue(state.snapshot_seed_built)
        self.assertEqual(state.snapshot_seed_source, "publisher_plan")
        self.assertTrue(state.snapshot_seed_topology_available)
        self.assertEqual(state.snapshot_seed_schema_version, 2)
        seed = state.get_snapshot_execution_seed()
        self.assertIsNotNone(seed)
        assert seed is not None
        self.assertEqual(seed.schema_version, 2)
        self.assertTrue(seed.static_node_signatures)


# ── 7. Cold/warm request parity ───────────────────────────────────────────


class TestColdWarmRequestParity(unittest.IsolatedAsyncioTestCase):
    async def _run_request(self, executor: RuntimeExecutor, plan: ExecutionPlan, seed: Any) -> ExecutionContext:
        ctx = ExecutionContext(
            request_id="parity",
            metadata={
                "snapshot_execution_seed": seed,
                "deployment_combined_hash": "dep-hash-1",
                "custom_node_generation": "cn-gen-1",
            },
        )
        await executor.execute(plan, context=ctx)
        return ctx

    async def test_cold_and_warm_requests_share_frozen_seed_decision(self):
        # "Cold": hydrate the persisted publisher payload into state once.
        payload = build_snapshot_seed_payload(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
        )
        assert payload is not None
        state = BootstrapState()
        self.assertTrue(state.hydrate_snapshot_seed_payload(payload))
        frozen_seed = state.get_snapshot_execution_seed()
        self.assertIsNotNone(frozen_seed)

        executor = RuntimeExecutor(in_process_runner=lambda p, c: {"result": "ok"})
        plan = _make_plan("wf-hash-1")

        cold_ctx = await self._run_request(executor, plan, frozen_seed)
        warm_ctx = await self._run_request(executor, plan, frozen_seed)

        # Identical decisions across cold (first) and warm (later) requests.
        cold_decision = cold_ctx.metadata.get("snapshot_seed_decision")
        warm_decision = warm_ctx.metadata.get("snapshot_seed_decision")
        self.assertIsNotNone(cold_decision)
        assert cold_decision is not None and warm_decision is not None
        self.assertEqual(cold_decision["status"], warm_decision["status"])
        self.assertEqual(cold_decision["status"], "match")
        self.assertEqual(cold_decision["seed_schema_version"], 2)

        # The request never rebuilt or mutated the shared seed.
        self.assertIs(state.get_snapshot_execution_seed(), frozen_seed)
        self.assertTrue(state.snapshot_seed_built)
        self.assertEqual(state.snapshot_seed_source, "publisher_plan")

    async def test_minimal_fallback_is_parity_stable(self):
        state = BootstrapState()
        seed = state.build_minimal_snapshot_seed_v2(
            workflow_hash="wf-hash-1",
            deployment_combined_hash="dep-hash-1",
        )
        executor = RuntimeExecutor(in_process_runner=lambda p, c: {"result": "ok"})
        plan = _make_plan("wf-hash-1")
        first = await self._run_request(executor, plan, seed)
        second = await self._run_request(executor, plan, seed)
        d1 = first.metadata.get("snapshot_seed_decision")
        d2 = second.metadata.get("snapshot_seed_decision")
        assert d1 is not None and d2 is not None
        self.assertEqual(d1["status"], d2["status"])
        self.assertIs(state.get_snapshot_execution_seed(), seed)


if __name__ == "__main__":
    unittest.main()
