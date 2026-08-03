"""Focused CPU-only tests for the deployment-scoped Step 3 seed publication path.

Covers the repaired restore-plan/seed publication chain end-to-end (no ComfyUI,
no Modal SDK, no CUDA):

  1. ``ModalTransport.publish_restore_plan`` — invokes the v2 handle's
     registered ``publish_restore_plan`` remote with the plan dict and the
     already-built ``snapshot_seed`` payload (passed through, never rebuilt).
  2. Atomic plan+seed persistence — ``RestorePlanPublisher.publish_with_metrics``
     writes ``restore_plan`` and ``snapshot_seed`` into the SAME state file in
     one write/commit; both read back atomically.
  3. Remote-state read/hydration — ``_publish_restore_plan_impl`` mirrors the
     seed to ``snapshot_seed.json`` on the deployment-scoped volume path and
     restore-time hydration reads exactly that payload (``publisher_plan``).
  4. Publication failure fallback — a failing publisher is recorded on the
     trace, nothing is cached, the seed is never claimed persisted, and
     restore-time hydration honestly falls back to ``startup_minimal``.
  5. ``execute_plan`` passes the already-built publisher seed payload to the
     publisher unchanged (no self-validation / rebuild in the remote request).
"""

from __future__ import annotations

import asyncio
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.contracts import (
    ExecutionOptions,
    ExecutionPlan,
    ModelRestoreKey,
    RestorePlan,
    stable_hash,
)
from comfymodal_runtime.execution_seed import (
    build_snapshot_seed_payload,
    read_snapshot_seed_payload,
    snapshot_seed_payload_from_dict,
)
from comfymodal_runtime.restore_plan import (
    RemoteRestorePlanPublisher,
    RestorePlanPublisher,
)
from comfymodal_runtime.runtime_bootstrap import RuntimeBootstrap
from comfymodal_runtime.runtime_executor import (
    ExecutionContext,
    RuntimeExecutor,
    apply_snapshot_seed_to_executor,
)
from comfymodal_runtime.runtime_state import (
    CommitCoordinator,
    MountedStateVolume,
)
from comfymodal_runtime.trace import RuntimeTrace


# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_workflow() -> dict[str, dict[str, Any]]:
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd3.5_large.safetensors"}},
        "6": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "sd3"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["6", 0]}},
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42, "steps": 20, "cfg": 4.5,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                "model": ["4", 0], "positive": ["5", 0],
            },
        },
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["7", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["13", 0]}},
    }


def _make_plan(workflow_hash: str = "wf-hash-1") -> ExecutionPlan:
    return ExecutionPlan(
        workflow=_make_workflow(),
        workflow_hash=workflow_hash,
        source_workflow_hash="src-hash-1",
        output_node_ids=("12", "13"),
        execution_options=ExecutionOptions(production_enabled=False),
        request_metadata={
            "prompt_id": "pub-test",
            "custom_node_generation": "cn-gen-1",
            "deployment_combined_hash": "dep-hash-1",
        },
    )


def _build_seed_payload(workflow: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = build_snapshot_seed_payload(
        workflow or _make_workflow(),
        output_node_ids=["12", "13"],
        workflow_hash="wf-hash-1",
        source_workflow_hash="src-hash-1",
        custom_node_generation="cn-gen-1",
        deployment_combined_hash="dep-hash-1",
    )
    assert payload is not None
    return payload


class _FakeModalVolume:
    """Minimal Modal-volume stand-in: commit/reload counting, no-op bodies."""

    def __init__(self) -> None:
        self.reload_count = 0
        self.commit_count = 0

    def reload(self) -> None:
        self.reload_count += 1

    def commit(self) -> None:
        self.commit_count += 1


# ── 1. Transport invocation ───────────────────────────────────────────────


class TestTransportPublishRestorePlan(unittest.IsolatedAsyncioTestCase):
    """``ModalTransport.publish_restore_plan`` must route the plan dict and the
    already-built seed payload to the registered v2 Modal method."""

    def _fake_handle(self, capture: dict[str, Any]):
        class _Remote:
            async def aio(self, plan_payload, snapshot_seed=None):
                capture["plan_payload"] = plan_payload
                capture["snapshot_seed"] = snapshot_seed
                return {
                    "status": "published",
                    "generation": 7,
                    "state_path": "restore_state.json",
                    "snapshot_seed_present": int(snapshot_seed is not None),
                }

        class _Fn:
            remote = _Remote()

        return types.SimpleNamespace(publish_restore_plan=_Fn())

    async def test_invokes_remote_with_seed_passed_through(self):
        from comfymodal_runtime.modal_transport import ModalTransport

        capture: dict[str, Any] = {}
        transport = ModalTransport(
            v2_handle_factory=lambda **kwargs: self._fake_handle(capture),
        )
        plan = _make_plan()
        seed = _build_seed_payload()
        trace = RuntimeTrace(request_id="transport-test", process="local")

        result = await transport.publish_restore_plan(
            plan.to_dict(),
            workspace={"id": "ws-1"},
            snapshot_seed=seed,
            gpu=None,
            runtime_trace=trace,
        )

        self.assertEqual(result["status"], "published")
        self.assertEqual(result["generation"], 7)
        # The exact payload is passed through — never rebuilt or re-validated.
        self.assertEqual(capture["snapshot_seed"], seed)
        self.assertEqual(capture["plan_payload"]["workflow_hash"], "wf-hash-1")
        event_names = [e.name for e in trace.events]
        self.assertIn("restore_plan_remote_submit", event_names)

    async def test_invokes_remote_without_seed(self):
        from comfymodal_runtime.modal_transport import ModalTransport

        capture: dict[str, Any] = {}
        transport = ModalTransport(
            v2_handle_factory=lambda **kwargs: self._fake_handle(capture),
        )
        result = await transport.publish_restore_plan(
            _make_plan().to_dict(), workspace=None,
        )
        self.assertEqual(capture["snapshot_seed"], None)
        self.assertEqual(result["snapshot_seed_present"], 0)


class TestRemoteRestorePlanPublisherForwarding(unittest.IsolatedAsyncioTestCase):
    """``RemoteRestorePlanPublisher`` forwards the seed through the transport."""

    async def test_seed_forwarded(self):
        captured: dict[str, Any] = {}

        class _FakeTransport:
            async def publish_restore_plan(self, plan_payload, *, workspace=None, snapshot_seed=None):
                captured["plan_payload"] = plan_payload
                captured["workspace"] = workspace
                captured["snapshot_seed"] = snapshot_seed
                return {"status": "published", "generation": 3}

        seed = _build_seed_payload()
        publisher = RemoteRestorePlanPublisher(_FakeTransport(), {"id": "ws-1"})
        plan = RestorePlan(generation=0, source_workflow_hash="wf-modal")
        result = await publisher.publish(plan, snapshot_seed=seed)

        self.assertEqual(result["generation"], 3)
        self.assertEqual(captured["snapshot_seed"], seed)
        self.assertEqual(captured["workspace"], {"id": "ws-1"})
        self.assertEqual(captured["plan_payload"]["source_workflow_hash"], "wf-modal")

    async def test_errors_propagate(self):
        class _BrokenTransport:
            async def publish_restore_plan(self, plan_payload, **kwargs):
                raise RuntimeError("volume unavailable")

        publisher = RemoteRestorePlanPublisher(_BrokenTransport(), None)
        with self.assertRaises(RuntimeError):
            await publisher.publish(
                RestorePlan(generation=0, source_workflow_hash="wf"),
                snapshot_seed=_build_seed_payload(),
            )


# ── 2. Atomic plan+seed persistence ───────────────────────────────────────


class TestAtomicPlanSeedPersistence(unittest.TestCase):
    """Plan + seed land in the SAME state file in ONE write/commit."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.volume = MountedStateVolume(root=self._tmp.name)
        self.coordinator = CommitCoordinator(self.volume, state_path="restore_state.json")
        self.publisher = RestorePlanPublisher(self.coordinator)

    def test_seed_written_atomically_with_plan(self):
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="unet-a", clip_identity="clip-a"),
            source_workflow_hash="wf-1",
        )
        seed = _build_seed_payload()
        result = self.publisher.publish_with_metrics(plan, snapshot_seed=seed)

        self.assertTrue(result["changed"])
        self.assertEqual(result["generation"], 1)
        # Exactly one state write and one commit for plan + seed.
        self.assertEqual(self.coordinator.metrics.write_count, 1)
        self.assertEqual(self.coordinator.metrics.commit_count, 1)

        # Both read back from the SAME authoritative state file.
        read_plan = self.publisher.read_current_plan()
        self.assertIsNotNone(read_plan)
        assert read_plan is not None
        self.assertEqual(read_plan.model_key.unet_identity, "unet-a")
        read_seed = self.publisher.read_snapshot_seed()
        self.assertIsNotNone(read_seed)
        assert read_seed is not None
        self.assertEqual(read_seed.get("seed_source"), "publisher_plan")
        self.assertEqual(read_seed.get("workflow_hash"), "wf-hash-1")
        self.assertEqual(read_seed["seed"]["schema_version"], 2)

    def test_unchanged_publish_does_not_rewrite_seed(self):
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="unet-a"),
            source_workflow_hash="wf-1",
        )
        seed = _build_seed_payload()
        self.publisher.publish(plan, snapshot_seed=seed)
        first_write_count = self.coordinator.metrics.write_count

        # Identical plan + seed → no-op (no extra write/commit).
        result = self.publisher.publish_with_metrics(plan, snapshot_seed=seed)
        self.assertFalse(result["changed"])
        self.assertEqual(self.coordinator.metrics.write_count, first_write_count)
        self.assertEqual(self.coordinator.metrics.commit_count, 1)

    def test_changed_seed_forces_republish(self):
        """A seed that changes while the plan identity is unchanged must still
        be persisted (identity hash comparison covers the full state payload)."""
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="unet-a"),
            source_workflow_hash="wf-1",
        )
        seed_a = _build_seed_payload()
        seed_b = _build_seed_payload()
        seed_b["seed"]["workflow_hash"] = "wf-hash-2"
        seed_b["workflow_hash"] = "wf-hash-2"

        self.publisher.publish(plan, snapshot_seed=seed_a)
        result = self.publisher.publish_with_metrics(plan, snapshot_seed=seed_b)
        self.assertTrue(result["changed"])
        read_seed = self.publisher.read_snapshot_seed()
        assert read_seed is not None
        self.assertEqual(read_seed.get("workflow_hash"), "wf-hash-2")

    def test_read_snapshot_seed_absent_when_none(self):
        plan = RestorePlan(generation=1, source_workflow_hash="wf-1")
        self.publisher.publish(plan)
        self.assertIsNone(self.publisher.read_snapshot_seed())


# ── 3. Remote-state read / hydration ──────────────────────────────────────


class TestRemoteStateReadHydration(unittest.TestCase):
    """``_publish_restore_plan_impl`` mirrors the seed onto the deployment-scoped
    volume path and restore-time hydration reads exactly that payload."""

    def test_impl_writes_seed_file_and_hydrates(self):
        import comfymodal_runtime.modal_app as modal_app
        from comfymodal_runtime.runtime_bootstrap import (
            BootstrapConfig,
            RuntimeBootstrap,
        )

        seed = _build_seed_payload()
        plan = RestorePlan(generation=0, source_workflow_hash="wf-modal")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(modal_app, "_MODAL_RESOURCES", {"runtime_state_volume": _FakeModalVolume()}), \
             patch.object(modal_app, "RUNTIME_STATE_PATH", tmp):
            result = modal_app._publish_restore_plan_impl(plan, snapshot_seed=seed)

            self.assertEqual(result["status"], "published")
            self.assertEqual(result["snapshot_seed_present"], 1)
            self.assertEqual(result["snapshot_seed_file_written"], 1)

            # The standalone seed file on the deployment-scoped state path is a
            # valid schema-v2 publisher payload that restore-time hydration reads.
            self.assertTrue(Path(tmp, "snapshot_seed.json").is_file())
            loaded = read_snapshot_seed_payload(root=tmp)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded["seed_source"], "publisher_plan")
            self.assertTrue(loaded["topology_available"])
            self.assertEqual(loaded["seed"]["schema_version"], 2)
            # Same payload also atomically readable from the plan state file.
            self.assertIsNotNone(
                RestorePlanPublisher(
                    CommitCoordinator(
                        MountedStateVolume(root=tmp),
                        state_path=modal_app.V2_RESTORE_STATE_FILE,
                    )
                ).read_snapshot_seed()
            )

            # Restore-time hydration consumes the mirrored file.
            config = BootstrapConfig(
                seed_payload_path=str(Path(tmp, "snapshot_seed.json")),
            )
            state = RuntimeBootstrap(config).restore()
            self.assertTrue(state.snapshot_seed_built)
            self.assertEqual(state.snapshot_seed_source, "publisher_plan")
            self.assertTrue(state.snapshot_seed_topology_available)
            self.assertEqual(state.snapshot_seed_schema_version, 2)

    def test_async_impl_writes_seed_file(self):
        import comfymodal_runtime.modal_app as modal_app

        seed = _build_seed_payload()
        plan = RestorePlan(generation=0, source_workflow_hash="wf-modal")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(modal_app, "_MODAL_RESOURCES", {"runtime_state_volume": _FakeModalVolume()}), \
             patch.object(modal_app, "RUNTIME_STATE_PATH", tmp):
            result = asyncio.run(
                modal_app._publish_restore_plan_impl_async(plan, snapshot_seed=seed)
            )
            self.assertEqual(result["status"], "published")
            self.assertEqual(result["snapshot_seed_file_written"], 1)
            loaded = read_snapshot_seed_payload(root=tmp)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded["seed_source"], "publisher_plan")

    def test_validation_rejects_wrong_schema(self):
        # Fail-closed: an invalid payload cannot be hydrated as publisher seed.
        bogus = dict(_build_seed_payload())
        bogus["seed"]["schema_version"] = 1
        self.assertIsNone(snapshot_seed_payload_from_dict(bogus))
        self.assertIsNone(snapshot_seed_payload_from_dict(None))


# ── 4. Publication failure fallback ───────────────────────────────────────


class _RaisingPublisher:
    def publish(self, *args, **kwargs):
        raise RuntimeError("runtime-state volume unavailable")


class _SemanticFailurePublisher:
    """Publisher that returns a semantic error (volume write failed remotely)."""

    def publish(self, plan, *, snapshot_seed=None):
        return {
            "status": "error",
            "ok": False,
            "error": "volume commit failed",
            "generation": 0,
        }


class TestPublicationFailureFallback(unittest.IsolatedAsyncioTestCase):
    """execute_plan stays fail-closed when the publisher is unavailable."""

    async def _run_execute_plan(self, publisher: Any, trace: RuntimeTrace) -> dict[str, Any]:
        from canonical_execution import execute_plan

        async def _stream(**kwargs: Any):
            yield {"type": "status", "data": {"phase": "restore"}}
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        from comfymodal_runtime.modal_transport import ModalTransport

        transport = ModalTransport(prompt_stream_fn=_stream)
        return await execute_plan(
            _make_plan(),
            transport=transport,
            restore_publisher=publisher,
            trace=trace,
        )

    async def test_failing_publisher_recorded_and_seed_not_claimed(self):
        import canonical_execution as ce

        ce._reset_restore_publish_cache()
        trace = RuntimeTrace(request_id="pub-fail", process="local")
        result = await self._run_execute_plan(_RaisingPublisher(), trace)

        # Execution completed (the seed is an optimization, not a gate).
        self.assertIn("images", result)
        # The failure is explicit on the trace.
        self.assertIn("restore_publish_error", trace._metadata)
        self.assertTrue(
            str(trace._metadata["restore_publish_error"]).startswith("restore_plan_publish_error"),
            trace._metadata["restore_publish_error"],
        )
        # The seed is NEVER claimed persisted on failure.
        build_events = [e for e in trace.events if e.name == "snapshot_seed_build"]
        self.assertEqual(len(build_events), 1)
        self.assertEqual(build_events[0].metadata.get("persisted"), 0)
        # Nothing was cached from the failed publication.
        with ce._RESTORE_PUBLISH_CACHE_LOCK:
            self.assertEqual(len(ce._RESTORE_PUBLISH_CACHE), 0)

    async def test_semantic_failure_never_claims_seeded_parity(self):
        """A publisher that reports status=error must not mark the seed
        persisted and must not populate the success cache."""
        import canonical_execution as ce

        ce._reset_restore_publish_cache()
        trace = RuntimeTrace(request_id="pub-semfail", process="local")
        result = await self._run_execute_plan(_SemanticFailurePublisher(), trace)

        self.assertIn("images", result)
        build_events = [e for e in trace.events if e.name == "snapshot_seed_build"]
        self.assertEqual(len(build_events), 1)
        self.assertEqual(build_events[0].metadata.get("persisted"), 0)
        with ce._RESTORE_PUBLISH_CACHE_LOCK:
            self.assertEqual(len(ce._RESTORE_PUBLISH_CACHE), 0)

    async def test_bootstrap_falls_back_to_startup_minimal(self):
        """When publication is unavailable, restore() honestly uses
        ``startup_minimal`` and reports it (never seeded parity)."""
        from comfymodal_runtime.runtime_bootstrap import RuntimeBootstrap

        bootstrap = RuntimeBootstrap()
        state = bootstrap.restore()
        self.assertTrue(state.snapshot_seed_built)
        self.assertEqual(state.snapshot_seed_source, "startup_minimal")
        self.assertFalse(state.snapshot_seed_topology_available)
        self.assertEqual(state.snapshot_seed_schema_version, 2)


# ── 5. execute_plan passes the already-built seed unchanged ───────────────


class TestExecutePlanPassesSeedToPublisher(unittest.IsolatedAsyncioTestCase):
    """execute_plan hands the publisher the payload it already built — the
    remote request never rebuilds or re-validates the seed."""

    async def test_publisher_receives_exact_built_payload(self):
        from canonical_execution import _reset_restore_publish_cache, execute_plan
        from comfymodal_runtime.modal_transport import ModalTransport

        _reset_restore_publish_cache()
        captured: dict[str, Any] = {}

        class _CapturingPublisher:
            def publish(self, plan: RestorePlan, *, snapshot_seed=None):
                captured["plan"] = plan
                captured["snapshot_seed"] = snapshot_seed
                return {
                    "status": "published",
                    "generation": 1,
                    "changed": True,
                }

        async def _stream(**kwargs: Any):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        plan = _make_plan()
        transport = ModalTransport(prompt_stream_fn=_stream)
        trace = RuntimeTrace(request_id="pub-pass", process="local")
        result = await execute_plan(
            plan,
            transport=transport,
            restore_publisher=_CapturingPublisher(),
            trace=trace,
        )

        self.assertIn("images", result)
        # The captured payload is the deterministic payload the publisher
        # would build from the same canonical workflow — passed through
        # unchanged (only the volatile built_at timestamp may differ).
        expected = _build_seed_payload()
        self.assertEqual(captured["snapshot_seed"]["seed"], expected["seed"])
        self.assertEqual(captured["snapshot_seed"]["seed_source"], expected["seed_source"])
        self.assertEqual(captured["snapshot_seed"]["schema_version"], expected["schema_version"])
        self.assertEqual(captured["snapshot_seed"]["workflow_hash"], expected["workflow_hash"])
        self.assertIsInstance(captured["plan"], RestorePlan)
        self.assertEqual(captured["plan"].workflow_hash, "wf-hash-1")
        # Trace records the successful publication.
        end_events = [e for e in trace.events if e.name == "restore_plan_publish_end"]
        self.assertEqual(len(end_events), 1)
        self.assertEqual(end_events[0].metadata.get("generation"), 1)
        # Seed is reported persisted (atomic publication succeeded).
        build_events = [e for e in trace.events if e.name == "snapshot_seed_build"]
        self.assertEqual(build_events[0].metadata.get("persisted"), 1)

    async def test_async_publisher_awaited(self):
        from canonical_execution import _reset_restore_publish_cache, execute_plan
        from comfymodal_runtime.modal_transport import ModalTransport

        _reset_restore_publish_cache()
        captured: dict[str, Any] = {}

        class _AsyncCapturingPublisher:
            async def publish(self, plan: RestorePlan, *, snapshot_seed=None):
                captured["snapshot_seed"] = snapshot_seed
                return {"status": "published", "generation": 5, "changed": True}

        async def _stream(**kwargs: Any):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        result = await execute_plan(
            _make_plan(),
            transport=ModalTransport(prompt_stream_fn=_stream),
            restore_publisher=_AsyncCapturingPublisher(),
        )
        self.assertIn("images", result)
        self.assertEqual(captured["snapshot_seed"]["seed_source"], "publisher_plan")


# ── 6. Publication followed by a request on the SAME container ─────────────


class _OutputsCache:
    """Fake executor outputs cache: tracks deletes/sets so tests can prove
    invalidation-only behavior (same shape as test_v2_cold_warm_parity)."""

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


class _SeedApplyFakeExecutor:
    """Fake executor exposing ``caches.outputs`` so the real
    ``apply_snapshot_seed_to_executor`` seam can run a match validation."""

    def __init__(self, seeded: dict[str, Any] | None = None) -> None:
        self.caches = types.SimpleNamespace(outputs=_OutputsCache(seeded=seeded))


def _runner(plan: ExecutionPlan, ctx: ExecutionContext) -> dict[str, Any]:
    """Trivial in-process runner producing a result event (CPU-only)."""
    return {"result": "ok", "trace": RuntimeTrace(process="remote").to_dict()}


class _RecordingExecutorForPublish:
    """Wraps a RuntimeExecutor and captures the context at the chokepoint."""

    def __init__(self, inner: RuntimeExecutor) -> None:
        self._inner = inner
        self.captured_contexts: list[ExecutionContext | None] = []

    def stream(self, plan: ExecutionPlan, *, context: ExecutionContext | None = None):
        self.captured_contexts.append(context)
        return self._inner.stream(plan, context=context)


class TestPublishThenRequestSameContainer(unittest.IsolatedAsyncioTestCase):
    """V2-only correction: the Modal ``publish_restore_plan`` container may
    have already run ``restore()`` before the publisher wrote the seed, so a
    subsequent request can reuse that same container without restore-time
    hydration seeing the newly published payload.  After the remote write
    succeeds, the exact validated payload must be hydrated into the current
    container's ``BootstrapState`` so the next request on the same
    entrypoint sees ``seed_source=publisher_plan``,
    ``snapshot_seed_decision=match`` and a seed-apply
    ``fallback_reason=none``."""

    async def _publish_then_collect_request(self, seed: Any):
        import comfymodal_runtime.modal_app as modal_app

        bootstrap = RuntimeBootstrap()
        real = RuntimeExecutor(in_process_runner=_runner)
        recorder = _RecordingExecutorForPublish(real)
        entrypoint = modal_app.ModalRuntimeEntrypoint(
            bootstrap=bootstrap,
            executor=recorder,  # type: ignore[arg-type]  # duck-typed stream()
        )
        plan = _make_plan()

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(modal_app, "_MODAL_RESOURCES", {"runtime_state_volume": _FakeModalVolume()}), \
             patch.object(modal_app, "RUNTIME_STATE_PATH", tmp), \
             patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", ""):
            result = entrypoint.publish_restore_plan(plan.to_dict(), snapshot_seed=seed)
            self.assertEqual(result["status"], "published")
            self.assertEqual(result["snapshot_seed_present"], int(seed is not None))
            # The exact validated payload is hydrated in-container BEFORE the
            # method returns — never rebuilt from plan_payload or workflow.
            if seed is not None:
                self.assertTrue(bootstrap.state.snapshot_seed_built)
                self.assertEqual(bootstrap.state.snapshot_seed_source, "publisher_plan")
                self.assertTrue(bootstrap.state.snapshot_seed_topology_available)
                self.assertEqual(bootstrap.state.snapshot_seed_schema_version, 2)

            # A subsequent request reuses the SAME entrypoint/container.
            messages = [
                msg
                async for msg in entrypoint.run_plan_stream(
                    plan.to_dict(), request_id="pub-same-container",
                )
            ]
        return bootstrap, recorder, messages, plan

    async def test_request_sees_publisher_seed_match_and_no_seed_apply_fallback(self):
        bootstrap, recorder, messages, plan = await self._publish_then_collect_request(
            _build_seed_payload()
        )

        self.assertTrue(any(m.get("type") == "result" for m in messages))
        ctx = recorder.captured_contexts[0]
        assert ctx is not None
        # The request reads the container state, which now holds the publisher
        # payload (not the startup_minimal fallback from the pre-publication
        # restore).
        self.assertIs(
            ctx.metadata["snapshot_execution_seed"],
            bootstrap.state.snapshot_execution_seed,
        )
        decision = ctx.metadata["snapshot_seed_decision"]
        self.assertEqual(decision["status"], "match")
        self.assertTrue(decision["reuse_enabled"])
        self.assertEqual(decision["reasons"], [])
        self.assertTrue(ctx.metadata["pre_sampler_cache"].seed_reuse_enabled)

        # The request's seed-apply seam (same frozen seed) validates without
        # any fallback: snapshot_graph_seed_apply_end fallback_reason=none.
        marker = await apply_snapshot_seed_to_executor(
            _SeedApplyFakeExecutor(seeded={"4": "e", "6": "e", "7": "e"}),
            bootstrap.state.snapshot_execution_seed,
            workflow=plan.workflow,
            workflow_hash=plan.workflow_hash,
            source_workflow_hash=plan.source_workflow_hash,
            deployment_combined_hash="dep-hash-1",
            custom_node_generation="cn-gen-1",
        )
        self.assertEqual(marker["decision"], "match")
        self.assertEqual(marker["fallback_reason"], "none")
        self.assertEqual(marker["invalidated"], 0)

    async def test_minimal_fallback_retained_when_no_payload(self):
        """Publication without a snapshot_seed payload must NOT hydrate
        anything: the same container stays on the absent/minimal seed path
        (no match decision claimed, no seeded parity)."""
        bootstrap, recorder, messages, _plan = await self._publish_then_collect_request(None)

        self.assertTrue(any(m.get("type") == "result" for m in messages))
        self.assertFalse(bootstrap.state.snapshot_seed_built)
        self.assertEqual(bootstrap.state.snapshot_seed_source, "")
        ctx = recorder.captured_contexts[0]
        assert ctx is not None
        self.assertIsNone(ctx.metadata["snapshot_execution_seed"])
        self.assertNotIn("snapshot_seed_decision", ctx.metadata)
        self.assertFalse(ctx.metadata["pre_sampler_cache"].seed_reuse_enabled)

    def test_invalid_payload_fails_closed_and_never_claims_seeded(self):
        """A payload that fails BootstrapState validation raises and leaves
        the container state untouched — the failure is explicit and never
        claims seeded parity."""
        import comfymodal_runtime.modal_app as modal_app

        bootstrap = RuntimeBootstrap()
        entrypoint = modal_app.ModalRuntimeEntrypoint(bootstrap=bootstrap)
        bogus = dict(_build_seed_payload())
        bogus["seed"]["schema_version"] = 1

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(modal_app, "_MODAL_RESOURCES", {"runtime_state_volume": _FakeModalVolume()}), \
             patch.object(modal_app, "RUNTIME_STATE_PATH", tmp):
            with self.assertRaises(RuntimeError) as ctx:
                entrypoint.publish_restore_plan(_make_plan().to_dict(), snapshot_seed=bogus)
        self.assertIn("snapshot_seed", str(ctx.exception))
        # Fail-closed: nothing was hydrated — no seeded-parity claim.
        self.assertFalse(bootstrap.state.snapshot_seed_built)
        self.assertEqual(bootstrap.state.snapshot_seed_source, "")

    def test_success_emits_remote_hydrated_marker(self):
        """A successful publication emits a concise structured marker for
        post-publication hydration (snapshot_seed_remote_hydrated=1)."""
        import comfymodal_runtime.modal_app as modal_app

        bootstrap = RuntimeBootstrap()
        entrypoint = modal_app.ModalRuntimeEntrypoint(bootstrap=bootstrap)
        trace = RuntimeTrace(request_id="pub-marker", process="remote_method")
        entrypoint._remember_lifecycle_trace(trace)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(modal_app, "_MODAL_RESOURCES", {"runtime_state_volume": _FakeModalVolume()}), \
             patch.object(modal_app, "RUNTIME_STATE_PATH", tmp):
            entrypoint.publish_restore_plan(
                _make_plan().to_dict(), snapshot_seed=_build_seed_payload(),
            )

        hydrated = [e for e in trace.events if e.name == "snapshot_seed_remote_hydrated"]
        self.assertEqual(len(hydrated), 1)
        self.assertEqual(hydrated[0].metadata.get("snapshot_seed_remote_hydrated"), 1)
        self.assertEqual(hydrated[0].metadata.get("seed_source"), "publisher_plan")
        self.assertEqual(hydrated[0].metadata.get("schema_version"), 2)
        errors = [e for e in trace.events if e.name == "snapshot_seed_remote_hydrate_error"]
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
